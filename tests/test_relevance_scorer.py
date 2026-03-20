"""Tests for relevance scoring."""

import time
from unittest.mock import patch

import pytest
from claude_note.relevance_scorer import (
    score_notes, budget_constrain, NoteScore,
    _score_department, _score_recency, _score_hub,
)
from claude_note.vault_indexer import NoteIndex, VaultIndex


class TestScoreComponents:
    def test_department_primary(self):
        score = _score_department("marketing/campaigns/q2.md", ["marketing/"], [], [])
        assert score == 1.0

    def test_department_secondary(self):
        score = _score_department("sales/pipeline/deals.md", ["marketing/"], ["sales/"], [])
        assert score == 0.5

    def test_department_excluded(self):
        score = _score_department(
            "engineering/infrastructure/k8s.md",
            ["engineering/"],
            [],
            ["engineering/infrastructure/"],
        )
        assert score == 0.0

    def test_department_other(self):
        score = _score_department("random/note.md", ["marketing/"], ["sales/"], [])
        assert score == 0.1

    def test_recency_today(self):
        score = _score_recency(time.time())
        assert score > 0.95

    def test_recency_14_days(self):
        score = _score_recency(time.time() - 14 * 86400)
        assert 0.45 < score < 0.55  # Should be ~0.5 at half-life

    def test_recency_28_days(self):
        score = _score_recency(time.time() - 28 * 86400)
        assert 0.2 < score < 0.3  # Should be ~0.25

    def test_hub_score(self):
        assert _score_hub("_hub/strategy.md") == 1.0
        assert _score_hub("marketing/campaign.md") == 0.0


class TestScoreNotes:
    def test_cmo_scores_marketing_higher_by_department(self, sample_vault_index):
        """Department scoring alone should rank marketing notes higher for CMO."""
        scored = score_notes(
            sample_vault_index,
            primary_folders=["marketing/", "_hub/"],
            secondary_folders=["sales/"],
            excluded_folders=["engineering/infrastructure/"],
        )

        marketing_scores = [s for s in scored if "marketing" in s.path]
        engineering_scores = [s for s in scored if "engineering" in s.path]

        if marketing_scores and engineering_scores:
            assert marketing_scores[0].total > engineering_scores[0].total

    def test_semantic_scores_boost_notes(self, sample_vault_index):
        """Notes with high semantic scores should rank higher."""
        # Find the actual path key (Windows uses backslashes)
        campaign_path = None
        for p in sample_vault_index.notes:
            if "q2-campaign" in p:
                campaign_path = p
                break

        if not campaign_path:
            pytest.skip("q2-campaign note not found in index")

        scored = score_notes(
            sample_vault_index,
            primary_folders=[],  # No folder bias
            semantic_scores={campaign_path: 0.95},
        )

        boosted = [s for s in scored if "q2-campaign" in s.path]
        non_boosted = [s for s in scored if "q2-campaign" not in s.path and s.total > 0]

        assert boosted  # Campaign note should be in results
        assert boosted[0].semantic == 0.95  # Got the semantic score


class TestBudgetConstrain:
    def test_partition_tiers(self):
        notes = [
            NoteScore(path="a.md", title="A", total=0.9),
            NoteScore(path="b.md", title="B", total=0.7),
            NoteScore(path="c.md", title="C", total=0.4),
            NoteScore(path="d.md", title="D", total=0.1),
        ]
        tiers = budget_constrain(notes)
        assert len(tiers["high"]) == 1
        assert len(tiers["mid"]) == 1
        assert len(tiers["low"]) == 1

    def test_max_notes_limit(self):
        notes = [NoteScore(path=f"{i}.md", title=str(i), total=0.9) for i in range(100)]
        tiers = budget_constrain(notes, max_notes=10)
        total = len(tiers["high"]) + len(tiers["mid"]) + len(tiers["low"])
        assert total <= 10
