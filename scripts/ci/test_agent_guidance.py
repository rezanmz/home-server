#!/usr/bin/env python3
"""Focused tests for repository-local agent guidance validation."""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType


def load_validator() -> ModuleType:
    path = Path(__file__).with_name("validate-agent-guidance.py")
    spec = importlib.util.spec_from_file_location("agent_guidance_validator", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


validator = load_validator()


AUTHORIZATION = """## Authorization

- Repository edits: [yes/no; scope]
- Create commits: [yes/no; scope]
- Push a branch: [yes/no; remote/branch]
- Open or update a pull request: [yes/no; target]
- Merge: [yes/no; pull request]
- Remote workflow dispatch or rerun: [yes/no; workflow/ref]
- Registry or artifact publication: [yes/no; registry/repository/tag]
- Read-only cluster/host access: [yes/no; scope]
- Live cluster/host mutation: [yes/no; scope]
- Application-state mutation: [yes/no; scope]
- External/provider mutation: [yes/no; scope]
- Credential or secret-material mutation: [yes/no; exact identity]
- Destructive actions: [yes/no; scope]

A pull-request deliverable requires its prerequisite commit and push permissions.
Before a push or merge, inspect current branch/path filters and authorize every
push-triggered workflow, registry, or artifact effect. Stop if an inevitable
effect is denied.
"""


ACCEPTANCE = """## Acceptance criteria

- [ ] The requested outcome and evidence contract are satisfied.
- [ ] Durable behavior and affected agent guidance are documented, or
      non-applicability is justified.
"""


def skill_text(name: str, description: str, body: str = "") -> str:
    return (
        f"---\nname: {name}\ndescription: {description}\n---\n\n"
        f"# {name}\n\n{body or 'Follow the authoritative manual.'}\n"
    )


def prompt_text(skills: list[str]) -> str:
    skill_list = "\n".join(f"- `{name}`" for name in skills)
    return f"""# Task brief: fixture

Perform a bounded fixture task.

## Required inputs

- Exact target: [value]

{AUTHORIZATION}

## Manuals and skills

Load these skills:

{skill_list}

Read [the procedure](../docs/manual.md#procedure).

## Workflow

1. Inspect.
2. Validate.

## Hard stops

Stop when authority or evidence is absent.

## Rollback and recovery

Restore the prior guidance set as one coherent change.

## Evidence contract

Report every workflow, registry, and artifact action plus the validation result.

{ACCEPTANCE}
"""


class GuidanceFixture:
    def __init__(self, root: Path) -> None:
        self.root = root

    def write(self, relative: str, content: str) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def build(self) -> None:
        self.write(
            "AGENTS.md",
            """# Fixture guide

## Task routing

| Task | Load this skill | Start here |
| --- | --- | --- |
| Orient safely | `home-server-safety` | `docs/manual.md` |
| Validate work | `validation` | `docs/manual.md` |
""",
        )
        self.write(
            "README.md",
            "# Fixture\n\nRead [the guide](AGENTS.md) and [procedure](docs/manual.md#procedure).\n",
        )
        self.write("docs/manual.md", "# Manual\n\n## Procedure\n\nFollow it.\n")
        self.write(
            "skills/home-server-safety/SKILL.md",
            skill_text(
                "home-server-safety",
                "Safely establish repository scope and authority. Use before changing this fixture.",
                "Read [the manual](../../docs/manual.md#procedure).",
            ),
        )
        self.write(
            "skills/validation/SKILL.md",
            skill_text(
                "validation",
                "Validate fixture guidance and references. Use when checking repository changes.",
            ),
        )
        self.write(
            "skills/README.md",
            "# Skills\n\nStart with [AGENTS.md](../AGENTS.md).\n",
        )
        self.write(
            "prompts/task-template.md",
            prompt_text(["home-server-safety", "validation"]),
        )
        self.write(
            "prompts/check-fixture.md",
            prompt_text(["home-server-safety", "validation"]),
        )
        self.write(
            "prompts/README.md",
            """# Prompts

## Prompt index

| Prompt | Use |
| --- | --- |
| [task-template.md](task-template.md) | Template |
| [check-fixture.md](check-fixture.md) | Check fixture |
""",
        )
        self.write("CLAUDE.md", "@AGENTS.md\n")
        self.write(".github/copilot-instructions.md", validator.COPILOT_INSTRUCTIONS)
        self.write(".cursor/rules/home-server.mdc", validator.CURSOR_RULE)
        self.write(".omp/AGENTS.md", "@../AGENTS.md\n")
        self.write(".omp/RULES.md", validator.OMP_RULES)
        self.write(
            ".omp/config.yml",
            "skills:\n"
            "  enableAgentsProject: false\n"
            "  customDirectories:\n"
            "    - skills\n",
        )
        agents_dir = self.root / ".agents"
        agents_dir.mkdir(parents=True, exist_ok=True)
        os.symlink("../skills", agents_dir / "skills")


class AgentGuidanceValidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.fixture = GuidanceFixture(self.root)
        self.fixture.build()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def messages(self) -> list[str]:
        return [item.message for item in validator.validate_repository(self.root)]

    def assertHasMessage(self, fragment: str) -> None:  # noqa: N802 - unittest style
        messages = self.messages()
        self.assertTrue(
            any(fragment in message for message in messages),
            f"missing {fragment!r} in findings: {messages}",
        )

    def test_valid_fixture_passes(self) -> None:
        self.assertEqual(validator.validate_repository(self.root), [])

    def test_frontmatter_rejects_unsafe_yaml_and_name_mismatch(self) -> None:
        path = self.root / "skills/validation/SKILL.md"
        path.write_text(
            skill_text(
                "wrong-name",
                "Validate a system: this colon is unsafe. Use when checking changes.",
            ),
            encoding="utf-8",
        )
        self.assertHasMessage("unsafe YAML plain scalar")
        self.assertHasMessage("does not match directory")

    def test_frontmatter_plain_scalars_must_resolve_to_strings(self) -> None:
        for value in ("true", "42", "2026-08-25"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "non-string YAML type"):
                    validator.parse_scalar(value)
        self.assertEqual(validator.parse_scalar('"true"'), "true")

    def test_frontmatter_single_quoted_scalars_require_yaml_escaping(self) -> None:
        with self.assertRaisesRegex(ValueError, "must be doubled"):
            validator.parse_scalar("'Don't skip safety.'")
        self.assertEqual(validator.parse_scalar("'Don''t skip safety.'"), "Don't skip safety.")

    def test_frontmatter_rejects_duplicate_descriptions_and_nested_skills(self) -> None:
        duplicate = (
            "Safely establish repository scope and authority. Use before changing this fixture."
        )
        self.fixture.write(
            "skills/validation/SKILL.md", skill_text("validation", duplicate)
        )
        self.fixture.write(
            "skills/group/nested/SKILL.md",
            skill_text(
                "nested",
                "Perform a nested fixture operation. Use when testing invalid layouts.",
            ),
        )
        self.assertHasMessage("duplicate canonical skill description")
        self.assertHasMessage("one-level skills/<name>/SKILL.md layout")

    def test_prompt_rejects_unknown_skill_and_missing_remote_plane(self) -> None:
        path = self.root / "prompts/check-fixture.md"
        text = path.read_text(encoding="utf-8")
        text = text.replace("- `validation`", "- `missing-skill`")
        text = text.replace(
            "- Remote workflow dispatch or rerun: [yes/no; workflow/ref]\n",
            "",
        )
        text = text.replace(
            "- Registry or artifact publication: [yes/no; registry/repository/tag]\n",
            "",
        )
        text = text.replace(
            "- Credential or secret-material mutation: [yes/no; exact identity]\n", ""
        )
        path.write_text(text, encoding="utf-8")
        self.assertHasMessage("references unknown skill: missing-skill")
        self.assertHasMessage("separate fields for remote workflow dispatch/rerun")
        self.assertHasMessage("credential/secret-material permission")

    def test_prompt_rejects_combined_remote_effect_field(self) -> None:
        path = self.root / "prompts/check-fixture.md"
        text = path.read_text(encoding="utf-8")
        text = text.replace(
            "- Remote workflow dispatch or rerun: [yes/no; workflow/ref]\n"
            "- Registry or artifact publication: [yes/no; registry/repository/tag]\n",
            "- Remote workflow dispatch/rerun or artifact publication: "
            "[yes/no; workflow/ref/artifact]\n",
        )
        path.write_text(text, encoding="utf-8")
        self.assertHasMessage("separate fields for remote workflow dispatch/rerun")

    def test_prompt_rejects_filled_standing_authority(self) -> None:
        path = self.root / "prompts/check-fixture.md"
        text = path.read_text(encoding="utf-8").replace(
            "- Merge: [yes/no; pull request]\n",
            "- Merge: yes [yes/no; pull request]\n",
        ).replace(
            "- Destructive actions: [yes/no; scope]\n",
            "- Destructive actions: [yes/no; default yes]\n",
        )
        path.write_text(text, encoding="utf-8")
        self.assertHasMessage("must remain an unfilled [yes/no; exact scope] placeholder")
        self.assertHasMessage("must not contain a standing yes/default grant")

    def test_prompt_rejects_missing_core_permission_fields(self) -> None:
        path = self.root / "prompts/check-fixture.md"
        text = path.read_text(encoding="utf-8")
        for line in (
            "- Repository edits: [yes/no; scope]\n",
            "- Create commits: [yes/no; scope]\n",
            "- Push a branch: [yes/no; remote/branch]\n",
            "- Open or update a pull request: [yes/no; target]\n",
            "- Merge: [yes/no; pull request]\n",
            "- Read-only cluster/host access: [yes/no; scope]\n",
            "- Live cluster/host mutation: [yes/no; scope]\n",
            "- Application-state mutation: [yes/no; scope]\n",
            "- External/provider mutation: [yes/no; scope]\n",
            "- Destructive actions: [yes/no; scope]\n",
        ):
            text = text.replace(line, "")
        path.write_text(text, encoding="utf-8")
        self.assertHasMessage("Authorization is missing core permission field(s)")

    def test_prompt_core_fields_use_words_not_substrings(self) -> None:
        path = self.root / "prompts/check-fixture.md"
        text = path.read_text(encoding="utf-8")
        text = text.replace(
            "- Live cluster/host mutation: [yes/no; scope]\n",
            "",
        ).replace(
            "- Registry or artifact publication: [yes/no; registry/repository/tag]\n",
            "- Deliverable publication: [yes/no; registry/repository/tag]\n",
        )
        path.write_text(text, encoding="utf-8")
        self.assertHasMessage("live cluster/host mutation")

    def test_prompt_core_fields_require_permission_label_shapes(self) -> None:
        path = self.root / "prompts/check-fixture.md"
        replacements = {
            "Repository edits": "Repository edit history review",
            "Create commits": "Commit history review",
            "Push a branch": "Push notification review",
            "Open or update a pull request": "Pull request template review",
            "Merge": "Merge conflict review",
            "Read-only cluster/host access": "Read-only documentation pass",
            "Live cluster/host mutation": "Live documentation review",
            "Application-state mutation": "Application-state observation",
            "External/provider mutation": "External/provider status report",
            "Destructive actions": "Destructive-risk assessment",
        }
        text = path.read_text(encoding="utf-8")
        for original, replacement in replacements.items():
            text = text.replace(f"- {original}:", f"- {replacement}:")
        path.write_text(text, encoding="utf-8")
        self.assertHasMessage("Authorization is missing core permission field(s)")

    def test_prompt_live_mutation_label_rejects_non_permission_suffixes(self) -> None:
        path = self.root / "prompts/check-fixture.md"
        text = path.read_text(encoding="utf-8").replace(
            "- Live cluster/host mutation: [yes/no; scope]\n",
            "- Live cluster/host mutation documentation review: [yes/no; scope]\n",
        )
        path.write_text(text, encoding="utf-8")
        self.assertHasMessage("live cluster/host mutation")

    def test_prompt_core_permission_planes_cannot_share_a_field(self) -> None:
        path = self.root / "prompts/check-fixture.md"
        text = path.read_text(encoding="utf-8").replace(
            "- Repository edits: [yes/no; scope]\n"
            "- Create commits: [yes/no; scope]\n",
            "- Repository edits and create commits: [yes/no; scope]\n",
        )
        path.write_text(text, encoding="utf-8")
        self.assertHasMessage("repository edits, commit creation")

    def test_prompt_permission_planes_must_have_exactly_one_field(self) -> None:
        path = self.root / "prompts/check-fixture.md"
        text = path.read_text(encoding="utf-8").replace(
            "- Merge: [yes/no; pull request]\n",
            "- Merge: [yes/no; pull request]\n"
            "- Merge to protected main: [yes/no; pull request]\n",
        ).replace(
            "- Remote workflow dispatch or rerun: [yes/no; workflow/ref]\n",
            "- Remote workflow dispatch or rerun: [yes/no; workflow/ref]\n"
            "- Remote workflow dispatch or rerun: [yes/no; second workflow/ref]\n",
        ).replace(
            "- Credential or secret-material mutation: [yes/no; exact identity]\n",
            "- Credential or secret-material mutation: [yes/no; exact identity]\n"
            "- Credential or secret-material action: [yes/no; second identity]\n",
        )
        path.write_text(text, encoding="utf-8")
        self.assertHasMessage("exactly one field for each core permission plane")
        self.assertHasMessage("separate fields for remote workflow dispatch/rerun")
        self.assertHasMessage("exactly one explicit credential/secret-material permission")

    def test_prompt_rejects_shadow_authorization_and_unparsed_bullets(self) -> None:
        path = self.root / "prompts/check-fixture.md"
        text = path.read_text(encoding="utf-8").replace(
            "A pull-request deliverable requires its prerequisite commit and push permissions.\n",
            "All operations above, including merge and destructive actions, are authorized "
            "by default.\n"
            "- Merge and destructive actions are authorized by default\n"
            "  - Merge: yes\n\n"
            "A pull-request deliverable requires its prerequisite commit and push permissions.\n",
        )
        text += "\n## Authorization override\n\n- Merge: yes\n"
        path.write_text(text, encoding="utf-8")
        self.assertHasMessage("exactly one H2 named 'Authorization'")
        self.assertHasMessage("Authorization bullets must be top-level")
        self.assertHasMessage("standing positive grant")

    def test_prompt_allows_explicit_denial_prose(self) -> None:
        path = self.root / "prompts/check-fixture.md"
        text = path.read_text(encoding="utf-8").replace(
            "A pull-request deliverable requires its prerequisite commit and push permissions.\n",
            "No actions are authorized by default. Nothing is allowed by default.\n\n"
            "A pull-request deliverable requires its prerequisite commit and push permissions.\n",
        )
        path.write_text(text, encoding="utf-8")
        self.assertEqual(validator.validate_repository(self.root), [])

    def test_prompt_allows_restrictive_conditional_prose(self) -> None:
        path = self.root / "prompts/check-fixture.md"
        text = path.read_text(encoding="utf-8").replace(
            "A pull-request deliverable requires its prerequisite commit and push permissions.\n",
            "Merge is allowed only after the matching field is filled and checks pass.\n"
            "If explicitly authorized, merge is approved.\n\n"
            "A pull-request deliverable requires its prerequisite commit and push permissions.\n",
        )
        path.write_text(text, encoding="utf-8")
        self.assertEqual(validator.validate_repository(self.root), [])

    def test_prompt_rejects_additional_positive_grant_phrases(self) -> None:
        path = self.root / "prompts/check-fixture.md"
        text = path.read_text(encoding="utf-8").replace(
            "A pull-request deliverable requires its prerequisite commit and push permissions.\n",
            "No further approval is required because all actions are permitted by default.\n"
            "Merge and destructive actions may proceed without additional approval.\n"
            "Registry actions are pre-approved. Permission to publish has already been granted.\n"
            "You have permission to merge.\n\n"
            "A pull-request deliverable requires its prerequisite commit and push permissions.\n",
        )
        path.write_text(text, encoding="utf-8")
        self.assertHasMessage("standing positive grant")

    def test_prompt_rejects_each_common_positive_grant_form(self) -> None:
        path = self.root / "prompts/check-fixture.md"
        original = path.read_text(encoding="utf-8")
        grants = (
            "Merge is approved.",
            "Merge and destructive actions are always allowed.",
            "These actions require no further approval.",
            "The operator authorizes merge and publication.",
            "No further approval is required.",
        )
        marker = "A pull-request deliverable requires its prerequisite commit and push permissions.\n"
        for grant in grants:
            with self.subTest(grant=grant):
                path.write_text(original.replace(marker, f"{grant}\n{marker}"), encoding="utf-8")
                messages = self.messages()
                self.assertTrue(
                    any("standing positive grant" in item for item in messages),
                    messages,
                )
        path.write_text(original, encoding="utf-8")

    def test_prompt_rejects_delivery_and_documentation_contract_drift(self) -> None:
        path = self.root / "prompts/check-fixture.md"
        text = path.read_text(encoding="utf-8")
        text = text.replace(
            "A pull-request deliverable requires its prerequisite commit and push permissions.\n",
            "",
        )
        text = text.replace(
            "Before a push or merge, inspect current branch/path filters and authorize every\n"
            "push-triggered workflow, registry, or artifact effect. Stop if an inevitable\n"
            "effect is denied.\n",
            "",
        )
        text = text.replace(
            "- [ ] Durable behavior and affected agent guidance are documented, or\n"
            "      non-applicability is justified.\n",
            "",
        )
        path.write_text(text, encoding="utf-8")
        self.assertHasMessage("commit-and-push prerequisites")
        self.assertHasMessage("branch/path-filter review")
        self.assertHasMessage("durable documentation/guidance")

    def test_prompt_requires_lifecycle_sections_and_remote_action_evidence(self) -> None:
        path = self.root / "prompts/check-fixture.md"
        text = path.read_text(encoding="utf-8")
        text = text.replace("## Workflow\n", "## Procedure\n")
        text = text.replace(
            "## Hard stops\n\nStop when authority or evidence is absent.\n\n", ""
        )
        text = text.replace("## Rollback and recovery", "## Reversal")
        text = text.replace(
            "Report every workflow, registry, and artifact action plus the validation result.",
            "Report the validation result.",
        )
        path.write_text(text, encoding="utf-8")
        self.assertHasMessage("missing a workflow contract")
        self.assertHasMessage("missing a hard-stop contract")
        self.assertHasMessage("missing a rollback/recovery contract")
        self.assertHasMessage("Evidence contract must record workflow, registry, and artifact actions")

    def test_routing_and_prompt_indexes_are_complete_and_unique(self) -> None:
        agents = self.root / "AGENTS.md"
        agents.write_text(
            agents.read_text(encoding="utf-8").replace(
                "| Validate work | `validation` | `docs/manual.md` |\n", ""
            ),
            encoding="utf-8",
        )
        prompt_index = self.root / "prompts/README.md"
        prompt_index.write_text(
            prompt_index.read_text(encoding="utf-8").replace(
                "| [check-fixture.md](check-fixture.md) | Check fixture |\n", ""
            ),
            encoding="utf-8",
        )
        self.assertHasMessage("canonical skill is missing from Task routing: validation")
        self.assertHasMessage("canonical prompt is missing from index: check-fixture.md")

    def test_generic_template_must_inventory_every_skill(self) -> None:
        path = self.root / "prompts/task-template.md"
        path.write_text(
            path.read_text(encoding="utf-8").replace("- `validation`\n", ""),
            encoding="utf-8",
        )
        self.assertHasMessage("generic task template omits skill: validation")

    def test_local_links_and_fragments_must_resolve(self) -> None:
        readme = self.root / "README.md"
        readme.write_text(
            "# Fixture\n\n[missing](docs/nope.md) [bad heading](docs/manual.md#absent)\n",
            encoding="utf-8",
        )
        self.assertHasMessage("local link target does not exist: docs/nope.md")
        self.assertHasMessage("Markdown fragment does not exist: docs/manual.md#absent")

    def test_links_ignore_inline_code_and_reject_reference_style(self) -> None:
        readme = self.root / "README.md"
        readme.write_text(
            "# Fixture\n\n`[example](docs/nope.md)` and [uncheckable][manual].\n\n"
            "[manual]: docs/manual.md#procedure\n",
            encoding="utf-8",
        )
        messages = self.messages()
        self.assertTrue(any("reference-style Markdown links are forbidden" in item for item in messages))
        self.assertFalse(any("docs/nope.md" in item for item in messages))

    def test_omp_adapters_are_exact_and_bridges_are_forbidden(self) -> None:
        self.fixture.write("CLAUDE.md", "Read AGENTS.md\n")
        self.fixture.write(".omp/AGENTS.md", "Read ../AGENTS.md\n")
        self.fixture.write(
            ".omp/config.yml",
            "skills:\n"
            "  enableAgentsProject: true\n"
            "  customDirectories:\n"
            "    - skills\n",
        )
        bridge = self.root / ".claude/skills"
        bridge.parent.mkdir(parents=True)
        os.symlink(self.root / "skills", bridge)
        self.assertHasMessage("Claude adapter must be exactly")
        self.assertHasMessage("OMP AGENTS adapter must be exactly")
        self.assertHasMessage("OMP config must disable skills.enableAgentsProject")
        self.assertHasMessage("skill or prompt bridge is forbidden")

    def test_agents_skill_bridge_must_use_exact_canonical_symlink(self) -> None:
        bridge = self.root / ".agents/skills"
        bridge.unlink()
        os.symlink("../prompts", bridge)
        self.assertHasMessage("symlink target must be exactly ../skills")

    def test_agents_adapter_rejects_rogue_skill_copy(self) -> None:
        self.fixture.write(
            ".agents/rogue/SKILL.md",
            skill_text(
                "rogue",
                "Duplicate runtime-specific guidance. Use when testing invalid copies.",
            ),
        )
        self.assertHasMessage("unexpected adapter entry")

    def test_exact_omp_and_agents_adapters_reject_extra_capabilities(self) -> None:
        self.fixture.write(".omp/commands/rogue.md", "# Command\n")
        self.fixture.write(".omp/tools/rogue.md", "# Tool\n")
        self.fixture.write(".omp/settings.json", "{}\n")
        self.fixture.write(".agents/settings.json", "{}\n")
        self.fixture.write("apps/example/.omp/config.yml", "skills: {}\n")
        self.assertHasMessage("unexpected adapter entry")
        self.assertHasMessage("runtime context directory is not a canonical adapter")

    def test_runtime_adapters_reject_shadow_context_files(self) -> None:
        self.fixture.write(".omp/rules/rogue.md", "# Copied policy\n")
        self.fixture.write(".omp/instructions/rogue.md", "# Copied policy\n")
        self.fixture.write("apps/example/AGENTS.md", "# Shadow policy\n")
        self.fixture.write("apps/lowercase/agents.md", "# Lowercase shadow policy\n")
        self.fixture.write("apps/example/.cursor/rules/nested/rogue.mdc", "# Policy\n")
        self.fixture.write("apps/example/.windsurf/rules/rogue.md", "# Policy\n")
        self.fixture.write(
            ".github/instructions/rogue.instructions.md", "# Copied policy\n"
        )
        self.assertHasMessage("unexpected auto-loaded context file")

    def test_direct_recursive_rule_patterns_each_reject_shadow_context(self) -> None:
        for relative in (
            ".claude/rules/rogue.md",
            ".cursor/rules/rogue.mdc",
            ".github/instructions/rogue.instructions.md",
        ):
            with self.subTest(relative=relative):
                path = self.root / relative
                self.fixture.write(relative, "# Shadow policy\n")
                messages = self.messages()
                self.assertTrue(
                    any("unexpected auto-loaded context file" in item for item in messages),
                    messages,
                )
                path.unlink()

    def test_deep_recursive_rule_patterns_each_reject_shadow_context(self) -> None:
        for relative in (
            ".claude/rules/a/b/rogue.md",
            ".cursor/rules/a/b/rogue.mdc",
            ".github/instructions/a/b/rogue.instructions.md",
            ".windsurf/rules/a/b/rogue.md",
            ".clinerules/a/b/rogue.md",
        ):
            with self.subTest(relative=relative):
                path = self.root / relative
                self.fixture.write(relative, "# Shadow policy\n")
                messages = self.messages()
                self.assertTrue(
                    any("unexpected auto-loaded context file" in item for item in messages),
                    messages,
                )
                path.unlink()

    def test_runtime_adapters_reject_nested_skill_trees(self) -> None:
        self.fixture.write(
            "apps/example/.opencode/skills/rogue/SKILL.md",
            skill_text(
                "rogue",
                "Duplicate nested runtime guidance. Use when testing shadow skill trees.",
            ),
        )
        self.assertHasMessage("runtime-specific skill tree is forbidden")

    def test_runtime_adapters_reject_symlinked_context_trees(self) -> None:
        self.fixture.write("rogue-rules/policy.md", "# Shadow policy\n")
        rules = self.root / ".claude/rules"
        rules.parent.mkdir(parents=True, exist_ok=True)
        os.symlink("../rogue-rules", rules)
        self.assertHasMessage("symlinked runtime context tree is forbidden")

    def test_runtime_adapters_reject_system_prompt_surfaces(self) -> None:
        for relative in (
            ".agent/SYSTEM.md",
            ".claude/APPEND_SYSTEM.md",
            ".codex/SYSTEM.md",
            ".gemini/APPEND_SYSTEM.md",
            "apps/example/.gemini/system.md",
            ".opencode/commands/rogue.md",
            ".windsurf/rules/rogue.md",
        ):
            self.fixture.write(relative, "# Shadow policy\n")
        self.assertHasMessage("unexpected auto-loaded context file")

    def test_runtime_adapters_reject_local_review_and_watchdog_overrides(self) -> None:
        for relative in (
            "CLAUDE.local.md",
            "REVIEW.md",
            "WATCHDOG.yaml",
        ):
            self.fixture.write(relative, "# Shadow policy\n")
        self.assertHasMessage("unexpected auto-loaded context file")

    def test_runtime_configuration_directories_are_not_allowed_to_bypass_guidance(self) -> None:
        for relative in (
            ".claude/settings.json",
            ".cursor/mcp.json",
            ".gemini/settings.json",
            ".opencode/opencode.json",
        ):
            self.fixture.write(relative, "{}\n")
        self.assertHasMessage("runtime context directory is not a canonical adapter")
        self.assertHasMessage("unexpected adapter entry")

    def test_runtime_side_effect_configuration_is_rejected(self) -> None:
        self.fixture.write(
            ".claude/settings.json",
            '{"hooks":{"SessionStart":[{"hooks":[{"type":"command","command":"id"}]}]}}\n',
        )
        self.fixture.write(
            ".opencode/opencode.json",
            '{"instructions":["shadow.md"],"plugin":["example-plugin"]}\n',
        )
        self.fixture.write(".github/hooks/hooks.json", "{}\n")
        self.assertHasMessage("runtime context directory is not a canonical adapter")
        self.assertHasMessage("GitHub agent overlay directory is forbidden")

    def test_opencode_ancestor_configuration_is_rejected(self) -> None:
        for relative in (
            "opencode.json",
            "apps/example/opencode.jsonc",
        ):
            with self.subTest(relative=relative):
                path = self.root / relative
                self.fixture.write(
                    relative,
                    '{"instructions":["https://example.invalid/policy.md"],'
                    '"plugin":["example-plugin"]}\n',
                )
                messages = self.messages()
                self.assertTrue(
                    any("unexpected auto-loaded context file" in item for item in messages),
                    messages,
                )
                path.unlink()

    def test_mcp_capability_configuration_is_rejected(self) -> None:
        for relative in (
            "mcp.json",
            "apps/example/.mcp.json",
            "apps/example/.vscode/mcp.json",
        ):
            with self.subTest(relative=relative):
                path = self.root / relative
                self.fixture.write(
                    relative,
                    '{"servers":{"external":{"command":"example-server"}}}\n',
                )
                messages = self.messages()
                self.assertTrue(
                    any("unexpected auto-loaded context file" in item for item in messages),
                    messages,
                )
                path.unlink()

    def test_cursor_adapter_requires_exact_always_apply_pointer(self) -> None:
        self.fixture.write(
            ".cursor/rules/home-server.mdc",
            validator.CURSOR_RULE.replace("alwaysApply: true", "alwaysApply: false"),
        )
        self.assertHasMessage("Cursor adapter must match its canonical thin pointer exactly")

    def test_runtime_shims_cannot_grow_policy_sections(self) -> None:
        path = self.root / ".github/copilot-instructions.md"
        path.write_text(
            path.read_text(encoding="utf-8")
            + "\n## Independent policy\n\n- Apply a copied rule.\n",
            encoding="utf-8",
        )
        self.assertHasMessage("runtime adapter must remain a thin pointer")

    def test_root_agent_guide_has_codex_compatible_size_limit(self) -> None:
        path = self.root / "AGENTS.md"
        path.write_text(path.read_text(encoding="utf-8") + ("x" * 33_000), encoding="utf-8")
        self.assertHasMessage("Codex compatibility requires at most 32768")

    def test_checked_in_repository_passes(self) -> None:
        findings = validator.validate_repository(validator.REPO_ROOT)
        self.assertEqual(findings, [], "\n".join(f"{item.path}: {item.message}" for item in findings))


if __name__ == "__main__":
    unittest.main()
