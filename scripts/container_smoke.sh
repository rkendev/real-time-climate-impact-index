#!/usr/bin/env bash
# Container smoke (UC-6, FR-6, FR-7): the Phase 1 smoke, but through the real
# containers and a live Kafka broker instead of the in-memory transport. It builds
# the app image, stands up single-node Kafka in KRaft mode, produces a bounded
# batch to the broker, drains it with the consumer into the local DuckDB store,
# then asserts through the dashboard read path that the aggregate is non-empty and
# duplicate-free. Everything runs on the local backend: no AWS, no spend.
#
# This exercises the live-broker path Phase 1 left skipped (the two deferred Kafka
# tests), offline. On any failure it tears the stack down and exits non-zero.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

COMPOSE="docker compose"
DRAIN_ATTEMPTS=10

cleanup() {
	${COMPOSE} down -v --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT

# The read-back assertion runs through the dashboard's own read factory, so the
# smoke proves the exact path the dashboard serves (non-empty, duplicate-free).
CHECK_PY='
import sys
from climate_index.config import get_settings
from climate_index.store_factory import build_readonly_aggregate_store

settings = get_settings()
store = build_readonly_aggregate_store(settings)
rows = []
for region in settings.region_list:
    rows.extend(store.read_region_series(region))
if not rows:
    print("container smoke: aggregate store is empty", file=sys.stderr)
    sys.exit(1)
keys = [(r["region"], r["window_start"], r["window_end"]) for r in rows]
if len(keys) != len(set(keys)):
    print("container smoke: duplicate natural keys (FR-6)", file=sys.stderr)
    sys.exit(1)
print("CONTAINER_SMOKE_OK rows=%d regions=%d" % (len(rows), len({r["region"] for r in rows})))
'

aggregate_is_populated() {
	${COMPOSE} run --rm --no-deps --entrypoint python consumer -c "${CHECK_PY}"
}

echo "== build the app image =="
${COMPOSE} build

echo "== start single-node Kafka (KRaft) and wait for healthy =="
${COMPOSE} up -d --wait kafka

echo "== produce a bounded batch to the broker =="
${COMPOSE} run --rm producer

echo "== drain the broker into the store (retry until windows land) =="
populated=0
for attempt in $(seq 1 "${DRAIN_ATTEMPTS}"); do
	${COMPOSE} run --rm -e CII_CONSUMER_ONESHOT=1 consumer
	if aggregate_is_populated; then
		populated=1
		break
	fi
	echo "   drain attempt ${attempt}: no windows yet, retrying"
done

if [ "${populated}" -ne 1 ]; then
	echo "container smoke FAILED: no windows after ${DRAIN_ATTEMPTS} drains" >&2
	exit 1
fi

echo "container smoke OK: producer to consumer to store to dashboard, non-empty and duplicate-free"
