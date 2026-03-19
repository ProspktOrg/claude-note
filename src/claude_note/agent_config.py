"""Agent configuration for multi-agent company brain.

Manages agent profiles with department scoping, tag ownership,
and context budgets.

Agent ID resolution order:
1. PAPERCLIP_AGENT_ID env var (Paperclip multi-agent systems)
2. CLAUDE_NOTE_AGENT_ID env var (manual override)
3. config.toml [agent] id = "..." (standalone / non-Paperclip setups)
4. "default" fallback
"""

import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from . import config


# Default agent for non-Paperclip usage
DEFAULT_AGENT_ID = "default"


@dataclass
class AgentProfile:
    """Configuration for a single agent."""
    agent_id: str
    role: str = ""
    department: str = ""
    primary_folders: list[str] = field(default_factory=list)
    secondary_folders: list[str] = field(default_factory=list)
    excluded_folders: list[str] = field(default_factory=list)
    tags_primary: list[str] = field(default_factory=list)
    tags_secondary: list[str] = field(default_factory=list)
    home_nodes: list[str] = field(default_factory=list)
    context_budget: int = 50  # max notes to consider
    briefing_token_budget: int = 4000

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "AgentProfile":
        # Filter to only valid fields
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> "AgentProfile":
        return cls.from_dict(json.loads(json_str))

    def owns_folder(self, folder_path: str) -> bool:
        """Check if this agent owns a folder (primary)."""
        normalized = folder_path.replace("\\", "/").strip("/")
        for pf in self.primary_folders:
            pf_norm = pf.replace("\\", "/").strip("/")
            if normalized.startswith(pf_norm):
                return True
        return False

    def can_access_folder(self, folder_path: str) -> bool:
        """Check if this agent can access a folder (primary or secondary)."""
        normalized = folder_path.replace("\\", "/").strip("/")
        # Check exclusions first
        for ef in self.excluded_folders:
            ef_norm = ef.replace("\\", "/").strip("/")
            if normalized.startswith(ef_norm):
                return False
        # Check primary + secondary
        for pf in self.primary_folders + self.secondary_folders:
            pf_norm = pf.replace("\\", "/").strip("/")
            if normalized.startswith(pf_norm):
                return True
        return False

    def owns_tag(self, tag: str) -> bool:
        """Check if tag is in agent's primary tags."""
        return tag.lower() in [t.lower() for t in self.tags_primary]

    def is_relevant_tag(self, tag: str) -> bool:
        """Check if tag is in primary or secondary tags."""
        all_tags = [t.lower() for t in self.tags_primary + self.tags_secondary]
        return tag.lower() in all_tags


def get_default_agent() -> AgentProfile:
    """Return default agent profile for non-Paperclip usage."""
    return AgentProfile(
        agent_id=DEFAULT_AGENT_ID,
        role="Default Agent",
        department="",
        primary_folders=["_hub/"],
        secondary_folders=[],
        excluded_folders=[],
        tags_primary=[],
        tags_secondary=[],
        home_nodes=[],
    )


class AgentRegistry:
    """Registry of agent profiles, stored as JSON in .claude-note/agents/."""

    def __init__(self, vault_root: Path = None):
        if vault_root is None:
            vault_root = config.VAULT_ROOT
        self.agents_dir = vault_root / ".claude-note" / "agents"
        self._cache: dict[str, AgentProfile] = {}

    def _agent_path(self, agent_id: str) -> Path:
        return self.agents_dir / f"{agent_id}.json"

    def get(self, agent_id: str) -> Optional[AgentProfile]:
        """Load agent profile by ID. Returns None if not found."""
        if agent_id in self._cache:
            return self._cache[agent_id]

        path = self._agent_path(agent_id)
        if not path.exists():
            return None

        try:
            profile = AgentProfile.from_json(path.read_text(encoding="utf-8"))
            self._cache[agent_id] = profile
            return profile
        except Exception:
            return None

    def save(self, profile: AgentProfile) -> None:
        """Save agent profile to registry."""
        self.agents_dir.mkdir(parents=True, exist_ok=True)
        path = self._agent_path(profile.agent_id)
        path.write_text(profile.to_json(), encoding="utf-8")
        self._cache[profile.agent_id] = profile

    def list_agents(self) -> list[str]:
        """List all registered agent IDs."""
        if not self.agents_dir.exists():
            return []
        return [p.stem for p in self.agents_dir.glob("*.json")]

    def get_all(self) -> list[AgentProfile]:
        """Load all agent profiles."""
        agents = []
        for agent_id in self.list_agents():
            profile = self.get(agent_id)
            if profile:
                agents.append(profile)
        return agents

    def delete(self, agent_id: str) -> bool:
        """Delete an agent profile."""
        path = self._agent_path(agent_id)
        if path.exists():
            path.unlink()
            self._cache.pop(agent_id, None)
            return True
        return False


def get_current_agent_id() -> str:
    """
    Get current agent ID.

    Resolution order:
    1. PAPERCLIP_AGENT_ID env var
    2. CLAUDE_NOTE_AGENT_ID env var
    3. config.toml [agent] id
    4. DEFAULT_AGENT_ID ("default")
    """
    agent_id = os.environ.get("PAPERCLIP_AGENT_ID")
    if agent_id:
        return agent_id.lower().strip()

    agent_id = os.environ.get("CLAUDE_NOTE_AGENT_ID")
    if agent_id:
        return agent_id.lower().strip()

    # Fall back to config file
    config_id = config.AGENT_ID
    if config_id and config_id != "default":
        return config_id.lower().strip()

    return DEFAULT_AGENT_ID


def get_current_agent(vault_root: Path = None) -> AgentProfile:
    """
    Get current agent profile from environment + registry.

    Returns default profile if no agent is configured or found.
    """
    agent_id = get_current_agent_id()

    if agent_id == DEFAULT_AGENT_ID:
        return get_default_agent()

    registry = AgentRegistry(vault_root)
    profile = registry.get(agent_id)

    if profile is None:
        # Agent ID is set but no profile exists - return minimal profile
        return AgentProfile(
            agent_id=agent_id,
            role=agent_id.replace("-", " ").title(),
            department="",
            primary_folders=["_hub/"],
        )

    return profile


# Standard agent templates for quick setup
AGENT_TEMPLATES = {
    "ceo": AgentProfile(
        agent_id="ceo",
        role="Chief Executive Officer",
        department="executive",
        primary_folders=["executive/", "_hub/"],
        secondary_folders=["marketing/", "sales/", "engineering/", "product/"],
        excluded_folders=[],
        tags_primary=["strategy", "leadership", "board", "fundraising", "vision"],
        tags_secondary=["okr", "culture", "hiring", "partnerships"],
        home_nodes=["strategy", "okrs", "company-brain"],
        context_budget=60,
        briefing_token_budget=5000,
    ),
    "cmo": AgentProfile(
        agent_id="cmo",
        role="Chief Marketing Officer",
        department="marketing",
        primary_folders=["marketing/", "_hub/"],
        secondary_folders=["sales/", "product/"],
        excluded_folders=["engineering/infrastructure/"],
        tags_primary=["marketing", "brand", "campaign", "content", "analytics"],
        tags_secondary=["strategy", "okr", "customer-insight", "product-launch"],
        home_nodes=["marketing-strategy", "brand-guidelines"],
        context_budget=50,
        briefing_token_budget=4000,
    ),
    "cto": AgentProfile(
        agent_id="cto",
        role="Chief Technology Officer",
        department="engineering",
        primary_folders=["engineering/", "_hub/"],
        secondary_folders=["product/", "operations/"],
        excluded_folders=[],
        tags_primary=["engineering", "architecture", "infrastructure", "tech-decision", "security"],
        tags_secondary=["strategy", "okr", "api", "devops", "incident"],
        home_nodes=["architecture", "tech-decisions", "infrastructure"],
        context_budget=50,
        briefing_token_budget=4000,
    ),
    "head-of-sales": AgentProfile(
        agent_id="head-of-sales",
        role="Head of Sales",
        department="sales",
        primary_folders=["sales/", "_hub/"],
        secondary_folders=["marketing/", "product/"],
        excluded_folders=["engineering/infrastructure/"],
        tags_primary=["sales", "pipeline", "account", "pricing", "deal"],
        tags_secondary=["strategy", "okr", "customer-insight", "product-launch"],
        home_nodes=["pipeline", "pricing", "sales-playbook"],
        context_budget=50,
        briefing_token_budget=4000,
    ),
    "solo": AgentProfile(
        agent_id="solo",
        role="Solo Operator",
        department="",
        primary_folders=[
            "_hub/", "executive/", "marketing/", "sales/",
            "engineering/", "product/", "operations/",
        ],
        secondary_folders=["literature/", "journal/"],
        excluded_folders=[],
        tags_primary=[],  # empty = all tags relevant
        tags_secondary=[],
        home_nodes=["company-brain", "strategy"],
        context_budget=60,
        briefing_token_budget=5000,
    ),
}
