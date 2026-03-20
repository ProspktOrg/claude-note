"""Context retrieval for agent sessions.

Builds agent-scoped context from the vault and outputs it to stdout.
Claude Code's UserPromptSubmit hook captures stdout and injects it
directly into the conversation context -- no CLAUDE.md modification needed.

Context sources:
1. Agent domain briefing (auto-generated, refreshed when stale)
2. Scored vault notes (6-component relevance scoring, budget-constrained)
3. Recent cross-department decisions
"""

import re
import sys
from pathlib import Path
from typing import Optional

from . import config
from . import agent_config
from . import vault_zones
from . import vault_indexer
from . import relevance_scorer
from . import briefing_generator


# Token estimation: ~4 chars per token
CHARS_PER_TOKEN = 4

# Context budget allocation (tokens)
BRIEFING_BUDGET = 4000
HIGH_NOTES_BUDGET = 4000
MID_NOTES_BUDGET = 2000
LOW_NOTES_BUDGET = 500


def _truncate_to_tokens(text: str, max_tokens: int) -> str:
    """Truncate text to approximately max_tokens."""
    max_chars = max_tokens * CHARS_PER_TOKEN
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n...(truncated)"


def _format_high_note(note: relevance_scorer.NoteScore, vault_root: Path) -> str:
    """Format a high-relevance note with full content."""
    note_path = vault_root / note.path
    if not note_path.exists():
        return f"### [[{note.title}]]\n(Note not found)\n"

    try:
        content = note_path.read_text(encoding="utf-8")
        content = re.sub(r'^---\n.*?\n---\n', '', content, flags=re.DOTALL)
        content = content.strip()
        if len(content) > 2000:
            content = content[:2000] + "\n...(truncated)"
        return f"### [[{note.title}]] (score: {note.total:.2f})\n{content}\n"
    except Exception:
        return f"### [[{note.title}]]\n(Could not read)\n"


def _format_mid_note(note: relevance_scorer.NoteScore, vault_root: Path) -> str:
    """Format a mid-relevance note with preview."""
    note_path = vault_root / note.path
    preview = ""
    if note_path.exists():
        try:
            content = note_path.read_text(encoding="utf-8")
            content = re.sub(r'^---\n.*?\n---\n', '', content, flags=re.DOTALL)
            lines = [l for l in content.strip().split("\n") if l.strip()][:5]
            preview = "\n".join(lines)
        except Exception:
            pass

    return f"- [[{note.title}]] (score: {note.total:.2f}): {preview[:200]}\n"


def _format_low_note(note: relevance_scorer.NoteScore) -> str:
    """Format a low-relevance note as title+link only."""
    return f"[[{note.title}]]"


def build_agent_context(
    agent_id: str = None,
    vault_root: Path = None,
    include_briefing: bool = True,
    include_notes: bool = True,
    include_decisions: bool = True,
    mycelium_scores: dict[str, float] = None,
) -> str:
    """
    Build complete context block for an agent session.

    Returns formatted markdown that can be printed to stdout
    for Claude Code hook injection, or used anywhere else.
    """
    if vault_root is None:
        vault_root = config.VAULT_ROOT
    if agent_id is None:
        agent_id = agent_config.get_current_agent_id()

    profile = agent_config.get_current_agent(vault_root)
    sections = []

    # Header
    role_title = profile.role or agent_id.replace("-", " ").title()
    sections.append(f"## Vault Context: {role_title}")
    sections.append("")

    # 1. Briefing
    if include_briefing:
        briefing_path = vault_zones.get_agent_briefing_path(agent_id, vault_root)
        if briefing_path.exists():
            briefing_content = briefing_path.read_text(encoding="utf-8")
            briefing_content = re.sub(r'^---\n.*?\n---\n', '', briefing_content, flags=re.DOTALL)
            briefing_content = _truncate_to_tokens(briefing_content.strip(), BRIEFING_BUDGET)
            sections.append("### Briefing")
            sections.append(briefing_content)
            sections.append("")

    # 2. Activated Notes
    if include_notes:
        vault_index = vault_indexer.get_index()
        scored = relevance_scorer.score_notes(
            vault_index=vault_index,
            primary_tags=profile.tags_primary,
            secondary_tags=profile.tags_secondary,
            primary_folders=profile.primary_folders,
            secondary_folders=profile.secondary_folders,
            excluded_folders=profile.excluded_folders,
            mycelium_scores=mycelium_scores or {},
        )

        tiers = relevance_scorer.budget_constrain(
            scored,
            max_notes=profile.context_budget,
        )

        if tiers["high"] or tiers["mid"] or tiers["low"]:
            sections.append("### Activated Notes")

            for note in tiers["high"]:
                content = _format_high_note(note, vault_root)
                sections.append(content)

            if tiers["mid"]:
                sections.append("**Related:**")
                for note in tiers["mid"]:
                    sections.append(_format_mid_note(note, vault_root))

            if tiers["low"]:
                low_links = ", ".join(_format_low_note(n) for n in tiers["low"])
                sections.append(f"**See also:** {low_links}")

            sections.append("")

    # 3. Recent Cross-Department Decisions
    if include_decisions:
        decisions_path = vault_zones.get_decisions_log_path(vault_root)
        if decisions_path.exists():
            try:
                decisions_content = decisions_path.read_text(encoding="utf-8")
                entries = re.findall(
                    r'(### .+?\n(?:.*?\n)*?)(?=### |\Z)',
                    decisions_content,
                    re.DOTALL,
                )
                if entries:
                    recent = entries[-5:]
                    sections.append("### Recent Cross-Dept Decisions")
                    for entry in recent:
                        sections.append(entry.strip())
                    sections.append("")
            except Exception:
                pass

    return "\n".join(sections)


def inject_context(
    agent_id: str = None,
    vault_root: Path = None,
    mycelium_scores: dict[str, float] = None,
) -> str:
    """
    Build and return agent context for injection.

    When called from a UserPromptSubmit hook, the caller prints
    the returned string to stdout. Claude Code captures it and
    injects it directly into the conversation context.

    Also ensures the agent briefing is fresh (regenerates if stale).

    Returns:
        Context string, or empty string if nothing to inject.
    """
    if vault_root is None:
        vault_root = config.VAULT_ROOT

    if agent_id is None:
        agent_id = agent_config.get_current_agent_id()

    # Ensure briefing is fresh (only if agent mode is active)
    if agent_id != agent_config.DEFAULT_AGENT_ID:
        try:
            briefing_generator.update_briefing(agent_id, vault_root)
        except Exception:
            pass  # Don't fail if briefing regen fails

    # Build context
    context = build_agent_context(
        agent_id=agent_id,
        vault_root=vault_root,
        mycelium_scores=mycelium_scores,
    )

    return context.strip()
