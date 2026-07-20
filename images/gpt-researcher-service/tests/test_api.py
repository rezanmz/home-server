from __future__ import annotations

import importlib
import os
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient


class ResearchServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.environ["RESEARCH_API_TOKEN"] = "t" * 64
        cls.api = importlib.import_module("research_service.api")
        cls.client = TestClient(cls.api.app)
        cls.headers = {"Authorization": f"Bearer {'t' * 64}"}

    def test_health_does_not_require_credentials(self) -> None:
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_openapi_and_research_require_credentials(self) -> None:
        self.assertEqual(self.client.get("/openapi.json").status_code, 401)
        self.assertEqual(
            self.client.post(
                "/v1/research",
                json={"query": "A sufficiently long research question"},
            ).status_code,
            401,
        )

    def test_research_returns_sanitized_result(self) -> None:
        result = {
            "report": "# Result\n\nSupported.",
            "sources": [{"title": "Primary", "url": "https://example.com/source"}],
            "estimated_cost_usd": 0.0123,
        }
        with patch.object(self.api, "_run_worker", AsyncMock(return_value=result)):
            response = self.client.post(
                "/v1/research",
                headers=self.headers,
                json={"query": "Research this sufficiently long question"},
            )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["report"], result["report"])
        self.assertEqual(payload["estimated_cost_usd"], result["estimated_cost_usd"])
        self.assertNotIn("step_costs_usd", payload)

    def test_unknown_fields_and_short_queries_are_rejected(self) -> None:
        response = self.client.post(
            "/v1/research",
            headers=self.headers,
            json={"query": "short", "source_url": "http://127.0.0.1"},
        )
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
