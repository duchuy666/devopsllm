#!/usr/bin/env bash
# Shared project-local Kubernetes state; never changes the user's kube context.
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PATH="/opt/homebrew/bin:/Applications/Docker.app/Contents/Resources/bin:$PATH"
export MINIKUBE_HOME="$PROJECT_ROOT/.runtime/minikube"
export KUBECONFIG="$PROJECT_ROOT/.runtime/kubeconfig"
export HELM_CONFIG_HOME="$PROJECT_ROOT/.runtime/helm/config"
export HELM_CACHE_HOME="$PROJECT_ROOT/.runtime/helm/cache"
export HELM_DATA_HOME="$PROJECT_ROOT/.runtime/helm/data"
mkdir -p "$MINIKUBE_HOME"
