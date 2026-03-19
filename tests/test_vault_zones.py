"""Tests for vault zone management."""

from claude_note.vault_zones import (
    ensure_department_structure, ensure_hub_structure, ensure_agent_structure,
    resolve_note_department, resolve_note_zone, get_session_note_path,
    get_moc_path, get_decisions_log_path, DEPARTMENTS,
)
from datetime import datetime


class TestVaultZones:
    def test_ensure_department_structure(self, tmp_path):
        created = ensure_department_structure("marketing", tmp_path)
        assert (tmp_path / "marketing").exists()
        assert (tmp_path / "marketing" / "campaigns").exists()
        assert (tmp_path / "marketing" / "_moc-marketing.md").exists()

    def test_ensure_hub_structure(self, tmp_path):
        created = ensure_hub_structure(tmp_path)
        assert (tmp_path / "_hub").exists()
        assert (tmp_path / "_hub" / "decisions-log.md").exists()
        assert (tmp_path / "_hub" / "strategy.md").exists()

    def test_ensure_agent_structure(self, tmp_path):
        created = ensure_agent_structure("cmo", "Chief Marketing Officer", tmp_path)
        assert (tmp_path / "_agents" / "cmo").exists()
        assert (tmp_path / "_agents" / "cmo" / "CLAUDE.md").exists()
        assert (tmp_path / "_agents" / "cmo" / "briefing.md").exists()
        assert (tmp_path / "_agents" / "cmo" / "inbox.md").exists()

    def test_resolve_note_department(self):
        assert resolve_note_department("marketing/campaigns/q2.md") == "marketing"
        assert resolve_note_department("engineering/arch.md") == "engineering"
        assert resolve_note_department("_hub/strategy.md") is None
        assert resolve_note_department("random-note.md") is None

    def test_resolve_note_zone(self):
        assert resolve_note_zone("_hub/strategy.md") == "hub"
        assert resolve_note_zone("_agents/cmo/briefing.md") == "agents"
        assert resolve_note_zone("journal/2026/note.md") == "journal"
        assert resolve_note_zone("marketing/campaign.md") == "department:marketing"
        assert resolve_note_zone("random.md") == "root"

    def test_session_note_path(self, tmp_path):
        dt = datetime(2026, 3, 19)
        path = get_session_note_path("ceo", "abc12345678", dt, tmp_path)
        assert "2026-03-19" in str(path)
        assert "ceo" in str(path)
        assert "abc12345" in str(path)

    def test_moc_path(self, tmp_path):
        path = get_moc_path("engineering", tmp_path)
        assert path.name == "_moc-engineering.md"

    def test_all_departments_have_subfolders(self):
        for dept, info in DEPARTMENTS.items():
            assert len(info["subfolders"]) > 0
            assert info["moc_title"]
