from datetime import UTC, datetime, timedelta

from pythia.schemas import ReelMetadata
from pythia.services.ranking import engagement_score, rank_reels

NOW = datetime(2026, 10, 15, tzinfo=UTC)


def reel(code: str, likes: int | None, comments: int | None, days: int | None = None) -> ReelMetadata:
    return ReelMetadata(
        shortcode=code, url=f"https://www.instagram.com/reel/{code}/",
        likes_count=likes, comments_count=comments,
        published_at=NOW - timedelta(days=days) if days is not None else None,
    )


def test_score_weights_comments():
    assert engagement_score(100, 10) == 130
    assert engagement_score(0, 0) == 0
    assert engagement_score(None, 5) is None
    assert engagement_score(5, None) is None


def test_comments_can_beat_likes():
    ranking = rank_reels({1: reel("a", 100, 0, 3), 2: reel("b", 50, 20, 1)}, NOW)
    assert ranking.winners == [2]
    assert [entry.position for entry in ranking.entries] == [2, 1]
    assert ranking.entries[0].score == 110
    assert ranking.entries[1].age_days == 3


def test_tie_has_several_winners_in_input_order():
    ranking = rank_reels({1: reel("a", 30, 0), 2: reel("b", 1, 1), 3: reel("c", 0, 10)}, NOW)
    assert ranking.winners == [1, 3]


def test_missing_metrics_are_excluded_not_zero():
    ranking = rank_reels({1: reel("a", None, 5), 2: reel("b", 0, 0), 3: reel("c", 2, 0)}, NOW)
    assert ranking.winners == [3]
    assert ranking.entries[-1].position == 1
    assert ranking.entries[-1].score is None


def test_no_winner_with_fewer_than_two_scored_reels():
    assert rank_reels({1: reel("a", 10, 1), 2: reel("b", None, None)}, NOW).winners == []
    assert rank_reels({2: reel("b", 10, 1)}, NOW).winners == []


def test_ranking_is_json_serialisable():
    import json
    json.dumps(rank_reels({1: reel("a", 1, 1), 2: reel("b", 2, 2)}, NOW).as_dict())
