"""Tests for flat -> structured vault migration."""

from pathlib import Path

from claude_note.migration import detect_vault_version, plan_migration, format_migration_plan


class TestDetectVersion:
    def test_empty_vault(self, tmp_path):
        assert detect_vault_version(tmp_path) == "empty"

    def test_v1_vault(self, tmp_path):
        (tmp_path / ".claude-note").mkdir()
        (tmp_path / "some-note.md").write_text("hello")
        assert detect_vault_version(tmp_path) == "v1"

    def test_v2_vault(self, temp_vault):
        assert detect_vault_version(temp_vault) == "v2"


class TestPlanMigration:
    def test_v2_already_migrated(self, temp_vault):
        plan = plan_migration(temp_vault)
        assert "already appears to be v2" in plan["warnings"][0]

    def test_empty_vault_plan(self, tmp_path):
        plan = plan_migration(tmp_path)
        assert plan["version_from"] == "empty"
        assert len(plan["creates"]) > 0

    def test_format_plan(self, tmp_path):
        plan = plan_migration(tmp_path)
        output = format_migration_plan(plan)
        assert "Migration Plan" in output
