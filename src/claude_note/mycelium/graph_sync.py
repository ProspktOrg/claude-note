"""Graph synchronizer: vault index <-> knowledge graph.

Syncs vault notes to graph nodes, creates edges from:
- Wikilinks between notes
- Tag co-occurrence
- Synthesis relationships
- Code dependencies (if GitNexus available)
"""

import time
from pathlib import Path
from typing import Optional

from .graph_store import KnowledgeGraph, GraphNode, GraphEdge


def sync_from_vault_index(
    graph: KnowledgeGraph,
    vault_index,  # vault_indexer.VaultIndex (avoid circular import)
    vault_root: Path = None,
) -> dict:
    """
    Sync graph nodes and edges from vault index.

    Creates/updates nodes for each note, edges for wikilinks and tag co-occurrence.

    Returns dict with counts of added/updated/removed items.
    """
    results = {
        "nodes_added": 0,
        "nodes_updated": 0,
        "nodes_removed": 0,
        "edges_added": 0,
    }

    now = time.time()
    existing_node_ids = set(graph.nodes.keys())
    seen_node_ids = set()

    # 1. Sync nodes from vault index
    for path, note_index in vault_index.notes.items():
        seen_node_ids.add(path)

        # Determine category
        from .. import vault_zones
        category = vault_zones.resolve_note_zone(path)

        existing_node = graph.get_node(path)
        if existing_node:
            # Update
            existing_node.title = note_index.title
            existing_node.category = category
            results["nodes_updated"] += 1
        else:
            # Add new node
            node = GraphNode(
                node_id=path,
                title=note_index.title,
                category=category,
                is_frontier=True,  # New nodes start as frontier
                storage_strength=1.0,
                retrieval_strength=1.0,
                last_accessed=note_index.mtime,
                created_ts=now,
            )
            graph.add_node(node)
            results["nodes_added"] += 1

    # 2. Remove nodes for deleted notes
    for node_id in existing_node_ids - seen_node_ids:
        # Only remove vault-derived nodes (not manually added)
        node = graph.get_node(node_id)
        if node and node.node_id.endswith(".md"):
            graph.remove_node(node_id)
            results["nodes_removed"] += 1

    # 3. Create wikilink edges
    for path, note_index in vault_index.notes.items():
        for link_target in note_index.outbound_links:
            # Resolve link target to a node_id
            target_id = _resolve_wikilink(link_target, vault_index)
            if target_id and graph.has_node(target_id):
                existing = graph.get_edge(path, target_id, "wikilink")
                if not existing:
                    edge = GraphEdge(
                        source=path,
                        target=target_id,
                        edge_type="wikilink",
                        weight=0.7,
                    )
                    graph.add_edge(edge)
                    results["edges_added"] += 1

    # 4. Create tag co-occurrence edges
    tag_to_notes: dict[str, list[str]] = {}
    for path, note_index in vault_index.notes.items():
        for tag in note_index.tags:
            tag_to_notes.setdefault(tag, []).append(path)

    for tag, note_paths in tag_to_notes.items():
        if len(note_paths) < 2 or len(note_paths) > 20:
            continue  # Skip too rare or too common tags

        # Create edges between first few co-occurring notes
        for i in range(min(len(note_paths), 5)):
            for j in range(i + 1, min(len(note_paths), 5)):
                src, tgt = note_paths[i], note_paths[j]
                existing = graph.get_edge(src, tgt, "tag_cooccurrence")
                if not existing:
                    edge = GraphEdge(
                        source=src,
                        target=tgt,
                        edge_type="tag_cooccurrence",
                        weight=0.3,
                    )
                    graph.add_edge(edge)
                    results["edges_added"] += 1

    return results


def _resolve_wikilink(link_text: str, vault_index) -> Optional[str]:
    """Resolve a wikilink to a note path in the vault index."""
    # Try exact filename match
    target = link_text.strip()
    if not target.endswith(".md"):
        target_md = target + ".md"
    else:
        target_md = target

    # Search by filename
    for path in vault_index.notes:
        if Path(path).stem == link_text.strip():
            return path
        if path == target_md:
            return path

    # Search by alias
    for path, note in vault_index.notes.items():
        if link_text.strip() in note.aliases:
            return path

    return None


def add_synthesis_edges(
    graph: KnowledgeGraph,
    source_session: str,
    target_notes: list[str],
    weight: float = 0.6,
) -> int:
    """
    Add synthesis edges from a session to notes it referenced/created.

    Args:
        graph: KnowledgeGraph
        source_session: Session note path
        target_notes: List of note paths created/updated by synthesis
        weight: Edge weight

    Returns:
        Number of edges added
    """
    count = 0
    for target in target_notes:
        if graph.has_node(source_session) and graph.has_node(target):
            existing = graph.get_edge(source_session, target, "synthesis")
            if not existing:
                edge = GraphEdge(
                    source=source_session,
                    target=target,
                    edge_type="synthesis",
                    weight=weight,
                )
                graph.add_edge(edge)
                count += 1
    return count


def add_semantic_edges(
    graph: KnowledgeGraph,
    pairs: list[tuple[str, str, float]],
) -> int:
    """
    Add semantic similarity edges.

    Args:
        graph: KnowledgeGraph
        pairs: List of (source, target, similarity_score) tuples

    Returns:
        Number of edges added
    """
    count = 0
    for source, target, score in pairs:
        if graph.has_node(source) and graph.has_node(target):
            existing = graph.get_edge(source, target, "semantic")
            if existing:
                # Update weight if higher
                if score > existing.weight:
                    existing.weight = score
            else:
                edge = GraphEdge(
                    source=source,
                    target=target,
                    edge_type="semantic",
                    weight=score,
                )
                graph.add_edge(edge)
                count += 1
    return count


class GraphSynchronizer:
    """High-level graph sync operations."""

    def __init__(self, graph: KnowledgeGraph, vault_root: Path = None):
        self.graph = graph
        self.vault_root = vault_root

    def full_sync(self, vault_index) -> dict:
        """Perform full sync from vault index."""
        return sync_from_vault_index(self.graph, vault_index, self.vault_root)

    def post_synthesis_sync(
        self,
        session_path: str,
        created_notes: list[str],
        updated_notes: list[str],
    ) -> None:
        """Update graph after synthesis completes."""
        all_targets = created_notes + updated_notes
        add_synthesis_edges(self.graph, session_path, all_targets)

        # Mark created notes as frontier
        for path in created_notes:
            node = self.graph.get_node(path)
            if node:
                node.is_frontier = True
