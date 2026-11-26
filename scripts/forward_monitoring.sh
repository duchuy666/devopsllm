#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/common.sh
source config/testbed.env
pids=()
cleanup() {
  for pid in "${pids[@]}"; do kill "$pid" 2>/dev/null || true; done
}
trap cleanup EXIT
trap 'exit 0' INT TERM
forward_service() {
  local service="$1" ports="$2" child_pid=''
  trap 'if [[ -n "$child_pid" ]]; then kill "$child_pid" 2>/dev/null || true; fi; exit 0' INT TERM
  while true; do
    kubectl --context="$PROFILE" -n monitoring port-forward --address=127.0.0.1 "service/$service" "$ports" &
    child_pid=$!
    wait "$child_pid" || true
    child_pid=''
    echo "$service tunnel ended; reconnecting in 2 seconds."
    sleep 2
  done
}
for mapping in 'prometheus-server 9090:80' 'loki 3100:3100' 'jaeger 16686:16686' 'grafana 3000:80'; do
  read -r service ports <<< "$mapping"
  forward_service "$service" "$ports" &
  pids+=("$!")
done
wait
