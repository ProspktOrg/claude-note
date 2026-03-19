"""Classifier job for processing agent inboxes.

Runs periodically (via systemd timer / launchd / Task Scheduler) to:
1. Scan all _agents/*/inbox.md for unprocessed entries
2. Classify ambiguous items using Claude CLI
3. Route to final department folders
4. Update MOCs for departments that received new notes
5. Regenerate stale briefings
6. Detect cross-agent conflicts
"""

import json
import logging
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

from . import config
from . import vault_zones
from . import agent_config
from . import briefing_generator
from . import managed_blocks


def setup_logging(verbose: bool = False) -> logging.Logger:
    """Configure logging for classifier job."""
    config.LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_file = config.LOGS_DIR / f"classifier-{datetime.utcnow().strftime('%Y-%m-%d')}.log"

    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler() if verbose else logging.NullHandler(),
        ],
    )
    return logging.getLogger("claude-note-classifier")


def _parse_inbox_entries(inbox_path: Path) -> list[dict]:
    """Parse inbox.md into list of entry dicts."""
    if not inbox_path.exists():
        return []

    content = inbox_path.read_text(encoding="utf-8")

    # Split by ## headers
    entry_pattern = re.compile(
        r"^## (\d{4}-\d{2}-\d{2})(?:\s+(\d{2}:\d{2}:\d{2}))?\s*-\s*(.+)$",
        re.MULTILINE,
    )

    matches = list(entry_pattern.finditer(content))
    entries = []

    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)

        entry_content = content[start:end].strip()

        # Check if already processed
        if "<!-- classified -->" in entry_content:
            continue

        entries.append({
            "date": match.group(1),
            "time": match.group(2) or "",
            "title": match.group(3),
            "content": entry_content,
            "start": start,
            "end": end,
        })

    return entries


def _classify_entry(entry: dict, available_departments: list[str], model: str = None) -> dict:
    """
    Classify an inbox entry using Claude CLI.

    Returns dict with 'department', 'note_type', 'filename', 'confidence'.
    """
    if model is None:
        model = config.SYNTH_MODEL

    departments_str = ", ".join(available_departments)

    prompt = f"""Classify this knowledge entry into the correct department.

Available departments: {departments_str}

Entry:
{entry['content'][:2000]}

Return a JSON object:
{{
    "department": "one of [{departments_str}]",
    "note_type": "concept | decision | howto | insight",
    "suggested_filename": "kebab-case-name.md",
    "confidence": 0.0-1.0,
    "cross_departments": ["other departments this affects"]
}}

Return ONLY valid JSON.
"""

    env = os.environ.copy()
    env["CLAUDE_CODE_HOOKS_ENABLED"] = "false"

    try:
        result = subprocess.run(
            ["claude", "-p", prompt, "--model", model],
            capture_output=True,
            text=True,
            env=env,
            timeout=60,
        )

        if result.returncode != 0:
            return {"department": "", "confidence": 0.0}

        output = result.stdout.strip()
        # Extract JSON
        json_match = re.search(r'\{[\s\S]*\}', output)
        if json_match:
            return json.loads(json_match.group())

        return {"department": "", "confidence": 0.0}

    except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError):
        return {"department": "", "confidence": 0.0}


def _route_entry_to_department(
    entry: dict,
    classification: dict,
    vault_root: Path,
    logger: logging.Logger,
) -> Optional[Path]:
    """
    Route a classified entry to its department folder.

    Returns path to created note, or None on failure.
    """
    department = classification.get("department", "")
    if not department or department not in vault_zones.DEPARTMENTS:
        return None

    filename = classification.get("suggested_filename", "")
    if not filename:
        # Generate from title
        title = entry["title"]
        filename = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-') + ".md"

    if not filename.endswith(".md"):
        filename += ".md"

    dept_path = vault_zones.get_department_path(department, vault_root)
    note_path = dept_path / filename

    if note_path.exists():
        # Append as managed block
        block_id = f"classified-{entry['date']}"
        managed_blocks.write_managed_block(
            note_path,
            block_id,
            entry["content"],
            create_if_missing=True,
        )
        logger.info(f"Appended to existing note: {note_path.name}")
        return note_path

    # Create new note
    note_type = classification.get("note_type", "concept")
    tags = [department, note_type, "auto-classified"]
    cross_depts = classification.get("cross_departments", [])
    if cross_depts:
        tags.extend(cross_depts)

    frontmatter = f"""---
tags:
  - {chr(10) + '  - '.join(tags)}
created: {entry['date']}
classified_from: {entry.get('agent_id', 'unknown')}
---

"""

    dept_path.mkdir(parents=True, exist_ok=True)
    note_path.write_text(frontmatter + entry["content"], encoding="utf-8")
    logger.info(f"Created note: {note_path.name} in {department}/")

    return note_path


def _mark_entry_classified(inbox_path: Path, entry: dict) -> None:
    """Mark an inbox entry as classified."""
    if not inbox_path.exists():
        return

    content = inbox_path.read_text(encoding="utf-8")

    # Add classified marker after the entry header
    header_line = f"## {entry['date']}"
    if entry.get("time"):
        header_line += f" {entry['time']}"
    header_line += f" - {entry['title']}"

    marker = f"{header_line}\n<!-- classified -->"
    content = content.replace(header_line, marker, 1)

    inbox_path.write_text(content, encoding="utf-8")


def scan_and_classify(
    vault_root: Path = None,
    model: str = None,
    dry_run: bool = False,
    logger: logging.Logger = None,
) -> dict:
    """
    Scan all agent inboxes and classify/route entries.

    Returns dict with results per agent.
    """
    if vault_root is None:
        vault_root = config.VAULT_ROOT
    if logger is None:
        logger = logging.getLogger("claude-note-classifier")

    available_departments = list(vault_zones.DEPARTMENTS.keys())
    results = {
        "agents_scanned": 0,
        "entries_found": 0,
        "entries_classified": 0,
        "entries_routed": 0,
        "errors": [],
    }

    agents_path = vault_zones.get_agents_path(vault_root)
    if not agents_path.exists():
        return results

    for agent_dir in agents_path.iterdir():
        if not agent_dir.is_dir():
            continue

        agent_id = agent_dir.name
        inbox_path = agent_dir / "inbox.md"

        entries = _parse_inbox_entries(inbox_path)
        if not entries:
            continue

        results["agents_scanned"] += 1
        results["entries_found"] += len(entries)

        logger.info(f"Processing {len(entries)} entries from {agent_id} inbox")

        for entry in entries:
            entry["agent_id"] = agent_id

            # Classify
            classification = _classify_entry(entry, available_departments, model)
            results["entries_classified"] += 1

            confidence = classification.get("confidence", 0.0)
            if confidence < 0.5:
                logger.debug(f"Low confidence ({confidence:.2f}) for: {entry['title']}")
                continue

            if dry_run:
                logger.info(f"Would route '{entry['title']}' to {classification.get('department', '?')}")
                continue

            # Route
            note_path = _route_entry_to_department(entry, classification, vault_root, logger)
            if note_path:
                results["entries_routed"] += 1
                _mark_entry_classified(inbox_path, entry)

    return results


def regenerate_stale_briefings(
    vault_root: Path = None,
    model: str = None,
    logger: logging.Logger = None,
) -> list[str]:
    """
    Regenerate all stale agent briefings.

    Returns list of agent IDs whose briefings were updated.
    """
    if vault_root is None:
        vault_root = config.VAULT_ROOT
    if logger is None:
        logger = logging.getLogger("claude-note-classifier")

    updated = []
    registry = agent_config.AgentRegistry(vault_root)

    for aid in registry.list_agents():
        if briefing_generator.is_briefing_stale(aid, vault_root):
            logger.info(f"Regenerating stale briefing for {aid}")
            if briefing_generator.update_briefing(aid, vault_root, model):
                updated.append(aid)
                logger.info(f"Updated briefing for {aid}")

    return updated


def detect_conflicts(
    vault_root: Path = None,
    logger: logging.Logger = None,
) -> list[dict]:
    """
    Detect cross-agent conflicts (contradictory decisions/assertions).

    Returns list of conflict descriptions.
    """
    # Simplified conflict detection: look for same-day decisions
    # from different agents that mention similar topics
    if vault_root is None:
        vault_root = config.VAULT_ROOT
    if logger is None:
        logger = logging.getLogger("claude-note-classifier")

    conflicts = []
    # TODO: Implement semantic conflict detection
    # For now, return empty list
    return conflicts


def run_classifier_job(
    vault_root: Path = None,
    model: str = None,
    dry_run: bool = False,
    verbose: bool = False,
) -> dict:
    """
    Run the full classifier job.

    1. Scan and classify inbox entries
    2. Update MOCs
    3. Regenerate stale briefings
    4. Detect conflicts
    """
    logger = setup_logging(verbose)
    logger.info("Classifier job starting")

    results = {
        "classification": {},
        "mocs_updated": [],
        "briefings_updated": [],
        "conflicts": [],
    }

    # 1. Classify and route
    results["classification"] = scan_and_classify(vault_root, model, dry_run, logger)

    # 2. Update MOCs
    if not dry_run:
        from . import moc_generator
        try:
            results["mocs_updated"] = moc_generator.update_all_mocs(vault_root)
        except Exception as e:
            logger.error(f"MOC update failed: {e}")

    # 3. Regenerate stale briefings
    if not dry_run:
        results["briefings_updated"] = regenerate_stale_briefings(vault_root, model, logger)

    # 4. Detect conflicts
    results["conflicts"] = detect_conflicts(vault_root, logger)
    if results["conflicts"]:
        logger.warning(f"Found {len(results['conflicts'])} cross-agent conflicts")

    logger.info("Classifier job complete")
    return results
