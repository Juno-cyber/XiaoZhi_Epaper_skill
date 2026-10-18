#!/usr/bin/env python3
"""Accept historical JSONL layouts through the current validated builder (2.0.7+)."""
import argparse
import json
import os
import shlex
import sys

from quick_page_builder import BuildError, DeviceClient, build_page, parse_layout, read_layout_stream


def convert(text):
    records = [json.loads(line) for line in text.splitlines() if line.strip()]
    if not records or len(records) > 31:
        raise BuildError("expected 1-30 elements plus optional final refresh")
    lines = ["clear"]
    for index, record in enumerate(records):
        if not isinstance(record, dict) or not isinstance(record.get("args"), dict):
            raise BuildError("invalid JSONL command")
        tool, args = record.get("tool"), record["args"]
        if tool == "fridge.canvas.refresh":
            if index != len(records) - 1 or set(args) - {"refresh"}:
                raise BuildError("refresh must be last with no unknown fields")
            continue
        allowed = {"fridge.canvas.add_" + kind: kind for kind in ("text", "rect", "line", "image")}
        if tool not in allowed or args.get("refresh", False) is not False:
            raise BuildError("unsupported legacy command or per-element refresh")
        values = []
        for key, value in args.items():
            token = value if isinstance(value, str) else json.dumps(value)
            values.append(key + "=" + shlex.quote(token))
        lines.append(allowed[tool] + " " + " ".join(values))
    lines.append("refresh")
    layout = "\n".join(lines)
    parse_layout(layout, 6)
    return layout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("host")
    parser.add_argument("layout")
    parser.add_argument("--port", type=int, default=int(os.environ.get("XIAOZHI_PORT", "8080")))
    args = parser.parse_args()
    if args.layout == "-":
        text = read_layout_stream(sys.stdin.buffer, "stdin")
    else:
        with open(args.layout, "rb") as handle:
            text = read_layout_stream(handle, args.layout)
    try:
        layout = convert(text)
    except (BuildError, ValueError) as exc:
        print(f"ERROR: invalid legacy layout: {exc}", file=sys.stderr)
        return 2
    client = DeviceClient(args.host, port=args.port)
    client.health()
    build_page(client, 6, layout)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (BuildError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
