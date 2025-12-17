#!/usr/bin/env bash
set -euo pipefail
# tools/run_smoke_test.sh
# Debian 13-compatible smoke test for Docker-Archiver running via docker-compose
# Usage (examples):
# 1) Host-exposed web port:
#    WEB_HOST_PORT=8080 STACK_PATH=/path/on/host/to/stack ./tools/run_smoke_test.sh
# 2) Using container curl (no host port):
#    WEB_SERVICE=web PG_CONTAINER=postgres STACK_PATH=/srv/stacks/my_stack ./tools/run_smoke_test.sh

# Defaults (override via env)
WEB_SERVICE=${WEB_SERVICE:-web}
PG_CONTAINER=${PG_CONTAINER:-postgres}
COMPOSE_CMD=${COMPOSE_CMD:-docker-compose}
WEB_HOST_PORT=${WEB_HOST_PORT:-}
APP_INTERNAL_PORT=${APP_INTERNAL_PORT:-5000}
STACK_PATH=${STACK_PATH:-}
STACK_NAME=${STACK_NAME:-}
ARCHIVE_DIR=${ARCHIVE_DIR:-/archives}
TAIL_SECONDS=${TAIL_SECONDS:-12}
AUDIT_SQL=tools/audit_jobs.sql

if [ -z "$STACK_PATH" ]; then
  echo "ERROR: STACK_PATH must be set (path to stack directory as seen by the web container)." >&2
  echo "Example: STACK_PATH=/srv/stacks/my_stack ./tools/run_smoke_test.sh" >&2
  exit 2
fi

if [ -z "$STACK_NAME" ]; then
  STACK_NAME=$(basename "$STACK_PATH")
fi

echo "Smoke test starting: WEB_SERVICE=$WEB_SERVICE PG_CONTAINER=$PG_CONTAINER STACK_PATH=$STACK_PATH STACK_NAME=$STACK_NAME"

# 1) show containers
echo "\n== Containers =="
$COMPOSE_CMD ps || docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Ports}}'

# 2) trigger archive
echo "\n== Triggering manual archive for stack: $STACK_NAME =="
if [ -n "$WEB_HOST_PORT" ]; then
  echo "Using host port $WEB_HOST_PORT"
  curl -v -X POST "http://localhost:$WEB_HOST_PORT/archive" \
    -F "stacks=$STACK_PATH" \
    -F "manual_description=smoke test" \
    -F "store_unpacked=on" || echo "host curl failed"
else
  echo "No host port provided; attempting in-container curl via $COMPOSE_CMD exec $WEB_SERVICE"
  # Try to run curl inside the web container. If curl not available, try python fallback.
  set +e
  $COMPOSE_CMD exec -T $WEB_SERVICE sh -c "curl -s -X POST http://localhost:$APP_INTERNAL_PORT/archive -F 'stacks=$STACK_PATH' -F 'manual_description=smoke test' -F 'store_unpacked=on'"
  rc=$?
  if [ $rc -ne 0 ]; then
    echo "In-container curl failed (rc=$rc), trying Python fallback inside container..."
    $COMPOSE_CMD exec -T $WEB_SERVICE sh -c "python3 - <<'PY'
import sys,urllib.parse,urllib.request
data = {'stacks': '$STACK_PATH', 'manual_description':'smoke test', 'store_unpacked':'on'}
body = urllib.parse.urlencode(data).encode()
req = urllib.request.Request('http://localhost:%s/archive' % $APP_INTERNAL_PORT, data=body)
try:
    res = urllib.request.urlopen(req, timeout=10)
    print('Request status', res.status)
except Exception as e:
    print('Python POST failed', e)
    sys.exit(1)
PY"
  fi
  set -e
fi

# 3) tail logs for a short period to capture immediate activity
echo "\n== Tailing $WEB_SERVICE logs for $TAIL_SECONDS seconds =="
$COMPOSE_CMD logs -f --tail=200 $WEB_SERVICE &
LOG_PID=$!
sleep $TAIL_SECONDS
kill $LOG_PID 2>/dev/null || true

# 4) inspect archive files for the stack inside container
echo "\n== Archive files for stack $STACK_NAME (last 20) =="
$COMPOSE_CMD exec -T $WEB_SERVICE sh -c "ls -alh \"$ARCHIVE_DIR/$STACK_NAME\" 2>/dev/null || echo 'No archive dir found or not accessible'" || true

echo "\n== Archive dir size summary =="
$COMPOSE_CMD exec -T $WEB_SERVICE sh -c "du -sh \"$ARCHIVE_DIR\" 2>/dev/null || echo 'du unavailable'" || true

# 5) run audit SQL against Postgres container
if [ ! -f "$AUDIT_SQL" ]; then
  echo "Audit SQL not found at $AUDIT_SQL. Skipping DB audit." >&2
else
  echo "\n== Running DB audit using $PG_CONTAINER =="
  docker cp "$AUDIT_SQL" "$PG_CONTAINER":/tmp/audit_jobs.sql || true
  # try to detect user and db inside container
  echo "Container env (attempting to read POSTGRES_USER and POSTGRES_DB)"
  docker exec $PG_CONTAINER printenv POSTGRES_USER POSTGRES_DB || true
  echo "Executing psql inside $PG_CONTAINER"
  docker exec -i $PG_CONTAINER bash -lc "psql -U \"\${POSTGRES_USER:-postgres}\" -d \"\${POSTGRES_DB:-postgres}\" -f /tmp/audit_jobs.sql" || echo "psql audit failed"
fi

# 6) quick tips
echo "\nSmoke test finished. Review logs and audit output above. If errors occurred, re-run with WEB_HOST_PORT set or check that the web container has curl/python."