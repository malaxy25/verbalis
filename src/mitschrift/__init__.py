"""Mitschrift – lokale Gesprächsaufnahme und Transkription."""

import os as _os

# Hinweise von Hugging Face ausblenden, die für Nutzer:innen nicht relevant sind
# (fehlende Symlinks unter Windows, Info-Meldungen). Muss vor dem ersten Import
# von huggingface_hub passieren, deshalb hier.
_os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
_os.environ.setdefault("HF_HUB_VERBOSITY", "error")

__version__ = "0.6.0"
