"""MLX on Apple M chips (experimental): model conversion names, times after the silence filter, missing package."""

import sys
from types import SimpleNamespace

import numpy as np
import pytest

from verbalis.transcription import mlx
from verbalis.transcription.models import ModelError


def test_transformers_names_become_mlx_names():
    assert mlx.mlx_key("model.encoder.layers.3.self_attn.q_proj.weight") == "encoder.blocks.3.attn.query.weight"
    assert mlx.mlx_key("model.decoder.layers.0.encoder_attn.out_proj.bias") == "decoder.blocks.0.cross_attn.out.bias"
    assert mlx.mlx_key("model.decoder.layers.1.encoder_attn_layer_norm.weight") == "decoder.blocks.1.cross_attn_ln.weight"
    assert mlx.mlx_key("model.decoder.layers.1.final_layer_norm.bias") == "decoder.blocks.1.mlp_ln.bias"
    assert mlx.mlx_key("model.encoder.layers.2.fc1.weight") == "encoder.blocks.2.mlp1.weight"
    assert mlx.mlx_key("model.decoder.embed_tokens.weight") == "decoder.token_embedding.weight"
    assert mlx.mlx_key("model.decoder.embed_positions.weight") == "decoder.positional_embedding"
    assert mlx.mlx_key("model.encoder.layer_norm.weight") == "encoder.ln_post.weight"
    assert mlx.mlx_key("model.decoder.layer_norm.weight") == "decoder.ln.weight"


def test_dimensions_from_transformers_config():
    config = {"num_mel_bins": 128, "max_source_positions": 1500, "d_model": 1280, "encoder_attention_heads": 20,
              "encoder_layers": 32, "vocab_size": 51866, "max_target_positions": 448, "decoder_attention_heads": 20,
              "decoder_layers": 4}
    assert mlx.hf_dims(config) == {"n_mels": 128, "n_audio_ctx": 1500, "n_audio_state": 1280, "n_audio_head": 20,
                                   "n_audio_layer": 32, "n_vocab": 51866, "n_text_ctx": 448, "n_text_state": 1280,
                                   "n_text_head": 20, "n_text_layer": 4}


def test_without_mlx_whisper_a_clear_message(monkeypatch):
    monkeypatch.setitem(sys.modules, "mlx_whisper", None)    # import fails
    with pytest.raises(ModelError, match="mac-gpu"):
        mlx.MlxTranscriber("gcoli/whisper-large-v3-turbo-swiss-german-mit")


def test_only_speech_is_transcribed_and_times_point_into_the_recording(monkeypatch, tmp_path):
    calls = []

    def transcribe(audio, **options):
        calls.append((len(audio), options))
        # the speech-only audio: 2 s from 1–3 s, then 1 s from 10–11 s of the recording
        return {"segments": [
            {"start": 0.0, "end": 2.0, "text": " Grüezi mitenand", "words": [
                {"start": 0.0, "end": 0.8, "word": " Grüezi"}, {"start": 0.9, "end": 2.0, "word": " mitenand"}]},
            {"start": 2.0, "end": 3.0, "text": " Tocco", "words": [{"start": 2.1, "end": 2.9, "word": " Tocco"}]},
            {"start": 3.0, "end": 3.0, "text": " ", "words": []},
        ]}

    monkeypatch.setitem(sys.modules, "mlx_whisper", SimpleNamespace(transcribe=transcribe))
    monkeypatch.setattr(mlx, "convert", lambda model: tmp_path)
    import faster_whisper.vad as vad
    monkeypatch.setattr(vad, "get_speech_timestamps",
                        lambda audio, options: [{"start": 16000, "end": 48000}, {"start": 160000, "end": 176000}])

    tr = mlx.MlxTranscriber("gcoli/whisper-large-v3-turbo-swiss-german-mit", keywords="Tocco, Höngg")
    tr.prompt = "Andrea"
    segments = tr.transcribe(np.zeros(12 * 16000, dtype=np.float32))

    assert calls[0][0] == 3 * 16000                     # 9 s of silence are not sent
    assert calls[0][1]["initial_prompt"] == "Andrea Tocco, Höngg"   # no hotwords in MLX: keywords in the prompt
    assert "beam_size" not in calls[0][1]               # mlx-whisper has no beam search
    assert [(s.start, s.end, s.text) for s in segments] == [(1.0, 3.0, "Grüezi mitenand"), (10.0, 11.0, "Tocco")]
    assert segments[0].words == [(1.0, 1.8, " Grüezi"), (1.9, 3.0, " mitenand")]
    assert segments[1].words == [(10.1, 10.9, " Tocco")]
    assert tr.name == "mlx:gcoli/whisper-large-v3-turbo-swiss-german-mit"


def test_silence_only_sends_nothing(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "mlx_whisper", SimpleNamespace(transcribe=lambda *a, **k: pytest.fail("called")))
    monkeypatch.setattr(mlx, "convert", lambda model: tmp_path)
    import faster_whisper.vad as vad
    monkeypatch.setattr(vad, "get_speech_timestamps", lambda audio, options: [])
    assert mlx.MlxTranscriber("x/y").transcribe(np.zeros(16000, dtype=np.float32)) == []


def test_model_converted_by_0_7_36_is_renamed_not_converted_again(tmp_path, monkeypatch):
    """First Mac test (0.7.36): «[load_npz] Input must be a zip file» – the conversion saved
    model.safetensors, but mlx-whisper 0.4.3 only loads weights.safetensors."""
    monkeypatch.setenv("VERBALIS_HOME", str(tmp_path))
    folder = mlx.mlx_folder("gcoli/whisper-large-v3-turbo-swiss-german-mit")
    folder.mkdir(parents=True)
    (folder / "model.safetensors").write_bytes(b"weights")
    (folder / "config.json").write_text("{}")
    assert mlx.convert("gcoli/whisper-large-v3-turbo-swiss-german-mit") == folder   # no mlx needed: nothing to convert
    assert (folder / "weights.safetensors").read_bytes() == b"weights"
    assert not (folder / "model.safetensors").exists()
