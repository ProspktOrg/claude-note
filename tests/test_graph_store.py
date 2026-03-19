"""Tests for Mycelium graph store."""

import json

import pytest
from claude_note.mycelium.graph_store import GraphNode, GraphEdge, KnowledgeGraph


class TestGraphNode:
    def test_create_node(self):
        node = GraphNode(node_id="test.md", title="Test Note")
        assert node.node_id == "test.md"
        assert node.storage_strength == 1.0
        assert node.retrieval_strength == 1.0

    def test_serialization(self):
        node = GraphNode(node_id="test.md", title="Test", category="marketing")
        data = node.to_dict()
        restored = GraphNode.from_dict(data)
        assert restored.node_id == "test.md"
        assert restored.category == "marketing"


class TestGraphEdge:
    def test_edge_id(self):
        edge = GraphEdge(source="a.md", target="b.md", edge_type="wikilink")
        assert edge.edge_id == "a.md|b.md|wikilink"


class TestKnowledgeGraph:
    def test_add_and_get_node(self):
        graph = KnowledgeGraph()
        node = GraphNode(node_id="test.md", title="Test")
        graph.add_node(node)
        assert graph.get_node("test.md") is not None
        assert graph.has_node("test.md")

    def test_remove_node(self):
        graph = KnowledgeGraph()
        graph.add_node(GraphNode(node_id="a.md"))
        graph.add_node(GraphNode(node_id="b.md"))
        graph.add_edge(GraphEdge(source="a.md", target="b.md", edge_type="link"))

        graph.remove_node("a.md")
        assert not graph.has_node("a.md")
        assert len(graph.get_incoming_edges("b.md")) == 0

    def test_add_and_get_edge(self):
        graph = KnowledgeGraph()
        graph.add_node(GraphNode(node_id="a.md"))
        graph.add_node(GraphNode(node_id="b.md"))
        edge = GraphEdge(source="a.md", target="b.md", edge_type="wikilink", weight=0.7)
        graph.add_edge(edge)

        retrieved = graph.get_edge("a.md", "b.md", "wikilink")
        assert retrieved is not None
        assert retrieved.weight == 0.7

    def test_neighbors(self):
        graph = KnowledgeGraph()
        graph.add_node(GraphNode(node_id="a.md"))
        graph.add_node(GraphNode(node_id="b.md"))
        graph.add_node(GraphNode(node_id="c.md"))
        graph.add_edge(GraphEdge(source="a.md", target="b.md", edge_type="link"))
        graph.add_edge(GraphEdge(source="c.md", target="a.md", edge_type="link"))

        neighbors = graph.get_neighbors("a.md")
        assert "b.md" in neighbors
        assert "c.md" in neighbors

    def test_persistence_roundtrip(self, tmp_path):
        graph_dir = tmp_path / "graph"
        graph_dir.mkdir()

        # Save
        graph = KnowledgeGraph(graph_dir)
        graph.add_node(GraphNode(node_id="test.md", title="Test"))
        graph.add_edge(GraphEdge(source="test.md", target="test.md", edge_type="self"))
        graph.save()

        # Load
        graph2 = KnowledgeGraph(graph_dir)
        graph2.load()
        assert graph2.has_node("test.md")
        assert len(graph2.edges) == 1

    def test_access_node(self):
        graph = KnowledgeGraph()
        graph.add_node(GraphNode(node_id="test.md", access_count=0))
        graph.access_node("test.md")
        assert graph.get_node("test.md").access_count == 1

    def test_traverse_edge(self):
        graph = KnowledgeGraph()
        graph.add_node(GraphNode(node_id="a.md"))
        graph.add_node(GraphNode(node_id="b.md"))
        graph.add_edge(GraphEdge(source="a.md", target="b.md", edge_type="link"))

        graph.traverse_edge("a.md", "b.md", "link")
        edge = graph.get_edge("a.md", "b.md", "link")
        assert edge.traversal_count == 1
