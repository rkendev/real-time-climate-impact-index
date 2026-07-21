#!/usr/bin/env bash
# Add (or remove) the demo's site block in the host's existing Caddy config.
#
# The box already runs one Caddy that owns 80 and 443 and fronts several other
# sites. This script never replaces that configuration: it strips any previously
# installed block of its own between the managed markers, appends the freshly
# rendered one, validates the whole file, and reloads. Every other site is left
# byte for byte as it was, and a failed validation restores the backup rather than
# leaving a broken front door for anyone else on the box.
#
#   deploy/vps/install_caddy_site.sh            add or update the demo block
#   deploy/vps/install_caddy_site.sh --remove   take the demo block out again
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TEMPLATE="${REPO_ROOT}/deploy/vps/caddy-site.template"
ENV_FILE="${CII_DEMO_ENV_FILE:-${REPO_ROOT}/deploy/vps/demo.env}"
CADDYFILE="${CII_DEMO_CADDYFILE:-/etc/caddy/Caddyfile}"
# The validator and the reload are seams so the strip-and-append logic can be
# exercised against a fixture without touching the box's running proxy.
CADDY_BIN="${CII_DEMO_CADDY_BIN:-caddy}"
RELOAD_CMD="${CII_DEMO_RELOAD_CMD:-systemctl reload caddy}"

BEGIN_MARKER="# >>> climate-index demo (managed) >>>"
END_MARKER="# <<< climate-index demo (managed) <<<"

remove_only=0
if [ "${1:-}" = "--remove" ]; then
	remove_only=1
fi

if [ ! -f "${ENV_FILE}" ]; then
	echo "missing demo environment: ${ENV_FILE} (run deploy/vps/install.sh)" >&2
	exit 2
fi
set -a
# shellcheck disable=SC1090
. "${ENV_FILE}"
set +a

if [ ! -f "${CADDYFILE}" ]; then
	echo "no Caddy configuration at ${CADDYFILE}" >&2
	exit 2
fi
if ! command -v "${CADDY_BIN}" >/dev/null 2>&1; then
	echo "${CADDY_BIN} is not on PATH; cannot validate the configuration" >&2
	exit 2
fi

backup="${CADDYFILE}.bak.climate-index"
cp -p "${CADDYFILE}" "${backup}"

candidate="$(mktemp)"
trap 'rm -f "${candidate}"' EXIT

# Everything except a previously installed demo block, verbatim. Blank lines are
# held back until a real line follows, so the separator this script appends is not
# accumulated across re-runs and repeated installs are byte-identical.
awk -v begin="${BEGIN_MARKER}" -v end="${END_MARKER}" '
	$0 == begin { skipping = 1 }
	skipping != 1 {
		if ($0 ~ /^[[:space:]]*$/) {
			pending++
		} else {
			while (pending > 0) { print ""; pending-- }
			print
		}
	}
	$0 == end { skipping = 0 }
' "${CADDYFILE}" >"${candidate}"

if [ "${remove_only}" -eq 0 ]; then
	: "${CII_DEMO_HOST:?CII_DEMO_HOST is not set (run deploy/vps/install.sh)}"
	port="${CII_DEMO_PORT:-8501}"
	printf '\n' >>"${candidate}"
	awk -v begin="${BEGIN_MARKER}" 'index($0, begin) == 1 { found = 1 } found { print }' \
		"${TEMPLATE}" |
		sed -e "s|__DEMO_HOST__|${CII_DEMO_HOST}|g" -e "s|__PORT__|${port}|g" >>"${candidate}"
fi

if ! "${CADDY_BIN}" validate --config "${candidate}" --adapter caddyfile >/dev/null 2>&1; then
	echo "the rendered Caddy configuration failed validation; nothing was changed" >&2
	"${CADDY_BIN}" validate --config "${candidate}" --adapter caddyfile >&2 || true
	exit 1
fi

cat "${candidate}" >"${CADDYFILE}"

if ! ${RELOAD_CMD}; then
	echo "caddy reload failed; restoring the previous configuration" >&2
	cat "${backup}" >"${CADDYFILE}"
	${RELOAD_CMD} || true
	exit 1
fi

if [ "${remove_only}" -eq 1 ]; then
	echo "removed the demo site block; the previous configuration is at ${backup}"
else
	echo "serving the demo at https://${CII_DEMO_HOST} (previous configuration at ${backup})"
fi
