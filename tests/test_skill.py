import datetime
import http.client
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
sys.path.insert(0, SCRIPTS)

import quick_page_builder as builder
import pixel_art_generator
import quote_fetcher
import xiaozhi_discovery as discovery


class FakeClient:
    def __init__(self, pages=None):
        self.calls = []
        self.images = []
        self.elements = []
        self.pages = pages if pages is not None else [{"page": 7, "name": "Test", "builtin": False}]

    def call(self, tool, args):
        self.calls.append((tool, dict(args)))
        if tool == "fridge.page.control" and args.get("action") == "list":
            return list(self.pages)
        if args.get("action") == "list" and tool in ("fridge.canvas.control", "fridge.page.element.control"):
            return [dict(item) for item in self.elements]
        if args.get("action") == "clear":
            self.elements = []
        if args.get("action") == "add" or str(args.get("action", "")).startswith("add_"):
            item = dict(args)
            item["type"] = item.get("type") or item["action"].removeprefix("add_")
            for key in ("action", "page", "refresh"):
                item.pop(key, None)
            self.elements.append(item)
        return {"status": "success"}

    def list_images(self):
        return list(self.images)

    def upload_image(self, name, bitmap):
        self.images.append({"name": name, "size": len(bitmap)})


class LayoutTests(unittest.TestCase):
    def test_quoted_spaces_and_escapes_are_preserved(self):
        commands = builder.parse_layout(
            'text id=title text="hello world \\"quoted\\"" x=1 y=2 font_size=12', 6
        )
        self.assertEqual(commands[0][1]["text"], 'hello world "quoted"')

    def test_custom_page_uses_add_and_type_contract(self):
        client = FakeClient()
        builder.build_page(
            client,
            7,
            "clear\nhline id=sep x1=17 x2=280 y=10 width=1\nrefresh",
            output=lambda _: None,
        )
        self.assertEqual(client.calls[0], ("fridge.page.control", {"action": "list"}))
        self.assertEqual(client.calls[1], ("fridge.page.element.control", {"action": "list", "page": 7}))
        self.assertEqual(client.calls[2], ("fridge.page.control", {"action": "clear", "refresh": False, "page": 7}))
        tool, args = client.calls[3]
        self.assertEqual(tool, "fridge.page.element.control")
        self.assertEqual(args["action"], "add")
        self.assertEqual(args["type"], "line")
        self.assertEqual((args["x"], args["y"]), (17, 10))
        self.assertEqual((args["x1"], args["y1"], args["x2"], args["y2"]), (17, 10, 280, 10))
        self.assertEqual(client.calls[4], ("fridge.page.element.control", {"action": "list", "page": 7}))
        self.assertEqual(client.calls[5], ("fridge.pagemanager", {"target_page": 7}))

    def test_missing_custom_page_is_detected_before_clear(self):
        client = FakeClient(pages=[])
        with self.assertRaisesRegex(builder.BuildError, "does not exist"):
            builder.build_page(client, 7, "clear\ntext id=t text=x x=0 y=0", output=lambda _: None)
        self.assertEqual(client.calls, [("fridge.page.control", {"action": "list"})])

    def test_canvas_uses_canvas_actions(self):
        client = FakeClient()
        builder.build_page(
            client,
            6,
            'text id=t text="hello" x=1 y=2 font_size=16\nrefresh',
            output=lambda _: None,
        )
        self.assertEqual(client.calls[0][0], "fridge.canvas.control")
        self.assertEqual(client.calls[0][1]["action"], "add_text")
        self.assertEqual(client.calls[1], ("fridge.canvas.control", {"action": "list"}))
        self.assertEqual(client.calls[2], ("fridge.pagemanager", {"target_page": 6}))

    def test_hline_expands_to_equal_nonzero_y_endpoints_and_is_verified(self):
        client = FakeClient()
        builder.build_page(
            client,
            6,
            "hline id=sep x1=12 x2=284 y=63 width=2\nrefresh",
            output=lambda _: None,
        )
        tool, args = client.calls[0]
        self.assertEqual(tool, "fridge.canvas.control")
        self.assertEqual(
            {key: args[key] for key in ("x1", "y1", "x2", "y2")},
            {"x1": 12, "y1": 63, "x2": 284, "y2": 63},
        )
        self.assertEqual(client.calls[1], ("fridge.canvas.control", {"action": "list"}))
        self.assertEqual(client.calls[2], ("fridge.pagemanager", {"target_page": 6}))

    def test_line_geometry_mismatch_fails_before_refresh(self):
        class WrongStartClient(FakeClient):
            def call(self, tool, args):
                result = super().call(tool, args)
                if args.get("action") in ("add", "add_line") and args.get("id") == "sep":
                    self.elements[-1]["x1"] = 0
                    self.elements[-1]["y1"] = 0
                return result

        client = WrongStartClient()
        with self.assertRaisesRegex(builder.BuildError, "geometry mismatch"):
            builder.build_page(
                client,
                6,
                "hline id=sep x1=12 x2=284 y=63\nrefresh",
                output=lambda _: None,
            )
        self.assertFalse(any(tool == "fridge.pagemanager" for tool, _ in client.calls))

    def test_line_geometry_mismatch_after_clear_rolls_back_before_refresh(self):
        class WrongStartClient(FakeClient):
            def call(self, tool, args):
                result = super().call(tool, args)
                if args.get("action") in ("add", "add_line") and args.get("id") == "new":
                    self.elements[-1]["x1"] = 0
                    self.elements[-1]["y1"] = 0
                return result

        client = WrongStartClient()
        original = {"type": "line", "id": "old", "x1": 5, "y1": 20, "x2": 290, "y2": 20, "width": 1}
        client.elements = [dict(original)]
        with self.assertRaisesRegex(builder.BuildError, "geometry mismatch"):
            builder.build_page(
                client,
                6,
                "clear\nhline id=new x1=12 x2=284 y=63\nrefresh",
                output=lambda _: None,
            )
        self.assertEqual(client.elements, [original])
        self.assertFalse(any(tool == "fridge.pagemanager" for tool, _ in client.calls))

    def test_full_preflight_prevents_partial_clear(self):
        client = FakeClient()
        with self.assertRaisesRegex(builder.BuildError, "unknown command"):
            builder.build_page(client, 6, "clear\nexplode now", output=lambda _: None)
        self.assertEqual(client.calls, [])

    def test_failed_rebuild_restores_snapshot(self):
        class FailOnceClient(FakeClient):
            def call(self, tool, args):
                if args.get("action") == "add" and args.get("id") == "new" and not hasattr(self, "failed"):
                    self.failed = True
                    self.calls.append((tool, dict(args)))
                    raise builder.BuildError("forced add failure")
                return super().call(tool, args)

        client = FailOnceClient()
        client.elements = [{"type": "text", "id": "old", "text": "keep", "x": 0, "y": 0, "font_size": 12}]
        with self.assertRaisesRegex(builder.BuildError, "forced add failure"):
            builder.build_page(client, 7, "clear\ntext id=new text=x x=0 y=0", output=lambda _: None)
        self.assertEqual(client.elements, [{"type": "text", "id": "old", "text": "keep", "x": 0, "y": 0, "font_size": 12}])

    def test_clear_refuses_unrestorable_snapshot(self):
        client = FakeClient()
        client.elements = [{"type": "future-widget", "id": "x"}]
        with self.assertRaisesRegex(builder.BuildError, "cannot safely snapshot"):
            builder.build_page(client, 7, "clear\ntext id=new text=x x=0 y=0", output=lambda _: None)
        self.assertFalse(any(args.get("action") == "clear" for _, args in client.calls))

    def test_missing_image_is_detected_before_clear(self):
        client = FakeClient()
        with self.assertRaisesRegex(builder.BuildError, "does not exist"):
            builder.build_page(
                client, 6, "clear\nimage id=logo name=missing x=0 y=0 w=8 h=8\nrefresh",
                output=lambda _: None,
            )
        self.assertEqual(client.calls, [])

    def test_adversarial_boundaries(self):
        invalid_layouts = [
            "text id=t text=x x=-1 y=0",
            "rect id=r x=290 y=0 w=7 h=1",
            "line id=l x1=0 y1=0 x2=296 y2=0",
            "line id=l x1=1 y1=1 x2=1 y2=1",
            "line id=l x=0 y=8 x1=4 y1=8 x2=20 y2=8",
            "line id=l x=4 y=0 x1=4 y1=8 x2=20 y2=8",
            "hline id=l x1=1 x2=2 y=3 y1=3",
            "text id=t text=x x=0 y=0 typo=1",
            "text id=t text=x x=0 y=0 id=t2",
            "text id=t text=居中 x=148 y=0 align=center",
            "text id=t text=右对齐 x=30 y=0 align=right",
            "text id=t text=x x=0 y=0 dynamic=true",
            "pixart id=p art=../../etc/passwd x=0 y=0",
            "text id=t text=x x=0 y=0 refresh=true",
            "text id=t text=x x=0 y=0\nclear",
            "refresh\ntext id=t text=x x=0 y=0",
            "clear\nclear",
        ]
        for layout in invalid_layouts:
            with self.subTest(layout=layout), self.assertRaises(builder.BuildError):
                builder.parse_layout(layout, 6)

    def test_element_limit_and_duplicate_ids(self):
        too_many = "\n".join(f"text id=t{i} text=x x=0 y=0" for i in range(31))
        with self.assertRaisesRegex(builder.BuildError, "30-element"):
            builder.parse_layout(too_many, 6)
        with self.assertRaisesRegex(builder.BuildError, "duplicate element"):
            builder.parse_layout("text id=t text=x x=0 y=0\ntext id=t text=y x=0 y=1", 6)

    def test_custom_dynamic_types_and_fonts_match_firmware(self):
        command = builder.parse_layout(
            "text id=clock text=--:-- x=10 y=5 font_size=56 dynamic=true dynamic_type=clock", 7
        )[0]
        self.assertEqual(command[1]["dynamic_type"], "clock")
        builder.parse_layout(
            "text id=date text=---- x=10 y=5 font_size=16 dynamic=true dynamic_type=date", 7
        )
        with self.assertRaisesRegex(builder.BuildError, "unsupported dynamic_type"):
            builder.parse_layout(
                "text id=temp text=-- x=10 y=5 dynamic=true dynamic_type=cpu_temp", 7
            )
        with self.assertRaisesRegex(builder.BuildError, "font_size"):
            builder.parse_layout(
                "text id=date text=---- x=10 y=5 font_size=56 dynamic=true dynamic_type=date", 7
            )
        with self.assertRaisesRegex(builder.BuildError, "ignores max_width"):
            builder.parse_layout(
                "text id=t text=x x=10 y=5 max_width=100", 7
            )

    def test_image_names_allow_safe_extensions_but_not_paths(self):
        command = builder.parse_layout("image id=logo name=logo.bin x=0 y=0 w=8 h=8", 6)[0]
        self.assertEqual(command[1]["name"], "logo.bin")
        for name in ("../secret", ".hidden", "two..dots", "a/b"):
            with self.subTest(name=name), self.assertRaises(builder.BuildError):
                builder.parse_layout(f"image id=logo name={name} x=0 y=0 w=8 h=8", 6)

    def test_layout_reader_is_bounded_and_requires_utf8(self):
        with self.assertRaisesRegex(builder.BuildError, "exceeds"):
            builder.read_layout_stream(io.BytesIO(b"x" * (builder.MAX_LAYOUT_BYTES + 1)), "test")
        with self.assertRaisesRegex(builder.BuildError, "UTF-8"):
            builder.read_layout_stream(io.BytesIO(b"\xff"), "test")

    def test_target_rejects_urls_and_public_addresses(self):
        for host in ("http://192.168.1.2", "192.168.1.2/path", "user@192.168.1.2", "8.8.8.8", "0.0.0.0", "192.0.2.1"):
            with self.subTest(host=host), self.assertRaises(builder.BuildError):
                builder.normalize_host(host)
        self.assertEqual(builder.normalize_host("192.168.1.2"), "192.168.1.2")
        self.assertEqual(builder.normalize_host("::1"), "[::1]")
        with mock.patch("quick_page_builder.socket.getaddrinfo", return_value=[
            (2, 1, 6, "", ("8.8.8.8", 8080)),
        ]):
            with self.assertRaisesRegex(builder.BuildError, "outside the trusted LAN"):
                builder.DeviceClient("example.test")

    def test_nested_device_errors_are_fatal(self):
        with self.assertRaisesRegex(builder.BuildError, "tool error"):
            builder.DeviceClient._unwrap_response(
                {"result": {"isError": True, "content": [{"type": "text", "text": "bad input"}]}}
            )
        with self.assertRaisesRegex(builder.BuildError, "timeout"):
            builder.DeviceClient._unwrap_response({"error": "timeout"})
        with self.assertRaisesRegex(builder.BuildError, "no text result"):
            builder.DeviceClient._unwrap_response({"result": {"isError": False, "content": []}})
        with self.assertRaisesRegex(builder.BuildError, "non-string"):
            builder.DeviceClient._unwrap_response(
                {"result": {"isError": False, "content": [{"type": "text", "text": {"bad": "shape"}}]}}
            )
        self.assertIsNone(builder.NoRedirect().redirect_request(None, None, 302, "", {}, "http://8.8.8.8/"))


class MockDeviceHandler(BaseHTTPRequestHandler):
    requests = []
    elements = []
    fail = False

    def do_GET(self):
        encoded = json.dumps({"status": "ok", "board": "mock-epaper", "version": "test"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length))
        type(self).requests.append(payload)
        tool = payload.get("tool")
        args = payload.get("args", {})
        if tool == "fridge.page.control" and args.get("action") == "list":
            inner = [{"page": 7, "name": "Test", "builtin": False}]
        elif tool in ("fridge.canvas.control", "fridge.page.element.control") and args.get("action") == "list":
            inner = [dict(item) for item in type(self).elements]
        else:
            if args.get("action") == "clear":
                type(self).elements = []
            elif args.get("action") == "add" or str(args.get("action", "")).startswith("add_"):
                item = dict(args)
                item["type"] = item.get("type") or item["action"].removeprefix("add_")
                for key in ("action", "page", "refresh", "x", "y"):
                    if item.get("type") == "line" or key not in ("x", "y"):
                        item.pop(key, None)
                type(self).elements.append(item)
            inner = {"status": "success"}
        body = (
            {"error": "forced failure"}
            if type(self).fail
            else {
                "result": {
                    "isError": False,
                    "content": [{"type": "text", "text": json.dumps(inner)}],
                }
            }
        )
        encoded = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, *_):
        pass


class HttpIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), MockDeviceHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        MockDeviceHandler.requests = []
        MockDeviceHandler.elements = []
        MockDeviceHandler.fail = False

    def test_real_http_round_trip_and_error(self):
        client = builder.DeviceClient("127.0.0.1", port=self.server.server_port, timeout=1)
        result = client.call("fridge.canvas.control", {"action": "refresh"})
        self.assertEqual(result["status"], "success")
        self.assertEqual(MockDeviceHandler.requests[0]["tool"], "fridge.canvas.control")
        MockDeviceHandler.fail = True
        with self.assertRaisesRegex(builder.BuildError, "forced failure"):
            client.call("fridge.canvas.control", {"action": "refresh"})

    def test_todo_template_end_to_end_with_mock_device_and_hostile_text(self):
        env = dict(os.environ, XIAOZHI_PORT=str(self.server.server_port))
        hostile_text = '引号 " 与 $(不会执行) ; <tag>'
        result = subprocess.run(
            [
                "bash", os.path.join(ROOT, "templates", "todo-list-page.sh"),
                "127.0.0.1", "7", hostile_text, "第二项", "第三项",
            ],
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        text_calls = [
            request for request in MockDeviceHandler.requests
            if request.get("tool") == "fridge.page.element.control"
            and request.get("args", {}).get("id") == "item1"
        ]
        self.assertEqual(text_calls[0]["args"]["text"], hostile_text)


class QuoteTests(unittest.TestCase):
    def test_rolling_window_uses_days_argument(self):
        now = datetime.datetime(2026, 9, 6, 12, 0, 0)
        with tempfile.TemporaryDirectory() as directory:
            history = os.path.join(directory, "history.jsonl")
            entries = [
                {"ts": "2026-09-01 08:00:00", "text": "fresh"},
                {"ts": "2026-08-01 08:00:00", "text": "old"},
                {"ts": "not-a-date", "text": "broken"},
            ]
            with open(history, "w", encoding="utf-8") as handle:
                for entry in entries:
                    handle.write(json.dumps(entry) + "\n")
            with mock.patch.object(quote_fetcher, "HIST", history):
                self.assertEqual(quote_fetcher.recent_texts(14, now=now), {"fresh"})

    def test_source_separator_is_firmware_safe(self):
        source = quote_fetcher.fmt_source("素材池", "哲学")
        self.assertEqual(source, "素材池-哲学")
        self.assertNotIn("・", source)


class UtilityTests(unittest.TestCase):
    def test_pixel_art_is_row_padded_1bpp(self):
        bitmap = pixel_art_generator.to_bitmap(pixel_art_generator.ARTISTS["heart"]())
        self.assertEqual(len(bitmap), 3 * 24)


class DiscoveryTests(unittest.TestCase):
    def test_linux_interface_parser_ignores_malformed_entries(self):
        outputs = [mock.Mock(stdout='[null,{"ifname":"eth0","addr_info":[null]}]'), mock.Mock(stdout="")]
        with mock.patch.object(discovery.subprocess, "run", side_effect=outputs):
            with mock.patch.object(discovery.socket, "socket", side_effect=OSError("offline")):
                self.assertEqual(discovery.local_networks(), [])

    def test_subnet_boundaries(self):
        self.assertEqual(str(discovery.parse_networks(["192.168.40.7/27"])[0]), "192.168.40.0/27")
        with self.assertRaisesRegex(ValueError, "private/local"):
            discovery.parse_networks(["8.8.8.0/24"])
        with self.assertRaisesRegex(ValueError, "private/local"):
            discovery.parse_networks(["192.0.2.0/24"])
        with self.assertRaisesRegex(ValueError, "allow-large-scan"):
            discovery.parse_networks(["10.0.0.0/19"])
        with self.assertRaisesRegex(ValueError, "hard safety limit"):
            discovery.parse_networks(["10.0.0.0/8"], allow_large_scan=True)
        with self.assertRaisesRegex(ValueError, "combined subnets"):
            discovery.parse_networks(["192.168.0.0/20", "192.168.16.0/20"])

    def test_cache_filters_public_and_malformed_addresses(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "device-cache")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("192.168.1.2\n8.8.8.8\nnot-an-ip\n")
            self.assertEqual(discovery.read_cache(path), ["192.168.1.2"])

    def test_macos_ifconfig_preserves_real_prefix(self):
        output = """en0: flags=8863<UP> mtu 1500
\tinet 192.168.32.17 netmask 0xfffff000 broadcast 192.168.47.255
lo0: flags=8049<UP> mtu 16384
\tinet 127.0.0.1 netmask 0xff000000
"""
        self.assertEqual([str(item) for item in discovery.networks_from_ifconfig(output)], ["192.168.32.0/20"])

    def test_broad_automatic_network_is_bounded_to_local_24(self):
        network = discovery.bounded_local_network(
            "10.20.30.40", discovery.ipaddress.ip_network("10.0.0.0/8")
        )
        self.assertEqual(str(network), "10.20.30.0/24")

    def test_scan_deduplicates_overlaps_and_excludes_known_hosts(self):
        calls = []

        def healthy(address, *_):
            calls.append(address)
            return {"status": "ok", "board": "mock"}

        networks = discovery.parse_networks(["192.168.1.0/30", "192.168.1.2/31"])
        with mock.patch.object(discovery, "try_health", side_effect=healthy):
            found = discovery.scan_networks(networks, workers=1, exclude={"192.168.1.1"})
        self.assertEqual(calls.count("192.168.1.2"), 1)
        self.assertNotIn("192.168.1.1", calls)
        self.assertEqual(set(found), {"192.168.1.2", "192.168.1.3"})

    def test_health_isolates_malformed_http(self):
        with mock.patch.object(discovery.HEALTH_OPENER, "open", side_effect=http.client.BadStatusLine("bad")):
            self.assertIsNone(discovery.try_health("127.0.0.1"))
        self.assertIsNone(discovery.NoRedirect().redirect_request(None, None, 302, "", {}, "http://8.8.8.8/"))

    def test_workers_reach_discovery(self):
        with mock.patch.object(discovery, "discover", return_value={"192.168.1.2": {"status": "ok", "board": "mock"}}) as called:
            with mock.patch("sys.stdout", new=io.StringIO()):
                self.assertEqual(discovery.main(["--subnet", "192.168.1.0/30", "--workers", "1"]), 0)
        self.assertEqual(called.call_args.kwargs["workers"], 1)

    def test_macos_dnssd_browse_resolves_xiaozhi_service(self):
        browse = "20:10:00 Add 2 4 local. _http._tcp. xiaozhi-kitchen\n"
        lookup = "xiaozhi-kitchen._http._tcp.local. can be reached at xiaozhi-kitchen.local.:8080\n"
        address = (discovery.socket.AF_INET, discovery.socket.SOCK_STREAM, 6, "", ("192.168.1.8", 8080))
        with mock.patch.object(discovery, "_bounded_command_output", side_effect=[browse, lookup]):
            with mock.patch.object(discovery, "resolve_ipv4", return_value=["192.168.1.8"]):
                self.assertEqual(discovery.resolve_dnssd_candidates(), ["192.168.1.8"])


class DeploymentTests(unittest.TestCase):
    def test_first_deploy_creates_target_and_removes_only_managed_stale_files(self):
        with tempfile.TemporaryDirectory() as directory:
            target = os.path.join(directory, "nested", "skill")
            os.makedirs(os.path.join(target, "scripts"))
            with open(os.path.join(target, "scripts", "stale.py"), "w", encoding="utf-8") as handle:
                handle.write("stale")
            with open(os.path.join(target, "scripts", "keep.bin"), "w", encoding="utf-8") as handle:
                handle.write("unmanaged")
            env = dict(os.environ, XIAOZHI_SKILL_DIR=target)
            result = subprocess.run(
                ["bash", os.path.join(ROOT, "deploy.sh")],
                env=env,
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(os.path.exists(os.path.join(target, "SKILL.md")))
            self.assertTrue(os.path.exists(os.path.join(target, "requirements-optional.txt")))
            self.assertFalse(os.path.exists(os.path.join(target, "scripts", "stale.py")))
            self.assertTrue(os.path.exists(os.path.join(target, "scripts", "keep.bin")))

    def test_deploy_refuses_symlink_targets(self):
        with tempfile.TemporaryDirectory() as directory:
            target = os.path.join(directory, "skill")
            outside = os.path.join(directory, "outside")
            os.makedirs(target)
            os.makedirs(outside)
            os.symlink(outside, os.path.join(target, "scripts"))
            env = dict(os.environ, XIAOZHI_SKILL_DIR=target)
            result = subprocess.run(
                ["bash", os.path.join(ROOT, "deploy.sh")],
                env=env,
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertEqual(result.returncode, 2)
            self.assertEqual(os.listdir(outside), [])


class LegacyTemplateTests(unittest.TestCase):
    def test_legacy_template_rejects_non_canvas_commands_before_network(self):
        invalid_commands = [
            '{"tool":"fridge.item.clear_all","args":{}}',
            '{"tool":"fridge.canvas.add_rect","args":{"id":"r","x":290,"y":0,"w":7,"h":1,"refresh":false}}',
        ]
        for command in invalid_commands:
            with self.subTest(command=command), tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", delete=False
            ) as handle:
                handle.write(command + "\n")
                path = handle.name
            try:
                result = subprocess.run(
                    ["bash", os.path.join(ROOT, "templates", "legacy_canvas_push.sh"), "127.0.0.1", path],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                self.assertEqual(result.returncode, 2)
                self.assertIn("invalid legacy layout", result.stderr)
            finally:
                os.unlink(path)


if __name__ == "__main__":
    unittest.main()
