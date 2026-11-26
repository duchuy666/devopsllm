#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/common.sh
source config/testbed.env
stamp=$(date -u +%Y%m%dT%H%M%SZ)
receipt="results/collector-rollout/$stamp"
mkdir -p "$receipt"
kubectl --context="$PROFILE" -n monitoring get deployment incident-collector -o json > "$receipt/before-deployment.json"
active=$(kubectl --context="$PROFILE" -n monitoring exec deployment/incident-collector -- python -c "import sqlite3; c=sqlite3.connect('/data/incidents.sqlite'); print(c.execute(\"select count(*) from incidents where status in ('queued','collecting')\").fetchone()[0])")
if [[ "$active" != "0" ]]; then
  echo "Collector has active captures; finish them before rollout." >&2
  exit 1
fi
applied=false
rollback() {
  code=$?
  if [[ "$code" != "0" && "$applied" == "true" ]]; then
    kubectl --context="$PROFILE" -n monitoring rollout undo deployment/incident-collector
    kubectl --context="$PROFILE" -n monitoring rollout status deployment/incident-collector --timeout=120s
  fi
  exit "$code"
}
trap rollback EXIT
docker build --platform linux/arm64 -t shyn-collector:0.3.1 -f app/Dockerfile .
minikube -p "$PROFILE" image load shyn-collector:0.3.1
applied=true
kubectl --context="$PROFILE" apply -f infra/observability/collector.yaml
.venv/bin/python - <<'PY'
import json,subprocess
from pathlib import Path
image_id=subprocess.check_output(['docker','image','inspect','shyn-collector:0.3.1','--format','{{.Id}}'],text=True).strip()
patch={'spec':{'template':{'metadata':{'annotations':{'thesis.shyn/image-id':image_id}}}}}
Path('.runtime/collector-template-patch.json').write_text(json.dumps(patch))
PY
kubectl --context="$PROFILE" -n monitoring patch deployment/incident-collector \
  --patch-file .runtime/collector-template-patch.json
kubectl --context="$PROFILE" -n monitoring rollout status deployment/incident-collector --timeout=120s
docker image inspect shyn-collector:0.3.1 --format '{{.Id}} {{.Architecture}} {{.Created}}' \
  > results/environment/collector-image.txt
cp results/environment/collector-image.txt "$receipt/image.txt"
echo "Collector rollout verified: $receipt"
