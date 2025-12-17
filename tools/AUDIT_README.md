Audit scripts for verifying legacy -> unified job mirroring and retention behavior.

Files:
- tools/audit_jobs.sql  : SQL queries that surface missing mirrors, missing fields, duration issues, and common log markers.
- tools/run_audit.ps1   : PowerShell wrapper to run the SQL script. Set environment variable `PG_CONN` to a libpq connection string first.

How to run (PowerShell):

1. Set connection string (example):

```powershell
$env:PG_CONN = 'postgresql://dbuser:secret@dbhost:5432/docker_archiver_db'
```

2. Run the audit script:

```powershell
cd c:\path\to\Docker-Archiver
.\tools\run_audit.ps1
```

If `psql` is not on PATH, install the PostgreSQL client tools or update the script to point to the full `psql` path.

Interpreting results:
- Look for rows in sections 1–3 where the `jobs_id` is NULL — those are legacy rows not mirrored into `jobs`.
- Section 4 highlights `jobs` entries missing archive path or size information.
- Section 5 finds entries with end_time but no duration_seconds.
- Section 6 surfaces `jobs` referencing missing legacy rows (orphaned mirrors).
- Section 7/8 help locate notification and disk‑usage log mentions.

Next actions (recommended):
- Run the script after triggering a manual archive+retention run to capture fresh data.
- If gaps are found, I can generate targeted patches to add missing mirror writes or fix duration/field assignments.
