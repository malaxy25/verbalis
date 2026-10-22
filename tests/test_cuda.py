"""Nvidia GPU (experimental): choosing the device, CPU fallback, downloading cuBLAS/cuDNN from PyPI."""

import hashlib
import io
import json
import zipfile
from types import SimpleNamespace

import pytest

from verbalis.transcription import cuda, faster
from verbalis.transcription.models import ModelError

LIBS = (["cublasLt64_12.dll", "cublas64_12.dll", "cudnn64_9.dll", "cudnn_ops64_9.dll"] if cuda.WINDOWS else
        ["libcublasLt.so.12", "libcublas.so.12", "libcudnn.so.9", "libcudnn_ops.so.9"])
FOLDER = "bin" if cuda.WINDOWS else "lib"


def test_the_wheel_for_this_system():
    assert cuda.wheel_matches("nvidia_cudnn_cu12-9.10.2.21-py3-none-win_amd64.whl", "win32")
    assert not cuda.wheel_matches("nvidia_cudnn_cu12-9.10.2.21-py3-none-manylinux_2_27_x86_64.whl", "win32")
    assert cuda.wheel_matches("nvidia_cudnn_cu12-9.10.2.21-py3-none-manylinux_2_27_x86_64.whl", "linux", "x86_64")
    assert not cuda.wheel_matches("nvidia_cudnn_cu12-9.10.2.21-py3-none-manylinux_2_27_aarch64.whl", "linux", "aarch64")
    assert not cuda.wheel_matches("nvidia_cudnn_cu12-9.10.2.21-py3-none-win_amd64.whl", "darwin", "arm64")


def test_libraries_in_loading_order_and_what_is_missing(tmp_path):
    for name in reversed(LIBS + ["readme.txt"]):
        (tmp_path / name).write_bytes(b"")
    assert [p.name for p in cuda.find_libraries([tmp_path])] == LIBS      # cuBLAS before cuDNN
    assert cuda.missing(cuda.find_libraries([tmp_path])) == []
    (tmp_path / LIBS[2]).unlink()
    assert cuda.missing(cuda.find_libraries([tmp_path])) == [LIBS[2]]


def test_device_choice(monkeypatch):
    monkeypatch.setattr(cuda, "prepare", lambda: "Keine Nvidia-Grafikkarte gefunden")
    assert cuda.choose("cpu") == ("cpu", "int8")
    assert cuda.choose("auto") == ("cpu", "int8")
    with pytest.raises(ModelError, match="Keine Nvidia"):
        cuda.choose("cuda")
    monkeypatch.setattr(cuda, "prepare", lambda: None)
    assert cuda.choose("auto") == ("cuda", "int8_float16")


class FakeWhisper:
    """faster_whisper.WhisperModel: `fail` = what goes wrong on the GPU ("load" or "run")."""
    fail = None
    loaded: list = []

    def __init__(self, path, device, compute_type):
        FakeWhisper.loaded.append((device, compute_type))
        if device == "cuda" and self.fail == "load":
            raise RuntimeError("CUDA failed with error out of memory")
        self.device = device

    def transcribe(self, audio, **options):
        if self.device == "cuda" and self.fail == "run":
            def broken():
                raise RuntimeError("CUDA failed with error out of memory")
                yield
            return broken(), None
        return iter([SimpleNamespace(start=0.0, end=1.0, text=" Hoi", words=None)]), None


@pytest.fixture
def fake_gpu(monkeypatch):
    import faster_whisper

    FakeWhisper.loaded = []
    monkeypatch.setattr(faster_whisper, "WhisperModel", FakeWhisper)
    monkeypatch.setattr(faster, "resolve", lambda model: model)
    monkeypatch.setattr(cuda, "prepare", lambda: None)
    return FakeWhisper


def test_gpu_used_when_ready(fake_gpu):
    fake_gpu.fail = None
    tr = faster.FasterWhisperTranscriber("m")
    assert tr.device == "cuda" and fake_gpu.loaded == [("cuda", "int8_float16")]


def test_too_little_graphics_memory_falls_back_to_the_cpu(fake_gpu):
    """A GPU that can't hold the model (e.g. T500 with 2 GB) must not stop the transcription."""
    fake_gpu.fail = "load"
    tr = faster.FasterWhisperTranscriber("m")
    assert tr.device == "cpu" and fake_gpu.loaded == [("cuda", "int8_float16"), ("cpu", "int8")]


def test_gpu_error_while_transcribing_repeats_on_the_cpu(fake_gpu):
    import numpy as np

    fake_gpu.fail = "run"
    tr = faster.FasterWhisperTranscriber("m")
    segments = tr.transcribe(np.zeros(16000, dtype=np.float32))
    assert [s.text for s in segments] == ["Hoi"] and tr.device == "cpu"


def test_device_cuda_asked_explicitly_does_not_fall_back(fake_gpu):
    fake_gpu.fail = "load"
    with pytest.raises(ModelError, match="out of memory"):
        faster.FasterWhisperTranscriber("m", device="cuda")


def _wheel(files: dict) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def _pypi(wheels: dict, wrong_sum: bool = False):
    """A fake PyPI: JSON per package and the wheel files."""
    def opener(request, timeout):
        url = request.full_url
        for package, data in wheels.items():
            if url.startswith(f"https://pypi.org/pypi/{package}/"):
                digest = "0" * 64 if wrong_sum else hashlib.sha256(data).hexdigest()
                body = json.dumps({"urls": [{"filename": f"{package}.whl", "url": f"https://files/{package}.whl",
                                             "size": len(data), "digests": {"sha256": digest}}]}).encode()
                return io.BytesIO(body)
            if url == f"https://files/{package}.whl":
                return io.BytesIO(data)
        raise AssertionError(url)
    return opener


@pytest.fixture
def pypi_wheels(monkeypatch, tmp_path):
    monkeypatch.setenv("VERBALIS_HOME", str(tmp_path))
    monkeypatch.setattr(cuda, "wheel_matches", lambda filename: True)
    return {
        "nvidia-cublas-cu12": _wheel({f"nvidia/cublas/{FOLDER}/{LIBS[0]}": b"lt", f"nvidia/cublas/{FOLDER}/{LIBS[1]}": b"b",
                                      "nvidia/cublas/include/cublas.h": b"header"}),
        "nvidia-cudnn-cu12": _wheel({f"nvidia/cudnn/{FOLDER}/{LIBS[2]}": b"dnn", f"nvidia/cudnn/{FOLDER}/{LIBS[3]}": b"ops",
                                     "nvidia_cudnn_cu12-9.dist-info/RECORD": b""}),
    }


def test_install_keeps_only_the_libraries(pypi_wheels, tmp_path):
    target = cuda.install(opener=_pypi(pypi_wheels))
    assert target == tmp_path / "cuda"
    assert sorted(p.name for p in target.iterdir()) == sorted(LIBS + ["versions.json"])
    assert (target / LIBS[2]).read_bytes() == b"dnn"


def test_install_with_a_wrong_checksum_installs_nothing(pypi_wheels, tmp_path):
    with pytest.raises(ModelError, match="Prüfsumme"):
        cuda.install(opener=_pypi(pypi_wheels, wrong_sum=True))
    assert not (tmp_path / "cuda").exists() and not (tmp_path / "cuda.partial").exists()
