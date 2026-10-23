"""Processor, memory and graphics card for the diagnosis – transcription speed depends on them.

Standard library only (no psutil). Every value falls back to «unbekannt»; nothing here may break the
diagnosis. On Apple Silicon the graphics are part of the chip, so its name is shown there.
"""

from __future__ import annotations

import os
import platform
import subprocess
import sys
from typing import Callable

UNKNOWN = "unbekannt"


def describe(system: str | None = None, run: Callable = subprocess.run) -> dict[str, str]:
    """{"Prozessor", "Arbeitsspeicher", "Grafikkarte"} as German display text."""
    system = system or sys.platform
    if system == "win32":
        cpu, ram, gpu = _safe(_windows_cpu), _safe(_windows_ram), _safe(lambda: _windows_gpu(run))
    elif system == "darwin":
        cpu = _safe(lambda: _sysctl(run, "machdep.cpu.brand_string"))
        ram = _safe(lambda: int(_sysctl(run, "hw.memsize")))
        gpu = f"im Chip ({cpu})" if cpu and cpu.startswith("Apple") else None
    else:
        cpu, ram, gpu = _safe(_linux_cpu), _safe(_linux_ram), _safe(lambda: _linux_gpu(run))
    cores = os.cpu_count()
    return {
        "Prozessor": (cpu or platform.processor() or UNKNOWN) + (f", {cores} Threads" if cores else ""),
        "Arbeitsspeicher": f"{ram / 1024 ** 3:.0f} GB" if ram else UNKNOWN,
        "Grafikkarte": gpu or UNKNOWN,
    }


def _safe(read: Callable):
    try:
        value = read()
    except Exception:
        return None
    return value.strip() if isinstance(value, str) else value


def _windows_cpu() -> str:
    import winreg

    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
        return " ".join(str(winreg.QueryValueEx(key, "ProcessorNameString")[0]).split())


def _windows_ram() -> int:
    import ctypes

    class MemoryStatus(ctypes.Structure):
        _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong), ("total", ctypes.c_ulonglong),
                    ("available", ctypes.c_ulonglong), ("total_page", ctypes.c_ulonglong),
                    ("available_page", ctypes.c_ulonglong), ("total_virtual", ctypes.c_ulonglong),
                    ("available_virtual", ctypes.c_ulonglong), ("available_extended", ctypes.c_ulonglong)]

    status = MemoryStatus()
    status.length = ctypes.sizeof(MemoryStatus)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        raise OSError("GlobalMemoryStatusEx failed")
    return status.total


def _windows_gpu(run: Callable) -> str:
    result = run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                  "(Get-CimInstance Win32_VideoController).Name"],
                 capture_output=True, text=True, timeout=10,
                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    names = [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]
    return ", ".join(names)


def _sysctl(run: Callable, name: str) -> str:
    return run(["sysctl", "-n", name], capture_output=True, text=True, timeout=5).stdout


def _linux_cpu() -> str:
    with open("/proc/cpuinfo", encoding="utf-8") as f:
        for line in f:
            if line.startswith("model name"):
                return line.split(":", 1)[1]
    return ""


def _linux_gpu(run: Callable) -> str:
    """The graphics controllers from `lspci` (package pciutils), e.g. «NVIDIA Corporation TU117GLM [T500]»."""
    result = run(["lspci"], capture_output=True, text=True, timeout=5)
    names = []
    for line in (result.stdout or "").splitlines():
        kind, _, name = line.partition(": ")
        if name and any(k in kind for k in ("VGA compatible controller", "3D controller", "Display controller")):
            names.append(name.split(" (rev ")[0].strip())
    return ", ".join(names)


def _linux_ram() -> int:
    with open("/proc/meminfo", encoding="utf-8") as f:
        for line in f:
            if line.startswith("MemTotal:"):
                return int(line.split()[1]) * 1024
    return 0
