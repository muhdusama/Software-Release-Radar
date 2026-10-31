"""Real subprocess protocol, browser lifecycle and operator-script refusals."""
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import unittest
from contextlib import asynccontextmanager
from unittest.mock import patch

import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

import test_mcp_auth as fixtures
from radar.db import transaction


class MCPHTTPTests(unittest.IsolatedAsyncioTestCase):
    setUp = fixtures.MCPAuthTests.setUp
    login = fixtures.MCPAuthTests.login

    async def asyncSetUp(self):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        self.url = f'http://127.0.0.1:{port}/mcp'
        env = {**os.environ, 'RADAR_MCP_ALLOWED_HOSTS': f'127.0.0.1:{port}',
               'RADAR_MCP_ALLOW_HTTP': 'true', 'RADAR_MCP_ALLOWED_ORIGINS': '',
               'RADAR_MCP_FORWARDED_ALLOW_IPS': '', 'RADAR_MCP_PUBLIC_URL': self.url}
        self.process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'radar.mcp_server:build_app',
            '--factory', '--host', '127.0.0.1', '--port', str(port), '--no-access-log',
            '--no-proxy-headers', '--limit-concurrency', '32'], env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addAsyncCleanup(self.stop_server)
        async with httpx2.AsyncClient(trust_env=False, timeout=2) as http:
            for _ in range(150):
                self.assertIsNone(self.process.poll(), 'Local MCP fixture exited early')
                try:
                    if (await http.get(self.url.replace('/mcp', '/healthz'))).status_code == 200:
                        break
                except httpx2.ConnectError:
                    pass
                await asyncio.sleep(.02)
            else:
                self.fail('Local MCP fixture not ready')

    async def stop_server(self):
        self.process.terminate()
        try:
            await asyncio.to_thread(self.process.wait, 5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            await asyncio.to_thread(self.process.wait, 5)

    @asynccontextmanager
    async def session(self, token):
        async with httpx2.AsyncClient(headers={'Authorization': 'Bearer ' + token}, trust_env=False) as http:
            async with streamable_http_client(self.url, http_client=http) as streams:
                async with ClientSession(*streams) as client:
                    result = await client.initialize()
                    self.assertRegex(result.protocol_version, r'^\d{4}-\d{2}-\d{2}$')
                    self.assertEqual(result.server_info.name, 'Software Release Radar')
                    yield client

    async def test_browser_key_full_protocol_fresh_role_and_live_revocation(self):
        csrf = self.login()
        response = self.client.post('/profile/mcp-keys', data={'csrf_token': csrf,
            'current_password': 'correct-horse-battery', 'label': 'real SDK', 'expires_days': '90',
            'scopes': ['read', 'operations:run', 'trackers:write', 'upgrades:write']})
        self.assertEqual(response.status_code, 200)
        token = re.search(r'srr_[a-f0-9]{16}_[A-Za-z0-9_-]{43}', response.get_data(as_text=True)).group()
        self.assertNotIn(token, self.client.get('/profile').get_data(as_text=True))
        expected = {'radar_status', 'trackers_list', 'tracker_get', 'releases_list', 'history_list',
            'upgrades_list', 'upgrade_get', 'inventory_list', 'inventory_summary', 'job_get',
            'tracker_check', 'tracker_probe', 'inventory_sync', 'tracker_create', 'tracker_update',
            'tracker_set_enabled', 'tracker_delete', 'upgrade_save_review'}
        async with self.session(token) as client:
            self.assertEqual({tool.name for tool in (await client.list_tools()).tools}, expected)
            status = await client.call_tool('radar_status', {})
            self.assertFalse(status.is_error)
            self.assertEqual(status.structured_content['name'], 'Software Release Radar')
            created = await client.call_tool('tracker_create', {'tracker': {'name': 'HTTP test', 'repository': 'example/project'}})
            self.assertFalse(created.is_error)
            tracker_id = created.structured_content['tracker_id']
            strict = await client.call_tool('tracker_get', {'tracker_id': True})
            self.assertTrue(strict.is_error)
            with transaction() as conn:
                conn.execute("UPDATE users SET role='user' WHERE id=?", (self.admin,))
            self.assertEqual(len((await client.list_tools()).tools), 7)
            hidden = await client.call_tool('tracker_delete', {'tracker_id': tracker_id, 'confirm': True})
            unknown = await client.call_tool('absent_tool', {})
            self.assertEqual(hidden.model_dump(), unknown.model_dump())
        with transaction() as conn:
            conn.execute("UPDATE users SET role='admin' WHERE id=?", (self.admin,))
        self.assertEqual(self.client.post('/profile/mcp-keys/' + token.split('_')[1] + '/revoke',
            data={'csrf_token': csrf}).status_code, 302)
        async with httpx2.AsyncClient(trust_env=False) as http:
            payload = {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
                'protocolVersion': '2025-03-26', 'capabilities': {}, 'clientInfo': {'name': 'fixture', 'version': '1'}}}
            headers = {'Accept': 'application/json, text/event-stream', 'Authorization': 'Bearer ' + token}
            self.assertEqual((await http.post(self.url, headers=headers, json=payload)).status_code, 401)
            self.assertEqual((await http.post(self.url, json=payload)).status_code, 401)
            self.assertEqual((await http.post(self.url, headers={'Host': 'wrong.invalid'}, json=payload)).status_code, 421)
            self.assertEqual((await http.post(self.url, headers={'Origin': 'https://wrong.invalid'}, json=payload)).status_code, 403)

    async def test_operator_scripts_refuse_unsafe_or_missing_inputs_without_echo(self):
        canary = 'srr_0000000000000000_' + 'Z' * 43
        env = {**os.environ, 'RADAR_MCP_KEY': canary, 'RADAR_MCP_REVOKED_KEY': canary,
               'RADAR_PUBLIC_URL': '', 'RADAR_MCP_URL': '', 'DOCKER_HOST': 'unix:///nonexistent-fixture'}
        commands = [
            [sys.executable, 'scripts/mcp_acceptance.py', '--project', 'production'],
            [sys.executable, 'scripts/mcp_deploy_verify.py', '--record-dir', self.tmp.name]]
        for command in commands:
            result = await asyncio.to_thread(subprocess.run, command, env=env, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertNotIn(canary, result.stdout + result.stderr)
        spec = importlib.util.spec_from_file_location('deploy_verify', 'scripts/mcp_deploy_verify.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        baseline = Path(self.tmp.name) / 'baseline.json'
        baseline.write_text(json.dumps({'approved_sha': 'a' * 40, 'maintenance_authorised': 'true'}))
        with self.assertRaises(ValueError):
            module.validate_baseline(baseline)

    async def test_acceptance_fixture_uses_application_password_format(self):
        from radar.auth import verify_password
        with patch.object(sys, 'path', [str(Path('scripts').resolve()), *sys.path]):
            from mcp_acceptance import Acceptance
        fixture = Acceptance(self.tmp.name)
        self.assertTrue(verify_password(fixture.password, fixture.env['ADMIN_PASSWORD_HASH']))

    async def test_ci_checkout_contains_archived_rollback_baseline(self):
        import tempfile
        root = Path(__file__).resolve().parents[1]
        workflow = (root / '.github/workflows/ci.yml').read_text().split('  docker-acceptance:', 1)[1]
        checkout = workflow.split('- name: Run the real public first-run setup', 1)[0]
        with tempfile.TemporaryDirectory() as directory:
            command = ['git', 'clone', '--quiet']
            if 'fetch-depth: 0' not in checkout:
                command += ['--depth', '1']
            command += [root.as_uri(), directory + '/checkout']
            await asyncio.to_thread(subprocess.run, command, check=True, capture_output=True, timeout=30)
            result = await asyncio.to_thread(subprocess.run, ['git', '-C', directory + '/checkout', 'archive',
                '--format=tar', '-o', os.devnull, '6624d4d2a2f03956a0cfc2397e064f461aaef6a1'], capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, 'CI checkout must contain the explicit rollback baseline')

    async def test_restore_refuses_live_optional_mcp_before_any_mutation(self):
        directory = Path(self.tmp.name)
        docker = directory / 'docker'
        docker.write_text('#!' + sys.executable + '\nimport sys\na=sys.argv[1:]\n'
            'if a in (["info"], ["compose","version"]): pass\n'
            'elif "config" in a: print("radar\\nmcp")\n'
            'elif "ps" in a: print("fixture-mcp")\n'
            'elif "inspect" in a: print("running")\n'
            'else: sys.exit(99)\n')
        docker.chmod(0o700)
        backup = directory / 'fixture.db'
        backup.write_bytes(b'not read: restore must refuse first')
        env = {**os.environ, 'PATH': str(directory) + os.pathsep + os.environ['PATH']}
        result = await asyncio.to_thread(subprocess.run, ['bash', 'scripts/restore.sh', str(backup), '--confirm'],
            env=env, capture_output=True, text=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('MCP', result.stderr)


if __name__ == '__main__':
    unittest.main()
