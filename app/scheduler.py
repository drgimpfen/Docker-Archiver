import os
from datetime import datetime
import threading
from apscheduler.schedulers.background import BackgroundScheduler
from zoneinfo import ZoneInfo

from db import get_db_connection
from psycopg2.extras import DictCursor
import archive
import retention


def _job_runner(schedule_id):
    try:
        conn = get_db_connection()
        with conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute("SELECT * FROM schedules WHERE id = %s;", (schedule_id,))
            s = cur.fetchone()
        conn.close()

        if not s or not s.get('enabled'):
            return

        schedule_type = (s.get('type') or 'archive').lower()
        stack_paths = [p for p in (s.get('stack_paths') or '').split('\n') if p.strip()]
        # Per-schedule retention removed; use global retention from settings instead
        retention_val = None

        # update last_run
        now = datetime.now()
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("UPDATE schedules SET last_run = %s WHERE id = %s;", (now, schedule_id))
            conn.commit()
        conn.close()

        archive_description = s.get('description') if s.get('description') else None
        if schedule_type == 'cleanup':
            threading.Thread(target=retention.run_retention_now, args=(os.environ.get('CONTAINER_ARCHIVE_DIR', '/archives'), archive_description, 'scheduled'), daemon=True).start()
        else:
            store_unpacked_flag = bool(s.get('store_unpacked'))
            threading.Thread(target=archive.run_archive_job, args=(stack_paths, retention_val, os.environ.get('CONTAINER_ARCHIVE_DIR', '/archives'), archive_description, store_unpacked_flag, 'scheduled'), daemon=True).start()
    except Exception as e:
        print(f"[scheduler] job_runner error for schedule {schedule_id}: {e}")


def schedule_db_job(scheduler, s):
    try:
        time_val = (s.get('time') or '00:00').strip()
        hh, mm = (int(x) for x in time_val.split(':'))
    except Exception:
        return

    job_id = f"schedule_{s['id']}"
    try:
        scheduler.add_job(
            func=_job_runner,
            trigger='cron',
            hour=hh,
            minute=mm,
            args=(s['id'],),
            id=job_id,
            replace_existing=True,
        )
    except Exception as e:
        print(f"[scheduler] failed to add job {job_id}: {e}")


def _load_and_schedule_all(scheduler):
    try:
        conn = get_db_connection()
        with conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute("SELECT * FROM schedules WHERE enabled = true;")
            rows = cur.fetchall()
        conn.close()
        cleanup_scheduled = False
        for s in rows:
            try:
                if (s.get('type') or 'archive').lower() == 'cleanup':
                    if cleanup_scheduled:
                        continue
                    cleanup_scheduled = True
                schedule_db_job(scheduler, s)
            except Exception:
                continue
    except Exception as e:
        print(f"[scheduler] load failed: {e}")


def start_scheduler():
    tz_name = os.environ.get('TZ', 'UTC')
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        try:
            tz = ZoneInfo('UTC')
        except Exception:
            tz = None

    scheduler = BackgroundScheduler(timezone=tz)
    try:
        scheduler.start()
    except Exception as e:
        print(f"[scheduler] could not start: {e}")
        return None

    _load_and_schedule_all(scheduler)
    return scheduler
