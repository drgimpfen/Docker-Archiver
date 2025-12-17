-- Audit script: tools/audit_jobs.sql
-- Run with psql -d "postgresql://user:pass@host:port/db" -f tools/audit_jobs.sql
\echo '--- 1) Recent archive masters without jobs mirror ---'
SELECT a.id AS archive_id, a.start_time, a.status, j.id AS jobs_id
FROM archive_jobs a
LEFT JOIN jobs j ON j.legacy_archive_id = a.id
WHERE a.start_time > now() - interval '7 days'
ORDER BY a.start_time DESC;

\echo '--- 2) Recent per-stack archive rows without jobs mirror ---'
SELECT a.id AS archive_row_id, a.archive_id AS master_id, a.stack_name, j.id AS jobs_id
FROM archive_jobs a
LEFT JOIN jobs j ON j.legacy_archive_id = a.id
WHERE a.archive_id IS NOT NULL
  AND a.start_time > now() - interval '7 days'
ORDER BY a.id DESC;

\echo '--- 3) Recent retention rows without jobs mirror ---'
SELECT r.id AS retention_id, r.start_time, r.status, j.id AS jobs_id
FROM retention_jobs r
LEFT JOIN jobs j ON j.legacy_retention_id = r.id
WHERE r.start_time > now() - interval '7 days'
ORDER BY r.start_time DESC;

\echo '--- 4) jobs missing archive_path or archive_size_bytes for archive entries ---'
SELECT id, job_type, legacy_archive_id, stack_name, archive_path, archive_size_bytes, start_time, end_time, status
FROM jobs
WHERE job_type IN ('archive_stack','archive_master')
  AND (archive_path IS NULL OR archive_size_bytes IS NULL)
ORDER BY start_time DESC
LIMIT 50;

\echo '--- 5) jobs with end_time but no duration_seconds ---'
SELECT id, job_type, start_time, end_time, duration_seconds
FROM jobs
WHERE end_time IS NOT NULL AND (duration_seconds IS NULL OR duration_seconds = 0)
ORDER BY end_time DESC
LIMIT 50;

\echo '--- 6) jobs referencing missing legacy rows ---'
SELECT j.id AS jobs_id, j.legacy_archive_id, (a.id IS NULL) AS archive_missing, j.legacy_retention_id, (r.id IS NULL) AS retention_missing
FROM jobs j
LEFT JOIN archive_jobs a ON a.id = j.legacy_archive_id
LEFT JOIN retention_jobs r ON r.id = j.legacy_retention_id
WHERE (j.legacy_archive_id IS NOT NULL AND a.id IS NULL)
   OR (j.legacy_retention_id IS NOT NULL AND r.id IS NULL)
ORDER BY j.id DESC
LIMIT 200;

\echo '--- 7) jobs showing notification log markers ---'
SELECT id, job_type, start_time, end_time, status, log
FROM jobs
WHERE COALESCE(log, '') ILIKE '%Notification sent:%'
   OR COALESCE(log, '') ILIKE '%Notification error:%'
ORDER BY start_time DESC
LIMIT 50;

\echo '--- 8) recent archive master logs containing disk usage ---'
SELECT id, start_time, log
FROM archive_jobs
WHERE COALESCE(log, '') ILIKE '%Disk usage%'
ORDER BY start_time DESC
LIMIT 20;

\echo '--- 9) quick summary counts ---'
SELECT
  (SELECT COUNT(*) FROM archive_jobs WHERE start_time > now() - interval '7 days') AS recent_archive_jobs,
  (SELECT COUNT(*) FROM retention_jobs WHERE start_time > now() - interval '7 days') AS recent_retention_jobs,
  (SELECT COUNT(*) FROM jobs WHERE start_time > now() - interval '7 days') AS recent_unified_jobs;

\echo '--- End of audit ---'
