import argparse
import contextlib
import io
import json
import multiprocessing
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from radar import manage
from radar.auth import hash_password
from radar.db import connect, init_db, transaction, utcnow
from radar.upgrade_workflow import save_upgrade_review


def decide_args(**kw):
    base = dict(repository=None, tracker_id=1, confirm=True, decision='update', priority=None, risk=None,
                maintenance_date=None, checklist_item=None, checklist_done=None, rollback_notes=None,
                change_record_url=None, notes=None)
    return argparse.Namespace(**{**base, **kw})


def deploy_args(**kw):
    return argparse.Namespace(**{**dict(repository=None, tracker_id=1, confirm=True, notes=None), **kw})


def run(function, args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        function(args)
    return json.loads(out.getvalue())


def race_cli(path, action, ready, queue):
    with patch.dict(os.environ, {'RADAR_DB': path}):
        ready.wait(10)
        try:
            if action == 'decide':
                run(manage.decide_upgrade, decide_args(decision='wait'))
            elif action == 'deploy':
                run(manage.mark_upgrade_deployed, deploy_args())
            else:
                save_upgrade_review(1, 'v2', 0, {'decision_status': 'ignore'}, user_id=1)
            queue.put('ok')
        except ValueError:
            queue.put('conflict')


class CliUpgradeIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = str(Path(self.tmp.name) / 'radar.db')
        env = patch.dict(os.environ, {'RADAR_DB': self.path, 'ADMIN_USERNAME': 'admin',
                                      'ADMIN_PASSWORD_HASH': hash_password('test-password', iterations=1000)})
        env.start()
        self.addCleanup(env.stop)
        init_db()
        with transaction() as conn:
            conn.execute("INSERT INTO trackers(id,name,repository,current_version,current_release_name,installed_version,created_at,updated_at)"
                         " VALUES(1,'Example','example/project','v2','v2','v1',?,?)", (utcnow(), utcnow()))

    def row(self, release='v2'):
        with connect() as conn:
            return conn.execute('SELECT * FROM upgrade_decisions WHERE release_version=?', (release,)).fetchone()

    def audits(self, action):
        with connect() as conn:
            return conn.execute('SELECT COUNT(*) FROM audit_log WHERE action=?', (action,)).fetchone()[0]

    def test_new_decision_starts_at_revision_one_and_edit_invalidates_stale_reader(self):
        run(manage.decide_upgrade, decide_args())
        self.assertEqual(self.row()['revision'], 1)
        run(manage.decide_upgrade, decide_args(decision='wait', notes='cli edit'))
        self.assertEqual(self.row()['revision'], 2)
        with self.assertRaises(ValueError):  # browser/MCP reader still holding revision 1
            save_upgrade_review(1, 'v2', 1, {'decision_status': 'ignore'}, user_id=1)
        row = self.row()
        self.assertEqual((row['decision_status'], row['decision_notes'], row['updated_by']), ('wait', 'cli edit', None))
        self.assertEqual(self.audits('cli_upgrade_decision_saved'), 2)

    def test_partial_edit_preserves_unspecified_fields(self):
        run(manage.decide_upgrade, decide_args(priority='high', risk='low', notes='keep', checklist_item=['a', 'b'], checklist_done=[1]))
        run(manage.decide_upgrade, decide_args(decision='wait'))
        row = self.row()
        self.assertEqual((row['priority'], row['risk'], row['decision_notes']), ('high', 'low', 'keep'))
        self.assertEqual(json.loads(row['checklist_json']), [{'text': 'a', 'done': False}, {'text': 'b', 'done': True}])

    def test_deployment_advances_revision_and_is_idempotent_and_immutable(self):
        run(manage.decide_upgrade, decide_args())
        first = run(manage.mark_upgrade_deployed, deploy_args())
        row = self.row()
        self.assertEqual((row['decision_status'], row['revision'], row['previous_version'], row['deployed_version']), ('deployed', 2, 'v1', 'v2'))
        self.assertEqual(first['previous_version'], 'v1')
        with self.assertRaises(ValueError):
            save_upgrade_review(1, 'v2', 1, {'decision_status': 'wait'}, user_id=1)
        with self.assertRaises(ValueError):
            run(manage.decide_upgrade, decide_args(decision='wait'))
        again = run(manage.mark_upgrade_deployed, deploy_args())  # intentional no-op
        self.assertEqual(again['deployed_at'], first['deployed_at'])
        self.assertEqual(self.row()['revision'], 2)

    def test_deployment_without_prior_decision_creates_revision_one(self):
        run(manage.mark_upgrade_deployed, deploy_args(notes='shipped'))
        row = self.row()
        self.assertEqual((row['decision_status'], row['revision'], row['decision_notes'], row['updated_by']), ('deployed', 1, 'shipped', None))

    def test_confirmation_is_still_required(self):
        for function, args in ((manage.decide_upgrade, decide_args(confirm=False)), (manage.mark_upgrade_deployed, deploy_args(confirm=False))):
            with self.assertRaises(ValueError):
                function(args)
        self.assertIsNone(self.row())

    def test_changed_release_creates_current_record_and_leaves_history_unchanged(self):
        run(manage.decide_upgrade, decide_args())
        with transaction() as conn:
            conn.execute("UPDATE trackers SET current_version='v3', current_release_name='v3' WHERE id=1")
        run(manage.mark_upgrade_deployed, deploy_args())
        old, new = self.row('v2'), self.row('v3')
        self.assertEqual((old['decision_status'], old['revision']), ('update', 1))
        self.assertEqual((new['decision_status'], new['revision']), ('deployed', 1))

    def test_browser_helper_still_requires_admin_and_cli_path_has_no_identity(self):
        with self.assertRaises(ValueError):
            save_upgrade_review(1, 'v2', 0, {}, user_id=None)
        with self.assertRaises(ValueError):
            save_upgrade_review(1, 'v2', 0, {}, user_id=1, cli=True)

    def test_audit_failure_rolls_back_mutation(self):
        run(manage.decide_upgrade, decide_args())
        for function, args in ((manage.decide_upgrade, decide_args(decision='wait')), (manage.mark_upgrade_deployed, deploy_args())):
            with patch('radar.upgrade_workflow.audit', side_effect=RuntimeError('audit failed')):
                with self.assertRaises(RuntimeError):
                    function(args)
            row = self.row()
            self.assertEqual((row['decision_status'], row['revision']), ('update', 1))
        with patch('radar.upgrade_workflow.audit', side_effect=RuntimeError('audit failed')):
            with self.assertRaises(RuntimeError):
                run(manage.decide_upgrade, decide_args(tracker_id=1, decision='review', notes='x'))
        with transaction() as conn:
            conn.execute('DELETE FROM upgrade_decisions')
        with patch('radar.upgrade_workflow.audit', side_effect=RuntimeError('audit failed')):
            with self.assertRaises(RuntimeError):
                run(manage.decide_upgrade, decide_args())
        self.assertIsNone(self.row())

    def test_concurrent_creation_and_races_leave_one_consistent_record(self):
        for actions in (('decide', 'decide'), ('decide', 'deploy'), ('deploy', 'browser'), ('decide', 'browser')):
            with transaction() as conn:
                conn.execute('DELETE FROM upgrade_decisions')
            ctx = multiprocessing.get_context('spawn')
            ready, queue = ctx.Event(), ctx.Queue()
            children = [ctx.Process(target=race_cli, args=(self.path, action, ready, queue)) for action in actions]
            try:
                for child in children:
                    child.start()
                ready.set()
                results = [queue.get(timeout=30) for _ in children]
                for child in children:
                    child.join(30)
                    self.assertEqual(child.exitcode, 0)
            finally:
                for child in children:
                    if child.is_alive():
                        child.terminate()
                queue.close()
                queue.join_thread()
            with connect() as conn:
                rows = conn.execute('SELECT * FROM upgrade_decisions').fetchall()
            self.assertEqual(len(rows), 1, actions)
            # every successful writer advanced the revision exactly once; a loser conflicted instead of overwriting
            self.assertEqual(rows[0]['revision'], results.count('ok'), (actions, results))
            self.assertGreaterEqual(results.count('ok'), 1)
            if 'deploy' in actions and rows[0]['decision_status'] != 'deployed':
                self.fail((actions, results))

if __name__ == '__main__':
    unittest.main()
