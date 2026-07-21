#!/usr/bin/env bash
# Stand the live demo up on this box (idempotent operator step).
#
# What it does, in order: create the git-ignored demo environment from the tracked
# placeholder on first run, derive the public host once and record it there, render
# the unit templates into systemd, run one refresh so the demo has data before it is
# reachable, arm the refresh timer, and add the site block to the existing Caddy.
#
# Nothing here is committed with a real value in it: the templates carry
# placeholders, and every host-specific value lives in the git-ignored demo.env
# (INV-1). Re-running is safe: it re-renders, re-enables, and re-installs the same
# state.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEPLOY_DIR="${REPO_ROOT}/deploy/vps"
ENV_FILE="${CII_DEMO_ENV_FILE:-${DEPLOY_DIR}/demo.env}"
UNIT_DIR="${CII_DEMO_UNIT_DIR:-/etc/systemd/system}"

DASHBOARD_UNIT=climate-index-dashboard.service
REFRESH_UNIT=climate-index-refresh.service
REFRESH_TIMER=climate-index-refresh.timer

if [ ! -x "${REPO_ROOT}/.venv/bin/streamlit" ]; then
	echo "the repository venv is missing streamlit; run 'make bootstrap' first" >&2
	exit 2
fi

# 1. The git-ignored environment, seeded from the tracked placeholder.
if [ ! -f "${ENV_FILE}" ]; then
	cp "${DEPLOY_DIR}/demo.env.example" "${ENV_FILE}"
	chmod 600 "${ENV_FILE}"
	echo "created ${ENV_FILE} from the tracked placeholder"
fi
set -a
# shellcheck disable=SC1090
. "${ENV_FILE}"
set +a

: "${CII_DEMO_DATA_DIR:?CII_DEMO_DATA_DIR is not set in ${ENV_FILE}}"
: "${CII_DEMO_REFRESH_INTERVAL:?CII_DEMO_REFRESH_INTERVAL is not set in ${ENV_FILE}}"

# 2. Derive the public IPv4 once and build the sslip.io host from it. The lookup
#    service is a config value, not a literal in this file; with none set the
#    address is read from the box's own default route instead.
if [ -z "${CII_DEMO_HOST:-}" ]; then
	ipv4=""
	if [ -n "${CII_DEMO_IP_LOOKUP_URL:-}" ]; then
		ipv4="$(curl -4 -fsS --max-time 10 "${CII_DEMO_IP_LOOKUP_URL}" | tr -d '[:space:]')"
	fi
	if [ -z "${ipv4}" ]; then
		ipv4="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{ for (i = 1; i < NF; i++) if ($i == "src") print $(i + 1) }')"
	fi
	if [ -z "${ipv4}" ]; then
		echo "could not derive the public IPv4; set CII_DEMO_HOST in ${ENV_FILE}" >&2
		exit 2
	fi
	host="climate-index.${ipv4//./-}.sslip.io"
	if grep -q '^CII_DEMO_HOST=' "${ENV_FILE}"; then
		sed -i "s|^CII_DEMO_HOST=.*|CII_DEMO_HOST=${host}|" "${ENV_FILE}"
	else
		printf 'CII_DEMO_HOST=%s\n' "${host}" >>"${ENV_FILE}"
	fi
	export CII_DEMO_HOST="${host}"
	echo "derived the demo host and recorded it in ${ENV_FILE}"
fi

mkdir -p "${CII_DEMO_DATA_DIR}"

# 3. The app image the refresh runs its roles from (built once, locally, no spend).
if ! docker image inspect climate-index:local >/dev/null 2>&1; then
	echo "== build the app image (first run only) =="
	docker compose -f "${REPO_ROOT}/docker-compose.yml" build
fi

# 4. Render the unit templates. The installed copies are derived artifacts: edit the
#    templates, never /etc/systemd/system.
render() {
	sed \
		-e "s|__REPO_ROOT__|${REPO_ROOT}|g" \
		-e "s|__ENV_FILE__|${ENV_FILE}|g" \
		-e "s|__DATA_DIR__|${CII_DEMO_DATA_DIR}|g" \
		-e "s|__REFRESH_INTERVAL__|${CII_DEMO_REFRESH_INTERVAL}|g" \
		"$1" >"$2"
}
render "${DEPLOY_DIR}/${DASHBOARD_UNIT}.template" "${UNIT_DIR}/${DASHBOARD_UNIT}"
render "${DEPLOY_DIR}/${REFRESH_UNIT}.template" "${UNIT_DIR}/${REFRESH_UNIT}"
render "${DEPLOY_DIR}/${REFRESH_TIMER}.template" "${UNIT_DIR}/${REFRESH_TIMER}"
systemctl daemon-reload

# 5. One refresh before anything is reachable, so the first visitor sees data. It
#    runs in the foreground: a broken pipeline fails the standup rather than
#    quietly publishing nothing.
echo "== first refresh =="
systemctl start "${REFRESH_UNIT}"

# 6. The always-on dashboard and the cadence. Enabling the timer after the first
#    refresh arms the interval from that activation.
systemctl enable --now "${DASHBOARD_UNIT}"
systemctl enable --now "${REFRESH_TIMER}"

# 7. The public door.
"${DEPLOY_DIR}/install_caddy_site.sh"

echo
systemctl --no-pager --lines=0 status "${DASHBOARD_UNIT}" | head -4 || true
systemctl list-timers --no-pager "${REFRESH_TIMER}" || true
