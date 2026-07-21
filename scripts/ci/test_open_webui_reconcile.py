import importlib.util
import io
import json
import sqlite3
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "apps" / "open-webui" / "config" / "reconcile.py"
SPEC = importlib.util.spec_from_file_location("open_webui_reconcile", MODULE_PATH)
reconcile_module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(reconcile_module)
ORIGINAL_CATALOG_FETCH = reconcile_module._fetch_openrouter_text_catalog


class OpenWebUIReconcileTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(
            "os.environ",
            {"GPT_RESEARCHER_API_TOKEN": "research-token-" + ("x" * 48)},
        )
        self.environment.start()
        self.catalog = [
            {
                "id": f"test-provider/model-{index:02d}",
                "name": f"Test Model {index:02d}",
            }
            for index in range(25)
        ] + [
            {"id": "z-ai/glm-5.1", "name": "GLM 5.1"},
            {
                "id": "anthropic/claude-sonnet-latest",
                "name": "Claude Sonnet Latest",
            },
        ]
        self.catalog_fetch = patch.object(
            reconcile_module,
            "_fetch_openrouter_text_catalog",
            return_value=self.catalog,
        )
        self.catalog_fetch_mock = self.catalog_fetch.start()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)
        self.db_path = self.data_dir / "webui.db"
        conn = sqlite3.connect(self.db_path)
        conn.executescript(
            """
            CREATE TABLE config (
                key TEXT PRIMARY KEY,
                value JSON NOT NULL,
                updated_at INTEGER NOT NULL
            );
            CREATE TABLE config_old (
                id INTEGER PRIMARY KEY,
                data JSON NOT NULL
            );
            CREATE TABLE user (
                id TEXT PRIMARY KEY,
                role TEXT,
                settings JSON,
                created_at INTEGER,
                updated_at INTEGER
            );
            CREATE TABLE function (
                id TEXT PRIMARY KEY,
                name TEXT,
                type TEXT,
                content TEXT,
                meta JSON
            );
            CREATE TABLE model (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                base_model_id TEXT,
                name TEXT,
                params JSON,
                meta JSON,
                is_active BOOLEAN,
                updated_at INTEGER,
                created_at INTEGER
            );
            CREATE TABLE access_grant (
                id TEXT PRIMARY KEY,
                resource_type TEXT,
                resource_id TEXT
            );
            CREATE TABLE automation (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                name TEXT NOT NULL,
                data JSON NOT NULL,
                meta JSON,
                is_active BOOLEAN NOT NULL,
                last_run_at INTEGER,
                next_run_at INTEGER,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            );
            """
        )
        conn.execute(
            "INSERT INTO config VALUES (?, ?, ?)",
            ("ui.enable_community_sharing", "true", 1),
        )
        conn.execute(
            "INSERT INTO config VALUES (?, ?, ?)",
            (
                "tool_server.connections",
                json.dumps(
                    [
                        {
                            "url": "https://mcphub.reza.network/mcp/git-mcp-server",
                            "info": {"id": "0", "name": "git-mcp-server"},
                        },
                        {
                            "url": "https://example.test/mcp",
                            "info": {"id": "keep", "name": "future-server"},
                        },
                    ]
                ),
                1,
            ),
        )
        for key, value in (
            ("openai.api_base_urls", ["https://openrouter.ai/api/v1"]),
            ("openai.api_keys", ["openrouter-test-key"]),
            ("rag.content_extraction_engine", "tika"),
            ("rag.embedding_engine", "openai"),
            ("rag.embedding_model", "text-embedding-3-small"),
            ("image_generation.engine", "gemini"),
            ("images.edit.engine", "gemini"),
            ("web.search.engine", "perplexity"),
            ("web.search.enable", True),
            ("web.search.perplexity_api_key", "retired-perplexity-key"),
            ("web.search.searxng_query_url", ""),
            ("rag.datalab_marker_api_key", "unused"),
            ("image_generation.openai.api_key", "unused"),
            ("images.edit.openai.api_key", "unused"),
            ("web.search.exa_api_key", "unused"),
        ):
            conn.execute(
                "INSERT INTO config VALUES (?, ?, ?)",
                (key, json.dumps(value), 1),
            )
        conn.execute(
            "INSERT INTO config_old VALUES (?, ?)",
            (1, '{"legacy_secret":"remove-me"}'),
        )
        conn.execute(
            "INSERT INTO user VALUES (?, ?, ?, ?, ?)",
            (
                "admin",
                "admin",
                json.dumps(
                    {
                        "ui": {
                            "iframeSandboxAllowSameOrigin": True,
                            "iframeSandboxAllowForms": True,
                            "system": "unsafe prompt",
                        }
                    }
                ),
                1,
                1,
            ),
        )
        conn.execute(
            "INSERT INTO user VALUES (?, ?, ?, ?, ?)",
            ("user", "user", None, 2, 2),
        )
        for function_id in reconcile_module.UNSAFE_FUNCTION_IDS:
            conn.execute(
                "INSERT INTO function VALUES (?, ?, ?, ?, ?)",
                (
                    function_id,
                    function_id,
                    "filter",
                    f"# {function_id}\n",
                    "{}",
                ),
            )
        conn.execute(
            "INSERT INTO function VALUES (?, ?, ?, ?, ?)",
            ("future_safe_function", "Future", "action", "# safe\n", "{}"),
        )
        conn.execute(
            "INSERT INTO model VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "~anthropic/claude-sonnet-latest",
                "admin",
                None,
                "Claude",
                '{"reasoning_effort":"high"}',
                json.dumps(reconcile_module.COMPANION_METADATA),
                1,
                1,
                1,
            ),
        )
        conn.execute(
            "INSERT INTO model VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "z-ai/glm-5.1",
                "admin",
                None,
                "GLM 5.1 Custom",
                '{"temperature":0.4}',
                '{"custom":true}',
                1,
                1,
                1,
            ),
        )
        conn.commit()
        conn.close()

        (self.data_dir / "vocab_embeddings_cache.json").write_text("{}")
        stale_model = (
            self.data_dir
            / "cache"
            / "embedding"
            / "models"
            / "models--sentence-transformers--all-MiniLM-L6-v2"
        )
        stale_model.mkdir(parents=True)
        (stale_model / "weights").write_text("stale")

    def tearDown(self):
        self.temp_dir.cleanup()
        self.catalog_fetch.stop()
        self.environment.stop()

    def test_managed_prompts_do_not_contain_the_users_name(self):
        for prompt in (
            reconcile_module.PERSONAL_COMPANION_PROMPT,
            reconcile_module.RIGOROUS_PROMPT,
            reconcile_module.DEEP_RESEARCH_PROFILE_PROMPT,
            reconcile_module.MODEL_STEWARD_PROMPT,
            reconcile_module.MODEL_STEWARD_AUTOMATION_PROMPT,
        ):
            self.assertNotIn("reza", prompt.lower())

    def test_catalog_fetch_requires_a_plausible_text_model_catalog(self):
        rows = [
            {
                "id": f"provider/model-{index:02d}",
                "name": f"Model {index:02d}",
                "architecture": {"output_modalities": ["text"]},
            }
            for index in range(25)
        ]
        rows.extend(
            [
                {
                    "id": "provider/image-only",
                    "name": "Image only",
                    "architecture": {"output_modalities": ["image"]},
                },
                {
                    "id": "invalid model id",
                    "name": "Invalid",
                    "architecture": {"output_modalities": ["text"]},
                },
            ]
        )
        response = io.BytesIO(json.dumps({"data": rows}).encode())
        with patch.object(
            reconcile_module.urllib.request,
            "urlopen",
            return_value=response,
        ):
            catalog = ORIGINAL_CATALOG_FETCH()

        self.assertEqual(len(catalog), 25)
        self.assertEqual(catalog[0]["id"], "provider/model-00")

        tiny = io.BytesIO(json.dumps({"data": rows[:5]}).encode())
        with patch.object(
            reconcile_module.urllib.request,
            "urlopen",
            return_value=tiny,
        ):
            with self.assertRaisesRegex(RuntimeError, "unexpectedly small"):
                ORIGINAL_CATALOG_FETCH()

    def test_cached_catalog_survives_a_transient_refresh_failure(self):
        first = reconcile_module.reconcile(self.db_path, self.data_dir)
        self.assertEqual(first["catalog_models"], len(self.catalog))
        self.assertIsNone(first["catalog_sync_error"])

        self.catalog_fetch_mock.side_effect = OSError("temporary catalog outage")
        second = reconcile_module.reconcile(self.db_path, self.data_dir)

        self.assertGreaterEqual(second["catalog_models"], 25)
        self.assertIn("temporary catalog outage", second["catalog_sync_error"])
        self.assertEqual(second["database_changes"], 0)

    def test_catalog_failure_without_cache_aborts_closed(self):
        self.catalog_fetch_mock.side_effect = OSError("catalog unavailable")

        with self.assertRaisesRegex(RuntimeError, "without a usable cached catalog"):
            reconcile_module.reconcile(self.db_path, self.data_dir)

    def test_reconcile_retires_unsafe_state_and_preserves_user_data(self):
        first = reconcile_module.reconcile(self.db_path, self.data_dir)

        conn = sqlite3.connect(self.db_path)
        remaining_functions = {
            row[0] for row in conn.execute("SELECT id FROM function")
        }
        self.assertEqual(remaining_functions, {"future_safe_function"})

        sharing = conn.execute(
            "SELECT value FROM config WHERE key = 'ui.enable_community_sharing'"
        ).fetchone()[0]
        self.assertFalse(json.loads(sharing))
        self.assertEqual(
            json.loads(
                conn.execute(
                    "SELECT value FROM config WHERE key = 'auth.jwt_expiry'"
                ).fetchone()[0]
            ),
            "7d",
        )
        self.assertFalse(
            json.loads(
                conn.execute(
                    "SELECT value FROM config "
                    "WHERE key = 'memories.background_review.enable'"
                ).fetchone()[0]
            )
        )

        connections = json.loads(
            conn.execute(
                "SELECT value FROM config WHERE key = 'tool_server.connections'"
            ).fetchone()[0]
        )
        self.assertEqual(
            [item["info"]["id"] for item in connections],
            ["keep", "gpt-researcher"],
        )
        researcher_connection = connections[-1]
        self.assertEqual(researcher_connection["auth_type"], "bearer")
        self.assertTrue(researcher_connection["config"]["enable"])
        self.assertEqual(
            researcher_connection["config"]["function_name_filter_list"],
            "conduct_deep_research",
        )
        for key in (
            "rag.datalab_marker_api_key",
            "image_generation.openai.api_key",
            "images.edit.openai.api_key",
            "web.search.exa_api_key",
            "web.search.perplexity_api_key",
        ):
            self.assertEqual(
                json.loads(
                    conn.execute(
                        "SELECT value FROM config WHERE key = ?", (key,)
                    ).fetchone()[0]
                ),
                "",
            )

        self.assertEqual(
            json.loads(
                conn.execute(
                    "SELECT value FROM config WHERE key = 'web.search.engine'"
                ).fetchone()[0]
            ),
            "searxng",
        )
        self.assertEqual(
            json.loads(
                conn.execute(
                    "SELECT value FROM config "
                    "WHERE key = 'web.search.searxng_query_url'"
                ).fetchone()[0]
            ),
            "http://searxng.apps.svc.cluster.local:8080/search?q=<query>",
        )
        self.assertTrue(
            json.loads(
                conn.execute(
                    "SELECT value FROM config WHERE key = 'web.search.enable'"
                ).fetchone()[0]
            )
        )
        self.assertEqual(
            reconcile_module._decode(
                conn.execute(
                    "SELECT value FROM config "
                    "WHERE key = 'web.search.concurrent_requests'"
                ).fetchone()[0]
            ),
            1,
        )

        default_metadata = json.loads(
            conn.execute(
                "SELECT value FROM config WHERE key = 'models.default_metadata'"
            ).fetchone()[0]
        )
        self.assertEqual(default_metadata, {})

        catalog_override = conn.execute(
            "SELECT user_id, base_model_id, params, meta FROM model "
            "WHERE id = 'test-provider/model-00'"
        ).fetchone()
        self.assertEqual(catalog_override[0], "admin")
        self.assertIsNone(catalog_override[1])
        self.assertEqual(json.loads(catalog_override[2]), {})
        catalog_metadata = json.loads(catalog_override[3])
        self.assertEqual(
            catalog_metadata["defaultFeatureIds"],
            ["web_search"],
        )
        for tool in (
            "time",
            "memory",
            "chats",
            "notes",
            "knowledge",
            "web_search",
            "tasks",
            "calendar",
        ):
            self.assertTrue(catalog_metadata["builtinTools"][tool])
        self.assertFalse(catalog_metadata["builtinTools"]["image_generation"])
        self.assertFalse(catalog_metadata["builtinTools"]["code_interpreter"])
        self.assertFalse(catalog_metadata["builtinTools"]["channels"])
        self.assertFalse(catalog_metadata["builtinTools"]["automations"])
        self.assertEqual(
            catalog_metadata["homeServer"],
            reconcile_module.CATALOG_OVERRIDE_MARKER,
        )

        glm = conn.execute(
            "SELECT name, params, meta FROM model WHERE id = 'z-ai/glm-5.1'"
        ).fetchone()
        self.assertEqual(glm[0], "GLM 5.1 Custom")
        self.assertEqual(json.loads(glm[1]), {"temperature": 0.4})
        self.assertEqual(json.loads(glm[2]), {"custom": True})

        admin_settings = json.loads(
            conn.execute(
                "SELECT settings FROM user WHERE id = 'admin'"
            ).fetchone()[0]
        )
        self.assertFalse(admin_settings["ui"]["iframeSandboxAllowSameOrigin"])
        self.assertFalse(admin_settings["ui"]["iframeSandboxAllowForms"])
        self.assertEqual(
            admin_settings["ui"]["system"],
            reconcile_module.PERSONAL_COMPANION_PROMPT,
        )
        self.assertEqual(
            admin_settings["ui"]["pinnedModels"],
            list(reconcile_module.MANAGED_PINNED_MODEL_IDS),
        )

        claude = conn.execute(
            "SELECT params, meta FROM model WHERE id = '~anthropic/claude-sonnet-latest'"
        ).fetchone()
        self.assertEqual(
            json.loads(claude[0]),
            {"reasoning_effort": "high"},
        )
        self.assertEqual(json.loads(claude[1]), {})

        companion = conn.execute(
            "SELECT base_model_id, params, meta FROM model WHERE id = 'companion'"
        ).fetchone()
        self.assertEqual(companion[0], "openrouter/auto")
        self.assertEqual(
            json.loads(companion[1])["system"],
            reconcile_module.PERSONAL_COMPANION_PROMPT,
        )
        self.assertEqual(json.loads(companion[1])["function_calling"], "native")
        companion_metadata = json.loads(companion[2])
        self.assertEqual(
            companion_metadata["defaultFeatureIds"],
            ["web_search", "code_interpreter"],
        )
        self.assertTrue(companion_metadata["builtinTools"]["calendar"])
        self.assertTrue(
            companion_metadata["capabilities"]["code_interpreter"]
        )
        self.assertFalse(
            companion_metadata["capabilities"]["image_generation"]
        )

        default_pins = json.loads(
            conn.execute(
                "SELECT value FROM config WHERE key = 'ui.default_pinned_models'"
            ).fetchone()[0]
        )
        self.assertEqual(
            default_pins,
            ",".join(reconcile_module.MANAGED_PINNED_MODEL_IDS),
        )
        model_order = json.loads(
            conn.execute(
                "SELECT value FROM config WHERE key = 'ui.model_order_list'"
            ).fetchone()[0]
        )
        self.assertEqual(
            model_order,
            list(reconcile_module.MANAGED_PINNED_MODEL_IDS),
        )

        rigorous = conn.execute(
            "SELECT base_model_id, params, meta FROM model WHERE id = 'rigorous'"
        ).fetchone()
        self.assertEqual(
            rigorous[0], "openrouter/auto"
        )
        self.assertEqual(
            json.loads(rigorous[1])["system"],
            reconcile_module.RIGOROUS_PROMPT,
        )
        self.assertEqual(json.loads(rigorous[1])["function_calling"], "native")
        self.assertTrue(
            json.loads(rigorous[2])["capabilities"]["code_interpreter"]
        )
        self.assertEqual(
            json.loads(rigorous[2])["defaultFeatureIds"],
            ["web_search", "code_interpreter"],
        )
        deep_research = conn.execute(
            "SELECT base_model_id, params, meta FROM model WHERE id = 'deep-research'"
        ).fetchone()
        self.assertEqual(
            json.loads(deep_research[1])["system"],
            reconcile_module.DEEP_RESEARCH_PROFILE_PROMPT,
        )
        self.assertEqual(
            json.loads(deep_research[1])["function_calling"], "native"
        )
        self.assertEqual(
            json.loads(deep_research[2])["toolIds"],
            ["server:gpt-researcher"],
        )
        model_steward = conn.execute(
            "SELECT base_model_id, params, meta FROM model WHERE id = 'model-steward'"
        ).fetchone()
        self.assertEqual(
            model_steward[0],
            "google/gemini-3.1-flash-lite",
        )
        self.assertEqual(
            json.loads(model_steward[1])["system"],
            reconcile_module.MODEL_STEWARD_PROMPT,
        )
        self.assertEqual(
            json.loads(model_steward[1])["function_calling"], "native"
        )
        self.assertIn("at most six distinct", reconcile_module.MODEL_STEWARD_PROMPT)
        self.assertIn("at most eight", reconcile_module.MODEL_STEWARD_PROMPT)
        self.assertIn("two consecutive searches", reconcile_module.MODEL_STEWARD_PROMPT)
        automation = conn.execute(
            "SELECT data, is_active, next_run_at FROM automation WHERE id = ?",
            (reconcile_module.MODEL_STEWARD_AUTOMATION_ID,),
        ).fetchone()
        self.assertEqual(
            json.loads(automation[0])["model_id"],
            "model-steward",
        )
        self.assertEqual(automation[1], 1)
        self.assertGreater(automation[2], 0)
        self.assertEqual(
            json.loads(
                conn.execute(
                    "SELECT value FROM config WHERE key = 'rag.embedding_model'"
                ).fetchone()[0]
            ),
            "google/gemini-embedding-2",
        )
        self.assertEqual(
            json.loads(
                conn.execute(
                    "SELECT value FROM config WHERE key = 'rag.openai.api_base_url'"
                ).fetchone()[0]
            ),
            "https://openrouter.ai/api/v1",
        )
        self.assertEqual(
            json.loads(
                conn.execute(
                    "SELECT value FROM config WHERE key = 'rag.openai.api_key'"
                ).fetchone()[0]
            ),
            "openrouter-test-key",
        )
        self.assertFalse(
            json.loads(
                conn.execute(
                    "SELECT value FROM config WHERE key = 'rag.full_context'"
                ).fetchone()[0]
            )
        )
        self.assertTrue(
            json.loads(
                conn.execute(
                    "SELECT value FROM config WHERE key = 'rag.enable_hybrid_search'"
                ).fetchone()[0]
            )
        )
        self.assertEqual(conn.execute("SELECT count(*) FROM config_old").fetchone()[0], 0)
        conn.close()

        self.assertTrue(
            (
                self.data_dir
                / "remediation-backups"
                / "webui-pre-security-policy-v6.db"
            ).is_file()
        )
        self.assertEqual(
            stat.S_IMODE(
                (
                    self.data_dir
                    / "remediation-backups"
                    / "webui-pre-security-policy-v6.db"
                ).stat().st_mode
            ),
            0o600,
        )
        for function_id in reconcile_module.UNSAFE_FUNCTION_IDS:
            quarantined = (
                self.data_dir
                / "quarantine"
                / "open-webui-functions"
                / f"{function_id}.py"
            )
            self.assertTrue(quarantined.is_file())
            self.assertEqual(stat.S_IMODE(quarantined.stat().st_mode), 0o600)
        self.assertFalse((self.data_dir / "vocab_embeddings_cache.json").exists())
        self.assertEqual(len(first["removed_cache_paths"]), 2)

        second = reconcile_module.reconcile(self.db_path, self.data_dir)
        self.assertEqual(second["database_changes"], 0)
        self.assertEqual(second["removed_cache_paths"], [])

    def test_reconcile_preserves_runtime_model_selections_and_automation_pause(self):
        conn = sqlite3.connect(self.db_path)
        for model_id, base_model in (
            ("companion", "google/new-approved-companion"),
            ("rigorous", "google/new-approved-rigorous"),
            ("deep-research", "google/new-approved-research"),
            ("model-steward", "google/new-approved-steward"),
        ):
            conn.execute(
                "INSERT INTO model VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    model_id,
                    "admin",
                    base_model,
                    "Old name",
                    "{}",
                    "{}",
                    1,
                    1,
                    1,
                ),
            )
        conn.execute(
            "INSERT INTO automation VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                reconcile_module.MODEL_STEWARD_AUTOMATION_ID,
                "admin",
                "Old name",
                "{}",
                "{}",
                0,
                123,
                None,
                1,
                1,
            ),
        )
        conn.commit()
        conn.close()

        reconcile_module.reconcile(self.db_path, self.data_dir)

        conn = sqlite3.connect(self.db_path)
        models = {
            row[0]: row[1:]
            for row in conn.execute(
                "SELECT id, base_model_id, name, params FROM model "
                "WHERE id IN ('companion', 'rigorous', 'deep-research', 'model-steward')"
            )
        }
        automation = conn.execute(
            "SELECT is_active, next_run_at FROM automation WHERE id = ?",
            (reconcile_module.MODEL_STEWARD_AUTOMATION_ID,),
        ).fetchone()
        conn.close()
        self.assertEqual(models["rigorous"][0], "google/new-approved-rigorous")
        self.assertEqual(
            models["companion"][0],
            "google/new-approved-companion",
        )
        self.assertEqual(models["deep-research"][0], "google/new-approved-research")
        self.assertEqual(models["model-steward"][0], "google/new-approved-steward")
        self.assertEqual(models["rigorous"][1], "Rigorous")
        self.assertEqual(
            json.loads(models["rigorous"][2])["system"],
            reconcile_module.RIGOROUS_PROMPT,
        )
        self.assertEqual(automation, (0, None))

    def test_reconcile_bounds_policy_backup_retention(self):
        backup_dir = self.data_dir / "remediation-backups"
        backup_dir.mkdir()
        for version in (3, 4, 5):
            (backup_dir / f"webui-pre-security-policy-v{version}.db").write_bytes(
                f"backup-{version}".encode()
            )

        result = reconcile_module.reconcile(self.db_path, self.data_dir)

        self.assertFalse(
            (backup_dir / "webui-pre-security-policy-v3.db").exists()
        )
        for version in (4, 5, 6):
            self.assertTrue(
                (backup_dir / f"webui-pre-security-policy-v{version}.db").is_file()
            )
        self.assertEqual(
            result["pruned_backups"],
            [str((backup_dir / "webui-pre-security-policy-v3.db").resolve())],
        )

    def test_reconcile_rejects_symlinked_private_directory(self):
        escape = self.data_dir / "escape"
        escape.mkdir()
        (self.data_dir / "quarantine").symlink_to(escape, target_is_directory=True)

        with self.assertRaisesRegex(RuntimeError, "not a real directory"):
            reconcile_module.reconcile(self.db_path, self.data_dir)

        conn = sqlite3.connect(self.db_path)
        remaining = conn.execute(
            "SELECT count(*) FROM function WHERE id IN (?, ?, ?, ?)",
            tuple(sorted(reconcile_module.UNSAFE_FUNCTION_IDS)),
        ).fetchone()[0]
        conn.close()
        self.assertEqual(remaining, len(reconcile_module.UNSAFE_FUNCTION_IDS))

    def test_reconcile_removes_retired_local_embedding_cache(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "UPDATE config SET value = ? WHERE key = 'rag.embedding_engine'",
            (json.dumps(""),),
        )
        conn.execute(
            "UPDATE config SET value = ? WHERE key = 'rag.embedding_model'",
            (json.dumps("sentence-transformers/all-MiniLM-L6-v2"),),
        )
        conn.commit()
        conn.close()

        reconcile_module.reconcile(self.db_path, self.data_dir)

        self.assertFalse(
            (
                self.data_dir
                / "cache"
                / "embedding"
                / "models"
                / "models--sentence-transformers--all-MiniLM-L6-v2"
                / "weights"
            ).is_file()
        )


if __name__ == "__main__":
    unittest.main()
