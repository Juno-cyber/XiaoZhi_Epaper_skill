#!/usr/bin/env bash
# deploy.sh — Deploy the repo skill to the Hermes skill directory.
# The REPO is the single source of truth; Hermes runs a deployed copy.
# Run this after every repo change, then (optionally) git push.
# Usage: bash deploy.sh            (deploy only)
#        bash deploy.sh --push     (deploy + git add/commit/push)
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$HOME/.hermes/skills/smart-home/xiaozhi-control"

if [ ! -d "$SKILL_DIR" ]; then
    echo "ERROR: Hermes skill dir not found: $SKILL_DIR"
    exit 1
fi

mkdir -p "$SKILL_DIR/scripts" "$SKILL_DIR/templates" "$SKILL_DIR/references"

# SKILL.md (includes Hermes frontmatter — safe to overwrite)
cp "$REPO_DIR/SKILL.md" "$SKILL_DIR/SKILL.md"

# Scripts
cp "$REPO_DIR"/scripts/*.py "$SKILL_DIR/scripts/"

# Templates (scripts + cron prompt templates — repo is the single source of truth)
cp "$REPO_DIR"/templates/*.sh "$SKILL_DIR/templates/" 2>/dev/null || true
cp "$REPO_DIR"/templates/*.md "$SKILL_DIR/templates/" 2>/dev/null || true

# References (repo dir name matches Hermes references/ — direct copy)
cp "$REPO_DIR"/references/*.md "$SKILL_DIR/references/"

echo "✅ Deployed to $SKILL_DIR"
echo "   SKILL.md        $(wc -l < "$SKILL_DIR/SKILL.md") lines"
echo "   scripts/        $(ls "$SKILL_DIR/scripts" | wc -l) files"
echo "   templates/      $(ls "$SKILL_DIR/templates" | wc -l) files"
echo "   references/     $(ls "$SKILL_DIR/references" | wc -l) files"

if [ "${1:-}" = "--push" ]; then
    cd "$REPO_DIR"
    git add -A
    if git diff --cached --quiet; then
        echo "No changes to commit."
    else
        git commit -m "Deploy skill update: $(date '+%Y-%m-%d %H:%M')"
        git push
        echo "✅ Pushed to GitHub."
    fi
fi
