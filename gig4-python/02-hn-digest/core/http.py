"""Polite HTTP client: retries with backoff, a rate limit, robots.txt checks and timeouts.

Usage:
    from core.http import PoliteSession
    http = PoliteSession(user_agent="my-bot/1.0", min_interval=1.0)
    html = http.get("https://books.toscrape.com/").text
    data = http.get_json("https://hacker-news.firebaseio.com/v0/topstories.json")

Retries: 429 and 5xx responses and connection errors are retried with exponential
backoff (1s, 2s, 4s, ...). A Retry-After header from the server is honoured.
Rate limit: at least `min_interval` seconds between requests (thread-safe). If
robots.txt sets a larger Crawl-delay for our user agent, that value wins.
robots.txt: a URL disallowed for our user agent raises RobotsDisallowed before any
request is sent. A missing robots.txt (404/410) means "everything allowed". Rules are
read per RFC 9309, including `*` and `$` wildcards and longest-match precedence
(Python's built-in urllib.robotparser ignores wildcards, which gets real sites wrong).
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any
import re
from dataclasses import dataclass, field
from urllib.parse import unquote, urlsplit

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

log = logging.getLogger(__name__)

RETRY_STATUSES = (429, 500, 502, 503, 504)


class RobotsDisallowed(RuntimeError):
    """Raised when robots.txt disallows a URL for our user agent."""


def describe_error(exc: BaseException) -> str:
    """One short, readable line for logs instead of urllib3's multi-line chains."""
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        return f"HTTP {exc.response.status_code} {exc.response.reason or ''}".strip()
    if isinstance(exc, requests.Timeout):
        return "timed out (after retries)"
    if isinstance(exc, requests.ConnectionError):
        text = str(exc)
        if "NameResolution" in text or "getaddrinfo" in text:
            return "network/DNS error (after retries)"
        if "Max retries exceeded" in text and "too many" in text.lower():
            return "server kept returning errors (after retries)"
        return "connection failed (after retries)"
    if isinstance(exc, requests.exceptions.RetryError):
        return "server kept returning 429/5xx (after retries)"
    return f"{type(exc).__name__}: {str(exc)[:160]}"


@dataclass
class RobotsRules:
    """The robots.txt group that applies to one user agent (RFC 9309)."""

    rules: list[tuple[bool, str, re.Pattern[str]]] = field(default_factory=list)  # (allow, raw, regex)
    crawl_delay: float | None = None

    @classmethod
    def parse(cls, text: str, user_agent: str) -> "RobotsRules":
        token = user_agent.split("/")[0].strip().lower()
        groups: list[tuple[list[str], list[tuple[str, str]]]] = []
        agents: list[str] = []
        lines: list[tuple[str, str]] = []
        last_was_agent = False
        for raw in text.splitlines():
            line = raw.split("#", 1)[0].strip()
            if ":" not in line:
                continue
            key, value = (part.strip() for part in line.split(":", 1))
            key = key.lower()
            if key == "user-agent":
                if not last_was_agent and agents:
                    groups.append((agents, lines))
                    agents, lines = [], []
                agents.append(value.lower())
                last_was_agent = True
            elif key in ("allow", "disallow", "crawl-delay"):
                lines.append((key, value))
                last_was_agent = False
        if agents:
            groups.append((agents, lines))

        specific = [g for g in groups if any(a != "*" and a in token for a in g[0])]
        chosen = specific or [g for g in groups if "*" in g[0]]
        result = cls()
        for _, group_lines in chosen:
            for key, value in group_lines:
                if key == "crawl-delay":
                    try:
                        result.crawl_delay = float(value)
                    except ValueError:
                        pass
                elif value:  # an empty Disallow means "allow everything"
                    result.rules.append((key == "allow", value, cls._compile(value)))
        return result

    @staticmethod
    def _compile(pattern: str) -> re.Pattern[str]:
        anchored = pattern.endswith("$")
        body = re.escape(unquote(pattern.rstrip("$"))).replace(r"\*", ".*")
        return re.compile(body + ("$" if anchored else ""))

    def can_fetch(self, url: str) -> bool:
        parts = urlsplit(url)
        path = unquote(parts.path or "/") + (f"?{parts.query}" if parts.query else "")
        best_len, allowed = -1, True
        for allow, raw, regex in self.rules:
            if regex.match(path):
                length = len(raw)
                if length > best_len or (length == best_len and allow):
                    best_len, allowed = length, allow
        return allowed


class LoggingRetry(Retry):
    """urllib3 Retry that logs one short line per retry (urllib3's own log lines are very long)."""

    def increment(self, method=None, url=None, response=None, error=None, _pool=None, _stacktrace=None):  # type: ignore[override]
        new = super().increment(method, url, response, error, _pool, _stacktrace)
        if response is not None and response.status:
            reason = f"HTTP {response.status}"
        elif error is not None:
            name = type(error).__name__
            reason = {"NameResolutionError": "DNS error", "ReadTimeoutError": "read timeout",
                      "ConnectTimeoutError": "connect timeout", "ProtocolError": "connection dropped"}.get(name, name)
            if name == "NewConnectionError" and "getaddrinfo" in str(error):
                reason = "DNS error"
        else:
            reason = "error"
        log.warning("retry %d/%d for %s (%s)", len(new.history), len(new.history) + (new.total or 0), url, reason)
        return new


class RateLimiter:
    """Enforces a minimum delay between calls. Safe to share between threads."""

    def __init__(self, min_interval: float) -> None:
        self.min_interval = max(0.0, float(min_interval))
        self._lock = threading.Lock()
        self._next_allowed = 0.0

    def wait(self) -> None:
        with self._lock:
            # Loop because sleep() can wake a little early on Windows (coarse timer).
            while (delay := self._next_allowed - time.monotonic()) > 0:
                time.sleep(delay)
            self._next_allowed = time.monotonic() + self.min_interval


class PoliteSession:
    """A requests.Session wrapper that behaves like a well-mannered bot."""

    def __init__(
        self,
        user_agent: str,
        min_interval: float = 1.0,
        max_retries: int = 4,
        backoff_factor: float = 1.0,
        timeout: float = 20.0,
        respect_robots: bool = True,
    ) -> None:
        if not user_agent.strip():
            raise ValueError("user_agent must not be empty; identify your bot honestly")
        self.user_agent = user_agent
        self.timeout = timeout
        self.respect_robots = respect_robots
        self.limiter = RateLimiter(min_interval)
        self.request_count = 0
        self._robots: dict[str, RobotsRules | None] = {}

        retry = LoggingRetry(
            total=max_retries,
            connect=max_retries,
            read=max_retries,
            status=max_retries,
            backoff_factor=backoff_factor,
            status_forcelist=RETRY_STATUSES,
            allowed_methods=frozenset({"GET", "HEAD"}),
            respect_retry_after_header=True,
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=4, pool_maxsize=8)
        self.session = requests.Session()
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.session.headers.update({"User-Agent": user_agent, "Accept-Language": "en"})

    # ------------------------------------------------------------------ robots
    def _robots_for(self, url: str) -> RobotsRules | None:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin in self._robots:
            return self._robots[origin]
        robots_url = f"{origin}/robots.txt"
        try:
            self.limiter.wait()
            self.request_count += 1
            resp = self.session.get(robots_url, timeout=self.timeout)
        except requests.RequestException as exc:
            log.warning("Could not fetch %s (%s); treating as allow-all", robots_url, exc)
            self._robots[origin] = None
            return None
        if 400 <= resp.status_code < 500 and resp.status_code not in (401, 403):
            log.info("robots.txt: none at %s (all paths allowed)", origin)
            self._robots[origin] = None
            return None
        if resp.status_code in (401, 403) or resp.status_code >= 500:
            log.warning("robots.txt at %s returned %s; treating as disallow-all", origin, resp.status_code)
            rules = RobotsRules.parse("User-agent: *\nDisallow: /", self.user_agent)
        else:
            rules = RobotsRules.parse(resp.text, self.user_agent)
            log.info("robots.txt: loaded %d rules for %s", len(rules.rules), origin)
        if rules.crawl_delay and rules.crawl_delay > self.limiter.min_interval:
            log.info("robots.txt Crawl-delay %ss is larger than our delay; using it", rules.crawl_delay)
            self.limiter.min_interval = rules.crawl_delay
        self._robots[origin] = rules
        return rules

    def allowed(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        rules = self._robots_for(url)
        return True if rules is None else rules.can_fetch(url)

    # ---------------------------------------------------------------- requests
    def get(self, url: str, **kwargs: Any) -> requests.Response:
        """GET with robots check, rate limit, retries and raise_for_status()."""
        if not self.allowed(url):
            raise RobotsDisallowed(f"robots.txt disallows {url}")
        self.limiter.wait()
        self.request_count += 1
        kwargs.setdefault("timeout", self.timeout)
        started = time.monotonic()
        resp = self.session.get(url, **kwargs)
        log.debug("GET %s -> %s in %.2fs", url, resp.status_code, time.monotonic() - started)
        resp.raise_for_status()
        return resp

    def get_json(self, url: str, **kwargs: Any) -> Any:
        return self.get(url, **kwargs).json()

    def close(self) -> None:
        self.session.close()

    def __enter__(self) -> "PoliteSession":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
