#!/usr/bin/env python3
"""One-time, rollback-safe migration of Open WebUI's persisted embeddings.

The security-policy reconciler selects the new embedding provider in SQLite.
This second init container starts Open WebUI on loopback, rebuilds every
persisted file and knowledge collection through the application's own API,
verifies the stored vector dimensions and metadata, and only then records the
migration as complete.

The pre-migration Chroma directory and SQLite policy backup remain on the
Longhorn volume. If any file fails, both the vector index and the previous RAG
configuration are restored before the main Open WebUI container is allowed to
start.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import sqlite3
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from typing import Any, Iterator


POLICY_VERSION = 4
TARGET_MODEL = "google/gemini-embedding-2"
TARGET_DIMENSIONS = 3_072
MARKER_KEY = "home-server.embedding_index_model"
STATE_KEY = "home-server.embedding_migration_state"
RAG_KEYS = (
    "rag.embedding_engine",
    "rag.embedding_model",
    "rag.embedding_batch_size",
    "rag.enable_async_embedding",
    "rag.embedding_concurrent_requests",
    "rag.openai.api_base_url",
    "rag.openai.api_key",
    "rag.full_context",
    "rag.enable_hybrid_search",
    "rag.hybrid_bm25_weight",
    "rag.top_k",
    "rag.top_k_reranker",
)


def _decode(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return value


def _encode(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _config_get(conn: sqlite3.Connection, key: str) -> Any:
    row = conn.execute("SELECT value FROM config WHERE key = ?", (key,)).fetchone()
    return _decode(row[0]) if row else None


def _config_set(conn: sqlite3.Connection, key: str, value: Any) -> None:
    now = int(time.time())
    conn.execute(
        """
        INSERT INTO config(key, value, updated_at) VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET
          value = excluded.value,
          updated_at = excluded.updated_at
        """,
        (key, _encode(value), now),
    )


@contextmanager
def _temporary_config_override(
    db_path: Path,
    key: str,
    value: Any,
) -> Iterator[None]:
    """Apply one startup-only ConfigVar and restore its exact prior row."""

    conn = sqlite3.connect(db_path)
    try:
        prior = conn.execute(
            "SELECT value, updated_at FROM config WHERE key = ?",
            (key,),
        ).fetchone()
        conn.execute("BEGIN IMMEDIATE")
        _config_set(conn, key, value)
        conn.commit()
    finally:
        conn.close()

    try:
        yield
    finally:
        conn = sqlite3.connect(db_path)
        try:
            conn.execute("BEGIN IMMEDIATE")
            if prior is None:
                conn.execute("DELETE FROM config WHERE key = ?", (key,))
            else:
                conn.execute(
                    """
                    INSERT INTO config(key, value, updated_at) VALUES (?, ?, ?)
                    ON CONFLICT(key) DO UPDATE SET
                      value = excluded.value,
                      updated_at = excluded.updated_at
                    """,
                    (key, prior[0], prior[1]),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def _real_directory(path: Path, parent: Path) -> Path:
    parent = parent.resolve(strict=True)
    path = path.resolve(strict=True)
    if path.parent != parent:
        raise RuntimeError(f"unexpected directory location: {path}")
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise RuntimeError(f"path is not a real directory: {path}")
    return path


def _copy_vector_backup(vector_dir: Path, backup_dir: Path, data_dir: Path) -> None:
    vector_dir = _real_directory(vector_dir, data_dir)
    try:
        info = backup_dir.lstat()
    except FileNotFoundError:
        info = None
    if info is not None:
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise RuntimeError(f"vector backup is not a real directory: {backup_dir}")
        database = backup_dir / "chroma.sqlite3"
        if not database.is_file() or database.stat().st_size == 0:
            raise RuntimeError(f"existing vector backup is incomplete: {backup_dir}")
        return

    temporary = backup_dir.with_name(f".{backup_dir.name}.{os.getpid()}.tmp")
    if temporary.exists():
        raise RuntimeError(f"temporary vector backup already exists: {temporary}")
    shutil.copytree(vector_dir, temporary, symlinks=False)
    database = temporary / "chroma.sqlite3"
    if not database.is_file() or database.stat().st_size == 0:
        shutil.rmtree(temporary)
        raise RuntimeError("new vector backup is incomplete")
    os.replace(temporary, backup_dir)


def _restore_vectors(vector_dir: Path, backup_dir: Path, data_dir: Path) -> None:
    vector_dir = _real_directory(vector_dir, data_dir)
    backup_dir = _real_directory(backup_dir, data_dir / "remediation-backups")
    failed = vector_dir.with_name(f".{vector_dir.name}.failed.{os.getpid()}")
    os.replace(vector_dir, failed)
    try:
        shutil.copytree(backup_dir, vector_dir, symlinks=False)
    except Exception:
        os.replace(failed, vector_dir)
        raise
    shutil.rmtree(failed)


def _restore_rag_config(db_path: Path, backup_db: Path, error_type: str) -> None:
    source = sqlite3.connect(f"file:{backup_db}?mode=ro", uri=True)
    target = sqlite3.connect(db_path)
    try:
        target.execute("BEGIN IMMEDIATE")
        for key in RAG_KEYS:
            row = source.execute(
                "SELECT value FROM config WHERE key = ?", (key,)
            ).fetchone()
            if row is None:
                target.execute("DELETE FROM config WHERE key = ?", (key,))
            else:
                _config_set(target, key, _decode(row[0]))
        _config_set(
            target,
            STATE_KEY,
            {
                "state": "rolled_back",
                "policy_version": POLICY_VERSION,
                "error_type": error_type,
            },
        )
        target.commit()
    except Exception:
        target.rollback()
        raise
    finally:
        source.close()
        target.close()


def _request(
    base_url: str,
    token: str | None,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    timeout: int = 120,
) -> Any:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        f"{base_url}{path}",
        data=data,
        headers=headers,
        method=method,
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read()
        return json.loads(body) if body else None


def _wait_for_health(base_url: str, process: subprocess.Popen, timeout: int) -> None:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                f"temporary Open WebUI exited with status {process.returncode}"
            )
        try:
            response = _request(base_url, None, "GET", "/health", timeout=5)
            if isinstance(response, dict) and response.get("status") is True:
                return
        except (OSError, urllib.error.URLError, ValueError) as error:
            last_error = error
        time.sleep(2)
    raise RuntimeError("temporary Open WebUI did not become healthy") from last_error


def _stop(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    process.send_signal(signal.SIGTERM)
    try:
        process.wait(timeout=30)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


def _admin_files_and_knowledge(
    db_path: Path,
) -> tuple[str, list[tuple[str, str]], dict[str, set[str]]]:
    conn = sqlite3.connect(db_path)
    try:
        admin = conn.execute(
            "SELECT id FROM user WHERE role = 'admin' ORDER BY created_at LIMIT 1"
        ).fetchone()
        if admin is None:
            raise RuntimeError("no Open WebUI administrator exists")
        files: list[tuple[str, str]] = []
        for file_id, raw_data in conn.execute("SELECT id, data FROM file ORDER BY id"):
            data = _decode(raw_data) if raw_data else {}
            content = data.get("content") if isinstance(data, dict) else None
            if not isinstance(content, str) or not content.strip():
                # Empty records have no useful embedding and are deliberately
                # excluded from the index.
                continue
            files.append((file_id, content))
        migrated_file_ids = {file_id for file_id, _ in files}
        knowledge: dict[str, set[str]] = {}
        has_knowledge_files = conn.execute(
            "SELECT 1 FROM sqlite_master "
            "WHERE type = 'table' AND name = 'knowledge_file'"
        ).fetchone()
        if has_knowledge_files:
            for knowledge_id, file_id in conn.execute(
                "SELECT knowledge_id, file_id FROM knowledge_file "
                "ORDER BY knowledge_id, file_id"
            ):
                if file_id in migrated_file_ids:
                    knowledge.setdefault(knowledge_id, set()).add(file_id)
        return admin[0], files, knowledge
    finally:
        conn.close()


def _validate_vectors(
    vector_dir: Path,
    expected_collections: dict[str, set[str]],
) -> None:
    import chromadb

    client = chromadb.PersistentClient(path=str(vector_dir))
    for collection_name, expected_file_ids in expected_collections.items():
        collection = client.get_collection(collection_name)
        result = collection.get(include=["embeddings", "metadatas"])
        embeddings = result.get("embeddings")
        if embeddings is None or len(embeddings) == 0:
            raise RuntimeError(f"{collection_name} has no embeddings")
        metadatas = result.get("metadatas") or []
        if len(metadatas) != len(embeddings):
            raise RuntimeError(f"{collection_name} metadata count is incomplete")
        observed_file_ids: set[str] = set()
        for embedding, metadata in zip(embeddings, metadatas, strict=True):
            if len(embedding) != TARGET_DIMENSIONS:
                raise RuntimeError(
                    f"{collection_name} has {len(embedding)} dimensions"
                )
            embedding_config = metadata.get("embedding_config", "")
            if TARGET_MODEL not in str(embedding_config):
                raise RuntimeError(
                    f"{collection_name} does not record the target embedding model"
                )
            file_id = metadata.get("file_id")
            if isinstance(file_id, str):
                observed_file_ids.add(file_id)
        if not expected_file_ids.issubset(observed_file_ids):
            missing = sorted(expected_file_ids - observed_file_ids)
            raise RuntimeError(
                f"{collection_name} is missing expected files: {missing}"
            )


def migrate(db_path: Path, data_dir: Path, port: int) -> dict[str, Any]:
    data_dir = data_dir.resolve(strict=True)
    db_path = db_path.resolve(strict=True)
    vector_dir = data_dir / "vector_db"
    backup_root = data_dir / "remediation-backups"
    vector_backup = backup_root / f"vector-db-pre-gemini-v{POLICY_VERSION}"
    database_backup = backup_root / f"webui-pre-security-policy-v{POLICY_VERSION}.db"

    conn = sqlite3.connect(db_path)
    try:
        selected_model = _config_get(conn, "rag.embedding_model")
        completed_model = _config_get(conn, MARKER_KEY)
    finally:
        conn.close()
    if completed_model == TARGET_MODEL:
        return {"status": "already-complete", "model": TARGET_MODEL}
    if selected_model != TARGET_MODEL:
        return {
            "status": "not-selected",
            "selected_model": selected_model,
            "target_model": TARGET_MODEL,
        }
    backup_root.mkdir(mode=0o700, exist_ok=True)
    backup_root.chmod(0o700)
    if not database_backup.is_file() or database_backup.stat().st_size == 0:
        raise RuntimeError(f"policy database backup is unavailable: {database_backup}")

    _copy_vector_backup(vector_dir, vector_backup, data_dir)
    admin_id, files, knowledge = _admin_files_and_knowledge(db_path)

    from open_webui.utils.auth import create_token

    token = create_token({"id": admin_id}, expires_delta=timedelta(hours=2))
    base_url = f"http://127.0.0.1:{port}"
    # The temporary server must not claim any due personal automation while it
    # is running only to rebuild vectors. Restore the exact prior ConfigVar row
    # before the normal server is allowed to start.
    with _temporary_config_override(db_path, "automations.enable", False):
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "open_webui.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--workers",
                "1",
                "--no-access-log",
            ],
            stdin=subprocess.DEVNULL,
        )
        try:
            _wait_for_health(base_url, process, timeout=180)
            migrated: list[str] = []
            for file_id, content in files:
                response = _request(
                    base_url,
                    token,
                    "POST",
                    "/api/v1/retrieval/process/file",
                    {"file_id": file_id, "content": content},
                    timeout=300,
                )
                if (
                    not isinstance(response, dict)
                    or response.get("status") is not True
                ):
                    raise RuntimeError(f"file migration failed: {file_id}")
                migrated.append(file_id)

            knowledge_result = _request(
                base_url,
                token,
                "POST",
                "/api/v1/knowledge/reindex",
                {},
                timeout=900,
            )
            if knowledge_result is not True:
                raise RuntimeError("knowledge collection migration failed")
        except Exception as error:
            _stop(process)
            _restore_vectors(vector_dir, vector_backup, data_dir)
            _restore_rag_config(db_path, database_backup, type(error).__name__)
            return {
                "status": "rolled-back",
                "model": TARGET_MODEL,
                "error_type": type(error).__name__,
            }
        finally:
            _stop(process)

    try:
        expected_collections = {
            f"file-{file_id}": {file_id}
            for file_id in migrated
        }
        expected_collections.update(knowledge)
        _validate_vectors(vector_dir, expected_collections)
    except Exception as error:
        _restore_vectors(vector_dir, vector_backup, data_dir)
        _restore_rag_config(db_path, database_backup, type(error).__name__)
        return {
            "status": "rolled-back",
            "model": TARGET_MODEL,
            "error_type": type(error).__name__,
        }

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        _config_set(conn, MARKER_KEY, TARGET_MODEL)
        _config_set(
            conn,
            STATE_KEY,
            {
                "state": "complete",
                "policy_version": POLICY_VERSION,
                "files": len(migrated),
                "knowledge_collections": len(knowledge),
                "dimensions": TARGET_DIMENSIONS,
            },
        )
        conn.commit()
    finally:
        conn.close()
    return {
        "status": "complete",
        "model": TARGET_MODEL,
        "files": len(migrated),
        "knowledge_collections": len(knowledge),
        "dimensions": TARGET_DIMENSIONS,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--database",
        type=Path,
        default=Path(os.getenv("WEBUI_DB_PATH", "/app/backend/data/webui.db")),
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(os.getenv("DATA_DIR", "/app/backend/data")),
    )
    parser.add_argument("--port", type=int, default=18_080)
    args = parser.parse_args()
    result = migrate(args.database, args.data_dir, args.port)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
