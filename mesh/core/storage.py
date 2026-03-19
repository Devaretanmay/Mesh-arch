"""
MeshStorage — High-performance SQLite-backed graph storage.

Optimizations:
- Batch operations with transactions
- Efficient indexes for fast queries
- Memory-mapped I/O
- Incremental updates support
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from mesh.core.graph import MeshGraph


@dataclass
class StorageConfig:
    db_path: Path
    code_base_root: Path

    @classmethod
    def from_root(cls, root: Path) -> "StorageConfig":
        mesh_dir = root / ".mesh"
        mesh_dir.mkdir(parents=True, exist_ok=True)
        return cls(db_path=mesh_dir / "mesh.db", code_base_root=root)


class MeshStorage:
    """
    High-performance SQLite-backed graph storage.
    
    Schema:
      nodes(id TEXT, type TEXT, file_path TEXT, data JSON)
      edges(from_id TEXT, to_id TEXT, type TEXT, data JSON)
      metadata(key TEXT, value TEXT)
      violations(id TEXT, kind TEXT, severity TEXT, file_path TEXT, data JSON, created_at TEXT)
      file_hashes(path TEXT PRIMARY KEY, hash TEXT, mtime REAL, size INTEGER)
    """

    def __init__(self, codebase_root: Path, batch_size: int = 1000):
        self._config = StorageConfig.from_root(codebase_root)
        self._conn: sqlite3.Connection | None = None
        self._batch_size = batch_size
        self._node_batch: list[tuple] = []
        self._edge_batch: list[tuple] = []
        self._ensure_schema()

    @property
    def mesh_dir(self) -> Path:
        return self._config.code_base_root / ".mesh"

    @property
    def db_path(self) -> Path:
        return self._config.db_path

    def _ensure_schema(self) -> None:
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS nodes (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                file_path TEXT,
                data JSON,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS edges (
                from_id TEXT NOT NULL,
                to_id TEXT NOT NULL,
                type TEXT NOT NULL,
                data JSON,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (from_id, to_id, type)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS violations (
                id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                severity TEXT,
                file_path TEXT,
                data JSON,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS analysis_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT DEFAULT CURRENT_TIMESTAMP,
                completed_at TEXT,
                files_analyzed INTEGER,
                functions_found INTEGER,
                edges_created INTEGER,
                errors TEXT,
                status TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS file_hashes (
                path TEXT PRIMARY KEY,
                hash TEXT NOT NULL,
                mtime REAL,
                size INTEGER
            )
        """)

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_nodes_file ON nodes(file_path)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_edges_type ON edges(type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_edges_from ON edges(from_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_edges_to ON edges(to_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_violations_kind ON violations(kind)")

        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=-64000")
        conn.execute("PRAGMA temp_store=MEMORY")

        conn.commit()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self._config.db_path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def clear(self) -> None:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM edges")
        cursor.execute("DELETE FROM nodes")
        cursor.execute("DELETE FROM violations")
        cursor.execute("DELETE FROM metadata")
        cursor.execute("DELETE FROM file_hashes")
        conn.commit()
        conn.execute("VACUUM")

    def clear_by_type(self, node_type: str) -> None:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM edges WHERE from_id IN (SELECT id FROM nodes WHERE type = ?)", (node_type,))
        cursor.execute("DELETE FROM nodes WHERE type = ?", (node_type,))
        conn.commit()

    def upsert_node(self, node_id: str, node_type: str, file_path: str, data: dict) -> None:
        self._node_batch.append((node_id, node_type, file_path, json.dumps(data)))
        if len(self._node_batch) >= self._batch_size:
            self._flush_nodes()

    def upsert_edge(self, from_id: str, to_id: str, edge_type: str, data: dict) -> None:
        self._edge_batch.append((from_id, to_id, edge_type, json.dumps(data)))
        if len(self._edge_batch) >= self._batch_size:
            self._flush_edges()

    def _flush_nodes(self) -> None:
        if not self._node_batch:
            return
        conn = self._get_conn()
        conn.executemany(
            """INSERT INTO nodes (id, type, file_path, data) VALUES (?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET type=excluded.type, file_path=excluded.file_path, data=excluded.data""",
            self._node_batch
        )
        conn.commit()
        self._node_batch.clear()

    def _flush_edges(self) -> None:
        if not self._edge_batch:
            return
        conn = self._get_conn()
        conn.executemany(
            """INSERT INTO edges (from_id, to_id, type, data) VALUES (?, ?, ?, ?)
               ON CONFLICT(from_id, to_id, type) DO UPDATE SET data=excluded.data""",
            self._edge_batch
        )
        conn.commit()
        self._edge_batch.clear()

    def flush(self) -> None:
        self._flush_nodes()
        self._flush_edges()

    def begin_transaction(self) -> None:
        self._get_conn().execute("BEGIN TRANSACTION")

    def commit_transaction(self) -> None:
        self.flush()
        self._get_conn().commit()

    def rollback_transaction(self) -> None:
        self._get_conn().rollback()
        self._node_batch.clear()
        self._edge_batch.clear()

    def upsert_node_batch(self, nodes: list[tuple[str, str, str, dict]]) -> None:
        conn = self._get_conn()
        data = [(nid, ntype, fp, json.dumps(d)) for nid, ntype, fp, d in nodes]
        conn.executemany(
            """INSERT INTO nodes (id, type, file_path, data) VALUES (?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET type=excluded.type, file_path=excluded.file_path, data=excluded.data""",
            data
        )
        conn.commit()

    def upsert_edge_batch(self, edges: list[tuple[str, str, str, dict]]) -> None:
        if not edges:
            return
        conn = self._get_conn()
        data = [(fid, tid, etype, json.dumps(d)) for fid, tid, etype, d in edges]
        conn.executemany(
            """INSERT INTO edges (from_id, to_id, type, data) VALUES (?, ?, ?, ?)
               ON CONFLICT(from_id, to_id, type) DO UPDATE SET data=excluded.data""",
            data
        )
        conn.commit()

    def set_metadata(self, key: str, value: str) -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO metadata (key, value) VALUES (?, ?)
               ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP""",
            (key, value)
        )
        conn.commit()

    def get_metadata(self, key: str) -> str | None:
        conn = self._get_conn()
        cursor = conn.execute("SELECT value FROM metadata WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row["value"] if row else None

    def get_all_metadata(self) -> dict[str, str]:
        conn = self._get_conn()
        cursor = conn.execute("SELECT key, value FROM metadata")
        return {row["key"]: row["value"] for row in cursor}

    def record_violation(self, violation_id: str, kind: str, severity: str, file_path: str, data: dict) -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO violations (id, kind, severity, file_path, data) VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET kind=excluded.kind, severity=excluded.severity, file_path=excluded.file_path, data=excluded.data""",
            (violation_id, kind, severity, file_path, json.dumps(data))
        )
        conn.commit()

    def get_violations(self, since: datetime | None = None, kind: str | None = None) -> list[dict]:
        conn = self._get_conn()
        query = "SELECT * FROM violations"
        params = []
        conditions = []
        
        if since:
            conditions.append("created_at >= ?")
            params.append(since.isoformat())
        if kind:
            conditions.append("kind = ?")
            params.append(kind)
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY created_at"
        
        cursor = conn.execute(query, params)
        return [
            {"id": row["id"], "kind": row["kind"], "severity": row["severity"],
             "file_path": row["file_path"], "data": json.loads(row["data"]) if row["data"] else {},
             "created_at": row["created_at"]}
            for row in cursor
        ]

    def save_file_hashes(self, hashes: list[dict]) -> None:
        conn = self._get_conn()
        data = [(h["path"], h["hash"], h.get("mtime", 0), h.get("size", 0)) for h in hashes]
        conn.executemany(
            """INSERT INTO file_hashes (path, hash, mtime, size) VALUES (?, ?, ?, ?)
               ON CONFLICT(path) DO UPDATE SET hash=excluded.hash, mtime=excluded.mtime, size=excluded.size""",
            data
        )
        conn.commit()

    def get_file_hash(self, path: str) -> str | None:
        conn = self._get_conn()
        cursor = conn.execute("SELECT hash FROM file_hashes WHERE path = ?", (path,))
        row = cursor.fetchone()
        return row["hash"] if row else None

    def get_all_file_hashes(self) -> dict[str, str]:
        conn = self._get_conn()
        cursor = conn.execute("SELECT path, hash FROM file_hashes")
        return {row["path"]: row["hash"] for row in cursor}

    def graphs_exist(self) -> bool:
        conn = self._get_conn()
        cursor = conn.execute("SELECT COUNT(*) as count FROM nodes")
        row = cursor.fetchone()
        return row["count"] > 0 if row else False

    def node_count(self, node_type: str | None = None) -> int:
        conn = self._get_conn()
        if node_type:
            cursor = conn.execute("SELECT COUNT(*) as count FROM nodes WHERE type = ?", (node_type,))
        else:
            cursor = conn.execute("SELECT COUNT(*) as count FROM nodes")
        row = cursor.fetchone()
        return row["count"] if row else 0

    def edge_count(self, edge_type: str | None = None) -> int:
        conn = self._get_conn()
        if edge_type:
            cursor = conn.execute("SELECT COUNT(*) as count FROM edges WHERE type = ?", (edge_type,))
        else:
            cursor = conn.execute("SELECT COUNT(*) as count FROM edges")
        row = cursor.fetchone()
        return row["count"] if row else 0

    def get_nodes(self, node_type: str | None = None, file_path: str | None = None) -> list[dict]:
        conn = self._get_conn()
        query = "SELECT * FROM nodes"
        params = []
        conditions = []
        
        if node_type:
            conditions.append("type = ?")
            params.append(node_type)
        if file_path:
            conditions.append("file_path LIKE ?")
            params.append(f"%{file_path}%")
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        cursor = conn.execute(query, params)
        return [
            {"id": row["id"], "type": row["type"], "file_path": row["file_path"],
             "data": json.loads(row["data"]) if row["data"] else {}}
            for row in cursor
        ]

    def get_edges(self, edge_type: str | None = None, from_id: str | None = None) -> list[dict]:
        conn = self._get_conn()
        query = "SELECT * FROM edges"
        params = []
        conditions = []
        
        if edge_type:
            conditions.append("type = ?")
            params.append(edge_type)
        if from_id:
            conditions.append("from_id = ?")
            params.append(from_id)
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        cursor = conn.execute(query, params)
        return [
            {"from_id": row["from_id"], "to_id": row["to_id"], "type": row["type"],
             "data": json.loads(row["data"]) if row["data"] else {}}
            for row in cursor
        ]

    def iter_nodes(self, node_type: str | None = None, batch_size: int = 1000) -> Iterator[dict]:
        conn = self._get_conn()
        query = "SELECT * FROM nodes"
        params = []
        
        if node_type:
            query += " WHERE type = ?"
            params.append(node_type)
        
        cursor = conn.execute(query, params)
        while True:
            rows = cursor.fetchmany(batch_size)
            if not rows:
                break
            for row in rows:
                yield {"id": row["id"], "type": row["type"], "file_path": row["file_path"],
                       "data": json.loads(row["data"]) if row["data"] else {}}

    def load_call_graph(self) -> MeshGraph:
        graph = MeshGraph("call")
        for node in self.iter_nodes("call"):
            node_id = node["id"]
            if node_id.startswith("call:"):
                node_id = node_id[5:]
            graph.add_node(node_id, node["data"])

        for edge in self.get_edges():
            from_id = edge["from_id"]
            to_id = edge["to_id"]
            if from_id.startswith("call:"):
                from_id = from_id[5:]
            if to_id.startswith("call:"):
                to_id = to_id[5:]
            graph.add_edge(from_id, to_id, edge.get("data", {}))

        return graph

    def load_data_flow_graph(self) -> MeshGraph:
        graph = MeshGraph("dataflow")
        for node in self.iter_nodes("dataflow"):
            node_id = node["id"]
            if node_id.startswith("dataflow:"):
                node_id = node_id[9:]
            graph.add_node(node_id, node["data"])

        for edge in self.get_edges("dataflow"):
            from_id = edge["from_id"]
            to_id = edge["to_id"]
            if from_id.startswith("dataflow:"):
                from_id = from_id[9:]
            if to_id.startswith("dataflow:"):
                to_id = to_id[9:]
            graph.add_edge(from_id, to_id, edge.get("data", {}))

        return graph

    def load_type_deps_graph(self) -> MeshGraph:
        graph = MeshGraph("type")
        for node in self.iter_nodes("type"):
            node_id = node["id"]
            if node_id.startswith("type:"):
                node_id = node_id[5:]
            graph.add_node(node_id, node["data"])

        for edge in self.get_edges("type"):
            from_id = edge["from_id"]
            to_id = edge["to_id"]
            if from_id.startswith("type:"):
                from_id = from_id[5:]
            if to_id.startswith("type:"):
                to_id = to_id[5:]
            graph.add_edge(from_id, to_id, edge.get("data", {}))

        return graph

    def close(self) -> None:
        self.flush()
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "MeshStorage":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if exc_type:
            self.rollback_transaction()
        else:
            self.commit_transaction()
        self.close()
