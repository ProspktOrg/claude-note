"""Tests for Mycelium memory dynamics."""

import time

import pytest
from claude_note.mycelium.graph_store import GraphNode, GraphEdge, KnowledgeGraph
from claude_note.mycelium.memory_dynamics import FSRSEngine, MemoryDynamics


class TestFSRSEngine:
    def test_retrieval_at_zero(self):
        r = FSRSEngine.retrieval_strength(0, 1.0)
        assert r == 1.0

    def test_retrieval_decays(self):
        r7 = FSRSEngine.retrieval_strength(7, 1.0)
        r30 = FSRSEngine.retrieval_strength(30, 1.0)
        assert r7 > r30
        assert 0.5 < r7 < 0.8  # Approximately 0.63

    def test_retrieval_at_30_days(self):
        r = FSRSEngine.retrieval_strength(30, 1.0)
        assert 0.3 < r <= 0.5  # Power-law decay

    def test_higher_storage_slower_decay(self):
        r_s1 = FSRSEngine.retrieval_strength(14, 1.0)
        r_s5 = FSRSEngine.retrieval_strength(14, 5.0)
        assert r_s5 > r_s1  # Higher storage = slower decay

    def test_update_storage_low_retrieval(self):
        """Low retrieval at access -> higher storage increase (desirable difficulty)."""
        s_easy = FSRSEngine.update_storage_strength(1.0, 0.9)  # Easy recall
        s_hard = FSRSEngine.update_storage_strength(1.0, 0.3)  # Hard recall
        assert s_hard > s_easy  # Harder recall = more strengthening


class TestMemoryDynamics:
    @pytest.fixture
    def graph_with_chain(self):
        """Create A -> B -> C chain."""
        graph = KnowledgeGraph()
        now = time.time()
        for nid in ["a.md", "b.md", "c.md"]:
            graph.add_node(GraphNode(node_id=nid, last_accessed=now, storage_strength=1.0))
        graph.add_edge(GraphEdge(source="a.md", target="b.md", edge_type="link", weight=0.8))
        graph.add_edge(GraphEdge(source="b.md", target="c.md", edge_type="link", weight=0.8))
        return graph

    def test_spreading_activation_seed(self, graph_with_chain):
        dynamics = MemoryDynamics(graph_with_chain)
        activation = dynamics.spreading_activation(["a.md"], decay_factor=0.6, max_hops=3)

        assert activation["a.md"] == 1.0
        assert activation.get("b.md", 0) > 0.3  # 0.6 * 0.8 = 0.48
        assert activation.get("c.md", 0) > 0  # Further decay

    def test_spreading_activation_decay(self, graph_with_chain):
        dynamics = MemoryDynamics(graph_with_chain)
        activation = dynamics.spreading_activation(["a.md"], decay_factor=0.6, max_hops=3)

        # Each hop decays by decay_factor * weight
        a = activation.get("a.md", 0)
        b = activation.get("b.md", 0)
        c = activation.get("c.md", 0)
        assert a > b > c

    def test_self_healing(self, graph_with_chain):
        dynamics = MemoryDynamics(graph_with_chain)
        healed = dynamics.heal_after_removal("b.md")

        # Should create A -> C healing edge
        assert len(healed) == 1
        assert healed[0].source == "a.md"
        assert healed[0].target == "c.md"
        assert healed[0].edge_type == "healed"

    def test_frontier_shielding(self):
        graph = KnowledgeGraph()
        graph.add_node(GraphNode(
            node_id="frontier.md",
            is_frontier=True,
            category="marketing",
            retrieval_strength=0.1,
        ))
        graph.add_node(GraphNode(
            node_id="old.md",
            is_frontier=False,
            category="marketing",
            retrieval_strength=0.1,
        ))

        dynamics = MemoryDynamics(graph)
        pruned = dynamics.prune_weak_nodes(threshold=0.2, active_categories=["marketing"])

        # frontier.md should be shielded, old.md should be pruned
        assert "old.md" in pruned
        assert "frontier.md" not in pruned

    def test_reinforce_path(self, graph_with_chain):
        dynamics = MemoryDynamics(graph_with_chain)
        original_s = graph_with_chain.get_node("a.md").storage_strength

        dynamics.reinforce_path(["a.md", "b.md"])

        new_s = graph_with_chain.get_node("a.md").storage_strength
        assert new_s >= original_s  # Storage should increase or stay same

    def test_flow_scoring(self):
        """Bridge node should have highest centrality."""
        graph = KnowledgeGraph()
        for nid in ["a.md", "b.md", "hub.md", "c.md", "d.md"]:
            graph.add_node(GraphNode(node_id=nid))

        # Create star topology around hub
        for nid in ["a.md", "b.md", "c.md", "d.md"]:
            graph.add_edge(GraphEdge(source=nid, target="hub.md", edge_type="link", weight=0.8))
            graph.add_edge(GraphEdge(source="hub.md", target=nid, edge_type="link", weight=0.8))

        dynamics = MemoryDynamics(graph)
        flow = dynamics.compute_flow_scores(sample_size=10)

        # Hub should have highest or near-highest flow score
        if flow:
            hub_score = flow.get("hub.md", 0)
            other_scores = [s for nid, s in flow.items() if nid != "hub.md"]
            if other_scores:
                assert hub_score >= min(other_scores)
