#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/common.sh
source config/testbed.env
: "${KUBERNETES_VERSION:?Set a verified Kubernetes version in config/testbed.env first}"
docker info >/dev/null
# Minikube cannot resize an existing Docker profile through --memory alone.
# Keep this project's actual container cap aligned without deleting its PVCs.
if docker inspect --type container "$PROFILE" >/dev/null 2>&1; then
  current_memory=$(docker inspect "$PROFILE" --format '{{.HostConfig.Memory}}')
  expected_memory=$((MEMORY_MB * 1024 * 1024))
  if [[ "$current_memory" != "$expected_memory" ]]; then
    docker update --memory="${MEMORY_MB}m" --memory-swap="${MEMORY_MB}m" "$PROFILE"
  fi
fi
minikube start -p "$PROFILE" --driver=docker --container-runtime=containerd \
  --cpus="$CPUS" --memory="$MEMORY_MB" --kubernetes-version="$KUBERNETES_VERSION"
kubectl --context="$PROFILE" wait --for=condition=Ready nodes --all --timeout=180s
kubectl --context="$PROFILE" get nodes -o wide
