"""Entry point of the bundled command line (verbalis-cli.exe)."""

import multiprocessing

multiprocessing.freeze_support()   # the diarization runs in a second process of the same exe

import sys

from verbalis.cli import main

sys.exit(main())
