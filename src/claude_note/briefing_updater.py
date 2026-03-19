"""Briefing updater for cross-agent decision propagation.

When a session produces decisions or cross-functional knowledge,
this module marks affected agents' briefings as stale so they
get regenerated before those agents' next sessions.
"""

import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from . import config
from . import vault_zones
from . import agent_config
from . import briefing_generator
from . import managed_blocks


def propagate_decision(
    decision_text: str,
    source_agent_id: str,
    rationale: str = "",
    impacted_departments: list[str] = None,
    vault_root: Path = None,
) -> dict:
    """
    Propagate a decision to the hub decisions log and mark affected briefings stale.

    Args:
        decision_text: The decision statement
        source_agent_id: Agent who made the decision
        rationale: Why the decision was made
        impacted_departments: List of affected departments
        vault_root: Override vault root

    Returns:
        Dict with 'logged', 'agents_marked_stale'
    """
    if vault_root is None:
        vault_root = config.VAULT_ROOT

    results = {
        "logged": False,
        "agents_marked_stale": [],
    }

    # 1. Append to decisions log
    decisions_path = vault_zones.get_decisions_log_path(vault_root)
    decisions_path.parent.mkdir(parents=True, exist_ok=True)

    now = datetime.utcnow()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M")

    # Build decision entry
    entry_lines = [
        f"### {decision_text} ({source_agent_id.upper()}, {date_str})",
        f"- **Decision:** {decision_text}",
    ]
    if rationale:
        entry_lines.append(f"- **Rationale:** {rationale}")
    if impacted_departments:
        entry_lines.append(f"- **Impacts:** {', '.join(impacted_departments)}")
    entry_lines.append(f"- **Time:** {time_str}")
    entry_lines.append("")

    entry = "\n".join(entry_lines)

    if decisions_path.exists():
        content = decisions_path.read_text(encoding="utf-8")
        content = content.rstrip() + "\n\n" + entry
        decisions_path.write_text(content, encoding="utf-8")
    else:
        header = """---
tags:
  - decisions
  - hub
  - auto-maintained
---

# Decisions Log

All major decisions, chronologically. Auto-appended by claude-note.

---

"""
        decisions_path.write_text(header + entry, encoding="utf-8")

    results["logged"] = True

    # 2. Mark affected agents' briefings as stale
    if impacted_departments:
        registry = agent_config.AgentRegistry(vault_root)
        for profile in registry.get_all():
            if profile.agent_id == source_agent_id:
                continue

            # Check if this agent's department is impacted
            if profile.department in impacted_departments:
                briefing_generator.mark_briefing_stale(profile.agent_id, vault_root)
                results["agents_marked_stale"].append(profile.agent_id)
            else:
                # Also check if any primary/secondary folder overlaps
                for dept in impacted_departments:
                    dept_folder = f"{dept}/"
                    if dept_folder in profile.primary_folders or dept_folder in profile.secondary_folders:
                        briefing_generator.mark_briefing_stale(profile.agent_id, vault_root)
                        results["agents_marked_stale"].append(profile.agent_id)
                        break
    else:
        # No specific departments - mark ALL other agents as stale
        registry = agent_config.AgentRegistry(vault_root)
        for profile in registry.get_all():
            if profile.agent_id != source_agent_id:
                briefing_generator.mark_briefing_stale(profile.agent_id, vault_root)
                results["agents_marked_stale"].append(profile.agent_id)

    return results


def propagate_cross_department_question(
    question: str,
    source_agent_id: str,
    target_agent_id: str,
    context: str = "",
    vault_root: Path = None,
) -> bool:
    """
    Add a question to a target agent's briefing.

    Args:
        question: The question text
        source_agent_id: Agent asking the question
        target_agent_id: Agent who should answer
        context: Additional context
        vault_root: Override vault root

    Returns:
        True if question was added
    """
    if vault_root is None:
        vault_root = config.VAULT_ROOT

    briefing_path = vault_zones.get_agent_briefing_path(target_agent_id, vault_root)
    if not briefing_path.exists():
        vault_zones.ensure_agent_structure(target_agent_id, vault_root=vault_root)

    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    question_text = f"- [ ] ({date_str}, from {source_agent_id}) {question}"
    if context:
        question_text += f"\n  - Context: {context}"

    # Append to Open Domain Questions section
    return managed_blocks.append_to_section(
        briefing_path,
        "## Open Domain Questions",
        question_text,
        create_section=True,
    )


def mark_stale_for_departments(
    departments: list[str],
    exclude_agent_id: str = None,
    vault_root: Path = None,
) -> list[str]:
    """
    Mark briefings stale for all agents in given departments.

    Returns list of agent IDs marked stale.
    """
    if vault_root is None:
        vault_root = config.VAULT_ROOT

    marked = []
    registry = agent_config.AgentRegistry(vault_root)

    for profile in registry.get_all():
        if profile.agent_id == exclude_agent_id:
            continue

        if profile.department in departments:
            briefing_generator.mark_briefing_stale(profile.agent_id, vault_root)
            marked.append(profile.agent_id)

    return marked
