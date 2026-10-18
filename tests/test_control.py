"""Cross-platform regression tests for discovery and serial display submission."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import crash_log
import install_skill
import legacy_canvas_push
import quick_page_builder as builder
import xiaozhi
import xiaozhi_discovery as discovery
from test_skill import FakeClient


class DisplayTests(unittest.TestCase):
    def test_early_switch_and_final_refresh_present_exactly_once_after_readback(self):
        client = FakeClient()
        builder.build_page(client, 6, 'switch 6\nclear\ntext id=t text=hello x=16 y=16\nrefresh', output=lambda _: None)
        presentations = [(i, args) for i, (tool, args) in enumerate(client.calls) if tool == "fridge.pagemanager"]
        self.assertEqual(presentations, [(len(client.calls)-1, {"target_page": 6})])
        self.assertEqual(client.calls[-2], ("fridge.canvas.control", {"action": "list"}))
        self.assertTrue(all(args.get("refresh") is False for _, args in client.calls if args.get("action") in ("clear", "add_text")))

    def test_no_presentation_when_staging_only(self):
        client = FakeClient()
        builder.build_page(client, 6, 'text id=t text=hello x=16 y=16', output=lambda _: None)
        self.assertFalse(any(tool == "fridge.pagemanager" for tool, _ in client.calls))
        self.assertEqual(client.calls[-1][1], {"action": "list"})

    def test_mismatching_switch_rejected_before_network(self):
        client = FakeClient()
        with self.assertRaises(builder.BuildError):
            builder.build_page(client, 6, 'switch 5\nclear\nrefresh')
        self.assertEqual(client.calls, [])

    def test_wrong_text_detected_and_previous_content_restored_without_show(self):
        class CorruptClient(FakeClient):
            def call(self, tool, args):
                result = super().call(tool, args)
                if args.get("id") == "new" and args.get("action") == "add_text":
                    self.elements[-1]["text"] = "truncated"
                return result
        client = CorruptClient()
        original = {"type": "text", "id": "old", "text": "saved", "x": 8, "y": 8}
        client.elements = [dict(original)]
        with self.assertRaisesRegex(builder.BuildError, "readback mismatch"):
            builder.build_page(client, 6, 'clear\ntext id=new text=hello x=8 y=8\nrefresh', output=lambda _: None)
        self.assertEqual(client.elements, [original])
        self.assertFalse(any(tool == "fridge.pagemanager" for tool, _ in client.calls))

    def test_ambiguous_write_does_not_retry_clear_or_rollback(self):
        class TimeoutClient(FakeClient):
            def call(self, tool, args):
                result = super().call(tool, args)
                if args.get("action") == "add_text":
                    raise builder.AmbiguousMutationError("response lost after write")
                return result
        client = TimeoutClient()
        with self.assertRaises(builder.AmbiguousMutationError):
            builder.build_page(client, 6, 'clear\ntext id=t text=hello x=8 y=8\nrefresh', output=lambda _: None)
        self.assertEqual([args.get("action") for _, args in client.calls], ["list", "clear", "add_text"])
        self.assertEqual(client.elements[0]["text"], "hello")

    def test_backup_survives_ambiguous_clear(self):
        class TimeoutClient(FakeClient):
            def call(self, tool, args):
                result = super().call(tool, args)
                if args.get("action") == "clear":
                    raise builder.AmbiguousMutationError("timeout")
                return result
        client = TimeoutClient()
        client.elements = [{"type": "text", "id": "old", "text": "saved", "x": 8, "y": 8}]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "before.json"
            with self.assertRaises(builder.AmbiguousMutationError):
                builder.build_page(client, 6, 'clear\nrefresh', backup_path=path, output=lambda _: None)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["elements"][0]["text"], "saved")

    def test_live_dynamic_text_does_not_fail_verification(self):
        class DynamicClient(FakeClient):
            def call(self, tool, args):
                result = super().call(tool, args)
                if args.get("action") == "add":
                    self.elements[-1]["dtype"] = self.elements[-1].pop("dynamic_type")
                    self.elements[-1]["text"] = "22:48"
                return result
        builder.build_page(DynamicClient(), 7,
                           'text id=t text="--:--" x=10 y=4 font_size=56 dynamic=true dynamic_type=clock\nrefresh',
                           output=lambda _: None)

    def test_bitmap_size_mismatch_prevents_clear(self):
        client = FakeClient()
        client.images = [{"name": "art", "size": 72}]
        with self.assertRaisesRegex(builder.BuildError, "size mismatch"):
            builder.build_page(client, 6, 'clear\nimage id=i name=art x=8 y=8 w=32 h=32\nrefresh')
        self.assertEqual(client.calls, [])

    def test_text_and_ids_preserve_numeric_and_boolean_strings(self):
        for value in ("123", "true", "false"):
            commands = builder.parse_layout(f'text id=123 text="{value}" x=8 y=8', 6)
            self.assertEqual(commands[0][1]["text"], value)
            self.assertEqual(commands[0][1]["id"], "123")

    def test_image_names_do_not_alias_or_overwrite_layout_files(self):
        for name in ("layout.json", "custom_pages.json", "page_7.json", "a-b"):
            self.assertFalse(builder.valid_image_name(name))
        self.assertTrue(builder.valid_image_name("picture.bin"))

    def test_builtin_pixel_art_cannot_be_resized_by_metadata(self):
        with self.assertRaisesRegex(builder.BuildError, "24x24"):
            builder.parse_layout('pixart id=i art=heart x=8 y=8 w=48 h=48', 6)

    def test_legacy_jsonl_uses_same_single_presentation_contract(self):
        raw = json.dumps({"tool":"fridge.canvas.add_text", "args":{"id":"t", "text":"hello ' world", "x":8,"y":8}})
        client = FakeClient()
        builder.build_page(client, 6, legacy_canvas_push.convert(raw), output=lambda _: None)
        self.assertEqual(sum(tool == "fridge.pagemanager" for tool, _ in client.calls), 1)
        self.assertEqual(client.elements[0]["text"], "hello ' world")


class DiscoveryTests(unittest.TestCase):
    def test_valid_cache_avoids_mdns_and_scan(self):
        with mock.patch.object(discovery, "cached_addresses", return_value=["192.168.1.8"]), \
             mock.patch.object(discovery, "try_health", return_value={"status":"ok","board":"epaper"}) as health, \
             mock.patch.object(discovery, "resolve_mdns_candidates") as mdns, \
             mock.patch.object(discovery, "scan_networks") as scan:
            self.assertIn("192.168.1.8", discovery.discover([]))
            self.assertEqual(health.call_args.args[2], 3)
            mdns.assert_not_called()
            scan.assert_not_called()

    def test_explicit_subnet_never_selects_cached_device_elsewhere(self):
        with mock.patch.object(discovery, "cached_addresses", return_value=["192.168.2.8"]), \
             mock.patch.object(discovery, "try_health") as health, \
             mock.patch.object(discovery, "resolve_mdns_candidates", return_value=["192.168.2.8"]), \
             mock.patch.object(discovery, "udp_discover", return_value=[]), \
             mock.patch.object(discovery, "scan_networks", return_value={}):
            discovery.discover(discovery.parse_networks(["192.168.1.0/24"]), restrict_networks=True)
            health.assert_not_called()

    def test_linux_down_interface_is_not_scanned(self):
        records = [{"ifname":"docker0", "operstate":"DOWN", "addr_info":[{"family":"inet","scope":"global","local":"172.17.0.1","prefixlen":16}]},
                   {"ifname":"wlan0", "operstate":"UP", "addr_info":[{"family":"inet","scope":"global","local":"192.168.1.7","prefixlen":24}]}]
        with mock.patch.object(discovery.subprocess, "run", return_value=mock.Mock(stdout=json.dumps(records))):
            self.assertEqual([str(n) for n in discovery.local_networks()], ["192.168.1.0/24"])

    def test_known_device_read_retry_is_serial_and_bounded(self):
        with mock.patch.object(discovery, "cached_addresses", return_value=["192.168.1.8"]), \
             mock.patch.object(discovery, "try_health", side_effect=[None,{"status":"ok","board":"epaper"}]) as health:
            self.assertIn("192.168.1.8", discovery.discover([]))
            self.assertEqual(health.call_count, 2)

    def test_explicit_host_bypasses_interface_cache_and_scan(self):
        with mock.patch.object(discovery, "local_networks") as interfaces, \
             mock.patch.object(discovery, "cached_addresses") as cache, \
             mock.patch.object(discovery, "scan_networks") as scan, \
             mock.patch.object(discovery, "try_health", return_value={"status":"ok","board":"epaper","ip":"wrong"}), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(discovery.main(["--host","192.168.1.8","--json"]), 0)
            self.assertEqual(json.loads(output.getvalue())[0]["ip"], "192.168.1.8")
            interfaces.assert_not_called(); cache.assert_not_called(); scan.assert_not_called()

    def test_failed_discovery_json_remains_machine_readable(self):
        with mock.patch.object(discovery, "try_health", return_value=None), \
             contextlib.redirect_stdout(io.StringIO()) as output, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(discovery.main(["--host","192.168.1.8","--json"]), 1)
            self.assertEqual(json.loads(output.getvalue()), [])

    def test_dns_timeout_is_bounded(self):
        with mock.patch.object(discovery.subprocess, "run", side_effect=subprocess.TimeoutExpired("dns", 3)) as run:
            self.assertEqual(discovery.resolve_ipv4("xiaozhi.local"), [])
            self.assertEqual(run.call_args.kwargs["timeout"], 3)

    def test_all_scan_keeps_multiple_devices_and_does_not_reprobe_found_host(self):
        with mock.patch.object(discovery, "cached_addresses", return_value=["192.168.1.8"]), \
             mock.patch.object(discovery, "try_health", return_value={"status":"ok","board":"epaper"}), \
             mock.patch.object(discovery, "resolve_mdns_candidates", return_value=[]), \
             mock.patch.object(discovery, "udp_discover", return_value=[]), \
             mock.patch.object(discovery, "scan_networks", return_value={"192.168.1.9":{"status":"ok","board":"epaper"}}) as scan:
            result = discovery.discover([], all_devices=True)
            self.assertEqual(set(result), {"192.168.1.8","192.168.1.9"})
            self.assertIn("192.168.1.8", scan.call_args.kwargs["exclude"])
            self.assertEqual(scan.call_args.kwargs["timeout"], 2)

    def test_windows_json_interfaces_preserve_prefix_and_filter_public(self):
        records = [{"IPAddress":"192.168.12.5","PrefixLength":27},
                   {"IPAddress":"127.0.0.1","PrefixLength":8},
                   {"IPAddress":"8.8.8.8","PrefixLength":24}, None]
        self.assertEqual([str(n) for n in discovery.networks_from_windows(json.dumps(records))], ["192.168.12.0/27"])
        self.assertEqual([str(n) for n in discovery.networks_from_windows(json.dumps(records[0]))], ["192.168.12.0/27"])

    def test_windows_local_network_path_without_unix_commands(self):
        with mock.patch.object(discovery.sys, "platform", "win32"), \
             mock.patch.object(discovery, "_bounded_command_output", return_value='{"IPAddress":"192.168.12.5","PrefixLength":24}'), \
             mock.patch.object(discovery.subprocess, "run", side_effect=FileNotFoundError):
            self.assertEqual([str(n) for n in discovery.local_networks()], ["192.168.12.0/24"])

    def test_cache_override_is_agent_independent(self):
        with mock.patch.dict(os.environ, {"XIAOZHI_CACHE_FILE":"~/my-xiaozhi-cache"}):
            self.assertEqual(discovery.default_cache_file(), os.path.expanduser("~/my-xiaozhi-cache"))

    def test_legacy_cache_still_supplies_candidate(self):
        with mock.patch.object(discovery, "read_cache", side_effect=[[],["192.168.1.8"],[]]):
            self.assertEqual(discovery.cached_addresses(), ["192.168.1.8"])


class ControlCliTests(unittest.TestCase):
    def test_partial_home_config_is_rejected_before_contact(self):
        with mock.patch.object(xiaozhi, "DeviceClient") as client:
            with self.assertRaisesRegex(builder.BuildError, "both"):
                xiaozhi.main(["192.168.1.8","home","--page","5"])
            client.assert_not_called()

    def test_disable_home_return_preserves_zero(self):
        with mock.patch.object(xiaozhi, "DeviceClient") as client, contextlib.redirect_stdout(io.StringIO()):
            client.return_value.http_json.return_value = {"status":"ok","page":5,"timeout_min":0}
            xiaozhi.main(["192.168.1.8","home","--page","5","--timeout-min","0"])
            client.return_value.http_json.assert_called_once_with("/api/home_page", {"page":5,"timeout_min":0})
            client.return_value.call.assert_not_called()

    def test_mac_mismatch_prevents_write(self):
        with mock.patch.object(xiaozhi, "DeviceClient") as client:
            client.return_value.health.return_value = {"mac":"aa:bb:cc:dd:ee:ff"}
            with self.assertRaisesRegex(builder.BuildError, "MAC"):
                xiaozhi.main(["192.168.1.8","--expect-mac","00:11:22:33:44:55","show","6"])
            client.return_value.call.assert_not_called()

    def test_missing_custom_home_prevents_setting(self):
        with mock.patch.object(xiaozhi, "DeviceClient") as client:
            client.return_value.call.return_value = []
            with self.assertRaisesRegex(builder.BuildError, "does not exist"):
                xiaozhi.main(["192.168.1.8","home","--page","7","--timeout-min","2"])
            client.return_value.http_json.assert_not_called()

    def test_oversized_request_rejected_before_post(self):
        client = builder.DeviceClient("127.0.0.1")
        with mock.patch.object(builder.DEVICE_OPENER, "open") as request:
            with self.assertRaisesRegex(builder.BuildError, "4095"):
                client.call("tool", {"text":"字"*2000})
            request.assert_not_called()

    def test_malformed_success_response_cannot_trigger_automatic_rollback(self):
        for response in ({"result": None}, {"result":{"isError":False,"content":[]}},
                         {"result":{"content":[{"type":"text","text":"not JSON"}]}},
                         {"error":"cannot track response"}):
            with self.subTest(response=response), self.assertRaises(builder.AmbiguousMutationError):
                builder.DeviceClient._unwrap_response(response)

    def test_device_timeout_is_ambiguous(self):
        with self.assertRaises(builder.AmbiguousMutationError):
            builder.DeviceClient._unwrap_response({"error":"timeout"})


class SerialCaptureTests(unittest.TestCase):
    def test_default_capture_sets_lines_before_open_and_does_not_reset(self):
        events = []
        class Port:
            in_waiting = 0
            def __setattr__(self, key, value):
                events.append((key, value))
                object.__setattr__(self, key, value)
            def open(self): events.append(("open", self.port))
            def close(self): events.append(("close", None))
        serial = mock.Mock()
        serial.Serial.return_value = Port()
        with mock.patch.dict(sys.modules, {"serial": serial}), \
             mock.patch.object(crash_log.time, "monotonic", side_effect=[0, 2]), \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(crash_log.main(["COM3", "1"]), 0)
        serial.Serial.assert_called_once_with(port=None, baudrate=115200, timeout=0.3)
        self.assertEqual(events, [("dtr",False),("rts",False),("port","COM3"),("open","COM3"),("close",None)])


class InstallTests(unittest.TestCase):
    def test_native_install_and_cleanup_keep_unmanaged_files(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            target = Path(directory).resolve()/"skill"
            (target/"scripts").mkdir(parents=True)
            (target/"scripts"/"old.py").write_text("stale")
            (target/"notes.txt").write_text("keep")
            install_skill.install(target)
            self.assertTrue((target/"scripts"/"xiaozhi.py").exists())
            self.assertTrue((target/"templates"/"hello.layout").exists())
            self.assertFalse((target/"scripts"/"old.py").exists())
            self.assertEqual((target/"notes.txt").read_text(), "keep")

    def test_dry_run_creates_nothing(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            target = Path(directory).resolve()/"skill"
            install_skill.install(target, dry_run=True)
            self.assertFalse(target.exists())

    def test_overlapping_source_and_home_targets_rejected(self):
        for target in (install_skill.SOURCE, install_skill.SOURCE/"installed", Path.home()):
            with self.subTest(target=target), self.assertRaises(ValueError):
                install_skill.install(target, dry_run=True)


if __name__ == "__main__":
    unittest.main()
