import pytest

import pythia.services.instagram as instagram_service
from pythia.services.instagram import MAX_REELS, InvalidReelUrl, normalize_reel_url, parse_reel_urls


@pytest.mark.parametrize("source", [
    "https://www.instagram.com/reel/DePzV26vLFB/?igsh=test",
    "instagram.com/nike/reel/DePzV26vLFB/",
    "https://instagram.com/reel/DePzV26vLFB",
])
def test_reel_urls_are_canonicalized(source):
    assert normalize_reel_url(source) == ("DePzV26vLFB", "https://www.instagram.com/reel/DePzV26vLFB/")


@pytest.mark.parametrize("source", [
    "https://instagram.com.evil.com/reel/abc/", "https://evil.com/reel/abc/",
    "https://www.instagram.com/p/abc/", "https://user@instagram.com/reel/abc/",
    "https://instagram.com/reel/../", "https://instagram.com/reel/abc/extra/",
    "https://www.instagram.com/nike/",
])
def test_invalid_input_never_reaches_downloader(source):
    with pytest.raises(InvalidReelUrl):
        normalize_reel_url(source)


@pytest.mark.parametrize("count", [1, 2, 3])
def test_message_with_one_to_three_reels_keeps_order(count):
    text = "\n".join(f"https://www.instagram.com/reel/code{i}/?igsh=x" for i in range(count))
    request = parse_reel_urls(text)
    assert request.urls == [f"https://www.instagram.com/reel/code{i}/" for i in range(count)]
    assert request.duplicates == 0


def test_duplicates_are_collapsed_and_counted():
    request = parse_reel_urls(
        "instagram.com/reel/a/ https://www.instagram.com/nike/reel/b/ https://instagram.com/reel/a/?x=1"
    )
    assert request.urls == ["https://www.instagram.com/reel/a/", "https://www.instagram.com/reel/b/"]
    assert request.duplicates == 1


def test_duplicates_do_not_count_towards_the_limit():
    text = " ".join(["instagram.com/reel/a/"] * 2 + [f"instagram.com/reel/{c}/" for c in "bc"])
    assert len(parse_reel_urls(text).urls) == MAX_REELS


@pytest.mark.parametrize("text", [
    "",
    "   \n ",
    " ".join(f"instagram.com/reel/code{i}/" for i in range(MAX_REELS + 1)),
    "instagram.com/reel/a/ https://www.instagram.com/nike/",
    "instagram.com/reel/a/ https://www.instagram.com/p/b/",
    "посмотри instagram.com/reel/a/",
])
def test_whole_message_is_rejected(text):
    with pytest.raises(InvalidReelUrl):
        parse_reel_urls(text)


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
