#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/common.sh
source config/testbed.env
child_pid=''
cleanup() {
  if [[ -n "$child_pid" ]]; then kill "$child_pid" 2>/dev/null || true; fi
  exit 0
}
trap cleanup INT TERM
while true; do
  kubectl --context="$PROFILE" -n "$SOCK_SHOP_NAMESPACE" port-forward \
    --address=127.0.0.1 service/front-end 8080:80 &
  child_pid=$!
  wait "$child_pid" || true
  child_pid=''
  echo 'Sock Shop tunnel ended; reconnecting in 2 seconds.'
  sleep 2
done
