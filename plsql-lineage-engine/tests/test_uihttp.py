"""Loopback UI HTTP: engine.json, focus, SSE, invoke."""

from __future__ import annotations

import json
import pathlib
import threading
import unittest
import urllib.error
import urllib.request

from plsqllineage.focus import digest_file
from plsqllineage.serve import LineageSession, main as serve_main
from plsqllineage.uihttp import (
    make_ui_http,
    parse_bind,
    start_ui_thread,
    stop_ui_http,
)

ROOT = pathlib.Path(__file__).resolve().parent
FIXTURE = ROOT / "fixtures" / "engine_sample.json"


class BindTests(unittest.TestCase):
    def test_port_only(self):
        self.assertEqual(parse_bind("8765"), ("127.0.0.1", 8765))

    def test_loopback(self):
        self.assertEqual(parse_bind("127.0.0.1:9000"), ("127.0.0.1", 9000))
        self.assertEqual(parse_bind("localhost:9000"), ("127.0.0.1", 9000))

    def test_rejects_wildcard(self):
        with self.assertRaises(ValueError):
            parse_bind("0.0.0.0:8765")


class UiHttpTests(unittest.TestCase):
    def setUp(self):
        self.session = LineageSession(FIXTURE)
        self.httpd = make_ui_http(self.session, "127.0.0.1", 0)
        start_ui_thread(self.httpd)
        self.port = self.httpd.server_address[1]
        self.base = f"http://127.0.0.1:{self.port}"

    def tearDown(self):
        stop_ui_http(self.httpd)

    def _get(self, path: str, timeout: float = 3) -> tuple[int, bytes, str]:
        req = urllib.request.Request(self.base + path)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read(), resp.headers.get("Content-Type", "")

    def _post(self, path: str, payload: dict, timeout: float = 3) -> tuple[int, bytes]:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.base + path, data=data,
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()

    def test_engine_json_matches_file(self):
        status, body, ctype = self._get("/engine.json")
        self.assertEqual(status, 200)
        self.assertIn("json", ctype)
        self.assertEqual(body, FIXTURE.read_bytes())
        self.assertEqual(
            "sha256:" + __import__("hashlib").sha256(body).hexdigest(),
            digest_file(FIXTURE),
        )

    def test_cors_on_focus(self):
        req = urllib.request.Request(self.base + "/focus")
        with urllib.request.urlopen(req, timeout=3) as resp:
            self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), "*")
            payload = json.loads(resp.read())
        self.assertEqual(payload["columns"], [])

    def test_invoke_query_updates_focus(self):
        status, body = self._post("/invoke", {
            "tool": "query_lineage",
            "column": "OUT_ALLOC.ORD_QTY",
        })
        self.assertEqual(status, 200)
        text = body.decode("utf-8")
        self.assertIn("EDGE DIRECT", text)
        _, focus_body, _ = self._get("/focus")
        focus = json.loads(focus_body)
        self.assertEqual(focus["tool"], "query_lineage")
        self.assertEqual(focus["seed"], "SYNWMS.OUT_ALLOC.ORD_QTY")
        self.assertEqual(focus["graph"], digest_file(FIXTURE))
        self.assertTrue(focus["columns"])
        self.assertTrue(focus["edges"])

    def test_invoke_unknown_tool(self):
        data = json.dumps({"tool": "nope"}).encode("utf-8")
        req = urllib.request.Request(
            self.base + "/invoke", data=data,
            headers={"Content-Type": "application/json"}, method="POST")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=3)
        self.assertEqual(ctx.exception.code, 400)

    def test_sse_emits_current_focus(self):
        self.session.query_lineage("IF_STOCK_SND.QTY")
        got = []

        def read_one():
            req = urllib.request.Request(self.base + "/events")
            with urllib.request.urlopen(req, timeout=4) as resp:
                buf = b""
                while b"event: focus" not in buf:
                    chunk = resp.read(128)
                    if not chunk:
                        break
                    buf += chunk
                got.append(buf)

        thread = threading.Thread(target=read_one)
        thread.start()
        thread.join(timeout=5)
        self.assertTrue(got)
        payload = got[0].decode("utf-8")
        self.assertIn("event: focus", payload)
        self.assertIn("IF_STOCK_SND.QTY", payload)


class ServeCliUiTests(unittest.TestCase):
    def test_ui_only_requires_ui(self):
        self.assertEqual(serve_main(["--ui-only"]), 1)

    def test_rejects_non_loopback(self):
        self.assertEqual(
            serve_main(["--input", str(FIXTURE), "--ui", "0.0.0.0:8765"]), 1)


if __name__ == "__main__":
    unittest.main()
