"""
MeshStorage — SQLite-backed graph storage.

Replaces msgpack files with queryable SQLite database.
Enables: incremental updates, complex queries, history tracking.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from mesh.core.graph import MeshGraph


@dataclass
class StorageConfig:
    """Configuration for Mesh storage."""

    db_path: Path
    code_base_root: Path

    @classmethod
    def from_root(cls, root: Path) -> "StorageConfig":
        """Create config from codebase root."""
        mesh_dir = root / ".mesh"
        mesh_dir.mkdir(parents=True, exist_ok=True)
        return cls(
            db_path=mesh_dir / "mesh.db",
            code_base_root=root,
        )


class MeshStorage:
    """
    SQLite-backed graph storage.

    Schema:
      nodes(id TEXT, type TEXT, file_path TEXT, data JSON)
      edges(from_id TEXT, to_id TEXT, type TEXT, data JSON)
      metadata(key TEXT, value TEXT)
      violations(id TEXT, kind TEXT, severity TEXT,
                 file_path TEXT, data JSON, created_at TEXT)
    """

    def __init__(self, codebase_root: Path):
        """
        Initialize storage.

        Args:
            codebase_root: Root directory of codebase
        """
        self._config = StorageConfig.from_root(codebase_root)
        self._conn: sqlite3.Connection | None = None
        self._ensure_schema()

    @property
    def mesh_dir(self) -> Path:
        """Get .mesh directory."""
        return self._config.code_base_root / ".mesh"

    @property
    def db_path(self) -> Path:
        """Get database path."""
        return self._config.db_path

    @property
    def call_graph_path(self) -> Path:
        """Get call graph path (legacy compatibility)."""
        return self.mesh_dir / "call_graph.msgpack"

    @property
    def data_flow_path(self) -> Path:
        """Get data flow graph path (legacy compatibility)."""
        return self.mesh_dir / "data_flow.msgpack"

    @property
    def type_deps_path(self) -> Path:
        """Get type deps graph path (legacy compatibility)."""
        return self.mesh_dir / "type_deps.msgpack"

    def _ensure_schema(self) -> None:
        """Ensure database schema exists."""
        conn = self._get_conn()
        cursor = conn.cursor()

        # Nodes table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS nodes (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                file_path TEXT,
                data JSON,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Edges table
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

        # Metadata table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Violations table
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

        # Analysis runs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS analysis_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT DEFAULT CURRENT_TIMESTAMP,
                completed_at TEXT,
                files_analyzed INTEGER,
                functions_found INTEGER,
                status TEXT
            )
        """)

        conn.commit()

    def _get_conn(self) -> sqlite3.Connection:
        """Get database connection."""
        if self._conn is None:
            self._conn = sqlite3.connect(str(self._config.db_path))
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def clear(self) -> None:
        """Clear all data."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM edges")
        cursor.execute("DELETE FROM nodes")
        cursor.execute("DELETE FROM violations")
        cursor.execute("DELETE FROM metadata")
        conn.commit()

    def upsert_node(
        self, node_id: str, node_type: str, file_path: str, data: dict
    ) -> None:
        """
        Insert or update a node.

        Args:
            node_id: Unique node identifier
            node_type: Type of node (function, class, etc.)
            file_path: File containing node
            data: Node data dict
        """
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO nodes (id, type, file_path, data)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                type = excluded.type,
                file_path = excluded.file_path,
                data = excluded.data
            """,
            (node_id, node_type, file_path, json.dumps(data)),
        )
        conn.commit()

    def upsert_edge(self, from_id: str, to_id: str, edge_type: str, data: dict) -> None:
        """
        Insert or update an edge.

        Args:
            from_id: Source node ID
            to_id: Target node ID
            edge_type: Type of edge (calls, imports, etc.)
            data: Edge data dict
        """
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO edges (from_id, to_id, type, data)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(from_id, to_id, type) DO UPDATE SET
                data = excluded.data
            """,
            (from_id, to_id, edge_type, json.dumps(data)),
        )
        conn.commit()

    def get_nodes(self, node_type: str | None = None) -> list[dict]:
        """
        Get all nodes, optionally filtered by type.

        Args:
            node_type: Optional filter by type

        Returns:
            List of node dicts
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        if node_type:
            cursor.execute("SELECT * FROM nodes WHERE type = ?", (node_type,))
        else:
            cursor.execute("SELECT * FROM nodes")

        rows = cursor.fetchall()
        return [
            {
                "id": row["id"],
                "type": row["type"],
                "file_path": row["file_path"],
                "data": json.loads(row["data"]) if row["data"] else {},
            }
            for row in rows
        ]

    def get_edges(self, edge_type: str | None = None) -> list[dict]:
        """
        Get all edges, optionally filtered by type.

        Args:
            edge_type: Optional filter by type

        Returns:
            List of edge dicts
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        if edge_type:
            cursor.execute("SELECT * FROM edges WHERE type = ?", (edge_type,))
        else:
            cursor.execute("SELECT * FROM edges")

        rows = cursor.fetchall()
        return [
            {
                "from_id": row["from_id"],
                "to_id": row["to_id"],
                "type": row["type"],
                "data": json.loads(row["data"]) if row["data"] else {},
            }
            for row in rows
        ]

    def set_metadata(self, key: str, value: str) -> None:
        """Set metadata value."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO metadata (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = CURRENT_TIMESTAMP
            """,
            (key, value),
        )
        conn.commit()

    def get_metadata(self, key: str) -> str | None:
        """Get metadata value."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM metadata WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row["value"] if row else None

    def record_violation(
        self,
        violation_id: str,
        kind: str,
        severity: str,
        file_path: str,
        data: dict,
    ) -> None:
        """Record a violation."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO violations (id, kind, severity, file_path, data)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                kind = excluded.kind,
                severity = excluded.severity,
                file_path = excluded.file_path,
                data = excluded.data
            """,
            (violation_id, kind, severity, file_path, json.dumps(data)),
        )
        conn.commit()

    def get_violations(self, since: datetime | None = None) -> list[dict]:
        """Get violations, optionally since a datetime."""
        conn = self._get_conn()
        cursor = conn.cursor()

        if since:
            cursor.execute(
                "SELECT * FROM violations WHERE created_at >= ? ORDER BY created_at",
                (since.isoformat(),),
            )
        else:
            cursor.execute("SELECT * FROM violations ORDER BY created_at")

        rows = cursor.fetchall()
        return [
            {
                "id": row["id"],
                "kind": row["kind"],
                "severity": row["severity"],
                "file_path": row["file_path"],
                "data": json.loads(row["data"]) if row["data"] else {},
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def graphs_exist(self) -> bool:
        """Check if analysis has been run (has nodes)."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM nodes")
        row = cursor.fetchone()
        return row["count"] > 0 if row else False

    def node_count(self) -> int:
        """Get total node count."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM nodes")
        row = cursor.fetchone()
        return row["count"] if row else 0

    def edge_count(self) -> int:
        """Get total edge count."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM edges")
        row = cursor.fetchone()
        return row["count"] if row else 0

    def close(self) -> None:
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "MeshStorage":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.close()

    def load_call_graph(self) -> MeshGraph:
        """Load call graph from storage."""
        graph = MeshGraph("call")

        nodes = self.get_nodes("call")
        for node in nodes:
            node_id = node["id"]
            if node_id.startswith("call:"):
                node_id = node_id[5:]
            graph.add_node(node_id, node["data"])

        # Load ALL edges for call graph (includes branch, loop, exception_handler, awaits)
        edges = self.get_edges()
        for edge in edges:
            from_id = edge["from_id"]
            to_id = edge["to_id"]
            # Only include edges from call graph
            if not from_id.startswith("call:") or not to_id.startswith("call:"):
                continue
            from_id = from_id[5:]
            to_id = to_id[5:]
            graph.add_edge(from_id, to_id, edge.get("data", {}))

        return graph

    def load_data_flow_graph(self) -> MeshGraph:
        """Load data flow graph from storage."""
        graph = MeshGraph("dataflow")

        nodes = self.get_nodes("dataflow")
        for node in nodes:
            node_id = node["id"]
            if node_id.startswith("dataflow:"):
                node_id = node_id[9:]
            graph.add_node(node_id, node["data"])

        edges = self.get_edges("dataflow")
        for edge in edges:
            from_id = edge["from_id"]
            to_id = edge["to_id"]
            if from_id.startswith("dataflow:"):
                from_id = from_id[9:]
            if to_id.startswith("dataflow:"):
                to_id = to_id[9:]
            graph.add_edge(from_id, to_id, edge.get("data", {}))

        return graph

    def load_type_deps_graph(self) -> MeshGraph:
        """Load type dependency graph from storage."""
        graph = MeshGraph("typedep")

        nodes = self.get_nodes("type")
        for node in nodes:
            node_id = node["id"]
            if node_id.startswith("type:"):
                node_id = node_id[5:]
            graph.add_node(node_id, node["data"])

        edges = self.get_edges("type")
        for edge in edges:
            from_id = edge["from_id"]
            to_id = edge["to_id"]
            if from_id.startswith("type:"):
                from_id = from_id[5:]
            if to_id.startswith("type:"):
                to_id = to_id[5:]
            graph.add_edge(from_id, to_id, edge.get("data", {}))

        return graph

        return graph
