"""Several processes starting on a brand-new database must all initialise it.

Docker Compose starts two web workers, the scheduler and the inventory worker
at once. Before the fix, one of them could fail with "database is locked" while
switching to WAL, or with "duplicate column name" during migrations.
"""
import multiprocessing
import os
import tempfile
import unittest
from pathlib import Path


def _start(path, barrier, results):
    os.environ["RADAR_DB"] = path
    from radar.db import init_db
    barrier.wait()
    try:
        init_db()
        results.put("ok")
    except Exception as exc:  # reported to the parent test
        results.put(repr(exc))


class ConcurrentStartupTests(unittest.TestCase):
    def test_parallel_init_on_fresh_database(self):
        context = multiprocessing.get_context("spawn")
        for _ in range(4):
            with tempfile.TemporaryDirectory() as tmp:
                path = str(Path(tmp) / "radar.db")
                barrier, results = context.Barrier(4), context.Queue()
                processes = [context.Process(target=_start, args=(path, barrier, results)) for _ in range(4)]
                for process in processes:
                    process.start()
                for process in processes:
                    process.join(60)
                self.assertEqual(sorted(results.get(timeout=5) for _ in processes), ["ok"] * 4)


if __name__ == "__main__":
    unittest.main()
