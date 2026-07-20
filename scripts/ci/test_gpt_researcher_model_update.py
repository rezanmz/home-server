import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "scripts" / "update_gpt_researcher_models.py"
SPEC = importlib.util.spec_from_file_location(
    "gpt_researcher_model_update",
    MODULE_PATH,
)
updater = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(updater)


def model_record(
    model_id: str,
    *,
    context_length: int = 1_000_000,
    max_completion_tokens: int = 64_000,
    output_modalities: list[str] | None = None,
    supported_parameters: list[str] | None = None,
) -> dict:
    return {
        "id": model_id,
        "name": model_id,
        "context_length": context_length,
        "architecture": {
            "output_modalities": output_modalities or ["text"],
        },
        "top_provider": {
            "max_completion_tokens": max_completion_tokens,
        },
        "supported_parameters": supported_parameters
        or ["max_tokens", "temperature", "tools"],
        "pricing": {
            "prompt": "0.000001",
            "completion": "0.000003",
        },
        "expiration_date": None,
    }


class GPTResearcherModelUpdateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = {
            "EMBEDDING": "openrouter:google/gemini-embedding-2",
            "FAST_LLM": "openrouter:google/fast-current",
            "SMART_LLM": "openrouter:google/smart-current",
            "STRATEGIC_LLM": "openrouter:google/strategic-current",
            "FAST_TOKEN_LIMIT": 6_000,
            "SMART_TOKEN_LIMIT": 12_000,
            "STRATEGIC_TOKEN_LIMIT": 8_000,
            "MAX_ITERATIONS": 3,
        }
        self.catalog = {
            model_id: model_record(model_id)
            for model_id in (
                "google/fast-current",
                "google/smart-current",
                "google/strategic-current",
                "google/fast-next",
            )
        }

    def test_current_roles_validate_without_paid_model_calls(self) -> None:
        results = updater.validate_role_models(self.config, self.catalog)

        self.assertEqual(
            [result["role"] for result in results],
            list(updater.ROLE_KEYS),
        )
        self.assertEqual(results[0]["prompt_usd_per_million"], 1.0)
        self.assertEqual(results[0]["completion_usd_per_million"], 3.0)

    def test_role_update_preserves_embedding_and_unrelated_tuning(self) -> None:
        changed = updater.update_roles(
            self.config,
            fast_model="google/fast-next",
            smart_model="",
        )

        self.assertTrue(changed)
        self.assertEqual(
            self.config["FAST_LLM"],
            "openrouter:google/fast-next",
        )
        self.assertEqual(
            self.config["EMBEDDING"],
            "openrouter:google/gemini-embedding-2",
        )
        self.assertEqual(self.config["MAX_ITERATIONS"], 3)

    def test_unavailable_or_incompatible_models_are_rejected(self) -> None:
        self.config["FAST_LLM"] = "openrouter:google/missing"
        with self.assertRaisesRegex(updater.ValidationError, "unavailable"):
            updater.validate_role_models(self.config, self.catalog)

        self.config["FAST_LLM"] = "openrouter:google/fast-current"
        self.catalog["google/fast-current"] = model_record(
            "google/fast-current",
            max_completion_tokens=4_000,
        )
        with self.assertRaisesRegex(updater.ValidationError, "cannot satisfy"):
            updater.validate_role_models(self.config, self.catalog)

        self.catalog["google/fast-current"] = model_record(
            "google/fast-current",
            supported_parameters=["max_tokens"],
        )
        with self.assertRaisesRegex(updater.ValidationError, "required parameters"):
            updater.validate_role_models(self.config, self.catalog)

    def test_invalid_provider_or_model_id_is_rejected(self) -> None:
        self.config["FAST_LLM"] = "google/fast-current"
        with self.assertRaisesRegex(updater.ValidationError, "provider prefix"):
            updater.validate_role_models(self.config, self.catalog)

        with self.assertRaisesRegex(updater.ValidationError, "invalid OpenRouter"):
            updater.update_roles(
                self.config,
                fast_model="google/fast-current; echo unsafe",
            )

    def test_catalog_file_and_atomic_write_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog_path = root / "catalog.json"
            catalog_path.write_text(
                json.dumps({"data": list(self.catalog.values())}),
                encoding="utf-8",
            )
            config_path = root / "researcher.json"
            config_path.write_text(json.dumps(self.config), encoding="utf-8")

            catalog = updater._load_catalog(catalog_file=catalog_path)
            updater.update_roles(self.config, fast_model="google/fast-next")
            updater.validate_role_models(self.config, catalog)
            updater._write_json_atomic(config_path, self.config)

            persisted = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertEqual(
                persisted["FAST_LLM"],
                "openrouter:google/fast-next",
            )
            self.assertFalse(
                any(path.name.endswith(".tmp") for path in root.iterdir())
            )


if __name__ == "__main__":
    unittest.main()
