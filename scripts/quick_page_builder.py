#!/usr/bin/env python3
"""Build xiaozhi e-paper canvas/custom pages from a small validated DSL."""

import argparse
import http.client
import ipaddress
import json
import math
import os
import shlex
import socket
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from pixel_art_generator import ARTISTS, to_bitmap

SCREEN_WIDTH = 296
SCREEN_HEIGHT = 128
MAX_ELEMENTS = 30
MAX_COMMANDS = 64
MAX_LAYOUT_BYTES = 256 * 1024
MAX_RESPONSE_BYTES = 1024 * 1024
DEFAULT_TIMEOUT = 8.0
VALID_HOST_CHARS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-:_[]")


class BuildError(RuntimeError):
    """A validation, transport, or device error that must fail the build."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Keep a LAN device from redirecting requests outside the validated target."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


DEVICE_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())


RFC1918_V4 = tuple(ipaddress.ip_network(value) for value in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))
ULA_V6 = ipaddress.ip_network("fc00::/7")


def is_trusted_address(address):
    if address.is_loopback or address.is_link_local:
        return True
    if address.version == 4:
        return any(address in network for network in RFC1918_V4)
    return address in ULA_V6


def normalize_host(value, allow_public=False):
    """Return a URL-safe LAN host without accepting paths or user-info."""
    host = value.strip()
    if not host or len(host) > 253:
        raise BuildError("device host is empty or too long")
    if "://" in host or "/" in host or "@" in host or any(c not in VALID_HOST_CHARS for c in host):
        raise BuildError("device must be an IP/hostname, not a URL or path")

    raw_host = host[1:-1] if host.startswith("[") and host.endswith("]") else host
    try:
        literal = ipaddress.ip_address(raw_host)
    except ValueError:
        literal = None
        labels = raw_host.rstrip(".").split(".")
        if any(not label or len(label) > 63 or label.startswith("-") or label.endswith("-") for label in labels):
            raise BuildError("invalid device hostname")

    if literal is not None and not allow_public:
        if not is_trusted_address(literal):
            raise BuildError("refusing a public device address; this skill is LAN-only")
    if literal is not None and literal.version == 6 and not host.startswith("["):
        host = f"[{host}]"
    return host


class DeviceClient:
    def __init__(self, host, port=8080, timeout=DEFAULT_TIMEOUT, allow_public=False):
        normalized = normalize_host(host, allow_public=allow_public)
        if not 1 <= port <= 65535:
            raise BuildError("port must be between 1 and 65535")
        if timeout <= 0 or timeout > 120:
            raise BuildError("timeout must be in (0, 120] seconds")
        raw_host = normalized[1:-1] if normalized.startswith("[") else normalized
        try:
            literal = ipaddress.ip_address(raw_host)
        except ValueError:
            try:
                resolved = socket.getaddrinfo(raw_host, port, type=socket.SOCK_STREAM)
            except socket.gaierror as exc:
                raise BuildError(f"cannot resolve device hostname: {exc}") from exc
            addresses = []
            for family, _, _, _, sockaddr in resolved:
                address = ipaddress.ip_address(sockaddr[0])
                if address not in addresses:
                    addresses.append(address)
            if not addresses:
                raise BuildError("device hostname resolved to no address")
            if not allow_public and any(not is_trusted_address(address) for address in addresses):
                raise BuildError("device hostname resolves outside the trusted LAN")
            addresses.sort(key=lambda address: address.version != 4)
            literal = addresses[0]
        self.host = f"[{literal}]" if literal.version == 6 else str(literal)
        self.base_url = f"http://{self.host}:{port}"
        self.timeout = timeout

    @staticmethod
    def _read_limited(response):
        raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise BuildError("device response exceeds 1 MiB")
        return raw

    def call(self, tool, args):
        payload = json.dumps({"tool": tool, "args": args}, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + "/api/call",
            data=payload,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        try:
            with DEVICE_OPENER.open(request, timeout=self.timeout) as response:
                raw = self._read_limited(response)
        except (urllib.error.URLError, http.client.HTTPException, TimeoutError, OSError) as exc:
            raise BuildError(f"device request failed: {exc}") from exc

        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BuildError("device returned invalid JSON") from exc
        return self._unwrap_response(data)

    def health(self):
        try:
            with DEVICE_OPENER.open(self.base_url + "/", timeout=self.timeout) as response:
                raw = self._read_limited(response)
            data = json.loads(raw.decode("utf-8"))
        except (urllib.error.URLError, http.client.HTTPException, TimeoutError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BuildError(f"device identity check failed: {exc}") from exc
        if not isinstance(data, dict) or data.get("status") != "ok" or not isinstance(data.get("board"), str) or not data["board"]:
            raise BuildError("target is not an identifiable xiaozhi device")
        return data

    @staticmethod
    def _unwrap_response(data):
        if not isinstance(data, dict):
            raise BuildError("device returned a non-object response")
        if data.get("error"):
            raise BuildError(f"device error: {data['error']}")

        result = data.get("result")
        if isinstance(result, dict):
            if result.get("isError"):
                content = result.get("content") or []
                message = content[0].get("text") if content and isinstance(content[0], dict) else "unknown error"
                raise BuildError(f"device tool error: {message}")
            content = result.get("content")
            found_text = False
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        found_text = True
                        value = item.get("text", "")
                        if not isinstance(value, str):
                            raise BuildError("device tool returned a non-string text result")
                        try:
                            data = json.loads(value)
                        except json.JSONDecodeError:
                            raise BuildError(f"device tool returned non-JSON: {value[:200]}")
                        break
            if not found_text:
                raise BuildError("device tool returned no text result")

        if isinstance(data, dict) and data.get("error"):
            raise BuildError(f"device error: {data['error']}")
        if isinstance(data, dict) and data.get("status") not in (None, "success", "ok"):
            raise BuildError(f"device returned unsuccessful status: {data.get('status')}")
        return data

    def list_images(self):
        try:
            with DEVICE_OPENER.open(self.base_url + "/api/canvas_image", timeout=self.timeout) as response:
                raw = self._read_limited(response)
            data = json.loads(raw.decode("utf-8"))
        except (urllib.error.URLError, http.client.HTTPException, TimeoutError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BuildError(f"cannot list device images: {exc}") from exc
        if not isinstance(data, list):
            raise BuildError("image list response is not an array")
        return data

    def upload_image(self, name, bitmap):
        if not valid_image_name(name):
            raise BuildError("image name must be a safe basename of at most 64 characters")
        query = urllib.parse.urlencode({"name": name})
        request = urllib.request.Request(
            self.base_url + "/api/canvas_image?" + query,
            data=bitmap,
            headers={"Content-Type": "application/octet-stream"},
            method="POST",
        )
        try:
            with DEVICE_OPENER.open(request, timeout=self.timeout) as response:
                raw = self._read_limited(response)
        except (urllib.error.URLError, http.client.HTTPException, TimeoutError, OSError) as exc:
            raise BuildError(f"image upload failed: {exc}") from exc
        try:
            result = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BuildError("image upload returned invalid JSON") from exc
        if not isinstance(result, dict) or result.get("error") or result.get("status") not in ("success", "ok"):
            raise BuildError(f"image upload was not successful: {result}")


def parse_value(value):
    lowered = value.lower()
    if lowered in ("true", "false"):
        return lowered == "true"
    try:
        return int(value)
    except ValueError:
        return value


def parse_kv(text, line_number=None):
    """Parse key=value tokens once, preserving whitespace inside quoted values."""
    try:
        tokens = shlex.split(text, posix=True)
    except ValueError as exc:
        where = f"line {line_number}: " if line_number else ""
        raise BuildError(where + str(exc)) from exc
    values = {}
    for token in tokens:
        if "=" not in token:
            where = f"line {line_number}: " if line_number else ""
            raise BuildError(where + f"expected key=value, got {token!r}")
        key, value = token.split("=", 1)
        if not key or key in values:
            where = f"line {line_number}: " if line_number else ""
            raise BuildError(where + f"invalid or duplicate key {key!r}")
        values[key] = parse_value(value)
    return values


def _require(args, required, line_number):
    missing = sorted(required - args.keys())
    if missing:
        raise BuildError(f"line {line_number}: missing {', '.join(missing)}")


def _allow_only(args, allowed, line_number):
    unknown = sorted(args.keys() - allowed)
    if unknown:
        raise BuildError(f"line {line_number}: unknown parameter(s): {', '.join(unknown)}")


def _integer_in(args, key, low, high, line_number):
    value = args[key]
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise BuildError(f"line {line_number}: {key} must be an integer in [{low}, {high}]")


def estimate_text_width(text, font_size):
    """Conservative width estimate for the two bitmap fonts."""
    half = math.ceil(font_size / 2)
    return sum(font_size if unicodedata.east_asian_width(char) in ("W", "F", "A") else half for char in text)


def valid_image_name(name):
    safe = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-"
    return (
        isinstance(name, str)
        and 0 < len(name) <= 64
        and not name.startswith(".")
        and ".." not in name
        and all(char in safe for char in name)
    )


def validate_element(command, args, line_number):
    common = {"id", "refresh"}
    schemas = {
        "text": ({"id", "text", "x", "y"}, common | {"text", "x", "y", "font_size", "align", "max_width", "dynamic", "dynamic_type"}),
        "rect": ({"id", "x", "y", "w", "h"}, common | {"x", "y", "w", "h", "filled"}),
        "line": ({"id", "x1", "y1", "x2", "y2"}, common | {"x", "y", "x1", "y1", "x2", "y2", "width"}),
        "image": ({"id", "name", "x", "y", "w", "h"}, common | {"name", "x", "y", "w", "h"}),
        "pixart": ({"id", "art", "x", "y"}, common | {"art", "x", "y", "w", "h"}),
    }
    required, allowed = schemas[command]
    _require(args, required, line_number)
    _allow_only(args, allowed, line_number)

    element_id = args["id"]
    safe_name_chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
    if not isinstance(element_id, str) or not element_id or len(element_id) > 48 or any(c not in safe_name_chars for c in element_id):
        raise BuildError(f"line {line_number}: id may contain only letters, digits, '_' and '-' (max 48)")
    if "refresh" in args and not isinstance(args["refresh"], bool):
        raise BuildError(f"line {line_number}: refresh must be true or false")

    if command in ("text", "rect", "image", "pixart"):
        _integer_in(args, "x", 0, SCREEN_WIDTH - 1, line_number)
        _integer_in(args, "y", 0, SCREEN_HEIGHT - 1, line_number)
    if command == "text":
        if not isinstance(args["text"], str) or not args["text"]:
            raise BuildError(f"line {line_number}: text must be non-empty")
        if len(args["text"].encode("utf-8")) > 1024 or any(ord(char) < 32 and char not in "\t" for char in args["text"]):
            raise BuildError(f"line {line_number}: text is too large or contains control characters")
        font_size = args.get("font_size", 16)
        allowed_fonts = (12, 16, 56) if args.get("dynamic_type") == "clock" else (12, 16)
        if font_size not in allowed_fonts:
            raise BuildError(f"line {line_number}: font_size must be 12 or 16 (clock dynamics also support 56)")
        if args.get("align", "left") not in ("left", "center", "right"):
            raise BuildError(f"line {line_number}: align must be left, center or right")
        if "max_width" in args:
            _integer_in(args, "max_width", 1, SCREEN_WIDTH, line_number)
        if "dynamic" in args and not isinstance(args["dynamic"], bool):
            raise BuildError(f"line {line_number}: dynamic must be true or false")
        if "dynamic_type" in args and args["dynamic_type"] not in ("clock", "date"):
            raise BuildError(f"line {line_number}: unsupported dynamic_type")
        if "dynamic_type" in args and not args.get("dynamic", False):
            raise BuildError(f"line {line_number}: dynamic_type requires dynamic=true")

        text_width = estimate_text_width(args["text"], font_size)
        max_width = args.get("max_width", 276)
        line_width = min(text_width, max_width)
        align = args.get("align", "left")
        if align == "left":
            left = args["x"]
        elif align == "center":
            left = args["x"] + (max_width - line_width) / 2
        else:
            left = args["x"] + max_width - line_width
        if left < 0 or left + line_width > SCREEN_WIDTH:
            raise BuildError(f"line {line_number}: estimated text position exceeds the 296px width")
        line_count = max(1, math.ceil(text_width / max_width))
        if args["y"] + line_count * (font_size + 2) > SCREEN_HEIGHT:
            raise BuildError(f"line {line_number}: estimated wrapped text exceeds the 128px height")
    elif command in ("rect", "image", "pixart"):
        width = args.get("w", 24 if command == "pixart" else None)
        height = args.get("h", 24 if command == "pixart" else None)
        if isinstance(width, bool) or not isinstance(width, int) or width <= 0:
            raise BuildError(f"line {line_number}: w must be a positive integer")
        if isinstance(height, bool) or not isinstance(height, int) or height <= 0:
            raise BuildError(f"line {line_number}: h must be a positive integer")
        if args["x"] + width > SCREEN_WIDTH or args["y"] + height > SCREEN_HEIGHT:
            raise BuildError(f"line {line_number}: element exceeds the 296x128 screen")
        if command == "rect" and "filled" in args and not isinstance(args["filled"], bool):
            raise BuildError(f"line {line_number}: filled must be true or false")
        if command == "image":
            name = args["name"]
            if not valid_image_name(name):
                raise BuildError(f"line {line_number}: image name must be a safe basename of at most 64 characters")
        if command == "pixart" and args["art"] not in ARTISTS:
            raise BuildError(f"line {line_number}: unknown pixel art {args['art']!r}")
    elif command == "line":
        for key, high in (("x1", 295), ("x2", 295), ("y1", 127), ("y2", 127)):
            _integer_in(args, key, 0, high, line_number)
        if "width" in args:
            _integer_in(args, "width", 1, 16, line_number)


def parse_layout(layout_text, page):
    if page != 6 and not 7 <= page <= 15:
        raise BuildError("page must be 6 or a custom page from 7 to 15")
    commands = []
    element_ids = set()
    seen_element = False
    seen_clear = False
    seen_refresh = False
    if len(layout_text.encode("utf-8")) > MAX_LAYOUT_BYTES:
        raise BuildError(f"layout exceeds {MAX_LAYOUT_BYTES} bytes")
    for line_number, raw_line in enumerate(layout_text.splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#") or line == "---":
            continue
        command, separator, rest = line.partition(" ")
        command = "text" if command == "label" else command
        if seen_refresh:
            raise BuildError(f"line {line_number}: refresh must be the final command")
        if command in ("clear", "refresh"):
            if separator and rest.strip():
                raise BuildError(f"line {line_number}: {command} takes no parameters")
            if command == "clear":
                if seen_clear or seen_element:
                    raise BuildError(f"line {line_number}: clear may appear once and before all elements")
                seen_clear = True
            else:
                seen_refresh = True
            commands.append((command, {}, line_number))
            if len(commands) > MAX_COMMANDS:
                raise BuildError(f"line {line_number}: layout exceeds {MAX_COMMANDS} commands")
            continue
        if command == "switch":
            try:
                target = int(rest.strip())
            except ValueError as exc:
                raise BuildError(f"line {line_number}: switch requires a page number") from exc
            if not 1 <= target <= 15:
                raise BuildError(f"line {line_number}: switch page must be in [1, 15]")
            commands.append((command, {"target_page": target}, line_number))
            if len(commands) > MAX_COMMANDS:
                raise BuildError(f"line {line_number}: layout exceeds {MAX_COMMANDS} commands")
            continue
        if command not in ("text", "rect", "line", "image", "pixart"):
            raise BuildError(f"line {line_number}: unknown command {command!r}")
        args = parse_kv(rest, line_number)
        if page >= 7 and command == "text" and "max_width" in args:
            raise BuildError(
                f"line {line_number}: custom-page firmware ignores max_width; omit it (the region is fixed at 276px)"
            )
        validate_element(command, args, line_number)
        if args.get("refresh", False):
            raise BuildError(f"line {line_number}: element refresh must be false; use one final refresh command")
        if page == 6 and ("dynamic" in args or "dynamic_type" in args):
            raise BuildError(f"line {line_number}: dynamic fields are supported only on custom pages 7-15")
        if args["id"] in element_ids:
            raise BuildError(f"line {line_number}: duplicate element id {args['id']!r}")
        element_ids.add(args["id"])
        seen_element = True
        if len(element_ids) > MAX_ELEMENTS:
            raise BuildError(f"line {line_number}: layout exceeds the {MAX_ELEMENTS}-element device limit")
        commands.append((command, args, line_number))
        if len(commands) > MAX_COMMANDS:
            raise BuildError(f"line {line_number}: layout exceeds {MAX_COMMANDS} commands")
    if not commands:
        raise BuildError("layout contains no commands")
    return commands


def prepare_images(client, commands):
    """Verify/upload every image before a page clear can occur."""
    image_commands = [(command, args) for command, args, _ in commands if command in ("image", "pixart")]
    if not image_commands:
        return
    files = client.list_images()
    available = {item.get("name") for item in files if isinstance(item, dict) and isinstance(item.get("name"), str)}
    for command, args in image_commands:
        name = args["art"] if command == "pixart" else args["name"]
        if name in available:
            continue
        if command == "image":
            raise BuildError(f"device image {name!r} does not exist; upload it before building")
        client.upload_image(name, to_bitmap(ARTISTS[name]()))
        available.add(name)


RESTORE_FIELDS = {
    "text": {"id", "text", "x", "y", "font_size", "align", "max_width", "dynamic", "dynamic_type"},
    "rect": {"id", "x", "y", "w", "h", "filled"},
    "line": {"id", "x", "y", "x1", "y1", "x2", "y2", "width"},
    "image": {"id", "name", "x", "y", "w", "h"},
}


def snapshot_page(client, page):
    """Read and validate a restorable snapshot before a destructive clear."""
    if page == 6:
        elements = client.call("fridge.canvas.control", {"action": "list"})
    else:
        elements = client.call("fridge.page.element.control", {"action": "list", "page": page})
    if not isinstance(elements, list):
        raise BuildError("cannot safely snapshot page before clear: element list is not an array")

    snapshot = []
    for index, item in enumerate(elements, 1):
        if not isinstance(item, dict) or item.get("type") not in RESTORE_FIELDS:
            raise BuildError(f"cannot safely snapshot page before clear: unsupported element {index}")
        element_type = item["type"]
        args = {key: item[key] for key in RESTORE_FIELDS[element_type] if key in item}
        if "dtype" in item and "dynamic_type" not in args:
            args["dynamic_type"] = item["dtype"]
            args["dynamic"] = True
        if page >= 7:
            args.pop("max_width", None)
        validate_element(element_type, args, 0)
        snapshot.append((element_type, args))
    return snapshot


def restore_page(client, page, snapshot):
    """Best-effort restore of a validated snapshot after a failed rebuild."""
    if page == 6:
        client.call("fridge.canvas.control", {"action": "clear", "refresh": False})
    else:
        client.call("fridge.page.control", {"action": "clear", "refresh": False, "page": page})
    for element_type, source_args in snapshot:
        args = dict(source_args)
        args["refresh"] = False
        if page == 6:
            args["action"] = "add_" + element_type
            client.call("fridge.canvas.control", args)
        else:
            args.update({"action": "add", "page": page, "type": element_type})
            if element_type == "line":
                args.setdefault("x", 0)
                args.setdefault("y", 0)
            client.call("fridge.page.element.control", args)


def build_page(client, page, layout_text, delay=0.0, output=print):
    """Validate the entire layout before applying any device mutation."""
    commands = parse_layout(layout_text, page)
    if page >= 7:
        pages = client.call("fridge.page.control", {"action": "list"})
        if not isinstance(pages, list) or page not in {
            item.get("page") for item in pages if isinstance(item, dict) and isinstance(item.get("page"), int)
        }:
            raise BuildError(f"custom page {page} does not exist; create it before building")
    is_canvas = page == 6
    has_clear = any(command == "clear" for command, _, _ in commands)
    prepare_images(client, commands)
    snapshot = snapshot_page(client, page) if has_clear else None
    element_count = 0
    clear_attempted = False

    try:
        for command, source_args, line_number in commands:
            if command == "clear":
                tool = "fridge.canvas.control" if is_canvas else "fridge.page.control"
                args = {"action": "clear", "refresh": False}
                if not is_canvas:
                    args["page"] = page
                clear_attempted = True
                result = client.call(tool, args)
            elif command == "switch":
                result = client.call("fridge.pagemanager", source_args)
            elif command == "refresh":
                if is_canvas:
                    result = client.call("fridge.canvas.control", {"action": "refresh"})
                else:
                    result = client.call("fridge.pagemanager", {"target_page": page})
            else:
                args = dict(source_args)
                args.setdefault("refresh", False)
                actual_type = "image" if command == "pixart" else command
                if command == "pixart":
                    art = args.pop("art")
                    args.setdefault("w", 24)
                    args.setdefault("h", 24)
                    args["name"] = art

                if is_canvas:
                    args["action"] = "add_" + actual_type
                    result = client.call("fridge.canvas.control", args)
                else:
                    args["page"] = page
                    args["action"] = "add"
                    args["type"] = actual_type
                    if actual_type == "line":
                        args.setdefault("x", 0)
                        args.setdefault("y", 0)
                    result = client.call("fridge.page.element.control", args)
                element_count += 1
            output(f"line {line_number}: {command} -> {result.get('status', 'ok') if isinstance(result, dict) else 'ok'}")
            if delay:
                time.sleep(delay)
    except Exception as exc:
        if clear_attempted:
            try:
                restore_page(client, page, snapshot)
                output(f"Rollback restored {len(snapshot)} prior element(s) on page {page}")
            except Exception as rollback_exc:
                raise BuildError(f"build failed ({exc}); rollback also failed ({rollback_exc})") from exc
        raise
    output(f"Done: {element_count} element(s) on page {page}")
    return element_count


def make_parser():
    parser = argparse.ArgumentParser(description="Build a validated xiaozhi e-paper layout")
    parser.add_argument("host", help="private/LAN device IP or hostname (without http://)")
    parser.add_argument("page", type=int, help="6 for canvas, or 7-15 for a custom page")
    parser.add_argument("layout", nargs="?", default="-", help="layout file, or - for stdin")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--delay", type=float, default=0.0, help="optional delay between serial requests")
    parser.add_argument("--allow-public", action="store_true", help="allow a public target (unsafe; LAN-only by default)")
    parser.add_argument("--check", action="store_true", help="validate only; do not contact or mutate the device")
    return parser


def read_layout_stream(stream, source_name):
    raw = stream.read(MAX_LAYOUT_BYTES + 1)
    if len(raw) > MAX_LAYOUT_BYTES:
        raise BuildError(f"layout exceeds {MAX_LAYOUT_BYTES} bytes")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BuildError(f"{source_name} is not valid UTF-8") from exc


def main(argv=None):
    parser = make_parser()
    args = parser.parse_intermixed_args(argv) if hasattr(parser, "parse_intermixed_args") else parser.parse_args(argv)
    if args.delay < 0 or args.delay > 10:
        raise BuildError("delay must be in [0, 10] seconds")
    normalize_host(args.host, allow_public=args.allow_public)
    if not 1 <= args.port <= 65535:
        raise BuildError("port must be between 1 and 65535")
    if args.timeout <= 0 or args.timeout > 120:
        raise BuildError("timeout must be in (0, 120] seconds")
    if args.layout == "-":
        layout_text = read_layout_stream(sys.stdin.buffer, "stdin layout")
    else:
        try:
            with open(args.layout, "rb") as handle:
                layout_text = read_layout_stream(handle, args.layout)
        except OSError as exc:
            raise BuildError(f"cannot read layout: {exc}") from exc
    commands = parse_layout(layout_text, args.page)
    if args.check:
        element_count = sum(command not in ("clear", "switch", "refresh") for command, _, _ in commands)
        print(f"Valid: {element_count} element(s), {len(commands)} command(s)")
        return 0
    client = DeviceClient(args.host, port=args.port, timeout=args.timeout, allow_public=args.allow_public)
    client.health()
    build_page(client, args.page, layout_text, delay=args.delay)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BuildError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
