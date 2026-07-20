import importlib.util
import json
import sqlite3
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = (
    REPO_ROOT / "apps" / "open-webui" / "config" / "migrate_embeddings.py"
)
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


class OpenWebUIEmbeddingMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_not_selected_is_a_noop(self) -> None:
        database = self.data_dir / "webui.db"
        create_config_database(
            database,
            {"rag.embedding_model": "text-embedding-3-small"},
        )

        result = migration.migrate(database, self.data_dir, 18_080)

        self.assertEqual(result["status"], "not-selected")
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

        fake_chromadb = types.SimpleNamespace(
            PersistentClient=lambda path: Client(),
        )
        with patch.dict(sys.modules, {"chromadb": fake_chromadb}):
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
