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


def test_urls_and_options_from_env_vars():
    environ = {
        "APP_HEALTH_URLS": "http://a.test/, http://b.test/",
        "APP_HEALTH_TIMEOUT": "2.5",
        "APP_HEALTH_OK_CODES": "200,204",
        "APP_HEALTH_INSECURE": "true",
        "APP_HEALTH_INTERVAL": "30",
    }
    args = app_health.parse_args([], environ)
    assert args.urls == ["http://a.test/", "http://b.test/"]
    assert args.timeout == 2.5
    assert app_health.parse_codes(args.ok_codes) == {200, 204}
    assert args.insecure is True
    assert args.interval == 30


def test_urls_on_the_command_line_win_over_env():
    args = app_health.parse_args(["http://c.test/"], {"APP_HEALTH_URLS": "http://a.test/"})
    assert args.urls == ["http://c.test/"]


def test_no_urls_at_all_is_an_error():
    with pytest.raises(SystemExit):
        app_health.parse_args([], {})


def test_results_go_to_the_log_file(server, tmp_path):
    log_file = tmp_path / "app.log"
    assert app_health.main(["--log-file", str(log_file), server + "/ok"]) == 0
    assert "UP" in log_file.read_text()
