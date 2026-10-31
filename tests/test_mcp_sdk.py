"""Characterise SDK capabilities relied upon by the MCP security boundary."""
import unittest
import asyncio
import socket
import threading
from importlib.metadata import version

import httpx2
import uvicorn
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.server import MCPServer
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import BaseModel, ConfigDict, StrictInt
from starlette.responses import JSONResponse
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware


class SDKCompatibilityTests(unittest.TestCase):
    def test_supported_sdk_exposes_native_server(self):
        from mcp.server import MCPServer

        self.assertTrue(version('mcp').startswith('2.3.'))
        self.assertIsNotNone(MCPServer('Radar compatibility'))


class SDKHTTPCompatibilityTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.middleware_keys = []
        self.calls = 0

        class Verifier:
            async def verify_token(self, token):
                if token == 'fixture-token':
                    return AccessToken(token='fixture-key-id', client_id='fixture-key-id', scopes=['read'])
                return None

        async def middleware(ctx, call_next):
            token = get_access_token()
            self.middleware_keys.append(token.client_id if token else None)
            return await call_next(ctx)

        class Input(BaseModel):
            model_config = ConfigDict(extra='forbid')
            value: StrictInt

        server = MCPServer('compatibility', token_verifier=Verifier(), middleware=[middleware],
                           auth=AuthSettings(issuer_url='https://example.invalid',
                                             resource_server_url='https://example.invalid/mcp',
                                             validate_token_resource=False, required_scopes=['read']))

        @server.tool()
        def identity(payload: Input) -> dict[str, object]:
            self.calls += 1
            token = get_access_token()
            return {'value': payload.value, 'key_id': token.client_id if token else None,
                    'threaded': threading.current_thread() is not threading.main_thread()}

        @server.custom_route('/healthz', methods=['GET'])
        async def health(request):
            return JSONResponse({'status': 'ok'})

        self.socket = socket.socket()
        self.socket.bind(('127.0.0.1', 0))
        port = self.socket.getsockname()[1]
        self.url = f'http://127.0.0.1:{port}'
        app = server.streamable_http_app(stateless_http=True, json_response=True,
            max_request_body_size=131072,
            transport_security=TransportSecuritySettings(allowed_hosts=[f'127.0.0.1:{port}']))
        self.server = uvicorn.Server(uvicorn.Config(app, log_level='critical', proxy_headers=False))
        self.thread = threading.Thread(target=self.server.run, kwargs={'sockets': [self.socket]}, daemon=True)
        self.thread.start()
        for _ in range(100):
            if self.server.started:
                break
            await asyncio.sleep(.02)
        self.assertTrue(self.server.started)

    async def asyncTearDown(self):
        self.server.should_exit = True
        await asyncio.to_thread(self.thread.join, 5)
        self.socket.close()
        self.assertFalse(self.thread.is_alive())

    async def test_real_session_strict_model_and_auth_context(self):
        async with httpx2.AsyncClient(headers={'Authorization': 'Bearer fixture-token'}, trust_env=False) as client:
            async with streamable_http_client(self.url + '/mcp', http_client=client) as streams:
                async with ClientSession(streams[0], streams[1]) as session:
                    await session.initialize()
                    listed = await session.list_tools()
                    self.assertEqual([t.name for t in listed.tools], ['identity'])
                    result = await session.call_tool('identity', {'payload': {'value': 7}})
                    self.assertFalse(result.is_error)
                    self.assertEqual(result.structured_content, {'value': 7, 'key_id': 'fixture-key-id', 'threaded': True})
                    for payload in ({'value': 7, 'extra': True}, {'value': True}, {'value': '7'}):
                        result = await session.call_tool('identity', {'payload': payload})
                        self.assertTrue(result.is_error)
        self.assertEqual(self.calls, 1)
        self.assertTrue(self.middleware_keys)
        self.assertEqual(set(self.middleware_keys), {'fixture-key-id'})

    async def test_auth_metadata_and_custom_route_security_characterisation(self):
        async with httpx2.AsyncClient(trust_env=False) as client:
            missing = await client.post(self.url + '/mcp', json={})
            self.assertEqual(missing.status_code, 401)
            self.assertIn('resource_metadata=', missing.headers['www-authenticate'])
            metadata = await client.get(self.url + '/.well-known/oauth-protected-resource/mcp')
            self.assertEqual(metadata.status_code, 200)
            self.assertEqual(metadata.json()['authorization_servers'], ['https://example.invalid'])
            health = await client.get(self.url + '/healthz', headers={'Host': 'untrusted.invalid', 'Origin': 'https://untrusted.invalid'})
            # SDK custom routes bypass transport security: the outer guard must cover them.
            self.assertEqual(health.status_code, 200)

    async def test_uvicorn_trusts_only_configured_peers_and_cidrs(self):
        observed = []

        async def record(scope, receive, send):
            observed.append(scope['scheme'])

        for peer, expected in [('127.0.0.1', 'https'), ('192.0.2.2', 'http')]:
            app = ProxyHeadersMiddleware(record, trusted_hosts=['127.0.0.0/8'])
            await app({'type': 'http', 'scheme': 'http', 'client': (peer, 1),
                       'headers': [(b'x-forwarded-proto', b'https')]}, None, None)
            self.assertEqual(observed[-1], expected)
