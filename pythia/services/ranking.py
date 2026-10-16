from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from pythia.schemas import ReelMetadata

COMMENT_WEIGHT = 3


@dataclass(frozen=True, slots=True)
class RankedReel:
    position: int
    url: str
    likes: int | None
    comments: int | None
    score: int | None
    age_days: int | None


@dataclass(frozen=True, slots=True)
class Ranking:
    entries: list[RankedReel]
    winners: list[int]

    def as_dict(self) -> dict:
        return asdict(self)


def engagement_score(likes: int | None, comments: int | None) -> int | None:
    """Likes plus weighted comments; missing data is not treated as zero."""
    if likes is None or comments is None:
        return None
    return likes + COMMENT_WEIGHT * comments


def rank_reels(reels: dict[int, ReelMetadata], now: datetime | None = None) -> Ranking:
    """Rank successfully analysed reels by engagement; positions are 1-based input order."""
    now = now or datetime.now(UTC)
    entries = [
        RankedReel(
            position=position,
            url=metadata.url,
            likes=metadata.likes_count,
            comments=metadata.comments_count,
            score=engagement_score(metadata.likes_count, metadata.comments_count),
            age_days=(now - metadata.published_at).days if metadata.published_at else None,
        )
        for position, metadata in reels.items()
    ]
    entries.sort(key=lambda entry: (entry.score is None, -(entry.score or 0), entry.position))
    scored = [entry for entry in entries if entry.score is not None]
    winners: list[int] = []
    if len(scored) >= 2:
        best = scored[0].score
        winners = [entry.position for entry in scored if entry.score == best]
    return Ranking(entries=entries, winners=winners)
