"""Tests for Mesh v2.0 core modules.

Tests:
- Core graph (rustworkx-backed)
- Parser (ast-grep-py, 26 languages)
- Storage (SQLite)
- Detection functions
- MCP server
- CLI commands
"""

import tempfile
import time
from pathlib import Path

import pytest


class TestMeshGraph:
    """Tests for rustworkx-backed MeshGraph."""

    def test_graph_creation(self):
        """Test creating a MeshGraph."""
        from mesh.core.graph import MeshGraph

        graph = MeshGraph("call")
        assert graph.graph_type == "call"
        assert graph.node_count == 0
        assert graph.edge_count == 0

    def test_add_node(self):
        """Test adding nodes to graph."""
        from mesh.core.graph import MeshGraph

        graph = MeshGraph("call")
        graph.add_node("func1", {"name": "test_func", "file_path": "test.py"})

        assert graph.node_count == 1

    def test_add_edge(self):
        """Test adding edges to graph."""
        from mesh.core.graph import MeshGraph

        graph = MeshGraph("call")
        graph.add_node("func1", {"name": "caller", "file_path": "a.py"})
        graph.add_node("func2", {"name": "callee", "file_path": "b.py"})
        graph.add_edge("func1", "func2", {"type": "calls"})

        assert graph.edge_count == 1

    def test_nodes_iterator(self):
        """Test iterating over nodes."""
        from mesh.core.graph import MeshGraph

        graph = MeshGraph("call")
        graph.add_node("func1", {"name": "func1", "file_path": "a.py"})
        graph.add_node("func2", {"name": "func2", "file_path": "b.py"})

        nodes = list(graph.nodes())
        assert len(nodes) == 2


class TestUniversalParser:
    """Tests for 26-language UniversalParser."""

    def test_parser_creation(self):
        """Test creating parser."""
        from mesh.core.parser import UniversalParser

        with tempfile.TemporaryDirectory() as tmpdir:
            parser = UniversalParser(Path(tmpdir))
            assert parser is not None

    def test_parse_python_file(self):
        """Test parsing a Python file."""
        from mesh.core.parser import UniversalParser

        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.py"
            test_file.write_text("""
def hello_world():
    '''Say hello.'''
    print("Hello, world!")

def goodbye():
    pass
""")

            parser = UniversalParser(Path(tmpdir))
            result = parser.parse_file(test_file, Path(tmpdir))

            assert len(result.functions) == 2
            names = [f.name for f in result.functions]
            assert "hello_world" in names
            assert "goodbye" in names

    def test_language_map(self):
        """Test language mapping."""
        from mesh.core.parser import LANGUAGE_MAP

        assert ".py" in LANGUAGE_MAP
        assert ".js" in LANGUAGE_MAP
        assert ".ts" in LANGUAGE_MAP
        assert ".go" in LANGUAGE_MAP
        assert ".rs" in LANGUAGE_MAP


class TestMeshStorage:
    """Tests for SQLite-backed MeshStorage."""

    def test_storage_creation(self):
        """Test creating storage."""
        from mesh.core.storage import MeshStorage

        with tempfile.TemporaryDirectory() as tmpdir:
            storage = MeshStorage(Path(tmpdir))
            assert storage is not None
            storage.close()

    def test_graphs_exist(self):
        """Test checking if graphs exist."""
        from mesh.core.storage import MeshStorage

        with tempfile.TemporaryDirectory() as tmpdir:
            storage = MeshStorage(Path(tmpdir))
            assert not storage.graphs_exist()
            storage.close()

    def test_upsert_and_get_nodes(self):
        """Test upserting and retrieving nodes."""
        from mesh.core.storage import MeshStorage

        with tempfile.TemporaryDirectory() as tmpdir:
            storage = MeshStorage(Path(tmpdir))
            storage.upsert_node(
                node_id="test_func",
                node_type="call",
                file_path="test.py",
                data={"name": "test_func", "line": 10},
                repo_id="test-repo",
            )
            storage.flush()

            nodes = storage.get_nodes("call", repo_id="test-repo")
            assert len(nodes) == 1
            assert nodes[0]["id"] == "test_func"
            assert nodes[0]["repo_id"] == "test-repo"
            storage.close()


class TestDetectionFunctions:
    """Tests for detection functions."""

    def test_detect_duplicates(self):
        """Test duplicate detection."""
        from mesh.analysis.builder import detect_duplicates
        from mesh.core.graph import MeshGraph

        graph = MeshGraph("call")
        graph.add_node("func1", {"name": "validate", "file_path": "a.py"})
        graph.add_node("func2", {"name": "validate", "file_path": "b.py"})

        dups = detect_duplicates(graph)
        assert len(dups) > 0

    def test_detect_naming_violations(self):
        """Test naming violation detection."""
        from mesh.analysis.builder import detect_naming_violations
        from mesh.core.graph import MeshGraph

        graph = MeshGraph("call")
        graph.add_node("func1", {"name": "getUserData", "file_path": "a.py"})
        graph.add_node("func2", {"name": "get_user_data", "file_path": "b.py"})

        violations = detect_naming_violations(graph)
        assert isinstance(violations, list)


class TestAnalysisBuilder:
    """Tests for AnalysisBuilder."""

    def test_builder_creation(self):
        """Test creating analysis builder."""
        from mesh.analysis.builder import AnalysisBuilder

        with tempfile.TemporaryDirectory() as tmpdir:
            builder = AnalysisBuilder(Path(tmpdir))
            assert builder is not None
            builder.close()

    def test_run_full_analysis(self):
        """Test running full analysis."""
        from mesh.analysis.builder import AnalysisBuilder

        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.py"
            test_file.write_text("""
def func_a():
    func_b()

def func_b():
    pass
""")

            builder = AnalysisBuilder(Path(tmpdir))
            result = builder.run_full_analysis()

            assert result.files_analyzed >= 1
            assert result.functions_found >= 2
            builder.close()


class TestMCPServer:
    """Tests for MCP server."""

    def test_server_creation(self):
        """Test creating MCP server."""
        from mesh.mcp.server import MCPServer

        with tempfile.TemporaryDirectory() as tmpdir:
            server = MCPServer(Path(tmpdir))
            assert server is not None

    def test_get_tools(self):
        """Test getting tool list."""
        from mesh.mcp.server import MCPServer

        with tempfile.TemporaryDirectory() as tmpdir:
            server = MCPServer(Path(tmpdir))
            tools = server.get_tools()

            assert len(tools) == 7
            tool_names = [t["name"] for t in tools]
            assert "mesh_architecture" in tool_names
            assert "mesh_check" in tool_names
            assert "mesh_locate" in tool_names
            assert "mesh_explain" in tool_names
            assert "mesh_dependencies" in tool_names
            assert "mesh_callers" in tool_names
            assert "mesh_impact" in tool_names


class TestCLICheck:
    """Tests for CLI check command."""

    def test_check_import(self):
        """Test CLI check command can be imported."""
        from mesh.cli import check

        assert check is not None


class TestPerformance:
    """Performance benchmarks."""

    def test_graph_build_performance(self):
        """Test that 10K node graph builds quickly."""
        from mesh.core.graph import MeshGraph

        start = time.perf_counter()

        graph = MeshGraph("call")
        for i in range(10000):
            graph.add_node(
                f"func_{i}", {"name": f"func_{i}", "file_path": f"file_{i % 100}.py"}
            )

        elapsed = time.perf_counter() - start
        assert elapsed < 1.0, f"Graph build took {elapsed:.2f}s, expected < 1s"
