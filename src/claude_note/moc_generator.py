"""MOC (Map of Content) generator for department folders.

Auto-maintains _moc-{department}.md files with categorized
lists of notes in each department folder.
"""

import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from . import config
from . import vault_zones
from . import vault_indexer
from . import managed_blocks


def _categorize_notes(notes: list[vault_indexer.NoteIndex]) -> dict[str, list[vault_indexer.NoteIndex]]:
    """
    Categorize notes by their subfolder.

    Returns dict of subfolder -> notes list.
    """
    categories: dict[str, list[vault_indexer.NoteIndex]] = {}

    for note in notes:
        parts = Path(note.path).parts
        if len(parts) >= 2:
            category = parts[1]  # First subfolder under department
        else:
            category = "general"

        if category not in categories:
            categories[category] = []
        categories[category].append(note)

    return categories


def _format_note_entry(note: vault_indexer.NoteIndex) -> str:
    """Format a single note as a MOC entry."""
    name = Path(note.path).stem
    tags_str = ""
    if note.tags:
        tags_str = " " + " ".join(f"#{t}" for t in note.tags[:3])

    preview = note.preview[:80] + "..." if len(note.preview) > 80 else note.preview

    if preview:
        return f"- [[{name}]] - {preview}{tags_str}"
    return f"- [[{name}]]{tags_str}"


def generate_moc_content(department: str, vault_root: Path = None) -> str:
    """
    Generate MOC content for a department.

    Args:
        department: Department name
        vault_root: Override vault root

    Returns:
        Formatted markdown content for the managed block
    """
    if vault_root is None:
        vault_root = config.VAULT_ROOT

    dept_path = vault_zones.get_department_path(department, vault_root)
    if not dept_path.exists():
        return "(Department folder not found)"

    # Get all notes in department
    index = vault_indexer.get_index()
    dept_notes = [
        note for path, note in index.notes.items()
        if path.startswith(f"{department}/") and not Path(path).name.startswith("_moc-")
    ]

    if not dept_notes:
        return "(No notes in this department yet)"

    # Categorize
    categories = _categorize_notes(dept_notes)

    lines = []
    lines.append(f"**{len(dept_notes)} notes** (updated {datetime.utcnow().strftime('%Y-%m-%d %H:%M')})")
    lines.append("")

    for category, notes in sorted(categories.items()):
        # Capitalize and format category name
        cat_title = category.replace("-", " ").replace("_", " ").title()
        lines.append(f"#### {cat_title}")

        # Sort by mtime descending
        notes.sort(key=lambda n: n.mtime, reverse=True)

        for note in notes:
            lines.append(_format_note_entry(note))

        lines.append("")

    return "\n".join(lines)


def update_moc(department: str, vault_root: Path = None) -> bool:
    """
    Update MOC for a department.

    Args:
        department: Department name
        vault_root: Override vault root

    Returns:
        True if MOC was updated
    """
    if vault_root is None:
        vault_root = config.VAULT_ROOT

    moc_path = vault_zones.get_moc_path(department, vault_root)

    # Ensure MOC file exists
    if not moc_path.exists():
        vault_zones.ensure_department_structure(department, vault_root)

    if not moc_path.exists():
        return False

    # Generate content
    content = generate_moc_content(department, vault_root)

    # Update managed block
    block_id = f"moc-{department}"
    return managed_blocks.write_managed_block(
        moc_path,
        block_id,
        content,
        create_if_missing=True,
    )


def update_all_mocs(vault_root: Path = None) -> list[str]:
    """
    Update MOCs for all departments.

    Returns list of departments that were updated.
    """
    if vault_root is None:
        vault_root = config.VAULT_ROOT

    updated = []

    for department in vault_zones.DEPARTMENTS:
        dept_path = vault_zones.get_department_path(department, vault_root)
        if dept_path.exists():
            if update_moc(department, vault_root):
                updated.append(department)

    return updated


def update_hub_moc(vault_root: Path = None) -> bool:
    """
    Update the master company-brain.md MOC in _hub/.

    Lists all departments and their note counts.
    """
    if vault_root is None:
        vault_root = config.VAULT_ROOT

    hub_path = vault_zones.get_hub_path(vault_root)
    brain_path = hub_path / "company-brain.md"

    if not brain_path.exists():
        return False

    index = vault_indexer.get_index()

    lines = []
    lines.append(f"Updated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}")
    lines.append("")

    for dept, info in vault_zones.DEPARTMENTS.items():
        dept_notes = [
            n for p, n in index.notes.items()
            if p.startswith(f"{dept}/")
        ]
        count = len(dept_notes)
        lines.append(f"- **[[_moc-{dept}|{info['name']}]]**: {count} notes")

    # Hub notes
    hub_notes = [n for p, n in index.notes.items() if p.startswith("_hub/")]
    lines.append(f"- **Hub**: {len(hub_notes)} cross-functional documents")

    lines.append("")
    lines.append(f"**Total**: {len(index.notes)} notes in vault")

    content = "\n".join(lines)

    return managed_blocks.write_managed_block(
        brain_path,
        "vault-stats",
        content,
        create_if_missing=True,
    )
