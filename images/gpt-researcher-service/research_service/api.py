from __future__ import annotations

import asyncio
import hmac
import json
import logging
import os
import secrets
import sys
import time
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .settings import Settings

log = logging.getLogger("research_service")
settings = Settings.from_environment()
research_slot = asyncio.Semaphore(1)
started_at = time.monotonic()

metrics = {
    "requests_total": 0,
    "success_total": 0,
    "failure_total": 0,
    "timeout_total": 0,
    "busy_total": 0,
    "active": 0,
    "duration_seconds_total": 0.0,
    "estimated_cost_usd_total": 0.0,
}


class ResearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(
        min_length=10,
        description=(
            "A self-contained research question. Calling this endpoint incurs "
            "OpenRouter usage charges."
        ),
    )
    report_type: Literal["research_report", "detailed_report", "deep"] = Field(
        default="research_report",
        description=(
            "research_report is the normal default; detailed_report and deep "
            "cost more and take longer."
        ),
    )

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        value = value.strip()
        if len(value) > settings.max_query_chars:
            raise ValueError(
                f"query exceeds the {settings.max_query_chars}-character limit"
            )
        return value


class Source(BaseModel):
    title: str
    url: str


class ResearchResponse(BaseModel):
    report: str
    sources: list[Source]
    estimated_cost_usd: float
    duration_seconds: float
    request_id: str


def require_bearer(authorization: str | None = Header(default=None)) -> None:
    prefix = "Bearer "
    candidate = (
        authorization[len(prefix) :]
        if isinstance(authorization, str) and authorization.startswith(prefix)
        else ""
    )
    if not hmac.compare_digest(candidate, settings.api_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )


app = FastAPI(
    title="GPT Researcher",
    description=(
        "Internal, read-only deep research using GPT Researcher and SearXNG. "
        "Each call incurs OpenRouter usage charges; never call it for ordinary "
        "conversation or without a research request from the user."
    ),
    version="0.16.0-4",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


@app.get("/health", include_in_schema=False)
async def health() -> dict[str, object]:
    return {
        "status": "ok",
        "active_research": bool(metrics["active"]),
        "uptime_seconds": round(time.monotonic() - started_at, 3),
    }


@app.get(
    "/openapi.json",
    include_in_schema=False,
    dependencies=[Depends(require_bearer)],
)
async def authenticated_openapi() -> dict:
    return app.openapi()


def _prometheus_lines() -> str:
    names = {
        "requests_total": "gpt_researcher_requests_total",
        "success_total": "gpt_researcher_success_total",
        "failure_total": "gpt_researcher_failure_total",
        "timeout_total": "gpt_researcher_timeout_total",
        "busy_total": "gpt_researcher_busy_total",
        "active": "gpt_researcher_active",
        "duration_seconds_total": "gpt_researcher_duration_seconds_total",
        "estimated_cost_usd_total": "gpt_researcher_estimated_cost_usd_total",
    }
    lines = []
    for internal, exported in names.items():
        metric_type = "gauge" if internal == "active" else "counter"
        lines.extend(
            [
                f"# TYPE {exported} {metric_type}",
                f"{exported} {metrics[internal]}",
            ]
        )
    return "\n".join(lines) + "\n"


@app.get(
    "/metrics",
    include_in_schema=False,
)
async def prometheus_metrics() -> Response:
    return Response(_prometheus_lines(), media_type="text/plain; version=0.0.4")


async def _terminate(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    process.terminate()
    try:
        await asyncio.wait_for(process.wait(), timeout=10)
    except TimeoutError:
        process.kill()
        await process.wait()


async def _run_worker(request_id: str, payload: ResearchRequest) -> dict:
    output_dir = Path(settings.worker_output_dir).resolve()
    output_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    output_dir.chmod(0o700)
    output_path = output_dir / f"{request_id}.json"

    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "research_service.worker",
        "--output",
        str(output_path),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
        env=os.environ.copy(),
    )
    request_bytes = payload.model_dump_json().encode("utf-8")
    try:
        _, stderr = await asyncio.wait_for(
            process.communicate(input=request_bytes),
            timeout=settings.timeout_seconds,
        )
    except TimeoutError:
        await _terminate(process)
        raise

    if stderr:
        log.warning(
            "research worker %s exited %s: %s",
            request_id,
            process.returncode,
            stderr.decode("utf-8", errors="replace")[-4_000:],
        )
    try:
        with output_path.open("r", encoding="utf-8") as handle:
            result = json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError, OSError) as error:
        raise RuntimeError("research worker did not produce a valid result") from error
    finally:
        output_path.unlink(missing_ok=True)

    if process.returncode != 0 or not result.get("ok"):
        raise RuntimeError(
            f"research worker failed ({result.get('error_type', 'unknown')})"
        )
    return result["result"]


@app.post(
    "/v1/research",
    operation_id="conduct_deep_research",
    summary="Conduct source-backed web research",
    description=(
        "Use only when the user explicitly asks for deep or comprehensive "
        "research. This can take several minutes and incurs OpenRouter charges. "
        "Do not use for ordinary factual lookups; use normal web search instead."
    ),
    response_model=ResearchResponse,
    dependencies=[Depends(require_bearer)],
)
async def research(payload: ResearchRequest) -> ResearchResponse:
    if research_slot.locked():
        metrics["busy_total"] += 1
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="another research request is already running",
            headers={"Retry-After": "60"},
        )

    request_id = secrets.token_hex(12)
    metrics["requests_total"] += 1
    started = time.monotonic()
    async with research_slot:
        metrics["active"] = 1
        try:
            result = await _run_worker(request_id, payload)
            report = result.get("report")
            if not isinstance(report, str) or not report.strip():
                raise RuntimeError("research worker returned an empty report")
            if len(report) > settings.max_report_chars:
                raise RuntimeError("research report exceeded the configured limit")
            duration = time.monotonic() - started
            cost = max(float(result.get("estimated_cost_usd") or 0.0), 0.0)
            metrics["success_total"] += 1
            metrics["duration_seconds_total"] += duration
            metrics["estimated_cost_usd_total"] += cost
            return ResearchResponse(
                report=report,
                sources=result.get("sources") or [],
                estimated_cost_usd=cost,
                duration_seconds=round(duration, 3),
                request_id=request_id,
            )
        except TimeoutError as error:
            metrics["timeout_total"] += 1
            metrics["failure_total"] += 1
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="research exceeded the configured time limit",
            ) from error
        except Exception as error:
            metrics["failure_total"] += 1
            log.exception("research request %s failed", request_id)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"research failed; request id {request_id}",
            ) from error
        finally:
            metrics["active"] = 0
