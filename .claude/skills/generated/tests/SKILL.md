---
name: tests
description: "Skill for the Tests area of claude-note. 34 symbols across 11 files."
---

# Tests

34 symbols | 11 files | Cohesion: 87%

## When to Use

- Working with code in `tests/`
- Understanding how test_department_primary, test_department_secondary, test_department_excluded work
- Modifying tests-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `tests/test_relevance_scorer.py` | test_department_primary, test_department_secondary, test_department_excluded, test_hub_score, test_tag_match_primary (+2) |
| `tests/test_agent_config.py` | test_paperclip_agent_id, test_default_when_no_env, test_get_current_agent_profile, test_owns_folder, test_can_access_folder (+1) |
| `src/claude_note/agent_config.py` | get_current_agent_id, get_current_agent, owns_folder, can_access_folder, owns_tag |
| `src/claude_note/relevance_scorer.py` | _score_department, _score_hub, score_notes, _score_tag_match |
| `tests/test_memory_dynamics.py` | test_retrieval_at_zero, test_retrieval_decays, test_retrieval_at_30_days, test_higher_storage_slower_decay |
| `tests/test_migration.py` | test_empty_vault, test_v1_vault, test_v2_vault |
| `src/claude_note/context_retriever.py` | inject_context |
| `src/claude_note/mycelium/memory_dynamics.py` | retrieval_strength |
| `src/claude_note/migration.py` | detect_vault_version |
| `tests/test_vault_zones.py` | test_resolve_note_department |

## Entry Points

Start here when exploring this area:

- **`test_department_primary`** (Function) — `tests/test_relevance_scorer.py:29`
- **`test_department_secondary`** (Function) — `tests/test_relevance_scorer.py:33`
- **`test_department_excluded`** (Function) — `tests/test_relevance_scorer.py:37`
- **`test_hub_score`** (Function) — `tests/test_relevance_scorer.py:58`
- **`score_notes`** (Function) — `src/claude_note/relevance_scorer.py:134`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `test_department_primary` | Function | `tests/test_relevance_scorer.py` | 29 |
| `test_department_secondary` | Function | `tests/test_relevance_scorer.py` | 33 |
| `test_department_excluded` | Function | `tests/test_relevance_scorer.py` | 37 |
| `test_hub_score` | Function | `tests/test_relevance_scorer.py` | 58 |
| `score_notes` | Function | `src/claude_note/relevance_scorer.py` | 134 |
| `test_paperclip_agent_id` | Function | `tests/test_agent_config.py` | 71 |
| `test_default_when_no_env` | Function | `tests/test_agent_config.py` | 75 |
| `test_get_current_agent_profile` | Function | `tests/test_agent_config.py` | 82 |
| `inject_context` | Function | `src/claude_note/context_retriever.py` | 197 |
| `get_current_agent_id` | Function | `src/claude_note/agent_config.py` | 166 |
| `get_current_agent` | Function | `src/claude_note/agent_config.py` | 192 |
| `test_retrieval_at_zero` | Function | `tests/test_memory_dynamics.py` | 10 |
| `test_retrieval_decays` | Function | `tests/test_memory_dynamics.py` | 14 |
| `test_retrieval_at_30_days` | Function | `tests/test_memory_dynamics.py` | 20 |
| `test_higher_storage_slower_decay` | Function | `tests/test_memory_dynamics.py` | 24 |
| `retrieval_strength` | Function | `src/claude_note/mycelium/memory_dynamics.py` | 33 |
| `test_tag_match_primary` | Function | `tests/test_relevance_scorer.py` | 14 |
| `test_tag_match_secondary` | Function | `tests/test_relevance_scorer.py` | 19 |
| `test_tag_match_none` | Function | `tests/test_relevance_scorer.py` | 24 |
| `test_empty_vault` | Function | `tests/test_migration.py` | 8 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Build_agent_context → Get_current_agent_id` | cross_community | 3 |
| `Build_agent_context → Get_default_agent` | cross_community | 3 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Claude_note | 2 calls |

## How to Explore

1. `gitnexus_context({name: "test_department_primary"})` — see callers and callees
2. `gitnexus_query({query: "tests"})` — find related execution flows
3. Read key files listed above for implementation details
