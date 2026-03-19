---
name: claude-note
description: "Skill for the Claude_note area of claude-note. 250 symbols across 39 files."
---

# Claude_note

250 symbols | 39 files | Cohesion: 84%

## When to Use

- Working with code in `src/`
- Understanding how process_session, get_state_file, load_session_state work
- Modifying claude_note-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `src/claude_note/vault_zones.py` | get_department_path, get_moc_path, ensure_department_structure, get_journal_path, get_session_note_path (+10) |
| `src/claude_note/cli.py` | cmd_migrate, _restart_worker, cmd_update, cmd_index, _format_bytes (+9) |
| `src/claude_note/vault_indexer.py` | to_dict, to_json, load_index, save_index, update_index (+8) |
| `src/claude_note/session_tracker.py` | get_state_file, load_session_state, save_session_state, should_flush_immediately, get_sessions_ready_for_write (+7) |
| `src/claude_note/note_router.py` | _find_similar_content_qmd, _enhance_concept_links, _format_frontmatter, create_note, apply_note_op (+7) |
| `src/claude_note/note_writer.py` | get_note_filename, format_timestamp, _extract_tool_name, _format_group, compress_timeline (+6) |
| `src/claude_note/classifier_job.py` | _route_entry_to_department, setup_logging, regenerate_stale_briefings, detect_conflicts, run_classifier_job (+4) |
| `src/claude_note/agent_config.py` | to_dict, to_json, _agent_path, get, save (+4) |
| `src/claude_note/managed_blocks.py` | _make_start_marker, _make_end_marker, _atomic_write, read_managed_block, write_managed_block (+4) |
| `src/claude_note/ingest.py` | _find_similar_existing_concept, convert_to_text, _merge_concept_sources, slugify, create_source_note (+3) |

## Entry Points

Start here when exploring this area:

- **`process_session`** (Function) — `src/claude_note/worker.py:238`
- **`get_state_file`** (Function) — `src/claude_note/session_tracker.py:11`
- **`load_session_state`** (Function) — `src/claude_note/session_tracker.py:37`
- **`save_session_state`** (Function) — `src/claude_note/session_tracker.py:49`
- **`should_flush_immediately`** (Function) — `src/claude_note/session_tracker.py:206`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `process_session` | Function | `src/claude_note/worker.py` | 238 |
| `get_state_file` | Function | `src/claude_note/session_tracker.py` | 11 |
| `load_session_state` | Function | `src/claude_note/session_tracker.py` | 37 |
| `save_session_state` | Function | `src/claude_note/session_tracker.py` | 49 |
| `should_flush_immediately` | Function | `src/claude_note/session_tracker.py` | 206 |
| `get_sessions_ready_for_write` | Function | `src/claude_note/session_tracker.py` | 212 |
| `mark_session_written` | Function | `src/claude_note/session_tracker.py` | 231 |
| `is_session_written` | Function | `src/claude_note/session_tracker.py` | 239 |
| `enqueue_event` | Function | `src/claude_note/queue_manager.py` | 19 |
| `filter_questions_with_llm` | Function | `src/claude_note/open_questions.py` | 45 |
| `extract_questions_from_events` | Function | `src/claude_note/open_questions.py` | 112 |
| `promote_session_questions` | Function | `src/claude_note/open_questions.py` | 217 |
| `to_json` | Function | `src/claude_note/models.py` | 45 |
| `should_write` | Function | `src/claude_note/models.py` | 79 |
| `main` | Function | `src/claude_note/enqueue.py` | 16 |
| `run_synthesis_for_drain` | Function | `src/claude_note/drain.py` | 20 |
| `drain_all` | Function | `src/claude_note/drain.py` | 47 |
| `main` | Function | `src/claude_note/drain.py` | 114 |
| `build_synthesis_prompt` | Function | `src/claude_note/synthesizer.py` | 213 |
| `is_qmd_available` | Function | `src/claude_note/qmd_search.py` | 23 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Apply_note_ops → Get_agents_path` | cross_community | 6 |
| `Cmd_clean → _extract_tool_name` | cross_community | 6 |
| `Cmd_clean → Format_timestamp` | cross_community | 6 |
| `Run_classifier_job → _make_start_marker` | cross_community | 5 |
| `Run_classifier_job → _make_end_marker` | cross_community | 5 |
| `Run_classifier_job → _atomic_write` | cross_community | 5 |
| `Run_classifier_job → Get_department_path` | cross_community | 5 |
| `Drain_all → Get_note_filename` | cross_community | 5 |
| `Drain_all → Calculate_duration` | cross_community | 5 |
| `Append_to_inbox → Is_qmd_available` | cross_community | 5 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Tests | 3 calls |
| Mycelium | 2 calls |

## How to Explore

1. `gitnexus_context({name: "process_session"})` — see callers and callees
2. `gitnexus_query({query: "claude_note"})` — find related execution flows
3. Read key files listed above for implementation details
