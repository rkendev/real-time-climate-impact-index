#!/usr/bin/env bash
# Role dispatcher for the one app image (ADR-0003). The first argument selects the
# role; config arrives entirely through CII_ environment variables (INV-1), so no
# endpoint or secret is baked into the image. The compose command sets the role.
set -euo pipefail

role="${1:-dashboard}"

case "${role}" in
producer)
	# One bounded batch to the broker (UC-1). Re-run the service to produce more.
	exec python -m climate_index.producer
	;;
consumer)
	# The commit-after-write consume loop (ADR-0002, UC-3, UC-4). Loops until
	# stopped; set CII_CONSUMER_ONESHOT=1 to drain once and exit (the broker smoke).
	exec python -m climate_index.consumer
	;;
dashboard)
	# The strictly read-only view (UC-5, INV-2). Binds all interfaces inside the
	# container; the security group is what limits reachability to the owner.
	exec streamlit run app/dashboard.py \
		--server.port "${CII_DASHBOARD_PORT:-8501}" \
		--server.address 0.0.0.0 \
		--server.headless true
	;;
*)
	echo "unknown role: ${role} (expected producer, consumer, or dashboard)" >&2
	exit 64
	;;
esac
