"""Context retrieval and CLAUDE.md injection for agent sessions.

Orchestrates loading agent profile, checking briefing freshness,
scoring notes, and injecting context into vault's CLAUDE.md.
"""

import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from . import config
from . import agent_config
from . import vault_zones
from . import vault_indexer
from . import relevance_scorer
from . import briefing_generator
from . import managed_blocks


# Token estimation: ~4 chars per token
CHARS_PER_TOKEN = 4

# Context budget allocation (tokens)
BRIEFING_BUDGET = 4000
HIGH_NOTES_BUDGET = 4000
MID_NOTES_BUDGET = 2000
LOW_NOTES_BUDGET = 500

# Managed block ID for agent context injection
CONTEXT_BLOCK_ID = "agent-context"


def _estimate_tokens(text: str) -> int:
    """Rough token count estimation."""
    return len(text) // CHARS_PER_TOKEN


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
        # Remove frontmatter for injection
        content = re.sub(r'^---\n.*?\n---\n', '', content, flags=re.DOTALL)
        content = content.strip()
        # Truncate individual notes
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
            # Get first few paragraphs
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

    Args:
        agent_id: Agent ID (defaults to current from env)
        vault_root: Override vault root
        include_briefing: Include domain briefing
        include_notes: Include activated notes
        include_decisions: Include recent cross-dept decisions
        mycelium_scores: Pre-computed mycelium activation scores

    Returns:
        Formatted markdown context block
    """
    if vault_root is None:
        vault_root = config.VAULT_ROOT
    if agent_id is None:
        agent_id = agent_config.get_current_agent_id()

    profile = agent_config.get_current_agent(vault_root)
    sections = []

    # Header
    role_title = profile.role or agent_id.replace("-", " ").title()
    sections.append(f"## Domain Context: {role_title}")
    sections.append("")

    # 1. Briefing
    if include_briefing:
        briefing_path = vault_zones.get_agent_briefing_path(agent_id, vault_root)
        if briefing_path.exists():
            briefing_content = briefing_path.read_text(encoding="utf-8")
            # Strip frontmatter
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

            # High tier: full content
            for note in tiers["high"]:
                content = _format_high_note(note, vault_root)
                sections.append(content)

            # Mid tier: previews
            if tiers["mid"]:
                sections.append("**Related:**")
                for note in tiers["mid"]:
                    sections.append(_format_mid_note(note, vault_root))

            # Low tier: just links
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
                # Extract recent entries (last 5 ### headings)
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
    claude_md_path: Path = None,
    mycelium_scores: dict[str, float] = None,
) -> bool:
    """
    Inject agent context into vault's CLAUDE.md as a managed block.

    Args:
        agent_id: Agent ID (defaults to current from env)
        vault_root: Override vault root
        claude_md_path: Override CLAUDE.md path (defaults to vault_root/CLAUDE.md)
        mycelium_scores: Pre-computed mycelium activation scores

    Returns:
        True if context was injected
    """
    if vault_root is None:
        vault_root = config.VAULT_ROOT
    if claude_md_path is None:
        claude_md_path = vault_root / "CLAUDE.md"

    # Ensure briefing is fresh
    if agent_id is None:
        agent_id = agent_config.get_current_agent_id()

    if agent_id != agent_config.DEFAULT_AGENT_ID:
        briefing_generator.update_briefing(agent_id, vault_root)

    # Build context
    context = build_agent_context(
        agent_id=agent_id,
        vault_root=vault_root,
        mycelium_scores=mycelium_scores,
    )

    if not context.strip():
        return False

    # Inject into CLAUDE.md
    if not claude_md_path.exists():
        # Create minimal CLAUDE.md
        claude_md_path.write_text(
            f"# Vault Knowledge\n\n"
            f"<!-- claude-note:{CONTEXT_BLOCK_ID}:start -->\n"
            f"{context}\n"
            f"<!-- claude-note:{CONTEXT_BLOCK_ID}:end -->\n",
            encoding="utf-8",
        )
        return True

    return managed_blocks.write_managed_block(
        claude_md_path,
        CONTEXT_BLOCK_ID,
        context,
        create_if_missing=True,
    )


def remove_context(vault_root: Path = None, claude_md_path: Path = None) -> bool:
    """Remove injected context from CLAUDE.md."""
    if vault_root is None:
        vault_root = config.VAULT_ROOT
    if claude_md_path is None:
        claude_md_path = vault_root / "CLAUDE.md"

    if not claude_md_path.exists():
        return False

    return managed_blocks.delete_managed_block(claude_md_path, CONTEXT_BLOCK_ID)
