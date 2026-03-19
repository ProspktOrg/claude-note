"""Graph storage with JSON persistence for Mycelium network.

Provides GraphNode, GraphEdge, and KnowledgeGraph with:
- In-memory adjacency lists for fast traversal
- Dirty tracking for batched saves
- JSON persistence to .claude-note/graph/
"""

import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


@dataclass
class GraphNode:
    """A node in the knowledge graph (corresponds to a vault note)."""
    node_id: str           # Relative path from vault root
    title: str = ""
    category: str = ""     # department or zone
    is_frontier: bool = False  # Newly created, exploratory

    # FSRS Dual-Strength Memory Model
    storage_strength: float = 1.0    # How well encoded (grows with reinforcement)
    retrieval_strength: float = 1.0  # How easily recalled (decays over time)

    # Activity tracking
    last_accessed: float = 0.0   # Unix timestamp
    access_count: int = 0
    created_ts: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "GraphNode":
        valid = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid}
        return cls(**filtered)


@dataclass
class GraphEdge:
    """An edge in the knowledge graph."""
    source: str          # node_id of source
    target: str          # node_id of target
    edge_type: str = ""  # wikilink, tag_cooccurrence, synthesis, semantic, code_dependency
    weight: float = 0.5  # 0.0 - 1.0
    last_traversed: float = 0.0
    traversal_count: int = 0

    @property
    def edge_id(self) -> str:
        return f"{self.source}|{self.target}|{self.edge_type}"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "GraphEdge":
        valid = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid}
        return cls(**filtered)


class KnowledgeGraph:
    """In-memory knowledge graph with JSON persistence."""

    def __init__(self, graph_dir: Path = None):
        self.graph_dir = graph_dir
        self.nodes: dict[str, GraphNode] = {}
        self.edges: dict[str, GraphEdge] = {}  # edge_id -> edge

        # Adjacency lists for fast traversal
        self._outgoing: dict[str, set[str]] = {}  # node_id -> set of edge_ids
        self._incoming: dict[str, set[str]] = {}  # node_id -> set of edge_ids

        self._dirty = False
        self._loaded = False

    # ===== Node operations =====

    def add_node(self, node: GraphNode) -> None:
        """Add or update a node."""
        if node.node_id not in self.nodes:
            self._outgoing.setdefault(node.node_id, set())
            self._incoming.setdefault(node.node_id, set())
        self.nodes[node.node_id] = node
        self._dirty = True

    def get_node(self, node_id: str) -> Optional[GraphNode]:
        """Get a node by ID."""
        return self.nodes.get(node_id)

    def remove_node(self, node_id: str) -> Optional[GraphNode]:
        """Remove a node and all its edges."""
        node = self.nodes.pop(node_id, None)
        if node is None:
            return None

        # Remove edges
        for edge_id in list(self._outgoing.get(node_id, set())):
            self.edges.pop(edge_id, None)
        for edge_id in list(self._incoming.get(node_id, set())):
            self.edges.pop(edge_id, None)

        self._outgoing.pop(node_id, None)
        self._incoming.pop(node_id, None)

        # Clean up references in other nodes' adjacency
        for adj in self._outgoing.values():
            adj.discard(node_id)
        for adj in self._incoming.values():
            adj.discard(node_id)

        self._dirty = True
        return node

    def has_node(self, node_id: str) -> bool:
        return node_id in self.nodes

    # ===== Edge operations =====

    def add_edge(self, edge: GraphEdge) -> None:
        """Add or update an edge."""
        eid = edge.edge_id
        self.edges[eid] = edge
        self._outgoing.setdefault(edge.source, set()).add(eid)
        self._incoming.setdefault(edge.target, set()).add(eid)
        self._dirty = True

    def get_edge(self, source: str, target: str, edge_type: str = "") -> Optional[GraphEdge]:
        """Get a specific edge."""
        eid = f"{source}|{target}|{edge_type}"
        return self.edges.get(eid)

    def remove_edge(self, source: str, target: str, edge_type: str = "") -> Optional[GraphEdge]:
        """Remove a specific edge."""
        eid = f"{source}|{target}|{edge_type}"
        edge = self.edges.pop(eid, None)
        if edge:
            self._outgoing.get(source, set()).discard(eid)
            self._incoming.get(target, set()).discard(eid)
            self._dirty = True
        return edge

    def get_outgoing_edges(self, node_id: str) -> list[GraphEdge]:
        """Get all outgoing edges from a node."""
        edge_ids = self._outgoing.get(node_id, set())
        return [self.edges[eid] for eid in edge_ids if eid in self.edges]

    def get_incoming_edges(self, node_id: str) -> list[GraphEdge]:
        """Get all incoming edges to a node."""
        edge_ids = self._incoming.get(node_id, set())
        return [self.edges[eid] for eid in edge_ids if eid in self.edges]

    def get_neighbors(self, node_id: str) -> list[str]:
        """Get IDs of all neighbor nodes (both directions)."""
        neighbors = set()
        for edge in self.get_outgoing_edges(node_id):
            neighbors.add(edge.target)
        for edge in self.get_incoming_edges(node_id):
            neighbors.add(edge.source)
        return list(neighbors)

    # ===== Traversal =====

    def traverse_edge(self, source: str, target: str, edge_type: str = "") -> Optional[GraphEdge]:
        """Record a traversal of an edge (updates stats)."""
        edge = self.get_edge(source, target, edge_type)
        if edge:
            edge.traversal_count += 1
            edge.last_traversed = time.time()
            self._dirty = True
        return edge

    def access_node(self, node_id: str) -> Optional[GraphNode]:
        """Record an access of a node (updates stats)."""
        node = self.get_node(node_id)
        if node:
            node.access_count += 1
            node.last_accessed = time.time()
            self._dirty = True
        return node

    # ===== Persistence =====

    def load(self) -> None:
        """Load graph from JSON files."""
        if self.graph_dir is None:
            return

        nodes_path = self.graph_dir / "nodes.json"
        edges_path = self.graph_dir / "edges.json"

        if nodes_path.exists():
            try:
                data = json.loads(nodes_path.read_text(encoding="utf-8"))
                for node_data in data.get("nodes", []):
                    node = GraphNode.from_dict(node_data)
                    self.nodes[node.node_id] = node
                    self._outgoing.setdefault(node.node_id, set())
                    self._incoming.setdefault(node.node_id, set())
            except (json.JSONDecodeError, KeyError):
                pass

        if edges_path.exists():
            try:
                data = json.loads(edges_path.read_text(encoding="utf-8"))
                for edge_data in data.get("edges", []):
                    edge = GraphEdge.from_dict(edge_data)
                    eid = edge.edge_id
                    self.edges[eid] = edge
                    self._outgoing.setdefault(edge.source, set()).add(eid)
                    self._incoming.setdefault(edge.target, set()).add(eid)
            except (json.JSONDecodeError, KeyError):
                pass

        self._loaded = True
        self._dirty = False

    def save(self, force: bool = False) -> None:
        """Save graph to JSON files (only if dirty or forced)."""
        if self.graph_dir is None:
            return

        if not force and not self._dirty:
            return

        self.graph_dir.mkdir(parents=True, exist_ok=True)

        # Save nodes
        nodes_data = {
            "nodes": [n.to_dict() for n in self.nodes.values()],
            "count": len(self.nodes),
            "saved_at": time.time(),
        }
        nodes_path = self.graph_dir / "nodes.json"
        temp = nodes_path.with_suffix(".tmp")
        temp.write_text(json.dumps(nodes_data, indent=2), encoding="utf-8")
        temp.replace(nodes_path)

        # Save edges
        edges_data = {
            "edges": [e.to_dict() for e in self.edges.values()],
            "count": len(self.edges),
            "saved_at": time.time(),
        }
        edges_path = self.graph_dir / "edges.json"
        temp = edges_path.with_suffix(".tmp")
        temp.write_text(json.dumps(edges_data, indent=2), encoding="utf-8")
        temp.replace(edges_path)

        # Save stats
        stats = {
            "nodes": len(self.nodes),
            "edges": len(self.edges),
            "saved_at": time.time(),
        }
        stats_path = self.graph_dir / "stats.json"
        stats_path.write_text(json.dumps(stats, indent=2), encoding="utf-8")

        self._dirty = False

    def get_stats(self) -> dict:
        """Get graph statistics."""
        edge_types = {}
        for edge in self.edges.values():
            edge_types[edge.edge_type] = edge_types.get(edge.edge_type, 0) + 1

        return {
            "nodes": len(self.nodes),
            "edges": len(self.edges),
            "edge_types": edge_types,
            "dirty": self._dirty,
        }
