#!/usr/bin/env python3
"""Compare high-risk Kubernetes constructs with an exact grandfathered baseline."""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable

from yaml_documents import ManifestError, github_error, iter_kubernetes_objects, load_documents


MUTABLE_TAGS = {"develop", "edge", "latest", "main", "master", "nightly", "snapshot"}
DIGEST_IMAGE = re.compile(r"@sha256:[0-9a-fA-F]{64}$")
IMAGE_FLAG = re.compile(r"^--[A-Za-z0-9][A-Za-z0-9_.-]*image$")
IMAGE_ENVIRONMENT = re.compile(r"(?:^|_)IMAGE$")
FULL_GIT_COMMIT = re.compile(r"^[0-9a-fA-F]{40}(?:[0-9a-fA-F]{24})?$")
EXACT_SEMVER = re.compile(
    r"^v?(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
CLUSTER_POD_NETWORKS = (ipaddress.ip_network("10.42.0.0/16"),)
REQUIRED_DEFAULT_DENY_NAMESPACES = {"apps", "media", "monitoring", "network-services"}


def text(value: Any, fallback: str) -> str:
    raw = str(value) if isinstance(value, (str, int)) else fallback
    return raw.replace("%", "%25").replace("|", "%7C").replace("\r", "%0D").replace(
        "\n", "%0A"
    )


def resource_id(document: dict[str, Any]) -> str:
    metadata = document.get("metadata") if isinstance(document.get("metadata"), dict) else {}
    return "|".join(
        (
            f"{text(document.get('apiVersion'), 'unknown')}/{text(document.get('kind'), 'unknown')}",
            text(metadata.get("namespace"), "default"),
            text(metadata.get("name"), "unnamed"),
        )
    )


def finding(rule: str, identity: str, location: str) -> str:
    return f"{rule}|{identity}|{location}"


def canonical_sha256(value: Any) -> str:
    canonical = json.dumps(value, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def pod_spec(document: dict[str, Any]) -> dict[str, Any] | None:
    kind = document.get("kind")
    spec = document.get("spec")
    if not isinstance(spec, dict):
        return None
    if kind == "Pod":
        return spec
    if kind == "CronJob":
        value = spec.get("jobTemplate", {})
        value = value.get("spec", {}) if isinstance(value, dict) else {}
        value = value.get("template", {}) if isinstance(value, dict) else {}
        value = value.get("spec") if isinstance(value, dict) else None
        return value if isinstance(value, dict) else None
    # Standard controllers and many CRDs use the same PodTemplateSpec shape.
    value = spec.get("template", {})
    value = value.get("spec") if isinstance(value, dict) else None
    if isinstance(value, dict):
        return value
    return None


def iter_containers(spec: dict[str, Any]) -> Iterable[tuple[str, dict[str, Any]]]:
    for field, label in (
        ("containers", "container"),
        ("initContainers", "init-container"),
        ("ephemeralContainers", "ephemeral-container"),
    ):
        containers = spec.get(field)
        if not isinstance(containers, list):
            continue
        for index, container in enumerate(containers):
            if isinstance(container, dict):
                name = text(container.get("name"), str(index))
                yield f"{label}/{name}", container


def iter_image_arguments(container: dict[str, Any]) -> Iterable[tuple[str, str]]:
    """Yield image references passed through explicit --*-image command flags."""
    for field in ("command", "args"):
        values = container.get(field)
        if not isinstance(values, list):
            continue
        index = 0
        while index < len(values):
            value = values[index]
            if not isinstance(value, str):
                index += 1
                continue
            flag, separator, image = value.partition("=")
            if separator and IMAGE_FLAG.fullmatch(flag) and image:
                yield f"{field}/{index}", image
            elif (
                IMAGE_FLAG.fullmatch(value)
                and index + 1 < len(values)
                and isinstance(values[index + 1], str)
            ):
                yield f"{field}/{index + 1}", values[index + 1]
                index += 1
            index += 1


def iter_image_environment(
    container: dict[str, Any],
) -> Iterable[tuple[str, str, str | None]]:
    """Yield env locations and values used as dynamic workload images."""
    environment = container.get("env")
    if not isinstance(environment, list):
        return
    for index, variable in enumerate(environment):
        if not isinstance(variable, dict):
            continue
        name = variable.get("name")
        if not isinstance(name, str) or IMAGE_ENVIRONMENT.search(name) is None:
            continue
        value = variable.get("value")
        yield f"env/{index}/{text(name, str(index))}", name, value if isinstance(value, str) else None


def mutable_tag(image: str) -> bool:
    if DIGEST_IMAGE.search(image):
        return False
    final_component = image.rsplit("/", 1)[-1]
    if ":" not in final_component:
        return True
    tag = final_component.rsplit(":", 1)[-1].lower()
    return tag in MUTABLE_TAGS or any(tag.endswith(f"-{suffix}") for suffix in MUTABLE_TAGS)


def walk(value: Any, path: tuple[str, ...] = ()) -> Iterable[tuple[tuple[str, ...], Any]]:
    yield path, value
    if isinstance(value, dict):
        for key, child in value.items():
            yield from walk(child, (*path, str(key)))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from walk(child, (*path, str(index)))


def git_ref_token(ref: Any) -> str:
    if not isinstance(ref, dict):
        return "<unset>"
    parts = [
        f"{key}={text(ref[key], '<unset>')}"
        for key in ("branch", "tag", "semver", "name", "commit")
        if ref.get(key) is not None
    ]
    return ",".join(parts) if parts else "<unset>"


def selector_is_universal(selector: Any) -> bool:
    if not isinstance(selector, dict):
        return False
    labels = selector.get("matchLabels")
    expressions = selector.get("matchExpressions")
    return not labels and not expressions


def cidr_is_default_route(cidr: Any) -> bool:
    if not isinstance(cidr, str):
        return False
    try:
        return ipaddress.ip_network(cidr, strict=False).prefixlen == 0
    except ValueError:
        return False


def cidr_overlaps_cluster_pods(cidr: Any) -> bool:
    if not isinstance(cidr, str):
        return False
    try:
        network = ipaddress.ip_network(cidr, strict=False)
    except ValueError:
        return False
    return any(network.overlaps(pod_network) for pod_network in CLUSTER_POD_NETWORKS)


def pod_findings(document: dict[str, Any], identity: str) -> set[str]:
    results: set[str] = set()
    spec = pod_spec(document)
    if spec is None:
        return results

    for key, rule in (
        ("hostNetwork", "host-network"),
        ("hostPID", "host-pid"),
        ("hostIPC", "host-ipc"),
        ("shareProcessNamespace", "shared-process-namespace"),
    ):
        if spec.get(key) is True:
            results.add(finding(rule, identity, "pod-spec"))
    # Kubernetes mounts a service-account token by default. New workloads must
    # opt out explicitly unless a reviewed baseline exception is added.
    if spec.get("automountServiceAccountToken") is not False:
        results.add(finding("service-account-token-mounted", identity, "pod-spec"))

    pod_security = spec.get("securityContext")
    pod_security = pod_security if isinstance(pod_security, dict) else {}
    if pod_security.get("runAsUser") == 0:
        results.add(finding("explicit-root-user", identity, "pod-security-context"))
    if pod_security.get("runAsGroup") == 0:
        results.add(finding("explicit-root-group", identity, "pod-security-context"))
    pod_seccomp = pod_security.get("seccompProfile")
    if isinstance(pod_seccomp, dict) and pod_seccomp.get("type") == "Unconfined":
        results.add(finding("unconfined-seccomp", identity, "pod-security-context"))
    windows_options = pod_security.get("windowsOptions")
    if isinstance(windows_options, dict) and windows_options.get("hostProcess") is True:
        results.add(finding("windows-host-process", identity, "pod-security-context"))
    sysctls = pod_security.get("sysctls")
    if isinstance(sysctls, list):
        for index, sysctl in enumerate(sysctls):
            if not isinstance(sysctl, dict):
                continue
            name = text(sysctl.get("name"), str(index))
            value = text(sysctl.get("value"), "<unset>")
            results.add(finding("pod-sysctl", identity, f"{name}/value/{value}"))

    volumes = spec.get("volumes")
    if isinstance(volumes, list):
        for index, volume in enumerate(volumes):
            if isinstance(volume, dict) and isinstance(volume.get("hostPath"), dict):
                name = text(volume.get("name"), str(index))
                path = text(volume["hostPath"].get("path"), "<unset>")
                results.add(finding("host-path", identity, f"volume/{name}/path/{path}"))

    for location, container in iter_containers(spec):
        security = container.get("securityContext")
        security = security if isinstance(security, dict) else {}
        if security.get("privileged") is True:
            results.add(finding("privileged-container", identity, location))
        if security.get("allowPrivilegeEscalation") is True:
            results.add(finding("allow-privilege-escalation", identity, location))
        if security.get("runAsUser") == 0:
            results.add(finding("explicit-root-user", identity, location))
        if security.get("runAsGroup") == 0:
            results.add(finding("explicit-root-group", identity, location))
        if security.get("procMount") == "Unmasked":
            results.add(finding("unmasked-proc", identity, location))
        seccomp = security.get("seccompProfile")
        if isinstance(seccomp, dict) and seccomp.get("type") == "Unconfined":
            results.add(finding("unconfined-seccomp", identity, location))
        windows_options = security.get("windowsOptions")
        if isinstance(windows_options, dict) and windows_options.get("hostProcess") is True:
            results.add(finding("windows-host-process", identity, location))

        capabilities = security.get("capabilities")
        added = capabilities.get("add") if isinstance(capabilities, dict) else None
        if isinstance(added, list):
            for capability in added:
                normalized = str(capability).upper()
                if normalized:
                    results.add(finding("added-capability", identity, f"{location}/{normalized}"))

        ports = container.get("ports")
        if isinstance(ports, list):
            for index, port in enumerate(ports):
                if not isinstance(port, dict) or not port.get("hostPort"):
                    continue
                port_name = text(port.get("name"), text(port.get("containerPort"), str(index)))
                results.add(
                    finding(
                        "host-port",
                        identity,
                        f"{location}/{port_name}/host-{port.get('hostPort')}",
                    )
                )

        image = container.get("image")
        if isinstance(image, str):
            image_token = text(image, "<unset>")
            if DIGEST_IMAGE.search(image) is None:
                results.add(finding("unpinned-image", identity, f"{location}/image/{image_token}"))
            if mutable_tag(image):
                results.add(
                    finding("mutable-image-tag", identity, f"{location}/image/{image_token}")
                )

        for argument_location, argument_image in iter_image_arguments(container):
            image_token = text(argument_image, "<unset>")
            location_token = f"{location}/{argument_location}/image-argument/{image_token}"
            if DIGEST_IMAGE.search(argument_image) is None:
                results.add(finding("unpinned-image-argument", identity, location_token))
            if mutable_tag(argument_image):
                results.add(finding("mutable-image-argument", identity, location_token))

        for environment_location, _, environment_image in iter_image_environment(container):
            if environment_image is None:
                results.add(
                    finding(
                        "indirect-image-environment",
                        identity,
                        f"{location}/{environment_location}",
                    )
                )
                continue
            image_token = text(environment_image, "<unset>")
            location_token = (
                f"{location}/{environment_location}/image-environment/{image_token}"
            )
            if DIGEST_IMAGE.search(environment_image) is None:
                results.add(finding("unpinned-image-environment", identity, location_token))
            if mutable_tag(environment_image):
                results.add(finding("mutable-image-environment", identity, location_token))

    return results


def rbac_findings(document: dict[str, Any], identity: str) -> set[str]:
    results: set[str] = set()
    kind = document.get("kind")
    if kind in {"ClusterRole", "Role"}:
        rules = document.get("rules")
        if isinstance(rules, list):
            for index, rule in enumerate(rules):
                if not isinstance(rule, dict):
                    continue
                for field in ("apiGroups", "resources", "verbs", "nonResourceURLs"):
                    values = rule.get(field)
                    if isinstance(values, list) and "*" in values:
                        results.add(
                            finding("wildcard-rbac", identity, f"rule/{index}/{field}")
                        )
                raw_verbs = rule.get("verbs")
                raw_resources = rule.get("resources")
                verbs = (
                    {str(value).lower() for value in raw_verbs}
                    if isinstance(raw_verbs, list)
                    else set()
                )
                resources = (
                    {str(value).lower() for value in raw_resources}
                    if isinstance(raw_resources, list)
                    else set()
                )
                for verb in sorted(verbs & {"bind", "escalate", "impersonate"}):
                    results.add(
                        finding("rbac-escalation-verb", identity, f"rule/{index}/verb/{verb}")
                    )
                names = rule.get("resourceNames")
                name_scope = (
                    ",".join(sorted(text(value, "<unset>") for value in names))
                    if isinstance(names, list) and names
                    else "all"
                )
                for resource in sorted(resources & {"secrets", "serviceaccounts/token"}):
                    for verb in sorted(verbs & {"create", "get", "list", "patch", "update", "watch"}):
                        results.add(
                            finding(
                                "rbac-secret-or-token-access",
                                identity,
                                f"rule/{index}/resource/{resource}/verb/{verb}/names/{name_scope}",
                            )
                        )
                for resource in sorted(
                    resources & {"pods/attach", "pods/ephemeralcontainers", "pods/exec", "pods/portforward"}
                ):
                    for verb in sorted(verbs & {"create", "get", "patch", "update"}):
                        results.add(
                            finding(
                                "rbac-workload-exec",
                                identity,
                                f"rule/{index}/resource/{resource}/verb/{verb}",
                            )
                        )
    if kind in {"ClusterRoleBinding", "RoleBinding"}:
        role_ref = document.get("roleRef")
        if isinstance(role_ref, dict) and role_ref.get("name") == "cluster-admin":
            results.add(finding("cluster-admin-binding", identity, "roleRef"))
    return results


def resource_findings(document: dict[str, Any]) -> set[str]:
    identity = resource_id(document)
    results = pod_findings(document, identity) | rbac_findings(document, identity)
    kind = document.get("kind")
    spec = document.get("spec") if isinstance(document.get("spec"), dict) else {}

    if kind == "Namespace":
        metadata = document.get("metadata")
        labels = metadata.get("labels") if isinstance(metadata, dict) else None
        if isinstance(labels, dict) and labels.get("pod-security.kubernetes.io/enforce") == "privileged":
            results.add(finding("privileged-namespace", identity, "pod-security-enforce"))

    if kind == "Middleware" and str(document.get("apiVersion", "")).startswith("traefik.io/"):
        results.add(
            finding("middleware-boundary", identity, f"spec/sha256/{canonical_sha256(spec)}")
        )
        ip_allow_list = spec.get("ipAllowList")
        ranges = ip_allow_list.get("sourceRange") if isinstance(ip_allow_list, dict) else None
        if isinstance(ranges, list):
            for cidr in ranges:
                if cidr_overlaps_cluster_pods(cidr):
                    results.add(
                        finding(
                            "pod-cidr-ip-allowlist",
                            identity,
                            f"spec.ipAllowList.sourceRange/{text(cidr, '<unset>')}",
                        )
                    )

    if kind == "ConfigMap" and re.fullmatch(
        r".+-access-proxy(?:-[a-z0-9]+)?",
        str(document.get("metadata", {}).get("name", "")),
    ):
        results.add(
            finding(
                "access-proxy-boundary",
                identity,
                f"data/sha256/{canonical_sha256(document.get('data', {}))}",
            )
        )

    if kind in {"ServersTransport", "TraefikService"} and str(
        document.get("apiVersion", "")
    ).startswith("traefik.io/"):
        results.add(
            finding(
                "traefik-backend-boundary",
                identity,
                f"spec/sha256/{canonical_sha256(spec)}",
            )
        )

    if kind in {
        "Gateway",
        "HTTPRoute",
        "GRPCRoute",
        "TCPRoute",
        "TLSRoute",
        "UDPRoute",
        "Ingress",
        "IngressRoute",
        "IngressRouteTCP",
        "IngressRouteUDP",
    }:
        results.add(
            finding("route-boundary", identity, f"spec/sha256/{canonical_sha256(spec)}")
        )

    if kind == "NetworkPolicy":
        policy_types = spec.get("policyTypes")
        if isinstance(policy_types, list) and "Ingress" in policy_types:
            ingress_boundary = {
                "podSelector": spec.get("podSelector"),
                "policyTypes": policy_types,
                "ingress": spec.get("ingress"),
            }
            results.add(
                finding(
                    "network-policy-ingress-boundary",
                    identity,
                    f"spec/sha256/{canonical_sha256(ingress_boundary)}",
                )
            )

        ingress = spec.get("ingress")
        if isinstance(ingress, list):
            for rule_index, rule in enumerate(ingress):
                if not isinstance(rule, dict):
                    continue
                peers = rule.get("from")
                if peers is None or peers == []:
                    results.add(
                        finding(
                            "universal-ingress-source",
                            identity,
                            f"ingress/{rule_index}/all-sources",
                        )
                    )
                    continue
                if not isinstance(peers, list):
                    continue
                for peer_index, peer in enumerate(peers):
                    if peer == {}:
                        results.add(
                            finding(
                                "universal-ingress-source",
                                identity,
                                f"ingress/{rule_index}/peer/{peer_index}/all-sources",
                            )
                        )
                        continue
                    if not isinstance(peer, dict):
                        continue
                    namespace_selector = peer.get("namespaceSelector")
                    if selector_is_universal(namespace_selector):
                        results.add(
                            finding(
                                "cluster-wide-ingress-source",
                                identity,
                                f"ingress/{rule_index}/peer/{peer_index}/all-namespaces",
                            )
                        )
                    ip_block = peer.get("ipBlock")
                    if isinstance(ip_block, dict) and cidr_is_default_route(
                        ip_block.get("cidr")
                    ):
                        exceptions = ip_block.get("except")
                        exception_token = (
                            ",".join(sorted(text(value, "<unset>") for value in exceptions))
                            if isinstance(exceptions, list) and exceptions
                            else "none"
                        )
                        results.add(
                            finding(
                                "internet-wide-ingress-source",
                                identity,
                                f"ingress/{rule_index}/peer/{peer_index}/cidr/{ip_block.get('cidr')}/except/{exception_token}",
                            )
                        )

        egress = spec.get("egress")
        if isinstance(egress, list):
            for rule_index, rule in enumerate(egress):
                if not isinstance(rule, dict):
                    continue
                peers = rule.get("to")
                if peers is None or peers == []:
                    results.add(
                        finding(
                            "universal-egress-destination",
                            identity,
                            f"egress/{rule_index}/all-destinations",
                        )
                    )
                    continue
                if not isinstance(peers, list):
                    continue
                for peer_index, peer in enumerate(peers):
                    if peer == {}:
                        results.add(
                            finding(
                                "universal-egress-destination",
                                identity,
                                f"egress/{rule_index}/peer/{peer_index}/all-destinations",
                            )
                        )
                        continue
                    if not isinstance(peer, dict):
                        continue
                    namespace_selector = peer.get("namespaceSelector")
                    if selector_is_universal(namespace_selector):
                        results.add(
                            finding(
                                "cluster-wide-egress-destination",
                                identity,
                                f"egress/{rule_index}/peer/{peer_index}/all-namespaces",
                            )
                        )
                    ip_block = peer.get("ipBlock")
                    if isinstance(ip_block, dict) and cidr_is_default_route(ip_block.get("cidr")):
                        exceptions = ip_block.get("except")
                        exception_token = (
                            ",".join(sorted(text(value, "<unset>") for value in exceptions))
                            if isinstance(exceptions, list) and exceptions
                            else "none"
                        )
                        results.add(
                            finding(
                                "internet-wide-egress-destination",
                                identity,
                                f"egress/{rule_index}/peer/{peer_index}/cidr/{ip_block.get('cidr')}/except/{exception_token}",
                            )
                        )

    if kind == "Service":
        service_type = spec.get("type", "ClusterIP")
        if service_type in {"ExternalName", "LoadBalancer", "NodePort"}:
            target = text(spec.get("externalName"), "<none>")
            results.add(
                finding("externally-exposed-service", identity, f"{service_type}/target/{target}")
            )
        external_ips = spec.get("externalIPs")
        if isinstance(external_ips, list) and external_ips:
            ips = ",".join(sorted(text(value, "<unset>") for value in external_ips))
            results.add(finding("service-external-ips", identity, f"spec.externalIPs/{ips}"))

    if kind == "GitRepository":
        source_url = text(spec.get("url"), "<unset>")
        ref = spec.get("ref")
        ref_token = git_ref_token(ref)
        if not isinstance(spec.get("verify"), dict):
            results.add(
                finding(
                    "unverified-git-source",
                    identity,
                    f"spec.verify/url/{source_url}/ref/{ref_token}",
                )
            )
        commit = ref.get("commit") if isinstance(ref, dict) else None
        if not isinstance(commit, str) or FULL_GIT_COMMIT.fullmatch(commit) is None:
            results.add(
                finding("mutable-git-ref", identity, f"spec.ref/{ref_token}/url/{source_url}")
            )

    if kind in {"HelmRepository", "GitRepository", "OCIRepository"}:
        results.add(
            finding(
                "external-source-boundary",
                identity,
                f"spec/sha256/{canonical_sha256(spec)}",
            )
        )
        url = spec.get("url")
        if isinstance(url, str) and url.startswith("http://"):
            results.add(finding("insecure-source-url", identity, f"spec.url/{text(url, '<unset>')}"))

    if kind == "HelmRepository":
        results.add(
            finding(
                "mutable-helm-repository",
                identity,
                f"spec.url/{text(spec.get('url'), '<unset>')}",
            )
        )

    if kind == "OCIRepository":
        ref = spec.get("ref")
        if not isinstance(ref, dict) or not ref.get("digest"):
            reference = ref.get("tag") if isinstance(ref, dict) else None
            reference = reference or (ref.get("semver") if isinstance(ref, dict) else None)
            results.add(
                finding(
                    "unpinned-oci-source",
                    identity,
                    f"spec.ref/{text(reference, '<unset>')}/url/{text(spec.get('url'), '<unset>')}",
                )
            )

    if kind == "HelmRelease":
        results.add(
            finding(
                "helm-release-boundary",
                identity,
                f"spec/sha256/{canonical_sha256(spec)}",
            )
        )
        chart = spec.get("chart")
        chart_ref = spec.get("chartRef")
        if isinstance(chart, dict):
            chart_spec = chart.get("spec")
            version = chart_spec.get("version") if isinstance(chart_spec, dict) else None
            source_ref = chart_spec.get("sourceRef") if isinstance(chart_spec, dict) else None
            source_kind = source_ref.get("kind") if isinstance(source_ref, dict) else None
            # GitRepository and Bucket charts are selected by artifact path;
            # their source revision, not a Helm index version, is the lock.
            version_is_required = source_kind not in {"GitRepository", "Bucket"}
            if version_is_required and (
                not isinstance(version, str) or EXACT_SEMVER.fullmatch(version) is None
            ):
                results.add(
                    finding(
                        "mutable-helm-chart",
                        identity,
                        f"spec.chart.spec.version/{text(version, '<unset>')}",
                    )
                )
        elif not isinstance(chart_ref, dict):
            results.add(
                finding(
                    "mutable-helm-chart",
                    identity,
                    "spec.chart.spec.version/<unset>",
                )
            )

        values = spec.get("values")
        for path, value in walk(values):
            if not path:
                continue
            key = path[-1]
            location = "spec.values." + ".".join(path)
            if key in {
                "allowPrivilegeEscalation",
                "hostIPC",
                "hostNetwork",
                "hostPID",
                "privileged",
            } and value is True:
                results.add(finding(f"helm-{key}", identity, location))
            if key == "allowExternalNameServices" and value is True:
                results.add(finding("helm-allow-external-name-services", identity, location))
            if key == "type" and value in {"ExternalName", "LoadBalancer", "NodePort"}:
                results.add(
                    finding(
                        "helm-externally-exposed-service",
                        identity,
                        f"{location}/value-{text(value, '<unset>')}",
                    )
                )
            if key == "externalIPs" and isinstance(value, list) and value:
                ips = ",".join(sorted(text(entry, "<unset>") for entry in value))
                results.add(finding("helm-service-external-ips", identity, f"{location}/{ips}"))
            if key == "hostPort" and isinstance(value, (int, str)) and str(value) not in {"", "0"}:
                results.add(finding("helm-host-port", identity, f"{location}/value-{text(value, '<unset>')}"))
            if key == "add" and len(path) >= 2 and path[-2] == "capabilities" and isinstance(value, list):
                for capability in value:
                    normalized = str(capability).upper()
                    if normalized:
                        results.add(
                            finding(
                                "helm-added-capability",
                                identity,
                                f"{location}.{normalized}",
                            )
                        )

        post_renderers = spec.get("postRenderers")
        if isinstance(post_renderers, list):
            for index, renderer in enumerate(post_renderers):
                if not isinstance(renderer, dict):
                    continue
                canonical = json.dumps(renderer, separators=(",", ":"), sort_keys=True)
                digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
                results.add(
                    finding(
                        "helm-post-renderer",
                        identity,
                        f"spec.postRenderers/{index}/sha256/{digest}",
                    )
                )

    if kind == "PersistentVolume" and (
        isinstance(spec.get("hostPath"), dict) or isinstance(spec.get("local"), dict)
    ):
        storage = spec.get("hostPath") if isinstance(spec.get("hostPath"), dict) else spec.get("local")
        path = text(storage.get("path"), "<unset>") if isinstance(storage, dict) else "<unset>"
        results.add(finding("node-local-persistent-volume", identity, f"spec/path/{path}"))

    return results


def detect(documents: list[Any]) -> set[str]:
    results: set[str] = set()
    resources: list[dict[str, Any]] = []
    for document in documents:
        for resource in iter_kubernetes_objects(document):
            if resource.get("kind"):
                resources.append(resource)
                results.update(resource_findings(resource))

    used_namespaces = {
        str(resource.get("metadata", {}).get("namespace"))
        for resource in resources
        if isinstance(resource.get("metadata"), dict)
        and resource.get("metadata", {}).get("namespace")
    }
    valid_default_denies: set[str] = set()
    for resource in resources:
        if resource.get("kind") != "NetworkPolicy":
            continue
        metadata = resource.get("metadata")
        spec = resource.get("spec")
        if not isinstance(metadata, dict) or not isinstance(spec, dict):
            continue
        namespace = metadata.get("namespace")
        policy_types = spec.get("policyTypes")
        if (
            metadata.get("name") == "default-deny"
            and isinstance(namespace, str)
            and selector_is_universal(spec.get("podSelector"))
            and isinstance(policy_types, list)
            and {"Ingress", "Egress"}.issubset(policy_types)
            and not spec.get("ingress")
            and not spec.get("egress")
        ):
            valid_default_denies.add(namespace)

    for namespace in sorted(REQUIRED_DEFAULT_DENY_NAMESPACES & used_namespaces):
        if namespace not in valid_default_denies:
            identity = f"networking.k8s.io/v1/NetworkPolicy|{namespace}|default-deny"
            results.add(finding("missing-default-deny", identity, "spec"))
    return results


def read_baseline(path: Path) -> tuple[list[str], set[str]]:
    lines = [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    return lines, set(lines)


def write_baseline(path: Path, findings: set[str]) -> None:
    header = (
        "# Grandfathered high-risk constructs that predate this guardrail.\n"
        "#\n"
        "# CI requires this list to be sorted, exact, and free of stale entries. Removing\n"
        "# a risk therefore also removes its exception; adding one requires an explicit\n"
        "# baseline change for review. Format: rule|apiVersion/kind|namespace|name|location\n"
    )
    body = "\n".join(sorted(findings))
    path.write_text(f"{header}{body}\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("baseline", type=Path)
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help="replace the baseline with findings from the supplied manifest",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        documents = load_documents(args.manifest)
    except ManifestError as error:
        github_error(str(error), path=args.manifest)
        return 1

    findings = detect(documents)
    if args.write_baseline:
        write_baseline(args.baseline, findings)
        print(f"Wrote {len(findings)} grandfathered finding(s) to {args.baseline}.")
        return 0

    if not args.baseline.is_file():
        github_error(f"high-risk baseline is missing: {args.baseline}")
        return 1

    baseline_lines, baseline = read_baseline(args.baseline)
    if baseline_lines != sorted(set(baseline_lines)):
        github_error(f"high-risk baseline must be sorted and contain no duplicates: {args.baseline}")
        return 1

    introduced = sorted(findings - baseline)
    stale = sorted(baseline - findings)
    if introduced:
        for item in introduced:
            github_error(f"new high-risk construct: {item}", path=args.baseline)
    if stale:
        for item in stale:
            github_error(
                f"stale high-risk exception (remove it to prevent reintroduction): {item}",
                path=args.baseline,
            )
    if introduced or stale:
        print(
            f"High-risk policy failed: {len(introduced)} new and {len(stale)} stale finding(s).",
            file=sys.stderr,
        )
        return 1

    print(f"High-risk policy matches {len(findings)} exact grandfathered finding(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
