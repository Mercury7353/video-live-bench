#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

python "$SCRIPT_DIR/balance_catogory_new.py"

python "$SCRIPT_DIR/plot_duration_dis.py"
