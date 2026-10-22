"""Transcription on the GPU of Apple M chips with MLX (mlx-whisper) – experimental, for measuring.

faster-whisper (CTranslate2) only uses the CPU on Apple Silicon. mlx-whisper runs the same
Whisper weights on the GPU. Differences to FasterWhisperTranscriber:
- no beam search (greedy decoding only), no hotwords – the keywords go into the prompt;
- no silence filter of its own: Silero VAD from faster-whisper finds the speech, and like
  faster-whisper we transcribe only that and map the times back.

Models: a Hugging Face model in Transformers format (model.safetensors + config.json) is
converted once into ~/.verbalis/models/mlx/<slug> (float16, alignment heads for word times
from generation_config.json). The conversion follows convert.py of ml-explore/mlx-examples
(commit e52c128) but reads safetensors directly, so it needs no PyTorch.

In `verbalis compare` the prefix «mlx:» selects this backend: --models gcoli/… mlx:gcoli/…
Install on a Mac: pip install -e ".[mac-gpu]"
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Callable

import numpy as np

from .base import Segment
from .models import ModelError, models_dir, slug

PREFIX = "mlx:"
WHISPER_SAMPLERATE = 16000
VAD_MIN_SILENCE_MS = 500          # as in FasterWhisperTranscriber


def mlx_folder(model: str) -> Path:
    return models_dir() / "mlx" / slug(model)


def hf_dims(config: dict) -> dict:
    """Transformers config.json → mlx-whisper ModelDimensions."""
    return {
        "n_mels": config["num_mel_bins"],
        "n_audio_ctx": config["max_source_positions"],
        "n_audio_state": config["d_model"],
        "n_audio_head": config["encoder_attention_heads"],
        "n_audio_layer": config["encoder_layers"],
        "n_vocab": config["vocab_size"],
        "n_text_ctx": config["max_target_positions"],
        "n_text_state": config["d_model"],
        "n_text_head": config["decoder_attention_heads"],
        "n_text_layer": config["decoder_layers"],
    }


_RENAMES = [
    ("model.", ""), (".layers", ".blocks"), (".self_attn", ".attn"), (".attn_layer_norm", ".attn_ln"),
    (".encoder_attn.", ".cross_attn."), (".encoder_attn_layer_norm", ".cross_attn_ln"),
    (".final_layer_norm", ".mlp_ln"), (".q_proj", ".query"), (".k_proj", ".key"), (".v_proj", ".value"),
    (".out_proj", ".out"), (".fc1", ".mlp1"), (".fc2", ".mlp2"),
    ("embed_positions.weight", "positional_embedding"), ("decoder.embed_tokens", "decoder.token_embedding"),
    ("encoder.layer_norm", "encoder.ln_post"), ("decoder.layer_norm", "decoder.ln"),
]


def mlx_key(key: str) -> str:
    """Transformers weight name → mlx-whisper weight name (same order as convert.py)."""
    for old, new in _RENAMES:
        key = key.replace(old, new)
    return key


def convert(model: str) -> Path:
    """Convert a Transformers Whisper model once; returns the MLX folder."""
    target = mlx_folder(model)
    if (target / "model.safetensors").exists():
        return target
    import mlx.core as mx
    from mlx.utils import tree_flatten
    from mlx_whisper.whisper import ModelDimensions, Whisper

    source = Path(model).expanduser()
    if not source.is_dir():
        from huggingface_hub import snapshot_download

        source = Path(snapshot_download(model, allow_patterns=["config.json", "generation_config.json",
                                                               "model.safetensors"]))
    if not (source / "model.safetensors").exists():
        raise ModelError(f"{model} hat kein model.safetensors (Transformers-Format) – für MLX nicht umwandelbar.")
    print(f"Wandle {model} für MLX um (einmalig) …")
    dims = hf_dims(json.loads((source / "config.json").read_text(encoding="utf-8")))
    weights = {}
    for key, value in mx.load(str(source / "model.safetensors")).items():
        if key == "proj_out.weight":            # shared with the token embedding
            continue
        key = mlx_key(key)
        if key == "encoder.positional_embedding":   # computed by mlx-whisper (sinusoids)
            continue
        if "conv" in key and value.ndim == 3:
            value = value.swapaxes(1, 2)
        weights[key] = value.astype(mx.float16)
    whisper = Whisper(ModelDimensions(**dims), mx.float16)
    expected = {k for k, _ in tree_flatten(whisper.parameters())} - {"alignment_heads"}
    missing = sorted(expected - set(weights))
    if missing:
        raise ModelError(f"Umwandlung von {model} unvollständig, es fehlen: {', '.join(missing[:5])} …")
    whisper.load_weights(list(weights.items()), strict=False)
    generation = source / "generation_config.json"
    heads = json.loads(generation.read_text(encoding="utf-8")).get("alignment_heads") if generation.exists() else None
    if heads:
        whisper.set_alignment_heads(np.array(heads, dtype=np.int32))
    partial = target.with_name(target.name + ".partial")
    shutil.rmtree(partial, ignore_errors=True)
    partial.mkdir(parents=True)
    mx.save_safetensors(str(partial / "model.safetensors"), dict(tree_flatten(whisper.parameters())))
    (partial / "config.json").write_text(json.dumps({**dims, "model_type": "whisper"}, indent=2), encoding="utf-8")
    partial.replace(target)
    return target


class MlxTranscriber:
    def __init__(self, model: str, keywords: str | None = None):
        try:
            import mlx_whisper
        except ImportError as e:
            raise ModelError('mlx-whisper fehlt. Auf einem Mac mit M-Chip: pip install -e ".[mac-gpu]"') from e
        self._mlx = mlx_whisper
        self.name = PREFIX + model
        self.beam_size = 1
        self.keywords = keywords or None
        self.prompt: str | None = None
        self._path = str(convert(model))

    def transcribe(
        self,
        audio: np.ndarray,
        language: str = "de",
        progress: Callable[[float, float], None] | None = None,
    ) -> list[Segment]:
        """audio: mono float32 at 16 kHz (see load_audio)."""
        from faster_whisper.vad import SpeechTimestampsMap, VadOptions, collect_chunks, get_speech_timestamps

        duration = len(audio) / WHISPER_SAMPLERATE
        if duration == 0:
            return []
        chunks = get_speech_timestamps(audio, VadOptions(min_silence_duration_ms=VAD_MIN_SILENCE_MS))
        if not chunks:
            return []
        speech = np.concatenate(collect_chunks(audio, chunks)[0])
        times = SpeechTimestampsMap(chunks, WHISPER_SAMPLERATE)
        prompt = " ".join(p for p in (self.prompt, self.keywords) if p) or None
        result = self._mlx.transcribe(
            speech,
            path_or_hf_repo=self._path,
            language=language,
            task="transcribe",
            condition_on_previous_text=False,
            initial_prompt=prompt,
            word_timestamps=True,
        )
        segments = []
        for s in result["segments"]:
            text = s["text"].strip()
            if not text:
                continue
            words = [(times.get_original_time(w["start"]), times.get_original_time(w["end"], is_end=True), w["word"])
                     for w in s.get("words") or []]
            segments.append(Segment(start=times.get_original_time(s["start"]),
                                    end=times.get_original_time(s["end"], is_end=True),
                                    text=text, words=words or None))
        if progress:
            progress(duration, duration)
        return segments
