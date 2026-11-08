#!/usr/bin/env python3
"""Quick, non-blocking fast-forward update check for the Yunmo skill."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parent.parent
SOURCE_RECORD = ".yunmo-source.json"
TRUSTED_REMOTE = "https://github.com/juno-cyber/xiaozhi_epaper_skill"


class UpdateSkipped(Exception):
    """A safe reason to keep using the installed version."""


def canonical_remote(value):
    value = value.strip().replace("\\", "/")
    if value.startswith("git@github.com:"):
        value = "https://github.com/" + value[len("git@github.com:"):]
    elif value.startswith("ssh://git@github.com/"):
        value = "https://github.com/" + value[len("ssh://git@github.com/"):]
    return value.removesuffix(".git").rstrip("/").lower()


def run_git(source, args, deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise UpdateSkipped("检查超时")
    environment = os.environ.copy()
    environment.update({
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_SSH_COMMAND": "ssh -o BatchMode=yes -o ConnectTimeout=3",
    })
    try:
        return subprocess.run(
            ["git", *args], cwd=source, env=environment,
            capture_output=True, text=True, timeout=max(0.1, remaining), check=True)
    except subprocess.TimeoutExpired as exc:
        raise UpdateSkipped("检查超时") from exc
    except (OSError, subprocess.CalledProcessError) as exc:
        raise UpdateSkipped("远程仓库暂时不可用") from exc


def locate_source(root):
    if (root / ".git").exists():
        return root, False, ""
    record = root / SOURCE_RECORD
    try:
        data = json.loads(record.read_text(encoding="utf-8"))
        source = Path(data["source"]).expanduser().resolve()
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise UpdateSkipped("未找到可更新的源码仓库") from exc
    if not (source / ".git").exists():
        raise UpdateSkipped("安装来源已不存在")
    return source, True, str(data.get("commit", ""))


def update(root=ROOT, timeout=8.0):
    deadline = time.monotonic() + max(1.0, timeout)
    source, installed_copy, installed_commit = locate_source(root)
    remote = run_git(source, ["remote", "get-url", "origin"], deadline).stdout.strip()
    if canonical_remote(remote) != TRUSTED_REMOTE:
        raise UpdateSkipped("远程仓库地址不匹配")
    branch = run_git(source, ["branch", "--show-current"], deadline).stdout.strip()
    if branch != "main":
        raise UpdateSkipped("源码仓库不在 main 分支")
    if run_git(source, ["status", "--porcelain"], deadline).stdout.strip():
        raise UpdateSkipped("源码仓库有本地修改")

    run_git(source, ["fetch", "--quiet", "origin", "main:refs/remotes/origin/main"], deadline)
    local = run_git(source, ["rev-parse", "HEAD"], deadline).stdout.strip()
    remote_head = run_git(source, ["rev-parse", "origin/main"], deadline).stdout.strip()
    if local == remote_head:
        source_updated = False
    else:
        try:
            run_git(source, ["merge-base", "--is-ancestor", local, remote_head], deadline)
        except UpdateSkipped:
            try:
                run_git(source, ["merge-base", "--is-ancestor", remote_head, local], deadline)
                source_updated = False
            except UpdateSkipped as exc:
                raise UpdateSkipped("本地与远程历史已分叉") from exc
        else:
            run_git(source, ["merge", "--ff-only", "origin/main"], deadline)
            local = remote_head
            source_updated = True

    if installed_copy and installed_commit != local:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise UpdateSkipped("源码已更新，安装副本将在下次检查时同步")
        installer = source / "scripts" / "install_skill.py"
        try:
            subprocess.run(
                [sys.executable, str(installer), "--target", str(root)],
                cwd=source, timeout=remaining, check=True,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except subprocess.TimeoutExpired as exc:
            raise UpdateSkipped("源码已更新，安装副本将在下次检查时同步") from exc
        except (OSError, subprocess.CalledProcessError) as exc:
            raise UpdateSkipped("源码已更新，安装副本同步失败") from exc
        return "updated"
    return "updated" if source_updated else "current"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=float, default=8.0,
                        help="total update-check budget in seconds (default: 8)")
    args = parser.parse_args(argv)
    try:
        result = update(timeout=args.timeout)
        print("云墨 Skill 已更新，可以继续使用。" if result == "updated"
              else "云墨 Skill 已是最新版本。")
    except UpdateSkipped as exc:
        print(f"云墨 Skill 更新检查已跳过：{exc}；继续使用当前版本。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
