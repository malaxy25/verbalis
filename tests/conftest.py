"""Shared test helpers.

Every Service starts a background thread. Without cleanup it keeps running
after the test and could – because the recordings folder changes per test via
VERBALIS_HOME – work on the files of the next test.
"""

import pytest

from verbalis import service


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("VERBALIS_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("MITSCHRIFT_HOME", str(tmp_path / "old-home"))  # never touch a real old folder
    return tmp_path / "home"


@pytest.fixture(autouse=True)
def shutdown_services(monkeypatch):
    created = []
    original = service.Service.__init__

    def remember(self, *args, **kwargs):
        original(self, *args, **kwargs)
        created.append(self)

    monkeypatch.setattr(service.Service, "__init__", remember)
    yield
    for s in created:
        s.shutdown(wait_s=10)
