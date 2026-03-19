# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

claude-note is a background service that captures Claude Code sessions and synthesizes knowledge into an Obsidian vault. It runs as a daemon, watching for hook events and processing them into structured notes.

## Development Commands

```bash
# Install for development (editable)
uv tool install --force .

# Run CLI directly during development
uv run claude-note status
uv run claude-note worker --foreground --verbose

# Reinstall after changes
uv tool install --force --reinstall .
```

## Release Process

```bash
# 1. Bump version in src/claude_note/__init__.py
# 2. Commit and push
git add -A && git commit -m "Bump to vX.Y.Z" && git push fork main

# 3. Tag and push - triggers auto-release via GitHub Actions
git tag vX.Y.Z && git push fork vX.Y.Z
```

## Architecture

### Data Flow

```
Claude Code Hook → enqueue.py → queue/*.jsonl → worker.py → synthesizer.py → vault notes
```

1. **Hooks** fire on Claude Code events (PostToolUse, UserPromptSubmit, Stop)
2. **enqueue.py** receives JSON via stdin, writes to daily queue files
3. **worker.py** polls queue, groups events by session, applies debounce
4. **synthesizer.py** calls Claude CLI to extract knowledge from transcripts
5. **note_router.py** writes to inbox or routes to specific notes

### Key Data Structures

- **QueuedEvent** (`models.py`): Single hook event with session_id, transcript_path
- **SessionState** (`models.py`): Tracks processing state, debounce timing
- **KnowledgePack** (`knowledge_pack.py`): Structured extraction output (concepts, decisions, questions, how-tos)

### Module Responsibilities

| Module | Purpose |
|--------|---------|
| `cli.py` | Command dispatch, argument parsing |
| `worker.py` | Background daemon, poll loop, synthesis trigger |
| `enqueue.py` | Hook handler, stdin → queue file |
| `synthesizer.py` | Claude API calls for knowledge extraction |
| `note_router.py` | Route KnowledgePack to vault notes |
| `ingest.py` | PDF/DOCX ingestion into literature notes |
| `version_checker.py` | GitHub releases API for update notifications |

### Storage Locations

All state lives in `{vault}/.claude-note/`:
- `queue/YYYY-MM-DD.jsonl` - Daily event queues
- `state/{session_id}.json` - Session processing state
- `state/{session_id}.lock` - File locks for concurrent access
- `logs/worker-*.log` - Worker logs

## Design Decisions

- **Pure stdlib**: No runtime dependencies (except Claude CLI for synthesis)
- **File-based queue**: Simple JSONL files, no database
- **Debounce**: Wait 15s after last event before writing notes
- **Synthesis modes**: `log` (just log), `inbox` (safe), `route` (full)
- **Version from `__init__.py`**: pyproject.toml uses dynamic versioning via hatch

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **claude-note** (867 symbols, 2212 relationships, 71 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> If any GitNexus tool warns the index is stale, run `npx gitnexus analyze` in terminal first.

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `gitnexus_detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `gitnexus_query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `gitnexus_context({name: "symbolName"})`.

## When Debugging

1. `gitnexus_query({query: "<error or symptom>"})` — find execution flows related to the issue
2. `gitnexus_context({name: "<suspect function>"})` — see all callers, callees, and process participation
3. `READ gitnexus://repo/claude-note/process/{processName}` — trace the full execution flow step by step
4. For regressions: `gitnexus_detect_changes({scope: "compare", base_ref: "main"})` — see what your branch changed

## When Refactoring

- **Renaming**: MUST use `gitnexus_rename({symbol_name: "old", new_name: "new", dry_run: true})` first. Review the preview — graph edits are safe, text_search edits need manual review. Then run with `dry_run: false`.
- **Extracting/Splitting**: MUST run `gitnexus_context({name: "target"})` to see all incoming/outgoing refs, then `gitnexus_impact({target: "target", direction: "upstream"})` to find all external callers before moving code.
- After any refactor: run `gitnexus_detect_changes({scope: "all"})` to verify only expected files changed.

## Never Do

- NEVER edit a function, class, or method without first running `gitnexus_impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `gitnexus_rename` which understands the call graph.
- NEVER commit changes without running `gitnexus_detect_changes()` to check affected scope.

## Tools Quick Reference

| Tool | When to use | Command |
|------|-------------|---------|
| `query` | Find code by concept | `gitnexus_query({query: "auth validation"})` |
| `context` | 360-degree view of one symbol | `gitnexus_context({name: "validateUser"})` |
| `impact` | Blast radius before editing | `gitnexus_impact({target: "X", direction: "upstream"})` |
| `detect_changes` | Pre-commit scope check | `gitnexus_detect_changes({scope: "staged"})` |
| `rename` | Safe multi-file rename | `gitnexus_rename({symbol_name: "old", new_name: "new", dry_run: true})` |
| `cypher` | Custom graph queries | `gitnexus_cypher({query: "MATCH ..."})` |

## Impact Risk Levels

| Depth | Meaning | Action |
|-------|---------|--------|
| d=1 | WILL BREAK — direct callers/importers | MUST update these |
| d=2 | LIKELY AFFECTED — indirect deps | Should test |
| d=3 | MAY NEED TESTING — transitive | Test if critical path |

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/claude-note/context` | Codebase overview, check index freshness |
| `gitnexus://repo/claude-note/clusters` | All functional areas |
| `gitnexus://repo/claude-note/processes` | All execution flows |
| `gitnexus://repo/claude-note/process/{name}` | Step-by-step execution trace |

## Self-Check Before Finishing

Before completing any code modification task, verify:
1. `gitnexus_impact` was run for all modified symbols
2. No HIGH/CRITICAL risk warnings were ignored
3. `gitnexus_detect_changes()` confirms changes match expected scope
4. All d=1 (WILL BREAK) dependents were updated

## Keeping the Index Fresh

After committing code changes, the GitNexus index becomes stale. Re-run analyze to update it:

```bash
npx gitnexus analyze
```

If the index previously included embeddings, preserve them by adding `--embeddings`:

```bash
npx gitnexus analyze --embeddings
```

To check whether embeddings exist, inspect `.gitnexus/meta.json` — the `stats.embeddings` field shows the count (0 means no embeddings). **Running analyze without `--embeddings` will delete any previously generated embeddings.**

> Claude Code users: A PostToolUse hook handles this automatically after `git commit` and `git merge`.

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |
| Work in the Claude_note area (250 symbols) | `.claude/skills/generated/claude-note/SKILL.md` |
| Work in the Mycelium area (45 symbols) | `.claude/skills/generated/mycelium/SKILL.md` |
| Work in the Tests area (34 symbols) | `.claude/skills/generated/tests/SKILL.md` |

<!-- gitnexus:end -->
