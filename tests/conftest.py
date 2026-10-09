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


@pytest.fixture(autouse=True)
def no_real_diarization(monkeypatch):
    """Tests never download or run the diarization models: one speaker per track by default.

    Tests that check speaker diarization set `fake_turns.value` to the turns they want.
    """
    from verbalis import diarization

    turns = type("Turns", (), {"value": [], "real_ensure_models": staticmethod(diarization.ensure_models),
                               "real_models_ready": staticmethod(diarization.models_ready)})()
    monkeypatch.setattr(diarization, "models_ready", lambda folder=None: True)
    monkeypatch.setattr(diarization, "ensure_models", lambda *a, **k: None)
    monkeypatch.setattr(diarization, "find_turns", lambda audio, folder=None: list(turns.value))
    return turns
