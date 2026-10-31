"""Operations keep durable ownership through disconnect, failure and recovery."""
import asyncio
import importlib.util
import json
import multiprocessing
import os
from pathlib import Path
import subprocess
import sys
import threading
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import httpx2
from mcp.server.auth.provider import AccessToken

import test_mcp_reads as fixtures
from radar.checker import CheckResult
from radar.db import connect, transaction, utcnow
from radar.mcp_auth import create_key, Principal
from radar.probes import ProbeResult


def acquire_child(db, key_id, user_id, ready, queue):
    from radar.mcp_tools import acquire_operation
    with patch.dict(os.environ, {'RADAR_DB': db}), patch('radar.mcp_auth.get_access_token',
            return_value=AccessToken(token=key_id, client_id=key_id, scopes=['read', 'operations:run'])):
        ready.wait(10)
        try:
            lease = acquire_operation(Principal(key_id, user_id, True, frozenset({'read', 'operations:run'})), 'tracker_check', 1)
            queue.put(('acquired', lease))
        except Exception:
            queue.put(('blocked', None))


class MCPOperationTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.MCPReadTests.asyncSetUp
    asyncTearDown = fixtures.MCPReadTests.asyncTearDown
    session = fixtures.MCPReadTests.session
    call = fixtures.MCPReadTests.call

    def ops_key(self):
        return create_key(1, 'test-password', 'operations', ['read', 'operations:run'])

    async def test_declared_check_probe_and_enqueue_effects(self):
        _, key = self.ops_key()
        async with self.session(key) as s:
            self.assertEqual({t.name for t in (await s.list_tools()).tools}, fixtures.READS |
                             {'tracker_check', 'tracker_probe', 'inventory_sync'})
            result = CheckResult(self.tracker, 'Example', 'example/project', 'ok', version='v3', changed=True, event_id=42)
            with patch('radar.mcp_tools.check_tracker', return_value=result) as check, \
                 patch('radar.mcp_tools.dispatch_release_notifications', return_value={'sent': 2, 'failed': 0, 'skipped': 1}) as notify, \
                 patch('radar.checker.probe_tracker', side_effect=AssertionError('probe forbidden')), \
                 patch('radar.portainer.sync_inventory', side_effect=AssertionError('sync forbidden')):
                response = await self.call(s, 'tracker_check', {'tracker_id': self.tracker, 'confirm': True})
                self.assertEqual(response['notifications']['sent'], 2)
                check.assert_called_once_with(self.tracker, run_probe=False)
                notify.assert_called_once_with([42])
            with patch('radar.mcp_tools.probe_tracker', return_value=ProbeResult(self.tracker, 'ok', True, 'v2', 3)) as probe:
                response = await self.call(s, 'tracker_probe', {'tracker_id': self.tracker, 'confirm': True})
                self.assertEqual(response['source_kind'], 'live')
                probe.assert_called_once_with(self.tracker, refresh_portainer=False)
            first = await self.call(s, 'inventory_sync')
            second = await self.call(s, 'inventory_sync')
            self.assertEqual(first['job_id'], self.job)
            self.assertEqual(first['job_id'], second['job_id'])
            self.assertTrue(second['reused'])
        with connect() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM mcp_operation_leases').fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM audit_log WHERE action='mcp_operation_dispatch'").fetchone()[0], 4)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM audit_log WHERE action='mcp_operation_outcome'").fetchone()[0], 4)

    async def test_confirmation_fresh_authority_and_sanitised_failures(self):
        key_id, key = self.ops_key()
        async with self.session(key) as s:
            with patch('radar.mcp_tools.check_tracker') as check, patch('radar.mcp_tools.probe_tracker') as probe:
                for name in ('tracker_check', 'tracker_probe'):
                    for args in ({'tracker_id': self.tracker}, {'tracker_id': self.tracker, 'confirm': False},
                                 {'tracker_id': self.tracker, 'confirm': 'true'}):
                        self.assertTrue((await s.call_tool(name, args)).is_error)
                check.assert_not_called()
                probe.assert_not_called()
            with patch('radar.mcp_tools.check_tracker', side_effect=RuntimeError(self.canary)):
                with self.assertLogs(level='INFO') as logs:
                    result = await s.call_tool('tracker_check', {'tracker_id': self.tracker, 'confirm': True})
                self.assertTrue(result.is_error)
                self.assertNotIn(self.canary, result.model_dump_json() + repr(logs.output))
            with transaction() as conn:
                conn.execute("UPDATE users SET role='user' WHERE id=1")
            self.assertTrue((await s.call_tool('tracker_check', {'tracker_id': self.tracker, 'confirm': True})).is_error)
        from radar.mcp_tools import acquire_operation
        with patch('radar.mcp_auth.get_access_token', return_value=AccessToken(token=key_id, client_id=key_id, scopes=['read', 'operations:run'])):
            with self.assertRaises(Exception):
                acquire_operation(Principal(key_id, 1, True, frozenset({'read', 'operations:run'})), 'tracker_check', self.tracker)
        with connect() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM mcp_operation_leases').fetchone()[0], 0)

    async def test_real_check_baseline_change_analysis_and_cooldown(self):
        from radar.github import ReleaseInfo
        _, key = self.ops_key()
        with patch('radar.checker.get_latest', return_value=ReleaseInfo('v3', 'Third', 'https://example.invalid/v3', 'body', utcnow())), \
             patch('radar.auto_analysis.chat', return_value=('review', 'fixture-model')) as model, \
             patch('radar.mcp_tools.dispatch_release_notifications', return_value={'sent': 1, 'failed': 0, 'skipped': 0}) as notify, \
             patch('radar.checker.probe_tracker', side_effect=AssertionError('probe forbidden')), \
             patch('radar.checker.sync_inventory', side_effect=AssertionError('sync forbidden')):
            async with self.session(key) as s:
                with transaction() as conn:
                    conn.execute('UPDATE trackers SET enabled=0 WHERE id=?', (self.tracker,))
                changed = await self.call(s, 'tracker_check', {'tracker_id': self.tracker, 'confirm': True})
                self.assertTrue(changed['changed'])
                model.assert_not_called()
                await self.call(s, 'tracker_check', {'tracker_id': self.tracker, 'confirm': True})
                self.assertEqual(notify.call_count, 1)
                with transaction() as conn:
                    conn.execute('UPDATE trackers SET current_version=NULL WHERE id=?', (self.tracker,))
                baseline = await self.call(s, 'tracker_check', {'tracker_id': self.tracker, 'confirm': True})
                self.assertTrue(baseline['baseline'])
                self.assertEqual(notify.call_count, 1)
                with transaction() as conn:
                    conn.execute("UPDATE settings SET value='1' WHERE key='openai_auto_analyse'")
                with patch('radar.checker.get_latest', return_value=ReleaseInfo('v4', 'Fourth', 'https://example.invalid/v4', 'body', utcnow())):
                    await self.call(s, 'tracker_check', {'tracker_id': self.tracker, 'confirm': True})
                    model.assert_called_once()
                with patch('radar.checker.shared_rate_limit_until', return_value=datetime(2099, 1, 1, tzinfo=timezone.utc)), \
                     patch('radar.checker.get_latest', side_effect=AssertionError('cooldown network')):
                    self.assertEqual((await self.call(s, 'tracker_check', {'tracker_id': self.tracker, 'confirm': True}))['status'], 'deferred')

    async def test_cached_inventory_probe_never_refreshes_and_unconfigured_runs_nothing(self):
        _, key = self.ops_key()
        with transaction() as conn:
            conn.execute("UPDATE trackers SET probe_mode='portainer',portainer_service_id=1 WHERE id=?", (self.tracker,))
            conn.execute("INSERT OR REPLACE INTO settings(key,value,updated_at) VALUES('portainer_last_sync_at',?,?)", (utcnow(), utcnow()))
        with patch('radar.probes.sync_inventory', side_effect=AssertionError('sync forbidden')):
            async with self.session(key) as s:
                response = await self.call(s, 'tracker_probe', {'tracker_id': self.tracker, 'confirm': True})
                self.assertEqual(response['source_kind'], 'cached_inventory')
                self.assertEqual(response['provider'], 'portainer')
                self.assertIsNotNone(response['inventory_synced_at'])
                with transaction() as conn:
                    conn.execute("UPDATE trackers SET probe_mode='manual',install_host=NULL WHERE id=?", (self.tracker,))
                with patch('radar.mcp_tools.probe_tracker') as probe:
                    self.assertTrue((await s.call_tool('tracker_probe', {'tracker_id': self.tracker, 'confirm': True})).is_error)
                    probe.assert_not_called()

    async def test_all_durable_concurrency_caps_and_deleted_owner(self):
        from radar.mcp_tools import acquire_operation, release_operation
        keys = [self.ops_key()[0] for _ in range(3)]
        def acquire(key, tracker=None):
            with patch('radar.mcp_auth.get_access_token', return_value=AccessToken(token=key, client_id=key, scopes=['read', 'operations:run'])):
                return acquire_operation(Principal(key, 1, True, frozenset({'read', 'operations:run'})),
                                         'tracker_check' if tracker else 'inventory_sync', tracker)
        first = acquire(keys[0], self.tracker)
        with self.assertRaises(Exception):
            acquire(keys[0])
        second = acquire(keys[1])
        with self.assertRaises(Exception):
            acquire(keys[2])
        release_operation(second, 'succeeded')
        third = acquire(keys[2])
        with transaction() as conn:
            conn.execute('DELETE FROM users WHERE id=1')
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM mcp_operation_leases').fetchone()[0], 2)
        release_operation(first, 'unknown')
        release_operation(third, 'unknown')
        with connect() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM mcp_operation_leases').fetchone()[0], 0)

    async def test_disconnect_does_not_release_lease_or_allow_overlapping_probe(self):
        _, key = self.ops_key()
        _, other = self.ops_key()
        entered, finish = threading.Event(), threading.Event()
        def blocked(*args, **kwargs):
            entered.set()
            finish.wait(10)
            return CheckResult(self.tracker, 'Example', 'example/project', 'ok')
        try:
            with patch('radar.mcp_tools.check_tracker', side_effect=blocked):
                async with httpx2.AsyncClient(headers={'Authorization': 'Bearer ' + key}, trust_env=False, timeout=.1) as client:
                    with self.assertRaises(httpx2.TimeoutException):
                        await client.post('http://' + self.host + '/mcp', headers={'Accept': 'application/json, text/event-stream'},
                            json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
                                  'params': {'name': 'tracker_check', 'arguments': {'tracker_id': self.tracker, 'confirm': True}}})
                self.assertTrue(entered.is_set())
                with transaction() as conn:
                    conn.execute("UPDATE mcp_operation_leases SET created_at='1900-01-01T00:00:00+00:00'")
                    self.assertEqual(conn.execute('SELECT COUNT(*) FROM mcp_operation_leases').fetchone()[0], 1)
                async with self.session(other) as s:
                    result = await s.call_tool('tracker_probe', {'tracker_id': self.tracker, 'confirm': True})
                    self.assertTrue(result.is_error)
                    self.assertIn('awaiting operator recovery', result.model_dump_json())
                with transaction() as conn:
                    conn.execute('DELETE FROM mcp_keys WHERE id IN (SELECT key_id FROM mcp_operation_leases)')
                    self.assertEqual(conn.execute('SELECT COUNT(*) FROM mcp_operation_leases').fetchone()[0], 1)
                finish.set()
                for _ in range(200):
                    with connect() as conn:
                        count = conn.execute('SELECT COUNT(*) FROM mcp_operation_leases').fetchone()[0]
                    if count == 0:
                        break
                    await asyncio.sleep(.01)
                self.assertEqual(count, 0)
        finally:
            finish.set()

    async def test_audit_failures_preserve_atomic_ownership_and_enqueue(self):
        _, key = self.ops_key()
        from radar import mcp_tools
        original = mcp_tools.audit
        async with self.session(key) as s:
            def fail_dispatch(*args, **kwargs):
                if args[1] == 'mcp_operation_dispatch':
                    raise RuntimeError(self.canary)
                return original(*args, **kwargs)
            with patch('radar.mcp_tools.audit', side_effect=fail_dispatch), patch('radar.mcp_tools.check_tracker') as check:
                self.assertTrue((await s.call_tool('tracker_check', {'tracker_id': self.tracker, 'confirm': True})).is_error)
                check.assert_not_called()
            def fail_outcome(*args, **kwargs):
                if args[1] == 'mcp_operation_outcome':
                    raise RuntimeError(self.canary)
                return original(*args, **kwargs)
            with patch('radar.mcp_tools.audit', side_effect=fail_outcome), \
                 patch('radar.mcp_tools.check_tracker', return_value=CheckResult(self.tracker, 'Example', 'example/project', 'ok')):
                self.assertTrue((await s.call_tool('tracker_check', {'tracker_id': self.tracker, 'confirm': True})).is_error)
            with connect() as conn:
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM mcp_operation_leases').fetchone()[0], 1)
        from radar.mcp_server import build_app
        build_app()
        with connect() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM mcp_operation_leases').fetchone()[0], 1)

    async def test_rate_caps_and_multiprocess_durable_uniqueness(self):
        key_id, key = self.ops_key()
        with patch.dict(os.environ, {'MCP_OPERATION_HOURLY_LIMIT': '1'}):
            async with self.session(key) as s:
                await self.call(s, 'inventory_sync')
                self.assertTrue((await s.call_tool('inventory_sync', {})).is_error)
                with transaction() as conn:
                    conn.execute("UPDATE mcp_rate_counters SET expires_at='2000-01-01T00:00:00+00:00'")
                await self.call(s, 'inventory_sync')
        ctx = multiprocessing.get_context('spawn')
        ready, queue = ctx.Event(), ctx.Queue()
        children = [ctx.Process(target=acquire_child, args=(os.environ['RADAR_DB'], key_id, 1, ready, queue)) for _ in range(6)]
        try:
            for child in children:
                child.start()
            ready.set()
            results = [await asyncio.to_thread(queue.get, True, 20) for _ in children]
            for child in children:
                await asyncio.to_thread(child.join, 20)
                self.assertEqual(child.exitcode, 0)
            self.assertEqual(sum(r[0] == 'acquired' for r in results), 1)
        finally:
            for child in children:
                if child.is_alive():
                    child.terminate()
                    child.join(5)
            queue.close()
            queue.join_thread()

    async def test_offline_recovery_requires_confirmation_and_atomic_audit(self):
        key_id, _ = self.ops_key()
        with transaction() as conn:
            conn.execute('INSERT INTO mcp_operation_leases(id,key_id,user_id,tool,tracker_id,created_at) VALUES(?,?,?,?,?,?)',
                         ('stale', key_id, 1, 'tracker_check', self.tracker, '1900-01-01'))
        command = [sys.executable, 'scripts/mcp_recover_leases.py']
        result = await asyncio.to_thread(subprocess.run, command, capture_output=True, text=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        with connect() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM mcp_operation_leases').fetchone()[0], 1)
        spec = importlib.util.spec_from_file_location('recover', 'scripts/mcp_recover_leases.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with patch.object(module, 'audit', side_effect=RuntimeError(self.canary)):
            with self.assertRaises(RuntimeError):
                module.recover_leases()
        with connect() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM mcp_operation_leases').fetchone()[0], 1)
        result = await asyncio.to_thread(subprocess.run, command + ['--confirm-workers-stopped'], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn(key_id, result.stdout)
        with connect() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM mcp_operation_leases').fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM trackers').fetchone()[0], 1)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM portainer_sync_jobs').fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM audit_log WHERE action='mcp_operation_recovery'").fetchone()[0], 1)


if __name__ == '__main__':
    unittest.main()
