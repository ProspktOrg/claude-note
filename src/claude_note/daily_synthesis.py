"""Daily knowledge synthesis for claude-note (Stage 2).

Stage 1 (at session end): Worker compacts each session into a digest
         stored in the session note's Summary section.

Stage 2 (this module, once daily): Reads ALL session digests for the day,
         extracts cross-session knowledge, and routes it to the right
         vault folders. Can create new folders, notes, update existing
         notes, and update the knowledge graph.

Usage:
    claude-note daily                    # synthesize today
    claude-note daily --date 2026-03-19  # specific date
    claude-note daily --all              # all unprocessed days
"""

import json
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

from . import config
from . import knowledge_pack
from . import note_router
from . import vault_indexer


def _find_session_notes(date: str, vault_root: Path = None) -> list[Path]:
    """Find all session notes for a given date."""
    if vault_root is None:
        vault_root = config.VAULT_ROOT

    notes = []

    # v1 location: vault root
    for p in vault_root.glob(f"claude-session-{date}-*.md"):
        notes.append(p)

    # v2 location: journal/
    journal_dir = vault_root / "journal"
    if journal_dir.exists():
        for p in journal_dir.rglob(f"{date}-*-session-*.md"):
            notes.append(p)
        for p in journal_dir.rglob(f"claude-session-{date}-*.md"):
            if p not in notes:
                notes.append(p)

    return sorted(set(notes))


def _extract_digest(note_path: Path) -> Optional[str]:
    """
    Extract the digest/summary from a session note.

    Reads the ## Summary section. If it still has the placeholder,
    returns None (session wasn't compacted yet).
    """
    try:
        content = note_path.read_text(encoding="utf-8")

        # Skip if still has placeholder (not compacted)
        if "(Updated on Stop/SessionEnd with session highlights)" in content:
            return None

        # Extract Summary section
        match = re.search(r"## Summary\n\n(.*?)(?=\n## |\Z)", content, re.DOTALL)
        if match:
            digest = match.group(1).strip()
            if digest:
                return digest

        return None
    except Exception:
        return None


def _extract_session_meta(note_path: Path) -> dict:
    """Extract metadata from session note frontmatter."""
    meta = {"filename": note_path.stem, "path": str(note_path)}
    try:
        content = note_path.read_text(encoding="utf-8")
        fm_match = re.match(r"^---\n(.*?)\n---\n", content, re.DOTALL)
        if fm_match:
            for line in fm_match.group(1).split("\n"):
                if ":" in line:
                    key, _, val = line.partition(":")
                    meta[key.strip()] = val.strip().strip('"')

        # Extract working directory
        cwd_match = re.search(r"\*\*Working directory:\*\* `(.+?)`", content)
        if cwd_match:
            meta["cwd"] = cwd_match.group(1)

        # Extract duration
        dur_match = re.search(r"\*\*Duration:\*\* (.+)", content)
        if dur_match:
            meta["duration"] = dur_match.group(1)

    except Exception:
        pass
    return meta


def _check_already_synthesized(date: str) -> bool:
    """Check if daily synthesis has already run for this date."""
    marker = config.STATE_DIR / f"daily-synth-{date}.done"
    return marker.exists()


def _mark_synthesized(date: str) -> None:
    """Mark daily synthesis as complete for a date."""
    marker = config.STATE_DIR / f"daily-synth-{date}.done"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(datetime.utcnow().isoformat() + "Z", encoding="utf-8")


def build_daily_prompt(
    date: str,
    session_digests: list[dict],
    vault_index: vault_indexer.VaultIndex,
) -> str:
    """Build the Stage 2 prompt: extract knowledge from all daily digests."""
    schema = knowledge_pack.get_schema_description()

    # Vault context
    vault_summary = ""
    if vault_index and vault_index.notes:
        note_names = sorted([Path(n.path).stem for n in vault_index.notes.values()])
        all_tags = set()
        for note in vault_index.notes.values():
            all_tags.update(note.tags)
        vault_summary = (
            f"Vault has {len(vault_index.notes)} notes.\n"
            f"Available tags: {', '.join(sorted(all_tags))}\n"
            f"Existing notes: {', '.join(note_names)}"
        )

    # Format session digests
    digest_sections = []
    for sd in session_digests:
        meta = sd["meta"]
        header = f"### Session: {meta.get('filename', 'unknown')}"
        if meta.get("cwd"):
            header += f" (in `{meta['cwd']}`)"
        if meta.get("duration"):
            header += f" [{meta['duration']}]"
        if meta.get("agent"):
            header += f" -- agent: {meta['agent']}"
        digest_sections.append(f"{header}\n\n{sd['digest']}")

    digests_text = "\n\n---\n\n".join(digest_sections)

    return f"""You are the daily knowledge curator for a developer's Obsidian vault.

Below are ALL the session digests from {date}. Each digest is a compact
summary of one Claude Code session. Your job is to extract DURABLE knowledge
that spans across sessions, identify patterns, and route knowledge to the
right vault locations.

## Today's Sessions ({len(session_digests)} sessions)

{digests_text}

## Existing Vault (for linking and deduplication)

{vault_summary}

## Your Task

Extract knowledge into this JSON schema:
{schema}

## Rules

1. **Cross-session synthesis** -- merge related learnings across sessions
2. **Check existing notes** -- if a note exists, use "upsert_block" not "create"
3. **Route to departments** -- use folder paths like "engineering/tech-decisions/my-note.md"
   Available departments: executive/, marketing/, sales/, engineering/, product/, operations/
   Each has subfolders (e.g., engineering/architecture/, engineering/incidents/)
   You can create new subfolders if needed
4. **Decisions** -- extract all decisions with rationale into standalone notes or existing ones
5. **Patterns** -- identify recurring themes, gotchas, conventions
6. **Skip trivial sessions** -- don't extract from sessions that were just navigation
7. **Open threads** -- collect unresolved questions across sessions
8. **Frontmatter** -- for "create" ops, include tags matching the department and topic

Return ONLY valid JSON. No markdown wrapping, no explanation.
"""


def synthesize_daily(
    date: str = None,
    vault_root: Path = None,
    model: str = None,
    force: bool = False,
    timeout: int = 180,
) -> Optional[dict]:
    """
    Stage 2: Extract knowledge from all session digests for a date.

    Reads session notes, collects their digests, sends them all to
    Claude in one prompt, then routes the extracted knowledge to
    the correct vault folders.
    """
    if vault_root is None:
        vault_root = config.VAULT_ROOT
    if date is None:
        date = datetime.utcnow().strftime("%Y-%m-%d")
    if model is None:
        model = config.SYNTH_MODEL

    if not force and _check_already_synthesized(date):
        return {"status": "already_done", "date": date}

    # Find session notes
    session_notes = _find_session_notes(date, vault_root)
    if not session_notes:
        return {"status": "no_sessions", "date": date}

    # Extract digests
    session_digests = []
    skipped = 0
    for note_path in session_notes:
        digest = _extract_digest(note_path)
        if digest:
            meta = _extract_session_meta(note_path)
            session_digests.append({"digest": digest, "meta": meta})
        else:
            skipped += 1

    if not session_digests:
        return {
            "status": "no_digests",
            "date": date,
            "sessions_found": len(session_notes),
            "skipped": skipped,
        }

    # Build prompt
    vault_index = vault_indexer.get_index()
    prompt = build_daily_prompt(date, session_digests, vault_index)

    # Call Claude CLI
    env = os.environ.copy()
    env["CLAUDE_CODE_HOOKS_ENABLED"] = "false"

    try:
        result = subprocess.run(
            ["claude", "-p", prompt, "--model", model],
            capture_output=True,
            text=True,
            env=env,
            timeout=timeout,
        )

        if result.returncode != 0:
            return {"status": "error", "error": result.stderr[:500], "date": date}

        # Parse JSON output
        output = result.stdout.strip()
        if output.startswith("```"):
            first_nl = output.find("\n")
            if first_nl > 0:
                output = output[first_nl + 1:]
            if output.endswith("```"):
                output = output[:-3].strip()

        json_match = re.search(r'\{[\s\S]*\}', output)
        if json_match:
            output = json_match.group()

        data = json.loads(output)
        pack = knowledge_pack.KnowledgePack.from_dict(data)

        if not pack.time:
            pack.time = datetime.utcnow().strftime("%H:%M:%S")

        # Ensure note_op paths create proper folder structure
        for op in pack.note_ops:
            if "/" in op.path:
                folder = Path(vault_root) / Path(op.path).parent
                folder.mkdir(parents=True, exist_ok=True)

        # Route knowledge to vault
        routing = note_router.apply_note_ops(pack, mode="route", vault_root=vault_root)

        # Update knowledge graph if enabled
        if config.MYCELIUM_ENABLED:
            try:
                from .mycelium import KnowledgeGraph
                from .mycelium.graph_sync import sync_from_vault_index

                graph = KnowledgeGraph(config.GRAPH_DIR)
                graph.load()
                new_index = vault_indexer.build_index()
                sync_from_vault_index(graph, new_index, vault_root)
                graph.save()
                vault_indexer.save_index(new_index)
            except Exception:
                pass

        _mark_synthesized(date)

        return {
            "status": "ok",
            "date": date,
            "sessions_processed": len(session_digests),
            "sessions_skipped": skipped,
            "concepts": len(pack.concepts),
            "decisions": len(pack.decisions),
            "open_questions": len(pack.open_questions),
            "howtos": len(pack.howtos),
            "note_ops": len(pack.note_ops),
            "routing": routing,
        }

    except subprocess.TimeoutExpired:
        return {"status": "error", "error": f"Timed out after {timeout}s", "date": date}
    except FileNotFoundError:
        return {"status": "error", "error": "Claude CLI not found", "date": date}
    except json.JSONDecodeError as e:
        return {"status": "error", "error": f"JSON parse: {e}", "date": date}
    except Exception as e:
        return {"status": "error", "error": str(e), "date": date}


def get_unprocessed_dates(lookback_days: int = 7) -> list[str]:
    """Find dates with session notes that haven't been daily-synthesized."""
    dates = set()

    # Check queue files
    if config.QUEUE_DIR.exists():
        for qf in config.QUEUE_DIR.glob("*.jsonl"):
            date = qf.stem
            if re.match(r"\d{4}-\d{2}-\d{2}", date):
                if not _check_already_synthesized(date):
                    dates.add(date)

    # Check session notes
    vault_root = config.VAULT_ROOT
    for p in vault_root.glob("claude-session-*-*.md"):
        match = re.match(r"claude-session-(\d{4}-\d{2}-\d{2})-", p.name)
        if match and not _check_already_synthesized(match.group(1)):
            dates.add(match.group(1))

    # Don't include today (sessions may still be active)
    today = datetime.utcnow().strftime("%Y-%m-%d")
    dates.discard(today)

    return sorted(dates)[-lookback_days:]
