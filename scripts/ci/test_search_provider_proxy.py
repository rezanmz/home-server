#!/usr/bin/env python3
"""Tests for the SearXNG sequential provider adapter."""

from __future__ import annotations

import importlib.util
import io
import sys
import unittest
import urllib.error
import urllib.parse
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = (
    REPO_ROOT / "apps" / "open-webui" / "config" / "search_provider_proxy.py"
)
SPEC = importlib.util.spec_from_file_location("search_provider_proxy", MODULE_PATH)
assert SPEC and SPEC.loader
proxy = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = proxy
SPEC.loader.exec_module(proxy)


RESULT = [{"link": "https://example.com", "title": "Example", "snippet": "Body"}]


class SearchProviderProxyTests(unittest.TestCase):
    def setUp(self) -> None:
        with proxy._metrics_lock:
            proxy._metrics.clear()
            proxy._search_metrics.clear()
        with proxy._cooldowns_lock:
            proxy._cooldowns.clear()

    def test_free_engine_success_does_not_call_paid_providers(self) -> None:
        with (
            mock.patch.object(proxy, "searxng_engine_search", return_value=RESULT) as free,
            mock.patch.object(proxy, "brave_search") as brave,
            mock.patch.object(proxy, "serpapi_search") as serpapi,
            mock.patch.object(proxy, "log_attempt"),
        ):
            document = proxy.ordered_search("current model pricing")

        self.assertEqual(document["provider"], "duckduckgo")
        self.assertEqual(document["attempted"], ["duckduckgo"])
        free.assert_called_once_with("current model pricing", 1, "ddg")
        brave.assert_not_called()
        serpapi.assert_not_called()

    def test_brave_runs_after_each_free_engine_fails_or_is_empty(self) -> None:
        free_results = [proxy.ProviderError("rate limited"), [], []]
        with (
            mock.patch.object(proxy, "searxng_engine_search", side_effect=free_results),
            mock.patch.object(proxy, "brave_search", return_value=RESULT) as brave,
            mock.patch.object(proxy, "serpapi_search") as serpapi,
            mock.patch.object(proxy, "log_attempt"),
        ):
            document = proxy.ordered_search("current model pricing")

        self.assertEqual(document["provider"], "brave")
        self.assertEqual(
            document["attempted"],
            ["duckduckgo", "mojeek", "startpage", "brave"],
        )
        brave.assert_called_once_with("current model pricing", 1)
        serpapi.assert_not_called()

    def test_serpapi_is_the_last_resort(self) -> None:
        with (
            mock.patch.object(proxy, "searxng_engine_search", return_value=[]),
            mock.patch.object(proxy, "brave_search", side_effect=proxy.ProviderError("down")),
            mock.patch.object(proxy, "serpapi_search", return_value=RESULT) as serpapi,
            mock.patch.object(proxy, "log_attempt"),
        ):
            document = proxy.ordered_search("current model pricing")

        self.assertEqual(document["provider"], "serpapi")
        self.assertEqual(document["attempted"][-2:], ["brave", "serpapi"])
        serpapi.assert_called_once_with("current model pricing", 1)

    def test_failed_free_engine_enters_cooldown(self) -> None:
        with (
            mock.patch.object(
                proxy,
                "searxng_engine_search",
                side_effect=[proxy.ProviderError("blocked"), RESULT, RESULT],
            ) as free,
            mock.patch.object(proxy, "brave_search") as brave,
            mock.patch.object(proxy, "serpapi_search") as serpapi,
            mock.patch.object(proxy, "log_attempt"),
        ):
            first = proxy.ordered_search("one")
            second = proxy.ordered_search("two")

        self.assertEqual(first["provider"], "mojeek")
        self.assertEqual(second["provider"], "mojeek")
        self.assertEqual(free.call_count, 3)
        self.assertNotIn("duckduckgo", second["attempted"])
        brave.assert_not_called()
        serpapi.assert_not_called()

    def test_untrusted_bangs_cannot_select_additional_engines(self) -> None:
        with mock.patch.object(
            proxy,
            "fetch_json",
            return_value={"results": RESULT, "unresponsive_engines": []},
        ) as fetch:
            proxy.searxng_engine_search("!ddg !!google useful query", 1, "mjk")

        parsed = urllib.parse.urlparse(fetch.call_args.args[0])
        forwarded = urllib.parse.parse_qs(parsed.query)["q"][0]
        self.assertEqual(forwarded, "!mjk ddg google useful query")
        self.assertEqual(forwarded.count("!"), 1)

    def test_upstream_errors_do_not_expose_credential_bearing_url(self) -> None:
        secret_url = "https://serpapi.com/search.json?api_key=do-not-log-this"
        error = urllib.error.HTTPError(
            secret_url, 429, "rate limited", {}, io.BytesIO(b"")
        )
        self.addCleanup(error.close)
        with mock.patch.object(proxy.urllib.request, "urlopen", side_effect=error):
            with self.assertRaises(proxy.ProviderError) as raised:
                proxy.fetch_json(secret_url)
        self.assertEqual(str(raised.exception), "HTTP 429")
        self.assertNotIn("do-not-log-this", str(raised.exception))

    def test_metrics_contain_only_bounded_provider_and_outcome_labels(self) -> None:
        with (
            mock.patch.object(proxy, "searxng_engine_search", return_value=[]),
            mock.patch.object(proxy, "brave_search", side_effect=proxy.ProviderError("down")),
            mock.patch.object(proxy, "serpapi_search", return_value=RESULT),
            mock.patch.object(proxy, "log_attempt"),
        ):
            proxy.ordered_search("a private query that must not become a label")

        metrics = proxy.prometheus_metrics()
        self.assertIn('provider="brave",outcome="error"', metrics)
        self.assertIn('provider="serpapi",outcome="success"', metrics)
        self.assertIn('searxng_search_requests_total{outcome="success"} 1', metrics)
        self.assertNotIn("private query", metrics)

    def test_failed_paid_provider_enters_short_cooldown(self) -> None:
        with (
            mock.patch.object(proxy, "searxng_engine_search", return_value=[]),
            mock.patch.object(
                proxy, "brave_search", side_effect=proxy.ProviderError("HTTP 429")
            ),
            mock.patch.object(proxy, "serpapi_search", return_value=RESULT),
            mock.patch.object(proxy, "log_attempt"),
        ):
            first = proxy.ordered_search("cooldown probe")

        self.assertEqual(first["provider"], "serpapi")

        with (
            mock.patch.object(proxy, "searxng_engine_search", return_value=[]),
            mock.patch.object(proxy, "brave_search") as brave,
            mock.patch.object(proxy, "serpapi_search", return_value=RESULT) as serpapi,
            mock.patch.object(proxy, "log_attempt"),
        ):
            second = proxy.ordered_search("cooldown probe two")

        brave.assert_not_called()
        serpapi.assert_called_once()
        self.assertEqual(second["provider"], "serpapi")
        self.assertNotIn("brave", second["attempted"])

    def test_paid_cooldown_expires_and_recovers_brave(self) -> None:
        with (
            mock.patch.object(proxy, "searxng_engine_search", return_value=[]),
            mock.patch.object(
                proxy, "brave_search", side_effect=proxy.ProviderError("HTTP 429")
            ),
            mock.patch.object(proxy, "serpapi_search", return_value=RESULT),
            mock.patch.object(proxy, "log_attempt"),
        ):
            proxy.ordered_search("expiry probe")

        self.assertIn("brave", proxy._cooldowns)
        deadline = proxy._cooldowns["brave"]
        self.assertLessEqual(
            deadline - __import__("time").monotonic(),
            proxy.PAID_PROVIDER_COOLDOWN_SECONDS,
        )

        proxy._cooldowns["brave"] = 0
        with (
            mock.patch.object(proxy, "searxng_engine_search", return_value=[]),
            mock.patch.object(proxy, "brave_search", return_value=RESULT) as brave,
            mock.patch.object(proxy, "serpapi_search") as serpapi,
            mock.patch.object(proxy, "log_attempt"),
        ):
            recovered = proxy.ordered_search("expiry probe two")

        brave.assert_called_once()
        serpapi.assert_not_called()


if __name__ == "__main__":
    unittest.main()
