"""Tests for core.http against a throwaway local server: retries, robots.txt, rate limit."""
from __future__ import annotations

import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.http import PoliteSession, RateLimiter, RobotsDisallowed  # noqa: E402


class Handler(BaseHTTPRequestHandler):
    flaky_hits = 0

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/robots.txt":
            self._send(200, b"User-agent: *\nDisallow: /private/\n")
        elif self.path == "/flaky":
            Handler.flaky_hits += 1
            if Handler.flaky_hits < 3:
                self._send(503, b"busy")
            else:
                self._send(200, b'{"ok": true}')
        elif self.path == "/missing":
            self._send(404, b"nope")
        else:
            self._send(200, b"hello")

    def _send(self, status: int, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:  # keep test output quiet
        pass


@pytest.fixture()
def server() -> str:
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def test_retries_then_succeeds(server: str) -> None:
    Handler.flaky_hits = 0
    with PoliteSession("test-bot/1.0", min_interval=0, backoff_factor=0.01) as http:
        assert http.get_json(f"{server}/flaky") == {"ok": True}
    assert Handler.flaky_hits == 3


def test_robots_disallow_blocks_request(server: str) -> None:
    with PoliteSession("test-bot/1.0", min_interval=0) as http:
        assert http.get(f"{server}/public").text == "hello"
        with pytest.raises(RobotsDisallowed):
            http.get(f"{server}/private/page")


def test_http_errors_raise(server: str) -> None:
    import requests

    with PoliteSession("test-bot/1.0", min_interval=0) as http:
        with pytest.raises(requests.HTTPError):
            http.get(f"{server}/missing")


def test_rate_limiter_spaces_calls() -> None:
    limiter = RateLimiter(0.2)
    start = time.monotonic()
    for _ in range(3):
        limiter.wait()
    assert time.monotonic() - start >= 0.37  # 2 gaps of 0.2s, minus Windows timer granularity


def test_empty_user_agent_rejected() -> None:
    with pytest.raises(ValueError):
        PoliteSession("  ")


def test_robots_wildcards_and_longest_match() -> None:
    from core.http import RobotsRules

    # The real Hacker News API robots.txt (Firebase): only *.json paths are allowed.
    rules = RobotsRules.parse("User-agent: *\nAllow: /*.json$\nAllow: /*.json?*$\nDisallow: /\n", "my-bot/1.0")
    assert rules.can_fetch("https://hacker-news.firebaseio.com/v0/topstories.json")
    assert rules.can_fetch("https://hacker-news.firebaseio.com/v0/item/1.json?print=pretty")
    assert not rules.can_fetch("https://hacker-news.firebaseio.com/v0/")

    rules = RobotsRules.parse(
        "User-agent: otherbot\nDisallow: /\n\nUser-agent: *\nDisallow: /search\nAllow: /search/about\nCrawl-delay: 3\n",
        "my-bot/1.0",
    )
    assert rules.can_fetch("https://x.test/books")
    assert not rules.can_fetch("https://x.test/search?q=1")
    assert rules.can_fetch("https://x.test/search/about")
    assert rules.crawl_delay == 3.0

    specific = RobotsRules.parse("User-agent: *\nDisallow: /\n\nUser-agent: my-bot\nAllow: /\n", "my-bot/1.0")
    assert specific.can_fetch("https://x.test/anything")
