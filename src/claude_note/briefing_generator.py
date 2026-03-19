"""Briefing generator for agent domain briefings.

Auto-generates domain-only briefings via Claude CLI.
Briefings contain strategic context, domain state, lessons,
cross-department dependencies, and open questions.

Does NOT include Paperclip-handled info (tasks, org chart, budget).
"""

import json
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

from . import config
from . import vault_zones
from . import vault_indexer


# Briefing staleness threshold (4 hours in seconds)
BRIEFING_STALE_HOURS = 4
BRIEFING_STALE_SECONDS = BRIEFING_STALE_HOURS * 3600

# Stale marker file pattern
STALE_MARKER = ".briefing-stale-{agent_id}"


def is_briefing_stale(agent_id: str, vault_root: Path = None) -> bool:
    """
    Check if an agent's briefing needs regeneration.

    A briefing is stale if:
    1. It doesn't exist
    2. It's older than BRIEFING_STALE_HOURS
    3. A stale marker file exists (set by cross-agent decision propagation)
    """
    if vault_root is None:
        vault_root = config.VAULT_ROOT

    briefing_path = vault_zones.get_agent_briefing_path(agent_id, vault_root)

    # Check if briefing exists
    if not briefing_path.exists():
        return True

    # Check stale marker
    state_dir = vault_root / ".claude-note" / "state"
    marker_path = state_dir / STALE_MARKER.format(agent_id=agent_id)
    if marker_path.exists():
        return True

    # Check age
    import time
    age = time.time() - briefing_path.stat().st_mtime
    return age > BRIEFING_STALE_SECONDS


def mark_briefing_stale(agent_id: str, vault_root: Path = None) -> None:
    """Mark an agent's briefing as needing regeneration."""
    if vault_root is None:
        vault_root = config.VAULT_ROOT

    state_dir = vault_root / ".claude-note" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)

    marker_path = state_dir / STALE_MARKER.format(agent_id=agent_id)
    marker_path.write_text(datetime.utcnow().isoformat() + "Z", encoding="utf-8")


def clear_stale_marker(agent_id: str, vault_root: Path = None) -> None:
    """Clear the stale marker for an agent's briefing."""
    if vault_root is None:
        vault_root = config.VAULT_ROOT

    state_dir = vault_root / ".claude-note" / "state"
    marker_path = state_dir / STALE_MARKER.format(agent_id=agent_id)
    if marker_path.exists():
        marker_path.unlink()


def _gather_briefing_context(agent_id: str, vault_root: Path = None) -> str:
    """
    Gather context for briefing generation.

    Reads recent department notes, decisions log, and cross-functional impacts.
    """
    if vault_root is None:
        vault_root = config.VAULT_ROOT

    from . import agent_config

    registry = agent_config.AgentRegistry(vault_root)
    profile = registry.get(agent_id)
    if not profile:
        profile = agent_config.get_default_agent()

    sections = []

    # 1. Recent notes from agent's primary folders
    sections.append("## Recent Department Notes")
    for folder in profile.primary_folders:
        folder_path = vault_root / folder
        if not folder_path.exists():
            continue

        # Get recent .md files sorted by mtime
        md_files = sorted(
            folder_path.rglob("*.md"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[:10]

        for md_file in md_files:
            try:
                content = md_file.read_text(encoding="utf-8")
                # Truncate to first 500 chars
                if len(content) > 500:
                    content = content[:500] + "..."
                rel_path = md_file.relative_to(vault_root)
                sections.append(f"\n### [[{md_file.stem}]] ({rel_path})")
                sections.append(content)
            except Exception:
                continue

    # 2. Decisions log (recent entries)
    decisions_path = vault_zones.get_decisions_log_path(vault_root)
    if decisions_path.exists():
        sections.append("\n## Recent Decisions")
        try:
            decisions_content = decisions_path.read_text(encoding="utf-8")
            # Get last 2000 chars (most recent entries)
            if len(decisions_content) > 2000:
                decisions_content = "..." + decisions_content[-2000:]
            sections.append(decisions_content)
        except Exception:
            sections.append("(Could not read decisions log)")

    # 3. Other agents' recent outputs that affect this agent
    sections.append("\n## Cross-Department Context")
    agents_path = vault_zones.get_agents_path(vault_root)
    if agents_path.exists():
        for other_agent_dir in agents_path.iterdir():
            if not other_agent_dir.is_dir():
                continue
            if other_agent_dir.name == agent_id:
                continue

            other_briefing = other_agent_dir / "briefing.md"
            if other_briefing.exists():
                try:
                    content = other_briefing.read_text(encoding="utf-8")
                    # Extract cross-department section if it exists
                    cross_match = re.search(
                        r"## Cross-Department Dependencies\n(.+?)(?=\n## |\Z)",
                        content,
                        re.DOTALL,
                    )
                    if cross_match:
                        sections.append(f"\nFrom {other_agent_dir.name}:")
                        sections.append(cross_match.group(1).strip())
                except Exception:
                    continue

    return "\n".join(sections)


def _build_briefing_prompt(agent_id: str, role: str, department: str, context: str) -> str:
    """Build the Claude CLI prompt for briefing generation."""
    return f"""You are generating a domain briefing for the {role} ({agent_id}).
Department: {department}

This briefing provides DOMAIN KNOWLEDGE ONLY. Do NOT include:
- Task assignments (Paperclip handles this)
- Organization chart (Paperclip handles this)
- Budget information (Paperclip handles this)
- Company goal one-liner (Paperclip handles this)

The briefing SHOULD include:
- Strategic context relevant to this role
- Current domain state (projects, initiatives, deadlines)
- Recent lessons and gotchas
- Cross-department dependencies
- Open domain questions

## Context from Vault
{context}

## Output Format
Generate markdown with these sections:
1. ## Strategic Context (2-3 bullets on company direction affecting this role)
2. ## Your Domain State (current projects, deadlines, key metrics)
3. ## Recent Lessons & Gotchas (what went wrong/right recently)
4. ## Cross-Department Dependencies (what other teams need from you / you need from them)
5. ## Open Domain Questions (unresolved strategic/tactical questions)

Keep it concise. Each section should have 2-5 bullet points maximum.
Use [[wikilinks]] to reference vault notes.
Output ONLY the markdown content, no code blocks or explanation.
"""


def generate_briefing(
    agent_id: str,
    vault_root: Path = None,
    model: str = None,
    timeout: int = 120,
) -> Optional[str]:
    """
    Generate a domain briefing for an agent using Claude CLI.

    Args:
        agent_id: Agent to generate briefing for
        vault_root: Override vault root
        model: Override Claude model
        timeout: CLI timeout in seconds

    Returns:
        Generated briefing markdown, or None on failure
    """
    if vault_root is None:
        vault_root = config.VAULT_ROOT
    if model is None:
        model = config.SYNTH_MODEL

    from . import agent_config

    registry = agent_config.AgentRegistry(vault_root)
    profile = registry.get(agent_id)
    if not profile:
        profile = agent_config.AgentProfile(
            agent_id=agent_id,
            role=agent_id.replace("-", " ").title(),
            department="",
        )

    # Gather context
    context = _gather_briefing_context(agent_id, vault_root)

    # Build prompt
    prompt = _build_briefing_prompt(
        agent_id=agent_id,
        role=profile.role,
        department=profile.department,
        context=context,
    )

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
            return None

        return result.stdout.strip()

    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def update_briefing(
    agent_id: str,
    vault_root: Path = None,
    model: str = None,
    force: bool = False,
) -> bool:
    """
    Update an agent's briefing if stale.

    Args:
        agent_id: Agent to update briefing for
        vault_root: Override vault root
        model: Override Claude model
        force: If True, regenerate even if not stale

    Returns:
        True if briefing was updated
    """
    if vault_root is None:
        vault_root = config.VAULT_ROOT

    if not force and not is_briefing_stale(agent_id, vault_root):
        return False

    briefing_content = generate_briefing(agent_id, vault_root, model)
    if briefing_content is None:
        return False

    from . import agent_config

    registry = agent_config.AgentRegistry(vault_root)
    profile = registry.get(agent_id)
    role = profile.role if profile else agent_id.replace("-", " ").title()

    # Write briefing with frontmatter
    briefing_path = vault_zones.get_agent_briefing_path(agent_id, vault_root)
    briefing_path.parent.mkdir(parents=True, exist_ok=True)

    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    full_content = f"""---
tags:
  - agent-briefing
  - auto-maintained
agent: {agent_id}
updated: {now}
---

# {role} Domain Briefing

{briefing_content}
"""

    briefing_path.write_text(full_content, encoding="utf-8")

    # Clear stale marker
    clear_stale_marker(agent_id, vault_root)

    return True
