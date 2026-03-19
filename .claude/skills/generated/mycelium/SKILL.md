---
name: mycelium
description: "Skill for the Mycelium area of claude-note. 45 symbols across 10 files."
---

# Mycelium

45 symbols | 10 files | Cohesion: 92%

## When to Use

- Working with code in `src/`
- Understanding how test_resolve_note_zone, graph_with_chain, test_self_healing work
- Modifying mycelium-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `src/claude_note/mycelium/graph_store.py` | add_node, remove_node, has_node, add_edge, get_edge (+9) |
| `tests/test_graph_store.py` | test_add_and_get_node, test_remove_node, test_add_and_get_edge, test_neighbors, test_persistence_roundtrip (+3) |
| `src/claude_note/mycelium/memory_dynamics.py` | heal_after_removal, get_shielded_nodes, prune_weak_nodes, compute_flow_scores, spreading_activation (+2) |
| `tests/test_memory_dynamics.py` | graph_with_chain, test_self_healing, test_frontier_shielding, test_flow_scoring, test_reinforce_path |
| `src/claude_note/mycelium/graph_sync.py` | sync_from_vault_index, _resolve_wikilink, add_synthesis_edges, add_semantic_edges, full_sync |
| `src/claude_note/mycelium/retrieval.py` | get_decay_candidates, get_knowledge_hubs |
| `tests/test_vault_zones.py` | test_resolve_note_zone |
| `tests/conftest.py` | sample_knowledge_graph |
| `src/claude_note/vault_zones.py` | resolve_note_zone |
| `src/claude_note/cli.py` | cmd_graph |

## Entry Points

Start here when exploring this area:

- **`test_resolve_note_zone`** (Function) — `tests/test_vault_zones.py:36`
- **`graph_with_chain`** (Function) — `tests/test_memory_dynamics.py:38`
- **`test_self_healing`** (Function) — `tests/test_memory_dynamics.py:66`
- **`test_frontier_shielding`** (Function) — `tests/test_memory_dynamics.py:76`
- **`test_flow_scoring`** (Function) — `tests/test_memory_dynamics.py:107`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `test_resolve_note_zone` | Function | `tests/test_vault_zones.py` | 36 |
| `graph_with_chain` | Function | `tests/test_memory_dynamics.py` | 38 |
| `test_self_healing` | Function | `tests/test_memory_dynamics.py` | 66 |
| `test_frontier_shielding` | Function | `tests/test_memory_dynamics.py` | 76 |
| `test_flow_scoring` | Function | `tests/test_memory_dynamics.py` | 107 |
| `test_add_and_get_node` | Function | `tests/test_graph_store.py` | 30 |
| `test_remove_node` | Function | `tests/test_graph_store.py` | 37 |
| `test_add_and_get_edge` | Function | `tests/test_graph_store.py` | 47 |
| `test_neighbors` | Function | `tests/test_graph_store.py` | 58 |
| `test_persistence_roundtrip` | Function | `tests/test_graph_store.py` | 70 |
| `test_traverse_edge` | Function | `tests/test_graph_store.py` | 92 |
| `sample_knowledge_graph` | Function | `tests/conftest.py` | 142 |
| `resolve_note_zone` | Function | `src/claude_note/vault_zones.py` | 449 |
| `get_decay_candidates` | Function | `src/claude_note/mycelium/retrieval.py` | 102 |
| `heal_after_removal` | Function | `src/claude_note/mycelium/memory_dynamics.py` | 150 |
| `get_shielded_nodes` | Function | `src/claude_note/mycelium/memory_dynamics.py` | 199 |
| `prune_weak_nodes` | Function | `src/claude_note/mycelium/memory_dynamics.py` | 217 |
| `compute_flow_scores` | Function | `src/claude_note/mycelium/memory_dynamics.py` | 247 |
| `spreading_activation` | Function | `src/claude_note/mycelium/memory_dynamics.py` | 309 |
| `sync_from_vault_index` | Function | `src/claude_note/mycelium/graph_sync.py` | 16 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Tests | 2 calls |

## How to Explore

1. `gitnexus_context({name: "test_resolve_note_zone"})` — see callers and callees
2. `gitnexus_query({query: "mycelium"})` — find related execution flows
3. Read key files listed above for implementation details
