"""Verbalis – record and transcribe conversations locally."""

import os as _os

# Hide Hugging Face notices that are irrelevant to users (missing symlinks on
# Windows, info messages). Must happen before huggingface_hub is first imported.
_os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
_os.environ.setdefault("HF_HUB_VERBOSITY", "error")

__version__ = "0.7.13"
