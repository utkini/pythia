import re
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import instaloader
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from pythia.config import settings
from pythia.schemas import DownloadedReel, ReelMetadata

USERNAME_RE = re.compile(r"^[A-Za-z0-9._]{1,30}$")


class InstagramError(Exception):
    code = "instagram_failed"


class InvalidProfileUrl(InstagramError):
    code = "invalid_url"


class PrivateProfile(InstagramError):
    code = "private_profile"


class NoReels(InstagramError):
    code = "no_reels"


class InstagramLimited(InstagramError):
    code = "instagram_limited"


class InstagramBlocked(InstagramError):
    code = "instagram_blocked"


def normalize_profile_url(value: str) -> tuple[str, str]:
    """Return the Instagram username and canonical profile URL, rejecting post URLs."""
    candidate = value.strip()
    if not candidate.startswith(("http://", "https://")):
        candidate = f"https://{candidate}"
    parsed = urlparse(candidate)
    if parsed.netloc.lower() not in {"instagram.com", "www.instagram.com"}:
        raise InvalidProfileUrl("Нужна ссылка на профиль instagram.com/<username>.")
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) != 1 or not USERNAME_RE.fullmatch(parts[0]) or parts[0].lower() in {"p", "reel", "reels", "stories"}:
        raise InvalidProfileUrl("Нужна ссылка на публичный профиль, а не на пост или Reel.")
    username = parts[0]
    return username, f"https://www.instagram.com/{username}/"


def normalize_reel_url(value: str) -> tuple[str, str]:
    candidate = value.strip()
    if not candidate.startswith(("http://", "https://")):
        candidate = f"https://{candidate}"
    parsed = urlparse(candidate)
    parts = [part for part in parsed.path.split("/") if part]
    if parsed.netloc.lower() not in {"instagram.com", "www.instagram.com"}:
        raise InvalidProfileUrl("Нужна ссылка на Instagram-профиль или Reel.")
    if len(parts) == 3 and USERNAME_RE.fullmatch(parts[0]):
        parts = parts[1:]
    if len(parts) != 2 or parts[0] != "reel" or not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", parts[1]):
        raise InvalidProfileUrl("Нужна ссылка вида instagram.com/reel/<код>/.")
    return parts[1], f"https://www.instagram.com/reel/{parts[1]}/"


def normalize_instagram_url(value: str) -> tuple[str | None, str]:
    try:
        return normalize_profile_url(value)
    except InvalidProfileUrl:
        _, url = normalize_reel_url(value)
        return None, url


class InstagramCollector:
    """Discover profile Reels with Instaloader and download with yt-dlp in a worker thread."""
    def _loader(self, destination: Path) -> instaloader.Instaloader:
        loader = instaloader.Instaloader(
            dirname_pattern=str(destination / "{target}"),
            filename_pattern="{shortcode}",
            download_pictures=False,
            download_videos=True,
            download_video_thumbnails=False,
            download_geotags=False,
            download_comments=False,
            save_metadata=False,
            compress_json=False,
            quiet=True,
            max_connection_attempts=3,
            request_timeout=float(settings.external_timeout_seconds),
        )
        session_file = settings.instagram_session_file
        session_username = settings.instagram_username
        if not session_file or not session_username or not session_file.is_file():
            return loader
        try:
            loader.load_session_from_file(
                session_username,
                str(session_file),
            )
        except instaloader.exceptions.InstaloaderException as error:
            raise InstagramError("Unable to load the Instagram session.") from error
        return loader

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

    def collect(self, username: str, destination: Path) -> list[DownloadedReel]:
        destination.mkdir(parents=True, exist_ok=True)
        loader = self._loader(destination)
        try:
            profile = instaloader.Profile.from_username(loader.context, username)
            if profile.is_private:
                raise PrivateProfile("Профиль закрыт.")
            posts = []
            for post in profile.get_reels():
                posts.append(post)
                if len(posts) == 3:
                    break
        except PrivateProfile:
            raise
        except instaloader.exceptions.TooManyRequestsException as error:
            raise InstagramLimited("Instagram temporarily limited requests.") from error
        except instaloader.exceptions.AbortDownloadException as error:
            raise InstagramBlocked("Instagram stopped access; check the account and session before retrying.") from error
        except instaloader.exceptions.InstaloaderException as error:
            raise InstagramError("Instagram did not return public profile data.") from error

        if not posts:
            raise NoReels("У профиля нет доступных Reels.")

        return [
            self.download_reel(f"https://www.instagram.com/reel/{post.shortcode}/", destination)
            for post in posts
        ]
