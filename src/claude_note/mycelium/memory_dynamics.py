"""Memory dynamics implementing 6 bio-inspired mechanisms.

1. FSRS temporal decay (power-law forgetting curve)
2. Adaptive path reinforcement
3. Self-healing after node removal
4. Exploratory tendrils (frontier shielding)
5. Flow scoring (betweenness centrality approximation)
6. Spreading activation (Collins & Loftus)
"""

import math
import time
from typing import Optional

from .graph_store import KnowledgeGraph, GraphNode, GraphEdge


class FSRSEngine:
    """FSRS-inspired spaced repetition engine.

    Uses power-law forgetting curve:
    R(t, S) = (1 + 0.1 * t/S)^(-0.5)

    Where:
    - R = retrieval strength (probability of recall)
    - t = time since last access (days)
    - S = storage strength (stability)
    """

    DECAY_FACTOR = 0.1
    DECAY_POWER = -0.5

    @staticmethod
    def retrieval_strength(t_days: float, storage_strength: float) -> float:
        """
        Calculate retrieval strength R(t, S).

        Args:
            t_days: Days since last access
            storage_strength: Storage strength S (stability)

        Returns:
            Retrieval strength between 0 and 1
        """
        if storage_strength <= 0:
            return 0.0
        if t_days <= 0:
            return 1.0

        return math.pow(
            1 + FSRSEngine.DECAY_FACTOR * t_days / storage_strength,
            FSRSEngine.DECAY_POWER,
        )

    @staticmethod
    def update_storage_strength(
        current_s: float,
        retrieval_at_access: float,
        alpha: float = 0.2,
        beta: float = 0.5,
    ) -> float:
        """
        Update storage strength after an access.

        S' = S * (1 + alpha * (1 - R) * S^(-beta))

        Harder recall (lower R) leads to stronger encoding (desirable difficulty).

        Args:
            current_s: Current storage strength
            retrieval_at_access: Retrieval strength at time of access
            alpha: Learning rate
            beta: Stability decay factor

        Returns:
            Updated storage strength
        """
        if current_s <= 0:
            return 1.0

        difficulty_bonus = 1 - retrieval_at_access
        stability_factor = math.pow(current_s, -beta)
        growth = 1 + alpha * difficulty_bonus * stability_factor

        return current_s * growth


class MemoryDynamics:
    """Implements all 6 bio-inspired mechanisms on a KnowledgeGraph."""

    def __init__(self, graph: KnowledgeGraph):
        self.graph = graph
        self.fsrs = FSRSEngine()

    # ===== 1. Temporal Decay =====

    def apply_decay(self) -> dict:
        """
        Apply FSRS decay to all nodes, updating retrieval_strength.

        Returns dict with 'updated' count and 'below_threshold' list.
        """
        now = time.time()
        results = {"updated": 0, "below_threshold": []}

        for node in self.graph.nodes.values():
            if node.last_accessed <= 0:
                continue

            t_days = (now - node.last_accessed) / 86400.0
            new_r = self.fsrs.retrieval_strength(t_days, node.storage_strength)
            node.retrieval_strength = new_r
            results["updated"] += 1

            if new_r < 0.3:
                results["below_threshold"].append(node.node_id)

        return results

    # ===== 2. Adaptive Path Reinforcement =====

    def reinforce_path(self, path: list[str]) -> None:
        """
        Reinforce a path through the graph (sequence of node IDs).

        Updates node storage strength and edge weights.
        """
        now = time.time()

        for node_id in path:
            node = self.graph.access_node(node_id)
            if node:
                t_days = (now - node.last_accessed) / 86400.0 if node.last_accessed > 0 else 0
                r = self.fsrs.retrieval_strength(t_days, node.storage_strength)
                node.storage_strength = self.fsrs.update_storage_strength(
                    node.storage_strength, r
                )

        # Reinforce edges between consecutive nodes
        for i in range(len(path) - 1):
            src, tgt = path[i], path[i + 1]
            # Try all edge types
            for edge in self.graph.get_outgoing_edges(src):
                if edge.target == tgt:
                    edge.weight = min(1.0, edge.weight + 0.1)
                    edge.traversal_count += 1
                    edge.last_traversed = now

    # ===== 3. Self-Healing =====

    def heal_after_removal(self, removed_node_id: str) -> list[GraphEdge]:
        """
        Create bypass edges after a node is removed.

        If A -> X -> B and X is removed, creates A -> B (healing edge).

        Args:
            removed_node_id: ID of the node that was just removed

        Returns:
            List of newly created healing edges
        """
        # Collect neighbors before removal (must be called before remove_node)
        predecessors = set()
        successors = set()

        for edge in self.graph.get_incoming_edges(removed_node_id):
            predecessors.add(edge.source)
        for edge in self.graph.get_outgoing_edges(removed_node_id):
            successors.add(edge.target)

        # Remove the node
        self.graph.remove_node(removed_node_id)

        # Create healing edges
        healed = []
        for pred in predecessors:
            for succ in successors:
                if pred == succ:
                    continue
                # Don't create if edge already exists
                existing = self.graph.get_edge(pred, succ, "healed")
                if existing:
                    continue

                healing_edge = GraphEdge(
                    source=pred,
                    target=succ,
                    edge_type="healed",
                    weight=0.3,  # Weak initial weight
                    last_traversed=time.time(),
                )
                self.graph.add_edge(healing_edge)
                healed.append(healing_edge)

        return healed

    # ===== 4. Frontier Shielding =====

    def get_shielded_nodes(self, active_categories: list[str]) -> set[str]:
        """
        Get frontier nodes in active categories that should be shielded from pruning.

        Args:
            active_categories: Categories currently active (e.g., department names)

        Returns:
            Set of node IDs to shield
        """
        shielded = set()

        for node in self.graph.nodes.values():
            if node.is_frontier and node.category in active_categories:
                shielded.add(node.node_id)

        return shielded

    def prune_weak_nodes(
        self,
        threshold: float = 0.2,
        active_categories: list[str] = None,
    ) -> list[str]:
        """
        Prune nodes with retrieval strength below threshold.
        Shields frontier nodes in active categories.

        Returns list of pruned node IDs.
        """
        active_categories = active_categories or []
        shielded = self.get_shielded_nodes(active_categories)

        to_prune = []
        for node in list(self.graph.nodes.values()):
            if node.retrieval_strength < threshold:
                if node.node_id not in shielded:
                    to_prune.append(node.node_id)

        # Prune with healing
        pruned = []
        for node_id in to_prune:
            self.heal_after_removal(node_id)
            pruned.append(node_id)

        return pruned

    # ===== 5. Flow Scoring (Betweenness Centrality Approximation) =====

    def compute_flow_scores(self, sample_size: int = 50) -> dict[str, float]:
        """
        Approximate betweenness centrality for all nodes.

        Uses BFS from a sample of nodes to estimate how often
        each node appears on shortest paths.

        Args:
            sample_size: Number of source nodes to sample

        Returns:
            {node_id: flow_score} normalized to [0, 1]
        """
        if not self.graph.nodes:
            return {}

        flow_counts: dict[str, int] = {nid: 0 for nid in self.graph.nodes}
        all_nodes = list(self.graph.nodes.keys())

        # Sample sources
        import random
        sources = random.sample(all_nodes, min(sample_size, len(all_nodes)))

        for source in sources:
            # BFS to find shortest paths
            visited = {source}
            queue = [source]
            predecessors: dict[str, list[str]] = {}

            while queue:
                current = queue.pop(0)
                for neighbor in self.graph.get_neighbors(current):
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append(neighbor)
                        predecessors[neighbor] = [current]
                    elif len(predecessors.get(neighbor, [])) < 3:
                        predecessors.setdefault(neighbor, []).append(current)

            # Count nodes on paths (simplified)
            for node_id in visited:
                if node_id != source:
                    # Trace path back
                    current = node_id
                    path_len = 0
                    while current in predecessors and path_len < 20:
                        for pred in predecessors[current]:
                            if pred != source:
                                flow_counts[pred] = flow_counts.get(pred, 0) + 1
                            current = pred
                            break
                        path_len += 1

        # Normalize
        max_flow = max(flow_counts.values()) if flow_counts else 1
        if max_flow == 0:
            max_flow = 1

        return {nid: count / max_flow for nid, count in flow_counts.items()}

    # ===== 6. Spreading Activation =====

    def spreading_activation(
        self,
        seed_nodes: list[str],
        decay_factor: float = 0.6,
        max_hops: int = 3,
        min_activation: float = 0.01,
    ) -> dict[str, float]:
        """
        Collins & Loftus spreading activation from seed nodes.

        Activation spreads outward from seeds, decaying by
        decay_factor * edge_weight at each hop.

        Args:
            seed_nodes: Starting nodes (activation = 1.0)
            decay_factor: Decay per hop (0.6 = 60% retained)
            max_hops: Maximum propagation distance
            min_activation: Minimum activation to continue spreading

        Returns:
            {node_id: activation_score}
        """
        activation: dict[str, float] = {}

        # Initialize seeds
        for seed in seed_nodes:
            if self.graph.has_node(seed):
                activation[seed] = 1.0

        # Spread
        current_layer = set(seed_nodes)

        for hop in range(max_hops):
            next_layer = set()

            for node_id in current_layer:
                current_act = activation.get(node_id, 0.0)
                if current_act < min_activation:
                    continue

                # Spread to neighbors
                for edge in self.graph.get_outgoing_edges(node_id):
                    spread = current_act * decay_factor * edge.weight
                    if spread < min_activation:
                        continue

                    target = edge.target
                    existing = activation.get(target, 0.0)
                    new_act = max(existing, spread)  # Take max, don't accumulate

                    if new_act > existing:
                        activation[target] = new_act
                        next_layer.add(target)

                # Also spread via incoming edges (bidirectional)
                for edge in self.graph.get_incoming_edges(node_id):
                    spread = current_act * decay_factor * edge.weight
                    if spread < min_activation:
                        continue

                    source = edge.source
                    existing = activation.get(source, 0.0)
                    new_act = max(existing, spread)

                    if new_act > existing:
                        activation[source] = new_act
                        next_layer.add(source)

            current_layer = next_layer

        return activation
