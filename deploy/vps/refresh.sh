#!/usr/bin/env bash
# One bounded refresh of the live demo snapshot (UC-6, FR-6, FR-7).
#
# This is the container smoke shape (scripts/container_smoke.sh) turned into the
# demo's data clock: bring single-node Kafka up, publish a bounded backfill,
# drain it with the committed consumer into a staging DuckDB, publish that
# snapshot atomically over the served file, then bring every streaming component
# down again. Between refreshes only the dashboard is resident.
#
# Properties this script is responsible for:
#   * bounded: the staging directory is wiped first, so each refresh rebuilds one
#     self-contained snapshot and the disk footprint stays flat, aggregate store
#     and raw audit trail alike;
#   * atomic: only deploy/vps/publish_snapshot.py touches the served path, and
#     only by renaming a verified staging file over it;
#   * safe to fail: any failure before the publish step leaves the last good
#     snapshot serving, and the EXIT trap tears the broker down either way;
#   * never overlapping: a lock means a slow refresh cannot collide with the next
#     timer firing.
#
# Local backend only: no cloud credential is read and no cloud call is made.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${REPO_ROOT}"

ENV_FILE="${CII_DEMO_ENV_FILE:-${REPO_ROOT}/deploy/vps/demo.env}"
if [ ! -f "${ENV_FILE}" ]; then
	echo "missing demo environment: ${ENV_FILE} (run deploy/vps/install.sh)" >&2
	exit 2
fi
set -a
# shellcheck disable=SC1090
. "${ENV_FILE}"
set +a

DATA_DIR="${CII_DEMO_DATA_DIR:?CII_DEMO_DATA_DIR is not set}"
PROJECT="${CII_DEMO_COMPOSE_PROJECT:-cii-demo}"
STAGING_DIR="${DATA_DIR}/staging"
SERVED="${DATA_DIR}/aggregates.duckdb"
DRAIN_ATTEMPTS="${CII_DEMO_DRAIN_ATTEMPTS:-10}"
PYTHON="${CII_DEMO_PYTHON:-${REPO_ROOT}/.venv/bin/python}"

COMPOSE=(docker compose -p "${PROJECT}" -f docker-compose.yml -f deploy/vps/compose.refresh.yml)

export CII_DEMO_STAGING_DIR="${STAGING_DIR}"
export PYTHONPATH="${REPO_ROOT}/src"

mkdir -p "${DATA_DIR}"

# Serialize refreshes: the lock is held for the life of this script, so a slow run
# makes the next timer firing skip rather than pile up.
exec 9>"${DATA_DIR}/refresh.lock"
if ! flock -n 9; then
	echo "a refresh is already running; skipping this firing"
	exit 0
fi

teardown() {
	"${COMPOSE[@]}" down -v --remove-orphans >/dev/null 2>&1 || true
}
trap teardown EXIT

# A fresh staging area every time: this is what makes the snapshot self-contained
# and keeps the footprint flat (the raw audit store is rebuilt and discarded too).
rm -rf "${STAGING_DIR}"
mkdir -p "${STAGING_DIR}"

echo "== start single-node Kafka (KRaft) and wait for healthy =="
"${COMPOSE[@]}" up -d --wait kafka

echo "== publish the bounded backfill =="
"${COMPOSE[@]}" run --rm --entrypoint python producer /app/deploy/vps/feed_history.py

echo "== drain into the staging snapshot and publish when it verifies =="
published=0
for attempt in $(seq 1 "${DRAIN_ATTEMPTS}"); do
	"${COMPOSE[@]}" run --rm -e CII_CONSUMER_ONESHOT=1 consumer
	# The publish step is also the completeness check: it verifies the staging
	# snapshot through the dashboard read path and renames it over the served file
	# only if every configured region is present with unique natural keys.
	if "${PYTHON}" deploy/vps/publish_snapshot.py \
		--staging "${STAGING_DIR}/aggregates.duckdb" --served "${SERVED}"; then
		published=1
		break
	fi
	echo "   drain attempt ${attempt}: snapshot not complete yet, retrying"
done

if [ "${published}" -ne 1 ]; then
	echo "refresh FAILED: no complete snapshot after ${DRAIN_ATTEMPTS} drains (serving the previous one)" >&2
	exit 1
fi

echo "refresh OK: snapshot published atomically; bringing the streaming components down"
