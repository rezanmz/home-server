from __future__ import annotations

import os
from dataclasses import dataclass


def _positive_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as error:
        raise RuntimeError(f"{name} must be an integer") from error
    if value < 1:
        raise RuntimeError(f"{name} must be positive")
    return value


@dataclass(frozen=True)
class Settings:
    api_token: str
    timeout_seconds: int
    max_query_chars: int
    max_report_chars: int
    worker_output_dir: str

    @classmethod
    def from_environment(cls) -> "Settings":
        api_token = os.getenv("RESEARCH_API_TOKEN", "")
        if len(api_token) < 32:
            raise RuntimeError("RESEARCH_API_TOKEN must contain at least 32 characters")
        return cls(
            api_token=api_token,
            timeout_seconds=_positive_int("RESEARCH_TIMEOUT_SECONDS", 900),
            max_query_chars=_positive_int("RESEARCH_MAX_QUERY_CHARS", 4_000),
            max_report_chars=_positive_int("RESEARCH_MAX_REPORT_CHARS", 750_000),
            worker_output_dir=os.getenv(
                "RESEARCH_WORKER_OUTPUT_DIR", "/tmp/research-service"
            ),
        )
