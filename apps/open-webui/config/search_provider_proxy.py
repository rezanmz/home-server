#!/usr/bin/env python3
"""Keep paid search credentials private and enforce sequential search fallback."""

from __future__ import annotations

import json
import os
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"
SERPAPI_URL = "https://serpapi.com/search.json"
SEARXNG_URL = os.getenv(
    "SEARXNG_INTERNAL_SEARCH_URL", "http://127.0.0.1:8082/search"
)
MAX_QUERY_CHARS = 1_000
MAX_UPSTREAM_BYTES = 4 * 1024 * 1024
PUBLIC_ENGINE_TIMEOUT_SECONDS = 4
PAID_PROVIDER_TIMEOUT_SECONDS = 7
PUBLIC_ENGINE_COOLDOWN_SECONDS = 15 * 60
RESULT_LIMIT = 10
PUBLIC_ENGINES = (
    ("duckduckgo", "ddg"),
    ("mojeek", "mjk"),
    ("startpage", "sp"),
)

_metrics: Counter[tuple[str, str]] = Counter()
_metrics_lock = threading.Lock()
_search_metrics: Counter[str] = Counter()
_cooldowns: dict[str, float] = {}
_cooldowns_lock = threading.Lock()


class ProviderError(RuntimeError):
    """An upstream provider failed without exposing its request URL or key."""


def required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if len(value) < 20:
        raise RuntimeError(f"{name} is missing or too short")
    return value


def record(provider: str, outcome: str) -> None:
    with _metrics_lock:
        _metrics[(provider, outcome)] += 1


def record_search(outcome: str) -> None:
    with _metrics_lock:
        _search_metrics[outcome] += 1


def log_attempt(provider: str, outcome: str, result_count: int = 0) -> None:
    print(
        json.dumps(
            {
                "level": "info" if outcome == "success" else "warning",
                "service": "searxng-provider-proxy",
                "provider": provider,
                "outcome": outcome,
                "result_count": result_count,
            },
            separators=(",", ":"),
        ),
        file=sys.stderr,
        flush=True,
    )


def fetch_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: int = PAID_PROVIDER_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", **(headers or {})},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if response.status != 200:
                raise ProviderError(f"upstream returned HTTP {response.status}")
            body = response.read(MAX_UPSTREAM_BYTES + 1)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as error:
        status = getattr(error, "code", None)
        detail = f"HTTP {status}" if status else type(error).__name__
        raise ProviderError(detail) from None

    if len(body) > MAX_UPSTREAM_BYTES:
        raise ProviderError("upstream response exceeded the size limit")
    try:
        document = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ProviderError("upstream returned invalid JSON") from None
    if not isinstance(document, dict):
        raise ProviderError("upstream returned an invalid document")
    return document


def concise_result(item: dict[str, Any], position: int) -> dict[str, Any] | None:
    link = item.get("url") or item.get("link")
    title = item.get("title")
    if not isinstance(link, str) or not link.startswith(("https://", "http://")):
        return None
    if not isinstance(title, str) or not title.strip():
        return None
    description = item.get("description") or item.get("snippet") or ""
    return {
        "link": link,
        "title": title.strip()[:1_000],
        "snippet": str(description).strip()[:4_000],
        "position": position,
    }


def brave_search(query: str, page: int) -> list[dict[str, Any]]:
    parameters = urllib.parse.urlencode(
        {
            "q": query,
            "count": RESULT_LIMIT,
            "offset": (page - 1) * RESULT_LIMIT,
            "country": "CA",
            "search_lang": "en",
            "safesearch": "moderate",
            "text_decorations": "false",
        }
    )
    document = fetch_json(
        f"{BRAVE_URL}?{parameters}",
        headers={"X-Subscription-Token": required("BRAVE_SEARCH_API_KEY")},
    )
    candidates = (document.get("web") or {}).get("results") or []
    if not isinstance(candidates, list):
        raise ProviderError("Brave returned an invalid result list")
    return [
        result
        for index, item in enumerate(candidates[:RESULT_LIMIT], start=1)
        if isinstance(item, dict)
        and (result := concise_result(item, index)) is not None
    ]


def searxng_engine_search(
    query: str, page: int, shortcut: str
) -> list[dict[str, Any]]:
    """Ask exactly one disabled SearXNG engine through its bang shortcut."""
    # SearXNG parses any whitespace-delimited !token as an engine selector.
    # Remove that control prefix from untrusted/model-generated query tokens so
    # only the adapter's reviewed shortcut can choose the engine.
    safe_query = " ".join(token.lstrip("!") for token in query.split())
    parameters = urllib.parse.urlencode(
        {
            "q": f"!{shortcut} {safe_query}",
            "format": "json",
            "pageno": page,
            "language": "en-CA",
            "safesearch": 1,
        }
    )
    document = fetch_json(
        f"{SEARXNG_URL}?{parameters}", timeout=PUBLIC_ENGINE_TIMEOUT_SECONDS
    )
    candidates = document.get("results") or []
    if not isinstance(candidates, list):
        raise ProviderError("SearXNG returned an invalid result list")
    results = [
        result
        for index, item in enumerate(candidates[:RESULT_LIMIT], start=1)
        if isinstance(item, dict)
        and (
            result := concise_result(
                {
                    "url": item.get("url"),
                    "title": item.get("title"),
                    "description": item.get("content"),
                },
                index,
            )
        )
        is not None
    ]
    if not results and document.get("unresponsive_engines"):
        raise ProviderError("SearXNG engine was unresponsive")
    return results


def serpapi_search(query: str, page: int) -> list[dict[str, Any]]:
    # SerpAPI accepts its credential only as a query parameter. This URL never
    # leaves this process or enters an exception/log message.
    parameters = urllib.parse.urlencode(
        {
            "engine": "google",
            "q": query,
            "api_key": required("SERPAPI_API_KEY"),
            "start": (page - 1) * RESULT_LIMIT,
            "num": RESULT_LIMIT,
            "gl": "ca",
            "hl": "en",
            "safe": "active",
        }
    )
    document = fetch_json(f"{SERPAPI_URL}?{parameters}")
    if document.get("error"):
        raise ProviderError("SerpAPI returned an API error")
    candidates = document.get("organic_results") or []
    if not isinstance(candidates, list):
        raise ProviderError("SerpAPI returned an invalid result list")
    return [
        result
        for index, item in enumerate(candidates[:RESULT_LIMIT], start=1)
        if isinstance(item, dict)
        and (result := concise_result(item, index)) is not None
    ]


def is_available(provider: str) -> bool:
    now = time.monotonic()
    with _cooldowns_lock:
        deadline = _cooldowns.get(provider, 0)
        if deadline <= now:
            _cooldowns.pop(provider, None)
            return True
        return False


def start_cooldown(provider: str) -> None:
    with _cooldowns_lock:
        _cooldowns[provider] = time.monotonic() + PUBLIC_ENGINE_COOLDOWN_SECONDS


def attempt(
    provider: str,
    search: Any,
    query: str,
    page: int,
    attempted: list[str],
    *,
    cooldown_on_error: bool = False,
) -> list[dict[str, Any]]:
    if cooldown_on_error and not is_available(provider):
        record(provider, "cooldown")
        return []
    attempted.append(provider)
    try:
        results = search(query, page)
    except ProviderError:
        record(provider, "error")
        log_attempt(provider, "error")
        if cooldown_on_error:
            start_cooldown(provider)
        return []
    outcome = "success" if results else "empty"
    record(provider, outcome)
    log_attempt(provider, outcome, len(results))
    return results


def ordered_search(query: str, page: int = 1) -> dict[str, Any]:
    attempted: list[str] = []
    for provider, shortcut in PUBLIC_ENGINES:
        results = attempt(
            provider,
            lambda current_query, current_page, current_shortcut=shortcut: searxng_engine_search(
                current_query, current_page, current_shortcut
            ),
            query,
            page,
            attempted,
            cooldown_on_error=True,
        )
        if results:
            record_search("success")
            return {"organic_results": results, "provider": provider, "attempted": attempted}

    for provider, search in (("brave", brave_search), ("serpapi", serpapi_search)):
        results = attempt(provider, search, query, page, attempted)
        if results:
            record_search("success")
            return {"organic_results": results, "provider": provider, "attempted": attempted}
    record_search("failed")
    return {"organic_results": [], "provider": None, "attempted": attempted}


def prometheus_metrics() -> str:
    lines = [
        "# HELP searxng_provider_requests_total Sequential search-provider decisions by provider and outcome.",
        "# TYPE searxng_provider_requests_total counter",
    ]
    with _metrics_lock:
        snapshot = sorted(_metrics.items())
    for (provider, outcome), value in snapshot:
        lines.append(
            f'searxng_provider_requests_total{{provider="{provider}",outcome="{outcome}"}} {value}'
        )
    lines.extend(
        [
            "# HELP searxng_search_requests_total End-to-end search requests by outcome.",
            "# TYPE searxng_search_requests_total counter",
        ]
    )
    with _metrics_lock:
        search_snapshot = sorted(_search_metrics.items())
    for outcome, value in search_snapshot:
        lines.append(f'searxng_search_requests_total{{outcome="{outcome}"}} {value}')
    return "\n".join(lines) + "\n"


class BaseHandler(BaseHTTPRequestHandler):
    server_version = "HomeSearchProvider/1.0"

    def send_body(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *_args: Any) -> None:
        return


class SearchHandler(BaseHandler):
    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/healthz":
            self.send_body(200, "application/json", b'{"status":"ok"}')
            return
        if parsed.path != "/search":
            self.send_body(404, "application/json", b'{"error":"not_found"}')
            return

        parameters = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
        query = parameters.get("q", [""])[0].strip()
        try:
            page = int(parameters.get("pageno", ["1"])[0])
        except ValueError:
            page = 0
        if not query or len(query) > MAX_QUERY_CHARS or page < 1 or page > 10:
            self.send_body(400, "application/json", b'{"error":"invalid_request"}')
            return

        document = ordered_search(query, page)
        provider = document["provider"] or "none"
        results = [
            {
                "url": item["link"],
                "title": item["title"],
                "content": item["snippet"],
                "engine": provider,
                "engines": [provider],
                "score": max(1.0 / int(item.get("position", 1)), 0.01),
            }
            for item in document["organic_results"]
        ]
        response = {
            "query": query,
            "results": results,
            "answers": [],
            "corrections": [],
            "infoboxes": [],
            "suggestions": [],
            "unresponsive_engines": [],
        }
        self.send_body(
            200,
            "application/json",
            json.dumps(response, separators=(",", ":")).encode("utf-8"),
        )


class MetricsHandler(BaseHandler):
    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/healthz":
            self.send_body(200, "application/json", b'{"status":"ok"}')
            return
        if parsed.path == "/metrics":
            self.send_body(
                200,
                "text/plain; version=0.0.4; charset=utf-8",
                prometheus_metrics().encode("utf-8"),
            )
            return
        self.send_body(404, "application/json", b'{"error":"not_found"}')


def main() -> None:
    required("BRAVE_SEARCH_API_KEY")
    required("SERPAPI_API_KEY")
    metrics_server = ThreadingHTTPServer(("0.0.0.0", 8081), MetricsHandler)
    threading.Thread(target=metrics_server.serve_forever, daemon=True).start()
    search_server = ThreadingHTTPServer(("0.0.0.0", 8080), SearchHandler)
    print(
        '{"level":"info","service":"searxng-provider-proxy","message":"started","search_port":8080,"metrics_port":8081}',
        file=sys.stderr,
        flush=True,
    )
    search_server.serve_forever()


if __name__ == "__main__":
    main()
