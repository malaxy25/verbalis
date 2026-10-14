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


def test_download_checks_sha256_and_size(tmp_path):
    import hashlib
    payload = b"installer" * 1000
    good = hashlib.sha256(payload).hexdigest()
    target = updates.download_installer("https://dl/x.exe", tmp_path / "ok.exe", None,
                                        opener=fake_opener(payload), sha256=good, size=len(payload))
    assert target.read_bytes() == payload
    with pytest.raises(RuntimeError, match="Prüfsumme"):
        updates.download_installer("https://dl/x.exe", tmp_path / "bad.exe", None,
                                   opener=fake_opener(payload), sha256="0" * 64, size=len(payload))
    with pytest.raises(RuntimeError, match="unvollständig"):
        updates.download_installer("https://dl/x.exe", tmp_path / "short.exe", None,
                                   opener=fake_opener(payload[:100]), size=len(payload))
    assert not (tmp_path / "bad.exe").exists() and not list(tmp_path.glob("*.part"))   # nothing left to run


def test_check_reads_the_github_digest_and_name(monkeypatch):
    monkeypatch.setattr(updates.sys, "platform", "win32")
    release = {"tag_name": "v99.0.0", "assets": [{"name": "Verbalis-99.0.0-setup.exe", "size": 5,
               "browser_download_url": "https://dl/win.exe", "digest": "sha256:ABC123"}]}
    info = updates.check(opener=fake_opener(release))
    assert info["installer_sha256"] == "abc123" and info["installer_size"] == 5
    assert updates.expected_name(info)
    assert not updates.expected_name({**info, "installer_name": "Verbalis-98.0.0-setup.exe"})


def test_mac_app_finds_certificates(monkeypatch):
    """0.7.19 bug on macOS: the update check failed with «CERTIFICATE_VERIFY_FAILED» – the Python
    inside the Mac app has no CA certificates. certifi's are used instead."""
    import os

    import certifi

    import verbalis
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    verbalis._certificates_on_macos("win32")
    assert "SSL_CERT_FILE" not in os.environ                 # Windows uses its own certificate store
    verbalis._certificates_on_macos("darwin")
    assert os.environ["SSL_CERT_FILE"] == certifi.where() and os.path.exists(certifi.where())
    monkeypatch.setenv("SSL_CERT_FILE", "/company/ca.pem")
    verbalis._certificates_on_macos("darwin")
    assert os.environ["SSL_CERT_FILE"] == "/company/ca.pem"  # a certificate file set by IT wins


def test_app_started_from_downloads_is_recognised():
    """0.7.21 on macOS: «Verbalis darf /private/var/folders/… nicht ändern» – the app had been started
    from «Downloads», so macOS ran a read-only copy. The message now says to move it to «Programme»."""
    from pathlib import PurePosixPath
    copy = PurePosixPath("/private/var/folders/od/k2wb/T/AppTranslocation/D4/d/Verbalis.app")
    assert updates.translocated(copy)
    assert not updates.translocated(PurePosixPath("/Applications/Verbalis.app"))


def test_mac_app_in_a_locked_folder_offers_the_download(monkeypatch):
    """0.7.22 on a Mac without admin rights: «Verbalis darf /Applications nicht ändern» – and no way on.
    The update dialog now explains it and opens the download of the new version."""
    import sys
    from pathlib import PurePosixPath

    from verbalis import service as service_module
    from verbalis.service import Service
    from verbalis.settings import Settings
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(updates, "app_bundle", lambda: PurePosixPath("/Applications/Verbalis.app"))
    monkeypatch.setattr(updates, "can_write", lambda folder: False)
    s = Service(settings=Settings(), list_devices=lambda: {}, cleanup_on_start=False)
    url = "https://github.com/malaxy25/verbalis/releases/download/v9.9.9/Verbalis-9.9.9-macos-arm64.zip"
    s._update = {"available": True, "can_install": True, "latest": "9.9.9", "installer_url": url}
    info = s.update_info()
    assert info["can_install"] is False and "Administratorkonto" in info["manual"]
    opened = []
    monkeypatch.setattr("webbrowser.open", opened.append)
    s.open_update_download()
    s._update["installer_url"] = "https://example.com/evil.zip"
    s.open_update_download()
    assert opened == [url, "https://github.com/malaxy25/verbalis/releases/latest"]
    assert service_module.sys.platform == "darwin"


def test_test_build_gets_the_real_release_as_update():
    """A test build «0.7.23.dev1» (manual build, not released) must see the release 0.7.23 as newer."""
    assert updates.is_newer("0.7.23", "0.7.23.dev1")
    assert not updates.is_newer("0.7.23.dev1", "0.7.23")
    assert updates.is_newer("0.7.23.dev2", "0.7.23.dev1") and updates.is_newer("0.7.23.dev1", "0.7.22")


# ---------------------------------------------------------------- macOS: install into «Programme»

def _app(folder, version="0.7.26"):
    import plistlib
    app = folder / "Verbalis.app"
    (app / "Contents").mkdir(parents=True)
    with open(app / "Contents" / "Info.plist", "wb") as f:
        plistlib.dump({"CFBundleShortVersionString": version}, f)
    return app


def test_where_verbalis_lies_and_where_it_goes(tmp_path):
    """0.7.26: started from «Downloads», «Schreibtisch» or the disk image, Verbalis offers to move itself."""
    from pathlib import PurePosixPath
    home = tmp_path / "home"
    assert updates.install_place(home / "Applications" / "Verbalis.app", home) is None
    assert "Desktop" in updates.install_place(home / "Desktop" / "Verbalis.app", home)
    assert "schreibgeschützt" in updates.install_place(
        PurePosixPath("/private/var/folders/x/T/AppTranslocation/A/d/Verbalis.app"), home)
    assert "Disk-Image" in updates.install_place(PurePosixPath("/Volumes/Verbalis/Verbalis.app"), home)
    # without administrator rights: the personal «Programme» folder
    assert updates.install_target(home, writable=lambda folder: False) == home / "Applications"


def test_move_into_the_personal_programme_folder(tmp_path):
    """Andrea's case: no administrator account, Verbalis on the desktop – it ends up in ~/Applications,
    without a second copy, an older one there is replaced."""
    home = tmp_path / "home"
    desktop_app = _app(home / "Desktop")
    _app(home / "Applications", version="0.7.20")             # an older one is already there
    calls = []
    target, left = updates.move_to_applications(desktop_app, home, writable=lambda f: False,
                                                run=lambda cmd, check: calls.append(cmd[0]))
    assert target == home / "Applications" / "Verbalis.app" and left is None
    assert not desktop_app.exists() and updates.bundle_version(target) == "0.7.26"
    assert not (home / "Applications" / "Verbalis.app.old").exists()
    assert calls == ["xattr"]                                  # quarantine removed, nothing copied


def test_translocated_copy_moves_its_original_from_downloads(tmp_path, monkeypatch):
    home = tmp_path / "home"
    original = _app(home / "Downloads")
    running = _app(tmp_path / "AppTranslocation" / "d")        # the read-only copy macOS runs
    monkeypatch.setattr(updates, "translocated", lambda bundle: "AppTranslocation" in str(bundle))
    target, left = updates.move_to_applications(running, home, writable=lambda f: False,
                                                run=lambda cmd, check: None)
    assert target == home / "Applications" / "Verbalis.app" and not original.exists() and left is None


def test_relaunch_script_starts_the_moved_app(tmp_path):
    script = updates.write_relaunch_script(tmp_path / "Applications" / "Verbalis.app", 4242, tmp_path / "r.sh")
    text = script.read_text(encoding="utf-8")
    assert "kill -0 4242" in text and "open " in text and "Verbalis.app" in text
