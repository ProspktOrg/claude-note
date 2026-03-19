"""Vault zone management for multi-agent company brain.

Handles department folder structure, _hub/ cross-functional area,
_agents/ per-agent directories, and journal/ temporal notes.
"""

from datetime import datetime
from pathlib import Path
from typing import Optional

from . import config


# Department definitions
DEPARTMENTS = {
    "executive": {
        "name": "Executive",
        "subfolders": ["board-updates", "fundraising", "leadership"],
        "moc_title": "Executive",
    },
    "marketing": {
        "name": "Marketing",
        "subfolders": ["campaigns", "brand", "content-strategy", "analytics"],
        "moc_title": "Marketing",
    },
    "sales": {
        "name": "Sales",
        "subfolders": ["pipeline", "accounts", "playbooks", "pricing"],
        "moc_title": "Sales",
    },
    "engineering": {
        "name": "Engineering",
        "subfolders": ["architecture", "infrastructure", "incidents", "tech-decisions"],
        "moc_title": "Engineering",
    },
    "product": {
        "name": "Product",
        "subfolders": ["roadmap", "features", "user-research"],
        "moc_title": "Product",
    },
    "operations": {
        "name": "Operations",
        "subfolders": ["processes", "playbooks", "templates"],
        "moc_title": "Operations",
    },
}

# Hub files that should exist
HUB_FILES = [
    "company-brain.md",
    "strategy.md",
    "okrs.md",
    "decisions-log.md",
    "customer-insights.md",
    "competitive-landscape.md",
    "weekly-sync.md",
]


def get_department_path(department: str, vault_root: Path = None) -> Path:
    """Get the root path for a department."""
    if vault_root is None:
        vault_root = config.VAULT_ROOT
    return vault_root / department


def get_hub_path(vault_root: Path = None) -> Path:
    """Get the _hub/ path."""
    if vault_root is None:
        vault_root = config.VAULT_ROOT
    return vault_root / "_hub"


def get_agents_path(vault_root: Path = None) -> Path:
    """Get the _agents/ path."""
    if vault_root is None:
        vault_root = config.VAULT_ROOT
    return vault_root / "_agents"


def get_agent_dir(agent_id: str, vault_root: Path = None) -> Path:
    """Get the _agents/{agent_id}/ path."""
    return get_agents_path(vault_root) / agent_id


def get_journal_path(date: datetime = None, vault_root: Path = None) -> Path:
    """Get journal path for a date (journal/YYYY/YYYY-QN/YYYY-WNN/)."""
    if vault_root is None:
        vault_root = config.VAULT_ROOT
    if date is None:
        date = datetime.utcnow()

    year = date.strftime("%Y")
    quarter = f"{year}-Q{(date.month - 1) // 3 + 1}"
    week = f"{year}-W{date.isocalendar()[1]:02d}"

    return vault_root / "journal" / year / quarter / week


def get_session_note_path(
    agent_id: str,
    session_id: str,
    date: datetime = None,
    vault_root: Path = None,
) -> Path:
    """Get path for a session note in the journal."""
    journal_dir = get_journal_path(date, vault_root)
    if date is None:
        date = datetime.utcnow()
    date_str = date.strftime("%Y-%m-%d")
    short_id = session_id[:8]
    filename = f"{date_str}-{agent_id}-session-{short_id}.md"
    return journal_dir / filename


def get_moc_path(department: str, vault_root: Path = None) -> Path:
    """Get the MOC (Map of Content) path for a department."""
    dept_path = get_department_path(department, vault_root)
    return dept_path / f"_moc-{department}.md"


def get_decisions_log_path(vault_root: Path = None) -> Path:
    """Get path to the cross-functional decisions log."""
    return get_hub_path(vault_root) / "decisions-log.md"


def get_agent_inbox_path(agent_id: str, vault_root: Path = None) -> Path:
    """Get path to an agent's inbox."""
    return get_agent_dir(agent_id, vault_root) / "inbox.md"


def get_agent_briefing_path(agent_id: str, vault_root: Path = None) -> Path:
    """Get path to an agent's auto-generated briefing."""
    return get_agent_dir(agent_id, vault_root) / "briefing.md"


def get_agent_claude_md_path(agent_id: str, vault_root: Path = None) -> Path:
    """Get path to an agent's CLAUDE.md."""
    return get_agent_dir(agent_id, vault_root) / "CLAUDE.md"


def ensure_department_structure(department: str, vault_root: Path = None) -> list[Path]:
    """
    Ensure department folder structure exists.

    Returns list of created directories.
    """
    dept_info = DEPARTMENTS.get(department)
    if dept_info is None:
        return []

    dept_path = get_department_path(department, vault_root)
    created = []

    dept_path.mkdir(parents=True, exist_ok=True)
    created.append(dept_path)

    for subfolder in dept_info["subfolders"]:
        sub_path = dept_path / subfolder
        if not sub_path.exists():
            sub_path.mkdir(parents=True, exist_ok=True)
            created.append(sub_path)

    # Create MOC file if missing
    moc_path = get_moc_path(department, vault_root)
    if not moc_path.exists():
        moc_content = f"""---
tags:
  - moc
  - {department}
  - auto-maintained
---

# {dept_info['moc_title']}

Map of Content for the {dept_info['name']} department.

<!-- claude-note:moc-{department}:start -->
(Auto-populated by claude-note)
<!-- claude-note:moc-{department}:end -->
"""
        moc_path.write_text(moc_content, encoding="utf-8")

    return created


def ensure_hub_structure(vault_root: Path = None) -> list[Path]:
    """Ensure _hub/ cross-functional area exists with template files."""
    hub_path = get_hub_path(vault_root)
    hub_path.mkdir(parents=True, exist_ok=True)
    created = [hub_path]

    hub_templates = {
        "company-brain.md": """---
tags:
  - moc
  - hub
---

# Company Brain

Master Map of Content. Auto-maintained by claude-note.

## Departments

- [[_moc-executive|Executive]]
- [[_moc-marketing|Marketing]]
- [[_moc-sales|Sales]]
- [[_moc-engineering|Engineering]]
- [[_moc-product|Product]]
- [[_moc-operations|Operations]]

## Key Documents

- [[strategy]]
- [[okrs]]
- [[decisions-log]]
""",
        "strategy.md": """---
tags:
  - strategy
  - hub
---

# Company Strategy

(Maintained by CEO agent and cross-functional input)
""",
        "okrs.md": """---
tags:
  - okr
  - hub
---

# Quarterly OKRs

(Maintained by CEO agent)
""",
        "decisions-log.md": """---
tags:
  - decisions
  - hub
  - auto-maintained
---

# Decisions Log

All major decisions, chronologically. Auto-appended by claude-note.

---

""",
        "customer-insights.md": """---
tags:
  - customer-insight
  - hub
---

# Customer Insights

Shared customer intelligence across departments.
""",
        "competitive-landscape.md": """---
tags:
  - competitive
  - hub
---

# Competitive Landscape

Competitor analysis and market positioning.
""",
        "weekly-sync.md": """---
tags:
  - sync
  - hub
---

# Weekly Sync

Cross-department synchronization notes.
""",
    }

    for filename, content in hub_templates.items():
        file_path = hub_path / filename
        if not file_path.exists():
            file_path.write_text(content, encoding="utf-8")
            created.append(file_path)

    return created


def ensure_agent_structure(agent_id: str, role: str = "", vault_root: Path = None) -> list[Path]:
    """Ensure _agents/{agent_id}/ directory exists with templates."""
    agent_dir = get_agent_dir(agent_id, vault_root)
    agent_dir.mkdir(parents=True, exist_ok=True)
    created = [agent_dir]

    # CLAUDE.md for agent
    claude_md = agent_dir / "CLAUDE.md"
    if not claude_md.exists():
        role_title = role or agent_id.replace("-", " ").title()
        claude_md.write_text(f"""# {role_title} Vault Navigation

You are the {role_title}. This vault contains domain knowledge for your work.

## Your Primary Areas
See briefing.md for current domain context.

## How to Use This Vault
- Check briefing.md at the start of each session
- Your inbox.md contains unprocessed items for review
- Hub documents in _hub/ are shared across all agents
""", encoding="utf-8")
        created.append(claude_md)

    # Briefing
    briefing = agent_dir / "briefing.md"
    if not briefing.exists():
        briefing.write_text(f"""---
tags:
  - agent-briefing
  - auto-maintained
agent: {agent_id}
updated: {datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')}
---

# {role or agent_id.replace('-', ' ').title()} Domain Briefing

(Auto-generated. Will be populated after first session synthesis.)
""", encoding="utf-8")
        created.append(briefing)

    # Inbox
    inbox = agent_dir / "inbox.md"
    if not inbox.exists():
        inbox.write_text(f"""---
tags:
  - inbox
  - agent-inbox
  - auto-maintained
agent: {agent_id}
---

# {role or agent_id.replace('-', ' ').title()} Inbox

Unprocessed synthesis output. Reviewed by classifier job.

---

""", encoding="utf-8")
        created.append(inbox)

    return created


def ensure_full_vault_structure(vault_root: Path = None, agent_ids: list[str] = None) -> dict:
    """
    Ensure full v2 vault structure exists.

    Returns dict of created paths by category.
    """
    if vault_root is None:
        vault_root = config.VAULT_ROOT

    results = {
        "hub": [],
        "departments": {},
        "agents": {},
        "other": [],
    }

    # Hub
    results["hub"] = ensure_hub_structure(vault_root)

    # Departments
    for dept in DEPARTMENTS:
        results["departments"][dept] = ensure_department_structure(dept, vault_root)

    # Agents base dir + shared CLAUDE.md
    agents_path = get_agents_path(vault_root)
    agents_path.mkdir(parents=True, exist_ok=True)

    shared_claude = agents_path / "CLAUDE.md"
    if not shared_claude.exists():
        shared_claude.write_text("""# Shared Agent Rules

These rules apply to ALL agents using this vault.

## Knowledge Extraction
- Only extract genuinely durable knowledge
- Use existing vault tags when they fit
- Cross-reference related notes with [[wikilinks]]

## Vault Conventions
- Department folders contain domain-specific knowledge
- _hub/ contains cross-functional documents
- Decisions go to _hub/decisions-log.md
- Each agent has briefing.md (auto-updated) and inbox.md
""", encoding="utf-8")

    # Agent directories
    if agent_ids:
        from . import agent_config
        for aid in agent_ids:
            template = agent_config.AGENT_TEMPLATES.get(aid)
            role = template.role if template else ""
            results["agents"][aid] = ensure_agent_structure(aid, role, vault_root)

    # Journal
    journal_path = vault_root / "journal"
    journal_path.mkdir(parents=True, exist_ok=True)
    results["other"].append(journal_path)

    # Literature (existing)
    lit_path = vault_root / "literature"
    lit_path.mkdir(parents=True, exist_ok=True)

    # Operations
    ops_path = vault_root / "operations"
    ops_path.mkdir(parents=True, exist_ok=True)

    return results


def resolve_note_department(note_path: str) -> Optional[str]:
    """
    Determine which department a note belongs to based on its path.

    Args:
        note_path: Relative path from vault root

    Returns:
        Department name or None if not in a department
    """
    normalized = note_path.replace("\\", "/").strip("/")
    parts = normalized.split("/")

    if not parts:
        return None

    first_dir = parts[0]
    if first_dir in DEPARTMENTS:
        return first_dir

    return None


def resolve_note_zone(note_path: str) -> str:
    """
    Determine which zone a note belongs to.

    Returns one of: 'hub', 'agents', 'journal', 'department:{name}',
    'literature', 'operations', 'root'
    """
    normalized = note_path.replace("\\", "/").strip("/")
    parts = normalized.split("/")

    if not parts:
        return "root"

    first_dir = parts[0]

    if first_dir == "_hub":
        return "hub"
    elif first_dir == "_agents":
        return "agents"
    elif first_dir == "journal":
        return "journal"
    elif first_dir == "literature":
        return "literature"
    elif first_dir == "operations":
        return "operations"
    elif first_dir in DEPARTMENTS:
        return f"department:{first_dir}"
    else:
        return "root"
