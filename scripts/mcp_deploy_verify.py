"""Read-only, fail-closed production verification; never deploys or issues keys."""
from __future__ import annotations

import argparse
import asyncio
from contextlib import asynccontextmanager
import json
import logging
import os
from pathlib import Path
import re
import stat
import subprocess
from urllib.parse import urlsplit

import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

ALL_TOOLS = frozenset(('radar_status', 'trackers_list', 'tracker_get', 'releases_list', 'history_list',
    'upgrades_list', 'upgrade_get', 'inventory_list', 'inventory_summary', 'job_get', 'tracker_check',
    'tracker_probe', 'inventory_sync', 'tracker_create', 'tracker_update', 'tracker_set_enabled',
    'tracker_delete', 'upgrade_save_review'))


def validate_baseline(path: Path) -> dict:
    data = json.loads(path.read_text())
    if stat.S_IMODE(path.stat().st_mode) != 0o600:
        raise ValueError('Baseline must be private.')
    for field in ('approved_sha', 'head_before'):
        if not isinstance(data.get(field), str) or not re.fullmatch('[a-f0-9]{40}', data[field]):
            raise ValueError('Missing revision evidence.')
    if (not isinstance(data.get('image_ids_before'), list) or not data['image_ids_before']
            or not all(isinstance(item, str) and re.fullmatch(r'sha256:[a-f0-9]{64}', item) for item in data['image_ids_before'])):
        raise ValueError('Missing prior image evidence.')
    for field in ('maintenance_authorised', 'git_workflow_verified', 'route_verified'):
        if data.get(field) is not True:
            raise ValueError('Required rollout authority/evidence missing.')
    if data.get('backup_integrity') != 'ok' or data.get('backup_mode') != '0600':
        raise ValueError('Verified private backup required.')
    return data


@asynccontextmanager
async def session(url, key, *, host=None):
    headers = {'Authorization': 'Bearer ' + key}
    if host:
        headers['Host'] = host
    async with httpx2.AsyncClient(headers=headers, trust_env=False, timeout=30) as http:
        async with streamable_http_client(url, http_client=http) as streams:
            async with ClientSession(*streams) as client:
                await client.initialize()
                yield client


def read_command(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=30).stdout.strip()


async def verify(baseline, public_url, mcp_url, key, revoked, expected):
    approved = baseline['approved_sha']
    if read_command('git', 'rev-parse', 'HEAD') != approved:
        raise ValueError('Checkout revision mismatch.')
    if read_command('git', 'status', '--porcelain', '--untracked-files=no'):
        raise ValueError('Tracked production checkout is not clean.')
    for name in ('radar', 'scheduler', 'portainer-worker', 'mcp'):
        container = read_command('docker', 'compose', '--profile', 'mcp', 'ps', '-q', name)
        if not container or '\n' in container:
            raise ValueError('Missing or ambiguous service.')
        state = json.loads(read_command('docker', 'inspect', '--format', '{{json .State}}', container))
        image = read_command('docker', 'inspect', '--format', '{{.Image}}', container)
        revision = read_command('docker', 'image', 'inspect', '--format', '{{index .Config.Labels "org.opencontainers.image.revision"}}', image)
        if state.get('Status') != 'running' or revision != approved:
            raise ValueError('Runtime revision/state mismatch.')
        if name in ('radar', 'mcp') and state.get('Health', {}).get('Status') != 'healthy':
            raise ValueError('Service is not healthy.')
    async with httpx2.AsyncClient(trust_env=False, timeout=30) as http:
        health = await http.get(public_url.rstrip('/') + '/healthz')
        health.raise_for_status()
        if health.json().get('commit') != approved or health.json().get('status') != 'ok':
            raise ValueError('Live revision mismatch.')
        payload = {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
            'protocolVersion': '2025-03-26', 'capabilities': {}, 'clientInfo': {'name': 'radar-verifier', 'version': '1'}}}
        for token in (None, revoked):
            headers = {'Accept': 'application/json, text/event-stream'}
            if token:
                headers['Authorization'] = 'Bearer ' + token
            if (await http.post(mcp_url, headers=headers, json=payload)).status_code != 401:
                raise ValueError('Missing/revoked authentication was not rejected.')
    async with session(mcp_url, key) as client:
        if {tool.name for tool in (await client.list_tools()).tools} != expected:
            raise ValueError('Unexpected scope/role tool set.')
        result = await client.call_tool('radar_status', {})
        if result.is_error or result.structured_content.get('commit') != approved:
            raise ValueError('Live MCP read revision mismatch.')
    return {'approved_sha': approved, 'checkout_matches': True, 'service_revisions_match': True,
        'services_healthy': True, 'missing_key_rejected': True, 'revoked_key_rejected': True,
        'sdk_read_passed': True, 'exact_tool_set_passed': True, 'backup_preflight_recorded': True,
        'read_only_verification': True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--record-dir', required=True)
    args = parser.parse_args()
    logging.disable(logging.CRITICAL)
    try:
        directory = Path(args.record_dir)
        baseline = validate_baseline(directory / 'baseline.json')
        values = [os.environ.get(name, '') for name in ('RADAR_PUBLIC_URL', 'RADAR_MCP_URL', 'RADAR_MCP_KEY', 'RADAR_MCP_REVOKED_KEY')]
        if not all(values) or any(urlsplit(url).scheme != 'https' or urlsplit(url).username
                                  or urlsplit(url).query or urlsplit(url).fragment for url in values[:2]):
            raise ValueError('Missing protected verification inputs.')
        expected = json.loads(os.environ.get('RADAR_MCP_EXPECTED_TOOLS', json.dumps(sorted(ALL_TOOLS))))
        if not isinstance(expected, list) or not expected or not all(isinstance(name, str) and name in ALL_TOOLS for name in expected):
            raise ValueError('Invalid expected tool set.')
        result = asyncio.run(verify(baseline, *values, set(expected)))
        descriptor = os.open(directory / 'verification.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'w') as output:
            json.dump(result, output, indent=2)
        print('PASS read-only production revision, services, SDK scopes and missing/revoked authentication checks.')
        return 0
    except Exception:
        print('Verification refused or failed. Check protected inputs, baseline and live state privately; no deployment performed.')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
