from __future__ import annotations

import argparse
import asyncio
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any


REPORT_TYPES = {
    "research_report",
    "detailed_report",
    "deep",
}


def _safe_sources(raw_sources: list[dict[str, Any]], raw_urls: list[str]) -> list[dict[str, str]]:
    """Return citation metadata without duplicating scraped document bodies."""

    sources: list[dict[str, str]] = []
    seen: set[str] = set()
    for source in raw_sources:
        if not isinstance(source, dict):
            continue
        url = source.get("url") or source.get("href")
        if not isinstance(url, str) or not url.startswith(("https://", "http://")):
            continue
        if url in seen:
            continue
        title = source.get("title")
        sources.append(
            {
                "title": title[:500] if isinstance(title, str) else "",
                "url": url[:4_096],
            }
        )
        seen.add(url)
    for url in raw_urls:
        if (
            isinstance(url, str)
            and url.startswith(("https://", "http://"))
            and url not in seen
        ):
            sources.append({"title": "", "url": url[:4_096]})
            seen.add(url)
    return sources[:200]


async def conduct(payload: dict[str, Any]) -> dict[str, Any]:
    from gpt_researcher import GPTResearcher

    query = payload["query"]
    report_type = payload["report_type"]
    if report_type not in REPORT_TYPES:
        raise ValueError("unsupported report type")

    researcher = GPTResearcher(
        query=query,
        report_type=report_type,
        report_format="markdown",
        report_source="web",
        verbose=False,
        max_subtopics=3,
        mcp_strategy="disabled",
    )
    await researcher.conduct_research()
    report = await researcher.write_report()
    return {
        "report": report,
        "sources": _safe_sources(
            researcher.get_research_sources(),
            researcher.get_source_urls(),
        ),
        "estimated_cost_usd": researcher.get_costs(),
        "step_costs_usd": researcher.get_step_costs(),
    }


def _write_exclusive(path: Path, payload: dict[str, Any]) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise RuntimeError("worker output is not a regular file")
        with os.fdopen(descriptor, "w", encoding="utf-8", closefd=False) as handle:
            json.dump(payload, handle, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        os.close(descriptor)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("request must be an object")
        result = asyncio.run(conduct(payload))
        _write_exclusive(args.output, {"ok": True, "result": result})
        return 0
    except Exception as error:
        # The parent returns a stable public error and keeps this diagnostic in
        # pod logs. Never serialize environment variables, request headers, or
        # exception locals to the response file.
        # Third-party exceptions can echo a query, document body, URL query
        # string, or provider response. Keep the durable pod log useful without
        # persisting any user-supplied research content.
        print(f"research worker failed: {type(error).__name__}", file=sys.stderr)
        try:
            _write_exclusive(
                args.output,
                {"ok": False, "error_type": type(error).__name__},
            )
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
