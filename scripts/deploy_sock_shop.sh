#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/common.sh
source config/testbed.env
.venv/bin/python scripts/prepare_sock_shop.py
kubectl --context="$PROFILE" create namespace "$SOCK_SHOP_NAMESPACE" --dry-run=client -o yaml \
  | kubectl --context="$PROFILE" apply -f -
kubectl --context="$PROFILE" apply --dry-run=server -f infra/sock-shop/local-emulated.yaml
kubectl --context="$PROFILE" apply -f infra/sock-shop/local-emulated.yaml
while IFS= read -r deployment; do
  kubectl --context="$PROFILE" -n "$SOCK_SHOP_NAMESPACE" rollout status "$deployment" --timeout=300s
done < <(kubectl --context="$PROFILE" -n "$SOCK_SHOP_NAMESPACE" get deployments -o name)
kubectl --context="$PROFILE" -n "$SOCK_SHOP_NAMESPACE" get pods -o wide
