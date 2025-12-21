"""
Cleanup tasks for orphaned files and old data.
"""
import os
import shutil
from pathlib import Path
from datetime import datetime, timedelta
from app.db import get_db
from app.notifications import get_setting
from app import utils


ARCHIVE_BASE = '/archives'


def run_cleanup(dry_run_override=None):
    """Run all cleanup tasks.

    If `dry_run_override` is provided (True/False), it overrides the configured
    `cleanup_dry_run` setting for this invocation.
    """
    from app.notifications import get_setting
    from datetime import datetime
    
    # Check if cleanup is enabled
    enabled = get_setting('cleanup_enabled', 'true').lower() == 'true'
    if not enabled:
        print("[Cleanup] Cleanup task is disabled in settings")
        return
    
    is_dry_run = get_setting('cleanup_dry_run', 'false').lower() == 'true'
    if dry_run_override is not None:
        is_dry_run = bool(dry_run_override)

    log_retention_days = int(get_setting('cleanup_log_retention_days', '90'))
    notify_cleanup = get_setting('notify_on_cleanup', 'false').lower() == 'true'
    
    mode = "DRY RUN" if is_dry_run else "LIVE"
    start_time = utils.now()
    
    # Create job record
    job_id = None
    log_lines = []
    
    def log_message(level, message):
        timestamp = utils.local_now().strftime('%Y-%m-%d %H:%M:%S')
        log_line = f"[{timestamp}] [{level}] {message}\n"
        log_lines.append(log_line)
        print(f"[Cleanup] {message}")
    
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO jobs (job_type, status, start_time, triggered_by, is_dry_run, log)
                VALUES ('cleanup', 'running', %s, 'scheduled', %s, '')
                RETURNING id;
            """, (start_time, is_dry_run))
            job_id = cur.fetchone()['id']
            conn.commit()
    except Exception as e:
        print(f"[Cleanup] Failed to create job record: {e}")
        # Continue anyway
    
    log_message('INFO', f"Starting cleanup task ({mode})")
    
    # Run cleanup tasks and collect stats
    try:
        orphaned_stats = cleanup_orphaned_archives(is_dry_run, log_message)
        log_stats = cleanup_old_logs(log_retention_days, is_dry_run, log_message)
        temp_stats = cleanup_temp_files(is_dry_run, log_message)
        
        total_reclaimed = orphaned_stats.get('reclaimed', 0) + temp_stats.get('reclaimed', 0)
        
        # If dry-run, include a structured report in the log so operators can review candidates
        if is_dry_run:
            try:
                report = generate_cleanup_report()
                log_message('INFO', '--- Cleanup Dry-Run Report ---')
                # Orphaned archive dirs
                if report.get('orphaned'):
                    log_message('INFO', f"Orphaned archive directories (not in DB): {len(report['orphaned'])}")
                    for o in report['orphaned']:
                        log_message('INFO', f"  - {o['name']} ({format_bytes(o['size'])})")
                else:
                    log_message('INFO', 'Orphaned archive directories: None')

                # Old logs
                log_message('INFO', f"Old job logs older than retention: {report.get('old_logs_count', 0)}")

                # Temp items
                if report.get('temp_items'):
                    log_message('INFO', f"Empty/Temp stack directories: {len(report['temp_items'])}")
                    for t in report['temp_items']:
                        flag = 'KEEP' if t['has_active_db_ref'] else 'DELETE'
                        log_message('INFO', f"  - {t['display_path']} -> {t['path']} [{flag}] {t['reference_info']}")
                else:
                    log_message('INFO', 'Empty/Temp stack directories: None')

                log_message('INFO', '--- End Cleanup Dry-Run Report ---')
            except Exception as e:
                log_message('ERROR', f'Failed to generate dry-run report: {e}')

        log_message('INFO', f"Cleanup task completed ({mode})")
        log_message('INFO', f"Total reclaimed: {format_bytes(total_reclaimed)}")
        
        # Update job status
        if job_id:
            with get_db() as conn:
                cur = conn.cursor()
                end_time = utils.now()
                cur.execute("""
                    UPDATE jobs 
                    SET status = 'success', end_time = %s, 
                        reclaimed_size_bytes = %s, log = %s
                    WHERE id = %s;
                """, (end_time, total_reclaimed, ''.join(log_lines), job_id))
                conn.commit()
        
        # Send notification if enabled
        if notify_cleanup:
            send_cleanup_notification(orphaned_stats, log_stats, temp_stats, total_reclaimed, is_dry_run)
            
    except Exception as e:
        log_message('ERROR', f"Cleanup failed: {str(e)}")
        
        if job_id:
            with get_db() as conn:
                cur = conn.cursor()
                end_time = utils.now()
                cur.execute("""
                    UPDATE jobs 
                    SET status = 'failed', end_time = %s, 
                        error_message = %s, log = %s
                    WHERE id = %s;
                """, (end_time, str(e), ''.join(log_lines), job_id))
                conn.commit()
        
        raise


def cleanup_orphaned_archives(is_dry_run=False, log_callback=None):
    """Remove archive directories that no longer have a database entry."""
    def log(message):
        if log_callback:
            log_callback('INFO', message)
        else:
            print(f"[Cleanup] {message}")
    
    log("Checking for orphaned archive directories...")
    
    archive_base = Path(ARCHIVE_BASE)
    if not archive_base.exists():
        log("Archive directory does not exist, skipping")
        return {'count': 0, 'reclaimed': 0}
    
    # Get all archive names from database
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT name FROM archives;")
        db_archives = {row['name'] for row in cur.fetchall()}
    
    # Check filesystem directories
    orphaned_count = 0
    reclaimed_bytes = 0
    
    for archive_dir in archive_base.iterdir():
        if not archive_dir.is_dir():
            continue
        
        # Skip special directories
        if archive_dir.name.startswith('_'):
            continue
        
        # Check if archive exists in database
        if archive_dir.name not in db_archives:
            size = get_directory_size(archive_dir)
            reclaimed_bytes += size
            orphaned_count += 1
            
            if is_dry_run:
                log(f"Would delete orphaned archive directory: {archive_dir.name} ({format_bytes(size)})")
            else:
                log(f"Deleting orphaned archive directory: {archive_dir.name} ({format_bytes(size)})")
                # Mark all archives in this directory as deleted
                _mark_archives_as_deleted_by_path(str(archive_dir), 'cleanup')
                try:
                    shutil.rmtree(archive_dir)
                except Exception as e:
                    # Log and continue with other directories; don't let one failure abort the entire cleanup
                    log(f"Failed to delete {archive_dir}: {e}")
        else:
            # Archive directory exists in DB — inspect files inside and log unreferenced files
            try:
                for entry in archive_dir.iterdir():
                    try:
                        if entry.is_file():
                            # Check DB references for this file
                            with get_db() as conn:
                                cur = conn.cursor()
                                # Check for exact match or a LIKE pattern containing the filename
                                cur.execute("SELECT 1 FROM job_stack_metrics WHERE archive_path = %s OR archive_path LIKE %s LIMIT 1;", (str(entry), f"%/{entry.name}"))
                                r = cur.fetchone()
                                if r:
                                    # referenced — log minimal info
                                    log(f"Keeping referenced file: {archive_dir.name}/{entry.name}")
                                else:
                                    # unreferenced file — candidate for cleanup
                                    log(f"Unreferenced file in archive dir: {archive_dir.name}/{entry.name} (candidate for manual cleanup)")
                        # If entry is directory, we skip here — deeper checks are in cleanup_temp_files
                    except Exception as inner_e:
                        log(f"Error inspecting {entry}: {inner_e}")
            except Exception as e:
                log(f"Failed to inspect files in {archive_dir}: {e}")
    
    if orphaned_count > 0:
        log(f"Found {orphaned_count} orphaned archive(s), {format_bytes(reclaimed_bytes)} to reclaim")
    else:
        log("No orphaned archives found")
    
    return {'count': orphaned_count, 'reclaimed': reclaimed_bytes}


def cleanup_old_logs(retention_days, is_dry_run=False, log_callback=None):
    """Delete old job records from database."""
    def log(message):
        if log_callback:
            log_callback('INFO', message)
        else:
            print(f"[Cleanup] {message}")
    
    if retention_days <= 0:
        log("Log retention disabled (retention_days <= 0)")
        return {'count': 0}
    
    log(f"Checking for logs older than {retention_days} days...")
    
    with get_db() as conn:
        cur = conn.cursor()
        
        # Count jobs to delete
        cur.execute("""
            SELECT COUNT(*) as count 
            FROM jobs 
            WHERE start_time < NOW() - INTERVAL '%s days';
        """, (retention_days,))
        count = cur.fetchone()['count']
        
        if count == 0:
            log("No old logs to delete")
            return {'count': 0}
        
        if is_dry_run:
            log(f"Would delete {count} old job record(s)")
        else:
            cur.execute("""
                DELETE FROM jobs 
                WHERE start_time < NOW() - INTERVAL '%s days';
            """, (retention_days,))
            conn.commit()
            log(f"Deleted {count} old job record(s)")
    
    return {'count': count}


def cleanup_temp_files(is_dry_run=False, log_callback=None):
    """Remove temporary files from failed jobs."""
    def log(message):
        if log_callback:
            log_callback('INFO', message)
        else:
            print(f"[Cleanup] {message}")
    
    log("Checking for temporary files...")
    
    archive_base = Path(ARCHIVE_BASE)
    if not archive_base.exists():
        return {'count': 0, 'reclaimed': 0}
    
    temp_count = 0
    reclaimed_bytes = 0
    
    # Find all .tmp files recursively
    for temp_file in archive_base.rglob('*.tmp'):
        size = temp_file.stat().st_size if temp_file.exists() else 0
        temp_count += 1
        reclaimed_bytes += size
        
        if is_dry_run:
            log(f"Would delete temp file: {temp_file.relative_to(archive_base)} ({format_bytes(size)})")
        else:
            log(f"Deleting temp file: {temp_file.relative_to(archive_base)} ({format_bytes(size)})")
            try:
                temp_file.unlink()
            except Exception as e:
                log(f"Failed to delete temp file {temp_file.relative_to(archive_base)}: {e}")
    
    # Find empty stack directories
    for archive_dir in archive_base.iterdir():
        if not archive_dir.is_dir() or archive_dir.name.startswith('_'):
            continue

        for stack_dir in archive_dir.iterdir():
            if not stack_dir.is_dir():
                continue

            # Check if stack directory is empty or has no valid backups
            if is_stack_directory_empty(stack_dir, log_callback=log):
                # Before removing, ensure there are no active DB references to archives under this path
                try:
                    with get_db() as conn:
                        cur = conn.cursor()
                        prefix = str(stack_dir) + '/%'
                        cur.execute("SELECT 1 FROM job_stack_metrics WHERE archive_path LIKE %s AND deleted_at IS NULL LIMIT 1;", (prefix,))
                        active = cur.fetchone()
                except Exception as e:
                    # If DB check fails, be conservative and skip deletion; log the error
                    log(f"DB check failed for {stack_dir.relative_to(archive_base)}: {e}. Skipping deletion.")
                    active = True

                if active:
                    # Skip deletion if an active DB reference exists
                    if is_dry_run:
                        log(f"Would keep stack directory (active DB references exist): {stack_dir.relative_to(archive_base)}")
                    else:
                        log(f"Skipping deletion (active DB references exist): {stack_dir.relative_to(archive_base)}")
                    continue

                temp_count += 1

                # Attempt to fetch a recent job reference for context (even if deleted) so logs show source
                reference_info = ''
                archive_label = None
                try:
                    with get_db() as conn:
                        cur = conn.cursor()
                        like = str(stack_dir) + '/%'
                        cur.execute("""
                            SELECT j.id as job_id, a.name as archive_name, m.stack_name
                            FROM job_stack_metrics m
                            LEFT JOIN jobs j ON m.job_id = j.id
                            LEFT JOIN archives a ON j.archive_id = a.id
                            WHERE m.archive_path LIKE %s
                            ORDER BY j.start_time DESC NULLS LAST LIMIT 1;
                        """, (like,))
                        ref = cur.fetchone()
                        if ref:
                            reference_info = f" (archive '{ref.get('archive_name') or 'unknown'}', stack '{ref.get('stack_name') or 'unknown'}')"
                            archive_label = ref.get('archive_name')
                except Exception as e:
                    # Non-fatal; include note in logs
                    reference_info = f" (DB lookup failed: {e})"

                # Determine display path to include archive name when available
                rel = str(stack_dir.relative_to(archive_base))
                if archive_label:
                    # Avoid duplicating the archive name if it's already present at the start
                    if rel.startswith(f"{archive_label}/") or rel == archive_label:
                        display_path = rel
                    else:
                        display_path = f"{archive_label}/{rel}"
                else:
                    # Fallback: infer archive name from path (parent directory)
                    try:
                        inferred = stack_dir.parent.name
                        if rel.startswith(f"{inferred}/") or rel == inferred:
                            display_path = rel
                        else:
                            display_path = f"{inferred}/{rel}"
                    except Exception:
                        display_path = rel

                if is_dry_run:
                    log(f"Would delete empty stack directory: {display_path}{reference_info}")
                else:
                    log(f"Deleting empty stack directory: {display_path}{reference_info}")
                    try:
                        shutil.rmtree(stack_dir)
                    except Exception as e:
                        log(f"Failed to delete empty stack directory {display_path}: {e}")
    
    if temp_count > 0:
        log(f"Found {temp_count} temp file(s)/directory(ies), {format_bytes(reclaimed_bytes)} to reclaim")
    else:
        log("No temporary files found")
    
    return {'count': temp_count, 'reclaimed': reclaimed_bytes}


def is_stack_directory_empty(stack_dir, log_callback=None):
    """Check if a stack directory has no valid backups.

    Heuristics used:
      - If any archive file (.tar, .tar.gz, .tar.zst) exists anywhere under the
        directory, it's considered non-empty.
      - If any subdirectory name starts with a timestamp pattern (YYYYMMDD_HHMMSS),
        optionally followed by suffix (e.g. "20251221_182125_beszel"), it's
        considered non-empty.
      - If there's a nested directory with the same stack name that contains files,
        it's considered non-empty (covers layouts like stack/stack/...).
    """
    import re

    # Completely empty
    try:
        if not any(stack_dir.iterdir()):
            return True
    except Exception:
        # If something goes wrong reading dir, treat it as non-empty to be safe
        return False

    # 1) If any file exists anywhere under this stack_dir, it's not empty
    for f in stack_dir.rglob('*'):
        try:
            if f.is_file():
                # Any regular file (compose.yaml, data files, archives, etc.) indicates the
                # directory holds content and should not be considered empty.
                return False
        except Exception:
            continue

    # If no regular files exist, we still consider timestamped subdirectories or nested
    # stack directories as indicators of non-empty backup folders.

    # 2) Check for timestamp-like subdirectories (timestamp at start of name)
    timestamp_re = re.compile(r'^\d{8}_\d{6}')
    for d in stack_dir.iterdir():
        if d.is_dir() and timestamp_re.match(d.name):
            return False

    # 3) Nested stack directory (e.g., stack/stack) that contains files
    for d in stack_dir.iterdir():
        if d.is_dir() and d.name == stack_dir.name:
            # if nested dir contains at least one file, consider non-empty
            try:
                if any(p.is_file() for p in d.rglob('*')):
                    return False
            except Exception:
                # Be conservative
                return False

    # If none of the above heuristics matched, consider it empty
    return True


def is_valid_timestamp_dirname(dirname):
    """Check if directory name matches timestamp pattern YYYYMMDD_HHMMSS.

    The project uses the compact format (YYYYMMDD_HHMMSS) for timestamped
    folders; only this canonical format is accepted here.
    """
    try:
        from re import match
        return bool(match(r"^\d{8}_\d{6}$", dirname))
    except Exception:
        return False


def get_directory_size(path):
    """Calculate total size of directory."""
    total = 0
    try:
        for entry in Path(path).rglob('*'):
            if entry.is_file():
                total += entry.stat().st_size
    except Exception as e:
        print(f"[Cleanup] Error calculating size for {path}: {e}")
    return total


def format_bytes(size):
    """Format bytes as human-readable string."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} PB"


def _mark_archives_as_deleted_by_path(path_prefix, deleted_by='cleanup'):
    """Mark all archives under a path as deleted in database."""
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE job_stack_metrics 
                SET deleted_at = NOW(), deleted_by = %s
                WHERE archive_path LIKE %s AND deleted_at IS NULL;
            """, (deleted_by, f"{path_prefix}%"))
            conn.commit()
    except Exception as e:
        print(f"[Cleanup] Failed to mark archives as deleted in DB: {e}")


def generate_cleanup_report(archive_base_path=None):
    """Generate a non-destructive report of what cleanup would delete.

    Returns a dict with keys: orphaned_dirs, old_logs_count, temp_items (list of dicts)
    Each temp item includes display_path, path, has_active_db_ref (bool), reference_info
    """
    report = {
        'orphaned': [],
        'old_logs_count': 0,
        'temp_items': []
    }

    archive_base = Path(archive_base_path) if archive_base_path else Path(ARCHIVE_BASE)
    if not archive_base.exists():
        return report

    # orphaned archive directories
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT name FROM archives;")
        db_archives = {row['name'] for row in cur.fetchall()}

    for archive_dir in archive_base.iterdir():
        if not archive_dir.is_dir():
            continue
        if archive_dir.name.startswith('_'):
            continue
        if archive_dir.name not in db_archives:
            size = get_directory_size(archive_dir)
            report['orphaned'].append({'name': archive_dir.name, 'size': size})

    # old logs count
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) as count FROM jobs WHERE start_time < NOW() - INTERVAL '%s days';", (int(get_setting('cleanup_log_retention_days', '90')),))
        row = cur.fetchone()
        if row:
            report['old_logs_count'] = int(row['count'])

    # temp files and empty stack dirs (using is_stack_directory_empty and DB checks)
    for archive_dir in archive_base.iterdir():
        if not archive_dir.is_dir() or archive_dir.name.startswith('_'):
            continue
        for stack_dir in archive_dir.iterdir():
            if not stack_dir.is_dir():
                continue
            # check if considered empty by current heuristics
            empty = is_stack_directory_empty(stack_dir, log_callback=None)
            if not empty:
                continue

            # DB active ref check
            active = False
            reference_info = ''
            archive_label = None
            try:
                with get_db() as conn:
                    cur = conn.cursor()
                    like = str(stack_dir) + '/%'
                    cur.execute("""
                        SELECT a.name as archive_name, m.stack_name
                        FROM job_stack_metrics m
                        LEFT JOIN jobs j ON m.job_id = j.id
                        LEFT JOIN archives a ON j.archive_id = a.id
                        WHERE m.archive_path LIKE %s
                        ORDER BY j.start_time DESC NULLS LAST LIMIT 1;
                    """, (like,))
                    ref = cur.fetchone()
                    if ref:
                        active = True if ref.get('stack_name') else False
                        reference_info = f"archive='{ref.get('archive_name') or 'unknown'}', stack='{ref.get('stack_name') or 'unknown'}'"
                        archive_label = ref.get('archive_name')
            except Exception as e:
                reference_info = f"DB lookup failed: {e}"
                active = True  # be conservative

            # determine display path similar to deletion logic
            rel = str(stack_dir.relative_to(archive_base))
            if archive_label:
                if rel.startswith(f"{archive_label}/") or rel == archive_label:
                    display_path = rel
                else:
                    display_path = f"{archive_label}/{rel}"
            else:
                try:
                    inferred = stack_dir.parent.name
                    if rel.startswith(f"{inferred}/") or rel == inferred:
                        display_path = rel
                    else:
                        display_path = f"{inferred}/{rel}"
                except Exception:
                    display_path = rel

            report['temp_items'].append({
                'display_path': display_path,
                'path': str(stack_dir),
                'has_active_db_ref': bool(active),
                'reference_info': reference_info
            })

    return report


def send_cleanup_notification(orphaned_stats, log_stats, temp_stats, total_reclaimed, is_dry_run):
    """Send notification about cleanup results."""
    try:
        import apprise
        from app.notifications import get_setting, get_subject_with_tag
        
        apprise_urls = get_setting('apprise_urls', '')
        if not apprise_urls:
            return
        
        apobj = apprise.Apprise()
        for url in apprise_urls.strip().split('\n'):
            url = url.strip()
            if url:
                apobj.add(url)
        
        if not apobj:
            return
        
        mode = "🧪 DRY RUN" if is_dry_run else "✅"
        
        # Build message
        title = get_subject_with_tag(f"{mode} Cleanup Task Completed")
        
        base_url = get_setting('base_url', 'http://localhost:8080')
        
        body = f"""
<h2>{mode} Cleanup Task</h2>

<h3>Summary</h3>
<ul>
    <li><strong>Orphaned Archives:</strong> {orphaned_stats.get('count', 0)} removed ({format_bytes(orphaned_stats.get('reclaimed', 0))})</li>
    <li><strong>Old Logs:</strong> {log_stats.get('count', 0)} deleted</li>
    <li><strong>Temp Files:</strong> {temp_stats.get('count', 0)} removed ({format_bytes(temp_stats.get('reclaimed', 0))})</li>
    <li><strong>Total Reclaimed:</strong> {format_bytes(total_reclaimed)}</li>
</ul>
"""
        
        if is_dry_run:
            body += "\n<p><em>⚠️ This was a dry run - no files were actually deleted.</em></p>"
        
        body += f"""
<hr>
<p><small>Docker Archiver: <a href="{base_url}">{base_url}</a></small></p>"""
        
        # Get format preference from notifications module
        from app.notifications import get_notification_format, strip_html_tags
        body_format = get_notification_format()
        
        # Convert to plain text if needed
        if body_format == apprise.NotifyFormat.TEXT:
            body = strip_html_tags(body)
        
        apobj.notify(
            body=body,
            title=title,
            body_format=body_format
        )
        
    except Exception as e:
        print(f"[Cleanup] Failed to send notification: {e}")


if __name__ == '__main__':
    import argparse, json
    parser = argparse.ArgumentParser(description='Cleanup utilities: generate a dry-run cleanup report')
    parser.add_argument('--archive-base', help='Path to archive base (overrides default)')
    parser.add_argument('--json', action='store_true', help='Output JSON')
    parser.add_argument('--run-cleanup', action='store_true', help='Run cleanup now (live mode)')
    parser.add_argument('--dry-run', action='store_true', help='Run cleanup in dry-run mode')
    args = parser.parse_args()

    if args.run_cleanup:
        # Run cleanup (honor --dry-run if provided)
        run_cleanup(dry_run_override=(True if args.dry_run else False))
    else:
        rep = generate_cleanup_report(args.archive_base)
        if args.json:
            print(json.dumps(rep, indent=2))
        else:
            print('Orphaned archive directories:')
            if not rep['orphaned']:
                print('  None')
            else:
                for o in rep['orphaned']:
                    print(f"  - {o['name']} ({o['size']} bytes)")

            print(f"\nOld job logs older than retention: {rep['old_logs_count']}")

            print('\nEmpty/Temp stack directories (would be deleted if no DB refs):')
            if not rep['temp_items']:
                print('  None')
            else:
                for t in rep['temp_items']:
                    flag = 'KEEP (has DB refs)' if t['has_active_db_ref'] else 'DELETE'
                    print(f"  - {t['display_path']} -> {t['path']} [{flag}] {t['reference_info']}")
