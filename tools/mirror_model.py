"""Copy one exact revision of a model to our own Hugging Face repo (a mirror), so it can't vanish or change.

Verbalis then downloads from the mirror (DOWNLOAD_REPO in src/verbalis/transcription/models.py). The
monthly check (.github/workflows/model-check.yml) opens an issue when the original gets a newer
version; after comparing it, run this script again with the new revision.

    hf auth login                     # once, with a token that may write
    python tools/mirror_model.py gcoli          # what is set up in MIRRORS below

Only the CTranslate2 files are copied (to the repo root), plus a model card with licence and credits,
the original README (as ORIGINAL_README.md) and – if present – the original's provenance file.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent

MIRRORS = {
    "gcoli": {
        "original": "gcoli/whisper-large-v3-turbo-swiss-german-mit",
        "revision": "540fb2e7a9135048963c5de9822579c96f8962e5",
        "subfolder": "ct2",
        "extra": ["README.md", "training_provenance.json"],
        "mirror": "malaxy/whisper-large-v3-turbo-swiss-german-ct2",
        "card": HERE / "gcoli-model" / "README.md",
        "licence": HERE / "gcoli-model" / "LICENSE",
    },
}
CT2_FILES = ["config.json", "model.bin", "preprocessor_config.json", "tokenizer.json", "vocabulary.*"]


def mirror(name: str, revision: str | None = None, dry_run: bool = False) -> str:
    from huggingface_hub import HfApi, snapshot_download

    setup = MIRRORS[name]
    revision = revision or setup["revision"]
    sub = setup["subfolder"]
    api = HfApi()
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "source"
        print(f"Downloading {setup['original']} @ {revision[:7]} …")
        snapshot_download(setup["original"], revision=revision, local_dir=source,
                          allow_patterns=[f"{sub}/{f}" if sub else f for f in CT2_FILES] + setup["extra"])
        staged = Path(tmp) / "staged"
        shutil.copytree(source / sub if sub else source, staged,
                        ignore=shutil.ignore_patterns(".cache", *setup["extra"]))
        if not (staged / "model.bin").exists():
            raise SystemExit("model.bin missing – wrong subfolder or revision?")
        card = setup["card"].read_text(encoding="utf-8").replace("{revision}", revision).replace("{short}", revision[:7])
        (staged / "README.md").write_text(card, encoding="utf-8")
        shutil.copy(setup["licence"], staged / "LICENSE")
        if (source / "README.md").exists():
            shutil.copy(source / "README.md", staged / "ORIGINAL_README.md")
        for extra in setup["extra"]:
            if extra != "README.md" and (source / extra).exists():
                shutil.copy(source / extra, staged / extra)
        files = sorted(p.name for p in staged.iterdir())
        print("Files:", ", ".join(files))
        if dry_run:
            print("Dry run – nothing uploaded.")
            return revision
        api.create_repo(setup["mirror"], repo_type="model", exist_ok=True)
        commit = api.upload_folder(repo_id=setup["mirror"], folder_path=staged, repo_type="model",
                                   commit_message=f"Mirror of {setup['original']} @ {revision[:7]}")
        print(f"Uploaded to https://huggingface.co/{setup['mirror']} ({commit.oid[:7] if commit.oid else 'done'})")
    print(f"Now set UPSTREAM_REVISIONS[{setup['original']!r}] = {revision!r} in models.py and release.")
    return revision


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("name", choices=sorted(MIRRORS))
    parser.add_argument("--revision", help="revision of the original (default: the one in MIRRORS)")
    parser.add_argument("--dry-run", action="store_true", help="download and prepare, but don't upload")
    args = parser.parse_args()
    mirror(args.name, args.revision, args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
