#!/usr/bin/env python3
"""Validate or update GPT Researcher's Git-managed OpenRouter LLM roles.

This deliberately does not choose models or make paid inference requests. It
checks exact role IDs against OpenRouter's public model catalog, validates the
minimum interface needed by GPT Researcher, and writes only FAST_LLM,
SMART_LLM, and STRATEGIC_LLM. Embedding changes require a separate indexed-data
migration and are therefore outside this updater's authority.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import tempfile
import urllib.parse
import urllib.request
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = REPO_ROOT / "apps" / "gpt-researcher" / "config" / "researcher.json"
DEFAULT_CATALOG_URL = "https://openrouter.ai/api/v1/models"
ROLE_KEYS = ("FAST_LLM", "SMART_LLM", "STRATEGIC_LLM")
ROLE_TOKEN_LIMIT_KEYS = {
    "FAST_LLM": "FAST_TOKEN_LIMIT",
    "SMART_LLM": "SMART_TOKEN_LIMIT",
    "STRATEGIC_LLM": "STRATEGIC_TOKEN_LIMIT",
}
MODEL_ID_PATTERN = re.compile(r"^[A-Za-z0-9._~-]+/[A-Za-z0-9._~:+-]+$")
MINIMUM_CONTEXT_TOKENS = 32_768


class ValidationError(RuntimeError):
    pass


def _provider_model_id(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ValidationError("GPT Researcher role model must be a non-empty string")
    prefix = "openrouter:"
    if not value.startswith(prefix):
        raise ValidationError(f"role model must use the {prefix} provider prefix: {value}")
    model_id = value.removeprefix(prefix)
    if len(model_id) > 200 or not MODEL_ID_PATTERN.fullmatch(model_id):
        raise ValidationError(f"invalid OpenRouter model ID: {model_id}")
    return model_id


def _normalized_role_value(value: str) -> str:
    value = value.strip()
    if value.startswith("openrouter:"):
        model_id = _provider_model_id(value)
    else:
        model_id = value
        if len(model_id) > 200 or not MODEL_ID_PATTERN.fullmatch(model_id):
            raise ValidationError(f"invalid OpenRouter model ID: {model_id}")
    return f"openrouter:{model_id}"


def _load_catalog(
    *,
    catalog_url: str = DEFAULT_CATALOG_URL,
    catalog_file: Path | None = None,
) -> dict[str, dict[str, Any]]:
    if catalog_file is not None:
        payload = json.loads(catalog_file.read_text(encoding="utf-8"))
    else:
        separator = "&" if "?" in catalog_url else "?"
        url = f"{catalog_url}{separator}{urllib.parse.urlencode({'output_modalities': 'text'})}"
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "home-server-gpt-researcher-model-validator/1.0",
            },
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)

    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or not rows:
        raise ValidationError("OpenRouter catalog contains no model records")
    models = {
        row["id"]: row
        for row in rows
        if isinstance(row, dict) and isinstance(row.get("id"), str)
    }
    if not models:
        raise ValidationError("OpenRouter catalog contains no valid model IDs")
    return models


def _decimal(value: Any, field: str, model_id: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValidationError(
            f"{model_id} has invalid {field} pricing metadata"
        ) from error
    if not parsed.is_finite() or parsed < 0:
        raise ValidationError(f"{model_id} has invalid {field} pricing metadata")
    return parsed


def validate_role_models(
    config: dict[str, Any],
    catalog: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for role in ROLE_KEYS:
        model_id = _provider_model_id(config.get(role))
        model = catalog.get(model_id)
        if model is None:
            raise ValidationError(f"{role} model is unavailable on OpenRouter: {model_id}")

        architecture = model.get("architecture") or {}
        output_modalities = architecture.get("output_modalities") or []
        if "text" not in output_modalities:
            raise ValidationError(f"{role} model does not produce text: {model_id}")

        context_length = model.get("context_length")
        if not isinstance(context_length, int) or context_length < MINIMUM_CONTEXT_TOKENS:
            raise ValidationError(
                f"{role} model context is below {MINIMUM_CONTEXT_TOKENS}: {model_id}"
            )

        token_limit_key = ROLE_TOKEN_LIMIT_KEYS[role]
        token_limit = config.get(token_limit_key)
        if not isinstance(token_limit, int) or token_limit < 1:
            raise ValidationError(f"{token_limit_key} must be a positive integer")
        max_completion = (model.get("top_provider") or {}).get(
            "max_completion_tokens"
        )
        if isinstance(max_completion, int) and max_completion < token_limit:
            raise ValidationError(
                f"{role} model cannot satisfy {token_limit_key}={token_limit}: {model_id}"
            )

        supported_parameters = set(model.get("supported_parameters") or [])
        required_parameters = {"max_tokens", "temperature"}
        missing_parameters = sorted(required_parameters - supported_parameters)
        if missing_parameters:
            raise ValidationError(
                f"{role} model lacks required parameters {missing_parameters}: {model_id}"
            )

        expiration = model.get("expiration_date")
        if isinstance(expiration, str) and expiration:
            try:
                expiration_date = date.fromisoformat(expiration[:10])
            except ValueError as error:
                raise ValidationError(
                    f"{role} model has invalid expiration metadata: {model_id}"
                ) from error
            if expiration_date <= date.today():
                raise ValidationError(f"{role} model is expired: {model_id}")

        pricing = model.get("pricing") or {}
        prompt_price = _decimal(pricing.get("prompt"), "prompt", model_id)
        completion_price = _decimal(
            pricing.get("completion"), "completion", model_id
        )
        prompt_per_million = float(prompt_price * Decimal(1_000_000))
        completion_per_million = float(completion_price * Decimal(1_000_000))
        if not math.isfinite(prompt_per_million) or not math.isfinite(
            completion_per_million
        ):
            raise ValidationError(f"{role} model pricing is not finite: {model_id}")

        results.append(
            {
                "role": role,
                "model_id": model_id,
                "name": model.get("name") or model_id,
                "context_length": context_length,
                "max_completion_tokens": max_completion,
                "prompt_usd_per_million": prompt_per_million,
                "completion_usd_per_million": completion_per_million,
                "expiration_date": expiration,
            }
        )
    return results


def update_roles(
    config: dict[str, Any],
    *,
    fast_model: str | None = None,
    smart_model: str | None = None,
    strategic_model: str | None = None,
) -> bool:
    requested = {
        "FAST_LLM": fast_model,
        "SMART_LLM": smart_model,
        "STRATEGIC_LLM": strategic_model,
    }
    changed = False
    for role, value in requested.items():
        if value is None or not value.strip():
            continue
        normalized = _normalized_role_value(value)
        if config.get(role) != normalized:
            config[role] = normalized
            changed = True
    return changed


def _write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    mode = path.stat().st_mode & 0o777
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        json.dump(data, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.chmod(mode)
    os.replace(temporary, path)


def _markdown_report(results: list[dict[str, Any]]) -> str:
    lines = [
        "## GPT Researcher model validation",
        "",
        "| Role | OpenRouter model | Context | Max output | Input $/M | Output $/M |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for result in results:
        lines.append(
            "| {role} | `{model_id}` | {context_length:,} | {max_output} | "
            "{prompt:.4f} | {completion:.4f} |".format(
                role=result["role"],
                model_id=result["model_id"],
                context_length=result["context_length"],
                max_output=(
                    f"{result['max_completion_tokens']:,}"
                    if isinstance(result["max_completion_tokens"], int)
                    else "unknown"
                ),
                prompt=result["prompt_usd_per_million"],
                completion=result["completion_usd_per_million"],
            )
        )
    lines.extend(
        [
            "",
            "This is a catalog compatibility check, not a quality benchmark or model recommendation.",
            "The embedding model is intentionally outside this updater because changing it requires a vector-index migration.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--catalog-url", default=DEFAULT_CATALOG_URL)
    parser.add_argument("--catalog-file", type=Path)
    parser.add_argument("--fast-model")
    parser.add_argument("--smart-model")
    parser.add_argument("--strategic-model")
    parser.add_argument("--github-summary", action="store_true")
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValidationError("GPT Researcher configuration must be a JSON object")
    changed = update_roles(
        config,
        fast_model=args.fast_model,
        smart_model=args.smart_model,
        strategic_model=args.strategic_model,
    )
    catalog = _load_catalog(
        catalog_url=args.catalog_url,
        catalog_file=args.catalog_file,
    )
    results = validate_role_models(config, catalog)
    if changed:
        _write_json_atomic(args.config, config)

    report = _markdown_report(results)
    print(report, end="")
    if args.github_summary:
        summary_path = os.getenv("GITHUB_STEP_SUMMARY")
        if not summary_path:
            raise ValidationError("GITHUB_STEP_SUMMARY is unavailable")
        with Path(summary_path).open("a", encoding="utf-8") as handle:
            handle.write(report)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValidationError as error:
        raise SystemExit(f"model validation failed: {error}") from error
