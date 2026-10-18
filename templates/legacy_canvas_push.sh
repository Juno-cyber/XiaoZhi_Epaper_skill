#!/usr/bin/env bash
# Compatibility for JSONL callers; uses the validated aggregate API (2.0.7+).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/../scripts/legacy_canvas_push.py" "$@"
