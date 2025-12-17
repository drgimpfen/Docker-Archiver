# PowerShell wrapper to run the SQL audit script
# Usage:
#   $env:PG_CONN = 'postgresql://user:pass@host:5432/dbname'
#   .\tools\run_audit.ps1

if (-not $env:PG_CONN) {
    Write-Host "Environment variable PG_CONN not set. Please set it to a libpq connection string, e.g. postgresql://user:pass@host:port/dbname"
    exit 1
}

$script = Join-Path $PSScriptRoot 'audit_jobs.sql'
Write-Host "Running audit script: $script against $env:PG_CONN"

$psql = 'psql'
# psql is expected to be on PATH. If not, user must provide full path.
$env:PGPASSWORD = $null  # do not override; user may prefer embedded password in connection string

$cmd = "$psql -d \"$env:PG_CONN\" -f \"$script\""
Write-Host "Executing: $cmd"
Invoke-Expression $cmd

Write-Host "Audit completed. Review the output above for anomalies."
