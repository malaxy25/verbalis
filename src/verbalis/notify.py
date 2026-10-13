"""A Windows notification with a click action, without extra packages.

Uses a notification-area icon with an info balloon (Shell_NotifyIcon); Windows 10/11
show it as a normal notification. A click on the notification or on the icon calls
`on_click` (e.g. bring the Verbalis window to the front). The icon stays in the
notification area until `hide()` – removing it earlier would also remove the
notification from the notification centre. On other systems everything is a no-op.
"""

from __future__ import annotations

import logging
import sys
import threading
from pathlib import Path
from typing import Callable

log = logging.getLogger(__name__)

WM_DESTROY, WM_CLOSE, WM_LBUTTONUP = 0x0002, 0x0010, 0x0202
WM_APP = 0x8000
WM_TRAY, WM_SHOW, WM_HIDE = WM_APP + 1, WM_APP + 2, WM_APP + 3
NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
NIF_MESSAGE, NIF_ICON, NIF_TIP, NIF_INFO = 0x01, 0x02, 0x04, 0x10
NIIF_USER, NIIF_LARGE_ICON = 0x04, 0x20
NIN_BALLOONUSERCLICK = 0x0405


class TrayNotifier:
    def __init__(self, icon: Path, on_click: Callable[[], None], tip: str = "Verbalis"):
        self._icon_path, self._on_click, self._tip = icon, on_click, tip
        self._hwnd = None
        self._message = ("", "")
        self._ready = threading.Event()
        self.available = sys.platform == "win32"
        if self.available:
            threading.Thread(target=self._run, name="notifications", daemon=True).start()
            self._ready.wait(5)

    def show(self, title: str, text: str) -> None:
        if self.available and self._hwnd:
            self._message = (title, text)
            self._user32.PostMessageW(self._hwnd, WM_SHOW, 0, 0)

    def hide(self) -> None:
        if self.available and self._hwnd:
            self._user32.PostMessageW(self._hwnd, WM_HIDE, 0, 0)

    def close(self) -> None:
        if self.available and self._hwnd:
            self._user32.PostMessageW(self._hwnd, WM_CLOSE, 0, 0)

    # ------------------------------------------------------------ Win32, in its own thread

    def _run(self) -> None:
        try:
            self._create()
        except Exception:
            log.exception("Notifications are not available")
            self.available = False
            self._ready.set()
            return
        self._ready.set()
        msg = self._wintypes.MSG()
        while self._user32.GetMessageW(self._ctypes.byref(msg), None, 0, 0) > 0:
            self._user32.TranslateMessage(self._ctypes.byref(msg))
            self._user32.DispatchMessageW(self._ctypes.byref(msg))

    def _create(self) -> None:
        import ctypes
        from ctypes import wintypes

        self._ctypes, self._wintypes = ctypes, wintypes
        user32, shell32, kernel32 = ctypes.windll.user32, ctypes.windll.shell32, ctypes.windll.kernel32
        self._user32, self._shell32 = user32, shell32
        LRESULT = ctypes.c_ssize_t
        WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
        user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user32.DefWindowProcW.restype = LRESULT
        user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user32.CreateWindowExW.restype = wintypes.HWND
        user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                           ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                           wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
        user32.LoadImageW.restype = wintypes.HANDLE
        user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT, ctypes.c_int,
                                      ctypes.c_int, wintypes.UINT]

        class WNDCLASSW(ctypes.Structure):
            _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                        ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                        ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
                        ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR)]

        class GUID(ctypes.Structure):
            _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD),
                        ("Data4", ctypes.c_ubyte * 8)]

        class NOTIFYICONDATAW(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND), ("uID", wintypes.UINT),
                        ("uFlags", wintypes.UINT), ("uCallbackMessage", wintypes.UINT), ("hIcon", wintypes.HICON),
                        ("szTip", wintypes.WCHAR * 128), ("dwState", wintypes.DWORD), ("dwStateMask", wintypes.DWORD),
                        ("szInfo", wintypes.WCHAR * 256), ("uTimeoutOrVersion", wintypes.UINT),
                        ("szInfoTitle", wintypes.WCHAR * 64), ("dwInfoFlags", wintypes.DWORD), ("guidItem", GUID),
                        ("hBalloonIcon", wintypes.HICON)]

        self._NOTIFYICONDATAW = NOTIFYICONDATAW
        shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
        self._added = False
        self._proc = WNDPROC(self._window_proc)          # keep a reference: Windows calls it
        instance = kernel32.GetModuleHandleW(None)
        cls = WNDCLASSW(lpfnWndProc=self._proc, hInstance=instance, lpszClassName="VerbalisNotifications")
        user32.RegisterClassW(ctypes.byref(cls))
        self._hwnd = user32.CreateWindowExW(0, "VerbalisNotifications", "Verbalis", 0, 0, 0, 0, 0,
                                            None, None, instance, None)
        if not self._hwnd:
            raise OSError("CreateWindowExW failed")
        self._hicon = user32.LoadImageW(None, str(self._icon_path), 1, 0, 0, 0x10 | 0x40)  # IMAGE_ICON, from file

    def _data(self, flags: int):
        data = self._NOTIFYICONDATAW()
        data.cbSize = self._ctypes.sizeof(data)
        data.hWnd, data.uID, data.uFlags = self._hwnd, 1, flags
        data.uCallbackMessage, data.hIcon, data.szTip = WM_TRAY, self._hicon, self._tip[:127]
        return data

    def _remove(self) -> None:
        if self._added:
            self._shell32.Shell_NotifyIconW(NIM_DELETE, self._ctypes.byref(self._data(0)))
            self._added = False

    def _window_proc(self, hwnd, message, wparam, lparam):
        try:
            if message == WM_SHOW:
                if not self._added:
                    self._shell32.Shell_NotifyIconW(NIM_ADD, self._ctypes.byref(self._data(NIF_MESSAGE | NIF_ICON | NIF_TIP)))
                    self._added = True
                data = self._data(NIF_MESSAGE | NIF_ICON | NIF_TIP | NIF_INFO)
                data.szInfoTitle, data.szInfo = self._message[0][:63], self._message[1][:255]
                data.dwInfoFlags = NIIF_USER | NIIF_LARGE_ICON
                self._shell32.Shell_NotifyIconW(NIM_MODIFY, self._ctypes.byref(data))
                return 0
            if message == WM_HIDE:
                self._remove()
                return 0
            if message == WM_TRAY and lparam in (NIN_BALLOONUSERCLICK, WM_LBUTTONUP):
                self._remove()
                self._on_click()
                return 0
            if message == WM_CLOSE:
                self._remove()
                self._user32.DestroyWindow(hwnd)
                return 0
            if message == WM_DESTROY:
                self._user32.PostQuitMessage(0)
                return 0
        except Exception:
            log.exception("Notification message %s failed", message)
        return self._user32.DefWindowProcW(hwnd, message, wparam, lparam)
