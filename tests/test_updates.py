import io
import json
from contextlib import contextmanager

import pytest

from verbalis import __version__, updates

CHANGELOG = """# Changelog

## 0.8.0 – 2026-11-01
- Big feature

## 0.7.5 – 2026-10-20
- Small fix

## 0.7.4 – 2026-10-08
- Earlier
"""


def fake_opener(payload: dict | bytes, headers=None):
    @contextmanager
    def opener(request, timeout=None):
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        response = io.BytesIO(body)
        response.headers = headers or {"Content-Length": str(len(body))}
        yield response
    return opener


def test_versions():
    assert updates.parse_version("v0.7.4") == (0, 7, 4)
    assert updates.parse_version("garbage") == ()
    assert updates.is_newer("0.7.10", "0.7.9") and not updates.is_newer("0.7.4", "0.7.4")
    assert not updates.is_newer("", "0.7.4")


def test_check_finds_newer_release_and_installer():
    release = {"tag_name": "v99.0.0", "body": "- Neu", "html_url": "https://github.com/x",
               "assets": [{"name": "Verbalis-99.0.0-setup.exe", "browser_download_url": "https://dl/x.exe",
                           "size": 250_000_000}]}
    info = updates.check(opener=fake_opener(release))
    assert info["available"] and info["latest"] == "99.0.0" and info["current"] == __version__
    assert info["installer_url"] == "https://dl/x.exe" and info["installer_mb"] == 250
    assert info["can_install"] is False      # tests run from a checkout, not the installer


def test_check_same_version_is_not_available():
    info = updates.check(opener=fake_opener({"tag_name": f"v{__version__}", "assets": []}))
    assert not info["available"] and info["installer_url"] is None


def test_download_installer(tmp_path):
    seen = []
    target = updates.download_installer("https://dl/x.exe", tmp_path / "setup.exe", seen.append,
                                        opener=fake_opener(b"x" * 3_000_000))
    assert target.read_bytes() == b"x" * 3_000_000 and seen[-1] == 1.0


def test_changes_between_versions():
    sections = updates.changes_between("0.7.4", "0.8.0", text=CHANGELOG)
    assert [s["version"] for s in sections] == ["0.8.0", "0.7.5"]
    assert sections[1]["body"] == "- Small fix" and sections[0]["title"].startswith("0.8.0")
    assert updates.changes_between("0.8.0", "0.8.0", text=CHANGELOG) == []


def test_bundled_changelog_has_current_version():
    assert updates.changelog_path() is not None
    assert updates.changes_between("0.0.0")[0]["version"] == __version__


@pytest.fixture
def service():
    from verbalis.service import Service
    from verbalis.settings import Settings
    return Service(settings=Settings(), list_devices=lambda: {}, cleanup_on_start=False)


def test_whats_new_first_start_and_after_update(service):
    assert service.whats_new() == []                      # very first start: nothing to show
    service.save_settings({"last_seen_version": "0.7.3"})
    entries = service.whats_new()
    assert entries and entries[0]["version"] == __version__
    service.whats_new_seen()
    assert service.whats_new() == []


def test_install_update_guards(service):
    with pytest.raises(RuntimeError, match="kein Update"):
        service.install_update()
    service._update = {"available": True, "can_install": False, "latest": "99.0.0"}
    with pytest.raises(RuntimeError, match="git"):
        service.install_update()
    assert service.state()["update"] == {"latest": "99.0.0"}


def test_update_check_setting_is_validated():
    from verbalis.settings import Settings
    assert Settings.from_dict({"update_check": "maybe"}).update_check == "on"
    assert Settings.from_dict({"update_check": "off"}).update_check == "off"
