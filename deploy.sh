#!/usr/bin/env bash
# Deploy the repository copy into Hermes. Git commits/pushes are intentionally separate.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="${XIAOZHI_SKILL_DIR:-${HOME}/.hermes/skills/smart-home/xiaozhi-control}"
DRY_RUN=false

case "${1:-}" in
  "") ;;
  --dry-run) DRY_RUN=true ;;
  *) echo "Usage: bash deploy.sh [--dry-run]" >&2; exit 2 ;;
esac

case "$SKILL_DIR" in
  ""|"/"|"$HOME"|"$REPO_DIR")
    echo "ERROR: unsafe deployment target: $SKILL_DIR" >&2
    exit 2
    ;;
esac
if [ -d "$SKILL_DIR" ] && [ -n "$(find "$SKILL_DIR" -type l -print -quit)" ]; then
  echo "ERROR: deployment target contains symlinks; refusing to follow them" >&2
  exit 2
fi

copy_file() {
  local source="$1" target="$2"
  if "$DRY_RUN"; then
    echo "COPY $source -> $target"
  else
    cp -p -- "$source" "$target"
  fi
}

sync_group() {
  local source_dir="$1" target_dir="$2" pattern="$3"
  if ! "$DRY_RUN"; then
    mkdir -p -- "$target_dir"
  fi

  local source existing basename
  shopt -s nullglob
  local sources=("$source_dir"/$pattern)
  shopt -u nullglob
  for source in "${sources[@]}"; do
    copy_file "$source" "$target_dir/"
  done

  [ -d "$target_dir" ] || return 0
  shopt -s nullglob
  local existing_files=("$target_dir"/$pattern)
  shopt -u nullglob
  for existing in "${existing_files[@]}"; do
    basename="${existing##*/}"
    if [ ! -f "$source_dir/$basename" ]; then
      if "$DRY_RUN"; then
        echo "REMOVE stale $existing"
      else
        rm -f -- "$existing"
      fi
    fi
  done
}

if ! "$DRY_RUN"; then
  mkdir -p -- "$SKILL_DIR"
fi
copy_file "$REPO_DIR/SKILL.md" "$SKILL_DIR/SKILL.md"
copy_file "$REPO_DIR/requirements-optional.txt" "$SKILL_DIR/requirements-optional.txt"
sync_group "$REPO_DIR/scripts" "$SKILL_DIR/scripts" "*.py"
sync_group "$REPO_DIR/templates" "$SKILL_DIR/templates" "*.sh"
sync_group "$REPO_DIR/templates" "$SKILL_DIR/templates" "*.md"
sync_group "$REPO_DIR/templates" "$SKILL_DIR/templates" "*.svg"
sync_group "$REPO_DIR/references" "$SKILL_DIR/references" "*.md"

if "$DRY_RUN"; then
  echo "Dry run complete: $SKILL_DIR"
else
  echo "Deployed to $SKILL_DIR"
fi
