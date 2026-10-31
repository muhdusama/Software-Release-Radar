"""Browser-managed bearer keys. No key lifecycle helper is an MCP tool."""
from __future__ import annotations

import asyncio
import hmac
import json
import re
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken

from .auth import token_digest, verify_password
from .db import audit, connect, transaction, utcnow

PHASE_ONE_SCOPES = frozenset({'read', 'operations:run'})
CAPABILITY_PHASE = 2


def available_scopes():
    return PHASE_ONE_SCOPES | ({'trackers:write', 'upgrades:write'} if CAPABILITY_PHASE == 2 else set())

_KEY_PATTERN = re.compile(r'srr_([a-f0-9]{16})_([A-Za-z0-9_-]{43})', re.ASCII)


@dataclass(frozen=True)
class Principal:
    key_id: str
    user_id: int
    is_admin: bool
    scopes: frozenset[str]


def create_key(user_id: int, current_password: str, label: str, scopes: list[str],
               expires_days: int = 90) -> tuple[str, str]:
    if not isinstance(label, str) or not 1 <= len(label.strip()) <= 80:
        raise ValueError('Key label must contain 1 to 80 characters.')
    if type(expires_days) is not int or not 1 <= expires_days <= 365:
        raise ValueError('Key expiry must be 1 to 365 days.')
    if not isinstance(scopes, list) or not all(isinstance(s, str) for s in scopes):
        raise ValueError('Invalid key scopes.')
    selected = frozenset(scopes)
    if 'read' not in selected or not selected <= available_scopes():
        raise ValueError('Read scope is required; only current phase scopes are available.')
    with transaction(immediate=True) as conn:
        owner = conn.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone()
        if not owner or not owner['active'] or not verify_password(current_password, owner['password_hash']):
            raise ValueError('Current password is incorrect or account is unavailable.')
        if owner['role'] != 'admin' and selected != {'read'}:
            raise ValueError('Only administrators can grant operational scopes.')
        key_id, secret = secrets.token_hex(8), secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc).replace(microsecond=0)
        conn.execute('''INSERT INTO mcp_keys
            (id,user_id,label,secret_digest,password_stamp,scopes_json,created_at,expires_at)
            VALUES(?,?,?,?,?,?,?,?)''',
            (key_id, user_id, label.strip(), token_digest(secret), token_digest(owner['password_hash']),
             json.dumps(sorted(selected)), now.isoformat(), (now + timedelta(days=expires_days)).isoformat()))
        audit(user_id, 'mcp_key_created', 'mcp_key', key_id, conn=conn, api_key_id=key_id)
    return key_id, f'srr_{key_id}_{secret}'


def revoke_key(user_id: int, key_id: str) -> None:
    with transaction(immediate=True) as conn:
        row = conn.execute('SELECT revoked_at FROM mcp_keys WHERE id=? AND user_id=?', (key_id, user_id)).fetchone()
        if row is None:
            raise ValueError('Key not found.')
        if not row['revoked_at']:
            conn.execute('UPDATE mcp_keys SET revoked_at=? WHERE id=?', (utcnow(), key_id))
            audit(user_id, 'mcp_key_revoked', 'mcp_key', key_id, conn=conn, api_key_id=key_id)


def list_keys(user_id: int) -> list[dict[str, object]]:
    with connect() as conn:
        rows = conn.execute('''SELECT id,label,scopes_json,created_at,expires_at,revoked_at,last_used_at
            FROM mcp_keys WHERE user_id=? ORDER BY created_at DESC,id''', (user_id,)).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item['scopes'] = sorted(_stored_scopes(item.pop('scopes_json')))
        result.append(item)
    return result


def _stored_scopes(raw: str) -> frozenset[str]:
    try:
        values = json.loads(raw)
        if isinstance(values, list) and all(isinstance(s, str) for s in values):
            return frozenset(values) & available_scopes()
    except (ValueError, TypeError):
        pass
    return frozenset()


def _key_row(conn: sqlite3.Connection, key_id: str):
    return conn.execute('''SELECT k.*,u.active,u.role,u.password_hash FROM mcp_keys k
        JOIN users u ON u.id=k.user_id WHERE k.id=?''', (key_id,)).fetchone()


def _principal(row) -> Principal:
    if not row or not row['active'] or row['revoked_at']:
        raise ValueError('Key is unavailable.')
    try:
        expired = datetime.fromisoformat(row['expires_at']) <= datetime.now(timezone.utc)
    except (ValueError, TypeError):
        expired = True
    if expired or not hmac.compare_digest(row['password_stamp'], token_digest(row['password_hash'])):
        raise ValueError('Key is unavailable.')
    scopes = _stored_scopes(row['scopes_json'])
    if 'read' not in scopes:
        raise ValueError('Key is unavailable.')
    admin = row['role'] == 'admin'
    return Principal(row['id'], int(row['user_id']), admin, scopes if admin else scopes & {'read'})


def current_principal(*, conn: sqlite3.Connection | None = None) -> Principal:
    access = get_access_token()
    if access is None:
        raise ValueError('Authentication required.')
    if conn is None:
        with connect() as own:
            return _principal(_key_row(own, access.client_id))
    return _principal(_key_row(conn, access.client_id))


class RadarTokenVerifier:
    async def verify_token(self, token: str) -> AccessToken | None:
        return await asyncio.to_thread(self._verify, token)

    def _verify(self, token: str) -> AccessToken | None:
        if not isinstance(token, str) or len(token) > 256:
            return None
        match = _KEY_PATTERN.fullmatch(token)
        if not match:
            return None
        key_id, secret = match.groups()
        with transaction(immediate=True) as conn:
            row = _key_row(conn, key_id)
            if not row or not hmac.compare_digest(row['secret_digest'], token_digest(secret)):
                return None
            try:
                principal = _principal(row)
            except ValueError:
                return None
            now = datetime.now(timezone.utc).replace(microsecond=0)
            cutoff = (now - timedelta(minutes=1)).isoformat()
            if row['last_used_at'] is None or row['last_used_at'] <= cutoff:
                conn.execute('UPDATE mcp_keys SET last_used_at=? WHERE id=?', (now.isoformat(), key_id))
            return AccessToken(token=key_id, client_id=key_id, scopes=sorted(principal.scopes),
                               expires_at=int(datetime.fromisoformat(row['expires_at']).timestamp()))
