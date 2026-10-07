from types import SimpleNamespace

from mitschrift.app import fenstergroesse


def test_standardgroesse_ohne_bildschirm():
    assert fenstergroesse() == (1180, 780)


def test_passt_sich_skaliertem_bildschirm_an():
    full_hd_150 = SimpleNamespace(width=1280, height=720)  # 1920×1080 bei 150 %
    assert fenstergroesse("", full_hd_150) == (1180, 620)


def test_gemerkte_groesse_wird_begrenzt():
    gross = SimpleNamespace(width=2560, height=1440)
    assert fenstergroesse("1400x900", gross) == (1400, 900)
    assert fenstergroesse("5000x3000", gross) == (2520, 1340)
    assert fenstergroesse("100x50", gross) == (860, 560)       # minimiert gespeichert
    assert fenstergroesse("kaputt", gross) == (1180, 780)
