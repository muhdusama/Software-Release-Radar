"""Real SDK mutations are constrained, atomic and never trigger outbound work."""
import unittest
from unittest.mock import patch

import test_mcp_reads as fixtures
from radar.db import connect, transaction
from radar.mcp_auth import create_key


class MCPWriteTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.MCPReadTests.asyncSetUp
    asyncTearDown = fixtures.MCPReadTests.asyncTearDown
    session = fixtures.MCPReadTests.session
    call = fixtures.MCPReadTests.call

    def write_key(self):
        return create_key(1, 'test-password', 'data writes', ['read', 'trackers:write', 'upgrades:write'])[1]

    async def test_tracker_crud_no_outbound_and_source_scheduling(self):
        key = self.write_key()
        with patch('radar.checker.check_tracker', side_effect=AssertionError('outbound')), \
             patch('radar.probes.probe_tracker', side_effect=AssertionError('outbound')), \
             patch('radar.portainer.sync_inventory', side_effect=AssertionError('outbound')):
            async with self.session(key) as s:
                created = await self.call(s, 'tracker_create', {'tracker': {'name': ' New ', 'repository': 'https://github.com/example/demo', 'tags': ['One', 'TWO']}})
                tracker_id = created['tracker_id']
                with connect() as conn:
                    row = dict(conn.execute('SELECT * FROM trackers WHERE id=?', (tracker_id,)).fetchone())
                    self.assertEqual(row['repository'], 'example/demo')
                    self.assertEqual(row['tags'], 'one,two')
                    self.assertEqual(row['probe_mode'], 'manual')
                    self.assertIsNone(row['last_checked_at'])
                with transaction() as conn:
                    conn.execute("UPDATE trackers SET current_version='v2',last_checked_at='2026-01-01T00:00:00+00:00',last_error='old',github_retry_at='2099-01-01' WHERE id=?", (tracker_id,))
                    conn.execute("INSERT INTO events(tracker_id,version,detected_at) VALUES(?,'v2','2026-01-01')", (tracker_id,))
                await self.call(s, 'tracker_update', {'tracker_id': tracker_id, 'changes': {'notes': 'reviewed'}})
                await self.call(s, 'tracker_set_enabled', {'tracker_id': tracker_id, 'enabled': False})
                with connect() as conn:
                    self.assertEqual(conn.execute('SELECT last_checked_at FROM trackers WHERE id=?', (tracker_id,)).fetchone()[0], row['last_checked_at'] or '2026-01-01T00:00:00+00:00')
                await self.call(s, 'tracker_update', {'tracker_id': tracker_id, 'changes': {'strategy': 'tag'}})
                with connect() as conn:
                    changed = conn.execute('SELECT * FROM trackers WHERE id=?', (tracker_id,)).fetchone()
                    self.assertIsNone(changed['current_version'])
                    self.assertIsNone(changed['last_checked_at'])
                    self.assertIsNone(changed['github_retry_at'])
                    self.assertEqual(conn.execute('SELECT COUNT(*) FROM events WHERE tracker_id=?', (tracker_id,)).fetchone()[0], 1)
                self.assertTrue((await s.call_tool('tracker_delete', {'tracker_id': tracker_id, 'confirm': False})).is_error)
                removed = await self.call(s, 'tracker_delete', {'tracker_id': tracker_id, 'confirm': True})
                self.assertEqual(removed['events_deleted'], 1)
                self.assertEqual(removed['decisions_deleted'], 0)
                self.assertTrue((await s.call_tool('tracker_delete', {'tracker_id': tracker_id, 'confirm': True})).is_error)

    async def test_strict_fields_authority_rate_and_audit_rollback(self):
        key = self.write_key()
        async with self.session(key) as s:
            for changes in ({}, {'repository': 'example/other'}, {'install_host': 'example.invalid'}, {'probe_mode': 'http_auto'},
                            {'ssh_key_name': 'private'}, {'enabled': 'true'}, {'enabled': None}, {'name': ' '}, {'refresh_hours': True},
                            {'refresh_hours': 5}, {'tags': ['x'] * 13}, {'notes': 'x' * 4001}, {'homepage_url': 'javascript:alert(1)'}):
                self.assertTrue((await s.call_tool('tracker_update', {'tracker_id': self.tracker, 'changes': changes})).is_error, changes)
            with patch('radar.mcp_tools.audit', side_effect=RuntimeError('private audit failure')):
                self.assertTrue((await s.call_tool('tracker_update', {'tracker_id': self.tracker, 'changes': {'notes': 'must rollback'}})).is_error)
            with connect() as conn:
                self.assertNotEqual(conn.execute('SELECT notes FROM trackers WHERE id=?', (self.tracker,)).fetchone()[0], 'must rollback')
            for _ in range(30):
                await self.call(s, 'tracker_set_enabled', {'tracker_id': self.tracker, 'enabled': True})
            self.assertTrue((await s.call_tool('tracker_set_enabled', {'tracker_id': self.tracker, 'enabled': False})).is_error)
        _, read_key = create_key(1, 'test-password', 'read', ['read'])
        async with self.session(read_key) as s:
            unknown = await s.call_tool('does_not_exist', {})
            self.assertEqual((await s.call_tool('tracker_create', {'tracker': {'name': 'no', 'repository': 'example/no'}})).model_dump(), unknown.model_dump())
