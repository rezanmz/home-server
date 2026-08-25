#!/usr/bin/env python3
"""Validate repository-local agent guidance without external dependencies.

This checker intentionally proves structure and discovery wiring, not whether a
workflow is operationally correct. The latter still requires manual review and
the cold-reader exercise documented by the agent-guidance skill.
"""

from __future__ import annotations

import html
import json
import os
import re
import sys
import unicodedata
from fnmatch import fnmatchcase
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
FRONTMATTER = re.compile(r"\A---\n(?P<fields>.*?)\n---\n", re.DOTALL)
MARKDOWN_LINK = re.compile(
    r"(?<!!)\[[^\]\n]+\]\((?P<target><[^>\n]+>|[^\s)]+)"
    r"(?:\s+(?:\"[^\"]*\"|'[^']*'))?\)"
)
CODE_SPAN = re.compile(r"(?<!`)`([^`\n]+)`(?!`)")
INLINE_CODE_SPAN = re.compile(
    r"(?<!`)(?P<fence>`+)(?!`)(?P<body>[^\n]*?)(?<!`)(?P=fence)(?!`)"
)
REFERENCE_LINK = re.compile(r"(?<!!)\[[^\]\n]+\]\[[^\]\n]*\]")
H2 = re.compile(r"^## (.+?)\s*$", re.MULTILINE)

OMP_AGENTS = "@../AGENTS.md\n"
OMP_CONFIG = (
    "skills:\n"
    "  enableAgentsProject: false\n"
    "  customDirectories:\n"
    "    - skills\n"
)
CLAUDE_AGENTS = "@AGENTS.md\n"
OMP_RULES = (
    "# Home Server sticky safety\n\n"
    "The repository-root `AGENTS.md` is authoritative. Before any repository write,\n"
    "commit, push, pull-request action, merge, live cluster or host mutation,\n"
    "application-state mutation, external/provider mutation, credential action, or\n"
    "destructive action, re-read and obey its **Non-negotiable rules**,\n"
    "**Authorization boundaries**, and **Unsupported operations and hard stops**.\n\n"
    "Permission in one plane never implies permission in another. If `AGENTS.md`\n"
    "cannot be read or conflicts with an authoritative operator manual, stop and\n"
    "report the discrepancy. Discovery grants no authority.\n"
)
COPILOT_INSTRUCTIONS = (
    "# Home Server repository instructions\n\n"
    "Before inspecting, editing, reviewing, or operating this repository, read and\n"
    "follow the repository-root `AGENTS.md`. It is the authoritative repository-wide\n"
    "agent guide.\n\n"
    "Load the task-specific `skills/<name>/SKILL.md` selected by the routing table in\n"
    "`AGENTS.md`, then read the operator manual it names. Reusable task briefs under\n"
    "`prompts/` define required inputs, separate authorization for Git/live/\n"
    "external/destructive actions, and the evidence expected at completion.\n\n"
    "Do not duplicate or weaken those rules here. If instructions disagree, stop\n"
    "and report the conflict using the precedence rules in `AGENTS.md`.\n"
)
CURSOR_RULE = (
    "---\n"
    "description: Required operating entry point for every home-server repository task\n"
    "alwaysApply: true\n"
    "---\n\n"
    "Read and follow `AGENTS.md` before inspecting, editing, reviewing, or operating\n"
    "this repository. Load the task-specific `skills/<name>/SKILL.md` selected by its\n"
    "routing table and read the authoritative operator manual named by that skill.\n"
    "Use `prompts/` for reusable task briefs and explicit authorization boundaries.\n\n"
    "Do not copy rules into this file or silently resolve conflicts. Apply the\n"
    "precedence and stop conditions in `AGENTS.md`.\n"
)
EXPECTED_SHIMS = (
    (Path(".github/copilot-instructions.md"), "GitHub Copilot", COPILOT_INSTRUCTIONS),
    (Path(".cursor/rules/home-server.mdc"), "Cursor", CURSOR_RULE),
)
FORBIDDEN_BRIDGES = (
    Path(".claude/skills"),
    Path(".codex/skills"),
    Path(".cursor/skills"),
    Path(".github/skills"),
    Path(".omp/skills"),
    Path(".omp/prompts"),
    Path(".opencode/skills"),
)
YAML_NON_STRING_WORDS = {
    "~",
    ".inf",
    "+.inf",
    "-.inf",
    ".nan",
    "false",
    "no",
    "null",
    "off",
    "on",
    "true",
    "yes",
}
YAML_NUMBER = re.compile(
    r"[-+]?(?:"
    r"0[bB][01_]+|0[oO][0-7_]+|0[xX][0-9a-fA-F_]+|"
    r"[0-9][0-9_]*|"
    r"(?:[0-9][0-9_]*)?\.[0-9_]+(?:[eE][-+]?[0-9]+)?|"
    r"[0-9][0-9_]*(?:[eE][-+]?[0-9]+)"
    r")"
)
YAML_TIMESTAMP = re.compile(r"[0-9]{4}-[0-9]{1,2}-[0-9]{1,2}(?:[Tt ]\S+)?")


@dataclass(frozen=True)
class Finding:
    """One deterministic validation failure."""

    path: str
    message: str
    line: int = 1


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    path: Path


def relative_path(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def finding(root: Path, path: Path, message: str, line: int = 1) -> Finding:
    return Finding(relative_path(root, path), message, line)


def read_text(root: Path, path: Path, findings: list[Finding]) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        findings.append(finding(root, path, f"cannot read UTF-8 guidance: {error}"))
        return None


def repository_entries(root: Path) -> tuple[set[Path], set[Path]]:
    """Inventory actual entry names without following directory symlinks."""

    files: set[Path] = set()
    directories: set[Path] = set()
    for current, child_directories, child_files in os.walk(root, followlinks=False):
        current_path = Path(current)
        retained_directories: list[str] = []
        for name in child_directories:
            child = current_path / name
            if child == root / ".git":
                continue
            directories.add(child)
            if not child.is_symlink():
                retained_directories.append(name)
        child_directories[:] = retained_directories
        files.update(current_path / name for name in child_files)
    return files, directories


def matches_context_pattern(relative: Path, pattern: str) -> bool:
    """Case-sensitive component glob with portable zero-or-more ** semantics."""

    path_parts = relative.parts
    pattern_parts = tuple(part for part in pattern.split("/") if part)
    seen: set[tuple[int, int]] = set()

    def match(path_index: int, pattern_index: int) -> bool:
        state = (path_index, pattern_index)
        if state in seen:
            return False
        seen.add(state)
        if pattern_index == len(pattern_parts):
            return path_index == len(path_parts)
        component = pattern_parts[pattern_index]
        if component == "**":
            return match(path_index, pattern_index + 1) or (
                path_index < len(path_parts)
                and match(path_index + 1, pattern_index)
            )
        return (
            path_index < len(path_parts)
            and fnmatchcase(path_parts[path_index], component)
            and match(path_index + 1, pattern_index + 1)
        )

    return match(0, 0)


def parse_scalar(raw: str) -> str:
    """Parse the deliberately small scalar subset used by skill frontmatter."""

    if not raw or raw != raw.strip():
        raise ValueError("value must be nonempty with no surrounding whitespace")
    if raw.startswith('"'):
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as error:
            raise ValueError(f"invalid double-quoted scalar: {error.msg}") from error
        if not isinstance(value, str):
            raise ValueError("quoted value must decode to a string")
        return value
    if raw.startswith("'"):
        if len(raw) < 2 or not raw.endswith("'"):
            raise ValueError("unterminated single-quoted scalar")
        inner = raw[1:-1]
        index = 0
        while index < len(inner):
            if inner[index] != "'":
                index += 1
                continue
            if index + 1 >= len(inner) or inner[index + 1] != "'":
                raise ValueError("single quote inside a single-quoted scalar must be doubled")
            index += 2
        return inner.replace("''", "'")
    if raw[0] in "-?:,[]{}#&*!|>'\"%@`":
        raise ValueError("plain scalar starts with a YAML indicator; quote it")
    if ": " in raw or re.search(r"\s#", raw):
        raise ValueError("unsafe YAML plain scalar; quote values containing ': ' or comments")
    if (
        raw.casefold() in YAML_NON_STRING_WORDS
        or YAML_NUMBER.fullmatch(raw) is not None
        or YAML_TIMESTAMP.fullmatch(raw) is not None
    ):
        raise ValueError("plain scalar resolves to a non-string YAML type; quote it")
    return raw


def parse_skill(root: Path, path: Path, findings: list[Finding]) -> Skill | None:
    text = read_text(root, path, findings)
    if text is None:
        return None
    match = FRONTMATTER.match(text)
    if match is None:
        findings.append(
            finding(root, path, "SKILL.md must start with closed YAML frontmatter")
        )
        return None

    values: dict[str, str] = {}
    field_lines: dict[str, int] = {}
    for offset, raw_line in enumerate(match.group("fields").splitlines(), start=2):
        field_match = re.fullmatch(r"([a-z][a-z0-9-]*): (.+)", raw_line)
        if field_match is None:
            findings.append(
                finding(
                    root,
                    path,
                    "frontmatter fields must use one-line 'key: value' syntax",
                    offset,
                )
            )
            continue
        key, raw_value = field_match.groups()
        if key in values:
            findings.append(finding(root, path, f"duplicate frontmatter field: {key}", offset))
            continue
        try:
            values[key] = parse_scalar(raw_value)
            field_lines[key] = offset
        except ValueError as error:
            findings.append(finding(root, path, f"invalid {key!r} value: {error}", offset))

    expected_fields = {"name", "description"}
    fields_complete = set(values) == expected_fields
    if not fields_complete:
        missing = sorted(expected_fields - set(values))
        extra = sorted(set(values) - expected_fields)
        detail: list[str] = []
        if missing:
            detail.append(f"missing {', '.join(missing)}")
        if extra:
            detail.append(f"unsupported {', '.join(extra)}")
        findings.append(
            finding(
                root,
                path,
                "frontmatter must contain exactly name and description"
                + (f" ({'; '.join(detail)})" if detail else ""),
            )
        )
    name = values.get("name")
    description = values.get("description")
    if name is not None and (
        not 1 <= len(name) <= 64 or SKILL_NAME.fullmatch(name) is None
    ):
        findings.append(
            finding(
                root,
                path,
                "skill name must be 1-64 lowercase letters/numbers/hyphens with no "
                "leading, trailing, or consecutive hyphen",
                field_lines["name"],
            )
        )
    if name is not None and name != path.parent.name:
        findings.append(
            finding(
                root,
                path,
                f"skill name {name!r} does not match directory {path.parent.name!r}",
                field_lines["name"],
            )
        )
    if description is not None and not 1 <= len(description) <= 1024:
        findings.append(
            finding(root, path, "skill description must be 1-1024 characters", field_lines["description"])
        )
    if description is not None and re.search(
        r"\bUse\s+(?:for|when|before)\b", description
    ) is None:
        findings.append(
            finding(
                root,
                path,
                "skill description must state when to use it",
                field_lines["description"],
            )
        )

    body = text[match.end() :]
    if re.match(r"\s*#\s+\S", body) is None:
        findings.append(finding(root, path, "skill body must start with a level-one heading"))
    if not fields_complete or name is None or description is None:
        return None
    return Skill(name=name, description=description, path=path)


def section(text: str, heading_prefix: str) -> str | None:
    """Return the first H2 section whose title starts with heading_prefix."""

    headings = list(H2.finditer(text))
    for index, match in enumerate(headings):
        if match.group(1).startswith(heading_prefix):
            end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
            return text[match.end() : end]
    return None


def mask_fenced_code(text: str) -> str:
    def blank(line: str) -> str:
        ending = "\n" if line.endswith("\n") else ""
        return " " * (len(line) - len(ending)) + ending

    output: list[str] = []
    fence: str | None = None
    for line in text.splitlines(keepends=True):
        marker = re.match(r"^\s*(```+|~~~+)", line)
        if marker is not None:
            candidate = marker.group(1)[0]
            if fence is None:
                fence = candidate
            elif fence == candidate:
                fence = None
            output.append(blank(line))
        elif fence is None:
            output.append(line)
        else:
            output.append(blank(line))
    return "".join(output)


def mask_inline_code(text: str) -> str:
    """Hide inline code while preserving offsets used for line annotations."""

    return INLINE_CODE_SPAN.sub(lambda match: " " * len(match.group(0)), text)


def markdown_slug(title: str) -> str:
    title = html.unescape(title)
    title = re.sub(r"<[^>]*>", "", title)
    title = re.sub(r"!\[([^]]*)\]\([^)]*\)", r"\1", title)
    title = re.sub(r"\[([^]]+)\]\([^)]*\)", r"\1", title)
    title = re.sub(r"[`*_~]", "", title).strip().lower()
    title = "".join(
        character
        for character in title
        if not unicodedata.category(character).startswith("P") or character in "-_"
    )
    return re.sub(r"\s+", "-", title)


def markdown_anchors(text: str) -> set[str]:
    counts: Counter[str] = Counter()
    anchors: set[str] = set()
    for line in mask_fenced_code(text).splitlines():
        match = re.match(r"^#{1,6}\s+(.+?)\s*#*\s*$", line)
        if match is None:
            continue
        base = markdown_slug(match.group(1))
        suffix = counts[base]
        counts[base] += 1
        anchors.add(base if suffix == 0 else f"{base}-{suffix}")
    return anchors


def guidance_files(root: Path, skills: list[Skill], prompts: list[Path]) -> list[Path]:
    candidates = [
        root / "AGENTS.md",
        root / "README.md",
        root / "CLAUDE.md",
        root / "skills/README.md",
        root / "prompts/README.md",
        root / ".github/copilot-instructions.md",
        root / ".cursor/rules/home-server.mdc",
        root / ".omp/AGENTS.md",
        root / ".omp/RULES.md",
    ]
    candidates.extend(skill.path for skill in skills)
    candidates.extend(prompts)
    return sorted(set(candidates), key=lambda item: item.as_posix())


def validate_link(
    root: Path,
    source: Path,
    text: str,
    match: re.Match[str],
    findings: list[Finding],
) -> None:
    raw_target = match.group("target")
    if raw_target.startswith("<") and raw_target.endswith(">"):
        raw_target = raw_target[1:-1]
    split = urlsplit(raw_target)
    if split.scheme or split.netloc:
        if split.scheme not in {"http", "https", "mailto"}:
            findings.append(
                finding(
                    root,
                    source,
                    f"unsupported or workstation-local link scheme: {split.scheme}",
                    text.count("\n", 0, match.start()) + 1,
                )
            )
        return

    decoded_path = unquote(split.path)
    line = text.count("\n", 0, match.start()) + 1
    if decoded_path.startswith(("/", "~")):
        findings.append(finding(root, source, f"local link must be repository-relative: {raw_target}", line))
        return
    target = source if not decoded_path else source.parent / decoded_path
    try:
        resolved = target.resolve(strict=False)
        resolved.relative_to(root.resolve())
    except (OSError, ValueError, RuntimeError):
        findings.append(finding(root, source, f"local link escapes the repository: {raw_target}", line))
        return
    if not resolved.exists():
        findings.append(finding(root, source, f"local link target does not exist: {raw_target}", line))
        return
    if split.fragment:
        if not resolved.is_file() or resolved.suffix.lower() != ".md":
            findings.append(finding(root, source, f"fragment target is not Markdown: {raw_target}", line))
            return
        target_text = read_text(root, resolved, findings)
        if target_text is not None and unquote(split.fragment) not in markdown_anchors(target_text):
            findings.append(finding(root, source, f"Markdown fragment does not exist: {raw_target}", line))

    parts = resolved.parts
    if resolved.name == "SKILL.md" and "skills" in parts:
        skill_index = len(parts) - 1 - list(reversed(parts)).index("skills")
        if skill_index + 2 == len(parts) - 1:
            expected_name = parts[skill_index + 1]
            original_match = text[match.start() : match.end()]
            label_match = re.match(r"\[([^]]+)\]", original_match)
            label = label_match.group(1).strip(" `") if label_match else ""
            if label != expected_name:
                findings.append(
                    finding(
                        root,
                        source,
                        f"skill link label {label!r} must match target skill {expected_name!r}",
                        line,
                    )
                )


def validate_links(
    root: Path, files: list[Path], findings: list[Finding]
) -> None:
    for path in files:
        text = read_text(root, path, findings)
        if text is None:
            continue
        visible = mask_inline_code(mask_fenced_code(text))
        for match in REFERENCE_LINK.finditer(visible):
            findings.append(
                finding(
                    root,
                    path,
                    "reference-style Markdown links are forbidden in agent guidance; "
                    "use an inline link so its target can be validated",
                    text.count("\n", 0, match.start()) + 1,
                )
            )
        for match in MARKDOWN_LINK.finditer(visible):
            validate_link(root, path, text, match, findings)


def validate_adapters(root: Path, findings: list[Finding]) -> None:
    repository_files, repository_directories = repository_entries(root)
    agents_skills = root / ".agents/skills"
    expected_skills = (root / "skills").resolve()
    if not agents_skills.is_symlink():
        findings.append(
            finding(
                root,
                agents_skills,
                ".agents/skills must be a symlink to the canonical ../skills directory",
            )
        )
    else:
        link_value = os.readlink(agents_skills)
        try:
            resolved_link = agents_skills.resolve(strict=True)
        except (OSError, RuntimeError):
            resolved_link = None
        if link_value != "../skills" or resolved_link != expected_skills:
            findings.append(
                finding(
                    root,
                    agents_skills,
                    ".agents/skills symlink target must be exactly ../skills",
                )
            )

    claude_path = root / "CLAUDE.md"
    claude = read_text(root, claude_path, findings)
    if claude is not None and claude != CLAUDE_AGENTS:
        findings.append(
            finding(root, claude_path, "Claude adapter must be exactly '@AGENTS.md'")
        )

    omp_agents_path = root / ".omp/AGENTS.md"
    omp_agents = read_text(root, omp_agents_path, findings)
    if omp_agents is not None and omp_agents != OMP_AGENTS:
        findings.append(
            finding(root, omp_agents_path, "OMP AGENTS adapter must be exactly '@../AGENTS.md'")
        )

    omp_config_path = root / ".omp/config.yml"
    omp_config = read_text(root, omp_config_path, findings)
    if omp_config is not None and omp_config != OMP_CONFIG:
        findings.append(
            finding(
                root,
                omp_config_path,
                "OMP config must disable skills.enableAgentsProject and contain only "
                "skills.customDirectories: ['skills']",
            )
        )

    rules_path = root / ".omp/RULES.md"
    rules = read_text(root, rules_path, findings)
    if rules is not None:
        if rules != OMP_RULES:
            findings.append(
                finding(root, rules_path, "OMP sticky-rules adapter must match the canonical meta-gate exactly")
            )
        words = re.findall(r"\b[\w'-]+\b", rules)
        normalized = re.sub(r"\s+", " ", rules).lower()
        if len(words) > 120:
            findings.append(finding(root, rules_path, "OMP sticky rules must stay at or below 120 words"))
        if any(
            re.search(pattern, rules, re.MULTILINE)
            for pattern in (r"^## ", r"^\s*(?:[-*]|\d+\.)\s+", r"```", r"^\s*\|")
        ):
            findings.append(
                finding(root, rules_path, "OMP sticky rules must be a short meta-only pointer, not copied policy")
            )
        for concept in ("agents.md", "no authority", "stop"):
            if concept not in normalized:
                findings.append(
                    finding(root, rules_path, f"OMP sticky rules must include the meta-gate concept {concept!r}")
                )

    for shim, runtime, expected in EXPECTED_SHIMS:
        path = root / shim
        text = read_text(root, path, findings)
        if text is None:
            continue
        if text != expected:
            findings.append(
                finding(root, path, f"{runtime} adapter must match its canonical thin pointer exactly")
            )
        body = text
        if shim.suffix == ".mdc" and body.startswith("---\n"):
            match = FRONTMATTER.match(body)
            if match is None:
                findings.append(finding(root, path, "Cursor adapter has malformed frontmatter"))
                continue
            body = body[match.end() :]
        words = re.findall(r"\b[\w'-]+\b", body)
        if len(words) > 180:
            findings.append(finding(root, path, "runtime adapter must stay at or below 180 words"))
        if any(
            re.search(pattern, body, re.MULTILINE)
            for pattern in (r"^## ", r"^\s*(?:[-*]|\d+\.)\s+", r"```", r"^\s*\|")
        ):
            findings.append(
                finding(root, path, "runtime adapter must remain a thin pointer without policy sections")
            )
        for target in ("AGENTS.md", "skills/<name>/SKILL.md", "prompts/"):
            if target not in body:
                findings.append(finding(root, path, f"runtime adapter must point to {target}"))

    exact_adapter_entries = {
        root / ".agents": {root / ".agents/skills"},
        root / ".omp": {
            root / ".omp/AGENTS.md",
            root / ".omp/RULES.md",
            root / ".omp/config.yml",
        },
        root / ".cursor": {root / ".cursor/rules"},
        root / ".cursor/rules": {root / ".cursor/rules/home-server.mdc"},
    }
    for adapter_root, allowed_entries in exact_adapter_entries.items():
        if not adapter_root.is_dir():
            continue
        for unexpected in sorted(set(adapter_root.iterdir()) - allowed_entries):
            findings.append(
                finding(
                    root,
                    unexpected,
                    "unexpected adapter entry; this runtime directory is reserved for "
                    "the canonical discovery bridge",
                )
            )

    project_runtime_directories = {
        ".agent",
        ".agents",
        ".claude",
        ".codex",
        ".cursor",
        ".gemini",
        ".omp",
        ".opencode",
        ".windsurf",
    }
    allowed_root_runtime_directories = {".agents", ".cursor", ".omp"}
    for directory in sorted(repository_directories):
        if directory.name not in project_runtime_directories:
            continue
        if directory.parent == root and directory.name in allowed_root_runtime_directories:
            continue
        findings.append(
            finding(
                root,
                directory,
                "runtime context directory is not a canonical adapter and can add or "
                "shadow instructions, tools, hooks, plugins, or permissions",
            )
        )

    for overlay_name in ("agents", "hooks", "instructions", "prompts"):
        overlay = root / ".github" / overlay_name
        if overlay.exists() or overlay.is_symlink():
            findings.append(
                finding(
                    root,
                    overlay,
                    "GitHub agent overlay directory is forbidden; use canonical guidance",
                )
            )

    for bridge in FORBIDDEN_BRIDGES:
        if (root / bridge).exists() or (root / bridge).is_symlink():
            findings.append(
                finding(
                    root,
                    root / bridge,
                    "copied/symlinked skill or prompt bridge is forbidden; OMP uses the canonical custom directory",
                )
            )

    runtime_skill_patterns = (
        "**/.agents/skills",
        "**/.claude/skills",
        "**/.codex/skills",
        "**/.cursor/skills",
        "**/.github/skills",
        "**/.omp/skills",
        "**/.opencode/skills",
    )
    runtime_skill_suffixes = {
        tuple(Path(pattern.removeprefix("**/")).parts)
        for pattern in runtime_skill_patterns
    }
    for skill_root in sorted(repository_directories):
        relative_parts = skill_root.relative_to(root).parts
        if not any(
            len(relative_parts) >= len(suffix)
            and relative_parts[-len(suffix) :] == suffix
            for suffix in runtime_skill_suffixes
        ):
            continue
        if skill_root == agents_skills:
            continue
        findings.append(
            finding(
                root,
                skill_root,
                "runtime-specific skill tree is forbidden; use canonical root skills/",
            )
        )

    context_directory_sequences = {
        (".agent", "rules"),
        (".agents", "rules"),
        (".claude", "rules"),
        (".cursor", "rules"),
        (".github", "instructions"),
        (".omp", "instructions"),
        (".omp", "rules"),
        (".opencode", "commands"),
        (".windsurf", "rules"),
    }
    runtime_directory_names = {
        ".agent",
        ".agents",
        ".claude",
        ".codex",
        ".cursor",
        ".gemini",
        ".omp",
        ".opencode",
        ".windsurf",
        ".clinerules",
    }
    for entry in sorted(repository_directories | repository_files):
        if not entry.is_symlink() or entry == agents_skills:
            continue
        parts = entry.relative_to(root).parts
        contains_context_sequence = any(
            any(parts[index : index + len(sequence)] == sequence for index in range(len(parts)))
            for sequence in context_directory_sequences
        )
        if entry.name in runtime_directory_names or contains_context_sequence:
            findings.append(
                finding(
                    root,
                    entry,
                    "symlinked runtime context tree is forbidden; it can hide auto-loaded guidance",
                )
            )

    allowed_context = {
        root / "AGENTS.md",
        root / "CLAUDE.md",
        root / ".github/copilot-instructions.md",
        root / ".cursor/rules/home-server.mdc",
        root / ".omp/AGENTS.md",
        root / ".omp/RULES.md",
    }
    context_patterns = (
        "**/AGENTS.md",
        "**/agents.md",
        "**/AGENTS.override.md",
        "**/CLAUDE.md",
        "**/CLAUDE.local.md",
        "**/GEMINI.md",
        "**/mcp.json",
        "**/.mcp.json",
        "**/.vscode/mcp.json",
        "**/opencode.json",
        "**/opencode.jsonc",
        "**/REVIEW.md",
        "**/WATCHDOG.md",
        "**/WATCHDOG.yml",
        "**/WATCHDOG.yaml",
        "**/.agent/SYSTEM.md",
        "**/.agents/SYSTEM.md",
        "**/.agent/rules/*.md",
        "**/.agent/rules/*.mdc",
        "**/.agents/rules/*.md",
        "**/.agents/rules/*.mdc",
        "**/.claude/SYSTEM.md",
        "**/.claude/APPEND_SYSTEM.md",
        "**/.claude/rules/*.md",
        "**/.claude/rules/**/*.md",
        "**/.codex/SYSTEM.md",
        "**/.codex/APPEND_SYSTEM.md",
        "**/.cursor/rules/*.md",
        "**/.cursor/rules/*.mdc",
        "**/.cursor/rules/**/*.mdc",
        "**/.github/instructions/*.instructions.md",
        "**/.github/instructions/**/*.instructions.md",
        "**/.gemini/SYSTEM.md",
        "**/.gemini/system.md",
        "**/.gemini/APPEND_SYSTEM.md",
        "**/.omp/SYSTEM.md",
        "**/.omp/APPEND_SYSTEM.md",
        "**/.omp/RULES.md",
        "**/.omp/WATCHDOG.md",
        "**/.omp/WATCHDOG.yml",
        "**/.omp/WATCHDOG.yaml",
        "**/.omp/instructions/*.md",
        "**/.omp/rules/*.md",
        "**/.omp/rules/*.mdc",
        "**/.opencode/commands/*.md",
        "**/.windsurf/rules/**/*.md",
        "**/.clinerules",
        "**/.clinerules/**/*.md",
        "**/.cursorrules",
        "**/.windsurfrules",
    )
    discovered_context = {
        candidate
        for candidate in repository_files
        if any(
            matches_context_pattern(candidate.relative_to(root), pattern)
            for pattern in context_patterns
        )
    }
    for unexpected in sorted(discovered_context - allowed_context):
        findings.append(
            finding(
                root,
                unexpected,
                "unexpected auto-loaded context file can shadow or duplicate canonical guidance",
            )
        )


def validate_routing(
    root: Path, skills: dict[str, Skill], findings: list[Finding]
) -> None:
    path = root / "AGENTS.md"
    text = read_text(root, path, findings)
    if text is None:
        return
    routing = section(text, "Task routing")
    if routing is None:
        findings.append(finding(root, path, "AGENTS.md is missing the Task routing section"))
        return

    routed: list[str] = []
    for line_number, line in enumerate(routing.splitlines(), start=1):
        if not line.startswith("|") or re.match(r"^\|\s*(?:Task|-)", line):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 3:
            continue
        skill_match = re.fullmatch(r"`([a-z0-9-]+)`", cells[1])
        if skill_match is None:
            findings.append(finding(root, path, f"routing row has invalid skill cell: {cells[1]!r}"))
            continue
        routed.append(skill_match.group(1))
        for token in CODE_SPAN.findall(cells[2]):
            if not ("/" in token or token.endswith((".md", ".py", ".json", ".yml", ".yaml"))):
                continue
            if token.startswith(("/", "~")) or ".." in Path(token).parts:
                findings.append(finding(root, path, f"routing source escapes repository: {token}"))
                continue
            if any(character in token for character in "*?["):
                if not list(root.glob(token)):
                    findings.append(finding(root, path, f"routing source glob has no matches: {token}"))
            elif not (root / token).exists():
                findings.append(finding(root, path, f"routing source does not exist: {token}"))

    counts = Counter(routed)
    for name in sorted(set(skills) - set(counts)):
        findings.append(finding(root, path, f"canonical skill is missing from Task routing: {name}"))
    for name in sorted(set(counts) - set(skills)):
        findings.append(finding(root, path, f"Task routing references unknown skill: {name}"))
    for name, count in sorted(counts.items()):
        if count > 1:
            findings.append(finding(root, path, f"Task routing contains skill {name!r} {count} times"))


def normalize_prose(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[-/]", " ", text.lower())).strip()


def validate_prompt(
    root: Path,
    path: Path,
    skill_names: set[str],
    findings: list[Finding],
) -> None:
    text = read_text(root, path, findings)
    if text is None:
        return
    if not text.startswith("# Task brief:"):
        findings.append(finding(root, path, "prompt must start with '# Task brief:'"))
    if len(path.stem) > 64 or SKILL_NAME.fullmatch(path.stem) is None:
        findings.append(
            finding(root, path, "prompt filename must be a lowercase hyphenated slug of at most 64 characters")
        )

    required_sections = ("Required inputs", "Authorization", "Manuals", "Acceptance criteria")
    sections: dict[str, str] = {}
    for name in required_sections:
        content = section(text, name)
        if content is None:
            findings.append(finding(root, path, f"prompt is missing required section: {name}"))
        else:
            sections[name] = content
    if len(sections) != len(required_sections):
        return

    headings = H2.findall(text)
    authorization_headings = [
        heading for heading in headings if heading.casefold().startswith("authorization")
    ]
    if authorization_headings != ["Authorization"]:
        findings.append(
            finding(
                root,
                path,
                "prompt must contain exactly one H2 named 'Authorization' and no override section",
            )
        )
    has_workflow = any("workflow" in heading.lower() for heading in headings) or {
        "Read-only diagnosis",
        "Choose the corrective path",
        "Validation and protected deployment",
    }.issubset(headings)
    if not has_workflow:
        findings.append(finding(root, path, "prompt is missing a workflow contract"))
    if not any(heading.startswith("Hard stops") for heading in headings):
        findings.append(finding(root, path, "prompt is missing a hard-stop contract"))

    rollback = section(text, "Rollback and recovery")
    evidence = section(text, "Evidence contract")
    combined_rollback_evidence = section(text, "Rollback and evidence")
    if rollback is None and combined_rollback_evidence is None:
        findings.append(finding(root, path, "prompt is missing a rollback/recovery contract"))
    if evidence is None and combined_rollback_evidence is None:
        findings.append(finding(root, path, "prompt is missing an evidence contract"))
    evidence_text = normalize_prose(evidence or combined_rollback_evidence or "")
    missing_action_evidence = [
        concept
        for concept in ("workflow", "registry", "artifact")
        if concept not in evidence_text
    ]
    if missing_action_evidence:
        findings.append(
            finding(
                root,
                path,
                "Evidence contract must record workflow, registry, and artifact actions "
                f"(missing: {', '.join(missing_action_evidence)})",
            )
        )

    manuals = sections["Manuals"]
    code_tokens = CODE_SPAN.findall(manuals)
    referenced_skills = {token for token in code_tokens if token in skill_names}
    for token in code_tokens:
        if SKILL_NAME.fullmatch(token) and token not in skill_names:
            findings.append(finding(root, path, f"Manuals section references unknown skill: {token}"))
    if "home-server-safety" not in referenced_skills:
        findings.append(finding(root, path, "prompt must load the home-server-safety skill"))
    if len(referenced_skills) < 2:
        findings.append(finding(root, path, "prompt must load at least one task-specific skill"))

    authorization = sections["Authorization"]
    authorization_fields = list(
        re.finditer(
            r"^- ([^:\n]+):[ \t]*(.*(?:\n[ \t]{2,}\S[^\n]*)*)",
            authorization,
            re.MULTILINE,
        )
    )
    for line_number, line in enumerate(authorization.splitlines(), start=1):
        if re.match(r"^\s*-\s+", line) and re.match(r"^- [^:\n]+:\s*\S", line) is None:
            findings.append(
                finding(
                    root,
                    path,
                    "Authorization bullets must be top-level 'Label: [yes/no; exact scope]' fields",
                    line_number,
                )
            )
    labels = [
        " ".join(re.findall(r"[a-z0-9]+", match.group(1).casefold()))
        for match in authorization_fields
    ]
    for match in authorization_fields:
        value = " ".join(match.group(2).split())
        placeholder = re.fullmatch(r"\[yes/no(?:; (?P<scope>[^\]]+))?\]", value)
        if placeholder is None:
            findings.append(
                finding(
                    root,
                    path,
                    f"Authorization field {match.group(1).strip()!r} must remain an "
                    "unfilled [yes/no; exact scope] placeholder",
                )
            )
        else:
            scope = placeholder.group("scope") or ""
            if re.search(r"\byes\b", scope, re.IGNORECASE):
                findings.append(
                    finding(
                        root,
                        path,
                        f"Authorization field {match.group(1).strip()!r} must not "
                        "contain a standing yes/default grant",
                    )
                )

    core_fields = {
        "repository edits": (r"repository edits",),
        "commit creation": (r"create commits",),
        "branch push": (r"push (?:a )?branch",),
        "pull-request action": (r"open or update a pull request",),
        "merge": (r"merge", r"merge (?:to )?protected main"),
        "read-only cluster/host access": (
            r"read only cluster host access",
            r"read only cluster host network access",
        ),
        "live cluster/host mutation": (
            r"live cluster mutation",
            r"live cluster host mutation",
            r"live cluster host mutation beyond automatic flux",
            r"live cluster host mutation reconcile restart scale or pod deletion",
            r"live cluster host mutation reconcile scale restart or delete updater resources",
        ),
        "application-state mutation": (r"application state mutation",),
        "external/provider mutation": (
            r"external provider mutation",
            r"external provider mutation not otherwise listed",
        ),
        "destructive actions": (
            r"destructive actions",
            r"destructive actions not otherwise listed",
        ),
    }
    core_matches = {
        field: {
            index
            for index, label in enumerate(labels)
            if any(re.fullmatch(pattern, label) for pattern in patterns)
        }
        for field, patterns in core_fields.items()
    }
    missing_core_fields = [
        field for field, matches in core_matches.items() if not matches
    ]
    if missing_core_fields:
        findings.append(
            finding(
                root,
                path,
                "Authorization is missing core permission field(s): "
                + ", ".join(missing_core_fields),
            )
        )
    duplicate_core_fields = [
        field for field, matches in core_matches.items() if len(matches) > 1
    ]
    if duplicate_core_fields:
        findings.append(
            finding(
                root,
                path,
                "Authorization must contain exactly one field for each core permission "
                f"plane (duplicates: {', '.join(duplicate_core_fields)})",
            )
        )
    overlapping_core_fields = sorted(
        f"{first}/{second}"
        for first, first_matches in core_matches.items()
        for second, second_matches in core_matches.items()
        if first < second and first_matches & second_matches
    )
    if overlapping_core_fields:
        findings.append(
            finding(
                root,
                path,
                "Authorization must use distinct fields for every core permission plane "
                f"(combined: {', '.join(overlapping_core_fields)})",
            )
        )

    workflow_labels = {
        index
        for index, label in enumerate(labels)
        if re.fullmatch(
            r"(?:remote workflow dispatch or rerun|dispatch or rerun an image workflow)",
            label,
        )
    }
    publication_labels = {
        index
        for index, label in enumerate(labels)
        if re.fullmatch(
            r"(?:registry or artifact publication|publish overwrite a registry tag|"
            r"publish or overwrite a registry artifact)",
            label,
        )
    }
    if (
        len(workflow_labels) != 1
        or len(publication_labels) != 1
        or workflow_labels & publication_labels
    ):
        findings.append(
            finding(
                root,
                path,
                "Authorization must use separate fields for remote workflow dispatch/rerun "
                "and artifact publication",
            )
        )
    credential_labels = {
        index
        for index, label in enumerate(labels)
        if re.fullmatch(
            r"(?:credential or secret material (?:action|mutation)|"
            r"edit rotate revoke a secret or external credential|"
            r"edit rotate revoke bearer wi fi or ota credentials)",
            label,
        )
    }
    if len(credential_labels) != 1:
        findings.append(
            finding(
                root,
                path,
                "Authorization must include exactly one explicit credential/secret-material permission",
            )
        )

    standing_grant_patterns = (
        r"\b(?:all|any|these|the above)\b[^\n.]{0,100}\b(?:are|is)\s+"
        r"(?:hereby\s+)?(?:authorized|authorised|approved|allowed|permitted)\b",
        r"\b(?:are|is)\s+(?:hereby\s+)?(?:authorized|authorised|approved|allowed|permitted)\s+"
        r"by default\b",
        r"\b(?:are|is)\s+pre[- ]?approved\b",
        r"\bdefault\s+(?:is\s+)?yes\b",
        r"\bpermission\s+(?:is\s+)?granted\b",
        r"\bpermission\b[^.\n]{0,80}\bhas\s+(?:already\s+)?been\s+granted\b",
        r"\b(?:you|the agent)\s+(?:now\s+)?(?:have|has)\s+(?:the\s+)?"
        r"(?:permission|authority)\b",
        r"\b(?:merge|push|edit|delete|publish|proceed)\b[^.\n]{0,50}\bmay\s+"
        r"proceed\s+without\s+(?:additional|further)\s+approval\b",
        r"\b(?:merge|destructive actions?|registry actions?|actions?|operations?)\b"
        r"[^.\n]{0,50}\b(?:is|are)\s+(?:already\s+|always\s+)?"
        r"(?:authorized|authorised|approved|allowed|permitted)\b",
        r"\b(?:these|all|any|merge|destructive actions?|actions?|operations?)\b"
        r"[^.\n]{0,50}\brequires?\s+no\s+(?:additional\s+|further\s+)?approval\b",
        r"\b(?:operator|user|requester|maintainer|owner|you)\s+(?:hereby\s+)?"
        r"authori[sz]es?\b",
        r"\bno\s+(?:additional\s+|further\s+)?approval\s+is\s+required\b",
    )
    standing_grant = False
    for pattern in standing_grant_patterns:
        for match in re.finditer(pattern, authorization, re.IGNORECASE):
            clause_start = max(
                authorization.rfind(separator, 0, match.start())
                for separator in ("\n", ".", ";")
            )
            subject = authorization[clause_start + 1 : match.start()]
            if re.search(
                r"\b(?:no|none|nothing|never)\b(?:\s+[a-z0-9-]+){0,3}\s*$",
                subject,
                re.IGNORECASE,
            ):
                continue
            if re.search(
                r"\b(?:if|when)\b[^.;\n]{0,80}$",
                subject,
                re.IGNORECASE,
            ):
                continue
            suffix = authorization[match.end() : match.end() + 40]
            if re.match(
                r"\s+(?:only\s+)?(?:after|if|when)\b",
                suffix,
                re.IGNORECASE,
            ):
                continue
            standing_grant = True
            break
        if standing_grant:
            break
    if standing_grant:
        findings.append(
            finding(
                root,
                path,
                "Authorization contains a standing positive grant outside scoped placeholders",
            )
        )

    normalized_auth = normalize_prose(authorization)
    has_delivery_prerequisites = (
        "commit" in normalized_auth
        and "push" in normalized_auth
        and ("prerequisite" in normalized_auth or "requires" in normalized_auth)
        and ("pull request" in normalized_auth or "deliverable" in normalized_auth)
    )
    if not has_delivery_prerequisites:
        findings.append(
            finding(root, path, "Authorization must state the commit-and-push prerequisites for a PR deliverable")
        )
    has_filter_effect_contract = all(
        concept in normalized_auth
        for concept in ("branch", "filter", "push", "workflow", "authoriz")
    ) and any(
        concept in normalized_auth
        for concept in ("inevitable", "automatic", "trigger", "publication", "registry", "artifact")
    )
    if not has_filter_effect_contract:
        findings.append(
            finding(
                root,
                path,
                "Authorization must require branch/path-filter review and authorization of push-triggered effects",
            )
        )

    acceptance = normalize_prose(sections["Acceptance criteria"])
    durable_guidance = (
        "durable" in acceptance
        and "guidance" in acceptance
        and ("document" in acceptance or "manual" in acceptance)
        and ("update" in acceptance or "document" in acceptance)
        and ("not applicable" in acceptance or "non applicability" in acceptance)
    )
    if not durable_guidance:
        findings.append(
            finding(
                root,
                path,
                "Acceptance criteria must require durable documentation/guidance or explicit non-applicability",
            )
        )


def prompt_index_targets(root: Path, text: str) -> list[str]:
    prompt_index = section(text, "Prompt index")
    if prompt_index is None:
        return []
    targets: list[str] = []
    for match in MARKDOWN_LINK.finditer(mask_fenced_code(prompt_index)):
        raw = match.group("target").strip("<>")
        split = urlsplit(raw)
        if split.scheme or split.netloc or not split.path.endswith(".md"):
            continue
        target = (root / "prompts" / unquote(split.path)).resolve(strict=False)
        if target.parent == (root / "prompts").resolve() and target.name != "README.md":
            targets.append(target.name)
    return targets


def validate_prompts(
    root: Path, prompts: list[Path], skills: dict[str, Skill], findings: list[Finding]
) -> None:
    for prompt in prompts:
        validate_prompt(root, prompt, set(skills), findings)

    index_path = root / "prompts/README.md"
    index_text = read_text(root, index_path, findings)
    if index_text is not None:
        indexed = prompt_index_targets(root, index_text)
        counts = Counter(indexed)
        canonical = {path.name for path in prompts}
        for name in sorted(canonical - set(counts)):
            findings.append(finding(root, index_path, f"canonical prompt is missing from index: {name}"))
        for name in sorted(set(counts) - canonical):
            findings.append(finding(root, index_path, f"prompt index references unknown prompt: {name}"))
        for name, count in sorted(counts.items()):
            if count > 1:
                findings.append(finding(root, index_path, f"prompt index contains {name!r} {count} times"))

    template_path = root / "prompts/task-template.md"
    template = read_text(root, template_path, findings)
    if template is not None:
        manuals = section(template, "Manuals") or ""
        template_skills = [token for token in CODE_SPAN.findall(manuals) if token in skills]
        counts = Counter(template_skills)
        for name in sorted(set(skills) - set(counts)):
            findings.append(finding(root, template_path, f"generic task template omits skill: {name}"))
        for name, count in sorted(counts.items()):
            if count > 1:
                findings.append(finding(root, template_path, f"generic task template lists {name!r} {count} times"))


def validate_repository(root: Path = REPO_ROOT) -> list[Finding]:
    root = root.resolve()
    findings: list[Finding] = []

    agents_path = root / "AGENTS.md"
    try:
        agents_size = len(agents_path.read_bytes())
    except OSError as error:
        findings.append(finding(root, agents_path, f"cannot read root guide: {error}"))
    else:
        if agents_size > 32_768:
            findings.append(
                finding(
                    root,
                    agents_path,
                    f"root guide is {agents_size} bytes; Codex compatibility requires at most 32768",
                )
            )

    skills_root = root / "skills"
    skill_paths = sorted(skills_root.glob("*/SKILL.md")) if skills_root.exists() else []
    if not skill_paths:
        findings.append(finding(root, skills_root, "no canonical skills were found"))
    for nested in sorted(skills_root.rglob("SKILL.md")) if skills_root.exists() else []:
        if nested not in skill_paths:
            findings.append(
                finding(root, nested, "skills must use the one-level skills/<name>/SKILL.md layout")
            )
    if skills_root.exists():
        for child in sorted(skills_root.iterdir()):
            if child.is_dir() and not child.name.startswith(".") and not (child / "SKILL.md").is_file():
                findings.append(finding(root, child, "skill package directory is missing SKILL.md"))

    parsed_skills = [parse_skill(root, path, findings) for path in skill_paths]
    skill_list = [skill for skill in parsed_skills if skill is not None]
    names = Counter(skill.name for skill in skill_list)
    descriptions = Counter(re.sub(r"\s+", " ", skill.description).casefold() for skill in skill_list)
    for name, count in sorted(names.items()):
        if count > 1:
            findings.append(finding(root, skills_root, f"duplicate canonical skill name {name!r}"))
    for description, count in descriptions.items():
        if count > 1:
            findings.append(finding(root, skills_root, f"duplicate canonical skill description: {description}"))
    skills = {skill.name: skill for skill in skill_list}

    prompts_root = root / "prompts"
    prompts = (
        sorted(path for path in prompts_root.glob("*.md") if path.name != "README.md")
        if prompts_root.exists()
        else []
    )
    if not prompts:
        findings.append(finding(root, prompts_root, "no canonical prompts were found"))
    if prompts_root.exists():
        for nested in sorted(prompts_root.rglob("*.md")):
            if nested.parent != prompts_root:
                findings.append(finding(root, nested, "prompts must be direct prompts/<name>.md files"))

    validate_adapters(root, findings)
    validate_routing(root, skills, findings)
    validate_prompts(root, prompts, skills, findings)
    validate_links(root, guidance_files(root, skill_list, prompts), findings)

    return sorted(findings, key=lambda item: (item.path, item.line, item.message))


def escape_annotation(value: str, *, property_value: bool = False) -> str:
    escaped = (
        value.encode("utf-8", "backslashreplace")
        .decode("utf-8")
        .replace("%", "%25")
        .replace("\r", "%0D")
        .replace("\n", "%0A")
    )
    if property_value:
        escaped = escaped.replace(":", "%3A").replace(",", "%2C")
    return escaped


def main() -> int:
    findings = validate_repository()
    for item in findings:
        path = escape_annotation(item.path, property_value=True)
        message = escape_annotation(item.message)
        print(
            f"::error file={path},line={item.line},title=Agent guidance validation::{message}"
        )
    if findings:
        print(f"Agent guidance validation found {len(findings)} error(s).", file=sys.stderr)
        return 1

    skill_count = len(list((REPO_ROOT / "skills").glob("*/SKILL.md")))
    prompt_count = len(
        [path for path in (REPO_ROOT / "prompts").glob("*.md") if path.name != "README.md"]
    )
    print(f"Validated agent guidance: {skill_count} skills and {prompt_count} prompts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
