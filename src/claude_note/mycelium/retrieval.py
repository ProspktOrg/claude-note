"""Graph-based retrieval for Mycelium network.

Provides query interfaces for:
- Spreading activation from seed nodes
- Knowledge hub detection (high betweenness centrality)
- Growth frontier identification
- Decay candidate listing
"""

from typing import Optional

from .graph_store import KnowledgeGraph, GraphNode
from .memory_dynamics import MemoryDynamics


class MyceliumRetrieval:
    """High-level retrieval interface for the Mycelium knowledge graph."""

    def __init__(self, graph: KnowledgeGraph):
        self.graph = graph
        self.dynamics = MemoryDynamics(graph)

    def find_by_activation(
        self,
        seed_nodes: list[str],
        decay_factor: float = 0.6,
        max_hops: int = 3,
        min_score: float = 0.1,
        limit: int = 20,
    ) -> list[tuple[str, float]]:
        """
        Find notes by spreading activation from seed nodes.

        Args:
            seed_nodes: Starting node IDs
            decay_factor: Decay per hop
            max_hops: Maximum propagation depth
            min_score: Minimum activation to include
            limit: Maximum results

        Returns:
            List of (node_id, activation_score) sorted by score desc
        """
        activation = self.dynamics.spreading_activation(
            seed_nodes=seed_nodes,
            decay_factor=decay_factor,
            max_hops=max_hops,
        )

        # Filter and sort
        results = [
            (nid, score)
            for nid, score in activation.items()
            if score >= min_score and nid not in seed_nodes
        ]
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:limit]

    def get_knowledge_hubs(self, top_n: int = 10) -> list[tuple[str, float]]:
        """
        Find knowledge hubs (high betweenness centrality nodes).

        These are critical cross-department bridge nodes.

        Args:
            top_n: Number of top hubs to return

        Returns:
            List of (node_id, flow_score) sorted by score desc
        """
        flow_scores = self.dynamics.compute_flow_scores()

        sorted_nodes = sorted(
            flow_scores.items(),
            key=lambda x: x[1],
            reverse=True,
        )
        return sorted_nodes[:top_n]

    def get_growth_frontiers(self, category: str = None, limit: int = 20) -> list[GraphNode]:
        """
        Find frontier nodes (newly created, exploratory).

        Args:
            category: Filter by category (e.g., department name)
            limit: Maximum results

        Returns:
            List of frontier GraphNodes
        """
        frontiers = []
        for node in self.graph.nodes.values():
            if not node.is_frontier:
                continue
            if category and node.category != category:
                continue
            frontiers.append(node)

        # Sort by creation time (newest first)
        frontiers.sort(key=lambda n: n.created_ts, reverse=True)
        return frontiers[:limit]

    def get_decay_candidates(
        self,
        threshold: float = 0.3,
        active_categories: list[str] = None,
    ) -> list[tuple[str, float]]:
        """
        Find nodes with low retrieval strength (candidates for pruning).

        Respects frontier shielding for active categories.

        Args:
            threshold: Retrieval strength threshold
            active_categories: Categories to shield from pruning

        Returns:
            List of (node_id, retrieval_strength) sorted by strength asc
        """
        active_categories = active_categories or []
        shielded = self.dynamics.get_shielded_nodes(active_categories)

        candidates = []
        for node in self.graph.nodes.values():
            if node.retrieval_strength < threshold:
                if node.node_id not in shielded:
                    candidates.append((node.node_id, node.retrieval_strength))

        candidates.sort(key=lambda x: x[1])
        return candidates

    def get_activation_scores_for_agent(
        self,
        home_nodes: list[str],
        owned_tags: list[str] = None,
        decay_factor: float = 0.6,
        max_hops: int = 3,
    ) -> dict[str, float]:
        """
        Get activation scores for an agent's context retrieval.

        Combines home_nodes with tag-based seed nodes.

        Args:
            home_nodes: Agent's configured home nodes
            owned_tags: Agent's primary tags (used to find additional seeds)
            decay_factor: Spreading activation decay
            max_hops: Maximum propagation depth

        Returns:
            {note_path: activation_score}
        """
        # Build seed set from home_nodes + tagged notes
        seeds = list(home_nodes)

        if owned_tags:
            for node in self.graph.nodes.values():
                # Check if node's path contains any owned tag
                # (simplified - in practice would check note's actual tags)
                for tag in owned_tags:
                    if tag.lower() in node.node_id.lower():
                        if node.node_id not in seeds:
                            seeds.append(node.node_id)
                            break

        if not seeds:
            return {}

        return self.dynamics.spreading_activation(
            seed_nodes=seeds,
            decay_factor=decay_factor,
            max_hops=max_hops,
        )
