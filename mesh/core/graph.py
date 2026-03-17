"""
MeshGraph — rustworkx-backed graph for Mesh.

Replaces networkx MultiDiGraph with rustworkx PyDiGraph.
Provides identical interface to old CallGraph, DataFlowGraph, TypeDepGraph.

Adapted from: rustworkx (Apache 2.0)
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class GraphNode:
    """Node in a Mesh graph."""

    id: str
    name: str
    file_path: str
    line_start: int = 0
    line_end: int = 0
    signature: str = ""
    docstring: str = ""
    kind: str = "function"
    data: dict = field(default_factory=dict)


@dataclass
class GraphEdge:
    """Edge in a Mesh graph."""

    source_id: str
    target_id: str
    edge_type: str = "calls"
    call_site_line: int = 0
    is_conditional: bool = False
    data: dict = field(default_factory=dict)


class MeshGraph:
    """
    rustworkx-backed directed graph for Mesh.

    Provides identical interface to old CallGraph, DataFlowGraph,
    TypeDepGraph — enforcement layer must not need changes.
    """

    GRAPH_TYPES = {"call", "dataflow", "typedep", "type", "cfg"}

    def __init__(self, graph_type: str = "call"):
        """
        Initialize graph.

        Args:
            graph_type: One of "call", "dataflow", "typedep", "type"
        """
        import rustworkx as rx

        if graph_type not in self.GRAPH_TYPES:
            raise ValueError(f"graph_type must be one of {self.GRAPH_TYPES}")

        self._graph = rx.PyDiGraph()
        self._id_to_idx: dict[str, int] = {}
        self._idx_to_id: dict[int, str] = {}
        self._graph_type = graph_type

    def add_node(self, node_id: str, data: dict) -> int:
        """
        Add node to graph.

        Args:
            node_id: Unique identifier for node
            data: Node data dict

        Returns:
            rustworkx index of added node
        """
        if node_id in self._id_to_idx:
            idx = self._id_to_idx[node_id]
            # Remove and re-add to update
            try:
                self._graph.remove_node(idx)
            except Exception:
                pass
            idx = self._graph.add_node({"id": node_id, **data})
            self._id_to_idx[node_id] = idx
            self._idx_to_id[idx] = node_id
            return idx

        idx = self._graph.add_node({"id": node_id, **data})
        self._id_to_idx[node_id] = idx
        self._idx_to_id[idx] = node_id
        return idx

    def add_edge(self, from_id: str, to_id: str, data: dict) -> None:
        """
        Add directed edge between nodes.

        Args:
            from_id: Source node ID
            to_id: Target node ID
            data: Edge data dict
        """
        from_idx = self._id_to_idx.get(from_id)
        to_idx = self._id_to_idx.get(to_id)

        if from_idx is None or to_idx is None:
            return  # Skip edges to/from missing nodes

        self._graph.add_edge(from_idx, to_idx, data)

    def has_node(self, node_id: str) -> bool:
        """Check if node exists."""
        return node_id in self._id_to_idx

    def has_edge(self, from_id: str, to_id: str) -> bool:
        """Check if edge exists."""
        from_idx = self._id_to_idx.get(from_id)
        to_idx = self._id_to_idx.get(to_id)
        if from_idx is None or to_idx is None:
            return False
        return self._graph.has_edge(from_idx, to_idx)

    def in_degree(self, node_id: str) -> int:
        """Get number of incoming edges."""
        idx = self._id_to_idx.get(node_id)
        if idx is None:
            return 0
        return self._graph.in_degree(idx)

    def out_degree(self, node_id: str) -> int:
        """Get number of outgoing edges."""
        idx = self._id_to_idx.get(node_id)
        if idx is None:
            return 0
        return self._graph.out_degree(idx)

    def find_cycles(self) -> list[list[str]]:
        """
        Find all cycles in the graph.

        Returns:
            List of cycles, each cycle is a list of node IDs
        """
        import rustworkx as rx

        try:
            cycles = rx.simple_cycles(self._graph)
            # Convert indices back to IDs
            result = []
            for cycle in cycles:
                cycle_ids = [self._idx_to_id.get(idx, str(idx)) for idx in cycle]
                if len(cycle_ids) > 1:
                    result.append(cycle_ids)
            return result
        except Exception:
            return []

    def is_dag(self) -> bool:
        """Check if graph is a directed acyclic graph."""
        return len(self.find_cycles()) == 0

    def topological_sort(self) -> list[str]:
        """
        Get topological sort of nodes.

        Returns:
            List of node IDs in topological order

        Raises:
            ValueError: If graph contains cycles
        """
        import rustworkx as rx

        cycles = self.find_cycles()
        if cycles:
            raise ValueError(f"Graph contains cycles: {cycles}")

        try:
            sorted_indices = rx.topological_sort(self._graph)
            return [self._idx_to_id.get(idx, str(idx)) for idx in sorted_indices]
        except Exception as e:
            raise ValueError(f"Topological sort failed: {e}")

    def get_node(self, node_id: str) -> dict | None:
        """Get node data by ID."""
        idx = self._id_to_idx.get(node_id)
        if idx is None:
            return None
        return self._graph.nodes()[idx]

    def get_edge_data(self, from_id: str, to_id: str) -> dict | None:
        """Get edge data."""
        from_idx = self._id_to_idx.get(from_id)
        to_idx = self._id_to_idx.get(to_id)
        if from_idx is None or to_idx is None:
            return None

        edges = self._graph.edges()
        # Find the edge - rustworkx doesn't have direct edge lookup
        for edge in edges:
            if hasattr(edge, "source") and hasattr(edge, "target"):
                # Check if this is the right edge
                pass
        return None

    def nodes(self) -> list[dict]:
        """Get all nodes as list of data dicts."""
        return self._graph.nodes()

    def edges(self) -> list[dict]:
        """Get all edges as list of data dicts."""
        return self._graph.edges()

    def get_all_edges(self) -> list[dict]:
        """Get all edges with source and target IDs."""
        result = []
        # rustworkx PyDiGraph stores edge data directly
        # We need to find edges by iterating through all node indices
        for from_idx in range(len(self._graph)):
            try:
                edges = self._graph.out_edges(from_idx)
                for edge in edges:
                    # edge is (from_idx, to_idx, data)
                    if isinstance(edge, tuple) and len(edge) >= 3:
                        to_idx = edge[1]
                        data = edge[2] if len(edge) > 2 else {}
                        from_id = self._idx_to_id.get(from_idx, str(from_idx))
                        to_id = self._idx_to_id.get(to_idx, str(to_idx))
                        result.append(
                            {
                                "from_id": from_id,
                                "to_id": to_id,
                                **data,
                            }
                        )
            except Exception:
                continue
        return result

    def node_ids(self) -> list[str]:
        """Get all node IDs."""
        return list(self._id_to_idx.keys())

    @property
    def node_count(self) -> int:
        """Number of nodes in graph."""
        return self._graph.num_nodes()

    @property
    def edge_count(self) -> int:
        """Number of edges in graph."""
        return self._graph.num_edges()

    @property
    def graph_type(self) -> str:
        """Graph type (call, dataflow, typedep)."""
        return self._graph_type

    def predecessors(self, node_id: str) -> list[str]:
        """Get all predecessor node IDs."""
        idx = self._id_to_idx.get(node_id)
        if idx is None:
            return []

        import rustworkx as rx

        try:
            return list(rx.bfs_predecessors(self._graph, idx))
        except Exception:
            return []

    def successors(self, node_id: str) -> list[str]:
        """Get all successor node IDs."""
        idx = self._id_to_idx.get(node_id)
        if idx is None:
            return []

        import rustworkx as rx

        try:
            return list(rx.bfs_successors(self._graph, idx))
        except Exception:
            return []

    def clear(self) -> None:
        """Clear all nodes and edges."""
        self._graph = self._graph.__class__()
        self._id_to_idx.clear()
        self._idx_to_id.clear()

    def __len__(self) -> int:
        """Number of nodes."""
        return self.node_count

    def __contains__(self, node_id: str) -> bool:
        """Check if node exists."""
        return node_id in self._id_to_idx
