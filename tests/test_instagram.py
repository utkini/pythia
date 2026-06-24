import pytest

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
