#!/usr/bin/env bash
# Simple helper to run pytest with the repository root on PYTHONPATH.
# Usage: ./run_tests.sh

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
export PYTHONPATH="$ROOT_DIR:${PYTHONPATH-}"

pytest -v --tb=short tests/
