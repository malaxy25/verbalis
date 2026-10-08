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
