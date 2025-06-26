#!/usr/bin/env bash
# Source this script to set PYTHONPATH to the repository root
# Useful for running local scripts and tests.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="${SCRIPT_DIR}${PYTHONPATH:+:$PYTHONPATH}"
