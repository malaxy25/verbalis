"""Entry point of the bundled app (Verbalis.exe, no console window)."""

import multiprocessing

multiprocessing.freeze_support()   # the diarization runs in a second process of the same exe

from verbalis.app import main

main()
