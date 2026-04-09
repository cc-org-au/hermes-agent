"""Tests for agent.turn_done_notify."""

import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import patch

import pytest

from agent.turn_done_notify import maybe_notify_turn_done


class _Ok(BaseHTTPRequestHandler):
    hits = 0

    def do_GET(self):
        _Ok.hits += 1
        self.send_response(204)
        self.end_headers()

    def log_message(self, *args):
        pass


def test_notify_skips_delegate_child():
    _Ok.hits = 0
    with HTTPServer(("127.0.0.1", 0), _Ok) as srv:
        port = srv.server_port
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        time.sleep(0.05)
        url = f"http://127.0.0.1:{port}/"
        with patch.dict("os.environ", {"HERMES_TURN_DONE_NOTIFY_URL": url}):
            parent = type("A", (), {"_delegate_depth": 0})()
            maybe_notify_turn_done(agent=parent, final_response="ok", interrupted=False)
            child = type("A", (), {"_delegate_depth": 1})()
            maybe_notify_turn_done(agent=child, final_response="ok", interrupted=False)
        deadline = time.time() + 2.0
        while time.time() < deadline and _Ok.hits < 1:
            time.sleep(0.05)
        srv.shutdown()
    assert _Ok.hits == 1


def test_notify_skips_interrupted():
    _Ok.hits = 0
    with HTTPServer(("127.0.0.1", 0), _Ok) as srv:
        port = srv.server_port
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        time.sleep(0.05)
        with patch.dict("os.environ", {"HERMES_TURN_DONE_NOTIFY_URL": f"http://127.0.0.1:{port}/"}):
            agent = type("A", (), {"_delegate_depth": 0})()
            maybe_notify_turn_done(agent=agent, final_response="x", interrupted=True)
        time.sleep(0.2)
        srv.shutdown()
    assert _Ok.hits == 0


def test_notify_skips_empty_url():
    agent = type("A", (), {"_delegate_depth": 0})()
    with patch.dict("os.environ", {"HERMES_TURN_DONE_NOTIFY_URL": ""}), patch(
        "agent.turn_done_notify._merge_hermes_env_files",
        return_value={},
    ):
        maybe_notify_turn_done(agent=agent, final_response="ok", interrupted=False)
    # no crash
