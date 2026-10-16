import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from pythia.config import settings
from pythia.schemas import DownloadedReel, ReelMetadata

USERNAME_RE = re.compile(r"^[A-Za-z0-9._]{1,30}$")


class InstagramError(Exception):
    code = "instagram_failed"


class InvalidReelUrl(InstagramError):
    code = "invalid_url"


MAX_REELS = 3
INPUT_EXAMPLE = (
    "Пример:\nhttps://www.instagram.com/reel/AAA/\nhttps://www.instagram.com/reel/BBB/"
)


def normalize_reel_url(value: str) -> tuple[str, str]:
    candidate = value.strip()
    if not candidate.startswith(("http://", "https://")):
        candidate = f"https://{candidate}"
    parsed = urlparse(candidate)
    parts = [part for part in parsed.path.split("/") if part]
    if parsed.netloc.lower() not in {"instagram.com", "www.instagram.com"}:
        raise InvalidReelUrl("Нужна ссылка на Instagram Reel.")
    if len(parts) == 3 and USERNAME_RE.fullmatch(parts[0]):
        parts = parts[1:]
    if len(parts) != 2 or parts[0] != "reel" or not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", parts[1]):
        raise InvalidReelUrl("Нужна ссылка вида instagram.com/reel/<код>/.")
    return parts[1], f"https://www.instagram.com/reel/{parts[1]}/"


@dataclass(frozen=True, slots=True)
class ReelRequest:
    urls: list[str]
    duplicates: int


def parse_reel_urls(text: str) -> ReelRequest:
    """Validate the whole message before any network call; keep the user's order."""
    tokens = text.split()
    if not tokens:
        raise InvalidReelUrl(f"Пришлите от 1 до {MAX_REELS} ссылок на Reels.\n{INPUT_EXAMPLE}")
    urls: dict[str, str] = {}
    for token in tokens:
        try:
            shortcode, canonical = normalize_reel_url(token)
        except InvalidReelUrl:
            raise InvalidReelUrl(
                f"Не похоже на ссылку на Reel: {token[:80]}\n"
                f"Принимаются только ссылки instagram.com/reel/<код>/ (профили и посты /p/ не поддерживаются).\n{INPUT_EXAMPLE}"
            ) from None
        urls.setdefault(shortcode, canonical)
    if len(urls) > MAX_REELS:
        raise InvalidReelUrl(f"Можно прислать не больше {MAX_REELS} разных Reels за раз, получено {len(urls)}.")
    return ReelRequest(urls=list(urls.values()), duplicates=len(tokens) - len(urls))


class InstagramCollector:
    """Download a single public Reel with yt-dlp; call from a worker thread."""

    def download_reel(self, url: str, destination: Path) -> DownloadedReel:
        shortcode, canonical = normalize_reel_url(url)
        reel_dir = destination / shortcode
        reel_dir.mkdir(parents=True, exist_ok=True)
        options = {
            "outtmpl": str(reel_dir / "video.%(ext)s"),
            "format": "best[acodec!=none][vcodec!=none]/bestvideo+bestaudio",
            "merge_output_format": "mp4",
            "noplaylist": True,
            "quiet": True,
            "noprogress": True,
            "cachedir": False,
            "retries": 0,
            "extractor_retries": 0,
            "fragment_retries": 0,
            "socket_timeout": settings.external_timeout_seconds,
            "max_filesize": 100 * 1024 * 1024,
        }
        try:
            with YoutubeDL(options) as downloader:
                info = downloader.extract_info(canonical, download=True)
        except DownloadError as error:
            raise InstagramError("Unable to download the public Reel with yt-dlp.") from error
        if not info or info.get("_type") in {"playlist", "multi_video"}:
            raise InstagramError("Instagram did not return a single Reel.")
        videos = [p for p in reel_dir.glob("video.*") if p.suffix in {".mp4", ".mkv", ".webm"}]
        if len(videos) != 1 or videos[0].stat().st_size == 0:
            raise InstagramError("No complete video was downloaded (possibly above the size limit).")
        username = info.get("channel")
        if not isinstance(username, str) or not USERNAME_RE.fullmatch(username):
            username = None
        timestamp = info.get("timestamp")
        return DownloadedReel(
            metadata=ReelMetadata(
                shortcode=shortcode, url=canonical, caption=info.get("description"),
                published_at=datetime.fromtimestamp(timestamp, UTC) if timestamp is not None else None,
                likes_count=info.get("like_count"), comments_count=info.get("comment_count"),
                views_count=None,
            ),
            video_path=videos[0],
            creator_username=username,
        )
