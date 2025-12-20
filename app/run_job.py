"""CLI entrypoint to run archive jobs as a detached subprocess.

Usage:
  python -m app.run_job --archive-id 42 [--dry-run] [--no-stop-containers] [--no-create-archive] [--no-run-retention]

This script loads the archive from the database and executes ArchiveExecutor.
It writes stdout/stderr to a per-job log under /var/log/archiver and relies on
executor.log() + DB persistence + SSE (Redis) for live tailing.
"""
import argparse
import json
import os
import sys
from pathlib import Path

from app.db import get_db
from app.executor import ArchiveExecutor
from app import utils


def parse_args(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument('--archive-id', type=int, required=True)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--job-id', type=int, help='Existing job id to attach to this run (optional)')
    parser.add_argument('--no-stop-containers', action='store_true')
    parser.add_argument('--no-create-archive', action='store_true')
    parser.add_argument('--no-run-retention', action='store_true')
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv or sys.argv[1:])

    # Load archive
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM archives WHERE id = %s;", (args.archive_id,))
        archive = cur.fetchone()

    if not archive:
        print(f"Archive id={args.archive_id} not found", file=sys.stderr)
        sys.exit(2)

    # Build dry run config if requested
    dry_run_config = None
    if args.dry_run:
        dry_run_config = {
            'stop_containers': not args.no_stop_containers,
            'create_archive': not args.no_create_archive,
            'run_retention': not args.no_run_retention,
        }

    # Ensure job log dir exists
    jobs_dir = Path(os.environ.get('ARCHIVE_JOB_LOG_DIR', '/var/log/archiver'))
    try:
        jobs_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    timestamp = utils.local_now().strftime('%Y%m%d_%H%M%S')
    archive_name = archive['name']
    log_name = f"job_{archive_name}_{timestamp}.log"
    log_path = jobs_dir / log_name

    # Redirect stdout/stderr to log file
    try:
        with open(log_path, 'ab') as fh:
            # Small wrapper to write both stdout/stderr to file while still printing to console
            # Execute the job
            executor = ArchiveExecutor(dict(archive), is_dry_run=args.dry_run, dry_run_config=dry_run_config)
            # Flush any prints to file
            executor.run(triggered_by='subprocess', job_id=args.job_id)
    except Exception as e:
        # Ensure exceptions are visible in the log
        try:
            with open(log_path, 'ab') as fh:
                fh.write((str(e) + '\n').encode('utf-8', errors='replace'))
        except Exception:
            pass
        raise


if __name__ == '__main__':
    main()
