"""Migration from flat vault to v2 structured vault.

Provides tools to migrate existing flat vault notes into
the department-based structure.
"""

import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from . import config
from . import vault_zones
from . import vault_indexer


def detect_vault_version(vault_root: Path = None) -> str:
    """
    Detect current vault structure version.

    Returns:
        'v1' for flat structure, 'v2' for department-based, 'empty' for new
    """
    if vault_root is None:
        vault_root = config.VAULT_ROOT

    hub_path = vault_root / "_hub"
    agents_path = vault_root / "_agents"

    if hub_path.exists() and agents_path.exists():
        return "v2"

    # Check for v1 indicators
    has_notes = any(vault_root.glob("*.md"))
    has_claude_note = (vault_root / ".claude-note").exists()

    if has_notes or has_claude_note:
        return "v1"

    return "empty"


def plan_migration(vault_root: Path = None) -> dict:
    """
    Plan migration from flat to structured vault.

    Returns dict describing planned moves without executing them.
    """
    if vault_root is None:
        vault_root = config.VAULT_ROOT

    plan = {
        "version_from": detect_vault_version(vault_root),
        "moves": [],  # list of (src, dst) tuples
        "creates": [],  # directories to create
        "skips": [],  # files to leave in place
        "warnings": [],
    }

    if plan["version_from"] == "v2":
        plan["warnings"].append("Vault already appears to be v2 structured")
        return plan

    if plan["version_from"] == "empty":
        plan["creates"] = list(vault_zones.DEPARTMENTS.keys()) + ["_hub", "_agents", "journal"]
        return plan

    # Analyze existing notes
    index = vault_indexer.build_index(vault_root)

    for note_path, note_index in index.notes.items():
        src = vault_root / note_path

        # Session notes -> journal/
        if note_path.startswith("claude-session-"):
            # Extract date from filename
            date_match = re.match(r"claude-session-(\d{4}-\d{2}-\d{2})", note_path)
            if date_match:
                date_str = date_match.group(1)
                try:
                    date = datetime.strptime(date_str, "%Y-%m-%d")
                    journal_dir = vault_zones.get_journal_path(date, vault_root)
                    dst = journal_dir / Path(note_path).name
                    plan["moves"].append((str(src), str(dst)))
                except ValueError:
                    plan["skips"].append(note_path)
            continue

        # Inbox -> stays (will be replaced by per-agent inboxes)
        if "inbox" in note_path.lower():
            plan["skips"].append(note_path)
            continue

        # Literature notes -> literature/ (if not already there)
        if note_path.startswith("lit-") or note_path.startswith("literature/"):
            if not note_path.startswith("literature/"):
                dst = vault_root / "literature" / Path(note_path).name
                plan["moves"].append((str(src), str(dst)))
            else:
                plan["skips"].append(note_path)
            continue

        # Try to classify by tags
        dept = _classify_note_by_tags(note_index)
        if dept:
            dst = vault_root / dept / Path(note_path).name
            plan["moves"].append((str(src), str(dst)))
        else:
            plan["skips"].append(note_path)

    return plan


def _classify_note_by_tags(note_index: vault_indexer.NoteIndex) -> Optional[str]:
    """Classify a note into a department based on its tags."""
    tag_to_dept = {
        "marketing": "marketing",
        "brand": "marketing",
        "campaign": "marketing",
        "content": "marketing",
        "sales": "sales",
        "pipeline": "sales",
        "account": "sales",
        "pricing": "sales",
        "engineering": "engineering",
        "architecture": "engineering",
        "infrastructure": "engineering",
        "tech-decision": "engineering",
        "security": "engineering",
        "incident": "engineering",
        "product": "product",
        "roadmap": "product",
        "feature": "product",
        "user-research": "product",
        "strategy": "executive",
        "leadership": "executive",
        "board": "executive",
        "fundraising": "executive",
    }

    dept_scores: dict[str, int] = {}
    for tag in note_index.tags:
        dept = tag_to_dept.get(tag.lower())
        if dept:
            dept_scores[dept] = dept_scores.get(dept, 0) + 1

    if not dept_scores:
        return None

    # Return department with highest score
    return max(dept_scores, key=dept_scores.get)


def execute_migration(plan: dict, vault_root: Path = None, dry_run: bool = False) -> dict:
    """
    Execute a migration plan.

    Args:
        plan: Migration plan from plan_migration()
        vault_root: Override vault root
        dry_run: If True, only report what would be done

    Returns:
        Dict with results
    """
    if vault_root is None:
        vault_root = config.VAULT_ROOT

    results = {
        "moved": 0,
        "created": 0,
        "errors": [],
    }

    # Create v2 structure
    if not dry_run:
        vault_zones.ensure_full_vault_structure(vault_root)

    # Execute moves
    for src_str, dst_str in plan.get("moves", []):
        src = Path(src_str)
        dst = Path(dst_str)

        if not src.exists():
            results["errors"].append(f"Source missing: {src}")
            continue

        if dst.exists():
            results["errors"].append(f"Destination exists: {dst}")
            continue

        if not dry_run:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))

        results["moved"] += 1

    return results


def format_migration_plan(plan: dict) -> str:
    """Format migration plan as human-readable text."""
    lines = [
        f"=== Vault Migration Plan ===",
        f"Current version: {plan['version_from']}",
        "",
    ]

    if plan.get("warnings"):
        lines.append("Warnings:")
        for w in plan["warnings"]:
            lines.append(f"  ! {w}")
        lines.append("")

    if plan.get("moves"):
        lines.append(f"Files to move ({len(plan['moves'])}):")
        for src, dst in plan["moves"][:20]:
            lines.append(f"  {Path(src).name} -> {Path(dst).parent.name}/{Path(dst).name}")
        if len(plan["moves"]) > 20:
            lines.append(f"  ... and {len(plan['moves']) - 20} more")
        lines.append("")

    if plan.get("skips"):
        lines.append(f"Files to skip ({len(plan['skips'])}):")
        for s in plan["skips"][:10]:
            lines.append(f"  {s}")
        if len(plan["skips"]) > 10:
            lines.append(f"  ... and {len(plan['skips']) - 10} more")
        lines.append("")

    if plan.get("creates"):
        lines.append(f"Directories to create: {', '.join(plan['creates'])}")
        lines.append("")

    return "\n".join(lines)
