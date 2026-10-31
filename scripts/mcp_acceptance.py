"""Disposable, loopback-only Compose acceptance. Never reads deployment .env."""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import logging
import os
from pathlib import Path
import re
import secrets
import shutil
import sqlite3
import stat
import subprocess
import sys
import tarfile
import tempfile

import httpx2

from mcp_deploy_verify import ALL_TOOLS, session

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
BASELINE = '6624d4d2a2f03956a0cfc2397e064f461aaef6a1'
PROJECT = 'srr01-4-acceptance'


def run(*args, env=None, timeout=900):
    result = subprocess.run(args, cwd=ROOT, env=env, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError('Acceptance command failed: ' + args[0])
    return result.stdout.strip()


class Acceptance:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.nonce = secrets.token_hex(8)
        self.image = f'radar-mcp-acceptance:{self.nonce}'
        self.old_image = f'radar-mcp-baseline:{self.nonce}'
        self.password = secrets.token_urlsafe(24)
        from radar.auth import hash_password
        self.env = {name: value for name, value in os.environ.items() if name in
                    ('PATH', 'HOME', 'DOCKER_HOST', 'DOCKER_CONTEXT', 'DOCKER_CONFIG', 'XDG_RUNTIME_DIR', 'TMPDIR')}
        self.env.update(COMPOSE_PROJECT_NAME=PROJECT, COMPOSE_DISABLE_ENV_FILE='1',
            COMPOSE_FILE=str(ROOT / 'docker-compose.yml') + os.pathsep + str(self.directory / 'override.yml'),
            COMPOSE_PROFILES='', ADMIN_USERNAME='admin', ADMIN_EMAIL='admin@example.invalid',
            ADMIN_PASSWORD_HASH=hash_password(self.password), SECRET_KEY=secrets.token_urlsafe(48),
            ENCRYPTION_KEY=base64.urlsafe_b64encode(os.urandom(32)).decode(), GITHUB_TOKEN='',
            RADAR_ACCEPTANCE_PASSWORD=self.password, RADAR_BUILD_COMMIT=run('git', 'rev-parse', 'HEAD'),
            RADAR_MCP_ALLOWED_HOSTS='radar.example.invalid', RADAR_MCP_ALLOW_HTTP='true',
            RADAR_MCP_PUBLIC_URL='http://radar.example.invalid/mcp')
        (self.directory / 'ssh').mkdir()
        envfile = self.directory / 'dummy.env'
        envfile.write_text('')
        envfile.chmod(0o600)
        self.env['COMPOSE_ENV_FILES'] = str(envfile)
        self.base = ['docker', 'compose', '--env-file', str(envfile)]
        self.override(self.image)

    def override(self, image):
        data = 'services:\n'
        for name in ('radar', 'scheduler', 'portainer-worker', 'mcp'):
            data += f'  {name}:\n    image: {image}\n    pull_policy: never\n'
            data += '    labels:\n      io.release-radar.acceptance: ' + json.dumps(self.nonce) + '\n'
            data += '    build:\n      context: ' + json.dumps(str(ROOT)) + '\n      labels:\n        io.release-radar.acceptance: ' + json.dumps(self.nonce) + '\n'
            data += '    volumes: !override\n      - radar-data:/data\n      - ' + json.dumps(str(self.directory / 'ssh') + ':/ssh:ro') + '\n'
            if name in ('radar', 'mcp'):
                port = 8080 if name == 'radar' else 8081
                data += f'    ports: !override\n      - "127.0.0.1::{port}"\n'
            if name == 'radar':
                data += '    environment:\n      RADAR_ACCEPTANCE_PASSWORD: "${RADAR_ACCEPTANCE_PASSWORD}"\n'
        data += 'volumes:\n  radar-data:\n    labels:\n      io.release-radar.acceptance: ' + json.dumps(self.nonce) + '\n'
        (self.directory / 'override.yml').write_text(data)

    def ownership(self, *, empty=False):
        for kind, listing in (('container', ['ps', '-aq']), ('volume', ['volume', 'ls', '-q'])):
            identifiers = run('docker', *listing, '--filter', 'label=com.docker.compose.project=' + PROJECT, env=self.env).splitlines()
            if empty and identifiers:
                raise ValueError('Acceptance project already exists; refusing reuse.')
            for identifier in identifiers:
                template = '{{index .Config.Labels "io.release-radar.acceptance"}}' if kind == 'container' else '{{index .Labels "io.release-radar.acceptance"}}'
                if run('docker', kind, 'inspect', '--format', template, identifier, env=self.env) != self.nonce:
                    raise ValueError('Foreign acceptance resource; refusing mutation.')

    def compose(self, *args):
        self.ownership()
        if args[0] in ('build', 'up', 'restart', 'stop', 'run', 'rm', 'down'):
            print('Isolated Compose stage: ' + args[0], flush=True)
        return run(*self.base, *args, env=self.env)

    def execute(self, code):
        return self.compose('exec', '-T', 'radar', 'python', '-c', code)

    def url(self, service, port):
        address = self.compose('port', service, str(port))
        if not address.startswith('127.0.0.1:') or '\n' in address:
            raise ValueError('Acceptance port is not exclusively loopback.')
        return 'http://' + address

    def browser_key(self, web):
        def csrf(response):
            return re.search(r'name="csrf_token"\s+value="([^"]+)"', response.text).group(1)
        with httpx2.Client(trust_env=False, follow_redirects=True, timeout=30) as browser:
            token = csrf(browser.get(web + '/login'))
            response = browser.post(web + '/login', data={'csrf_token': token, 'username': 'admin', 'password': self.password})
            response.raise_for_status()
            token = csrf(browser.get(web + '/profile'))
            response = browser.post(web + '/profile/mcp-keys', data={'csrf_token': token,
                'current_password': self.password, 'label': 'isolated acceptance',
                'scopes': ['read', 'operations:run', 'trackers:write', 'upgrades:write'], 'expires_days': '90'})
            response.raise_for_status()
            key = re.search(r'srr_[a-f0-9]{16}_[A-Za-z0-9_-]{43}', response.text).group()
            return key, browser.cookies, token

    async def smoke(self, url, key, tracker_id=None, *, busy=False):
        async with session(url + '/mcp', key, host='radar.example.invalid') as client:
            if {tool.name for tool in (await client.list_tools()).tools} != ALL_TOOLS:
                raise ValueError('Incorrect tool set.')
            result = await client.call_tool('radar_status', {})
            if result.is_error or result.structured_content['commit'] != self.env['RADAR_BUILD_COMMIT']:
                raise ValueError('MCP build revision mismatch.')
            if busy:
                result = await client.call_tool('inventory_sync', {})
                if not result.is_error or 'awaiting operator recovery' not in result.model_dump_json():
                    raise ValueError('Stale durable ownership was reclaimed.')
                return tracker_id
            if tracker_id is None:
                result = await client.call_tool('tracker_create', {'tracker': {'name': 'Acceptance', 'repository': 'example/acceptance', 'enabled': False}})
                if result.is_error:
                    raise ValueError('Tracker create failed.')
                tracker_id = result.structured_content['tracker_id']
                result = await client.call_tool('tracker_update', {'tracker_id': tracker_id, 'changes': {'notes': 'persistent fixture'}})
                if result.is_error:
                    raise ValueError('Tracker update failed.')
            result = await client.call_tool('tracker_get', {'tracker_id': tracker_id})
            if result.is_error or result.structured_content['notes'] != 'persistent fixture':
                raise ValueError('Persistent tracker missing.')
            return tracker_id

    def healthy(self, commit):
        for name in ('radar', 'scheduler', 'portainer-worker'):
            identifier = self.compose('ps', '-q', name)
            if run('docker', 'inspect', '--format', '{{.State.Status}}', identifier, env=self.env) != 'running':
                raise ValueError('Worker not running.')
        with httpx2.Client(trust_env=False, timeout=30) as http:
            result = http.get(self.url('radar', 8080) + '/healthz')
            result.raise_for_status()
            if result.json().get('commit') != commit:
                raise ValueError('Web revision mismatch.')

    def exercise(self):
        self.ownership(empty=True)
        config = json.loads(self.compose('config', '--format', 'json'))
        if 'mcp' in self.compose('config', '--services').splitlines():
            raise ValueError('Optional profile enabled by default.')
        for name in ('radar', 'mcp'):
            if any(item.get('host_ip') != '127.0.0.1' for item in config['services'].get(name, {}).get('ports', [])):
                raise ValueError('Non-loopback acceptance binding.')
        print('Building isolated candidate image.', flush=True)
        self.compose('build', 'radar')
        self.compose('up', '-d', '--no-build', '--wait', '--wait-timeout', '180')
        self.healthy(self.env['RADAR_BUILD_COMMIT'])
        self.env['COMPOSE_PROFILES'] = 'mcp'
        self.compose('up', '-d', '--no-build', '--wait', '--wait-timeout', '180')
        web, mcp = self.url('radar', 8080), self.url('mcp', 8081)
        key, cookies, csrf = self.browser_key(web)
        tracker_id = asyncio.run(self.smoke(mcp, key))
        self.compose('restart', 'mcp', 'radar')
        self.compose('up', '-d', '--no-build', '--wait', '--wait-timeout', '180')
        asyncio.run(self.smoke(self.url('mcp', 8081), key, tracker_id))
        self.compose('stop', 'mcp')
        self.execute("from radar.db import transaction,utcnow; c=transaction(immediate=True); conn=c.__enter__(); conn.execute(\"INSERT INTO mcp_operation_leases(id,key_id,user_id,tool,created_at) SELECT 'stale',id,user_id,'inventory_sync','1900-01-01' FROM mcp_keys LIMIT 1\"); c.__exit__(None,None,None)")
        self.compose('up', '-d', '--no-build', '--wait', '--wait-timeout', '180')
        asyncio.run(self.smoke(self.url('mcp', 8081), key, tracker_id, busy=True))
        self.compose('stop', 'mcp')
        self.compose('run', '--rm', '--no-deps', 'mcp', 'python', 'scripts/mcp_recover_leases.py', '--confirm-workers-stopped')
        if self.execute("from radar.db import connect; c=connect(); print(c.execute('SELECT COUNT(*) FROM mcp_operation_leases').fetchone()[0]); c.close()") != '0':
            raise ValueError('Offline recovery failed.')
        self.env['COMPOSE_PROFILES'] = ''
        runner = self.directory / 'runner'
        (runner / 'scripts').mkdir(parents=True)
        for name in ('backup.sh', 'restore.sh'):
            shutil.copyfile(ROOT / 'scripts' / name, runner / 'scripts' / name)
        self.ownership()
        run('bash', str(runner / 'scripts/backup.sh'), 'acceptance', str(runner / 'backups'), env=self.env)
        backup = runner / 'backups/radar-acceptance.db'
        if stat.S_IMODE(backup.stat().st_mode) != 0o600:
            raise ValueError('Backup permissions incorrect.')
        with sqlite3.connect('file:' + str(backup) + '?mode=ro', uri=True) as conn:
            if conn.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('Backup integrity failed.')
        self.ownership()
        run('bash', str(runner / 'scripts/restore.sh'), str(backup), '--confirm', env=self.env)
        self.healthy(self.env['RADAR_BUILD_COMMIT'])
        print('Building explicit archived baseline for additive-schema rollback.', flush=True)
        archive, old = self.directory / 'baseline.tar', self.directory / 'baseline'
        run('git', 'archive', '--format=tar', '--output=' + str(archive), BASELINE)
        old.mkdir()
        with tarfile.open(archive) as source:
            source.extractall(old, filter='data')
        run('docker', 'build', '--label', 'io.release-radar.acceptance=' + self.nonce,
            '--build-arg', 'VCS_REF=' + BASELINE, '--tag', self.old_image, str(old), env=self.env)
        self.override(self.old_image)
        self.compose('up', '-d', '--no-build', '--wait', '--wait-timeout', '180', 'radar', 'scheduler', 'portainer-worker')
        self.healthy(BASELINE)
        self.override(self.image)
        self.env['COMPOSE_PROFILES'] = 'mcp'
        self.compose('up', '-d', '--no-build', '--wait', '--wait-timeout', '180')
        web, mcp = self.url('radar', 8080), self.url('mcp', 8081)
        asyncio.run(self.smoke(mcp, key, tracker_id))
        with httpx2.Client(cookies=cookies, trust_env=False, timeout=30) as browser:
            response = browser.post(web + '/profile/mcp-keys/' + key.split('_')[1] + '/revoke', data={'csrf_token': csrf})
            if response.status_code != 302:
                raise ValueError('Browser revocation failed.')
            response = browser.post(mcp + '/mcp', headers={'Host': 'radar.example.invalid', 'Authorization': 'Bearer ' + key}, json={})
            if response.status_code != 401:
                raise ValueError('Revocation did not invalidate live bearer.')
            if browser.post(mcp + '/mcp', headers={'Host': 'radar.example.invalid'}, json={}).status_code != 401:
                raise ValueError('Missing bearer accepted.')
        self.compose('stop', 'mcp')
        self.compose('rm', '-f', 'mcp')
        self.env['COMPOSE_PROFILES'] = ''
        self.compose('up', '-d', '--no-build', '--wait', '--wait-timeout', '180')
        self.healthy(self.env['RADAR_BUILD_COMMIT'])
        sizes = {name: int(run('docker', 'image', 'inspect', '--format', '{{.Size}}', image, env=self.env))
                 for name, image in (('candidate_bytes', self.image), ('baseline_bytes', self.old_image))}
        print(json.dumps({'passed': True, 'checks': ['profile_off_on', 'sdk_read_write', 'persistence_restart',
            'durable_restart_offline_recovery', 'backup_integrity_0600', 'isolated_restore',
            'baseline_additive_rollback', 'browser_live_revocation', 'profile_removal'], **sizes}), flush=True)

    def cleanup(self):
        self.ownership()
        self.env['COMPOSE_PROFILES'] = 'mcp'
        self.compose('down', '--volumes', '--remove-orphans')
        for image in (self.image, self.old_image):
            found = subprocess.run(['docker', 'image', 'inspect', '--format', '{{index .Config.Labels "io.release-radar.acceptance"}}', image],
                                   env=self.env, capture_output=True, text=True, timeout=30)
            if found.returncode == 0 and found.stdout.strip() == self.nonce:
                run('docker', 'image', 'rm', image, env=self.env)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True)
    args = parser.parse_args()
    if args.project != PROJECT:
        print('Refused: only the dedicated acceptance project is allowed.')
        return 2
    logging.disable(logging.CRITICAL)
    temp_root = os.environ.get('TMPDIR') or tempfile.gettempdir()
    try:
        with tempfile.TemporaryDirectory(prefix='radar-mcp-acceptance-', dir=temp_root) as directory:
            acceptance = Acceptance(directory)
            # Refuse pre-existing resources before entering cleanup ownership.
            acceptance.ownership(empty=True)
            try:
                acceptance.exercise()
            finally:
                acceptance.cleanup()
        return 0
    except (ValueError, RuntimeError) as exc:
        print('FAIL isolated MCP acceptance: ' + str(exc) + ' No deployment performed.')
        return 1
    except Exception:
        print('FAIL isolated MCP acceptance; no deployment performed. Inspect local stages privately.')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
