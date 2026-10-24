"""2.5.2.4 contracts: editable registry, restored widths, voice URL-only HTTP."""
import contextlib
import io
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

from test_skill import FakeClient, builder
import xiaozhi


class PageContractTests(unittest.TestCase):
    def test_all_custom_page_numbers_use_registry_and_generic_tools(self):
        for page in (2, 3, 5, 6, 15):
            with self.subTest(page=page):
                client = FakeClient(pages=[{"page": page, "builtin": False}])
                builder.build_page(client, page, 'clear\ntext id=t text=hello x=10 y=8 max_width=120\nrefresh', output=lambda _: None)
                self.assertEqual(client.calls[0], ("fridge.page.control", {"action": "list"}))
                self.assertFalse(any(tool.startswith("fridge.canvas") for tool, _ in client.calls))
                added = next(args for _, args in client.calls if args.get("action") == "add")
                self.assertEqual(added["max_width"], 120)
                self.assertEqual(added["page"], page)
                self.assertEqual(client.calls[-1], ("fridge.pagemanager", {"target_page": page}))

    def test_read_only_or_missing_pages_never_mutate(self):
        for page, pages in [(1, []), (2, []), (6, []), (2, [{"page":2,"builtin":True}])]:
            client = FakeClient(pages=pages)
            with self.assertRaises(builder.BuildError):
                builder.build_page(client, page, 'clear\nrefresh', output=lambda _: None)
            self.assertTrue(all(args == {"action":"list"} for _, args in client.calls))

    def test_snapshot_restores_clock_width_and_ordinary_empty_dtype(self):
        client = FakeClient()
        client.elements = [
            {"type":"text","id":"clock","text":"12:34","x":140,"y":4,"font_size":56,"max_width":150,"align":"center","dtype":"clock"},
            {"type":"text","id":"title","text":"hello","x":10,"y":85,"font_size":12,"max_width":120,"dtype":""}]
        snapshot = builder.snapshot_page(client, 2)
        builder.restore_page(client, 2, snapshot)
        written = [args for _, args in client.calls if args.get("action") == "add"]
        self.assertEqual(written[0]["max_width"], 150)
        self.assertEqual(written[0]["dynamic_type"], "clock")
        self.assertNotIn("dynamic_type", written[1])
        self.assertEqual(written[1]["max_width"], 120)

    def test_clock_without_legacy_dynamic_flag_on_page_six(self):
        commands = builder.parse_layout('text id=c text="--:--" x=10 y=5 font_size=56 dynamic_type=clock max_width=150', 6)
        self.assertEqual(commands[0][1]["dynamic_type"], "clock")

    def test_invalid_voice_url_is_rejected_before_connecting(self):
        for url in ('', 'https://example.org', 'wss://user:pass@example.org/', 'wss://example.org/#secret', 'wss://example.org/\n', 'wss://example.org:99999/', 'wss://example.org/'+'a'*512):
            with self.subTest(url=url), mock.patch.object(xiaozhi, 'DeviceClient') as factory:
                with self.assertRaises((builder.BuildError, ValueError)):
                    xiaozhi.main(['192.168.1.12','voice','--url',url])
                factory.assert_not_called()


class VoiceHttpTests(unittest.TestCase):
    def test_cli_reads_and_writes_only_url_without_reboot(self):
        requests = []
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                requests.append(('GET', self.path, None))
                self.respond({"status":"ok","board":"test","version":"2.5.2.4"} if self.path=='/' else {"url":"wss://old.example/voice"})
            def do_POST(self):
                body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                requests.append(('POST',self.path,body));self.respond(body)
            def respond(self, body):
                data=json.dumps(body).encode();self.send_response(200);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
            def log_message(self, *args): pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            prefix=['127.0.0.1','--port',str(server.server_port),'voice']
            with contextlib.redirect_stdout(io.StringIO()) as output:
                xiaozhi.main(prefix)
            self.assertEqual(json.loads(output.getvalue()),{"url":"wss://old.example/voice"})
            with contextlib.redirect_stdout(io.StringIO()):
                xiaozhi.main(prefix+['--url','wss://next.example/voice'])
            self.assertEqual(requests,[('GET','/',None),('GET','/api/websocket_url',None),('GET','/',None),('POST','/api/websocket_url',{'url':'wss://next.example/voice'})])
        finally:
            server.shutdown();server.server_close();thread.join()
