"""Send a layout instruction to an open AviUtl2 plugin on Windows."""

import os
import subprocess
from pathlib import Path


def _send_file(path, kind):
    """Return the plugin result after sending a file to an open AviUtl2."""
    key = {"subtitles": 0x43435331, "layout": 0x43434C31, "media": 0x43434D31, "control": 0x43434531}[kind]
    if os.name != "nt":
        if not Path("/mnt/c/Windows").is_dir():
            return None
        script = Path(__file__).resolve().parents[1] / "editor-plugin" / "apply-layout.ps1"
        try:
            paths = [subprocess.run(["wslpath", "-w", str(item)], capture_output=True,
                                    text=True, check=True).stdout.strip()
                     for item in (script, Path(path).resolve())]
            result = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                                     "-File", *paths, kind],
                                    capture_output=True, text=True, timeout=70)
        except subprocess.TimeoutExpired:
            return 3 if kind == "control" else None
        except (OSError, subprocess.CalledProcessError):
            return None
        return result.returncode
    import ctypes
    from ctypes import wintypes

    class CopyData(ctypes.Structure):
        _fields_ = (("dwData", ctypes.c_size_t), ("cbData", wintypes.DWORD),
                    ("lpData", ctypes.c_void_p))

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.IsWindow.argtypes = (wintypes.HWND,)
    user32.IsWindow.restype = wintypes.BOOL
    user32.FindWindowExW.argtypes = (wintypes.HWND, wintypes.HWND,
                                      wintypes.LPCWSTR, wintypes.LPCWSTR)
    user32.FindWindowExW.restype = wintypes.HWND
    user32.SendMessageTimeoutW.argtypes = (wintypes.HWND, wintypes.UINT,
                                            ctypes.c_size_t, ctypes.c_ssize_t,
                                            wintypes.UINT, wintypes.UINT,
                                            ctypes.POINTER(ctypes.c_size_t))
    user32.SendMessageTimeoutW.restype = wintypes.BOOL
    # HWND_MESSAGE is (HWND)-3. Each AviUtl2 process has its own bridge window.
    parent = ctypes.c_void_p(-3)
    previous = wintypes.HWND()
    payload = ctypes.create_unicode_buffer(str(Path(path).resolve()))
    packet = CopyData(key, ctypes.sizeof(payload), ctypes.cast(payload, ctypes.c_void_p))
    while True:
        window = user32.FindWindowExW(parent, previous, "ClipChannelLayoutBridge", None)
        if not window:
            return 0
        result = ctypes.c_size_t()
        sent = user32.SendMessageTimeoutW(window, 0x004A, 0, ctypes.addressof(packet),
                                          0x0002, 60000, ctypes.byref(result))
        if kind == "control" and not sent:
            return 3 if user32.IsWindow(window) else 0
        if sent and result.value in (1, 2):
            return result.value
        previous = window


def apply_layout(path):
    """Return 'preview', 'applied', or None after applying a layout."""
    return {1: "preview", 2: "applied"}.get(_send_file(path, "layout") or 0)


def apply_subtitles(path):
    """Return whether a subtitle version was added to an open AviUtl2."""
    return _send_file(path, "subtitles") == 1


def apply_supporting_media(path):
    """Return 'preview', 'applied', or None for a supporting-media adjustment."""
    return {1: "preview", 2: "applied"}.get(_send_file(path, "media") or 0)


def send_control(path):
    """Submit control once; 3 means delivery completion could not be confirmed."""
    return _send_file(path, "control")
