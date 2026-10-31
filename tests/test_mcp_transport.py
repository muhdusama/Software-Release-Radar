"""MCP transport fences are independent of browser sessions and proxy guesses."""
import asyncio
import base64
import json
import os
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx2

from radar.auth import hash_password
from radar.db import connect, init_db, transaction
from radar.mcp_auth import create_key
from radar import mcp_server


class MCPTransportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = patch.dict(os.environ, {
            'RADAR_DB': str(Path(self.tmp.name) / 'test.db'),
            'ADMIN_PASSWORD_HASH': hash_password('correct-horse-battery', iterations=1000),
            'ADMIN_USERNAME': 'admin', 'SECRET_KEY': 'test-secret-key-that-is-long-enough',
            'ENCRYPTION_KEY': base64.urlsafe_b64encode(os.urandom(32)).decode(),
            'RADAR_MCP_ALLOWED_HOSTS': 'radar.example.invalid', 'RADAR_MCP_ALLOWED_ORIGINS': '',
            'RADAR_MCP_FORWARDED_ALLOW_IPS': '', 'RADAR_MCP_ALLOW_HTTP': 'false',
            'RADAR_MCP_PUBLIC_URL': 'https://radar.example.invalid/mcp',
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        init_db()
        with connect() as conn:
            owner = conn.execute("SELECT id FROM users WHERE username='admin'").fetchone()[0]
        _, self.key = create_key(owner, 'correct-horse-battery', 'transport', ['read'])
        self.app = mcp_server.build_app()
        self.lifespan_input, self.lifespan_output = asyncio.Queue(), asyncio.Queue()
        self.lifespan = asyncio.create_task(self.app({'type': 'lifespan'}, self.lifespan_input.get, self.lifespan_output.put))
        await self.lifespan_input.put({'type': 'lifespan.startup'})
        self.assertEqual((await self.lifespan_output.get())['type'], 'lifespan.startup.complete')

    async def asyncTearDown(self):
        await self.lifespan_input.put({'type': 'lifespan.shutdown'})
        self.assertEqual((await self.lifespan_output.get())['type'], 'lifespan.shutdown.complete')
        await self.lifespan

    async def request(self, path='/mcp', *, headers=None, content=b'{}', method='POST', scheme='https', client=None):
        transport = httpx2.ASGITransport(app=self.app, client=client or ('127.0.0.1', 1234))
        async with httpx2.AsyncClient(transport=transport, base_url=f'{scheme}://radar.example.invalid') as http:
            return await http.request(method, path, headers=headers or {}, content=content)

    async def test_host_origin_https_and_custom_health(self):
        for host in ('', 'localhost', 'bad.example.invalid'):
            self.assertEqual((await self.request('/healthz', method='GET', headers={'Host': host})).status_code, 421)
        self.assertEqual((await self.request('/healthz', method='GET', headers={'Origin': 'https://evil.invalid'})).status_code, 403)
        health = await self.request('/healthz', method='GET', scheme='http')
        self.assertEqual(health.json(), {'status': 'ok'})
        for path in ('/mcp', '/.well-known/oauth-protected-resource/mcp'):
            self.assertEqual((await self.request(path, scheme='http', headers={'X-Forwarded-Proto': 'https', 'Host': 'localhost'})).status_code, 421)
            self.assertEqual((await self.request(path, scheme='http', headers={'X-Forwarded-Proto': 'https'})).status_code, 403)
        response = await self.request(headers={'Authorization': 'Bearer never-echo-this'})
        self.assertEqual(response.status_code, 401)
        self.assertIn('resource_metadata', response.headers['WWW-Authenticate'])
        self.assertNotIn('never-echo-this', response.text)
        self.assertNotIn('Access-Control-Allow-Origin', response.headers)
        self.assertEqual((await self.request(f'/mcp?api_key={self.key}', headers={'Cookie': f'key={self.key}'})).status_code, 401)
        with patch.dict(os.environ, {'RADAR_MCP_ALLOW_HTTP': 'true', 'TRUST_PROXY_HEADERS': 'true'}):
            self.app = mcp_server.build_app()
        self.assertEqual((await self.request(scheme='http')).status_code, 401)

    async def test_body_bounds_and_invalid_lengths_before_auth(self):
        for value in ('bad', '-1', '+1', ' 1'):
            self.assertEqual((await self.request(headers={'Content-Length': value})).status_code, 400)
        self.assertEqual((await self.request(headers={'Content-Length': '131073'}, content=b'')).status_code, 413)
        async def chunks():
            yield b'x' * 65536
            yield b'x' * 65537
        self.assertEqual((await self.request(content=chunks())).status_code, 413)
        self.assertEqual((await self.request(content=b'x' * 131072)).status_code, 401)

    async def test_missing_host_and_limiter_failure_are_closed(self):
        sent = []
        async def receive():
            self.fail('Missing Host must be rejected before receiving or parsing a body.')
        async def send(message):
            sent.append(message)
        await self.app({'type': 'http', 'path': '/healthz', 'scheme': 'https', 'headers': []}, receive, send)
        self.assertEqual(sent[0]['status'], 421)
        with patch('radar.mcp_server._auth_failure', side_effect=RuntimeError('private database canary')):
            response = await self.request()
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('canary', response.text)

    async def test_shared_invalid_auth_limits_and_valid_key_bypass(self):
        for _ in range(20):
            self.assertEqual((await self.request()).status_code, 401)
        self.assertEqual((await self.request()).status_code, 429)
        init = json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
            'protocolVersion': '2025-11-25', 'capabilities': {}, 'clientInfo': {'name': 'test', 'version': '1'}
        }})
        valid = await self.request(content=init, headers={'Authorization': f'Bearer {self.key}',
            'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream'})
        self.assertEqual(valid.status_code, 200)
        self.app = mcp_server.build_app()  # independent instance, same SQLite counters
        self.assertEqual((await self.request()).status_code, 429)
        with transaction() as conn:
            conn.execute('DELETE FROM mcp_auth_failures')
        for i in range(200):
            response = await self.request(client=(f'192.0.2.{i % 250 + 1}', 1234))
            self.assertEqual(response.status_code, 401)
        self.assertEqual((await self.request(client=('198.51.100.1', 1234))).status_code, 429)
        with connect() as conn:
            rows = conn.execute('SELECT * FROM mcp_auth_failures').fetchall()
        self.assertNotIn('192.0.2.', str([tuple(row) for row in rows]))
        with transaction() as conn:
            conn.execute('UPDATE mcp_auth_failures SET occurred_at=0')
        self.assertEqual((await self.request()).status_code, 401)

    async def test_startup_and_numeric_ranges(self):
        for env in ({'RADAR_MCP_ALLOWED_HOSTS': ''}, {'RADAR_MCP_FORWARDED_ALLOW_IPS': '*'},
                    {'RADAR_MCP_PUBLIC_URL': 'https://other.invalid/mcp'},
                    {'RADAR_MCP_ALLOWED_HOSTS': '*'}, {'RADAR_MCP_ALLOW_HTTP': 'perhaps'}):
            with patch.dict(os.environ, env), self.assertRaises(ValueError):
                mcp_server.build_app()
        expected = {
            'MCP_KEY_MINUTE_LIMIT': (1, 10000), 'MCP_OPERATION_HOURLY_LIMIT': (1, 1000),
            'MCP_OPERATION_KEY_CONCURRENCY': (1, 4), 'MCP_OPERATION_GLOBAL_CONCURRENCY': (1, 16),
            'MCP_OPERATION_LEASE_SECONDS': (300, 3600), 'MCP_AUTH_FAILURE_LIMIT': (1, 1000),
        }
        for name, (low, high) in expected.items():
            with patch.dict(os.environ, {name: '-1'}):
                self.assertEqual(mcp_server.limit_config()[name], low)
            with patch.dict(os.environ, {name: '999999'}):
                self.assertEqual(mcp_server.limit_config()[name], high)
        with patch.dict(os.environ, {'RADAR_MCP_FORWARDED_ALLOW_IPS': '127.0.0.0/8'}):
            self.assertEqual(mcp_server.proxy_config(), {'proxy_headers': True, 'forwarded_allow_ips': '127.0.0.0/8'})
        self.assertEqual(mcp_server.proxy_config(), {'proxy_headers': False, 'forwarded_allow_ips': ''})

    async def test_real_uvicorn_proxy_peer_trust(self):
        for trusted, expected in (('', 403), ('192.0.2.1', 403), ('127.0.0.0/8', 200)):
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0))
                port = sock.getsockname()[1]
            flags = ['--proxy-headers', '--forwarded-allow-ips', trusted] if trusted else ['--no-proxy-headers']
            process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'radar.mcp_server:build_app',
                '--factory', '--host', '127.0.0.1', '--port', str(port), '--no-access-log', *flags],
                env={**os.environ, 'TRUST_PROXY_HEADERS': 'true'}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                async with httpx2.AsyncClient(base_url=f'http://127.0.0.1:{port}', trust_env=False, timeout=2) as http:
                    for _ in range(100):
                        if process.poll() is not None:
                            self.fail('Local uvicorn fixture exited before readiness.')
                        try:
                            health = await http.get('/healthz', headers={'Host': 'radar.example.invalid'})
                            if health.status_code == 200:
                                break
                        except httpx2.ConnectError:
                            pass
                        await asyncio.sleep(0.02)
                    else:
                        self.fail('Local uvicorn fixture did not become ready.')
                    path = '/.well-known/oauth-protected-resource/mcp'
                    response = await http.get(path, headers={'Host': 'radar.example.invalid',
                        'X-Forwarded-Proto': 'https', 'X-Forwarded-For': '198.51.100.1'})
                    self.assertEqual(response.status_code, expected)
                    self.assertEqual((await http.get(path, headers={'Host': 'radar.example.invalid'})).status_code, 403)
                    self.assertEqual((await http.get(path, headers={'Host': 'localhost', 'X-Forwarded-Proto': 'https'})).status_code, 421)
            finally:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
