#!/usr/bin/env python3
"""Render and validate the cluster's cross-service integration catalog."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
CI_DIR = REPO_ROOT / "scripts" / "ci"
sys.path.insert(0, str(CI_DIR))

from yaml_documents import ManifestError, load_documents  # noqa: E402


CATALOG_PATH = REPO_ROOT / "catalog" / "services.yaml"
HOMEPAGE_PATH = REPO_ROOT / "apps" / "homepage" / "config" / "services.yaml"
CLOUDFLARE_KUSTOMIZATION = REPO_ROOT / "apps" / "cloudflare-ddns" / "kustomization.yaml"
BLOCKY_CONFIG = REPO_ROOT / "apps" / "blocky" / "config.yml"
ROOT_KUSTOMIZATION = REPO_ROOT / "clusters" / "home-server" / "kustomization.yaml"
AUTHENTIK_BLUEPRINTS = REPO_ROOT / "apps" / "authentik" / "application-blueprints.yaml"
AUTHENTIK_WORKLOADS = REPO_ROOT / "apps" / "authentik" / "workloads.yaml"

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


def load_single_document(path: Path) -> dict[str, Any]:
    documents = [document for document in load_documents(path) if document is not None]
    if len(documents) != 1 or not isinstance(documents[0], dict):
        raise CatalogError(f"{path.relative_to(REPO_ROOT)} must contain one YAML mapping")
    return documents[0]


def load_catalog() -> dict[str, Any]:
    return load_single_document(CATALOG_PATH)


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

    grouped: dict[str, list[dict[str, Any]]] = {
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

        grouped[group].append({service.get("name"): details})

    return [{group: cards} for group, cards in grouped.items()]


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


def generated_outputs(catalog: dict[str, Any]) -> dict[Path, str]:
    header = (
        "# Generated from catalog/services.yaml by scripts/service_catalog.py.\n"
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
    }


def render(catalog: dict[str, Any]) -> None:
    for path, content in generated_outputs(catalog).items():
        path.write_text(content)
        print(f"Rendered {path.relative_to(REPO_ROOT)}")


def validate_generated_outputs(catalog: dict[str, Any], errors: list[str]) -> None:
    for path, expected in generated_outputs(catalog).items():
        if path.read_text() != expected:
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


def blueprint_data(errors: list[str]) -> dict[str, str]:
    try:
        document = load_single_document(AUTHENTIK_BLUEPRINTS)
    except (CatalogError, ManifestError) as error:
        errors.append(str(error))
        return {}
    data = document.get("data")
    if not isinstance(data, dict):
        errors.append("apps/authentik/application-blueprints.yaml data must be a mapping")
        return {}
    return {key: value for key, value in data.items() if isinstance(value, str)}


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
    if catalog.get("version") != 1:
        errors.append("catalog.version must be 1")

    homepage = require_mapping(catalog.get("homepage"), "catalog.homepage", errors)
    groups: list[str] = []
    if homepage is not None:
        raw_groups = homepage.get("groups")
        if not isinstance(raw_groups, list) or not raw_groups:
            errors.append("catalog.homepage.groups must be a non-empty list")
        else:
            groups = [group for group in raw_groups if isinstance(group, str)]
            if len(groups) != len(raw_groups) or len(set(groups)) != len(groups):
                errors.append("catalog.homepage.groups must contain unique strings")

    dns = require_mapping(catalog.get("dns"), "catalog.dns", errors)
    if dns is not None:
        require_nonempty_string(
            dns.get("splitHorizonAddress"),
            "catalog.dns.splitHorizonAddress",
            errors,
        )
        extras = dns.get("extraPublicNames")
        if not isinstance(extras, list) or not all(
            isinstance(item, str) and item for item in extras
        ):
            errors.append("catalog.dns.extraPublicNames must be a list of hostnames")

    roots = registered_roots(errors)
    blueprints = blueprint_data(errors)
    authentik_workloads = AUTHENTIK_WORKLOADS.read_text()
    ids: set[str] = set()
    hostnames: set[str] = set()
    catalog_app_paths: set[Path] = set()

    for index, service in enumerate(services(catalog)):
        label = f"catalog.services[{index}]"
        if not isinstance(service, dict):
            errors.append(f"{label} must be a mapping")
            continue

        service_id = require_nonempty_string(service.get("id"), f"{label}.id", errors)
        require_nonempty_string(service.get("name"), f"{label}.name", errors)
        if service_id is not None:
            if service_id in ids:
                errors.append(f"duplicate service id: {service_id}")
            ids.add(service_id)
            label = f"service {service_id}"

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
            hostname = require_nonempty_string(
                web.get("hostname"), f"{label}.web.hostname", errors
            )
            if hostname is not None:
                if hostname in hostnames:
                    errors.append(f"duplicate web hostname: {hostname}")
                hostnames.add(hostname)
                if not hostname.endswith(".reza.network"):
                    errors.append(f"{label}.web.hostname must be under reza.network")

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
                    require_nonempty_string(
                        auth.get("reason"), f"{label}.web.auth.reason", errors
                    )
                    if visibility == "public" and mode == "none":
                        errors.append(f"{label} cannot expose an unauthenticated public route")
                if mode in {"oidc", "forward-auth"}:
                    blueprint = require_nonempty_string(
                        auth.get("blueprint"), f"{label}.web.auth.blueprint", errors
                    )
                    application = require_nonempty_string(
                        auth.get("application"), f"{label}.web.auth.application", errors
                    )
                    content = blueprints.get(blueprint or "")
                    if blueprint is not None and content is None:
                        errors.append(
                            f"{label}.web.auth.blueprint is not present in "
                            "apps/authentik/application-blueprints.yaml"
                        )
                    elif content is not None and application is not None:
                        slug_pattern = re.compile(
                            rf"(?m)^\s+slug:\s*[\"']?{re.escape(application)}[\"']?\s*$"
                        )
                        if slug_pattern.search(content) is None:
                            errors.append(
                                f"{label}.web.auth.blueprint does not declare "
                                f"application slug {application}"
                            )
                    if mode == "oidc":
                        client_type = auth.get("client")
                        if client_type not in {"confidential", "public"}:
                            errors.append(
                                f"{label}.web.auth.client must be confidential or public"
                            )
                        elif content is not None and (
                            f"client_type: {client_type}" not in content
                        ):
                            errors.append(
                                f"{label}.web.auth.blueprint does not declare "
                                f"client_type: {client_type}"
                            )
                        if client_type == "confidential":
                            secret_env = require_nonempty_string(
                                auth.get("secretEnv"),
                                f"{label}.web.auth.secretEnv",
                                errors,
                            )
                            secret_references(
                                auth.get("secretFiles"),
                                f"{label}.web.auth.secretFiles",
                                errors,
                            )
                            if secret_env is not None:
                                if content is not None and secret_env not in content:
                                    errors.append(
                                        f"{label}.web.auth.secretEnv is not used by "
                                        "its Authentik blueprint"
                                    )
                                if secret_env not in authentik_workloads:
                                    errors.append(
                                        f"{label}.web.auth.secretEnv is not loaded by "
                                        "the Authentik worker"
                                    )
                    if mode == "forward-auth":
                        require_nonempty_string(
                            auth.get("middleware"),
                            f"{label}.web.auth.middleware",
                            errors,
                        )
                        if content is not None and "mode: forward_single" not in content:
                            errors.append(
                                f"{label}.web.auth.blueprint does not declare "
                                "mode: forward_single"
                            )

        placement = require_mapping(
            service.get("placement"), f"{label}.placement", errors
        )
        if placement is not None:
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
    path: Path, errors: list[str]
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
            if not isinstance(hostname, str) or not hostname.endswith(".reza.network"):
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
    actual, ip_allowlists = rendered_routes(rendered_path, errors)
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
    validate_generated_outputs(catalog, errors)

    temporary_render: Path | None = None
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
        "ID\tWEB\tAUTH\tPLACEMENT\tDATA\tOBSERVABILITY",
    )
    for service in services(catalog):
        web = service.get("web", {})
        print(
            "\t".join(
                [
                    str(service.get("id", "")),
                    str(web.get("hostname", "-")),
                    str(web.get("auth", {}).get("mode", "-")),
                    str(service.get("placement", {}).get("mode", "-")),
                    str(service.get("data", {}).get("protection", "-")),
                    str(service.get("observability", {}).get("mode", "-")),
                ]
            )
        )


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
    except (CatalogError, ManifestError, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
