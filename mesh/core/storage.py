"""
MeshStorage — High-performance SQLite-backed graph storage.

Multi-repo support:
- Layer 1: Complete context (all repos in one graph)
- Layer 2: Repo relationships (summary)
- Layer 3: Per-repo details

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
from typing import Any, Iterator, Optional

from mesh.core.graph import MeshGraph


@dataclass
class StorageConfig:
    db_path: Path
    code_base_root: Path

    @classmethod
    def from_root(cls, root: Path) -> "StorageConfig":
        mesh_dir = root / ".mesh"
        mesh_dir.mkdir(parents=True, exist_ok=True)
        db_dir = mesh_dir / "db"
        db_dir.mkdir(parents=True, exist_ok=True)
        return cls(db_path=db_dir / "mesh.db", code_base_root=root)


@dataclass
class Repo:
    id: str
    name: str
    path: str
    type: str  # 'git' or 'submodule'
    last_analyzed: Optional[str] = None


class MeshStorage:
    """
    High-performance SQLite-backed graph storage.
    
    Schema:
      repos(id, name, path, type, last_analyzed)
      nodes(id, repo_id, type, file_path, data)
      edges(from_id, to_id, from_repo, to_repo, type, data)
      repo_relationships(source_repo, target_repo, relationship_type, count)
      repo_details(repo_id, functions, classes, violations, metrics)
      metadata(key, value)
      violations(id, kind, severity, file_path, repo_id, data, created_at)
      file_hashes(path, repo_id, hash, mtime, size)
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
            CREATE TABLE IF NOT EXISTS repos (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                path TEXT NOT NULL,
                type TEXT NOT NULL DEFAULT 'git',
                last_analyzed TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS nodes (
                id TEXT NOT NULL,
                repo_id TEXT NOT NULL,
                type TEXT NOT NULL,
                file_path TEXT,
                data JSON,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (id, repo_id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS edges (
                from_id TEXT NOT NULL,
                to_id TEXT NOT NULL,
                from_repo TEXT NOT NULL,
                to_repo TEXT NOT NULL,
                type TEXT NOT NULL,
                data JSON,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (from_id, to_id, from_repo, to_repo, type)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS repo_relationships (
                source_repo TEXT NOT NULL,
                target_repo TEXT NOT NULL,
                relationship_type TEXT NOT NULL,
                count INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (source_repo, target_repo, relationship_type)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS repo_details (
                repo_id TEXT PRIMARY KEY,
                functions JSON,
                classes JSON,
                violations JSON,
                metrics JSON,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
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
                repo_id TEXT,
                data JSON,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS analysis_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                repo_id TEXT,
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
                path TEXT NOT NULL,
                repo_id TEXT NOT NULL,
                hash TEXT NOT NULL,
                mtime REAL,
                size INTEGER,
                PRIMARY KEY (path, repo_id)
            )
        """)

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_nodes_file ON nodes(file_path)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_nodes_repo ON nodes(repo_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_edges_type ON edges(type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_edges_from ON edges(from_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_edges_to ON edges(to_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_edges_from_repo ON edges(from_repo)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_edges_to_repo ON edges(to_repo)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_violations_kind ON violations(kind)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_violations_repo ON violations(repo_id)")

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

    def clear(self, repo_id: str | None = None) -> None:
        conn = self._get_conn()
        cursor = conn.cursor()
        
        if repo_id:
            cursor.execute("DELETE FROM edges WHERE from_repo = ? OR to_repo = ?", (repo_id, repo_id))
            cursor.execute("DELETE FROM nodes WHERE repo_id = ?", (repo_id,))
            cursor.execute("DELETE FROM violations WHERE repo_id = ?", (repo_id,))
            cursor.execute("DELETE FROM file_hashes WHERE repo_id = ?", (repo_id,))
            cursor.execute("DELETE FROM repo_details WHERE repo_id = ?", (repo_id,))
        else:
            cursor.execute("DELETE FROM edges")
            cursor.execute("DELETE FROM nodes")
            cursor.execute("DELETE FROM violations")
            cursor.execute("DELETE FROM file_hashes")
            cursor.execute("DELETE FROM repo_details")
        
        conn.commit()

    def clear_by_type(self, node_type: str, repo_id: str | None = None) -> None:
        conn = self._get_conn()
        if repo_id:
            cursor.execute(
                "DELETE FROM edges WHERE from_id IN (SELECT id FROM nodes WHERE type = ? AND repo_id = ?)",
                (node_type, repo_id)
            )
            cursor.execute("DELETE FROM nodes WHERE type = ? AND repo_id = ?", (node_type, repo_id))
        else:
            cursor.execute(
                "DELETE FROM edges WHERE from_id IN (SELECT id FROM nodes WHERE type = ?)",
                (node_type,)
            )
            cursor.execute("DELETE FROM nodes WHERE type = ?", (node_type,))
        conn.commit()

    def upsert_node(self, node_id: str, node_type: str, file_path: str, data: dict, repo_id: str) -> None:
        self._node_batch.append((node_id, repo_id, node_type, file_path, json.dumps(data)))
        if len(self._node_batch) >= self._batch_size:
            self._flush_nodes()

    def upsert_edge(self, from_id: str, to_id: str, edge_type: str, data: dict, from_repo: str, to_repo: str) -> None:
        self._edge_batch.append((from_id, to_id, from_repo, to_repo, edge_type, json.dumps(data)))
        if len(self._edge_batch) >= self._batch_size:
            self._flush_edges()

    def _flush_nodes(self) -> None:
        if not self._node_batch:
            return
        conn = self._get_conn()
        conn.executemany(
            """INSERT INTO nodes (id, repo_id, type, file_path, data) VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(id, repo_id) DO UPDATE SET type=excluded.type, file_path=excluded.file_path, data=excluded.data""",
            self._node_batch
        )
        conn.commit()
        self._node_batch.clear()

    def _flush_edges(self) -> None:
        if not self._edge_batch:
            return
        conn = self._get_conn()
        conn.executemany(
            """INSERT INTO edges (from_id, to_id, from_repo, to_repo, type, data) VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(from_id, to_id, from_repo, to_repo, type) DO UPDATE SET data=excluded.data""",
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

    def upsert_node_batch(self, nodes: list[tuple[str, str, str, dict]], repo_id: str) -> None:
        conn = self._get_conn()
        data = [(nid, repo_id, ntype, fp, json.dumps(d)) for nid, ntype, fp, d in nodes]
        conn.executemany(
            """INSERT INTO nodes (id, repo_id, type, file_path, data) VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(id, repo_id) DO UPDATE SET type=excluded.type, file_path=excluded.file_path, data=excluded.data""",
            data
        )
        conn.commit()

    def upsert_edge_batch(self, edges: list[tuple[str, str, str, dict]], from_repo: str, to_repo: str) -> None:
        if not edges:
            return
        conn = self._get_conn()
        data = [(fid, tid, from_repo, to_repo, etype, json.dumps(d)) for fid, tid, etype, d in edges]
        conn.executemany(
            """INSERT INTO edges (from_id, to_id, from_repo, to_repo, type, data) VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(from_id, to_id, from_repo, to_repo, type) DO UPDATE SET data=excluded.data""",
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

    def record_violation(self, violation_id: str, kind: str, severity: str, file_path: str, data: dict, repo_id: str | None = None) -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO violations (id, kind, severity, file_path, repo_id, data) VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET kind=excluded.kind, severity=excluded.severity, file_path=excluded.file_path, repo_id=excluded.repo_id, data=excluded.data""",
            (violation_id, kind, severity, file_path, repo_id, json.dumps(data))
        )
        conn.commit()

    def get_violations(self, since: datetime | None = None, kind: str | None = None, repo_id: str | None = None) -> list[dict]:
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
        if repo_id:
            conditions.append("repo_id = ?")
            params.append(repo_id)
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY created_at"
        
        cursor = conn.execute(query, params)
        return [
            {"id": row["id"], "kind": row["kind"], "severity": row["severity"],
             "file_path": row["file_path"], "repo_id": row["repo_id"],
             "data": json.loads(row["data"]) if row["data"] else {},
             "created_at": row["created_at"]}
            for row in cursor
        ]

    def save_file_hashes(self, hashes: list[dict], repo_id: str) -> None:
        conn = self._get_conn()
        data = [(h["path"], repo_id, h["hash"], h.get("mtime", 0), h.get("size", 0)) for h in hashes]
        conn.executemany(
            """INSERT INTO file_hashes (path, repo_id, hash, mtime, size) VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(path, repo_id) DO UPDATE SET hash=excluded.hash, mtime=excluded.mtime, size=excluded.size""",
            data
        )
        conn.commit()

    def get_file_hash(self, path: str, repo_id: str) -> str | None:
        conn = self._get_conn()
        cursor = conn.execute("SELECT hash FROM file_hashes WHERE path = ? AND repo_id = ?", (path, repo_id))
        row = cursor.fetchone()
        return row["hash"] if row else None

    def get_all_file_hashes(self, repo_id: str | None = None) -> dict[str, str]:
        conn = self._get_conn()
        if repo_id:
            cursor = conn.execute("SELECT path, hash FROM file_hashes WHERE repo_id = ?", (repo_id,))
        else:
            cursor = conn.execute("SELECT path, hash FROM file_hashes")
        return {row["path"]: row["hash"] for row in cursor}

    def graphs_exist(self, repo_id: str | None = None) -> bool:
        conn = self._get_conn()
        if repo_id:
            cursor = conn.execute("SELECT COUNT(*) as count FROM nodes WHERE repo_id = ?", (repo_id,))
        else:
            cursor = conn.execute("SELECT COUNT(*) as count FROM nodes")
        row = cursor.fetchone()
        return row["count"] > 0 if row else False

    def node_count(self, node_type: str | None = None, repo_id: str | None = None) -> int:
        conn = self._get_conn()
        if node_type and repo_id:
            cursor = conn.execute("SELECT COUNT(*) as count FROM nodes WHERE type = ? AND repo_id = ?", (node_type, repo_id))
        elif node_type:
            cursor = conn.execute("SELECT COUNT(*) as count FROM nodes WHERE type = ?", (node_type,))
        elif repo_id:
            cursor = conn.execute("SELECT COUNT(*) as count FROM nodes WHERE repo_id = ?", (repo_id,))
        else:
            cursor = conn.execute("SELECT COUNT(*) as count FROM nodes")
        row = cursor.fetchone()
        return row["count"] if row else 0

    def edge_count(self, edge_type: str | None = None, repo_id: str | None = None) -> int:
        conn = self._get_conn()
        if edge_type and repo_id:
            cursor = conn.execute("SELECT COUNT(*) as count FROM edges WHERE type = ? AND (from_repo = ? OR to_repo = ?)", (edge_type, repo_id, repo_id))
        elif edge_type:
            cursor = conn.execute("SELECT COUNT(*) as count FROM edges WHERE type = ?", (edge_type,))
        elif repo_id:
            cursor = conn.execute("SELECT COUNT(*) as count FROM edges WHERE from_repo = ? OR to_repo = ?", (repo_id, repo_id))
        else:
            cursor = conn.execute("SELECT COUNT(*) as count FROM edges")
        row = cursor.fetchone()
        return row["count"] if row else 0

    def get_nodes(self, node_type: str | None = None, file_path: str | None = None, repo_id: str | None = None) -> list[dict]:
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
        if repo_id:
            conditions.append("repo_id = ?")
            params.append(repo_id)
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        cursor = conn.execute(query, params)
        return [
            {"id": row["id"], "repo_id": row["repo_id"], "type": row["type"], "file_path": row["file_path"],
             "data": json.loads(row["data"]) if row["data"] else {}}
            for row in cursor
        ]

    def get_edges(self, edge_type: str | None = None, from_id: str | None = None, repo_id: str | None = None) -> list[dict]:
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
        if repo_id:
            conditions.append("(from_repo = ? OR to_repo = ?)")
            params.append(repo_id)
            params.append(repo_id)
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        cursor = conn.execute(query, params)
        return [
            {"from_id": row["from_id"], "to_id": row["to_id"], "from_repo": row["from_repo"],
             "to_repo": row["to_repo"], "type": row["type"],
             "data": json.loads(row["data"]) if row["data"] else {}}
            for row in cursor
        ]

    def iter_nodes(self, node_type: str | None = None, repo_id: str | None = None, batch_size: int = 1000) -> Iterator[dict]:
        conn = self._get_conn()
        query = "SELECT * FROM nodes"
        params = []
        
        conditions = []
        if node_type:
            conditions.append("type = ?")
            params.append(node_type)
        if repo_id:
            conditions.append("repo_id = ?")
            params.append(repo_id)
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        cursor = conn.execute(query, params)
        while True:
            rows = cursor.fetchmany(batch_size)
            if not rows:
                break
            for row in rows:
                yield {"id": row["id"], "repo_id": row["repo_id"], "type": row["type"], "file_path": row["file_path"],
                       "data": json.loads(row["data"]) if row["data"] else {}}

    def load_call_graph(self, repo_id: str | None = None) -> MeshGraph:
        graph = MeshGraph("call")
        for node in self.iter_nodes("call", repo_id):
            node_id = node["id"]
            if node_id.startswith("call:"):
                node_id = node_id[5:]
            node["data"]["repo_id"] = node["repo_id"]
            graph.add_node(node_id, node["data"])

        for edge in self.get_edges("call", repo_id=repo_id):
            from_id = edge["from_id"]
            to_id = edge["to_id"]
            if from_id.startswith("call:"):
                from_id = from_id[5:]
            if to_id.startswith("call:"):
                to_id = to_id[5:]
            graph.add_edge(from_id, to_id, edge.get("data", {}))

        return graph

    def load_data_flow_graph(self, repo_id: str | None = None) -> MeshGraph:
        graph = MeshGraph("dataflow")
        for node in self.iter_nodes("dataflow", repo_id):
            node_id = node["id"]
            if node_id.startswith("dataflow:"):
                node_id = node_id[9:]
            node["data"]["repo_id"] = node["repo_id"]
            graph.add_node(node_id, node["data"])

        for edge in self.get_edges("dataflow", repo_id=repo_id):
            from_id = edge["from_id"]
            to_id = edge["to_id"]
            if from_id.startswith("dataflow:"):
                from_id = from_id[9:]
            if to_id.startswith("dataflow:"):
                to_id = to_id[9:]
            graph.add_edge(from_id, to_id, edge.get("data", {}))

        return graph

    def load_type_deps_graph(self, repo_id: str | None = None) -> MeshGraph:
        graph = MeshGraph("type")
        for node in self.iter_nodes("type", repo_id):
            node_id = node["id"]
            if node_id.startswith("type:"):
                node_id = node_id[5:]
            node["data"]["repo_id"] = node["repo_id"]
            graph.add_node(node_id, node["data"])

        for edge in self.get_edges("type", repo_id=repo_id):
            from_id = edge["from_id"]
            to_id = edge["to_id"]
            if from_id.startswith("type:"):
                from_id = from_id[5:]
            if to_id.startswith("type:"):
                to_id = to_id[5:]
            graph.add_edge(from_id, to_id, edge.get("data", {}))

        return graph

    def get_cross_repo_edges(self) -> list[dict]:
        conn = self._get_conn()
        cursor = conn.execute("""
            SELECT * FROM edges 
            WHERE from_repo != to_repo
            ORDER BY from_repo, to_repo
        """)
        return [
            {"from_id": row["from_id"], "to_id": row["to_id"], "from_repo": row["from_repo"],
             "to_repo": row["to_repo"], "type": row["type"],
             "data": json.loads(row["data"]) if row["data"] else {}}
            for row in cursor
        ]

    def save_repo(self, repo: Repo) -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO repos (id, name, path, type, last_analyzed) VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET name=excluded.name, path=excluded.path, type=excluded.type, last_analyzed=excluded.last_analyzed""",
            (repo.id, repo.name, repo.path, repo.type, repo.last_analyzed)
        )
        conn.commit()

    def get_repos(self) -> list[Repo]:
        conn = self._get_conn()
        cursor = conn.execute("SELECT * FROM repos ORDER BY name")
        return [
            Repo(id=row["id"], name=row["name"], path=row["path"], type=row["type"], last_analyzed=row["last_analyzed"])
            for row in cursor
        ]

    def get_repo(self, repo_id: str) -> Repo | None:
        conn = self._get_conn()
        cursor = conn.execute("SELECT * FROM repos WHERE id = ?", (repo_id,))
        row = cursor.fetchone()
        if row:
            return Repo(id=row["id"], name=row["name"], path=row["path"], type=row["type"], last_analyzed=row["last_analyzed"])
        return None

    def delete_repo(self, repo_id: str) -> None:
        conn = self._get_conn()
        self.clear(repo_id)
        conn.execute("DELETE FROM repos WHERE id = ?", (repo_id,))
        conn.execute("DELETE FROM repo_details WHERE repo_id = ?", (repo_id,))
        conn.commit()

    def update_repo_analysis_time(self, repo_id: str) -> None:
        conn = self._get_conn()
        conn.execute("UPDATE repos SET last_analyzed = ? WHERE id = ?", (datetime.utcnow().isoformat(), repo_id))
        conn.commit()

    def save_repo_relationships(self, relationships: list[dict]) -> None:
        conn = self._get_conn()
        data = [(r["source_repo"], r["target_repo"], r["relationship_type"], r.get("count", 0)) for r in relationships]
        conn.executemany(
            """INSERT INTO repo_relationships (source_repo, target_repo, relationship_type, count) VALUES (?, ?, ?, ?)
               ON CONFLICT(source_repo, target_repo, relationship_type) DO UPDATE SET count=excluded.count""",
            data
        )
        conn.commit()

    def get_repo_relationships(self, repo_id: str | None = None) -> list[dict]:
        conn = self._get_conn()
        if repo_id:
            cursor = conn.execute(
                """SELECT * FROM repo_relationships 
                   WHERE source_repo = ? OR target_repo = ?
                   ORDER BY source_repo, target_repo""",
                (repo_id, repo_id)
            )
        else:
            cursor = conn.execute("SELECT * FROM repo_relationships ORDER BY source_repo, target_repo")
        return [
            {"source_repo": row["source_repo"], "target_repo": row["target_repo"],
             "relationship_type": row["relationship_type"], "count": row["count"]}
            for row in cursor
        ]

    def get_repo_matrix(self) -> dict:
        conn = self._get_conn()
        cursor = conn.execute("SELECT DISTINCT source_repo, target_repo FROM repo_relationships")
        matrix = {}
        for row in cursor:
            src = row["source_repo"]
            tgt = row["target_repo"]
            if src not in matrix:
                matrix[src] = {"depends_on": [], "depended_on_by": []}
            if tgt not in matrix:
                matrix[tgt] = {"depends_on": [], "depended_on_by": []}
            matrix[src]["depends_on"].append(tgt)
            matrix[tgt]["depended_on_by"].append(src)
        return matrix

    def save_repo_detail(self, repo_id: str, functions: list, classes: list, violations: list, metrics: dict) -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO repo_details (repo_id, functions, classes, violations, metrics, updated_at) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(repo_id) DO UPDATE SET functions=excluded.functions, classes=excluded.classes, 
               violations=excluded.violations, metrics=excluded.metrics, updated_at=CURRENT_TIMESTAMP""",
            (repo_id, json.dumps(functions), json.dumps(classes), json.dumps(violations), json.dumps(metrics))
        )
        conn.commit()

    def get_repo_detail(self, repo_id: str) -> dict | None:
        conn = self._get_conn()
        cursor = conn.execute("SELECT * FROM repo_details WHERE repo_id = ?", (repo_id,))
        row = cursor.fetchone()
        if row:
            return {
                "repo_id": row["repo_id"],
                "functions": json.loads(row["functions"]) if row["functions"] else [],
                "classes": json.loads(row["classes"]) if row["classes"] else [],
                "violations": json.loads(row["violations"]) if row["violations"] else [],
                "metrics": json.loads(row["metrics"]) if row["metrics"] else {},
                "updated_at": row["updated_at"]
            }
        return None

    def get_all_repo_details(self) -> list[dict]:
        conn = self._get_conn()
        cursor = conn.execute("SELECT * FROM repo_details ORDER BY repo_id")
        results = []
        for row in cursor:
            results.append({
                "repo_id": row["repo_id"],
                "functions": json.loads(row["functions"]) if row["functions"] else [],
                "classes": json.loads(row["classes"]) if row["classes"] else [],
                "violations": json.loads(row["violations"]) if row["violations"] else [],
                "metrics": json.loads(row["metrics"]) if row["metrics"] else {},
                "updated_at": row["updated_at"]
            })
        return results

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
