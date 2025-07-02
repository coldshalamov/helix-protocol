#!/usr/bin/env bash
# Simple helper to run pytest with the repository root on PYTHONPATH.
# Usage: ./run_tests.sh

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
export PYTHONPATH="$ROOT_DIR:${PYTHONPATH-}"

COV_ARGS="--cov=helix --cov-report=term"
if [[ -n "${COV_FAIL_UNDER:-}" ]]; then
  COV_ARGS+=" --cov-fail-under=${COV_FAIL_UNDER}"
fi

pytest -vv ${COV_ARGS} tests/ "$@"
