import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app_health  # noqa: E402


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        code = {"/ok": 200, "/missing": 404, "/broken": 500}.get(self.path, 200)
        self.send_response(code)
        self.end_headers()
        self.wfile.write(b"hello")

    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def server():
    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()


def test_200_is_up(server):
    r = app_health.check_url(server + "/ok")
    assert r["status"] == "UP" and r["code"] == 200


def test_404_and_500_are_down(server):
    assert app_health.check_url(server + "/missing")["status"] == "DOWN"
    assert app_health.check_url(server + "/broken")["status"] == "DOWN"


def test_custom_ok_codes(server):
    assert app_health.check_url(server + "/missing", ok_codes={404})["status"] == "UP"


def test_connection_refused_is_down():
    r = app_health.check_url("http://127.0.0.1:1/", timeout=1)
    assert r["status"] == "DOWN" and r["code"] is None


def test_main_exit_codes(server, capsys):
    assert app_health.main([server + "/ok"]) == 0
    assert app_health.main([server + "/ok", server + "/broken"]) == 1
    out = capsys.readouterr().out
    assert "UP" in out and "DOWN" in out
