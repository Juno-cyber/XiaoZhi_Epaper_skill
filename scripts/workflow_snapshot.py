#!/usr/bin/env python3
"""Build a bounded, conversation-safe snapshot of XiaoZhi cron jobs."""

import datetime
import json
import os
import re
import sqlite3
from urllib.parse import quote


SCHEMA_VERSION = 1
MAX_JOBS = 200
MAX_HISTORY = 64
MAX_EXECUTIONS_DB_BYTES = 64 * 1024 * 1024
META_RE = re.compile(
    r"\A\s*\[XIAOZHI_CRON_META v1 page=(6|[7-9]|1[0-5]) "
    r"mode=([a-z][a-z0-9-]{0,31})\]"
)


def _text(value, limit):
    text = value if isinstance(value, str) else "" if value is None else str(value)
    def valid_xml_character(char):
        codepoint = ord(char)
        return (
            codepoint == 0x09
            or 0x20 <= codepoint <= 0xD7FF
            or 0xE000 <= codepoint <= 0xFFFD
            or 0x10000 <= codepoint <= 0x10FFFF
        )
    return "".join(char for char in text if valid_xml_character(char))[:limit]


def parse_job_meta(prompt):
    """Parse the optional fixed-position metadata marker used by new jobs."""
    if not isinstance(prompt, str):
        return None
    match = META_RE.match(prompt[:512])
    if not match:
        return None
    return {"version": 1, "page": int(match.group(1)), "mode": match.group(2)}


def infer_target_page(job):
    """Return (page, confidence, mode) without exposing the prompt."""
    meta = parse_job_meta(job.get("prompt"))
    if meta:
        return meta["page"], "explicit", meta["mode"]

    blob = " ".join(
        _text(job.get(key), 4096) for key in ("name", "prompt", "script")
    )
    low = blob.lower()
    skills = job.get("skills") if isinstance(job.get("skills"), list) else []
    is_xiaozhi = (
        job.get("skill") == "xiaozhi-control"
        or "xiaozhi-control" in skills
        or "xiaozhi" in low
        or "墨水" in blob
        or "e-paper" in low
        or "画布" in blob
        or "屏幕" in blob
        or ("页" in blob and "排班" in blob)
    )
    if not is_xiaozhi:
        return None, None, None
    match = re.search(r"页\s*(\d+)", blob) or re.search(r"page\s*([0-9]+)", low)
    if match:
        page = int(match.group(1))
        return (page, "inferred", "unknown") if 6 <= page <= 15 else (None, "unknown", "unknown")
    if "画布" in blob or "canvas" in low:
        return 6, "inferred", "canvas-refresh"
    return None, "unknown", "unknown"


def is_xiaozhi_job(job):
    skills = job.get("skills") if isinstance(job.get("skills"), list) else []
    page, _, _ = infer_target_page(job)
    blob = " ".join(_text(job.get(key), 4096) for key in ("name", "prompt"))
    return (
        job.get("skill") == "xiaozhi-control"
        or "xiaozhi-control" in skills
        or page is not None
        or any(marker in blob for marker in ("墨水", "画布", "屏幕"))
    )


def normalize_jobs(raw_jobs, include_all=False):
    if not isinstance(raw_jobs, list):
        raise ValueError("jobs input must contain a jobs array")
    jobs = []
    dropped = 0
    for index, raw in enumerate(raw_jobs):
        if not isinstance(raw, dict):
            continue
        if not include_all and not is_xiaozhi_job(raw):
            continue
        if len(jobs) >= MAX_JOBS:
            dropped += 1
            continue
        page, confidence, mode = infer_target_page(raw)
        schedule = raw.get("schedule") if isinstance(raw.get("schedule"), dict) else {}
        enabled = raw.get("enabled", True) is not False
        status = "disabled" if not enabled else _text(raw.get("last_status") or raw.get("state") or "scheduled", 32)
        try:
            failure_streak = max(0, min(int(raw.get("failure_streak") or 0), 1000000))
        except (TypeError, ValueError):
            failure_streak = 0
        jobs.append(
            {
                "id": _text(raw.get("id") or f"job-{index}", 128),
                "name": _text(raw.get("name") or raw.get("id") or f"job-{index}", 256),
                "schedule": {
                    "kind": _text(schedule.get("kind"), 32),
                    "expr": _text(schedule.get("expr"), 256),
                    "display": _text(schedule.get("display"), 256),
                },
                "schedule_display": _text(raw.get("schedule_display"), 256),
                "enabled": enabled,
                "state": _text(raw.get("state"), 32),
                "last_status": status,
                "last_run_at": _text(raw.get("last_run_at"), 64),
                "next_run_at": _text(raw.get("next_run_at"), 64),
                "failure_streak": failure_streak,
                "created_at": _text(raw.get("created_at"), 64),
                "no_agent": bool(raw.get("no_agent")),
                "model": _text(raw.get("model"), 128),
                "target": {"page": page, "confidence": confidence, "mode": mode},
            }
        )
    return jobs, dropped


def normalize_history(history):
    if not isinstance(history, list):
        return []
    output = []
    for item in history[-MAX_HISTORY:]:
        if not isinstance(item, dict) or not isinstance(item.get("ts"), str):
            continue
        output.append(
            {
                "ts": _text(item.get("ts"), 64),
                "slot": _text(item.get("slot"), 32),
                "intent": _text(item.get("intent"), 64),
                "layout": _text(item.get("layout"), 64),
                "text": _text(item.get("text"), 512),
            }
        )
    return output


def _bounded_int(value, low, high, default=None):
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        return default
    return value


def normalize_device(device):
    pages = []
    elements = {}
    raw_pages = device.get("pages") if isinstance(device.get("pages"), list) else []
    raw_elements = device.get("elements") if isinstance(device.get("elements"), dict) else {}
    for raw_page in raw_pages[:15]:
        if not isinstance(raw_page, dict):
            continue
        page = _bounded_int(raw_page.get("page"), 1, 15)
        if page is None:
            continue
        pages.append(
            {
                "page": page,
                "name": _text(raw_page.get("name") or f"page {page}", 80),
                "builtin": bool(raw_page.get("builtin")),
            }
        )
        raw_items = raw_elements.get(page, raw_elements.get(str(page), []))
        safe_items = []
        if isinstance(raw_items, list):
            for item in raw_items[:30]:
                if not isinstance(item, dict) or item.get("type") not in {"text", "rect", "line", "image"}:
                    continue
                kind = item["type"]
                safe = {"type": kind, "id": _text(item.get("id"), 48)}
                if kind == "text":
                    x = _bounded_int(item.get("x"), 0, 295)
                    y = _bounded_int(item.get("y"), 0, 127)
                    font_size = _bounded_int(item.get("font_size", 12), 6, 64, 12)
                    if x is None or y is None:
                        continue
                    safe.update(
                        {
                            "text": _text(item.get("text"), 256),
                            "x": x,
                            "y": y,
                            "font_size": font_size,
                            "align": item.get("align") if item.get("align") in {"left", "center", "right"} else "left",
                            "max_width": _bounded_int(item.get("max_width", 276), 1, 296, 276),
                        }
                    )
                    dtype = item.get("dtype")
                    if dtype in {"clock", "date"}:
                        safe["dtype"] = dtype
                elif kind in {"rect", "image"}:
                    x = _bounded_int(item.get("x"), 0, 295)
                    y = _bounded_int(item.get("y"), 0, 127)
                    width = _bounded_int(item.get("w"), 1, 296)
                    height = _bounded_int(item.get("h"), 1, 128)
                    if x is None or y is None or width is None or height is None or x + width > 296 or y + height > 128:
                        continue
                    safe.update({"x": x, "y": y, "w": width, "h": height})
                    if kind == "rect":
                        safe["filled"] = bool(item.get("filled"))
                    else:
                        safe["name"] = _text(item.get("name"), 64)
                else:
                    coordinates = {
                        key: _bounded_int(item.get(key), 0, 295 if key.startswith("x") else 127)
                        for key in ("x1", "y1", "x2", "y2")
                    }
                    if any(value is None for value in coordinates.values()):
                        continue
                    safe.update(coordinates)
                    safe["width"] = _bounded_int(item.get("width", 1), 1, 16, 1)
                safe_items.append(safe)
        elements[page] = safe_items
    return {
        "online": bool(device.get("online", device.get("ip"))),
        "partial": bool(device.get("partial")),
        "name": _text(device.get("name"), 128),
        "ip": _text(device.get("ip"), 64),
        "version": _text(device.get("version"), 64),
        "pages": pages,
        "elements": elements,
    }


def load_recent_runs(path, job_ids, per_job=5):
    """Read bounded execution state from Hermes SQLite without writing to it."""
    if not path or not os.path.exists(path):
        return {}
    if os.path.islink(path) or not os.path.isfile(path):
        raise ValueError("executions database must be a regular non-symlink file")
    if os.path.getsize(path) > MAX_EXECUTIONS_DB_BYTES:
        raise ValueError("executions database exceeds 64 MiB")
    wanted = {str(job_id) for job_id in job_ids if job_id}
    if not wanted:
        return {}
    uri = "file:" + quote(os.path.abspath(path), safe="/") + "?mode=ro"
    try:
        connection = sqlite3.connect(uri, uri=True, timeout=1)
    except sqlite3.Error as exc:
        raise ValueError(f"cannot open executions database: {exc}") from exc
    try:
        names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "executions" not in names:
            connection.close()
            return {}
        rows = list(connection.execute(
            "SELECT id, job_id, status, claimed_at, started_at, finished_at "
            "FROM executions ORDER BY claimed_at DESC LIMIT ?",
            (min(5000, max(100, len(wanted) * per_job * 4)),),
        ))
    except sqlite3.Error as exc:
        connection.close()
        raise ValueError(f"cannot read executions database: {exc}") from exc
    output = {job_id: [] for job_id in wanted}
    connection.close()
    for row in rows:
        job_id = str(row[1])
        if job_id not in wanted or len(output[job_id]) >= per_job:
            continue
        output[job_id].append(
            {
                "id": _text(row[0], 128),
                "status": _text(row[2], 32),
                "claimed_at": _text(row[3], 64),
                "started_at": _text(row[4], 64),
                "finished_at": _text(row[5], 64),
            }
        )
    return {key: value for key, value in output.items() if value}


def build_snapshot(raw_jobs, history, device, executions_path=None, include_all=False, now=None):
    jobs, dropped = normalize_jobs(raw_jobs, include_all=include_all)
    safe_history = normalize_history(history)
    safe_device = normalize_device(device)
    warnings = []
    if dropped:
        warnings.append({"code": "jobs_truncated", "count": dropped})
    if not safe_device["online"]:
        warnings.append({"code": "device_offline"})
    elif safe_device["partial"]:
        warnings.append({"code": "device_partial"})
    owners = {}
    for job in jobs:
        page = job["target"]["page"]
        if job["target"]["confidence"] != "explicit":
            warnings.append({"code": "target_inferred", "job_id": job["id"]})
        if page is not None and job["enabled"]:
            owners.setdefault(page, []).append(job["id"])
        if job["failure_streak"]:
            warnings.append(
                {"code": "failure_streak", "job_id": job["id"], "count": job["failure_streak"]}
            )
    for page, job_ids in owners.items():
        if len(job_ids) > 1:
            warnings.append({"code": "page_conflict", "page": page, "job_ids": job_ids})
    try:
        recent_runs = load_recent_runs(executions_path, [job["id"] for job in jobs])
    except ValueError as exc:
        recent_runs = {}
        warnings.append({"code": "executions_unavailable", "detail": _text(exc, 160)})
    generated = now or datetime.datetime.now(datetime.timezone.utc).astimezone()
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated.isoformat(timespec="seconds"),
        "device": safe_device,
        "jobs": jobs,
        "history": safe_history,
        "recent_runs": recent_runs,
        "warnings": warnings,
    }
