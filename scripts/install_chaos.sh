#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/common.sh
source config/testbed.env
helm repo add chaos-mesh https://charts.chaos-mesh.org
kubectl --context="$PROFILE" annotate namespace "$SOCK_SHOP_NAMESPACE" chaos-mesh.org/inject=enabled --overwrite
helm upgrade --install chaos-mesh chaos-mesh/chaos-mesh --version 2.8.8 \
  --kube-context "$PROFILE" --namespace chaos-mesh --create-namespace \
  -f infra/chaos-mesh/values.yaml --wait --timeout 5m
kubectl --context="$PROFILE" apply -f infra/chaos-mesh/remotecluster-rbac.yaml
kubectl --context="$PROFILE" -n chaos-mesh rollout restart deployment/chaos-controller-manager
kubectl --context="$PROFILE" -n chaos-mesh rollout status deployment/chaos-controller-manager --timeout=120s
