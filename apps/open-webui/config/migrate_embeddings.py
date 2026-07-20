#!/usr/bin/env python3
"""One-time, rollback-safe migration of Open WebUI's persisted embeddings.

The security-policy reconciler selects the new embedding provider in SQLite.
This second init container starts Open WebUI on loopback, rebuilds every
persisted file and knowledge collection through the application's own API. It
also rebuilds the per-user memory collections with Open WebUI's own embedding
function. The stored vector dimensions, source IDs, documents, and metadata are
verified before either migration is recorded as complete.

The original full-index backup and a separate memory-only backup remain on the
Longhorn volume. A failure during the initial full migration restores both the
vector index and previous RAG configuration. A failure during a later
memory-only repair restores only the vector index, preserving the already
verified file migration and target RAG configuration.
"""

from __future__ import annotations

import argparse
import asyncio
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
MEMORY_MARKER_KEY = "home-server.memory_embedding_index_model"
MEMORY_STATE_KEY = "home-server.memory_embedding_migration_state"
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


def _record_memory_state(
    db_path: Path,
    state: str,
    *,
    error_type: str | None = None,
    memories: int | None = None,
    user_collections: int | None = None,
) -> None:
    value: dict[str, Any] = {
        "state": state,
        "policy_version": POLICY_VERSION,
    }
    if error_type is not None:
        value["error_type"] = error_type
    if memories is not None:
        value["memories"] = memories
    if user_collections is not None:
        value["user_collections"] = user_collections
    if state == "complete":
        value["dimensions"] = TARGET_DIMENSIONS

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        if state == "complete":
            _config_set(conn, MEMORY_MARKER_KEY, TARGET_MODEL)
        _config_set(conn, MEMORY_STATE_KEY, value)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


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


def _memories_by_user(db_path: Path) -> dict[str, list[dict[str, Any]]]:
    """Return the authoritative memory rows without exposing their content."""

    conn = sqlite3.connect(db_path)
    try:
        has_memory_table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'memory'"
        ).fetchone()
        if not has_memory_table:
            return {}

        memories: dict[str, list[dict[str, Any]]] = {}
        for (
            memory_id,
            user_id,
            memory_type,
            path,
            content,
            updated_at,
            created_at,
        ) in conn.execute(
            """
            SELECT id, user_id, type, path, content, updated_at, created_at
            FROM memory
            ORDER BY user_id, id
            """
        ):
            if not isinstance(memory_id, str) or not memory_id:
                raise RuntimeError("memory row has no valid ID")
            if not isinstance(user_id, str) or not user_id:
                raise RuntimeError(f"memory {memory_id} has no valid user ID")
            if not isinstance(content, str) or not content.strip():
                raise RuntimeError(f"memory {memory_id} has no usable content")
            memories.setdefault(user_id, []).append(
                {
                    "id": memory_id,
                    "type": (
                        memory_type
                        if memory_type in {"user", "context"}
                        else "context"
                    ),
                    "path": path if isinstance(path, str) and path else None,
                    "content": content,
                    "updated_at": int(updated_at),
                    "created_at": int(created_at),
                }
            )
        return memories
    finally:
        conn.close()


def _memory_vector_text(memory: dict[str, Any]) -> str:
    path = memory.get("path")
    return f"{path}\n{memory['content']}" if path else memory["content"]


def _memory_metadata(memory: dict[str, Any]) -> dict[str, Any]:
    metadata = {
        "created_at": memory["created_at"],
        "updated_at": memory["updated_at"],
        "type": memory["type"],
    }
    if memory.get("path") is not None:
        metadata["path"] = memory["path"]
    return metadata


def _persistent_vector_client(vector_dir: Path):
    """Return Open WebUI's configured Chroma client for the expected path."""

    from open_webui.retrieval.vector.factory import VECTOR_DB_CLIENT

    client = getattr(VECTOR_DB_CLIENT, "client", None)
    if client is None or not hasattr(client, "get_settings"):
        raise RuntimeError("embedding migration requires Open WebUI's Chroma client")
    configured_path = Path(client.get_settings().persist_directory).resolve()
    if configured_path != vector_dir.resolve():
        raise RuntimeError(
            f"configured Chroma path is {configured_path}, expected {vector_dir}"
        )
    return client


def _generate_memory_embeddings(
    db_path: Path,
    memories: dict[str, list[dict[str, Any]]],
) -> dict[str, list[list[float]]]:
    """Use the exact embedding helper and configuration used by Open WebUI."""

    if not memories:
        return {}

    conn = sqlite3.connect(db_path)
    try:
        engine = _config_get(conn, "rag.embedding_engine")
        model = _config_get(conn, "rag.embedding_model")
        url = _config_get(conn, "rag.openai.api_base_url")
        key = _config_get(conn, "rag.openai.api_key")
        batch_size = _config_get(conn, "rag.embedding_batch_size")
        enable_async = _config_get(conn, "rag.enable_async_embedding")
        concurrent_requests = _config_get(
            conn, "rag.embedding_concurrent_requests"
        )
    finally:
        conn.close()

    if engine != "openai" or model != TARGET_MODEL:
        raise RuntimeError("target OpenRouter embedding configuration is unavailable")
    if not isinstance(url, str) or not url:
        raise RuntimeError("embedding API URL is unavailable")
    if not isinstance(key, str) or not key:
        raise RuntimeError("embedding API key is unavailable")

    from open_webui.retrieval.utils import get_embedding_function

    embedding_function = get_embedding_function(
        engine,
        model,
        embedding_function=None,
        url=url,
        key=key,
        embedding_batch_size=int(batch_size or 1),
        enable_async=bool(enable_async),
        concurrent_requests=int(concurrent_requests or 0),
    )
    prefix = os.getenv("RAG_EMBEDDING_CONTENT_PREFIX")
    generated: dict[str, list[list[float]]] = {}
    for user_id, rows in memories.items():
        vectors = asyncio.run(
            embedding_function(
                [_memory_vector_text(row) for row in rows],
                prefix=prefix,
                user=None,
            )
        )
        if not isinstance(vectors, list) or len(vectors) != len(rows):
            raise RuntimeError(
                f"embedding response count is incomplete for memory owner {user_id}"
            )
        for vector in vectors:
            if not isinstance(vector, list) or len(vector) != TARGET_DIMENSIONS:
                dimensions = len(vector) if isinstance(vector, list) else "invalid"
                raise RuntimeError(
                    f"memory embedding response has {dimensions} dimensions"
                )
        generated[user_id] = vectors
    return generated


def _rebuild_memory_collections(
    vector_dir: Path,
    memories: dict[str, list[dict[str, Any]]],
    vectors: dict[str, list[list[float]]],
) -> None:
    """Replace derived memory indexes only after every new vector exists."""

    from open_webui.retrieval.vector.utils import process_metadata

    client = _persistent_vector_client(vector_dir)
    existing = [
        collection.name if hasattr(collection, "name") else str(collection)
        for collection in client.list_collections()
    ]
    for collection_name in existing:
        if collection_name.startswith("user-memory-"):
            client.delete_collection(collection_name)

    for user_id, rows in memories.items():
        user_vectors = vectors.get(user_id)
        if user_vectors is None or len(user_vectors) != len(rows):
            raise RuntimeError(
                f"generated vectors are incomplete for memory owner {user_id}"
            )
        collection = client.get_or_create_collection(
            name=f"user-memory-{user_id}",
            metadata={"hnsw:space": "cosine"},
        )
        collection.upsert(
            ids=[row["id"] for row in rows],
            documents=[_memory_vector_text(row) for row in rows],
            embeddings=user_vectors,
            metadatas=[process_metadata(_memory_metadata(row)) for row in rows],
        )


def _validate_vectors(
    vector_dir: Path,
    expected_collections: dict[str, set[str]],
) -> None:
    client = _persistent_vector_client(vector_dir)
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


def _validate_memory_vectors(
    vector_dir: Path,
    memories: dict[str, list[dict[str, Any]]],
) -> None:
    client = _persistent_vector_client(vector_dir)
    observed_collections = {
        collection.name if hasattr(collection, "name") else str(collection)
        for collection in client.list_collections()
        if (
            collection.name if hasattr(collection, "name") else str(collection)
        ).startswith("user-memory-")
    }
    expected_collections = {
        f"user-memory-{user_id}" for user_id, rows in memories.items() if rows
    }
    if observed_collections != expected_collections:
        missing = sorted(expected_collections - observed_collections)
        stale = sorted(observed_collections - expected_collections)
        raise RuntimeError(
            f"memory collections do not match SQLite; missing={missing}, stale={stale}"
        )

    for user_id, rows in memories.items():
        if not rows:
            continue
        collection_name = f"user-memory-{user_id}"
        result = client.get_collection(collection_name).get(
            include=["documents", "embeddings", "metadatas"]
        )
        ids = result.get("ids") or []
        documents = result.get("documents") or []
        embeddings = result.get("embeddings")
        metadatas = result.get("metadatas") or []
        if embeddings is None:
            raise RuntimeError(f"{collection_name} has no embeddings")
        if not (
            len(ids)
            == len(documents)
            == len(embeddings)
            == len(metadatas)
            == len(rows)
        ):
            raise RuntimeError(f"{collection_name} has incomplete records")

        expected = {row["id"]: row for row in rows}
        if set(ids) != set(expected):
            raise RuntimeError(f"{collection_name} has unexpected memory IDs")
        for memory_id, document, embedding, metadata in zip(
            ids,
            documents,
            embeddings,
            metadatas,
            strict=True,
        ):
            row = expected[memory_id]
            if document != _memory_vector_text(row):
                raise RuntimeError(
                    f"{collection_name} has stale memory document {memory_id}"
                )
            if len(embedding) != TARGET_DIMENSIONS:
                raise RuntimeError(
                    f"{collection_name} has {len(embedding)} dimensions"
                )
            if metadata != _memory_metadata(row):
                raise RuntimeError(
                    f"{collection_name} has stale memory metadata {memory_id}"
                )


def migrate(db_path: Path, data_dir: Path, port: int) -> dict[str, Any]:
    data_dir = data_dir.resolve(strict=True)
    db_path = db_path.resolve(strict=True)
    vector_dir = data_dir / "vector_db"
    backup_root = data_dir / "remediation-backups"
    vector_backup = backup_root / f"vector-db-pre-gemini-v{POLICY_VERSION}"
    memory_vector_backup = (
        backup_root / f"vector-db-pre-gemini-memory-v{POLICY_VERSION}"
    )
    database_backup = backup_root / f"webui-pre-security-policy-v{POLICY_VERSION}.db"

    conn = sqlite3.connect(db_path)
    try:
        selected_model = _config_get(conn, "rag.embedding_model")
        completed_model = _config_get(conn, MARKER_KEY)
        completed_memory_model = _config_get(conn, MEMORY_MARKER_KEY)
    finally:
        conn.close()
    if (
        completed_model == TARGET_MODEL
        and completed_memory_model == TARGET_MODEL
    ):
        return {"status": "already-complete", "model": TARGET_MODEL}
    if selected_model != TARGET_MODEL:
        return {
            "status": "not-selected",
            "selected_model": selected_model,
            "target_model": TARGET_MODEL,
        }
    backup_root.mkdir(mode=0o700, exist_ok=True)
    backup_root.chmod(0o700)
    full_migration = completed_model != TARGET_MODEL
    active_vector_backup = vector_backup if full_migration else memory_vector_backup
    if full_migration:
        if not database_backup.is_file() or database_backup.stat().st_size == 0:
            raise RuntimeError(
                f"policy database backup is unavailable: {database_backup}"
            )

    _copy_vector_backup(vector_dir, active_vector_backup, data_dir)
    admin_id, files, knowledge = _admin_files_and_knowledge(db_path)
    memories = _memories_by_user(db_path)
    migrated: list[str] = []

    if full_migration:
        from open_webui.utils.auth import create_token

        token = create_token({"id": admin_id}, expires_delta=timedelta(hours=2))
        base_url = f"http://127.0.0.1:{port}"
        # The temporary server must not claim any due personal automation while
        # it is running only to rebuild vectors. Restore the exact prior
        # ConfigVar row before the normal server is allowed to start.
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
                _restore_vectors(vector_dir, active_vector_backup, data_dir)
                _restore_rag_config(
                    db_path, database_backup, type(error).__name__
                )
                return {
                    "status": "rolled-back",
                    "model": TARGET_MODEL,
                    "error_type": type(error).__name__,
                }
            finally:
                _stop(process)
    else:
        migrated = [file_id for file_id, _ in files]

    try:
        memory_vectors = _generate_memory_embeddings(db_path, memories)
        _rebuild_memory_collections(vector_dir, memories, memory_vectors)
        expected_collections = {
            f"file-{file_id}": {file_id}
            for file_id in migrated
        }
        expected_collections.update(knowledge)
        _validate_vectors(vector_dir, expected_collections)
        _validate_memory_vectors(vector_dir, memories)
    except Exception as error:
        _restore_vectors(vector_dir, active_vector_backup, data_dir)
        if full_migration:
            _restore_rag_config(db_path, database_backup, type(error).__name__)
            status = "rolled-back"
        else:
            _record_memory_state(
                db_path,
                "rolled_back",
                error_type=type(error).__name__,
            )
            status = "memory-rolled-back"
        return {
            "status": status,
            "model": TARGET_MODEL,
            "error_type": type(error).__name__,
        }

    try:
        conn = sqlite3.connect(db_path)
        try:
            conn.execute("BEGIN IMMEDIATE")
            if full_migration:
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
            _config_set(conn, MEMORY_MARKER_KEY, TARGET_MODEL)
            _config_set(
                conn,
                MEMORY_STATE_KEY,
                {
                    "state": "complete",
                    "policy_version": POLICY_VERSION,
                    "memories": sum(len(rows) for rows in memories.values()),
                    "user_collections": len(memories),
                    "dimensions": TARGET_DIMENSIONS,
                },
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    except Exception as error:
        _restore_vectors(vector_dir, active_vector_backup, data_dir)
        if full_migration:
            _restore_rag_config(db_path, database_backup, type(error).__name__)
            status = "rolled-back"
        else:
            _record_memory_state(
                db_path,
                "rolled_back",
                error_type=type(error).__name__,
            )
            status = "memory-rolled-back"
        return {
            "status": status,
            "model": TARGET_MODEL,
            "error_type": type(error).__name__,
        }
    return {
        "status": "complete" if full_migration else "memory-complete",
        "model": TARGET_MODEL,
        "files": len(migrated),
        "knowledge_collections": len(knowledge),
        "memories": sum(len(rows) for rows in memories.values()),
        "user_collections": len(memories),
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
