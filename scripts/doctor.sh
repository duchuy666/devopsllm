#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/.."
source scripts/common.sh
mkdir -p results/environment
out="results/environment/doctor-$(date -u +%Y%m%dT%H%M%SZ).txt"
failed=0
{
  date -u
  sw_vers
  uname -m
  sysctl -n hw.memsize || echo 'WARN: hardware query restricted by execution environment'
  df -h /System/Volumes/Data
  for tool in git docker minikube kubectl helm; do
    if command -v "$tool"; then
      case "$tool" in
        git) git --version || failed=1 ;;
        docker) docker --version || failed=1 ;;
        minikube) minikube version || failed=1 ;;
        kubectl) kubectl version --client || failed=1 ;;
        helm) helm version --short || failed=1 ;;
      esac
    else
      echo "MISSING: $tool"
      failed=1
    fi
  done
  if command -v docker >/dev/null; then
    if ! docker info --format 'Server={{.ServerVersion}} OS={{.OSType}} Arch={{.Architecture}} CPUs={{.NCPU}} Memory={{.MemTotal}}'; then
      echo 'BLOCKED: Docker engine is not ready.'
      failed=1
    fi
  fi
  exit "$failed"
} 2>&1 | tee "$out"
status=$?
echo "Evidence: $out"
exit "$status"
