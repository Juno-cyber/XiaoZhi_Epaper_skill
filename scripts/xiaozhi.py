#!/usr/bin/env python3
"""Portable, JSON-output XiaoZhi control. No shell/curl or third-party packages."""

import argparse
import json
import sys
import urllib.parse

from quick_page_builder import BuildError, DeviceClient, DEFAULT_TIMEOUT, require_page


def existing_page(client, page):
    return require_page(client, page)


def validate_websocket_url(value):
    if not value or len(value.encode("utf-8")) > 512 or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value) or "#" in value or "\\" in value:
        raise BuildError("WebSocket URL must be at most 512 UTF-8 bytes, without whitespace, controls or fragments")
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme not in ("ws", "wss") or not parsed.hostname or parsed.username is not None or parsed.password is not None:
        raise BuildError("use a complete ws:// or wss:// URL without embedded credentials")
    try:
        parsed.port
    except ValueError as exc:
        raise BuildError("invalid WebSocket port") from exc
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("host", help="LAN IP/hostname from discovery")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--expect-mac", help="refuse a different device before any write")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("health")
    sub.add_parser("pages")
    for command in ("elements", "layout", "show"):
        item = sub.add_parser(command)
        item.add_argument("page", type=int, choices=range(2 if command == "elements" else 1, 16))
    home = sub.add_parser("home", help="read, or set both page and timeout in minutes")
    home.add_argument("--page", type=int, choices=range(1, 16))
    home.add_argument("--timeout-min", type=int, choices=range(61))
    name = sub.add_parser("name")
    name.add_argument("--set", dest="new_name", help="empty string resets the default name")
    voice = sub.add_parser("voice", help="read/set WebSocket URL only; restart separately to apply")
    voice.add_argument("--url", help="ws:// or wss:// URL; omitted means read only")
    call = sub.add_parser("call", help="call a documented MCP tool with a JSON args file")
    call.add_argument("tool")
    call.add_argument("--args-file", help="UTF-8 JSON object, or - for stdin; default {}")
    args = parser.parse_args(argv)

    # Reject bad input locally before contacting hardware.
    body = None
    if args.command == "voice" and args.url is not None:
        validate_websocket_url(args.url)
    if args.command == "home" and ((args.page is None) != (args.timeout_min is None)):
        raise BuildError("home writes require both --page and --timeout-min")
    if args.command == "name" and args.new_name is not None:
        if len(args.new_name.encode("utf-8")) > 64 or any(ord(c) < 32 or ord(c) == 127 for c in args.new_name):
            raise BuildError("device name must be at most 64 UTF-8 bytes without control characters")
    if args.command == "call":
        body = {}
        if args.args_file:
            if args.args_file == "-":
                raw = sys.stdin.buffer.read(4096)
            else:
                with open(args.args_file, "rb") as handle:
                    raw = handle.read(4096)
            if len(raw) >= 4096:
                raise BuildError("args file too large (max 4095 bytes)")
            body = json.loads(raw.decode("utf-8-sig"))
            if not isinstance(body, dict):
                raise BuildError("args file must contain a JSON object")

    client = DeviceClient(args.host, args.port, args.timeout)
    health = client.health()
    if args.expect_mac and str(health.get("mac", "")).lower() != args.expect_mac.lower():
        raise BuildError("device MAC differs from --expect-mac; no write performed")
    if args.command == "health":
        result = health
    elif args.command == "pages":
        result = client.call("fridge.page.control", {"action": "list"})
    elif args.command == "elements":
        require_page(client, args.page, editable=True)
        result = client.call("fridge.page.element.control", {"action": "list", "page": args.page})
    elif args.command == "show":
        existing_page(client, args.page)
        result = client.call("fridge.pagemanager", {"target_page": args.page})
    elif args.command == "layout":
        existing_page(client, args.page)
        result = client.http_json(f"/api/page_layout?page={args.page}")
    elif args.command == "home":
        if args.page is not None:
            existing_page(client, args.page)
            body = {"page": args.page, "timeout_min": args.timeout_min}
        result = client.http_json("/api/home_page", body)
    elif args.command == "voice":
        result = client.http_json("/api/websocket_url", None if args.url is None else {"url": args.url})
    elif args.command == "name":
        result = client.http_json("/api/device_name", None if args.new_name is None else {"name": args.new_name})
    else:
        result = client.call(args.tool, body)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (BuildError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
