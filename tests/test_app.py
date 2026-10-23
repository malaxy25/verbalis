"""Window size and position, log output without console, file dialog filter."""

from types import SimpleNamespace

from verbalis.app import _ToLog, window_position, window_size


def test_default_size_without_screen():
    assert window_size() == (1180, 780)


def test_adapts_to_scaled_screen():
    full_hd_150 = SimpleNamespace(width=1280, height=720)  # 1920×1080 at 150 %
    assert window_size("", full_hd_150) == (1180, 620)


def test_remembered_size_is_limited():
    big = SimpleNamespace(width=2560, height=1440)
    assert window_size("1400x900", big) == (1400, 900)
    assert window_size("5000x3000", big) == (2520, 1340)
    assert window_size("100x50", big) == (860, 560)       # saved while minimised
    assert window_size("broken", big) == (1180, 780)


def test_window_centered_in_free_area():
    full_hd_150 = SimpleNamespace(x=0, y=0, width=1280, height=720)          # no WorkingArea
    assert window_position(1180, 620, full_hd_150) == (50, 26)              # 720 − 48 taskbar
    windows = SimpleNamespace(x=0, y=0, width=1280, height=720, scale=1.5,
                              frame=SimpleNamespace(X=0, Y=0, Width=1280, Height=688))
    assert window_position(1180, 620, windows) == (50, 34)                  # taskbar 32 high
    second = SimpleNamespace(x=1920, y=0, width=1920, height=1080)
    assert window_position(1180, 780, second)[0] == 1920 + 370
    assert window_position(1180, 780, None) == (None, None)


def test_log_replacement_handles_progress_bars():
    from tqdm import tqdm

    replacement = _ToLog(20)
    for _ in tqdm(range(3), file=replacement):
        pass
    assert replacement.write("x\n") == 2 and not replacement.isatty()


def test_zip_filter_is_valid_for_pywebview():
    """Regression 0.7.3: «ZIP-Datei (*.zip)» was rejected by the save dialog."""
    from webview.util import parse_file_type

    from verbalis.app import ZIP_FILTER

    assert parse_file_type(ZIP_FILTER) == ("ZIP Archiv", "*.zip")



def test_taskbar_identity_only_for_development_version_on_windows():
    """Regression: the development version showed the Python logo in the taskbar."""
    from verbalis.app import set_taskbar_identity

    calls = []

    class Shell32:
        def SetCurrentProcessExplicitAppUserModelID(self, app_id):
            calls.append(app_id)

    assert set_taskbar_identity("win32", frozen=False, shell32=Shell32()) is True
    assert calls == ["Frehner.Verbalis"]
    assert set_taskbar_identity("win32", frozen=True, shell32=Shell32()) is False   # Verbalis.exe has its own
    assert set_taskbar_identity("darwin", frozen=False, shell32=Shell32()) is False
    assert len(calls) == 1


def test_app_ends_without_python_clean_up_only_while_audio_is_open_on_mac():
    """Regression 0.7.33: on the Mac the app sometimes crashed on quitting (after waking up) – a CoreAudio
    thread handed audio to Python while Python was shutting down."""
    from verbalis.app import audio_still_open

    meter = SimpleNamespace(name="track-me", is_alive=lambda: True)
    ended = SimpleNamespace(name="track-others", is_alive=lambda: False)
    other = SimpleNamespace(name="level-monitor", is_alive=lambda: True)
    assert audio_still_open("darwin", [meter])
    assert not audio_still_open("darwin", [ended, other])
    assert not audio_still_open("win32", [meter])


def test_linux_without_gtk_bindings_starts_qt_directly():
    """pipx on Ubuntu: no `gi` → pywebview logged «GTK cannot be loaded» with a traceback twice before Qt."""
    from verbalis.app import window_library

    assert window_library("linux", has_gtk=False) == "qt"
    assert window_library("linux", has_gtk=True) is None
    assert window_library("win32") is None and window_library("darwin") is None
