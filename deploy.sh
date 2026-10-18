#!/usr/bin/env bash
# Compatibility entry point. Windows can call scripts/install_skill.py directly.
set -euo pipefail
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$REPO_DIR/scripts/install_skill.py" "$@"
