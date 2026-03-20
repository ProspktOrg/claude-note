"""Relevance scoring for agent-scoped note retrieval.

Scores notes using 5 weighted components:
1. Semantic/qmd (0.35) - vector similarity (understands meaning, not just tags)
2. Department path (0.20) - folder proximity to agent's scope
3. Recency (0.20) - 14-day half-life decay
4. Mycelium activation (0.20) - spreading activation from knowledge graph
5. Hub score (0.05) - cross-functional importance
"""

import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from . import vault_indexer


# Scoring weights -- semantic search is the primary signal
WEIGHTS = {
    "semantic": 0.35,
    "department": 0.20,
    "recency": 0.20,
    "mycelium": 0.20,
    "hub": 0.05,
}

# Recency half-life in days
RECENCY_HALF_LIFE_DAYS = 14.0


@dataclass
class NoteScore:
    """Scored note with component breakdown."""
    path: str
    title: str
    total: float
    semantic: float = 0.0
    department: float = 0.0
    recency: float = 0.0
    mycelium: float = 0.0
    hub: float = 0.0

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "title": self.title,
            "total": round(self.total, 4),
            "components": {
                "semantic": round(self.semantic, 4),
                "department": round(self.department, 4),
                "recency": round(self.recency, 4),
                "mycelium": round(self.mycelium, 4),
                "hub": round(self.hub, 4),
            },
        }


def _score_department(note_path: str, primary_folders: list[str], secondary_folders: list[str], excluded_folders: list[str]) -> float:
    """Score based on folder proximity to agent's departments."""
    normalized = note_path.replace("\\", "/").strip("/")

    # Check exclusions first
    for ef in excluded_folders:
        ef_norm = ef.replace("\\", "/").strip("/")
        if normalized.startswith(ef_norm):
            return 0.0

    # Primary folder = 1.0
    for pf in primary_folders:
        pf_norm = pf.replace("\\", "/").strip("/")
        if normalized.startswith(pf_norm):
            return 1.0

    # Secondary folder = 0.5
    for sf in secondary_folders:
        sf_norm = sf.replace("\\", "/").strip("/")
        if normalized.startswith(sf_norm):
            return 0.5

    # Not in agent's scope
    return 0.1


def _score_recency(mtime: float, half_life_days: float = RECENCY_HALF_LIFE_DAYS) -> float:
    """Score based on note recency with exponential decay."""
    if mtime <= 0:
        return 0.0

    age_days = (time.time() - mtime) / 86400.0
    if age_days < 0:
        age_days = 0

    # Exponential decay: 0.5 at half_life_days
    return math.pow(0.5, age_days / half_life_days)


def _score_hub(note_path: str) -> float:
    """Score based on whether note is in _hub/ (cross-functional importance)."""
    normalized = note_path.replace("\\", "/").strip("/")
    if normalized.startswith("_hub/"):
        return 1.0
    return 0.0


def score_notes(
    vault_index: vault_indexer.VaultIndex,
    primary_folders: list[str] = None,
    secondary_folders: list[str] = None,
    excluded_folders: list[str] = None,
    mycelium_scores: dict[str, float] = None,
    semantic_scores: dict[str, float] = None,
    weights: dict[str, float] = None,
    # Legacy params (ignored, kept for backward compat)
    primary_tags: list[str] = None,
    secondary_tags: list[str] = None,
) -> list[NoteScore]:
    """
    Score all notes in the vault index for relevance to an agent.

    Args:
        vault_index: VaultIndex with all notes
        primary_folders: Agent's primary folders
        secondary_folders: Agent's secondary folders
        excluded_folders: Folders to exclude
        mycelium_scores: {path: activation_score} from mycelium graph
        semantic_scores: {path: similarity_score} from qmd search
        weights: Override default scoring weights

    Returns:
        List of NoteScore sorted by total score descending
    """
    primary_folders = primary_folders or []
    secondary_folders = secondary_folders or []
    excluded_folders = excluded_folders or []
    mycelium_scores = mycelium_scores or {}
    semantic_scores = semantic_scores or {}
    w = weights or WEIGHTS

    scored = []

    for path, note in vault_index.notes.items():
        # Skip hidden dirs and agent configs
        if path.startswith(".") or path.startswith("_agents/"):
            continue

        dept_score = _score_department(path, primary_folders, secondary_folders, excluded_folders)
        recency_score = _score_recency(note.mtime)
        mycelium_score = mycelium_scores.get(path, 0.0)
        semantic_score = semantic_scores.get(path, 0.0)
        hub_score = _score_hub(path)

        total = (
            w.get("semantic", 0.35) * semantic_score
            + w.get("department", 0.20) * dept_score
            + w.get("recency", 0.20) * recency_score
            + w.get("mycelium", 0.20) * mycelium_score
            + w.get("hub", 0.05) * hub_score
        )

        scored.append(NoteScore(
            path=path,
            title=note.title,
            total=total,
            semantic=semantic_score,
            department=dept_score,
            recency=recency_score,
            mycelium=mycelium_score,
            hub=hub_score,
        ))

    # Sort by total score descending
    scored.sort(key=lambda s: s.total, reverse=True)
    return scored


def budget_constrain(
    scored_notes: list[NoteScore],
    max_notes: int = 50,
    high_threshold: float = 0.8,
    mid_threshold: float = 0.5,
    low_threshold: float = 0.3,
) -> dict[str, list[NoteScore]]:
    """
    Partition scored notes into budget tiers.

    Returns:
        Dict with keys 'high', 'mid', 'low' containing notes in each tier
    """
    result = {"high": [], "mid": [], "low": []}

    count = 0
    for note in scored_notes:
        if count >= max_notes:
            break

        if note.total >= high_threshold:
            result["high"].append(note)
        elif note.total >= mid_threshold:
            result["mid"].append(note)
        elif note.total >= low_threshold:
            result["low"].append(note)
        else:
            continue  # Below all thresholds

        count += 1

    return result
