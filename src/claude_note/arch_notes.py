"""Architecture note generation from GitNexus Leiden communities.

Creates/updates architecture notes in engineering/architecture/
based on communities discovered via GitNexus Cypher queries.
"""

import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from . import config
from . import vault_zones
from . import managed_blocks
from . import gitnexus_client


def _community_to_filename(community_name: str) -> str:
    """Convert community name to a vault-friendly filename."""
    name = community_name.lower()
    name = re.sub(r'[^a-z0-9]+', '-', name).strip('-')
    return f"arch-{name}.md"


def _get_community_detail(client: gitnexus_client.GitNexusClient, community_name: str) -> dict:
    """
    Get detailed community info via Cypher query.

    Returns {name, members: [{name, kind, filePath}], files: [str]}.
    """
    # Get members of this community
    result = client.cypher(
        f"MATCH (s)-[:BELONGS_TO]->(c:Community {{name: '{community_name}'}}) "
        f"RETURN s.name AS name, labels(s)[0] AS kind, s.filePath AS file "
        f"ORDER BY s.name LIMIT 50"
    )

    members = []
    files = set()
    if result:
        markdown = result.get("markdown", "")
        for line in markdown.split("\n"):
            line = line.strip()
            if not line or line.startswith("| ---") or line.startswith("| name"):
                continue
            if line.startswith("|"):
                parts = [p.strip() for p in line.split("|") if p.strip()]
                if len(parts) >= 3:
                    members.append({"name": parts[0], "kind": parts[1], "file": parts[2]})
                    files.add(parts[2])

    return {
        "name": community_name,
        "members": members,
        "files": sorted(files),
        "member_count": len(members),
    }


def generate_community_note(community: dict) -> str:
    """
    Generate markdown content for a community architecture note.

    Args:
        community: Dict with name, members, files, member_count

    Returns:
        Markdown content for managed block
    """
    members = community.get("members", [])
    files = community.get("files", [])
    member_count = community.get("member_count", len(members))

    lines = []
    lines.append(f"**{member_count} symbols** across **{len(files)} files**")
    lines.append("")

    # Member list by kind
    by_kind: dict[str, list] = {}
    for m in members:
        kind = m.get("kind", "Symbol")
        by_kind.setdefault(kind, []).append(m)

    for kind, kind_members in sorted(by_kind.items()):
        lines.append(f"#### {kind}s")
        for m in kind_members[:20]:
            lines.append(f"- `{m['name']}` -- `{m.get('file', '')}`")
        if len(kind_members) > 20:
            lines.append(f"- ... and {len(kind_members) - 20} more")
        lines.append("")

    # File list
    if files:
        lines.append("#### Files")
        for fp in files[:20]:
            lines.append(f"- `{fp}`")
        if len(files) > 20:
            lines.append(f"- ... and {len(files) - 20} more")

    return "\n".join(lines)


def update_community_note(
    community: dict,
    vault_root: Path = None,
) -> Optional[Path]:
    """
    Create or update an architecture note for a community.

    Args:
        community: Dict with name, members, files

    Returns:
        Path to the note, or None on failure
    """
    if vault_root is None:
        vault_root = config.VAULT_ROOT

    name = community.get("name", "")
    if not name:
        return None

    arch_dir = vault_root / "engineering" / "architecture"
    arch_dir.mkdir(parents=True, exist_ok=True)

    filename = _community_to_filename(name)
    note_path = arch_dir / filename

    content = generate_community_note(community)
    block_id = f"community-{re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')}"

    if not note_path.exists():
        now = datetime.utcnow().strftime("%Y-%m-%d")
        frontmatter = f"""---
tags:
  - architecture
  - community
  - auto-maintained
  - engineering
community: {name}
created: {now}
---

# {name}

Architecture note for the `{name}` code community.
Auto-maintained by claude-note GitNexus integration.

<!-- claude-note:{block_id}:start -->
{content}
<!-- claude-note:{block_id}:end -->
"""
        note_path.write_text(frontmatter, encoding="utf-8")
        return note_path

    managed_blocks.write_managed_block(
        note_path,
        block_id,
        content,
        create_if_missing=True,
    )
    return note_path


class ArchitectureNoteGenerator:
    """Generate/update architecture notes from GitNexus communities."""

    def __init__(self, repo_path: str = ".", vault_root: Path = None):
        self.client = gitnexus_client.GitNexusClient(repo_path)
        self.vault_root = vault_root or config.VAULT_ROOT

    def is_available(self) -> bool:
        """Check if GitNexus is available and repo is indexed."""
        return self.client.is_available() and self.client.is_indexed()

    def update_all(self) -> list[Path]:
        """
        Update architecture notes for all communities.

        Uses Cypher queries to discover communities and their members.
        """
        if not self.is_available():
            return []

        # Get all communities via Cypher
        communities = self.client.get_communities_via_cypher()
        updated = []

        for comm_summary in communities:
            name = comm_summary.get("name", "")
            if not name:
                continue

            # Get full detail for each community
            detail = _get_community_detail(self.client, name)
            path = update_community_note(detail, self.vault_root)
            if path:
                updated.append(path)

        return updated

    def update_for_query(self, search_term: str) -> list[Path]:
        """
        Update architecture notes for communities related to a search term.

        Uses `gitnexus query` to find relevant processes, then updates
        notes for the modules those processes touch.
        """
        if not self.is_available():
            return []

        result = self.client.query(search_term, limit=5)
        if not result or not result.symbols:
            return []

        # Collect unique modules from query results
        modules = set()
        for symbol in result.symbols:
            if symbol.module:
                modules.add(symbol.module)

        updated = []
        for module_name in modules:
            detail = _get_community_detail(self.client, module_name)
            if detail.get("members"):
                path = update_community_note(detail, self.vault_root)
                if path:
                    updated.append(path)

        return updated
