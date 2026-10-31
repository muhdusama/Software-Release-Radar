"""Optional SDK HTTP process; browser cookies never authenticate this service."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import ipaddress
import logging
import os
import re
import time
from urllib.parse import urlsplit

import uvicorn
from mcp.server import MCPServer
from mcp.server.auth.settings import AuthSettings
from mcp.server.transport_security import RequestBodyLimitMiddleware, TransportSecuritySettings
from starlette.responses import JSONResponse
from starlette.types import ASGIApp

from .db import init_db, transaction
from .mcp_auth import RadarTokenVerifier
from .security_controls import _int_env

BODY_LIMIT = 131072


def limit_config() -> dict[str, int]:
    ranges = {
        'MCP_KEY_MINUTE_LIMIT': (120, 1, 10000),
        'MCP_OPERATION_HOURLY_LIMIT': (20, 1, 1000),
        'MCP_OPERATION_KEY_CONCURRENCY': (1, 1, 4),
        'MCP_OPERATION_GLOBAL_CONCURRENCY': (2, 1, 16),
        'MCP_OPERATION_LEASE_SECONDS': (300, 300, 3600),
        'MCP_AUTH_FAILURE_LIMIT': (20, 1, 1000),
    }
    return {name: _int_env(name, default, minimum=low, maximum=high)
            for name, (default, low, high) in ranges.items()}


def proxy_config() -> dict[str, object]:
    peers = os.environ.get('RADAR_MCP_FORWARDED_ALLOW_IPS', '').strip()
    if peers:
        for peer in peers.split(','):
            ipaddress.ip_network(peer.strip(), strict=False)
    return {'proxy_headers': bool(peers), 'forwarded_allow_ips': peers}


def _transport_config():
    hosts = [h.strip().lower() for h in os.environ.get('RADAR_MCP_ALLOWED_HOSTS', '').split(',') if h.strip()]
    if not hosts or any(not re.fullmatch(r'[a-z0-9.\[\]:-]+', h, re.ASCII) for h in hosts):
        raise ValueError('Explicit MCP allowed hosts are required; wildcards are not supported.')
    allow = os.environ.get('RADAR_MCP_ALLOW_HTTP', 'false').lower()
    if allow not in ('true', 'false'):
        raise ValueError('RADAR_MCP_ALLOW_HTTP must be true or false.')
    origins = [o.strip() for o in os.environ.get('RADAR_MCP_ALLOWED_ORIGINS', '').split(',') if o.strip()]
    public = os.environ.get('RADAR_MCP_PUBLIC_URL') or f'https://{hosts[0]}/mcp'
    url = urlsplit(public)
    if (url.scheme not in ('https', 'http') or (url.scheme == 'http' and allow != 'true')
            or url.netloc.lower() not in hosts or url.username or url.password
            or url.path != '/mcp' or url.query or url.fragment):
        raise ValueError('MCP public URL must use an allowed host and the /mcp path with HTTPS.')
    proxy_config()
    return hosts, origins, allow == 'true', public


def build_server() -> MCPServer:
    _, _, _, public = _transport_config()
    return MCPServer('Software Release Radar', token_verifier=RadarTokenVerifier(),
                     auth=AuthSettings(issuer_url=public.removesuffix('/mcp'), resource_server_url=public,
                                       required_scopes=['read'], validate_token_resource=False))


def _auth_failure(source: str, secret: str, limit: int) -> bool:
    bucket = hmac.new(secret.encode(), source.encode(), hashlib.sha256).hexdigest()
    now = time.time()
    with transaction(immediate=True) as conn:
        conn.execute('DELETE FROM mcp_auth_failures WHERE occurred_at<=?', (now - 600,))
        global_count = conn.execute('SELECT COUNT(*) FROM mcp_auth_failures').fetchone()[0]
        source_count = conn.execute('SELECT COUNT(*) FROM mcp_auth_failures WHERE source_hash=?', (bucket,)).fetchone()[0]
        if global_count <= 200:
            conn.execute('INSERT INTO mcp_auth_failures(source_hash,occurred_at) VALUES(?,?)', (bucket, now))
        return global_count >= 200 or source_count >= limit


def build_app() -> ASGIApp:
    hosts, origins, allow_http, _ = _transport_config()
    secret = os.environ.get('SECRET_KEY', '')
    if len(secret) < 32:
        raise ValueError('A strong SECRET_KEY is required for MCP rate limits.')
    limits = limit_config()
    init_db()
    server = build_server()

    @server.custom_route('/healthz', methods=['GET'])
    async def health(request):
        return JSONResponse({'status': 'ok'})

    # Tool registration is added at the next implementation task. The SDK owns
    # JSON-RPC, HTTP authentication and transport lifecycles, not this guard.
    sdk = server.streamable_http_app(stateless_http=True, json_response=True, max_request_body_size=BODY_LIMIT,
        transport_security=TransportSecuritySettings(allowed_hosts=hosts, allowed_origins=origins))

    async def checked(scope, receive, send):
        async def counted(message):
            if message['type'] == 'http.response.start' and message['status'] == 401 and scope['path'] == '/mcp':
                source = str((scope.get('client') or ('unknown',))[0])
                try:
                    limited = await asyncio.to_thread(_auth_failure, source, secret, limits['MCP_AUTH_FAILURE_LIMIT'])
                except Exception:
                    # Never expose database paths/errors or accept on limiter failure.
                    await JSONResponse({'error': 'Authentication temporarily unavailable.'}, status_code=503)(scope, receive, send)
                    raise _ResponseSent
                if limited:
                    await JSONResponse({'error': 'Authentication rate limit exceeded.'}, status_code=429,
                                       headers={'Retry-After': '600'})(scope, receive, send)
                    raise _ResponseSent
            await send(message)
        try:
            await sdk(scope, receive, counted)
        except _ResponseSent:
            pass

    bounded = RequestBodyLimitMiddleware(checked, max_body_size=BODY_LIMIT)

    async def guard(scope, receive, send):
        if scope['type'] != 'http':
            return await sdk(scope, receive, send)
        headers = scope.get('headers', [])
        def values(name):
            return [v.decode('latin-1') for k, v in headers if k.lower() == name]
        host, origin, length = values(b'host'), values(b'origin'), values(b'content-length')
        status, error = None, ''
        if len(host) != 1 or host[0].lower() not in hosts:
            status, error = 421, 'Unrecognised Host.'
        elif origin and (len(origin) != 1 or origin[0] not in origins):
            status, error = 403, 'Origin is not permitted.'
        elif scope.get('scheme') != 'https' and scope['path'] != '/healthz' and not allow_http:
            status, error = 403, 'HTTPS is required.'
        elif length and (len(length) != 1 or not re.fullmatch(r'[0-9]+', length[0], re.ASCII)):
            status, error = 400, 'Invalid content length.'
        elif length and (len(length[0]) > 9 or int(length[0]) > BODY_LIMIT):
            status, error = 413, 'Request body too large.'
        if status:
            return await JSONResponse({'error': error}, status_code=status)(scope, receive, send)
        return await bounded(scope, receive, send)
    return guard


class _ResponseSent(Exception):
    """Stop the SDK error response after a replacement response was sent."""


def main() -> None:
    app = build_app()
    if os.environ.get('RADAR_MCP_ALLOW_HTTP', 'false').lower() == 'true':
        logging.getLogger(__name__).warning('MCP plain HTTP explicitly enabled; use only a local development route.')
    uvicorn.run(app, host='0.0.0.0', port=8081, workers=1, access_log=False, **proxy_config())


if __name__ == '__main__':
    main()
