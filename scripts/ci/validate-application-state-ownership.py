#!/usr/bin/env python3
"""Reject known regressions that make Git overwrite application-owned state."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def read(relative: str) -> str:
    return (REPO_ROOT / relative).read_text(encoding="utf-8")


def main() -> int:
    errors: list[str] = []

    retired = (
        "apps/gpt-researcher/kustomization.yaml",
        "apps/personal-assistant/kustomization.yaml",
        "images/gpt-researcher-service/Dockerfile",
        "images/personal-assistant-mcp/package.json",
        "images/todoist-mcp/package.json",
        "scripts/configure-personal-assistant.py",
        "scripts/update_gpt_researcher_models.py",
        "apps/open-webui/config/reconcile.py",
        "apps/open-webui/config/migrate_embeddings.py",
    )
    for relative in retired:
        if (REPO_ROOT / relative).exists():
            errors.append(f"retired state reconciler or custom MCP artifact exists: {relative}")

    open_webui = read("apps/open-webui/deployments.yaml")
    for forbidden in (
        "initContainers:",
        "reconcile-security-policy",
        "migrate-gemini-embeddings",
        "RAG_EMBEDDING_CONTENT_PREFIX",
        "RAG_EMBEDDING_QUERY_PREFIX",
        "gpt-researcher-secrets",
        "personal-assistant-secrets",
    ):
        if forbidden in open_webui:
            errors.append(
                f"Open WebUI deployment contains application-state ownership regression: {forbidden}"
            )

    audiobookshelf = read("apps/audiobookshelf/deployment.yaml")
    for forbidden in (
        "postStart:",
        "AUDIOBOOKSHELF_BOOTSTRAP_PASSWORD",
        "AUDIOBOOKSHELF_OIDC_CLIENT_SECRET",
        "gitops-bootstrap-complete",
        "audiobookshelf-bootstrap",
    ):
        if forbidden in audiobookshelf:
            errors.append(
                f"Audiobookshelf deployment would overwrite application state: {forbidden}"
            )

    mcphub = read("apps/mcphub/workloads.yaml")
    for operational_setting in (
        "FAST_LLM",
        "SMART_LLM",
        "STRATEGIC_LLM",
        "MAX_ITERATIONS",
        "VIKUNJA_API_TOKEN",
        "GOOGLE_REFRESH_TOKEN",
    ):
        if operational_setting in mcphub:
            errors.append(
                "MCPHub operational setting must live in its database, not its "
                f"workload manifest: {operational_setting}"
            )

    package_image = read("images/mcphub-gptr/Dockerfile")
    required_package_evidence = (
        "https://github.com/assafelovic/gptr-mcp.git",
        "@modelcontextprotocol/server-filesystem@",
        "@eargollo/vikunja-mcp@",
        "@klodr/gmail-mcp@",
        "@cocal/google-calendar-mcp@",
        "mcp-arr-server@",
        "navidrome-mcp@",
        "audiobookshelf-mcp[mcp]==",
        "https://github.com/aserper/jellyseerr-mcp.git",
        "https://github.com/grafana/mcp-grafana.git",
        "https://github.com/containers/kubernetes-mcp-server.git",
        "https://github.com/github/github-mcp-server.git",
        "https://github.com/s-stefanov/actual-mcp.git",
    )
    for required in required_package_evidence:
        if required not in package_image:
            errors.append(f"reviewed MCP package pin is missing: {required}")

    code_image = read("images/mcp-v8/Dockerfile")
    for required in (
        "https://github.com/r33drichards/mcp-js/releases/download/",
        "sha256sum --check --strict",
        "USER 65532:65532",
    ):
        if required not in code_image:
            errors.append(f"sandboxed code-execution image guard is missing: {required}")

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print("Application-state ownership policy is satisfied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
