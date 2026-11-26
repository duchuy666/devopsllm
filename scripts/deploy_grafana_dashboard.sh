#!/usr/bin/env bash
# Deploy the generated Grafana dashboard overlay. Restarts the Grafana Pod, so it refuses to run
# while the collection controller holds its lock (a monitoring Pod change mid-scenario fails review).
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/common.sh
.venv/bin/python - <<'EOF'
import fcntl,sys
lock=open('.runtime/collection-controller.lock','a+')
try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
except BlockingIOError:sys.exit('Collection controller is active; stop it at a batch boundary before deploying Grafana.')
EOF
.venv/bin/python scripts/build_grafana_dashboard.py
version=$(.venv/bin/python -c "import json;print(json.load(open('infra/charts.lock.json'))['grafana']['version'])")
helm upgrade --install grafana grafana/grafana --version "$version" --kube-context shyn-thesis --namespace monitoring \
  -f infra/observability/grafana-values.yaml -f infra/observability/grafana-dashboards-values.yaml --wait --timeout 5m
echo "Dashboard: kubectl --context shyn-thesis -n monitoring port-forward svc/grafana 3000:80, then open /d/sockshop-incident"
