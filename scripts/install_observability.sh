#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/common.sh
exec .venv/bin/python scripts/install_observability.py
