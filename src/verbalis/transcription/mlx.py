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

Installing: in a development environment `pip install -e ".[mac-gpu]"`. The Mac app can't pip
install, so `install()` downloads the pinned wheels below from PyPI (about 150 MB, SHA-256
checked) and unpacks them into ~/.verbalis/mlx/site-cpXY; `activate()` adds that folder to
sys.path. mlx-whisper lists torch as a dependency but only its model converter uses it – the
packages the app already contains (numpy, scipy, tqdm, huggingface_hub) are not downloaded.
"""

from __future__ import annotations

import importlib
import json
import platform
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

import numpy as np

from .base import Segment
from .models import ModelError, models_dir, slug, verbalis_home

PREFIX = "mlx:"
WHISPER_SAMPLERATE = 16000
VAD_MIN_SILENCE_MS = 500          # as in FasterWhisperTranscriber


# for Python 3.12 (the Mac app) – other versions pick their own wheels of these versions if PyPI has them
PACKAGES = [
    ("mlx", "0.32.4"), ("mlx-metal", "0.32.4"), ("mlx-whisper", "0.4.3"),
    ("numba", "0.68.0"), ("llvmlite", "0.50.0"),            # word timestamps; numba 0.68 supports numpy < 2.6
    ("tiktoken", "0.14.0"), ("regex", "2026.9.29"), ("more-itertools", "11.2.1"),
    ("requests", "2.34.2"), ("urllib3", "2.8.0"), ("charset-normalizer", "3.5.2"), ("idna", "3.20"),
]
MIN_MACOS = (14, 0)


def site_dir() -> Path:
    return verbalis_home() / "mlx" / f"site-cp{sys.version_info[0]}{sys.version_info[1]}"


def supported() -> str | None:
    """None on a Mac with M chip and macOS 14+, otherwise why not (German)."""
    if sys.platform != "darwin" or platform.machine() != "arm64":
        return "MLX gibt es nur auf Macs mit M-Chip."
    from ..audio.mac_tap import macos_version

    if tuple(macos_version()) < MIN_MACOS:
        return "MLX braucht macOS 14 oder neuer."
    return None


def mac_wheel(names: list[str], python: tuple[int, int], macos: tuple[int, ...]) -> str | None:
    """The best wheel for this Python and macOS: a binary for the newest macOS not newer than ours, else pure Python."""
    cp = f"cp{python[0]}{python[1]}"
    best, best_score = None, None
    for name in names:
        py, abi, plat = name[:-4].split("-")[-3:]
        if not ((py == cp and abi == cp) or (abi == "abi3" and py.startswith("cp") and int(py[2:] or 0) <= int(cp[2:]))
                or (py.startswith("py3") and abi == "none")):
            continue
        score = None
        for tag in plat.split("."):
            if tag == "any":
                score = max(score or (0,), (0,))
            elif tag.startswith("macosx_") and (tag.endswith("_arm64") or tag.endswith("_universal2")):
                version = tuple(int(x) for x in tag.split("_")[1:3])
                if version <= tuple(macos[:2]):
                    score = max(score or (0,), (1, *version))
        if score is not None and (best_score is None or score > best_score):
            best, best_score = name, score
    return best


def activate() -> bool:
    """Make the downloaded MLX packages importable; True if they are there."""
    site = site_dir()
    if not site.is_dir():
        return False
    if str(site) not in sys.path:
        sys.path.append(str(site))   # after the app's own packages: theirs win
    return True


def install(progress: Callable[[str, float], None] | None = None,
            opener: Callable = urllib.request.urlopen) -> Path:
    """Download MLX and mlx-whisper once (Mac app); returns the folder."""
    from ..audio.mac_tap import macos_version
    from . import wheels

    problem = supported()
    if problem:
        raise ModelError(problem)
    python, macos = sys.version_info[:2], tuple(macos_version())
    target = site_dir()
    partial = target.with_name(target.name + ".partial")
    shutil.rmtree(partial, ignore_errors=True)
    partial.mkdir(parents=True)
    try:
        for package, version in PACKAGES:
            info = wheels.wheel_info(package, version, lambda names: mac_wheel(names, python, macos), opener)
            wheel = wheels.download(info, partial, (lambda f, p=package: progress(p, f)) if progress else None,
                                    opener)
            with zipfile.ZipFile(wheel) as archive:
                archive.extractall(partial)
            wheel.unlink()
    except BaseException:
        shutil.rmtree(partial, ignore_errors=True)
        raise
    shutil.rmtree(target, ignore_errors=True)
    partial.replace(target)
    return target


def status() -> dict:
    """For the diagnosis: can this computer use MLX, and is it there?"""
    problem = supported()
    if problem:
        return {"supported": False, "ready": False, "problem": problem}
    activate()
    try:
        importlib.import_module("mlx_whisper")
    except Exception as e:
        return {"supported": True, "ready": False,
                "problem": "MLX ist noch nicht geladen." if isinstance(e, ImportError) else f"MLX lädt nicht: {e}"}
    return {"supported": True, "ready": True, "problem": None}


# built-in names of faster-whisper → the original models in Transformers format
HF_NAMES = {"large-v3": "openai/whisper-large-v3", "large-v3-turbo": "openai/whisper-large-v3-turbo"}


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


# mlx-whisper 0.4.3 loads only weights.safetensors (or weights.npz); newer versions also model.safetensors
WEIGHTS = "weights.safetensors"


def _converted(target: Path) -> bool:
    """Is the model converted already? 0.7.36 saved model.safetensors, which 0.4.3 can't find
    («[load_npz] Input must be a zip file» on the first Mac test) – renamed instead of converting again."""
    if (target / WEIGHTS).exists():
        return True
    if (target / "model.safetensors").exists():
        (target / "model.safetensors").replace(target / WEIGHTS)
        return True
    return False


def convert(model: str) -> Path:
    """Convert a Transformers Whisper model once; returns the MLX folder."""
    target = mlx_folder(model)
    if _converted(target):
        return target
    import mlx.core as mx
    from mlx.utils import tree_flatten
    from mlx_whisper.whisper import ModelDimensions, Whisper

    source = Path(model).expanduser()
    if not source.is_dir():
        from huggingface_hub import snapshot_download

        source = Path(snapshot_download(HF_NAMES.get(model, model), allow_patterns=["config.json", "generation_config.json",
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
    mx.save_safetensors(str(partial / WEIGHTS), dict(tree_flatten(whisper.parameters())))
    (partial / "config.json").write_text(json.dumps({**dims, "model_type": "whisper"}, indent=2), encoding="utf-8")
    partial.replace(target)
    return target


class MlxTranscriber:
    def __init__(self, model: str, keywords: str | None = None):
        activate()
        try:
            import mlx_whisper
        except ImportError as e:
            raise ModelError("mlx-whisper fehlt: in der App Einstellungen → Diagnose → «MLX laden», "
                             'in der Entwicklerversion pip install -e ".[mac-gpu]"') from e
        self._mlx = mlx_whisper
        self.name = PREFIX + model
        self.beam_size = 1
        self.device = "mlx"
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
