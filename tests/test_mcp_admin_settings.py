"""Administrator MCP policy in Settings: off switch, scope and user policy, stored limits and key revocation."""
import asyncio
import os
import unittest
from unittest.mock import patch

import test_mcp_auth as fixtures
from radar import mcp_auth, mcp_server
from radar.db import connect, set_settings


class MCPAdminSettingsTests(unittest.TestCase):
    setUp = fixtures.MCPAuthTests.setUp
    key = fixtures.MCPAuthTests.key
    verify = fixtures.MCPAuthTests.verify
    login = fixtures.MCPAuthTests.login

    def login_reader(self):
        self.client.get('/login')
        with self.client.session_transaction() as session:
            csrf = session['csrf_token']
        self.client.post('/login', data={'csrf_token': csrf, 'username': 'reader', 'password': 'correct-horse-battery'})
        with self.client.session_transaction() as session:
            return session['csrf_token']

    def test_defaults_keep_existing_behaviour(self):
        policy = mcp_auth.mcp_policy()
        self.assertTrue(policy['enabled'])
        self.assertTrue(policy['user_keys'])
        self.assertEqual(policy['scopes'], mcp_auth.available_scopes())

    def test_scope_policy_applies_to_new_and_existing_keys(self):
        _, token = self.key(scopes=['read', 'trackers:write'])
        self.assertIn('trackers:write', self.verify(token).scopes)
        set_settings({'mcp_allowed_scopes': 'read'})
        self.assertEqual(self.verify(token).scopes, ['read'])
        with self.assertRaisesRegex(ValueError, 'not allowed'):
            self.key(scopes=['read', 'trackers:write'])

    def test_user_key_policy(self):
        _, reader_token = self.key(owner=self.user)
        _, admin_token = self.key()
        set_settings({'mcp_user_keys': '0'})
        self.assertIsNone(self.verify(reader_token))
        self.assertIsNotNone(self.verify(admin_token))
        with self.assertRaisesRegex(ValueError, 'administrators'):
            self.key(owner=self.user)

    def test_off_switch_refuses_requests_but_keeps_health(self):
        _, token = self.key()
        set_settings({'mcp_enabled': '0'})
        self.assertIsNone(self.verify(token))
        env = {'RADAR_MCP_ALLOWED_HOSTS': 'mcp.example.invalid'}
        with patch.dict(os.environ, env):
            app = mcp_server.build_app()

        def call(path):
            sent = []

            async def receive():
                return {'type': 'http.request', 'body': b'', 'more_body': False}

            async def send(message):
                sent.append(message)
            scope = {'type': 'http', 'method': 'GET', 'path': path, 'raw_path': path.encode(), 'query_string': b'',
                     'scheme': 'https', 'headers': [(b'host', b'mcp.example.invalid')], 'client': ('127.0.0.1', 1),
                     'server': ('mcp.example.invalid', 443), 'root_path': ''}
            asyncio.run(app(scope, receive, send))
            return sent[0]['status']
        self.assertEqual(call('/mcp'), 503)
        self.assertEqual(call('/healthz'), 200)

    def test_stored_limits_override_environment_within_range(self):
        set_settings({'mcp_key_minute_limit': '7', 'mcp_operation_hourly_limit': '99999'})
        limits = mcp_server.limit_config()
        self.assertEqual(limits['MCP_KEY_MINUTE_LIMIT'], 7)
        self.assertEqual(limits['MCP_OPERATION_HOURLY_LIMIT'], 20)

    def test_settings_section_validates_and_saves(self):
        csrf = self.login()
        response = self.client.post('/settings', data={'csrf_token': csrf, 'section': 'mcp', 'mcp_enabled': 'on',
                                                       'mcp_scopes': ['operations:run'], 'mcp_key_minute_limit': '0'})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(mcp_auth.mcp_policy()['user_keys'])  # rejected form changed nothing
        response = self.client.post('/settings', data={'csrf_token': csrf, 'section': 'mcp', 'mcp_enabled': 'on',
                                                       'mcp_scopes': ['operations:run'], 'mcp_key_minute_limit': '30'})
        self.assertEqual(response.status_code, 302)
        policy = mcp_auth.mcp_policy()
        self.assertFalse(policy['user_keys'])
        self.assertEqual(policy['scopes'], {'read', 'operations:run'})
        self.assertEqual(mcp_server.limit_config()['MCP_KEY_MINUTE_LIMIT'], 30)
        page = self.client.get('/settings?section=mcp')
        self.assertIn(b'All MCP keys', page.data)
        self.assertEqual(page.headers['Cache-Control'], 'no-store')

    def test_admin_revokes_any_key_and_standard_user_cannot(self):
        key_id, token = self.key(owner=self.user)
        csrf = self.login_reader()
        self.assertEqual(self.client.post('/settings', data={'csrf_token': csrf, 'section': 'mcp'}).status_code, 403)
        self.assertEqual(self.client.post(f'/settings/mcp-keys/{key_id}/revoke', data={'csrf_token': csrf}).status_code, 403)
        self.client.post('/logout', data={'csrf_token': csrf})
        csrf = self.login()
        self.assertEqual(self.client.post(f'/settings/mcp-keys/{key_id}/revoke', data={'csrf_token': csrf}).status_code, 302)
        self.assertIsNone(self.verify(token))
        with connect() as conn:
            actor = conn.execute("SELECT user_id FROM audit_log WHERE action='mcp_key_revoked'").fetchone()[0]
        self.assertEqual(actor, self.admin)


if __name__ == '__main__':
    unittest.main()
