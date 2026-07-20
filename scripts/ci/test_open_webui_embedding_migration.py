import importlib.util
import json
import os
import sqlite3
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = (
    REPO_ROOT / "apps" / "open-webui" / "config" / "migrate_embeddings.py"
)
DEPLOYMENT_PATH = REPO_ROOT / "apps" / "open-webui" / "deployments.yaml"
SPEC = importlib.util.spec_from_file_location(
    "open_webui_embedding_migration", MODULE_PATH
)
migration = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(migration)


def create_config_database(path: Path, values: dict[str, object]) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE config (
          key TEXT PRIMARY KEY,
          value JSON NOT NULL,
          updated_at INTEGER NOT NULL
        )
        """
    )
    for key, value in values.items():
        conn.execute(
            "INSERT INTO config VALUES (?, ?, 1)",
            (key, json.dumps(value)),
        )
    conn.commit()
    conn.close()


def create_memory_table(
    path: Path,
    rows: list[tuple[str, str, str, str | None, str, int, int]],
) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE memory (
          id TEXT PRIMARY KEY,
          user_id TEXT NOT NULL,
          type TEXT NOT NULL,
          path TEXT,
          content TEXT NOT NULL,
          updated_at INTEGER NOT NULL,
          created_at INTEGER NOT NULL
        )
        """
    )
    conn.executemany(
        """
        INSERT INTO memory(
          id, user_id, type, path, content, updated_at, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    conn.close()


class OpenWebUIEmbeddingMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_init_container_can_import_the_open_webui_backend(self) -> None:
        with DEPLOYMENT_PATH.open(encoding="utf-8") as handle:
            deployments = [
                document
                for document in yaml.safe_load_all(handle)
                if document
                and document.get("kind") == "Deployment"
                and document.get("metadata", {}).get("name") == "open-webui"
            ]
        self.assertEqual(len(deployments), 1)
        init_containers = {
            container["name"]: container
            for container in deployments[0]["spec"]["template"]["spec"][
                "initContainers"
            ]
        }
        migration_container = init_containers["migrate-gemini-embeddings"]
        environment = {
            entry["name"]: entry.get("value")
            for entry in migration_container["env"]
        }
        self.assertEqual(environment["PYTHONPATH"], "/app/backend")

    def test_not_selected_is_a_noop(self) -> None:
        database = self.data_dir / "webui.db"
        create_config_database(
            database,
            {"rag.embedding_model": "text-embedding-3-small"},
        )

        result = migration.migrate(database, self.data_dir, 18_080)

        self.assertEqual(result["status"], "not-selected")
        self.assertFalse((self.data_dir / "remediation-backups").exists())

    def test_both_file_and_memory_markers_are_required_for_completion(self) -> None:
        database = self.data_dir / "webui.db"
        create_config_database(
            database,
            {
                "rag.embedding_model": migration.TARGET_MODEL,
                migration.MARKER_KEY: migration.TARGET_MODEL,
                migration.MEMORY_MARKER_KEY: migration.TARGET_MODEL,
            },
        )

        result = migration.migrate(database, self.data_dir, 18_080)

        self.assertEqual(result["status"], "already-complete")
        self.assertFalse((self.data_dir / "remediation-backups").exists())

    def test_vector_backup_and_restore_are_lossless(self) -> None:
        vectors = self.data_dir / "vector_db"
        vectors.mkdir()
        (vectors / "chroma.sqlite3").write_bytes(b"original-index")
        remediation = self.data_dir / "remediation-backups"
        remediation.mkdir()
        backup = remediation / "vector-db-pre-gemini-v4"

        migration._copy_vector_backup(vectors, backup, self.data_dir)
        (vectors / "chroma.sqlite3").write_bytes(b"partially-migrated-index")
        migration._restore_vectors(vectors, backup, self.data_dir)

        self.assertEqual(
            (vectors / "chroma.sqlite3").read_bytes(),
            b"original-index",
        )
        self.assertEqual(
            (backup / "chroma.sqlite3").read_bytes(),
            b"original-index",
        )

    def test_rag_configuration_rolls_back_from_policy_backup(self) -> None:
        current = self.data_dir / "webui.db"
        backup = self.data_dir / "backup.db"
        create_config_database(
            current,
            {
                "rag.embedding_engine": "openai",
                "rag.embedding_model": migration.TARGET_MODEL,
                "rag.openai.api_base_url": "https://openrouter.ai/api/v1",
            },
        )
        create_config_database(
            backup,
            {
                "rag.embedding_engine": "openai",
                "rag.embedding_model": "text-embedding-3-small",
                "rag.openai.api_base_url": "https://api.openai.com/v1",
            },
        )

        migration._restore_rag_config(current, backup, "SyntheticFailure")

        conn = sqlite3.connect(current)
        try:
            values = {
                key: json.loads(value)
                for key, value in conn.execute("SELECT key, value FROM config")
            }
        finally:
            conn.close()
        self.assertEqual(values["rag.embedding_model"], "text-embedding-3-small")
        self.assertEqual(
            values["rag.openai.api_base_url"],
            "https://api.openai.com/v1",
        )
        self.assertEqual(
            values[migration.STATE_KEY]["state"],
            "rolled_back",
        )

    def test_vector_validation_covers_every_expected_knowledge_file(self) -> None:
        class Collection:
            def get(self, include):
                self.include = include
                return {
                    "embeddings": [[0.0] * migration.TARGET_DIMENSIONS],
                    "metadatas": [
                        {
                            "file_id": "file-a",
                            "embedding_config": {
                                "model": migration.TARGET_MODEL,
                            },
                        }
                    ],
                }

        class Client:
            def get_collection(self, name):
                self.name = name
                return Collection()

        with patch.object(
            migration,
            "_persistent_vector_client",
            return_value=Client(),
        ):
            migration._validate_vectors(
                self.data_dir,
                {"knowledge-a": {"file-a"}},
            )
            with self.assertRaisesRegex(
                RuntimeError,
                "missing expected files",
            ):
                migration._validate_vectors(
                    self.data_dir,
                    {"knowledge-a": {"file-a", "file-b"}},
                )

    def test_memory_rows_preserve_hierarchy_and_authoritative_metadata(self) -> None:
        database = self.data_dir / "webui.db"
        create_config_database(database, {})
        create_memory_table(
            database,
            [
                (
                    "memory-a",
                    "user-a",
                    "user",
                    "identity/preferences",
                    "Prefers concise answers.",
                    20,
                    10,
                ),
                (
                    "memory-b",
                    "user-a",
                    "context",
                    None,
                    "The cluster is a personal hobby.",
                    40,
                    30,
                ),
            ],
        )

        memories = migration._memories_by_user(database)

        self.assertEqual(list(memories), ["user-a"])
        first, second = memories["user-a"]
        self.assertEqual(
            migration._memory_vector_text(first),
            "identity/preferences\nPrefers concise answers.",
        )
        self.assertEqual(
            migration._memory_metadata(first),
            {
                "created_at": 10,
                "updated_at": 20,
                "type": "user",
                "path": "identity/preferences",
            },
        )
        self.assertNotIn("path", migration._memory_metadata(second))

    def test_vector_client_reuses_open_webui_configuration_and_checks_path(
        self,
    ) -> None:
        vector_dir = self.data_dir / "vector_db"
        vector_dir.mkdir()

        class Client:
            def get_settings(self):
                return types.SimpleNamespace(
                    persist_directory=str(vector_dir),
                )

        client = Client()
        fake_factory = types.ModuleType("open_webui.retrieval.vector.factory")
        fake_factory.VECTOR_DB_CLIENT = types.SimpleNamespace(client=client)
        fake_open_webui = types.ModuleType("open_webui")
        fake_open_webui.__path__ = []
        fake_retrieval = types.ModuleType("open_webui.retrieval")
        fake_retrieval.__path__ = []
        fake_vector = types.ModuleType("open_webui.retrieval.vector")
        fake_vector.__path__ = []

        with patch.dict(
            sys.modules,
            {
                "open_webui": fake_open_webui,
                "open_webui.retrieval": fake_retrieval,
                "open_webui.retrieval.vector": fake_vector,
                "open_webui.retrieval.vector.factory": fake_factory,
            },
        ):
            self.assertIs(
                migration._persistent_vector_client(vector_dir),
                client,
            )
            with self.assertRaisesRegex(RuntimeError, "configured Chroma path"):
                migration._persistent_vector_client(
                    self.data_dir / "different-vector-db"
                )

    def test_memory_embeddings_use_open_webui_helper_and_document_prefix(
        self,
    ) -> None:
        database = self.data_dir / "webui.db"
        create_config_database(
            database,
            {
                "rag.embedding_engine": "openai",
                "rag.embedding_model": migration.TARGET_MODEL,
                "rag.openai.api_base_url": "https://openrouter.ai/api/v1",
                "rag.openai.api_key": "synthetic-key",
                "rag.embedding_batch_size": 1,
                "rag.enable_async_embedding": True,
                "rag.embedding_concurrent_requests": 3,
            },
        )
        memories = {
            "user-a": [
                {
                    "id": "memory-a",
                    "type": "context",
                    "path": "home/preferences",
                    "content": "Personal preference.",
                    "updated_at": 20,
                    "created_at": 10,
                }
            ]
        }
        captured = {}

        async def embed(texts, prefix=None, user=None):
            captured["texts"] = texts
            captured["prefix"] = prefix
            captured["user"] = user
            return [[0.0] * migration.TARGET_DIMENSIONS for _ in texts]

        def get_embedding_function(*args, **kwargs):
            captured["factory_args"] = args
            captured["factory_kwargs"] = kwargs
            return embed

        fake_utils = types.ModuleType("open_webui.retrieval.utils")
        fake_utils.get_embedding_function = get_embedding_function
        fake_open_webui = types.ModuleType("open_webui")
        fake_open_webui.__path__ = []
        fake_retrieval = types.ModuleType("open_webui.retrieval")
        fake_retrieval.__path__ = []

        with (
            patch.dict(
                sys.modules,
                {
                    "open_webui": fake_open_webui,
                    "open_webui.retrieval": fake_retrieval,
                    "open_webui.retrieval.utils": fake_utils,
                },
            ),
            patch.dict(
                os.environ,
                {"RAG_EMBEDDING_CONTENT_PREFIX": "title: none | text: "},
            ),
        ):
            result = migration._generate_memory_embeddings(
                database,
                memories,
            )

        self.assertEqual(
            captured["factory_args"][:2],
            ("openai", migration.TARGET_MODEL),
        )
        self.assertEqual(
            captured["factory_kwargs"]["url"],
            "https://openrouter.ai/api/v1",
        )
        self.assertEqual(captured["factory_kwargs"]["embedding_batch_size"], 1)
        self.assertEqual(captured["factory_kwargs"]["concurrent_requests"], 3)
        self.assertEqual(
            captured["texts"],
            ["home/preferences\nPersonal preference."],
        )
        self.assertEqual(captured["prefix"], "title: none | text: ")
        self.assertIsNone(captured["user"])
        self.assertEqual(
            len(result["user-a"][0]),
            migration.TARGET_DIMENSIONS,
        )

    def test_memory_validation_rejects_old_dimensions_and_stale_collections(
        self,
    ) -> None:
        memories = {
            "user-a": [
                {
                    "id": "memory-a",
                    "type": "context",
                    "path": None,
                    "content": "Personal preference.",
                    "updated_at": 20,
                    "created_at": 10,
                }
            ]
        }

        class NamedCollection:
            def __init__(self, name):
                self.name = name

        class Collection:
            def __init__(self, dimensions):
                self.dimensions = dimensions

            def get(self, include):
                self.include = include
                return {
                    "ids": ["memory-a"],
                    "documents": ["Personal preference."],
                    "embeddings": [[0.0] * self.dimensions],
                    "metadatas": [
                        {
                            "created_at": 10,
                            "updated_at": 20,
                            "type": "context",
                        }
                    ],
                }

        class Client:
            def __init__(self, dimensions, stale=False):
                self.dimensions = dimensions
                self.stale = stale

            def list_collections(self):
                result = [NamedCollection("user-memory-user-a")]
                if self.stale:
                    result.append(NamedCollection("user-memory-deleted-user"))
                return result

            def get_collection(self, name):
                self.name = name
                return Collection(self.dimensions)

        with patch.object(
            migration,
            "_persistent_vector_client",
            return_value=Client(migration.TARGET_DIMENSIONS),
        ):
            migration._validate_memory_vectors(self.data_dir, memories)

        with patch.object(
            migration,
            "_persistent_vector_client",
            return_value=Client(1_536),
        ):
            with self.assertRaisesRegex(RuntimeError, "1536 dimensions"):
                migration._validate_memory_vectors(self.data_dir, memories)

        with patch.object(
            migration,
            "_persistent_vector_client",
            return_value=Client(
                migration.TARGET_DIMENSIONS,
                stale=True,
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "stale="):
                migration._validate_memory_vectors(self.data_dir, memories)

    def test_memory_rebuild_removes_stale_indexes_and_upserts_sqlite_rows(
        self,
    ) -> None:
        memories = {
            "user-a": [
                {
                    "id": "memory-a",
                    "type": "context",
                    "path": None,
                    "content": "Personal preference.",
                    "updated_at": 20,
                    "created_at": 10,
                }
            ]
        }
        vectors = {
            "user-a": [[0.0] * migration.TARGET_DIMENSIONS],
        }

        class NamedCollection:
            def __init__(self, name):
                self.name = name

        class Collection:
            def __init__(self):
                self.upserted = None

            def upsert(self, **kwargs):
                self.upserted = kwargs

        class Client:
            def __init__(self):
                self.deleted = []
                self.collection = Collection()

            def list_collections(self):
                return [
                    NamedCollection("file-a"),
                    NamedCollection("user-memory-user-a"),
                    NamedCollection("user-memory-deleted-user"),
                ]

            def delete_collection(self, name):
                self.deleted.append(name)

            def get_or_create_collection(self, name, metadata):
                self.created = (name, metadata)
                return self.collection

        client = Client()
        fake_utils = types.ModuleType("open_webui.retrieval.vector.utils")
        fake_utils.process_metadata = lambda metadata: metadata
        fake_open_webui = types.ModuleType("open_webui")
        fake_open_webui.__path__ = []
        fake_retrieval = types.ModuleType("open_webui.retrieval")
        fake_retrieval.__path__ = []
        fake_vector = types.ModuleType("open_webui.retrieval.vector")
        fake_vector.__path__ = []

        with (
            patch.object(
                migration,
                "_persistent_vector_client",
                return_value=client,
            ),
            patch.dict(
                sys.modules,
                {
                    "open_webui": fake_open_webui,
                    "open_webui.retrieval": fake_retrieval,
                    "open_webui.retrieval.vector": fake_vector,
                    "open_webui.retrieval.vector.utils": fake_utils,
                },
            ),
        ):
            migration._rebuild_memory_collections(
                self.data_dir,
                memories,
                vectors,
            )

        self.assertEqual(
            client.deleted,
            ["user-memory-user-a", "user-memory-deleted-user"],
        )
        self.assertEqual(
            client.created,
            ("user-memory-user-a", {"hnsw:space": "cosine"}),
        )
        self.assertEqual(client.collection.upserted["ids"], ["memory-a"])
        self.assertEqual(
            client.collection.upserted["documents"],
            ["Personal preference."],
        )
        self.assertEqual(
            client.collection.upserted["embeddings"],
            vectors["user-a"],
        )

    def test_memory_only_repair_preserves_completed_file_migration(self) -> None:
        database = self.data_dir / "webui.db"
        create_config_database(
            database,
            {
                "rag.embedding_model": migration.TARGET_MODEL,
                migration.MARKER_KEY: migration.TARGET_MODEL,
                migration.STATE_KEY: {"state": "complete", "files": 19},
            },
        )
        create_memory_table(
            database,
            [
                (
                    "memory-a",
                    "user-a",
                    "context",
                    None,
                    "Personal preference.",
                    20,
                    10,
                )
            ],
        )

        with (
            patch.object(migration, "_copy_vector_backup") as backup,
            patch.object(
                migration,
                "_admin_files_and_knowledge",
                return_value=("admin-a", [("file-a", "content")], {}),
            ),
            patch.object(
                migration,
                "_generate_memory_embeddings",
                return_value={
                    "user-a": [[0.0] * migration.TARGET_DIMENSIONS]
                },
            ),
            patch.object(migration, "_rebuild_memory_collections") as rebuild,
            patch.object(migration, "_validate_vectors") as validate_files,
            patch.object(
                migration, "_validate_memory_vectors"
            ) as validate_memories,
        ):
            result = migration.migrate(database, self.data_dir, 18_080)

        self.assertEqual(result["status"], "memory-complete")
        self.assertEqual(result["memories"], 1)
        self.assertIn("vector-db-pre-gemini-memory-v4", str(backup.call_args.args[1]))
        rebuild.assert_called_once()
        validate_files.assert_called_once()
        validate_memories.assert_called_once()

        conn = sqlite3.connect(database)
        try:
            values = {
                key: json.loads(value)
                for key, value in conn.execute("SELECT key, value FROM config")
            }
        finally:
            conn.close()
        self.assertEqual(values[migration.MARKER_KEY], migration.TARGET_MODEL)
        self.assertEqual(
            values[migration.MEMORY_MARKER_KEY],
            migration.TARGET_MODEL,
        )
        self.assertEqual(values[migration.STATE_KEY]["files"], 19)
        self.assertEqual(values[migration.MEMORY_STATE_KEY]["memories"], 1)

    def test_memory_only_failure_restores_vectors_without_rolling_back_rag(
        self,
    ) -> None:
        database = self.data_dir / "webui.db"
        create_config_database(
            database,
            {
                "rag.embedding_model": migration.TARGET_MODEL,
                "rag.openai.api_base_url": "https://openrouter.ai/api/v1",
                migration.MARKER_KEY: migration.TARGET_MODEL,
            },
        )

        with (
            patch.object(migration, "_copy_vector_backup"),
            patch.object(
                migration,
                "_admin_files_and_knowledge",
                return_value=("admin-a", [], {}),
            ),
            patch.object(
                migration,
                "_generate_memory_embeddings",
                return_value={},
            ),
            patch.object(
                migration,
                "_rebuild_memory_collections",
                side_effect=RuntimeError("synthetic"),
            ),
            patch.object(migration, "_restore_vectors") as restore,
            patch.object(migration, "_restore_rag_config") as restore_rag,
        ):
            result = migration.migrate(database, self.data_dir, 18_080)

        self.assertEqual(result["status"], "memory-rolled-back")
        restore.assert_called_once()
        restore_rag.assert_not_called()
        conn = sqlite3.connect(database)
        try:
            values = {
                key: json.loads(value)
                for key, value in conn.execute("SELECT key, value FROM config")
            }
        finally:
            conn.close()
        self.assertEqual(
            values["rag.openai.api_base_url"],
            "https://openrouter.ai/api/v1",
        )
        self.assertEqual(values[migration.MARKER_KEY], migration.TARGET_MODEL)
        self.assertNotIn(migration.MEMORY_MARKER_KEY, values)
        self.assertEqual(
            values[migration.MEMORY_STATE_KEY]["state"],
            "rolled_back",
        )

    def test_temporary_config_override_restores_exact_prior_value(self) -> None:
        database = self.data_dir / "webui.db"
        create_config_database(
            database,
            {"automations.enable": True},
        )

        with self.assertRaisesRegex(RuntimeError, "synthetic"):
            with migration._temporary_config_override(
                database,
                "automations.enable",
                False,
            ):
                conn = sqlite3.connect(database)
                try:
                    current = conn.execute(
                        "SELECT value FROM config WHERE key = ?",
                        ("automations.enable",),
                    ).fetchone()[0]
                finally:
                    conn.close()
                self.assertFalse(json.loads(current))
                raise RuntimeError("synthetic")

        conn = sqlite3.connect(database)
        try:
            restored = conn.execute(
                "SELECT value, updated_at FROM config WHERE key = ?",
                ("automations.enable",),
            ).fetchone()
        finally:
            conn.close()
        self.assertTrue(json.loads(restored[0]))
        self.assertEqual(restored[1], 1)


if __name__ == "__main__":
    unittest.main()
