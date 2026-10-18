#!/usr/bin/env python3
"""Install this skill for Hermes, Codex or an explicit agent directory."""

import argparse
import os
from pathlib import Path
import shutil
import sys

SOURCE = Path(__file__).resolve().parent.parent
GROUPS = {"scripts": ("*.py",), "references": ("*.md",),
          "templates": ("*.sh", "*.md", "*.svg", "*.layout")}


def install(target, dry_run=False):
    target = Path(os.path.abspath(os.path.expanduser(str(target))))
    if any(p.is_symlink() for p in (target, *target.parents)):
        raise ValueError("deployment target contains symlinks")
    resolved = target.resolve()
    if resolved == Path.home().resolve() or resolved in SOURCE.parents or SOURCE == resolved or SOURCE in resolved.parents:
        raise ValueError("unsafe deployment target (home, source or overlapping directory)")
    if target.exists() and any(p.is_symlink() for p in target.rglob("*")):
        raise ValueError("deployment target contains symlinks")
    copies = [(SOURCE / name, target / name) for name in ("SKILL.md", "requirements-optional.txt")]
    removals = []
    for group, patterns in GROUPS.items():
        for pattern in patterns:
            copies.extend((path, target / group / path.name) for path in sorted((SOURCE / group).glob(pattern)) if path.is_file())
            removals.extend(path for path in (target / group).glob(pattern)
                            if path.is_file() and not (SOURCE / group / path.name).exists())
    for source, destination in copies:
        print(f"COPY {source.relative_to(SOURCE)} -> {destination}")
        if not dry_run:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
    for path in removals:
        print(f"REMOVE stale {path}")
        if not dry_run:
            path.unlink()
    print(f"{'Dry run complete' if dry_run else 'Deployed'}: {target}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent", choices=("hermes", "codex"), default="hermes")
    parser.add_argument("--target", help="explicit directory; overrides --agent")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if args.agent == "codex":
        default = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "skills" / "xiaozhi-control"
    else:
        default = Path.home() / ".hermes" / "skills" / "smart-home" / "xiaozhi-control"
    install(args.target or os.environ.get("XIAOZHI_SKILL_DIR") or default, args.dry_run)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
