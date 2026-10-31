"""Exercise cached projections and discovery through a real SDK session."""
import asyncio
from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import socket
import tempfile
import threading
import unittest
from unittest.mock import patch
from datetime import datetime, timezone

import httpx2
import uvicorn
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from radar.auth import hash_password

from radar.db import init_db, transaction, utcnow
from radar.mcp_auth import create_key

READS = {'radar_status', 'trackers_list', 'tracker_get', 'releases_list', 'history_list',
         'upgrades_list', 'upgrade_get', 'inventory_list', 'inventory_summary', 'job_get'}


class MCPReadTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.socket = socket.socket()
        self.socket.bind(('127.0.0.1', 0))
        self.host = '127.0.0.1:' + str(self.socket.getsockname()[1])
        self.env = patch.dict(os.environ, {'RADAR_DB': str(Path(self.temp.name) / 'radar.db'),
            'ADMIN_PASSWORD_HASH': '', 'SECRET_KEY': 'read-test-secret-' * 4,
            'RADAR_MCP_ALLOWED_HOSTS': self.host, 'RADAR_MCP_ALLOWED_ORIGINS': '',
            'RADAR_MCP_PUBLIC_URL': 'http://' + self.host + '/mcp',
            'RADAR_MCP_ALLOW_HTTP': 'true', 'RADAR_MCP_FORWARDED_ALLOW_IPS': '',
            'MCP_KEY_MINUTE_LIMIT': '10000'})
        self.env.start()
        init_db()
        self.canary = 'SECRET_CANARY_NEVER_EXPOSE'
        now = utcnow()
        with transaction() as conn:
            for role in ('admin', 'user'):
                conn.execute('INSERT INTO users(username,password_hash,role,created_at,updated_at) VALUES(?,?,?,?,?)',
                    (role, hash_password('test-password', iterations=1000), role, now, now))
            self.tracker = conn.execute('INSERT INTO trackers(name,repository,tags,current_version,current_release_body,last_error,install_host,ssh_key_name,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)',
                ('Example', 'example/project', 'prod,web', 'v2', 'release data', self.canary,
                 'machine.invalid', 'id_ed25519', now, now)).lastrowid
            conn.execute('INSERT INTO events(tracker_id,version,release_body,detected_at) VALUES(?,?,?,?)',
                         (self.tracker, 'v2', 'body', now))
            conn.execute('INSERT INTO upgrade_decisions(tracker_id,release_version,release_name,created_at,updated_at) VALUES(?,?,?,?,?)',
                         (self.tracker, 'v2', 'Release 2', now, now))
            conn.execute('INSERT INTO portainer_environments(endpoint_id,name,updated_at) VALUES(1,?,?)', ('Environment', now))
            conn.execute('INSERT INTO portainer_services(endpoint_id,container_id,container_name,labels_json,tracker_id,first_seen_at,last_seen_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',
                         (1, 'container', 'Service', json.dumps({'secret': self.canary}), self.tracker, now, now, now))
            self.job = conn.execute('INSERT INTO portainer_sync_jobs(requested_at,message,error,worker_id) VALUES(?,?,?,?)',
                                     (now, self.canary, self.canary, self.canary)).lastrowid
            conn.execute('INSERT OR REPLACE INTO settings(key,value,updated_at) VALUES(?,?,?)', ('smtp_password', self.canary, now))
        self.admin_id, self.admin = create_key(1, 'test-password', 'admin', ['read'])
        self.user_id, self.user = create_key(2, 'test-password', 'user', ['read'])
        from radar.mcp_server import build_app
        self.server = uvicorn.Server(uvicorn.Config(build_app(), log_level='critical', proxy_headers=False))
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
        self.assertFalse(self.thread.is_alive())
        self.socket.close()
        self.env.stop()
        self.temp.cleanup()

    @asynccontextmanager
    async def session(self, key=None):
        async with httpx2.AsyncClient(headers={'Authorization': 'Bearer ' + (key or self.admin)}, trust_env=False) as client:
            async with streamable_http_client('http://' + self.host + '/mcp', http_client=client) as streams:
                async with ClientSession(*streams) as session:
                    await session.initialize()
                    yield session

    async def call(self, session, name, arguments=None):
        result = await session.call_tool(name, arguments or {})
        self.assertFalse(result.is_error, result)
        self.assertNotIn(self.canary, result.model_dump_json())
        self.assertLessEqual(len(result.model_dump_json(by_alias=True).encode()), 262144)
        return result.structured_content

    async def test_discovery_permissions_and_every_cached_read(self):
        with patch('radar.github.get_recent_releases', side_effect=AssertionError('network')), \
             patch('radar.portainer.sync_inventory', side_effect=AssertionError('network')):
            async with self.session() as s:
                tools = (await s.list_tools()).tools
                self.assertEqual({t.name for t in tools}, READS)
                for tool in tools:
                    self.assertTrue(tool.annotations.read_only_hint)
                    self.assertFalse(tool.annotations.destructive_hint)
                    self.assertFalse(tool.annotations.open_world_hint)
                    self.assertIn('untrusted', tool.description.lower())
                self.assertEqual(set(await self.call(s, 'radar_status')), {'name', 'version', 'commit', 'github_cooldown_until', 'server_time'})
                self.assertEqual(len((await self.call(s, 'trackers_list'))['items']), 1)
                detail = await self.call(s, 'tracker_get', {'tracker_id': self.tracker})
                self.assertEqual(detail['probe']['install_host'], 'machine.invalid')
                self.assertEqual(len((await self.call(s, 'releases_list', {'tracker_id': self.tracker}))['items']), 1)
                history = await self.call(s, 'history_list')
                self.assertNotIn('release_body', history['items'][0])
                self.assertEqual(len((await self.call(s, 'upgrades_list'))['items']), 1)
                self.assertEqual((await self.call(s, 'upgrade_get', {'tracker_id': self.tracker}))['revision'], 0)
                inventory = await self.call(s, 'inventory_list', {'linked': True})
                self.assertEqual(inventory['items'][0]['linked_tracker_id'], self.tracker)
                self.assertNotIn('labels_json', inventory['items'][0])
                self.assertEqual((await self.call(s, 'inventory_summary'))['service_count'], 1)
                self.assertEqual((await self.call(s, 'job_get', {'job_id': self.job}))['status'], 'queued')
            async with self.session(self.user) as s:
                self.assertEqual({t.name for t in (await s.list_tools()).tools}, READS - {'inventory_list', 'inventory_summary', 'job_get'})
                denied = await s.call_tool('inventory_list', {})
                missing = await s.call_tool('not_a_tool', {})
                self.assertEqual(denied, missing)
                self.assertTrue(denied.is_error)
                detail = await self.call(s, 'tracker_get', {'tracker_id': self.tracker})
                self.assertNotIn('probe', detail)
                self.assertNotIn('install_host', detail)
            with transaction() as conn:
                self.assertNotIn(self.canary, repr([tuple(row) for row in conn.execute('SELECT * FROM audit_log')]))

    async def test_strict_validation_and_fixed_errors(self):
        async with self.session() as s:
            for args in ({'limit': 0}, {'limit': 101}, {'after_id': 0}, {'after_id': -1},
                         {'after_id': True}, {'after_id': '1'}, {'enabled': 1},
                         {'query': 'a' * 121}, {'tag': 'a' * 65}, {'unknown': self.canary}):
                result = await s.call_tool('trackers_list', args)
                self.assertTrue(result.is_error, args)
                self.assertNotIn(self.canary, result.model_dump_json())
            for since in ('2026-02-30', '20260101', True):
                self.assertTrue((await s.call_tool('history_list', {'since': since})).is_error)
            self.assertTrue((await s.call_tool('upgrades_list', {'decision_status': 'bad'})).is_error)
            for tool, args in [('tracker_get', {'tracker_id': 999}), ('job_get', {'job_id': 999}),
                               ('upgrade_get', {'tracker_id': 999}), ('releases_list', {'tracker_id': 999})]:
                result = await s.call_tool(tool, args)
                self.assertTrue(result.is_error)
                self.assertIn('Not found.', result.model_dump_json())
            with patch('radar.mcp_tools._tracker', side_effect=RuntimeError(self.canary)):
                with self.assertLogs(level='INFO') as logs:
                    result = await s.call_tool('tracker_get', {'tracker_id': self.tracker})
                self.assertTrue(result.is_error)
                self.assertNotIn(self.canary, result.model_dump_json())
                self.assertNotIn(self.canary, repr(logs.output))

    async def test_filters_pagination_and_utf8_byte_bounds(self):
        now = utcnow()
        with transaction() as conn:
            conn.executemany('INSERT INTO trackers(name,repository,enabled,tags,current_release_body,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',
                [(f'Item {i}', f'example/item{i}', i % 2, 'prod' if i % 2 else 'nonprod', '🔥' * 10000, now, now) for i in range(105)])
            conn.executemany('INSERT INTO events(tracker_id,version,release_body,detected_at) VALUES(?,?,?,?)',
                [(self.tracker, f'v{i+3}', '🔥' * 10000, now) for i in range(105)])
        async with self.session() as s:
            self.assertEqual(len((await self.call(s, 'trackers_list', {'tag': 'prod', 'enabled': True, 'limit': 100}))['items']), 53)
            self.assertEqual((await self.call(s, 'trackers_list', {'query': "%' OR 1=1--"}))['items'], [])
            seen, after = [], None
            for _ in range(32):
                args = {'tracker_id': self.tracker, 'limit': 100}
                if after:
                    args['after_id'] = after
                page = await self.call(s, 'releases_list', args)
                self.assertLessEqual(len(json.dumps(page, ensure_ascii=False).encode()), 262144)
                seen.extend(item['id'] for item in page['items'])
                after = page['next_after_id']
                if not after:
                    break
                self.assertEqual(after, seen[-1])
            self.assertEqual(len(seen), 106)
            self.assertEqual(seen, sorted(set(seen)))
            self.assertTrue((await self.call(s, 'releases_list', {'tracker_id': self.tracker, 'limit': 100}))['items'][1]['truncated'])
            first = await self.call(s, 'trackers_list', {'limit': 100})
            with transaction() as conn:
                conn.execute('INSERT INTO trackers(name,repository,created_at,updated_at) VALUES(?,?,?,?)', ('New', 'example/new', now, now))
            second = await self.call(s, 'trackers_list', {'limit': 100, 'after_id': first['next_after_id']})
            self.assertFalse(set(i['id'] for i in first['items']) & set(i['id'] for i in second['items']))
            self.assertIsNone(second['next_after_id'])
            self.assertEqual(len((await self.call(s, 'history_list', {'since': '2099-01-01'}))['items']), 0)
            self.assertEqual((await self.call(s, 'history_list', {'tracker_id': 999}))['items'], [])
            self.assertEqual((await self.call(s, 'upgrades_list', {'decision_status': 'ignore'}))['items'], [])
            self.assertEqual((await self.call(s, 'inventory_list', {'linked': False}))['items'], [])
            self.assertEqual((await self.call(s, 'trackers_list', {'tag': 'pro'}))['items'], [])

    async def test_check_state_and_shared_authenticated_counter(self):
        from radar.mcp_tools import check_state
        now = datetime(2026, 10, 31, 12, tzinfo=timezone.utc)
        base = {'enabled': 1, 'last_checked_at': None, 'github_retry_at': None, 'refresh_hours': 6}
        cases = [({}, None, 'due'), ({'enabled': 0}, '2026-11-01T00:00:00Z', 'disabled'),
                 ({'github_retry_at': '2026-10-31T13:00:00Z'}, '2026-10-31T14:00:00Z', 'deferred'),
                 ({'last_checked_at': '2026-10-31T11:00:00Z'}, None, 'scheduled'),
                 ({'last_checked_at': '2026-10-30T11:00:00Z'}, None, 'due')]
        for change, cooldown, expected in cases:
            result = check_state(base | change, now=now, cooldown=cooldown)
            self.assertEqual(result['check_state'], expected)
        async with self.session() as s:
            with transaction() as conn:
                self.assertGreater(conn.execute('SELECT SUM(requests) FROM mcp_rate_counters').fetchone()[0], 0)
            with patch.dict(os.environ, {'MCP_KEY_MINUTE_LIMIT': '1'}):
                with self.assertRaises(Exception) as caught:
                    await s.list_tools()
                self.assertIn('Rate limit', str(caught.exception))
        with transaction() as conn:
            conn.execute("UPDATE mcp_rate_counters SET expires_at='2000-01-01T00:00:00+00:00'")
        async with self.session() as s:
            self.assertEqual(len((await s.list_tools()).tools), 10)

    async def test_denials_are_key_attributed_and_do_not_log_arguments(self):
        async with self.session(self.user) as s:
            await s.call_tool('inventory_list', {'unknown': self.canary})
            await s.call_tool('trackers_list', {'unknown': self.canary})
        with transaction() as conn:
            rows = conn.execute("SELECT api_key_id,details FROM audit_log WHERE action='mcp_denied'").fetchall()
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row['api_key_id'] == self.user_id for row in rows))
        self.assertNotIn(self.canary, repr([tuple(row) for row in rows]))


if __name__ == '__main__':
    unittest.main()
