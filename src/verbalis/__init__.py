"""Verbalis – record and transcribe conversations locally."""

import os as _os

# Hide Hugging Face notices that are irrelevant to users (missing symlinks on
# Windows, info messages). Must happen before huggingface_hub is first imported.
_os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
_os.environ.setdefault("HF_HUB_VERBOSITY", "error")


def _certificates_on_macos(platform: str | None = None) -> None:
    """The Python inside the Mac app has no CA certificates, so every HTTPS download through the
    standard library failed («CERTIFICATE_VERIFY_FAILED»: update check, diarization models,
    dictionary). Use certifi's – it is bundled anyway (huggingface-hub needs it)."""
    import sys

    if (platform or sys.platform) != "darwin" or _os.environ.get("SSL_CERT_FILE"):
        return
    try:
        import certifi
    except ImportError:
        return
    _os.environ["SSL_CERT_FILE"] = certifi.where()


_certificates_on_macos()

__version__ = "0.7.25"
