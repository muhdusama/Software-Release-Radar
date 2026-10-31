"""Inventory enqueue must remain atomic across web and MCP processes."""
import multiprocessing
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from radar.db import audit, connect, init_db, transaction
from radar.inventory_jobs import enqueue_sync


def enqueue_child(path, start, results, supplied):
    os.environ['RADAR_DB'] = path
    if not start.wait(10):
        raise RuntimeError('start barrier timed out')
    if supplied:
        with transaction(immediate=True) as conn:
            result = enqueue_sync(conn=conn)
    else:
        result = enqueue_sync()
    results.put(result)


class InventoryEnqueueConcurrencyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = str(Path(self.temp.name) / 'radar.db')
        self.env = patch.dict(os.environ, {'RADAR_DB': self.path, 'ADMIN_PASSWORD_HASH': ''})
        self.env.start()
        self.addCleanup(self.env.stop)
        init_db()

    def test_enqueue_and_attributed_audit_roll_back_together(self):
        with self.assertRaisesRegex(RuntimeError, 'abort'):
            with transaction(immediate=True) as conn:
                job_id, created = enqueue_sync(conn=conn)
                self.assertTrue(created)
                audit(None, 'mcp_inventory_sync', 'job', job_id, conn=conn, api_key_id='test-key')
                raise RuntimeError('abort')
        with connect() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM portainer_sync_jobs').fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM audit_log').fetchone()[0], 0)

    def test_supplied_connection_remains_open_and_uncommitted(self):
        with transaction(immediate=True) as conn:
            job_id, created = enqueue_sync(conn=conn)
            audit(None, 'mcp_inventory_sync', 'job', job_id, conn=conn, api_key_id='test-key')
            self.assertTrue(created)
            self.assertTrue(conn.in_transaction)
            with connect() as reader:
                self.assertEqual(reader.execute('SELECT COUNT(*) FROM audit_log').fetchone()[0], 0)
        with connect() as conn:
            row = conn.execute('SELECT api_key_id,target_id FROM audit_log').fetchone()
            self.assertEqual(tuple(row), ('test-key', str(job_id)))

    def test_direct_and_supplied_enqueue_deduplicate_across_processes(self):
        context = multiprocessing.get_context('spawn')
        for supplied in (False, True):
            with self.subTest(supplied=supplied):
                with transaction() as conn:
                    conn.execute('DELETE FROM portainer_sync_jobs')
                start, results = context.Event(), context.Queue()
                processes = [context.Process(target=enqueue_child,
                             args=(self.path, start, results, supplied)) for _ in range(8)]
                try:
                    for process in processes:
                        process.start()
                    start.set()
                    rows = [results.get(timeout=35) for _ in processes]
                    for process in processes:
                        process.join(35)
                        self.assertEqual(process.exitcode, 0)
                    self.assertEqual(len({row[0] for row in rows}), 1)
                    self.assertEqual(sum(row[1] for row in rows), 1)
                    with connect() as conn:
                        self.assertEqual(conn.execute('SELECT COUNT(*) FROM portainer_sync_jobs').fetchone()[0], 1)
                finally:
                    for process in processes:
                        if process.is_alive():
                            process.terminate()
                            process.join(5)
                    results.close()
                    results.join_thread()
