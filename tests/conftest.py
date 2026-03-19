"""Shared fixtures for claude-note tests."""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def temp_vault(tmp_path):
    """Create temp vault with v2 department structure and sample notes."""
    vault = tmp_path / "vault"
    vault.mkdir()

    # Create .claude-note directories
    (vault / ".claude-note" / "queue").mkdir(parents=True)
    (vault / ".claude-note" / "state").mkdir(parents=True)
    (vault / ".claude-note" / "logs").mkdir(parents=True)
    (vault / ".claude-note" / "graph").mkdir(parents=True)
    (vault / ".claude-note" / "agents").mkdir(parents=True)

    # Create department structure
    for dept in ["executive", "marketing", "sales", "engineering", "product", "operations"]:
        (vault / dept).mkdir()

    # Create subdirectories
    (vault / "engineering" / "architecture").mkdir()
    (vault / "engineering" / "infrastructure").mkdir()
    (vault / "marketing" / "campaigns").mkdir()
    (vault / "marketing" / "brand").mkdir()
    (vault / "sales" / "pipeline").mkdir()

    # Create _hub
    hub = vault / "_hub"
    hub.mkdir()
    (hub / "decisions-log.md").write_text("""---
tags: [decisions, hub]
---
# Decisions Log
---
""", encoding="utf-8")
    (hub / "strategy.md").write_text("""---
tags: [strategy, hub]
---
# Company Strategy
Enterprise pivot in progress.
""", encoding="utf-8")

    # Create _agents
    agents = vault / "_agents"
    agents.mkdir()
    for agent_id in ["ceo", "cmo", "cto", "head-of-sales"]:
        agent_dir = agents / agent_id
        agent_dir.mkdir()
        (agent_dir / "inbox.md").write_text(f"""---
tags: [inbox, agent-inbox]
agent: {agent_id}
---
# {agent_id.upper()} Inbox
---
""", encoding="utf-8")
        (agent_dir / "briefing.md").write_text(f"""---
tags: [agent-briefing]
agent: {agent_id}
updated: 2026-03-19T08:00:00Z
---
# {agent_id.upper()} Briefing
Sample briefing content.
""", encoding="utf-8")

    # Create sample notes
    (vault / "marketing" / "q2-campaign-plan.md").write_text("""---
tags: [marketing, campaign, q2]
---
# Q2 Campaign Plan
Launch enterprise marketing campaign in April.
Target: 500 MQLs.
[[brand-refresh-2026]]
""", encoding="utf-8")

    (vault / "marketing" / "brand-refresh-2026.md").write_text("""---
tags: [marketing, brand]
---
# Brand Refresh 2026
New brand guidelines for enterprise positioning.
[[q2-campaign-plan]]
""", encoding="utf-8")

    (vault / "engineering" / "architecture" / "auth-subsystem.md").write_text("""---
tags: [engineering, architecture, auth]
---
# Auth Subsystem
Authentication and session management architecture.
""", encoding="utf-8")

    (vault / "sales" / "pipeline" / "enterprise-deals.md").write_text("""---
tags: [sales, pipeline, enterprise]
---
# Enterprise Deals
Q2 pipeline: 12 enterprise prospects.
[[pricing-2026-q2]]
""", encoding="utf-8")

    # Journal
    journal = vault / "journal" / "2026" / "2026-Q1" / "2026-W12"
    journal.mkdir(parents=True)
    (journal / "2026-03-19-ceo-session-abc12345.md").write_text("""---
tags: [log, claude-note]
session_id: abc12345
---
# CEO Session 2026-03-19
Decision to pivot to enterprise.
""", encoding="utf-8")

    return vault


@pytest.fixture
def agent_registry(temp_vault):
    """Agent registry with CEO, CMO, CTO, Head of Sales configs."""
    from claude_note.agent_config import AgentRegistry, AGENT_TEMPLATES

    registry = AgentRegistry(temp_vault)
    for agent_id, template in AGENT_TEMPLATES.items():
        registry.save(template)
    return registry


@pytest.fixture
def sample_vault_index(temp_vault):
    """Build VaultIndex from temp vault."""
    with patch("claude_note.config.VAULT_ROOT", temp_vault), \
         patch("claude_note.config.INDEX_PATH", temp_vault / ".claude-note" / "state" / "vault_index.json"):
        from claude_note.vault_indexer import build_index
        return build_index(temp_vault)


@pytest.fixture
def sample_knowledge_graph(temp_vault, sample_vault_index):
    """KnowledgeGraph synced from sample vault index."""
    from claude_note.mycelium.graph_store import KnowledgeGraph
    from claude_note.mycelium.graph_sync import sync_from_vault_index

    graph = KnowledgeGraph(temp_vault / ".claude-note" / "graph")
    sync_from_vault_index(graph, sample_vault_index, temp_vault)
    return graph


@pytest.fixture
def mock_config(temp_vault):
    """Patch config to use temp vault."""
    with patch("claude_note.config.VAULT_ROOT", temp_vault), \
         patch("claude_note.config.CLAUDE_NOTE_DIR", temp_vault / ".claude-note"), \
         patch("claude_note.config.QUEUE_DIR", temp_vault / ".claude-note" / "queue"), \
         patch("claude_note.config.STATE_DIR", temp_vault / ".claude-note" / "state"), \
         patch("claude_note.config.LOGS_DIR", temp_vault / ".claude-note" / "logs"), \
         patch("claude_note.config.INDEX_PATH", temp_vault / ".claude-note" / "state" / "vault_index.json"):
        yield
