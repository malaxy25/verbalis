"""Update check, installer download, macOS bundle swap, what's new from the changelog."""

import io
import json
import sys
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


def test_check_finds_newer_release_and_installer(monkeypatch):
    monkeypatch.setattr(updates.sys, "platform", "win32")
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


def _fake_app(folder, version):
    app = folder / "Verbalis.app"
    (app / "Contents" / "MacOS").mkdir(parents=True)
    (app / "Contents" / "MacOS" / "Verbalis").write_text(version)
    return app


def test_app_bundle_found_from_executable(tmp_path):
    app = _fake_app(tmp_path, "0.7.9")
    assert updates.app_bundle(str(app / "Contents" / "MacOS" / "Verbalis")) == app
    assert updates.app_bundle(str(tmp_path / "python")) is None


@pytest.mark.skipif(sys.platform == "win32", reason="the swap script is a macOS shell script")
def test_mac_update_swaps_bundle_after_app_closed(tmp_path):
    import subprocess
    import time
    applications = tmp_path / "Applications"
    old = _fake_app(applications, "old")
    staged = applications / ".verbalis-update"

    def fake_extract(zip_path, dest):          # stands in for ditto on Linux
        _fake_app(dest, "new")

    new = updates.unpack_mac_update(tmp_path / "update.zip", staged, extract=fake_extract)
    running = subprocess.Popen(["sleep", "1"])  # stands in for the running Verbalis
    opened = tmp_path / "opened.txt"
    script = updates.write_swap_script(old, new, running.pid, tmp_path / "swap.sh",
                                       reopen=f"echo >{opened}")
    proc = subprocess.Popen(["/bin/sh", str(script)])
    time.sleep(0.3)
    assert (old / "Contents" / "MacOS" / "Verbalis").read_text() == "old"   # still waiting
    running.wait()
    proc.wait(timeout=10)
    assert (old / "Contents" / "MacOS" / "Verbalis").read_text() == "new"
    assert not staged.exists() and not (applications / "Verbalis.app.old").exists()
    assert opened.exists() and not script.exists()


@pytest.mark.skipif(sys.platform == "win32", reason="the swap script is a macOS shell script")
def test_mac_update_rolls_back_if_new_app_missing(tmp_path):
    import subprocess
    applications = tmp_path / "Applications"
    old = _fake_app(applications, "old")
    missing = applications / ".verbalis-update" / "Verbalis.app"
    script = updates.write_swap_script(old, missing, 999999, tmp_path / "swap.sh", reopen="true")
    subprocess.run(["/bin/sh", str(script)], timeout=10, check=True)
    assert (old / "Contents" / "MacOS" / "Verbalis").read_text() == "old"   # old version restored


def test_check_picks_the_asset_for_this_platform(monkeypatch):
    release = {"tag_name": "v99.0.0", "assets": [
        {"name": "Verbalis-99.0.0-setup.exe", "browser_download_url": "https://dl/win.exe", "size": 1},
        {"name": "Verbalis-99.0.0-macos-arm64.zip", "browser_download_url": "https://dl/mac.zip", "size": 1}]}
    monkeypatch.setattr(updates.sys, "platform", "darwin")
    assert updates.check(opener=fake_opener(release))["installer_url"] == "https://dl/mac.zip"
    monkeypatch.setattr(updates.sys, "platform", "win32")
    assert updates.check(opener=fake_opener(release))["installer_url"] == "https://dl/win.exe"
