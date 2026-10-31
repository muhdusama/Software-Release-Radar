import multiprocessing
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from radar.auth import hash_password
from radar.db import connect, init_db, transaction, utcnow
from radar.upgrade_workflow import save_upgrade_review


def race_save(path, deployed, ready, queue):
    with patch.dict(os.environ, {'RADAR_DB': path}):
        ready.wait(10)
        try:
            result = save_upgrade_review(1, 'v2', 1, {'decision_status': 'wait'}, user_id=1, mark_deployed=deployed)
            queue.put(('ok', result['revision']))
        except ValueError:
            queue.put(('conflict', None))


class UpgradeConcurrencyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = str(Path(self.tmp.name) / 'radar.db')
        self.env = patch.dict(os.environ, {'RADAR_DB': self.path, 'ADMIN_USERNAME': 'admin',
                'ADMIN_PASSWORD_HASH': hash_password('test-password', iterations=1000)})
        self.env.start()
        self.addCleanup(self.env.stop)
        init_db()
        with transaction() as conn:
            conn.execute("INSERT INTO trackers(id,name,repository,current_version,created_at,updated_at) VALUES(1,'Example','example/project','v2',?,?)", (utcnow(), utcnow()))

    def save(self, revision=0, release='v2', deployed=False, **review):
        return save_upgrade_review(1, release, revision, review, user_id=1, mark_deployed=deployed)

    def test_revisions_release_binding_and_deployed_immutability(self):
        first = self.save(decision_status='update')
        self.assertEqual(first['revision'], 1)
        with self.assertRaises(ValueError):
            self.save()
        with transaction() as conn:
            conn.execute("UPDATE trackers SET current_version='v3' WHERE id=1")
        with self.assertRaises(ValueError):
            self.save(0, release='unknown')
        with self.assertRaises(ValueError):
            self.save(1, deployed=True)
        self.assertEqual(self.save(1, decision_notes='historical')['revision'], 2)
        current = self.save(0, release='v3', deployed=True)
        self.assertEqual(current['decision_status'], 'deployed')
        for deployed in (False, True):
            with self.assertRaises(ValueError):
                self.save(current['revision'], release='v3', deployed=deployed)

    def test_same_revision_process_race(self):
        self.save()
        ctx = multiprocessing.get_context('spawn')
        ready, queue = ctx.Event(), ctx.Queue()
        children = [ctx.Process(target=race_save, args=(self.path, flag, ready, queue)) for flag in (False, True)]
        try:
            for child in children:
                child.start()
            ready.set()
            results = [queue.get(timeout=20) for _ in children]
            for child in children:
                child.join(20)
                self.assertEqual(child.exitcode, 0)
            self.assertEqual(sum(item[0] == 'ok' for item in results), 1)
            with connect() as conn:
                row = conn.execute('SELECT * FROM upgrade_decisions').fetchone()
            if row['decision_status'] != 'deployed':
                self.save(row['revision'], deployed=True)
            with self.assertRaises(ValueError):
                self.save(1, decision_status='wait')
        finally:
            for child in children:
                if child.is_alive():
                    child.terminate()
                    child.join(5)
            queue.close()
            queue.join_thread()

    def test_validation_audit_rollback_and_additive_migration(self):
        for review in ({'decision_status': 'deployed'}, {'priority': 'bad'}, {'risk': 'bad'},
                       {'maintenance_date': 'wrong'}, {'change_record_url': 'javascript:bad'},
                       {'decision_notes': 'x' * 10001}, {'checklist': [{'text': 'x', 'done': 'false'}]}):
            with self.assertRaises(ValueError):
                self.save(**review)
        with patch('radar.upgrade_workflow.audit', side_effect=RuntimeError('audit failed')):
            with self.assertRaises(RuntimeError):
                self.save()
        with connect() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM upgrade_decisions').fetchone()[0], 0)
        self.save()
        with transaction() as conn:
            conn.execute('ALTER TABLE upgrade_decisions DROP COLUMN revision')
        init_db()
        init_db()
        with connect() as conn:
            self.assertEqual(conn.execute('SELECT revision FROM upgrade_decisions').fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM upgrade_decisions').fetchone()[0], 1)


if __name__ == '__main__':
    unittest.main()
