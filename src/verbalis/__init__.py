"""Verbalis – record and transcribe conversations locally."""

import os as _os

# Hide Hugging Face notices that are irrelevant to users (missing symlinks on
# Windows, info messages). Must happen before huggingface_hub is first imported.
_os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
_os.environ.setdefault("HF_HUB_VERBOSITY", "error")


def _certificates_on_macos(platform: str | None = None) -> None:
    """The Python inside the Mac app has no CA certificates, so every HTTPS download through the
    standard library failed («CERTIFICATE_VERIFY_FAILED»: update check, diarization models,
    dictionary). Use certifi's – it is bundled anyway (huggingface-hub needs it).

    A value set by IT is kept. A value set by an earlier Verbalis process is not: after the app moved
    itself into «Programme» (0.7.26), the restarted app inherited the old path inside the vanished
    translocated copy, and every model download failed with «[Errno 2] No such file or directory» (0.7.28)."""
    import sys

    if (platform or sys.platform) != "darwin":
        return
    current = _os.environ.get("SSL_CERT_FILE")
    if current and _os.path.isfile(current) and not _os.environ.get(_OWN_CERT_MARK):
        return
    try:
        import certifi
    except ImportError:
        return
    _os.environ["SSL_CERT_FILE"] = certifi.where()
    _os.environ[_OWN_CERT_MARK] = "1"


_OWN_CERT_MARK = "VERBALIS_SSL_CERT_FILE_SET"


_certificates_on_macos()

__version__ = "0.7.30"
