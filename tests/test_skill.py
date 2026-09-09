import datetime
import http.client
import io
import json
import os
import re
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
import workflow_map
import workflow_snapshot
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
            "clear\nline id=sep x1=0 y1=10 x2=295 y2=10 width=1\nrefresh",
            output=lambda _: None,
        )
        self.assertEqual(client.calls[0], ("fridge.page.control", {"action": "list"}))
        self.assertEqual(client.calls[1], ("fridge.page.element.control", {"action": "list", "page": 7}))
        self.assertEqual(client.calls[2], ("fridge.page.control", {"action": "clear", "refresh": False, "page": 7}))
        tool, args = client.calls[3]
        self.assertEqual(tool, "fridge.page.element.control")
        self.assertEqual(args["action"], "add")
        self.assertEqual(args["type"], "line")
        self.assertEqual((args["x"], args["y"]), (0, 0))
        self.assertEqual(client.calls[4], ("fridge.pagemanager", {"target_page": 7}))

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
        self.assertEqual(client.calls[1], ("fridge.canvas.control", {"action": "refresh"}))

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
        inner = (
            [{"page": 7, "name": "Test", "builtin": False}]
            if payload.get("tool") == "fridge.page.control" and payload.get("args", {}).get("action") == "list"
            else []
            if payload.get("tool") in ("fridge.canvas.control", "fridge.page.element.control")
            and payload.get("args", {}).get("action") == "list"
            else {"status": "success"}
        )
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

    def test_cron_parser_rejects_dangerous_ranges(self):
        for expression in ("*/0 * * * *", "0 99 * * *", "0 20-10 * * *"):
            with self.subTest(expression=expression), self.assertRaises(ValueError):
                workflow_map.parse_cron(expression)

    def test_cron_parser_supports_steps_and_named_ranges(self):
        parsed = workflow_map.parse_cron("*/30 7-8 * * MON-FRI")
        self.assertEqual(parsed["minutes"], {0, 30})
        self.assertEqual(parsed["hours"], {7, 8})
        self.assertEqual(parsed["dow"], {1, 2, 3, 4, 5})


class WorkflowSnapshotTests(unittest.TestCase):
    def test_metadata_is_fixed_position_and_bounded(self):
        marker = "[XIAOZHI_CRON_META v1 page=7 mode=element-update]\nDo work"
        self.assertEqual(
            workflow_snapshot.parse_job_meta(marker),
            {"version": 1, "page": 7, "mode": "element-update"},
        )
        self.assertIsNone(workflow_snapshot.parse_job_meta("Do work\n" + marker))
        self.assertIsNone(workflow_snapshot.parse_job_meta("[XIAOZHI_CRON_META v1 page=16 mode=x]"))

    def test_snapshot_filters_and_redacts_job_secrets(self):
        jobs = [
            {
                "id": "screen",
                "name": "画布更新",
                "prompt": "[XIAOZHI_CRON_META v1 page=6 mode=canvas-refresh]\nsecret prompt",
                "skills": ["xiaozhi-control"],
                "origin": {"chat_id": "secret-chat"},
                "workdir": "/secret/path",
                "schedule": {"kind": "cron", "expr": "*/30 7-22 * * *"},
            },
            {"id": "other", "name": "unrelated", "prompt": "secret"},
        ]
        snapshot = workflow_snapshot.build_snapshot(jobs, [], {}, executions_path=None)
        self.assertEqual([job["id"] for job in snapshot["jobs"]], ["screen"])
        encoded = json.dumps(snapshot, ensure_ascii=False)
        self.assertNotIn("secret prompt", encoded)
        self.assertNotIn("secret-chat", encoded)
        self.assertNotIn("/secret/path", encoded)
        self.assertEqual(snapshot["jobs"][0]["target"]["confidence"], "explicit")

    def test_snapshot_strips_invalid_xml_unicode(self):
        snapshot = workflow_snapshot.build_snapshot(
            [{"id": "x", "name": "bad\ud800name", "skill": "xiaozhi-control"}],
            [{"ts": "2026-01-01T00:00:00", "text": "bad\ufffetext"}],
            {},
            executions_path=None,
        )
        svg = workflow_map.build(snapshot["jobs"], snapshot["history"], snapshot["device"])
        svg.encode("utf-8")
        self.assertNotIn("\ud800", svg)
        self.assertNotIn("\ufffe", svg)

    def test_execution_database_open_failure_is_nonfatal_warning(self):
        with mock.patch("workflow_snapshot.os.path.exists", return_value=True), \
             mock.patch("workflow_snapshot.os.path.islink", return_value=False), \
             mock.patch("workflow_snapshot.os.path.isfile", return_value=True), \
             mock.patch("workflow_snapshot.os.path.getsize", return_value=1024), \
             mock.patch("workflow_snapshot.sqlite3.connect", side_effect=workflow_snapshot.sqlite3.OperationalError("locked")):
            snapshot = workflow_snapshot.build_snapshot(
                [{"id": "x", "name": "画布", "skill": "xiaozhi-control"}], [], {}, executions_path="/tmp/executions.db"
            )
        self.assertIn("executions_unavailable", [item["code"] for item in snapshot["warnings"]])

    def test_partial_device_read_is_visible_as_warning(self):
        snapshot = workflow_snapshot.build_snapshot([], [], {"online": True, "partial": True}, executions_path=None)
        self.assertIn("device_partial", [item["code"] for item in snapshot["warnings"]])

    def test_device_content_is_not_rendered_in_compact_svg(self):
        device = {
            "online": True,
            "ip": "127.0.0.1",
            "pages": [{"page": 6, "name": "<script>alert(1)</script>", "builtin": True}],
            "elements": {6: [{"type": "text", "id": "x", "text": "<script>x</script>", "x": 0, "y": 0}]},
        }
        snapshot = workflow_snapshot.build_snapshot([], [], device, executions_path=None)
        svg = workflow_map.build(snapshot["jobs"], snapshot["history"], snapshot["device"])
        self.assertNotIn("<script>", svg)
        self.assertNotIn("&lt;script&gt;", svg)
        self.assertNotIn("当前屏幕", svg)

    def test_device_image_element_is_not_previewed(self):
        device = {
            "online": True,
            "ip": "192.168.1.9",
            "pages": [{"page": 6, "name": "Canvas", "builtin": True}],
            "elements": {6: [{"type": "image", "id": "icon", "name": "sun", "x": 1, "y": 2, "w": 24, "h": 24}]},
        }
        snapshot = workflow_snapshot.build_snapshot([], [], device, executions_path=None)
        svg = workflow_map.build(snapshot["jobs"], snapshot["history"], snapshot["device"])
        self.assertNotIn(">sun</text>", svg)
        self.assertNotIn("clipPath", svg)

    def test_dense_schedule_has_bounded_timeline_points(self):
        job = {
            "id": "dense", "name": "高频画布", "enabled": True,
            "schedule": {"kind": "cron", "expr": "* * * * *"},
            "target": {"page": 6, "confidence": "explicit", "mode": "canvas-refresh"},
        }
        svg = workflow_map.build([job], [], {"online": False, "ip": "", "pages": [], "elements": {}})
        self.assertIn(">高频</text>", svg)
        self.assertLessEqual(svg.count("<circle "), workflow_map.MAX_TIMELINE_POINTS_PER_JOB)

    def test_svg_uses_only_litsea_monochrome_and_brand_red(self):
        job = {
            "id": "x", "name": "提醒", "enabled": True, "last_status": "error",
            "schedule": {"kind": "cron", "expr": "0 8 * * *"},
            "target": {"page": 7, "confidence": "explicit", "mode": "element-update"},
        }
        svg = workflow_map.build([job], [], {"online": False}, warnings=[{"code": "device_offline"}])
        colors = set(re.findall(r"#[0-9A-Fa-f]{6}", svg))
        self.assertLessEqual(colors, set(workflow_map.COLOR.values()))
        self.assertIn("#FF5A5A", colors)

    def test_cli_writes_atomic_svg_and_json(self):
        with tempfile.TemporaryDirectory() as directory:
            jobs = os.path.join(directory, "jobs.json")
            history = os.path.join(directory, "history.jsonl")
            svg = os.path.join(directory, "map.svg")
            with open(jobs, "w", encoding="utf-8") as handle:
                json.dump({"jobs": [{"id": "x", "name": "画布", "skill": "xiaozhi-control", "prompt": "page 6"}]}, handle)
            with open(history, "w", encoding="utf-8") as handle:
                handle.write("{bad json}\n")
            with mock.patch("sys.stdout", new=io.StringIO()) as output:
                self.assertEqual(
                    workflow_map.main(["--jobs", jobs, "--history", history, "--executions", os.path.join(directory, "missing.db"), "--out", svg]),
                    0,
                )
            self.assertTrue(os.path.exists(svg))
            self.assertTrue(os.path.exists(os.path.splitext(svg)[0] + ".json"))
            self.assertIn("ARTIFACT_SVG=" + svg, output.getvalue())

    def test_invalid_registered_schedule_does_not_block_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            jobs = os.path.join(directory, "jobs.json")
            svg = os.path.join(directory, "map.svg")
            with open(jobs, "w", encoding="utf-8") as handle:
                json.dump({"jobs": [{
                    "id": "bad", "name": "坏调度画布", "skill": "xiaozhi-control",
                    "prompt": "page 6", "schedule": {"kind": "cron", "expr": "0 8 nope * *"},
                }]}, handle)
            self.assertEqual(workflow_map.main([
                "--jobs", jobs, "--history", os.path.join(directory, "missing"),
                "--executions", os.path.join(directory, "missing.db"), "--out", svg,
            ]), 0)
            with open(os.path.splitext(svg)[0] + ".json", encoding="utf-8") as handle:
                snapshot = json.load(handle)
            self.assertIn("invalid_schedule", [item["code"] for item in snapshot["warnings"]])

    def test_atomic_output_refuses_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            real = os.path.join(directory, "real.svg")
            link = os.path.join(directory, "link.svg")
            with open(real, "w", encoding="utf-8") as handle:
                handle.write("old")
            os.symlink(real, link)
            with self.assertRaisesRegex(ValueError, "symlink"):
                workflow_map.atomic_write_text(link, "new")
            with open(real, encoding="utf-8") as handle:
                self.assertEqual(handle.read(), "old")

    def test_preview_is_rendered_without_writing_scheduler_input(self):
        with tempfile.TemporaryDirectory() as directory:
            jobs = os.path.join(directory, "jobs.json")
            svg = os.path.join(directory, "preview.svg")
            with open(jobs, "w", encoding="utf-8") as handle:
                json.dump({"jobs": []}, handle)
            with open(jobs, "rb") as handle:
                original = handle.read()
            self.assertEqual(
                workflow_map.main([
                    "--jobs", jobs,
                    "--history", os.path.join(directory, "missing.jsonl"),
                    "--executions", os.path.join(directory, "missing.db"),
                    "--out", svg,
                    "--preview-name", "工作日提醒",
                    "--preview-schedule", "0 8 * * MON-FRI",
                    "--preview-page", "7",
                ]),
                0,
            )
            with open(jobs, "rb") as handle:
                self.assertEqual(handle.read(), original)
            with open(os.path.splitext(svg)[0] + ".json", encoding="utf-8") as handle:
                snapshot = json.load(handle)
            self.assertEqual(snapshot["jobs"][-1]["last_status"], "preview")
            self.assertEqual(snapshot["jobs"][-1]["target"]["page"], 7)
            self.assertNotIn("prompt", snapshot["jobs"][-1])

    def test_preview_requires_complete_valid_arguments(self):
        with self.assertRaisesRegex(ValueError, "必须一起提供"):
            workflow_map.main(["--preview-name", "incomplete"])
        with self.assertRaisesRegex(ValueError, "有效的 5 段"):
            workflow_map.main([
                "--preview-name", "bad", "--preview-schedule", "not cron", "--preview-page", "6"
            ])


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
            with mock.patch.object(discovery.socket, "getaddrinfo", return_value=[address]):
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
