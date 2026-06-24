from datetime import UTC, datetime
from pathlib import Path

from pythia.reporting import render_reel_details
from pythia.schemas import ContentAnalysis, ProcessedReel, ReelMetadata


def test_report_escapes_model_output_and_includes_metrics() -> None:
    reel = ProcessedReel(
        metadata=ReelMetadata(
            shortcode="abc",
            url="https://www.instagram.com/reel/abc/",
            published_at=datetime.now(UTC),
            views_count=1000,
            likes_count=50,
            comments_count=10,
        ),
        transcript="<script>",
        analysis=ContentAnalysis(summary="<b>test</b>", topics=["AI"], key_frame_index=0),
        key_frame_path=Path("/tmp/key.jpg"),
    )
    text = render_reel_details(reel, "1-е место")
    assert "Просмотры: 1000" in text
    assert "&lt;script&gt;" in text
    assert "&lt;b&gt;test&lt;/b&gt;" in text
    assert "1-е место" in text
