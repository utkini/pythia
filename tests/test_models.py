from pythia.models import analysis_runs, competitors, metadata, reel_analyses, reels


def test_core_metadata_exposes_the_persisted_schema() -> None:
    assert set(metadata.tables) == {"competitors", "analysis_runs", "reels", "reel_analyses"}
    assert analysis_runs.c.competitor_id.foreign_keys
    assert reels.c.run_id.foreign_keys
    assert reel_analyses.c.reel_id.unique
    assert competitors.c.username.unique
    assert analysis_runs.c.competitor_id.nullable
    assert reels.c.competitor_id.nullable
    assert {"source_urls", "ranking_json"} <= set(analysis_runs.c.keys())
    unique = {tuple(c.columns.keys()) for c in reels.constraints if c.__class__.__name__ == "UniqueConstraint"}
    assert unique == {("run_id", "shortcode")}
