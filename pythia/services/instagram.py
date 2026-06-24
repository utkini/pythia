import re
from pathlib import Path
from urllib.parse import urlparse

import instaloader

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


class InstagramCollector:
    """Synchronous Instaloader adapter; call it from a worker thread."""
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

    @staticmethod
    def _metadata(post: instaloader.Post) -> ReelMetadata:
        views = getattr(post, "video_view_count", None) or getattr(post, "video_play_count", None)
        return ReelMetadata(
            shortcode=post.shortcode,
            url=f"https://www.instagram.com/reel/{post.shortcode}/",
            caption=post.caption,
            published_at=post.date_utc,
            likes_count=post.likes,
            views_count=views,
            comments_count=post.comments,
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
        except instaloader.exceptions.InstaloaderException as error:
            raise InstagramError("Instagram did not return public profile data.") from error

        if not posts:
            raise NoReels("У профиля нет доступных Reels.")

        downloaded: list[DownloadedReel] = []
        for post in posts:
            metadata = self._metadata(post)
            try:
                loader.download_post(post, target=metadata.shortcode)
                matches = sorted((destination / metadata.shortcode).glob("*.mp4"), key=lambda path: path.stat().st_mtime)
                if not matches:
                    raise InstagramError(f"No video file was downloaded for {metadata.shortcode}.")
                downloaded.append(DownloadedReel(metadata=metadata, video_path=matches[-1]))
            except instaloader.exceptions.TooManyRequestsException as error:
                raise InstagramLimited("Instagram temporarily limited requests.") from error
            except instaloader.exceptions.InstaloaderException as error:
                raise InstagramError(f"Unable to download Reel {metadata.shortcode}.") from error
        return downloaded
