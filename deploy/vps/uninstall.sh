#!/usr/bin/env bash
# Take the live demo down cleanly (the reverse of install.sh).
#
# Stops and removes the two units, takes the site block out of the host's Caddy
# configuration without touching any other site, and brings the refresh compose
# project down with its volume. The served snapshot is kept unless --purge is
# passed, so a standup after a teardown serves data immediately.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEPLOY_DIR="${REPO_ROOT}/deploy/vps"
ENV_FILE="${CII_DEMO_ENV_FILE:-${DEPLOY_DIR}/demo.env}"
UNIT_DIR="${CII_DEMO_UNIT_DIR:-/etc/systemd/system}"

DASHBOARD_UNIT=climate-index-dashboard.service
REFRESH_UNIT=climate-index-refresh.service
REFRESH_TIMER=climate-index-refresh.timer

purge=0
if [ "${1:-}" = "--purge" ]; then
	purge=1
fi

if [ -f "${ENV_FILE}" ]; then
	set -a
	# shellcheck disable=SC1090
	. "${ENV_FILE}"
	set +a
fi

# The public door first, so nothing is served from a stopping backend.
if [ -f "${ENV_FILE}" ]; then
	"${DEPLOY_DIR}/install_caddy_site.sh" --remove || true
fi

for unit in "${REFRESH_TIMER}" "${DASHBOARD_UNIT}"; do
	systemctl disable --now "${unit}" >/dev/null 2>&1 || true
done
systemctl stop "${REFRESH_UNIT}" >/dev/null 2>&1 || true
rm -f "${UNIT_DIR}/${DASHBOARD_UNIT}" "${UNIT_DIR}/${REFRESH_UNIT}" "${UNIT_DIR}/${REFRESH_TIMER}"
systemctl daemon-reload

# Nothing of the refresh stack survives: its containers and its volume go too.
docker compose -p "${CII_DEMO_COMPOSE_PROJECT:-cii-demo}" \
	-f "${REPO_ROOT}/docker-compose.yml" down -v --remove-orphans >/dev/null 2>&1 || true

if [ "${purge}" -eq 1 ] && [ -n "${CII_DEMO_DATA_DIR:-}" ]; then
	rm -rf "${CII_DEMO_DATA_DIR}"
	echo "removed ${CII_DEMO_DATA_DIR}"
fi

echo "demo torn down (units removed, site block removed, refresh stack down)"
