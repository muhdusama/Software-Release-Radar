"""Bearer authority and browser-only key lifecycle, using an isolated database."""
import asyncio
import base64
import json
import os
import re
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from radar.application import create_app
from radar.auth import hash_password
from radar.db import connect, transaction, utcnow
from radar import mcp_auth


class MCPAuthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = patch.dict(os.environ, {
            'RADAR_DB': str(Path(self.tmp.name) / 'test.db'),
            'SECRET_KEY': 'local-test-secret-key-at-least-32-characters',
            'ENCRYPTION_KEY': base64.urlsafe_b64encode(os.urandom(32)).decode(),
            'ADMIN_USERNAME': 'admin', 'ADMIN_EMAIL': 'admin@example.invalid',
            'ADMIN_PASSWORD_HASH': hash_password('correct-horse-battery', iterations=1000),
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        self.app = create_app()
        self.app.testing = True
        self.client = self.app.test_client()
        with transaction() as conn:
            self.admin = conn.execute("SELECT id FROM users WHERE username='admin'").fetchone()[0]
            self.user = conn.execute(
                'INSERT INTO users(username,password_hash,role,active,created_at,updated_at) VALUES(?,?,?,?,?,?)',
                ('reader', hash_password('correct-horse-battery', iterations=1000), 'user', 1, utcnow(), utcnow())
            ).lastrowid

    def key(self, owner=None, scopes=None):
        return mcp_auth.create_key(owner or self.admin, 'correct-horse-battery', '<Hermes>', scopes or ['read'])

    def verify(self, token):
        return asyncio.run(mcp_auth.RadarTokenVerifier().verify_token(token))

    def login(self):
        self.client.get('/login')
        with self.client.session_transaction() as session:
            csrf = session['csrf_token']
        self.assertEqual(self.client.post('/login', data={
            'csrf_token': csrf, 'username': 'admin', 'password': 'correct-horse-battery'
        }).status_code, 302)
        with self.client.session_transaction() as session:
            return session['csrf_token']

    def test_digest_metadata_and_transactional_audit(self):
        key_id, token = self.key()
        self.assertRegex(token, r'^srr_[a-f0-9]{16}_[A-Za-z0-9_-]+$')
        secret = token.split('_', 2)[2]
        with connect() as conn:
            stored = dict(conn.execute('SELECT * FROM mcp_keys WHERE id=?', (key_id,)).fetchone())
            audit = dict(conn.execute("SELECT * FROM audit_log WHERE action='mcp_key_created'").fetchone())
        self.assertNotIn(secret, str(stored))
        self.assertNotIn(token, str(audit))
        self.assertEqual(audit['api_key_id'], key_id)
        self.assertEqual(set(mcp_auth.list_keys(self.admin)[0]),
                         {'id', 'label', 'scopes', 'created_at', 'expires_at', 'revoked_at', 'last_used_at'})
        self.assertNotIn(secret, str(mcp_auth.list_keys(self.admin)))
        self.assertEqual(self.verify(token).client_id, key_id)
        self.assertEqual(self.verify(token).token, key_id)
        with self.assertRaises(ValueError):
            mcp_auth.revoke_key(self.user, key_id)
        mcp_auth.revoke_key(self.admin, key_id)
        self.assertIsNone(self.verify(token))
        self.assertIsNotNone(mcp_auth.list_keys(self.admin)[0]['revoked_at'])

    def test_validation_and_phase_one_scopes(self):
        for scopes in ([], ['operations:run'], ['read', 'trackers:write'], ['read', 'upgrades:write'], ['read', 'unknown']):
            with self.subTest(scopes=scopes), self.assertRaises(ValueError):
                self.key(scopes=scopes) if scopes else mcp_auth.create_key(self.admin, 'correct-horse-battery', 'x', [])
        with self.assertRaises(ValueError):
            self.key(owner=self.user, scopes=['read', 'operations:run'])
        for label in ('', 'x' * 81):
            with self.assertRaises(ValueError):
                mcp_auth.create_key(self.admin, 'correct-horse-battery', label, ['read'])
        for days in (0, 366, True, '90'):
            with self.assertRaises(ValueError):
                mcp_auth.create_key(self.admin, 'correct-horse-battery', 'x', ['read'], days)
        with self.assertRaises(ValueError):
            mcp_auth.create_key(self.admin, 'wrong-password', 'x', ['read'])
        _, token = self.key()
        for invalid in ('', 'x' * 257, token + 'wrong', token.replace('srr_', 'bad_', 1), 'srr__x'):
            self.assertIsNone(self.verify(invalid))

    def test_default_expiry_and_audit_failure_roll_back(self):
        key_id, token = self.key()
        row = mcp_auth.list_keys(self.admin)[0]
        self.assertEqual(datetime.fromisoformat(row['expires_at']) - datetime.fromisoformat(row['created_at']),
                         timedelta(days=90))
        access = self.verify(token)
        with patch('radar.mcp_auth.audit', side_effect=RuntimeError('audit unavailable')):
            with self.assertRaises(RuntimeError):
                self.key()
            with self.assertRaises(RuntimeError):
                mcp_auth.revoke_key(self.admin, key_id)
        self.assertEqual(len(mcp_auth.list_keys(self.admin)), 1)
        self.assertIsNotNone(self.verify(token))
        mcp_auth.revoke_key(self.admin, key_id)
        with patch('radar.mcp_auth.get_access_token', return_value=access), self.assertRaises(ValueError):
            mcp_auth.current_principal()

    def test_fresh_authority_and_throttled_last_used(self):
        key_id, token = self.key(scopes=['read', 'operations:run'])
        self.verify(token)
        with transaction() as conn:
            conn.execute('CREATE TABLE updates(n INTEGER)')
            conn.execute('CREATE TRIGGER count_use AFTER UPDATE OF last_used_at ON mcp_keys BEGIN INSERT INTO updates VALUES(1); END')
            conn.execute('UPDATE mcp_keys SET scopes_json=? WHERE id=?',
                         (json.dumps(['read', 'operations:run', 'trackers:write', 'upgrades:write', 'unknown']), key_id))
        self.assertEqual(set(self.verify(token).scopes), {'read', 'operations:run'})
        with connect() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM updates').fetchone()[0], 0)
        with transaction() as conn:
            conn.execute("UPDATE users SET role='user' WHERE id=?", (self.admin,))
        self.assertEqual(self.verify(token).scopes, ['read'])
        access = self.verify(token)
        with patch('radar.mcp_auth.get_access_token', return_value=access):
            with transaction(immediate=True) as conn:
                self.assertFalse(mcp_auth.current_principal(conn=conn).is_admin)
            with transaction() as conn:
                conn.execute('UPDATE users SET active=0 WHERE id=?', (self.admin,))
            with self.assertRaises(ValueError):
                mcp_auth.current_principal()
        self.assertIsNone(self.verify(token))

    def test_expiry_password_change_and_deleted_owner(self):
        for change in ('expiry', 'password', 'delete'):
            with self.subTest(change=change):
                owner = self.user
                key_id, token = self.key(owner=owner)
                if change == 'expiry':
                    with transaction() as conn:
                        conn.execute("UPDATE mcp_keys SET expires_at='2000-01-01T00:00:00+00:00' WHERE id=?", (key_id,))
                elif change == 'password':
                    with transaction() as conn:
                        conn.execute('UPDATE users SET password_hash=? WHERE id=?',
                                     (hash_password('correct-horse-battery', iterations=1000), owner))
                else:
                    with transaction() as conn:
                        conn.execute('DELETE FROM users WHERE id=?', (owner,))
                self.assertIsNone(self.verify(token))

    def test_browser_secret_once_and_no_store(self):
        self.assertEqual(self.client.post('/profile/mcp-keys').status_code, 302)
        csrf = self.login()
        self.assertEqual(self.client.post('/profile/mcp-keys', data={}).status_code, 400)
        response = self.client.post('/profile/mcp-keys', data={
            'csrf_token': csrf, 'current_password': 'correct-horse-battery',
            'label': '<Hermes>', 'scopes': ['read'], 'expires_days': '90'
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        token = re.search(r'srr_[a-f0-9]{16}_[A-Za-z0-9_-]+', response.get_data(as_text=True))[0]
        self.assertIn('&lt;Hermes&gt;', response.get_data(as_text=True))
        self.assertNotIn(token, str(response.headers.getlist('Set-Cookie')))
        with self.client.session_transaction() as session:
            self.assertNotIn(token, str(dict(session)))
        self.assertNotIn(token, self.client.get('/profile').get_data(as_text=True))
        error = self.client.post('/profile/mcp-keys', data={
            'csrf_token': csrf, 'current_password': 'wrong', 'label': 'x', 'scopes': ['read']
        })
        self.assertEqual(error.status_code, 400)
        self.assertEqual(error.headers['Cache-Control'], 'no-store')
        key_id = token.split('_', 2)[1]
        other_id, _ = self.key(owner=self.user)
        self.assertEqual(self.client.post(f'/profile/mcp-keys/{other_id}/revoke', data={'csrf_token': csrf}).status_code, 404)
        self.assertEqual(self.client.post(f'/profile/mcp-keys/{key_id}/revoke', data={}).status_code, 400)
        self.assertEqual(self.client.post(f'/profile/mcp-keys/{key_id}/revoke', data={'csrf_token': csrf}).status_code, 302)
        self.assertIsNone(self.verify(token))
