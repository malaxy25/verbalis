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
