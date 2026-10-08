import json

import pytest

from verbalis.transcription import models


def test_builtin_names_and_hf_ids_pass_through():
    assert models.resolve("large-v3-turbo") == "large-v3-turbo"
    assert models.resolve("Systran/faster-whisper-large-v3") == "Systran/faster-whisper-large-v3"


def test_converted_model_is_preferred(home):
    target = home / "models" / "Flix-AI__flix-swissgerman-full"
    target.mkdir(parents=True)
    (target / "model.bin").write_bytes(b"x")
    (target / "verbalis.json").write_text(json.dumps({"source": "Flix-AI/flix-swissgerman-full"}))
    assert models.resolve("Flix-AI/flix-swissgerman-full") == str(target)
    assert models.converted_models() == ["Flix-AI/flix-swissgerman-full"]


def test_local_folder_without_model_bin(tmp_path):
    with pytest.raises(models.ModelError):
        models.resolve(str(tmp_path))


def test_unknown_name():
    with pytest.raises(models.ModelError):
        models.resolve("doesnotexist")


def test_mel_bins_pick_base_model():
    assert models._base_model_for(128) == "openai/whisper-large-v3"
    assert models._base_model_for(80) == "openai/whisper-large-v2"


def test_repo_check():
    models.check_repo("x/ok", {"config.json", "model.safetensors"})
    with pytest.raises(models.ModelError, match="zurückgezogen"):
        models.check_repo("x/gone", {"config.json", "README.md"})
    with pytest.raises(models.ModelError, match="LoRA"):
        models.check_repo("x/lora", {"adapter_config.json", "adapter_model.safetensors"})
    with pytest.raises(models.ModelError, match="CTranslate2"):
        models.check_repo("x/ct2", {"config.json", "model.bin"})


def test_download_sources():
    assert models.repo_for("Flix-AI/flix-swissgerman-full") == "malaxy25/flix-swissgerman-ct2"
    assert models.resolve("Flix-AI/flix-swissgerman-full") == "malaxy25/flix-swissgerman-ct2"
    assert models.repo_for("large-v3") == "Systran/faster-whisper-large-v3"
    assert models.repo_for("someone/faster-model") == "someone/faster-model"


def test_converted_model_is_local_and_needs_no_download(home):
    target = home / "models" / "Flix-AI__flix-swissgerman-full"
    target.mkdir(parents=True)
    (target / "model.bin").write_bytes(b"x")
    assert models.repo_for("Flix-AI/flix-swissgerman-full") is None
    assert models.is_local("Flix-AI/flix-swissgerman-full")


def test_cached_model_is_local(tmp_path, monkeypatch):
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path))
    import huggingface_hub.constants as c
    monkeypatch.setattr(c, "HF_HUB_CACHE", str(tmp_path))
    assert not models.is_local("large-v3-turbo")
    snap = tmp_path / "models--mobiuslabsgmbh--faster-whisper-large-v3-turbo" / "snapshots" / "abc"
    snap.mkdir(parents=True)
    (snap / "model.bin").write_bytes(b"x")
    refs = snap.parents[1] / "refs"
    refs.mkdir()
    (refs / "main").write_text("abc")
    assert models.is_local("large-v3-turbo")


def test_download_reports_progress_and_errors(tmp_path, monkeypatch):
    import huggingface_hub
    import huggingface_hub.constants as c
    monkeypatch.setattr(c, "HF_HUB_CACHE", str(tmp_path))

    def fake_snapshot(repo, allow_patterns):
        import time
        folder = tmp_path / ("models--" + repo.replace("/", "--")) / "blobs"
        folder.mkdir(parents=True)
        (folder / "a").write_bytes(b"x" * 1000)
        time.sleep(0.7)

    monkeypatch.setattr(huggingface_hub, "snapshot_download", fake_snapshot)
    seen = []
    models.download("large-v3", seen.append)
    assert seen and seen[-1] == 1000

    def failing(repo, allow_patterns):
        raise OSError("offline")
    monkeypatch.setattr(huggingface_hub, "snapshot_download", failing)
    with pytest.raises(models.ModelError, match="Internetverbindung"):
        models.download("large-v3")
