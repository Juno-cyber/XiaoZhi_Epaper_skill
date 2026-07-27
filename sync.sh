# Sync script for XiaoZhi_Epaper_skill repo
# Syncs from local Hermes skill to GitHub repo, then pushes
#!/bin/bash
set -e

SKILL_DIR="$HOME/.hermes/skills/smart-home/xiaozhi-control"
REPO_DIR="$HOME/Gitproject/XiaoZhi_Epaper_skill"

if [ ! -d "$SKILL_DIR" ] || [ ! -d "$REPO_DIR" ]; then
    echo "ERROR: Source skill or repo directory not found"
    exit 1
fi

cd "$REPO_DIR"

# Check for changes
git diff --quiet HEAD 2>/dev/null
HAS_UNSTAGED=$?

# Sync files from skill to repo
# SKILL.md is NOT synced (it's a condensed version in the repo)
# Scripts are synced directly
for f in scripts/xiaozhi_discovery.py scripts/quick_page_builder.py scripts/pixel_art_generator.py scripts/crash_log.py; do
    if [ -f "$SKILL_DIR/$f" ]; then
        cp "$SKILL_DIR/$f" "$REPO_DIR/$f"
    fi
done

# Templates
if [ -d "$SKILL_DIR/templates" ]; then
    cp "$SKILL_DIR/templates/"*.sh "$REPO_DIR/templates/" 2>/dev/null || true
fi

# References → docs (map filenames)
for ref in references/*.md; do
    basename=$(basename "$ref")
    case "$basename" in
        custom-pages.md|web-console.md|canvas-web-interaction.md|firmware-development.md|page-templates.md|display-philosophy.md)
            # These need manual de-personalization — skip auto-sync
            ;;
    esac
done

# Check if there are changes to commit
git add -A
if git diff --cached --quiet; then
    echo "No changes to sync."
    exit 0
fi

git commit -m "Sync from Hermes skill: $(date '+%Y-%m-%d %H:%M')"
echo "Changes committed. Run 'git push' to sync to GitHub."
