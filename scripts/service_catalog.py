#!/usr/bin/env python3
"""Render and validate the cluster's cross-service integration catalog."""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


REPO_ROOT = Path(__file__).resolve().parents[1]
CI_DIR = REPO_ROOT / "scripts" / "ci"
sys.path.insert(0, str(CI_DIR))

from yaml_documents import ManifestError, load_documents  # noqa: E402


CATALOG_CONFIG_PATH = REPO_ROOT / "catalog" / "cluster.yaml"
LEGACY_CATALOG_PATH = REPO_ROOT / "catalog" / "services.yaml"
CATALOG_API_VERSION = "catalog.reza.network/v1alpha1"
CATALOG_SEARCH_ROOTS = (
    REPO_ROOT / "apps",
    REPO_ROOT / "infrastructure",
    REPO_ROOT / "clusters",
)
HOMEPAGE_PATH = REPO_ROOT / "apps" / "homepage" / "config" / "services.yaml"
CLOUDFLARE_KUSTOMIZATION = REPO_ROOT / "apps" / "cloudflare-ddns" / "kustomization.yaml"
BLOCKY_CONFIG = REPO_ROOT / "apps" / "blocky" / "config.yml"
ROOT_KUSTOMIZATION = REPO_ROOT / "clusters" / "home-server" / "kustomization.yaml"
AUTHENTIK_BLUEPRINTS = REPO_ROOT / "apps" / "authentik" / "application-blueprints.yaml"
AUTHENTIK_WORKER_PATCH = (
    REPO_ROOT / "apps" / "authentik" / "generated-oidc-worker-env.yaml"
)

DDNS_START = "      # BEGIN SERVICE CATALOG GENERATED DOMAINS"
DDNS_END = "      # END SERVICE CATALOG GENERATED DOMAINS"
BLOCKY_START = "    # BEGIN SERVICE CATALOG GENERATED MAPPINGS"
BLOCKY_END = "    # END SERVICE CATALOG GENERATED MAPPINGS"

ALLOWED_AUTH_MODES = {"forward-auth", "native", "none", "oidc"}
ALLOWED_DATA_CLASSES = {
    "longhorn",
    "longhorn-observability",
    "mixed",
    "nfs-reproducible",
    "platform",
    "stateless",
}
ALLOWED_PROTECTION = {
    "excluded-observability",
    "excluded-reproducible",
    "longhorn-and-restic-b2",
    "longhorn-b2",
    "not-applicable",
    "platform-managed",
}
ALLOWED_OBSERVABILITY = {"kubernetes", "metrics", "none", "platform"}
ALLOWED_PLACEMENT = {
    "beelink",
    "every-node",
    "floating",
    "platform",
    "raspberrypi",
}
DNS_LABEL_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
AUTHENTIK_IDENTIFIER_PATTERN = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9_.:-]{0,126}[A-Za-z0-9])?$"
)


class CatalogError(RuntimeError):
    """Raised for catalog schema, integration, or generated-file drift."""


def repo_path(value: str) -> Path:
    """Return a repository-relative path without permitting path traversal."""

    candidate = (REPO_ROOT / value).resolve()
    try:
        candidate.relative_to(REPO_ROOT)
    except ValueError as error:
        raise CatalogError(f"path escapes the repository: {value}") from error
    return candidate


def is_dns_name(value: str) -> bool:
    """Return whether value is a lowercase DNS name accepted by the generators."""

    if len(value) > 253 or value.endswith("."):
        return False
    return all(DNS_LABEL_PATTERN.fullmatch(label) for label in value.split("."))


def is_same_host_https_url(value: str, hostname: str) -> bool:
    """Reject credentials, ports, fragments, and cross-origin generated URLs."""

    parsed = urlparse(value)
    return (
        parsed.scheme == "https"
        and parsed.netloc == hostname
        and (not parsed.path or parsed.path.startswith("/"))
        and not parsed.fragment
    )


def load_single_document(path: Path) -> dict[str, Any]:
    documents = [document for document in load_documents(path) if document is not None]
    if len(documents) != 1 or not isinstance(documents[0], dict):
        raise CatalogError(f"{path.relative_to(REPO_ROOT)} must contain one YAML mapping")
    return documents[0]


def load_catalog() -> dict[str, Any]:
    config = load_single_document(CATALOG_CONFIG_PATH)
    config_unknown = set(config) - {"apiVersion", "kind", "metadata", "spec"}
    if config_unknown:
        raise CatalogError(
            "catalog/cluster.yaml contains unknown field(s): "
            + ", ".join(sorted(config_unknown))
        )
    if config.get("apiVersion") != CATALOG_API_VERSION:
        raise CatalogError(
            f"catalog/cluster.yaml apiVersion must be {CATALOG_API_VERSION}"
        )
    if config.get("kind") != "ClusterCatalog":
        raise CatalogError("catalog/cluster.yaml kind must be ClusterCatalog")
    metadata = config.get("metadata")
    spec = config.get("spec")
    if not isinstance(metadata, dict) or not isinstance(spec, dict):
        raise CatalogError("catalog/cluster.yaml requires metadata and spec mappings")
    metadata_unknown = set(metadata) - {"name"}
    if metadata_unknown:
        raise CatalogError(
            "catalog/cluster.yaml metadata contains unknown field(s): "
            + ", ".join(sorted(metadata_unknown))
        )
    spec_unknown = set(spec) - {"authentik", "dns", "domain", "homepage"}
    if spec_unknown:
        raise CatalogError(
            "catalog/cluster.yaml spec contains unknown field(s): "
            + ", ".join(sorted(spec_unknown))
        )

    catalog: dict[str, Any] = {
        "version": 2,
        "domain": spec.get("domain"),
        "dns": spec.get("dns"),
        "homepage": spec.get("homepage"),
        "authentik": spec.get("authentik"),
        "registrationExclusions": [],
        "services": [],
    }
    descriptor_paths = sorted(
        path
        for root in CATALOG_SEARCH_ROOTS
        for path in root.rglob("*.catalog.yaml")
        if path.is_file()
    )
    if not descriptor_paths:
        raise CatalogError("no colocated *.catalog.yaml descriptors were found")

    for path in descriptor_paths:
        documents = [document for document in load_documents(path) if document is not None]
        if len(documents) != 1 or not isinstance(documents[0], dict):
            raise CatalogError(
                f"{path.relative_to(REPO_ROOT)} must contain one YAML mapping"
            )
        document = documents[0]
        relative = path.relative_to(REPO_ROOT)
        unknown = set(document) - {"apiVersion", "kind", "metadata", "spec"}
        if unknown:
            raise CatalogError(
                f"{relative} contains unknown top-level field(s): "
                + ", ".join(sorted(unknown))
            )
        if document.get("apiVersion") != CATALOG_API_VERSION:
            raise CatalogError(
                f"{relative} apiVersion must be {CATALOG_API_VERSION}"
            )
        metadata = document.get("metadata")
        spec = document.get("spec")
        if not isinstance(metadata, dict) or not isinstance(spec, dict):
            raise CatalogError(f"{relative} requires metadata and spec mappings")
        metadata_unknown = set(metadata) - {"name"}
        if metadata_unknown:
            raise CatalogError(
                f"{relative} metadata contains unknown field(s): "
                + ", ".join(sorted(metadata_unknown))
            )
        service_id = metadata.get("name")
        if not isinstance(service_id, str) or not service_id:
            raise CatalogError(f"{relative} metadata.name must be a non-empty string")

        kind = document.get("kind")
        if kind == "Service":
            service = dict(spec)
            service["id"] = service_id
            service["path"] = str(path.parent.relative_to(REPO_ROOT))
            service["_source"] = str(relative)
            catalog["services"].append(service)
        elif kind == "CatalogExclusion":
            catalog["registrationExclusions"].append(
                {
                    "path": str(path.parent.relative_to(REPO_ROOT)),
                    "reason": spec.get("reason"),
                    "_source": str(relative),
                }
            )
        else:
            raise CatalogError(
                f"{relative} kind must be Service or CatalogExclusion"
            )

    return catalog


def yaml_from_json(value: Any) -> str:
    """Use the CI-pinned yq formatter instead of an unpinned Python YAML module."""

    if shutil.which("yq") is None:
        raise CatalogError("required command is not installed: yq")
    process = subprocess.run(
        ["yq", "eval", "--prettyPrint", "--output-format=yaml", "."],
        input=json.dumps(value, ensure_ascii=False),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if process.returncode != 0:
        detail = process.stderr.strip() or "unknown yq error"
        raise CatalogError(f"yq could not format generated YAML: {detail}")
    return process.stdout


def replace_generated_region(
    text: str,
    *,
    start_marker: str,
    end_marker: str,
    generated_lines: list[str],
    path: Path,
) -> str:
    lines = text.splitlines()
    try:
        start = lines.index(start_marker)
        end = lines.index(end_marker)
    except ValueError as error:
        relative = path.relative_to(REPO_ROOT)
        raise CatalogError(f"{relative} is missing its service-catalog markers") from error
    if end <= start:
        raise CatalogError(
            f"{path.relative_to(REPO_ROOT)} has reversed service-catalog markers"
        )
    return "\n".join(lines[: start + 1] + generated_lines + lines[end:]) + "\n"


def services(catalog: dict[str, Any]) -> list[dict[str, Any]]:
    value = catalog.get("services")
    if not isinstance(value, list):
        raise CatalogError("catalog.services must be a list")
    return value


def homepage_document(catalog: dict[str, Any]) -> list[dict[str, Any]]:
    homepage = catalog.get("homepage")
    if not isinstance(homepage, dict) or not isinstance(homepage.get("groups"), list):
        raise CatalogError("catalog.homepage.groups must be a list")

    grouped: dict[str, list[tuple[int, str, dict[str, Any]]]] = {
        group: [] for group in homepage["groups"] if isinstance(group, str)
    }
    for service in services(catalog):
        card = service.get("homepage")
        if not isinstance(card, dict):
            continue
        if card.get("enabled", True) is False:
            continue
        group = card.get("group")
        if group not in grouped:
            continue

        details: dict[str, Any] = {
            "icon": card.get("icon"),
        }
        web = service.get("web")
        if isinstance(web, dict) and card.get("link", True):
            details["href"] = f"https://{web.get('hostname')}/"
        details["description"] = card.get("description")

        workload = service.get("workload")
        if isinstance(workload, dict):
            details["namespace"] = workload.get("namespace")
            if workload.get("app") is not None:
                details["app"] = workload["app"]
            elif workload.get("podSelector") is not None:
                details["podSelector"] = workload["podSelector"]

        order = card.get("order", 1000)
        grouped[group].append((order, str(service.get("name")), {service.get("name"): details}))

    return [
        {
            group: [
                card
                for _, _, card in sorted(
                    cards, key=lambda item: (item[0], item[1].casefold())
                )
            ]
        }
        for group, cards in grouped.items()
    ]


def dns_hostnames(catalog: dict[str, Any], key: str) -> list[str]:
    dns = catalog.get("dns")
    if not isinstance(dns, dict):
        raise CatalogError("catalog.dns must be a mapping")
    names = list(dns.get("extraPublicNames", [])) if key == "cloudflare" else []
    for service in services(catalog):
        web = service.get("web")
        if not isinstance(web, dict):
            continue
        web_dns = web.get("dns")
        if isinstance(web_dns, dict) and web_dns.get(key) is True:
            names.append(web.get("hostname"))
    return sorted({name for name in names if isinstance(name, str)})


def authentik_secret_key(service_id: str) -> str:
    normalized = re.sub(r"[^A-Z0-9]+", "_", service_id.upper()).strip("_")
    return f"AUTHENTIK_OIDC_{normalized}_CLIENT_SECRET"


def yaml_string(value: str) -> str:
    """Return a deterministic double-quoted YAML scalar."""

    return json.dumps(value, ensure_ascii=False)


MANAGED_SCOPE_MAPPINGS = {
    "openid": "goauthentik.io/providers/oauth2/scope-openid",
    "email": "goauthentik.io/providers/oauth2/scope-email",
    "profile": "goauthentik.io/providers/oauth2/scope-profile",
    "offline_access": "goauthentik.io/providers/oauth2/scope-offline_access",
}


def authentik_oidc_blueprint(service: dict[str, Any], auth: dict[str, Any]) -> str:
    service_id = str(service["id"])
    name = str(service["name"])
    application = auth["application"]
    client = auth["client"]
    slug = str(application["slug"])
    provider_id = f"{slug}-provider"
    blueprint_name = str(auth.get("blueprintName", f"{name} OIDC"))
    provider_name = str(auth.get("providerName", f"Provider for {name}"))

    lines = [
        "version: 1",
        "metadata:",
        f"  name: {yaml_string(blueprint_name)}",
        "  labels:",
        '    blueprints.goauthentik.io/instantiate: "true"',
        "entries:",
    ]
    for mapping in auth.get("claimMappings", []):
        lines.extend(
            [
                "  - model: authentik_providers_oauth2.scopemapping",
                f"    id: {mapping['id']}",
                "    identifiers:",
                f"      name: {yaml_string(str(mapping['name']))}",
                "    attrs:",
                f"      scope_name: {mapping['scope']}",
                f"      description: {yaml_string(str(mapping['description']))}",
                "      expression: |",
            ]
        )
        expression = str(mapping["expression"]).rstrip("\n")
        lines.extend(f"        {line}" for line in expression.splitlines())

    lines.extend(
        [
            "  - model: authentik_providers_oauth2.oauth2provider",
            f"    id: {provider_id}",
            "    identifiers:",
            f"      name: {yaml_string(provider_name)}",
            "    attrs:",
            "      authorization_flow: !Find [authentik_flows.flow, [slug, default-provider-authorization-implicit-consent]]",
            "      invalidation_flow: !Find [authentik_flows.flow, [slug, default-provider-invalidation-flow]]",
            f"      client_type: {client['type']}",
            f"      client_id: {yaml_string(str(client['id']))}",
        ]
    )
    if client["type"] == "confidential":
        lines.append(
            f"      client_secret: !Env [{authentik_secret_key(service_id)}, null]"
        )
    grants = ", ".join(str(item) for item in client["grantTypes"])
    lines.extend(
        [
            f"      grant_types: [{grants}]",
            "      issuer_mode: per_provider",
            "      include_claims_in_id_token: true",
            "      redirect_uris:",
        ]
    )
    for redirect in client["redirectUris"]:
        lines.extend(
            [
                "        - matching_mode: strict",
                f"          url: {yaml_string(str(redirect['url']))}",
                f"          redirect_uri_type: {redirect['type']}",
            ]
        )
    provider_logout = client.get("providerLogout")
    if isinstance(provider_logout, dict):
        lines.extend(
            [
                f"      logout_uri: {yaml_string(str(provider_logout['url']))}",
                f"      logout_method: {provider_logout['method']}",
            ]
        )
    lines.append("      property_mappings:")
    for scope in client["scopes"]:
        managed = MANAGED_SCOPE_MAPPINGS[scope]
        lines.append(
            "        - !Find "
            f"[authentik_providers_oauth2.scopemapping, [managed, {managed}]]"
        )
    for mapping in auth.get("claimMappings", []):
        lines.append(f"        - !KeyOf {mapping['id']}")
    lines.extend(
        [
            "      signing_key: !Find [authentik_crypto.certificatekeypair, [name, authentik Self-signed Certificate]]",
            "  - model: authentik_core.application",
            "    identifiers:",
            f"      slug: {slug}",
            "    attrs:",
            f"      name: {yaml_string(name)}",
            f"      provider: !KeyOf {provider_id}",
        ]
    )
    launch_url = application.get("launchUrl")
    if isinstance(launch_url, str):
        lines.append(f"      meta_launch_url: {yaml_string(launch_url)}")
    return "\n".join(lines) + "\n"


def authentik_forward_blueprint(
    entries: list[tuple[dict[str, Any], dict[str, Any]]],
) -> str:
    lines = [
        "version: 1",
        "metadata:",
        '  name: "Forward-auth applications"',
        "  labels:",
        '    blueprints.goauthentik.io/instantiate: "true"',
        "entries:",
    ]
    provider_ids: list[str] = []
    for service, auth in entries:
        name = str(service["name"])
        hostname = str(service["web"]["hostname"])
        application = auth["application"]
        slug = str(application["slug"])
        provider_id = f"{slug}-provider"
        provider_ids.append(provider_id)
        provider_name = str(auth.get("providerName", f"Provider for {name}"))
        launch_url = str(application.get("launchUrl", f"https://{hostname}/"))
        lines.extend(
            [
                "  - model: authentik_providers_proxy.proxyprovider",
                f"    id: {provider_id}",
                "    identifiers:",
                f"      name: {yaml_string(provider_name)}",
                "    attrs:",
                "      authorization_flow: !Find [authentik_flows.flow, [slug, default-provider-authorization-implicit-consent]]",
                "      invalidation_flow: !Find [authentik_flows.flow, [slug, default-provider-invalidation-flow]]",
                "      mode: forward_single",
                f"      external_host: {yaml_string(f'https://{hostname}')}",
                "  - model: authentik_core.application",
                "    identifiers:",
                f"      slug: {slug}",
                "    attrs:",
                f"      name: {yaml_string(name)}",
                f"      provider: !KeyOf {provider_id}",
                f"      meta_launch_url: {yaml_string(launch_url)}",
            ]
        )
        if auth.get("profile") == "authentik-forward-single-v2":
            allowed_groups = sorted(auth.get("allowedGroups", []))
            # The policy identity must be derived from the immutable
            # application slug only, never from the mutable display name:
            # renaming the service must keep the policy and its binding
            # stable so the blueprint updates them in place.
            policy_id = f"{slug}-allowed-groups"
            group_names = json.dumps(list(allowed_groups), ensure_ascii=False)
            lines.extend(
                [
                    "  - model: authentik_policies_expression.expressionpolicy",
                    f"    id: {policy_id}",
                    "    identifiers:",
                    f"      name: {yaml_string(f'{slug} allowed groups')}",
                    "    attrs:",
                    "      execution_logging: false",
                    "      expression: |",
                    f"        return any(ak_is_group_member(request.user, name=group) for group in {group_names})",
                    "  - model: authentik_policies.policybinding",
                    "    identifiers:",
                    f"      policy: !KeyOf {policy_id}",
                    f"      target: !Find [authentik_core.application, [slug, {slug}]]",
                    "      order: 0",
                ]
            )

    lines.extend(
        [
            "  - model: authentik_outposts.outpost",
            "    identifiers:",
            "      name: authentik Embedded Outpost",
            "    attrs:",
            "      providers:",
        ]
    )
    lines.extend(f"        - !KeyOf {provider_id}" for provider_id in provider_ids)
    lines.append("")
    return "\n".join(lines)


def authentik_blueprints_document(catalog: dict[str, Any]) -> str:
    entries: list[tuple[str, str]] = []
    forward_auth_entries: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for service in sorted(services(catalog), key=lambda item: str(item.get("id"))):
        auth = service.get("web", {}).get("auth", {})
        mode = auth.get("mode")
        if mode == "oidc":
            entries.append(
                (f"{service['id']}.yaml", authentik_oidc_blueprint(service, auth))
            )
        elif mode == "forward-auth":
            forward_auth_entries.append((service, auth))

    if forward_auth_entries:
        entries.append(
            (
                "forward-auth.yaml",
                authentik_forward_blueprint(forward_auth_entries),
            )
        )
    entries.sort(key=lambda item: item[0])

    lines = [
        "# Generated from colocated *.catalog.yaml descriptors by scripts/service_catalog.py.",
        "# Do not edit this file directly; run: python3 scripts/service_catalog.py render",
        "apiVersion: v1",
        "kind: ConfigMap",
        "metadata:",
        "  name: authentik-application-blueprints",
        "  namespace: apps",
        "data:",
    ]
    for key, blueprint in entries:
        lines.append(f"  {key}: |")
        lines.extend(f"    {line}" for line in blueprint.rstrip("\n").splitlines())
    return "\n".join(lines) + "\n"


def authentik_worker_patch(catalog: dict[str, Any]) -> str:
    authentik = catalog.get("authentik", {})
    secret = authentik.get("providerSecret", {})
    entries = [
        service
        for service in services(catalog)
        if service.get("web", {}).get("auth", {}).get("mode") == "oidc"
        and service["web"]["auth"].get("client", {}).get("type") == "confidential"
    ]
    lines = [
        "# Generated from colocated *.catalog.yaml descriptors by scripts/service_catalog.py.",
        "# Do not edit this file directly; run: python3 scripts/service_catalog.py render",
        "apiVersion: apps/v1",
        "kind: Deployment",
        "metadata:",
        "  name: authentik",
        f"  namespace: {authentik.get('namespace', 'apps')}",
        "spec:",
        "  template:",
        "    spec:",
        "      containers:",
        "        - name: worker",
        "          env:",
    ]
    for service in sorted(entries, key=lambda item: str(item["id"])):
        key = authentik_secret_key(str(service["id"]))
        lines.extend(
            [
                f"            - name: {key}",
                "              valueFrom:",
                "                secretKeyRef:",
                f"                  name: {secret.get('name')}",
                f"                  key: {key}",
            ]
        )
    return "\n".join(lines) + "\n"


def generated_outputs(catalog: dict[str, Any]) -> dict[Path, str]:
    header = (
        "# Generated from colocated *.catalog.yaml descriptors by scripts/service_catalog.py.\n"
        "# Do not edit this file directly; run: python3 scripts/service_catalog.py render\n"
    )
    homepage = header + yaml_from_json(homepage_document(catalog))

    ddns_names = dns_hostnames(catalog, "cloudflare")
    ddns_line = f"      - DOMAINS={','.join(ddns_names)}"
    cloudflare = replace_generated_region(
        CLOUDFLARE_KUSTOMIZATION.read_text(),
        start_marker=DDNS_START,
        end_marker=DDNS_END,
        generated_lines=[ddns_line],
        path=CLOUDFLARE_KUSTOMIZATION,
    )

    dns = catalog.get("dns", {})
    split_address = dns.get("splitHorizonAddress")
    blocky_lines = [
        f"    {hostname}: {split_address}"
        for hostname in dns_hostnames(catalog, "splitHorizon")
    ]
    blocky = replace_generated_region(
        BLOCKY_CONFIG.read_text(),
        start_marker=BLOCKY_START,
        end_marker=BLOCKY_END,
        generated_lines=blocky_lines,
        path=BLOCKY_CONFIG,
    )

    return {
        HOMEPAGE_PATH: homepage,
        CLOUDFLARE_KUSTOMIZATION: cloudflare,
        BLOCKY_CONFIG: blocky,
        AUTHENTIK_BLUEPRINTS: authentik_blueprints_document(catalog),
        AUTHENTIK_WORKER_PATCH: authentik_worker_patch(catalog),
    }


def render(catalog: dict[str, Any]) -> None:
    errors: list[str] = []
    validate_catalog_structure(catalog, errors)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        raise CatalogError(
            f"catalog input validation failed with {len(errors)} error(s); "
            "no generated files were changed"
        )

    outputs = generated_outputs(catalog)
    for path, content in outputs.items():
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f".{path.name}.",
                delete=False,
            ) as handle:
                handle.write(content)
                temporary = Path(handle.name)
            os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        print(f"Rendered {path.relative_to(REPO_ROOT)}")


def validate_generated_outputs(catalog: dict[str, Any], errors: list[str]) -> None:
    for path, expected in generated_outputs(catalog).items():
        if not path.is_file() or path.read_text() != expected:
            errors.append(
                f"{path.relative_to(REPO_ROOT)} is stale; run "
                "python3 scripts/service_catalog.py render"
            )


def require_mapping(
    value: Any, label: str, errors: list[str]
) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        errors.append(f"{label} must be a mapping")
        return None
    return value


def require_nonempty_string(value: Any, label: str, errors: list[str]) -> str | None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{label} must be a non-empty string")
        return None
    return value


def reject_unknown(
    value: dict[str, Any],
    allowed: set[str],
    label: str,
    errors: list[str],
) -> None:
    for key in sorted(set(value) - allowed):
        errors.append(f"{label} contains unknown field: {key}")


def referenced_paths(value: Any, label: str, errors: list[str]) -> list[Path]:
    if not isinstance(value, list) or not value:
        errors.append(f"{label} must be a non-empty list")
        return []
    result: list[Path] = []
    for index, item in enumerate(value):
        path_value = require_nonempty_string(item, f"{label}[{index}]", errors)
        if path_value is None:
            continue
        try:
            path = repo_path(path_value)
        except CatalogError as error:
            errors.append(str(error))
            continue
        if not path.is_file():
            errors.append(f"{label}[{index}] does not exist: {path_value}")
        result.append(path)
    return result


def secret_references(value: Any, label: str, errors: list[str]) -> None:
    if not isinstance(value, list) or not value:
        errors.append(f"{label} must be a non-empty list")
        return
    for index, reference in enumerate(value):
        item_label = f"{label}[{index}]"
        if not isinstance(reference, dict):
            errors.append(f"{item_label} must be a mapping with path and key")
            continue
        path_value = require_nonempty_string(
            reference.get("path"), f"{item_label}.path", errors
        )
        key = require_nonempty_string(
            reference.get("key"), f"{item_label}.key", errors
        )
        if path_value is None or key is None:
            continue
        try:
            path = repo_path(path_value)
        except CatalogError as error:
            errors.append(str(error))
            continue
        if not path.is_file():
            errors.append(f"{item_label}.path does not exist: {path_value}")
            continue
        try:
            documents = load_documents(path)
        except ManifestError as error:
            errors.append(str(error))
            continue
        keys: set[str] = set()
        for document in documents:
            if not isinstance(document, dict) or document.get("kind") != "Secret":
                continue
            for field in ("data", "stringData"):
                values = document.get(field)
                if isinstance(values, dict):
                    keys.update(item for item in values if isinstance(item, str))
        if key not in keys:
            errors.append(
                f"{item_label}.key is not present in Secret {path_value}: {key}"
            )


def nested_values(value: Any, key: str) -> Iterable[Any]:
    if isinstance(value, dict):
        for item_key, item_value in value.items():
            if item_key == key:
                yield item_value
            yield from nested_values(item_value, key)
    elif isinstance(value, list):
        for item in value:
            yield from nested_values(item, key)


def registered_roots(errors: list[str]) -> set[Path]:
    try:
        root = load_single_document(ROOT_KUSTOMIZATION)
    except (CatalogError, ManifestError) as error:
        errors.append(str(error))
        return set()
    resources = root.get("resources")
    if not isinstance(resources, list):
        errors.append("clusters/home-server/kustomization.yaml resources must be a list")
        return set()
    roots: set[Path] = set()
    for resource in resources:
        if not isinstance(resource, str):
            continue
        roots.add((ROOT_KUSTOMIZATION.parent / resource).resolve())
    return roots


def is_registered(path: Path, roots: set[Path]) -> bool:
    for root in roots:
        if path == root:
            return True
        try:
            path.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def route_hostnames(path: Path, errors: list[str]) -> set[str]:
    try:
        documents = load_documents(path)
    except ManifestError as error:
        errors.append(str(error))
        return set()
    result: set[str] = set()
    for document in documents:
        if not isinstance(document, dict) or document.get("kind") != "HTTPRoute":
            continue
        hostnames = document.get("spec", {}).get("hostnames", [])
        if isinstance(hostnames, list):
            result.update(item for item in hostnames if isinstance(item, str))
    return result


def validate_catalog_structure(catalog: dict[str, Any], errors: list[str]) -> None:
    if catalog.get("version") != 2:
        errors.append("catalog.version must be 2")
    if LEGACY_CATALOG_PATH.exists():
        errors.append(
            "catalog/services.yaml is the retired monolithic source; service "
            "intent belongs in colocated *.catalog.yaml descriptors"
        )

    domain = require_nonempty_string(
        catalog.get("domain"), "catalog.domain", errors
    )
    if domain is not None and not is_dns_name(domain):
        errors.append("catalog.domain must be a lowercase DNS name")

    homepage = require_mapping(catalog.get("homepage"), "catalog.homepage", errors)
    groups: list[str] = []
    if homepage is not None:
        reject_unknown(homepage, {"groups"}, "catalog.homepage", errors)
        raw_groups = homepage.get("groups")
        if not isinstance(raw_groups, list) or not raw_groups:
            errors.append("catalog.homepage.groups must be a non-empty list")
        else:
            groups = [group for group in raw_groups if isinstance(group, str)]
            if len(groups) != len(raw_groups) or len(set(groups)) != len(groups):
                errors.append("catalog.homepage.groups must contain unique strings")

    dns = require_mapping(catalog.get("dns"), "catalog.dns", errors)
    if dns is not None:
        reject_unknown(
            dns,
            {"extraPublicNames", "splitHorizonAddress"},
            "catalog.dns",
            errors,
        )
        split_horizon_address = require_nonempty_string(
            dns.get("splitHorizonAddress"),
            "catalog.dns.splitHorizonAddress",
            errors,
        )
        if split_horizon_address is not None:
            try:
                ipaddress.ip_address(split_horizon_address)
            except ValueError:
                errors.append(
                    "catalog.dns.splitHorizonAddress must be an IP address"
                )
        extras = dns.get("extraPublicNames")
        if not isinstance(extras, list) or not all(
            isinstance(item, str) and item for item in extras
        ):
            errors.append("catalog.dns.extraPublicNames must be a list of hostnames")
        elif domain is not None:
            for item in extras:
                if not is_dns_name(item) or not (
                    item == domain or item.endswith(f".{domain}")
                ):
                    errors.append(
                        "catalog.dns.extraPublicNames entries must be valid names "
                        f"at or below {domain}: {item}"
                    )

    authentik = require_mapping(
        catalog.get("authentik"), "catalog.authentik", errors
    )
    provider_secret_manifest: str | None = None
    provider_secret_name: str | None = None
    if authentik is not None:
        reject_unknown(
            authentik,
            {"baseUrl", "namespace", "providerSecret"},
            "catalog.authentik",
            errors,
        )
        base_url = require_nonempty_string(
            authentik.get("baseUrl"), "catalog.authentik.baseUrl", errors
        )
        if base_url is not None:
            parsed_base_url = urlparse(base_url)
            if (
                parsed_base_url.scheme != "https"
                or not parsed_base_url.hostname
                or parsed_base_url.netloc != parsed_base_url.hostname
                or parsed_base_url.path not in {"", "/"}
                or parsed_base_url.params
                or parsed_base_url.query
                or parsed_base_url.fragment
            ):
                errors.append(
                    "catalog.authentik.baseUrl must be an origin-only HTTPS URL"
                )
        authentik_namespace = require_nonempty_string(
            authentik.get("namespace"), "catalog.authentik.namespace", errors
        )
        if (
            authentik_namespace is not None
            and not DNS_LABEL_PATTERN.fullmatch(authentik_namespace)
        ):
            errors.append("catalog.authentik.namespace must be a DNS label")
        provider_secret = require_mapping(
            authentik.get("providerSecret"),
            "catalog.authentik.providerSecret",
            errors,
        )
        if provider_secret is not None:
            reject_unknown(
                provider_secret,
                {"manifest", "name"},
                "catalog.authentik.providerSecret",
                errors,
            )
            provider_secret_manifest = require_nonempty_string(
                provider_secret.get("manifest"),
                "catalog.authentik.providerSecret.manifest",
                errors,
            )
            provider_secret_name = require_nonempty_string(
                provider_secret.get("name"),
                "catalog.authentik.providerSecret.name",
                errors,
            )
            if (
                provider_secret_name is not None
                and not is_dns_name(provider_secret_name)
            ):
                errors.append(
                    "catalog.authentik.providerSecret.name must be a DNS name"
                )

    roots = registered_roots(errors)
    ids: set[str] = set()
    hostnames: set[str] = set()
    client_ids: set[str] = set()
    catalog_app_paths: set[Path] = set()

    for index, service in enumerate(services(catalog)):
        label = f"catalog.services[{index}]"
        if not isinstance(service, dict):
            errors.append(f"{label} must be a mapping")
            continue
        reject_unknown(
            service,
            {
                "_source",
                "data",
                "homepage",
                "id",
                "name",
                "observability",
                "path",
                "placement",
                "web",
                "workload",
            },
            label,
            errors,
        )

        service_id = require_nonempty_string(service.get("id"), f"{label}.id", errors)
        require_nonempty_string(service.get("name"), f"{label}.name", errors)
        if service_id is not None:
            if not DNS_LABEL_PATTERN.fullmatch(service_id):
                errors.append(f"{label}.id must be a DNS label")
            if service_id in ids:
                errors.append(f"duplicate service id: {service_id}")
            ids.add(service_id)
            source = service.get("_source")
            label = (
                f"service {service_id} ({source})"
                if isinstance(source, str)
                else f"service {service_id}"
            )

        path_value = require_nonempty_string(service.get("path"), f"{label}.path", errors)
        service_path: Path | None = None
        if path_value is not None:
            try:
                service_path = repo_path(path_value)
            except CatalogError as error:
                errors.append(str(error))
            else:
                if not service_path.is_dir():
                    errors.append(f"{label}.path does not exist: {path_value}")
                elif not is_registered(service_path, roots):
                    errors.append(f"{label}.path is not registered by the root Kustomization")
                if path_value.startswith("apps/"):
                    catalog_app_paths.add(service_path)

        workload = require_mapping(service.get("workload"), f"{label}.workload", errors)
        if workload is not None:
            reject_unknown(
                workload,
                {"app", "namespace", "podSelector"},
                f"{label}.workload",
                errors,
            )
            require_nonempty_string(
                workload.get("namespace"), f"{label}.workload.namespace", errors
            )
            selectors = [
                key
                for key in ("app", "podSelector")
                if isinstance(workload.get(key), str) and workload[key]
            ]
            if len(selectors) != 1:
                errors.append(
                    f"{label}.workload must set exactly one of app or podSelector"
                )

        card = require_mapping(service.get("homepage"), f"{label}.homepage", errors)
        if card is not None:
            reject_unknown(
                card,
                {"description", "enabled", "group", "icon", "link", "order", "reason"},
                f"{label}.homepage",
                errors,
            )
            enabled = card.get("enabled", True)
            if enabled not in {True, False}:
                errors.append(f"{label}.homepage.enabled must be a boolean")
            elif enabled is False:
                require_nonempty_string(
                    card.get("reason"), f"{label}.homepage.reason", errors
                )
            else:
                if card.get("group") not in groups:
                    errors.append(f"{label}.homepage.group is not declared")
                order = card.get("order", 1000)
                if not isinstance(order, int) or isinstance(order, bool) or order < 0:
                    errors.append(f"{label}.homepage.order must be a non-negative integer")
                require_nonempty_string(
                    card.get("icon"), f"{label}.homepage.icon", errors
                )
                require_nonempty_string(
                    card.get("description"), f"{label}.homepage.description", errors
                )
                if card.get("link", True) not in {True, False}:
                    errors.append(f"{label}.homepage.link must be a boolean")

        web = service.get("web")
        if web is not None:
            web = require_mapping(web, f"{label}.web", errors)
        if web is not None:
            reject_unknown(
                web,
                {
                    "accessMiddleware",
                    "auth",
                    "dns",
                    "hostname",
                    "route",
                    "visibility",
                },
                f"{label}.web",
                errors,
            )
            hostname = require_nonempty_string(
                web.get("hostname"), f"{label}.web.hostname", errors
            )
            if hostname is not None:
                if hostname in hostnames:
                    errors.append(f"duplicate web hostname: {hostname}")
                hostnames.add(hostname)
                if not is_dns_name(hostname):
                    errors.append(
                        f"{label}.web.hostname must be a lowercase DNS name"
                    )
                elif domain is not None and not hostname.endswith(f".{domain}"):
                    errors.append(f"{label}.web.hostname must be under {domain}")

            route_value = require_nonempty_string(
                web.get("route"), f"{label}.web.route", errors
            )
            if route_value is not None:
                try:
                    route_path = repo_path(route_value)
                except CatalogError as error:
                    errors.append(str(error))
                else:
                    if not route_path.is_file():
                        errors.append(f"{label}.web.route does not exist: {route_value}")
                    elif hostname is not None and hostname not in route_hostnames(
                        route_path, errors
                    ):
                        errors.append(
                            f"{label}.web.route does not declare hostname {hostname}"
                        )

            visibility = web.get("visibility")
            if visibility not in {"private", "public"}:
                errors.append(f"{label}.web.visibility must be private or public")
            middleware = web.get("accessMiddleware")
            if visibility == "private":
                require_nonempty_string(
                    middleware, f"{label}.web.accessMiddleware", errors
                )
            elif middleware is not None:
                errors.append(
                    f"{label}.web.accessMiddleware is only valid for private routes"
                )

            web_dns = require_mapping(web.get("dns"), f"{label}.web.dns", errors)
            if web_dns is not None:
                reject_unknown(
                    web_dns,
                    {"cloudflare", "splitHorizon"},
                    f"{label}.web.dns",
                    errors,
                )
                for key in ("cloudflare", "splitHorizon"):
                    if web_dns.get(key) not in {True, False}:
                        errors.append(f"{label}.web.dns.{key} must be a boolean")

            auth = require_mapping(web.get("auth"), f"{label}.web.auth", errors)
            if auth is not None:
                mode = auth.get("mode")
                if mode not in ALLOWED_AUTH_MODES:
                    errors.append(
                        f"{label}.web.auth.mode must be one of "
                        f"{sorted(ALLOWED_AUTH_MODES)}"
                    )
                if mode in {"native", "none"}:
                    reject_unknown(auth, {"mode", "reason"}, f"{label}.web.auth", errors)
                    require_nonempty_string(
                        auth.get("reason"), f"{label}.web.auth.reason", errors
                    )
                    if visibility == "public" and mode == "none":
                        errors.append(f"{label} cannot expose an unauthenticated public route")
                if mode in {"oidc", "forward-auth"}:
                    application = require_mapping(
                        auth.get("application"),
                        f"{label}.web.auth.application",
                        errors,
                    )
                    if application is not None:
                        reject_unknown(
                            application,
                            {"launchUrl", "slug"},
                            f"{label}.web.auth.application",
                            errors,
                        )
                        application_slug = require_nonempty_string(
                            application.get("slug"),
                            f"{label}.web.auth.application.slug",
                            errors,
                        )
                        if (
                            application_slug is not None
                            and not DNS_LABEL_PATTERN.fullmatch(application_slug)
                        ):
                            errors.append(
                                f"{label}.web.auth.application.slug must be a DNS label"
                            )
                        launch_url = application.get("launchUrl")
                        if launch_url is not None and (
                            not isinstance(launch_url, str)
                            or hostname is None
                            or not is_same_host_https_url(launch_url, hostname)
                        ):
                            errors.append(
                                f"{label}.web.auth.application.launchUrl must be "
                                f"an HTTPS URL on {hostname}"
                            )

                if mode == "forward-auth":
                    reject_unknown(
                        auth,
                        {
                            "allowedGroups",
                            "application",
                            "blueprintName",
                            "middleware",
                            "mode",
                            "profile",
                            "providerName",
                        },
                        f"{label}.web.auth",
                        errors,
                    )
                    profile = auth.get("profile")
                    if profile not in {
                        "authentik-forward-single-v1",
                        "authentik-forward-single-v2",
                    }:
                        errors.append(
                            f"{label}.web.auth.profile must be "
                            "authentik-forward-single-v1 or "
                            "authentik-forward-single-v2"
                        )
                    require_nonempty_string(
                        auth.get("middleware"),
                        f"{label}.web.auth.middleware",
                        errors,
                    )
                    allowed_groups = auth.get("allowedGroups")
                    if allowed_groups is not None:
                        groups_ok = (
                            isinstance(allowed_groups, list)
                            and bool(allowed_groups)
                            and all(
                                isinstance(group, str) and group.strip()
                                for group in allowed_groups
                            )
                        )
                        if not groups_ok or len(set(allowed_groups)) != len(
                            allowed_groups
                        ):
                            errors.append(
                                f"{label}.web.auth.allowedGroups must be "
                                "a non-empty list of unique non-empty "
                                "group names"
                            )
                    if profile == "authentik-forward-single-v1":
                        if allowed_groups is not None:
                            errors.append(
                                f"{label}.web.auth.allowedGroups is only "
                                "valid with profile "
                                "authentik-forward-single-v2"
                            )
                    elif not isinstance(allowed_groups, list) or not allowed_groups:
                        errors.append(
                            f"{label}.web.auth.allowedGroups is required "
                            "with profile authentik-forward-single-v2"
                        )

                if mode == "oidc":
                    reject_unknown(
                        auth,
                        {
                            "application",
                            "blueprintName",
                            "claimMappings",
                            "client",
                            "mode",
                            "profile",
                            "providerName",
                        },
                        f"{label}.web.auth",
                        errors,
                    )
                    if auth.get("profile") != "authentik-oidc-v1":
                        errors.append(
                            f"{label}.web.auth.profile must be authentik-oidc-v1"
                        )
                    client = require_mapping(
                        auth.get("client"), f"{label}.web.auth.client", errors
                    )
                    if client is not None:
                        reject_unknown(
                            client,
                            {
                                "grantTypes",
                                "id",
                                "pkce",
                                "providerLogout",
                                "redirectUris",
                                "scopes",
                                "secret",
                                "type",
                            },
                            f"{label}.web.auth.client",
                            errors,
                        )
                        client_type = client.get("type")
                        if client_type not in {"confidential", "public"}:
                            errors.append(
                                f"{label}.web.auth.client.type must be "
                                "confidential or public"
                            )
                        client_id = require_nonempty_string(
                            client.get("id"),
                            f"{label}.web.auth.client.id",
                            errors,
                        )
                        if client_id is not None:
                            if client_id in client_ids:
                                errors.append(f"duplicate OIDC client id: {client_id}")
                            client_ids.add(client_id)
                        grants = client.get("grantTypes")
                        if (
                            not isinstance(grants, list)
                            or not grants
                            or len(set(grants)) != len(grants)
                            or any(
                                grant not in {"authorization_code", "refresh_token"}
                                for grant in grants
                            )
                        ):
                            errors.append(
                                f"{label}.web.auth.client.grantTypes must contain "
                                "unique supported grants"
                            )
                        elif "authorization_code" not in grants:
                            errors.append(
                                f"{label}.web.auth.client.grantTypes must include "
                                "authorization_code"
                            )
                        scopes = client.get("scopes")
                        if (
                            not isinstance(scopes, list)
                            or len(set(scopes)) != len(scopes)
                            or any(scope not in MANAGED_SCOPE_MAPPINGS for scope in scopes)
                        ):
                            errors.append(
                                f"{label}.web.auth.client.scopes must contain "
                                "unique supported scopes"
                            )
                        redirects = client.get("redirectUris")
                        if not isinstance(redirects, list) or not redirects:
                            errors.append(
                                f"{label}.web.auth.client.redirectUris must be "
                                "a non-empty list"
                            )
                        else:
                            for redirect_index, redirect in enumerate(redirects):
                                redirect_label = (
                                    f"{label}.web.auth.client.redirectUris"
                                    f"[{redirect_index}]"
                                )
                                if not isinstance(redirect, dict):
                                    errors.append(f"{redirect_label} must be a mapping")
                                    continue
                                reject_unknown(
                                    redirect,
                                    {"type", "url"},
                                    redirect_label,
                                    errors,
                                )
                                if redirect.get("type") not in {
                                    "authorization",
                                    "logout",
                                }:
                                    errors.append(
                                        f"{redirect_label}.type must be "
                                        "authorization or logout"
                                    )
                                redirect_url = require_nonempty_string(
                                    redirect.get("url"),
                                    f"{redirect_label}.url",
                                    errors,
                                )
                                if redirect_url is not None:
                                    if (
                                        hostname is None
                                        or not is_same_host_https_url(
                                            redirect_url, hostname
                                        )
                                    ):
                                        errors.append(
                                            f"{redirect_label}.url must be an exact "
                                            f"https URL on {hostname}"
                                        )

                        provider_logout = client.get("providerLogout")
                        if provider_logout is not None:
                            logout_label = f"{label}.web.auth.client.providerLogout"
                            if not isinstance(provider_logout, dict):
                                errors.append(f"{logout_label} must be a mapping")
                            else:
                                reject_unknown(
                                    provider_logout,
                                    {"method", "url"},
                                    logout_label,
                                    errors,
                                )
                                if provider_logout.get("method") not in {
                                    "backchannel",
                                    "frontchannel",
                                }:
                                    errors.append(
                                        f"{logout_label}.method must be backchannel "
                                        "or frontchannel"
                                    )
                                logout_url = require_nonempty_string(
                                    provider_logout.get("url"),
                                    f"{logout_label}.url",
                                    errors,
                                )
                                if logout_url is not None and (
                                    hostname is None
                                    or not is_same_host_https_url(logout_url, hostname)
                                ):
                                    errors.append(
                                        f"{logout_label}.url must be an exact "
                                        f"https URL on {hostname}"
                                    )

                        if client_type == "confidential":
                            if client.get("pkce") is not None:
                                errors.append(
                                    f"{label}.web.auth.client.pkce is only valid "
                                    "for a public client"
                                )
                            relying_secret = require_mapping(
                                client.get("secret"),
                                f"{label}.web.auth.client.secret",
                                errors,
                            )
                            if relying_secret is not None:
                                if relying_secret.get("managedBy") == "application-state":
                                    reject_unknown(
                                        relying_secret,
                                        {"managedBy", "reason"},
                                        f"{label}.web.auth.client.secret",
                                        errors,
                                    )
                                    require_nonempty_string(
                                        relying_secret.get("reason"),
                                        f"{label}.web.auth.client.secret.reason",
                                        errors,
                                    )
                                else:
                                    reject_unknown(
                                        relying_secret,
                                        {"key", "manifest"},
                                        f"{label}.web.auth.client.secret",
                                        errors,
                                    )
                                    secret_references(
                                        [
                                            {
                                                "path": relying_secret.get("manifest"),
                                                "key": relying_secret.get("key"),
                                            }
                                        ],
                                        f"{label}.web.auth.client.secret",
                                        errors,
                                    )
                            if (
                                provider_secret_manifest is not None
                                and service_id is not None
                            ):
                                secret_references(
                                    [
                                        {
                                            "path": provider_secret_manifest,
                                            "key": authentik_secret_key(service_id),
                                        }
                                    ],
                                    f"{label}.web.auth.providerSecret",
                                    errors,
                                )
                            if provider_secret_name is None:
                                errors.append(
                                    f"{label} cannot wire a confidential OIDC client "
                                    "without catalog.authentik.providerSecret.name"
                                )
                        elif client_type == "public":
                            if client.get("secret") is not None:
                                errors.append(
                                    f"{label}.web.auth.client.secret is forbidden "
                                    "for a public client"
                                )
                            pkce = require_mapping(
                                client.get("pkce"),
                                f"{label}.web.auth.client.pkce",
                                errors,
                            )
                            if pkce is not None:
                                reject_unknown(
                                    pkce,
                                    {"evidence", "verified"},
                                    f"{label}.web.auth.client.pkce",
                                    errors,
                                )
                                if pkce.get("verified") is not True:
                                    errors.append(
                                        f"{label}.web.auth.client.pkce.verified "
                                        "must be true"
                                    )
                                require_nonempty_string(
                                    pkce.get("evidence"),
                                    f"{label}.web.auth.client.pkce.evidence",
                                    errors,
                                )

                    claim_mappings = auth.get("claimMappings", [])
                    if not isinstance(claim_mappings, list):
                        errors.append(
                            f"{label}.web.auth.claimMappings must be a list"
                        )
                    else:
                        mapping_ids: set[str] = set()
                        for mapping_index, mapping in enumerate(claim_mappings):
                            mapping_label = (
                                f"{label}.web.auth.claimMappings[{mapping_index}]"
                            )
                            if not isinstance(mapping, dict):
                                errors.append(f"{mapping_label} must be a mapping")
                                continue
                            reject_unknown(
                                mapping,
                                {
                                    "description",
                                    "expression",
                                    "id",
                                    "name",
                                    "reason",
                                    "scope",
                                },
                                mapping_label,
                                errors,
                            )
                            for key in (
                                "description",
                                "expression",
                                "id",
                                "name",
                                "reason",
                                "scope",
                            ):
                                require_nonempty_string(
                                    mapping.get(key),
                                    f"{mapping_label}.{key}",
                                    errors,
                                )
                            mapping_id = mapping.get("id")
                            if isinstance(mapping_id, str):
                                if not DNS_LABEL_PATTERN.fullmatch(mapping_id):
                                    errors.append(
                                        f"{mapping_label}.id must be a DNS label"
                                    )
                                if mapping_id in mapping_ids:
                                    errors.append(
                                        f"{mapping_label}.id is duplicated: "
                                        f"{mapping_id}"
                                    )
                                mapping_ids.add(mapping_id)
                            mapping_scope = mapping.get("scope")
                            if (
                                isinstance(mapping_scope, str)
                                and not AUTHENTIK_IDENTIFIER_PATTERN.fullmatch(
                                    mapping_scope
                                )
                            ):
                                errors.append(
                                    f"{mapping_label}.scope contains unsafe characters"
                                )

        placement = require_mapping(
            service.get("placement"), f"{label}.placement", errors
        )
        if placement is not None:
            reject_unknown(
                placement,
                {"manifest", "mode", "reason"},
                f"{label}.placement",
                errors,
            )
            mode = placement.get("mode")
            if mode not in ALLOWED_PLACEMENT:
                errors.append(
                    f"{label}.placement.mode must be one of {sorted(ALLOWED_PLACEMENT)}"
                )
            if mode != "floating":
                require_nonempty_string(
                    placement.get("reason"), f"{label}.placement.reason", errors
                )
            if mode in {"beelink", "raspberrypi"}:
                manifest_value = require_nonempty_string(
                    placement.get("manifest"), f"{label}.placement.manifest", errors
                )
                if manifest_value is not None:
                    try:
                        manifest_path = repo_path(manifest_value)
                    except CatalogError as error:
                        errors.append(str(error))
                    else:
                        if not manifest_path.is_file():
                            errors.append(
                                f"{label}.placement.manifest does not exist: "
                                f"{manifest_value}"
                            )
                        else:
                            try:
                                documents = load_documents(manifest_path)
                            except ManifestError as error:
                                errors.append(str(error))
                            else:
                                node_selectors = list(
                                    nested_values(documents, "nodeSelector")
                                )
                                expected = {"kubernetes.io/hostname": mode}
                                if expected not in node_selectors:
                                    errors.append(
                                        f"{label}.placement.manifest does not pin "
                                        f"kubernetes.io/hostname to {mode}"
                                    )

        data = require_mapping(service.get("data"), f"{label}.data", errors)
        if data is not None:
            reject_unknown(
                data,
                {"class", "manifests", "note", "protection"},
                f"{label}.data",
                errors,
            )
            data_class = data.get("class")
            protection = data.get("protection")
            if data_class not in ALLOWED_DATA_CLASSES:
                errors.append(
                    f"{label}.data.class must be one of {sorted(ALLOWED_DATA_CLASSES)}"
                )
            if protection not in ALLOWED_PROTECTION:
                errors.append(
                    f"{label}.data.protection must be one of "
                    f"{sorted(ALLOWED_PROTECTION)}"
                )
            if data_class in {
                "longhorn",
                "longhorn-observability",
                "mixed",
                "nfs-reproducible",
                "platform",
            }:
                referenced_paths(
                    data.get("manifests"), f"{label}.data.manifests", errors
                )
            if data_class == "mixed" or protection in {
                "excluded-observability",
                "excluded-reproducible",
                "platform-managed",
            }:
                require_nonempty_string(
                    data.get("note"), f"{label}.data.note", errors
                )

        observability = require_mapping(
            service.get("observability"), f"{label}.observability", errors
        )
        if observability is not None:
            reject_unknown(
                observability,
                {"manifests", "mode", "reason"},
                f"{label}.observability",
                errors,
            )
            mode = observability.get("mode")
            if mode not in ALLOWED_OBSERVABILITY:
                errors.append(
                    f"{label}.observability.mode must be one of "
                    f"{sorted(ALLOWED_OBSERVABILITY)}"
                )
            if mode in {"metrics", "platform"}:
                referenced_paths(
                    observability.get("manifests"),
                    f"{label}.observability.manifests",
                    errors,
                )
            if mode == "none":
                require_nonempty_string(
                    observability.get("reason"),
                    f"{label}.observability.reason",
                    errors,
                )

    exclusions = catalog.get("registrationExclusions")
    excluded_paths: set[Path] = set()
    if not isinstance(exclusions, list):
        errors.append("catalog.registrationExclusions must be a list")
    else:
        for index, exclusion in enumerate(exclusions):
            label = f"catalog.registrationExclusions[{index}]"
            if not isinstance(exclusion, dict):
                errors.append(f"{label} must be a mapping")
                continue
            value = require_nonempty_string(exclusion.get("path"), f"{label}.path", errors)
            require_nonempty_string(exclusion.get("reason"), f"{label}.reason", errors)
            if value is not None:
                try:
                    path = repo_path(value)
                except CatalogError as error:
                    errors.append(str(error))
                else:
                    if not path.is_dir():
                        errors.append(f"{label}.path does not exist: {value}")
                    excluded_paths.add(path)

    active_app_roots = {path for path in roots if path.parent == REPO_ROOT / "apps"}
    for path in sorted(excluded_paths - active_app_roots):
        errors.append(
            f"registration exclusion is not an active root app path: "
            f"{path.relative_to(REPO_ROOT)}"
        )
    for path in sorted(excluded_paths & catalog_app_paths):
        errors.append(
            f"active app path cannot be both cataloged and excluded: "
            f"{path.relative_to(REPO_ROOT)}"
        )
    missing_app_paths = active_app_roots - catalog_app_paths - excluded_paths
    for path in sorted(missing_app_paths):
        errors.append(
            f"active app path has no catalog service or documented exclusion: "
            f"{path.relative_to(REPO_ROOT)}"
        )


def rendered_routes(
    path: Path, domain: str, errors: list[str]
) -> tuple[dict[str, dict[str, Any]], set[str]]:
    result: dict[str, dict[str, Any]] = {}
    try:
        documents = load_documents(path)
    except ManifestError as error:
        errors.append(str(error))
        return result, set()
    ip_allowlists = {
        f"{document.get('metadata', {}).get('namespace', 'default')}/"
        f"{document.get('metadata', {}).get('name')}"
        for document in documents
        if isinstance(document, dict)
        and document.get("kind") == "Middleware"
        and isinstance(document.get("spec", {}).get("ipAllowList"), dict)
    }
    for document in documents:
        if not isinstance(document, dict) or document.get("kind") != "HTTPRoute":
            continue
        metadata = document.get("metadata", {})
        namespace = metadata.get("namespace", "default")
        name = metadata.get("name")
        filters: set[str] = set()
        for rule in document.get("spec", {}).get("rules", []):
            if not isinstance(rule, dict):
                continue
            for item in rule.get("filters", []):
                if not isinstance(item, dict):
                    continue
                extension = item.get("extensionRef")
                if isinstance(extension, dict) and isinstance(extension.get("name"), str):
                    filters.add(extension["name"])
        for hostname in document.get("spec", {}).get("hostnames", []):
            if not isinstance(hostname, str) or not hostname.endswith(f".{domain}"):
                continue
            if hostname in result:
                errors.append(f"rendered cluster has duplicate HTTPRoute hostname {hostname}")
            result[hostname] = {
                "route": f"{namespace}/{name}",
                "namespace": namespace,
                "filters": filters,
            }
    return result, ip_allowlists


def validate_rendered_cluster(
    catalog: dict[str, Any], rendered_path: Path, errors: list[str]
) -> None:
    domain = catalog.get("domain")
    if not isinstance(domain, str) or not domain:
        domain = "reza.network"
    actual, ip_allowlists = rendered_routes(rendered_path, domain, errors)
    expected: dict[str, dict[str, Any]] = {}
    for service in services(catalog):
        if not isinstance(service, dict) or not isinstance(service.get("web"), dict):
            continue
        web = service["web"]
        hostname = web.get("hostname")
        if isinstance(hostname, str):
            expected[hostname] = web

    for hostname in sorted(set(actual) - set(expected)):
        errors.append(
            f"rendered HTTPRoute hostname is missing from the service catalog: {hostname}"
        )
    for hostname in sorted(set(expected) - set(actual)):
        errors.append(
            f"catalog web hostname has no rendered HTTPRoute: {hostname}"
        )
    for hostname in sorted(set(actual) & set(expected)):
        web = expected[hostname]
        namespace = actual[hostname]["namespace"]
        filters = actual[hostname]["filters"]
        route_ip_allowlists = {
            name for name in filters if f"{namespace}/{name}" in ip_allowlists
        }
        if web.get("visibility") == "private":
            middleware = web.get("accessMiddleware")
            if middleware not in filters:
                errors.append(
                    f"{hostname} private route does not reference access middleware "
                    f"{middleware}"
                )
            elif middleware not in route_ip_allowlists:
                errors.append(
                    f"{hostname} declared access middleware {middleware} is not an "
                    "IP allow-list"
                )
        elif route_ip_allowlists:
            errors.append(
                f"{hostname} is cataloged public but its rendered route uses IP "
                f"allow-list(s): {sorted(route_ip_allowlists)}"
            )

        auth = web.get("auth", {})
        if auth.get("mode") == "forward-auth":
            middleware = auth.get("middleware")
            if middleware not in filters:
                errors.append(
                    f"{hostname} forward-auth route does not reference middleware "
                    f"{middleware}"
                )


def render_cluster() -> Path:
    if shutil.which("kubectl") is None:
        raise CatalogError("required command is not installed: kubectl")
    process = subprocess.run(
        ["kubectl", "kustomize", "clusters/home-server"],
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if process.returncode != 0:
        detail = process.stderr.strip() or "unknown kubectl kustomize error"
        raise CatalogError(f"could not render clusters/home-server: {detail}")
    temporary = tempfile.NamedTemporaryFile(
        mode="w", prefix="home-server-catalog-", suffix=".yaml", delete=False
    )
    with temporary:
        temporary.write(process.stdout)
    return Path(temporary.name)


def check(catalog: dict[str, Any], rendered_path: Path | None) -> None:
    errors: list[str] = []
    validate_catalog_structure(catalog, errors)

    temporary_render: Path | None = None
    if not errors:
        validate_generated_outputs(catalog, errors)
        if rendered_path is None:
            temporary_render = render_cluster()
            rendered_path = temporary_render
        if not rendered_path.is_file():
            errors.append(f"rendered manifest does not exist: {rendered_path}")
        else:
            validate_rendered_cluster(catalog, rendered_path, errors)

    if temporary_render is not None:
        temporary_render.unlink(missing_ok=True)

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        raise CatalogError(f"service catalog validation failed with {len(errors)} error(s)")

    route_count = sum(
        1 for service in services(catalog) if isinstance(service.get("web"), dict)
    )
    print(
        f"Validated {len(services(catalog))} service(s), "
        f"{route_count} web route(s), and all generated integrations."
    )


def summary(catalog: dict[str, Any]) -> None:
    print(
        "ID\tSOURCE\tWEB\tAUTH\tPLACEMENT\tDATA\tOBSERVABILITY",
    )
    for service in services(catalog):
        web = service.get("web", {})
        print(
            "\t".join(
                [
                    str(service.get("id", "")),
                    str(service.get("_source", "")),
                    str(web.get("hostname", "-")),
                    str(web.get("auth", {}).get("mode", "-")),
                    str(service.get("placement", {}).get("mode", "-")),
                    str(service.get("data", {}).get("protection", "-")),
                    str(service.get("observability", {}).get("mode", "-")),
                ]
            )
        )


def explain(catalog: dict[str, Any], service_id: str) -> None:
    matches = [
        service
        for service in services(catalog)
        if service.get("id") == service_id
    ]
    if not matches:
        available = ", ".join(
            sorted(str(service.get("id")) for service in services(catalog))
        )
        raise CatalogError(
            f"unknown service {service_id!r}; available services: {available}"
        )
    service = matches[0]
    web = service.get("web")
    auth = web.get("auth", {}) if isinstance(web, dict) else {}
    placement = service.get("placement", {})
    data = service.get("data", {})
    observability = service.get("observability", {})
    card = service.get("homepage", {})

    print(str(service.get("name")))
    print(f"  Descriptor: {service.get('_source')}")
    if isinstance(web, dict):
        visibility = web.get("visibility")
        reachability = (
            "LAN and WireGuard only"
            if visibility == "private"
            else "the public Internet"
        )
        print(f"  Reachable from: {reachability}")
        print(f"  Address: https://{web.get('hostname')}/")
        mode = auth.get("mode")
        if mode == "oidc":
            client = auth.get("client", {})
            print(
                "  Login: Authentik through native OIDC "
                f"({client.get('type')} client, profile {auth.get('profile')})"
            )
        elif mode == "forward-auth":
            print(
                "  Login: Authentik forward-auth "
                f"(profile {auth.get('profile')})"
            )
        elif mode == "native":
            print("  Login: the application's native authentication")
        else:
            print("  Login: no application authentication; network boundary only")
        dns = web.get("dns", {})
        destinations = []
        if dns.get("cloudflare"):
            destinations.append("Cloudflare DDNS")
        if dns.get("splitHorizon"):
            destinations.append("Blocky split DNS")
        print(f"  DNS: {', '.join(destinations) if destinations else 'unmanaged'}")
    else:
        print("  Reachable from: no shared HTTP route")
        print("  Login: not applicable")

    print(f"  Placement: {placement.get('mode')}")
    print(
        f"  State: {data.get('class')}; protection: {data.get('protection')}"
    )
    print(f"  Monitoring: {observability.get('mode')}")
    if card.get("enabled", True) is False:
        print(f"  Homepage: omitted — {card.get('reason')}")
    else:
        print(f"  Homepage: {card.get('group')} / {service.get('name')}")

    generated = ["Homepage service inventory"]
    if isinstance(web, dict):
        if web.get("dns", {}).get("cloudflare"):
            generated.append("Cloudflare DDNS domain aggregate")
        if web.get("dns", {}).get("splitHorizon"):
            generated.append("Blocky split-DNS mapping")
        if auth.get("mode") in {"oidc", "forward-auth"}:
            generated.append("Authentik application/provider blueprint")
        if (
            auth.get("mode") == "oidc"
            and auth.get("client", {}).get("type") == "confidential"
        ):
            generated.append(
                "Authentik worker Secret reference "
                f"({authentik_secret_key(service_id)})"
            )
    print("\nGenerated by the catalog compiler:")
    for item in generated:
        print(f"  - {item}")

    print("\nValidated but still explicitly owned by manifests:")
    if isinstance(web, dict):
        print(f"  - HTTPRoute and exposure middleware: {web.get('route')}")
        if auth.get("mode") == "oidc":
            client = auth.get("client", {})
            print("  - Relying application's OIDC settings and NetworkPolicy")
            print("  - Exact browser/mobile login and logout behavior")
            if client.get("type") == "confidential":
                secret = client.get("secret", {})
                if secret.get("managedBy") == "application-state":
                    print(
                        "  - Relying-party secret is application-owned state: "
                        f"{secret.get('reason')}"
                    )
                else:
                    print(
                        "  - Encrypted relying-party secret: "
                        f"{secret.get('manifest')} / {secret.get('key')}"
                    )
    for item in data.get("manifests", []):
        print(f"  - Storage/backup declaration: {item}")
    for item in observability.get("manifests", []):
        print(f"  - Monitoring resource: {item}")
    if placement.get("manifest"):
        print(f"  - Node placement: {placement.get('manifest')}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("render", help="regenerate aggregate YAML from the catalog")
    check_parser = subparsers.add_parser(
        "check", help="validate catalog completeness and generated-file drift"
    )
    check_parser.add_argument(
        "--rendered",
        type=Path,
        help="pre-rendered cluster manifest; otherwise kubectl kustomize is run",
    )
    subparsers.add_parser("summary", help="print a compact integration matrix")
    explain_parser = subparsers.add_parser(
        "explain",
        help="explain one service in operator language, including automation boundaries",
    )
    explain_parser.add_argument("service_id", help="stable metadata.name to explain")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        catalog = load_catalog()
        if args.command == "render":
            render(catalog)
        elif args.command == "check":
            check(catalog, args.rendered)
        elif args.command == "summary":
            summary(catalog)
        elif args.command == "explain":
            explain(catalog, args.service_id)
    except (CatalogError, ManifestError, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
