import pytest
from types import SimpleNamespace

from pythia.config import Settings
import pythia.services.instagram as instagram_service
from pythia.services.instagram import InvalidProfileUrl, normalize_profile_url


@pytest.mark.parametrize(
    ("source", "username", "canonical"),
    [
        ("https://www.instagram.com/example.creator/", "example.creator", "https://www.instagram.com/example.creator/"),
        ("instagram.com/example_1", "example_1", "https://www.instagram.com/example_1/"),
    ],
)
def test_normalize_profile_url(source: str, username: str, canonical: str) -> None:
    assert normalize_profile_url(source) == (username, canonical)


@pytest.mark.parametrize(
    "source",
    [
        "https://www.instagram.com/reel/Cx123/",
        "https://www.instagram.com/p/Cx123/",
        "https://example.com/someone",
        "https://www.instagram.com/too/many/segments",
    ],
)
def test_rejects_non_profile_urls(source: str) -> None:
    with pytest.raises(InvalidProfileUrl):
        normalize_profile_url(source)


def test_collector_uses_module_settings(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    replacement = Settings(instagram_username="", instagram_session_file="")
    monkeypatch.setattr(instagram_service, "settings", replacement)

    assert not instagram_service.InstagramCollector()._loader(tmp_path).context.is_logged_in


@pytest.mark.parametrize("stage", ["profile", "reels"])
@pytest.mark.parametrize("reason", ["feedback_required", "checkpoint_required", "challenge_required"])
def test_instagram_abort_is_reported_without_retry(monkeypatch, tmp_path, stage, reason) -> None:
    collector = instagram_service.InstagramCollector()
    calls = []

    def abort(*args, **kwargs):
        calls.append(stage)
        raise instagram_service.instaloader.exceptions.AbortDownloadException(reason)

    post = SimpleNamespace(shortcode="abc")
    profile = SimpleNamespace(is_private=False, get_reels=lambda: iter([post]))
    loader = SimpleNamespace(context=object(), download_post=lambda *args, **kwargs: None)
    monkeypatch.setattr(collector, "_loader", lambda destination: loader)
    monkeypatch.setattr(
        instagram_service.instaloader.Profile, "from_username",
        abort if stage == "profile" else lambda *args: profile,
    )
    if stage == "reels":
        profile.get_reels = abort

    with pytest.raises(instagram_service.InstagramBlocked) as error:
        collector.collect("example", tmp_path)

    assert error.value.code == "instagram_blocked"
    assert calls == [stage]


@pytest.mark.parametrize("source", [
    "https://www.instagram.com/reel/DePzV26vLFB/?igsh=test",
    "instagram.com/nike/reel/DePzV26vLFB/",
])
def test_reel_urls_are_canonicalized(source):
    assert instagram_service.normalize_instagram_url(source) == (
        None, "https://www.instagram.com/reel/DePzV26vLFB/",
    )


@pytest.mark.parametrize("source", [
    "https://instagram.com.evil.com/reel/abc/", "https://evil.com/reel/abc/",
    "https://www.instagram.com/p/abc/", "https://user@instagram.com/reel/abc/",
    "https://instagram.com/reel/../", "https://instagram.com/reel/abc/extra/",
])
def test_invalid_input_never_reaches_downloader(source):
    with pytest.raises(InvalidProfileUrl):
        instagram_service.normalize_instagram_url(source)


def test_profile_discovery_downloads_only_three_reels_with_ytdlp(monkeypatch, tmp_path):
    from unittest.mock import Mock
    collector = instagram_service.InstagramCollector()
    posts = [SimpleNamespace(shortcode=f"code{i}") for i in range(5)]
    profile = SimpleNamespace(is_private=False, get_reels=lambda: iter(posts))
    monkeypatch.setattr(collector, "_loader", lambda _: SimpleNamespace(context=object()))
    monkeypatch.setattr(instagram_service.instaloader.Profile, "from_username", lambda *args: profile)
    download = Mock(return_value="downloaded")
    monkeypatch.setattr(collector, "download_reel", download)
    assert collector.collect("nike", tmp_path) == ["downloaded"] * 3
    assert [call.args[0] for call in download.call_args_list] == [
        f"https://www.instagram.com/reel/code{i}/" for i in range(3)
    ]


def test_ytdlp_metadata_and_video_without_views(monkeypatch, tmp_path):
    class Downloader:
        def __init__(self, options):
            assert options["retries"] == 0
            assert "cookiefile" not in options
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def extract_info(self, url, download):
            assert url == "https://www.instagram.com/reel/abc/"
            assert download is True
            (tmp_path / "abc" / "video.mp4").write_bytes(b"video")
            return {"channel": "nike", "description": "caption", "timestamp": 1791491667,
                    "like_count": 0, "comment_count": 12, "view_count": 900}
    monkeypatch.setattr(instagram_service, "YoutubeDL", Downloader)
    result = instagram_service.InstagramCollector().download_reel("instagram.com/reel/abc/?x=1", tmp_path)
    assert result.creator_username == "nike"
    assert result.metadata.likes_count == 0
    assert result.metadata.comments_count == 12
    assert result.metadata.views_count is None
    assert result.metadata.published_at.tzinfo is not None
    assert result.video_path.read_bytes() == b"video"


@pytest.mark.parametrize("failed", [False, True])
def test_ytdlp_failure_or_missing_file_is_not_success(monkeypatch, tmp_path, failed):
    class Downloader:
        def __init__(self, options):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def extract_info(self, *args, **kwargs):
            if failed:
                raise instagram_service.DownloadError("blocked")
            return {"channel": "nike"}
    monkeypatch.setattr(instagram_service, "YoutubeDL", Downloader)
    with pytest.raises(instagram_service.InstagramError):
        instagram_service.InstagramCollector().download_reel("instagram.com/reel/abc/", tmp_path)
