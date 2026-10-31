"""Local offline recovery only: the operator must first stop every MCP worker."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from radar.db import audit, db_path, transaction


def recover_leases() -> int:
    if not db_path().is_file():
        raise RuntimeError('Existing application database is required.')
    with transaction(immediate=True) as conn:
        count = conn.execute('SELECT COUNT(*) FROM mcp_operation_leases').fetchone()[0]
        audit(None, 'mcp_operation_recovery', details=f'Cleared {count} leases; prior outcomes unknown; operator asserted all workers stopped.', conn=conn)
        conn.execute('DELETE FROM mcp_operation_leases')
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description='Offline recovery. You must stop and verify every MCP worker sharing this database first. This utility cannot verify worker shutdown.')
    parser.add_argument('--confirm-workers-stopped', action='store_true', help='Assert that every old worker has stopped; never use while a worker can still run.')
    args = parser.parse_args()
    if not args.confirm_workers_stopped:
        parser.error('Stop and verify every MCP worker, then supply --confirm-workers-stopped. No mutation performed.')
    try:
        count = recover_leases()
    except Exception:
        print('Recovery failed. Lease state retained; check the database privately.', file=sys.stderr)
        return 1
    print(f'Cleared {count} leases. Prior outcomes remain unknown; inspect tracker state before retrying.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
