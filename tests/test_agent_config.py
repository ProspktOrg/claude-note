"""Tests for agent configuration."""

import os
from unittest.mock import patch

import pytest
from claude_note.agent_config import (
    AgentProfile, AgentRegistry, get_current_agent_id,
    get_current_agent, AGENT_TEMPLATES, DEFAULT_AGENT_ID,
)


class TestAgentProfile:
    def test_create_profile(self):
        profile = AgentProfile(agent_id="cmo", role="CMO", department="marketing")
        assert profile.agent_id == "cmo"
        assert profile.department == "marketing"

    def test_serialization_roundtrip(self):
        profile = AGENT_TEMPLATES["cmo"]
        json_str = profile.to_json()
        restored = AgentProfile.from_json(json_str)
        assert restored.agent_id == "cmo"
        assert restored.department == "marketing"
        assert "marketing" in restored.tags_primary

    def test_owns_folder(self):
        profile = AGENT_TEMPLATES["cmo"]
        assert profile.owns_folder("marketing/campaigns/q2")
        assert not profile.owns_folder("engineering/architecture")

    def test_can_access_folder(self):
        profile = AGENT_TEMPLATES["cmo"]
        assert profile.can_access_folder("marketing/campaigns")
        assert profile.can_access_folder("sales/pipeline")  # secondary
        assert not profile.can_access_folder("engineering/infrastructure")  # excluded

    def test_owns_tag(self):
        profile = AGENT_TEMPLATES["cmo"]
        assert profile.owns_tag("marketing")
        assert profile.owns_tag("brand")
        assert not profile.owns_tag("engineering")


class TestAgentRegistry:
    def test_save_and_load(self, temp_vault):
        registry = AgentRegistry(temp_vault)
        profile = AgentProfile(agent_id="test-agent", role="Tester", department="engineering")
        registry.save(profile)

        loaded = registry.get("test-agent")
        assert loaded is not None
        assert loaded.role == "Tester"

    def test_list_agents(self, temp_vault, agent_registry):
        agents = agent_registry.list_agents()
        assert "ceo" in agents
        assert "cmo" in agents
        assert "cto" in agents

    def test_delete_agent(self, temp_vault):
        registry = AgentRegistry(temp_vault)
        profile = AgentProfile(agent_id="temp", role="Temp")
        registry.save(profile)
        assert registry.get("temp") is not None

        registry.delete("temp")
        assert registry.get("temp") is None


class TestGetCurrentAgent:
    def test_paperclip_agent_id(self, temp_vault, agent_registry):
        with patch.dict(os.environ, {"PAPERCLIP_AGENT_ID": "cmo"}):
            assert get_current_agent_id() == "cmo"

    def test_default_when_no_env(self):
        with patch.dict(os.environ, {}, clear=True):
            # Remove any existing agent env vars
            os.environ.pop("PAPERCLIP_AGENT_ID", None)
            os.environ.pop("CLAUDE_NOTE_AGENT_ID", None)
            assert get_current_agent_id() == DEFAULT_AGENT_ID

    def test_get_current_agent_profile(self, temp_vault, agent_registry):
        with patch.dict(os.environ, {"PAPERCLIP_AGENT_ID": "cto"}):
            profile = get_current_agent(temp_vault)
            assert profile.agent_id == "cto"
            assert profile.department == "engineering"
