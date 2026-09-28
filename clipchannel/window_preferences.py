"""Window preferences are separate from media data and corrected on every load."""

import ctypes
import json
import os
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from .responsive_ui import WORKS


@dataclass(frozen=True)
class DisplayArea:
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True)
class UiState:
    width: int
    height: int
    x: int = 0
    y: int = 0
    maximized: bool = False
    work: str = '動画を準備'
    tab: str = '取得・媒体操作'


class WindowPreferences:
    def __init__(self, path=None):
        base = Path(os.environ.get('LOCALAPPDATA', Path.home() / '.config'))
        self.path = Path(path) if path is not None else base / 'ClipChannelAPP' / 'ui.json'

    def load(self, display):
        initial = UiState(round(display.width * .85), round(display.height * .85),
                          display.x + round(display.width * .075),
                          display.y + round(display.height * .075))
        try:
            raw = json.loads(self.path.read_text(encoding='utf-8'))
            state = UiState(**raw)
            if any(type(value) is not int for value in (state.width, state.height, state.x, state.y)):
                raise ValueError('Invalid geometry')
            if type(state.maximized) is not bool or state.work not in WORKS:
                raise ValueError('Invalid navigation')
            if state.tab not in WORKS[state.work]:
                state = replace(state, tab=WORKS[state.work][0])
        except (OSError, ValueError, TypeError):
            state = initial
        width = min(display.width, max(round(display.width * .7), state.width))
        height = min(display.height, max(round(display.height * .7), state.height))
        return replace(state, width=width, height=height,
            x=max(display.x, min(state.x, display.x + display.width - width)),
            y=max(display.y, min(state.y, display.y + display.height - height)))

    def save(self, state):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        staged = self.path.with_suffix('.tmp')
        staged.write_text(json.dumps(asdict(state), ensure_ascii=False), encoding='utf-8')
        staged.replace(self.path)


def work_area(window):
    """Windows monitor work area, in the same coordinates as the Tk window."""
    if os.name == 'nt':
        from ctypes import wintypes
        class MonitorInfo(ctypes.Structure):
            _fields_ = [('size', wintypes.DWORD), ('monitor', wintypes.RECT),
                        ('work', wintypes.RECT), ('flags', wintypes.DWORD)]
        api = ctypes.windll.user32
        api.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
        api.MonitorFromWindow.restype = wintypes.HANDLE
        api.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MonitorInfo)]
        api.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
        api.GetAncestor.restype = wintypes.HWND
        handle = api.GetAncestor(window.winfo_id(), 2) or window.winfo_id()
        info = MonitorInfo()
        info.size = ctypes.sizeof(info)
        monitor = api.MonitorFromWindow(handle, 2)
        if api.GetMonitorInfoW(monitor, ctypes.byref(info)):
            rect = info.work
            dpi = 96
            if hasattr(api, 'GetDpiForWindow'):
                api.GetDpiForWindow.argtypes = [wintypes.HWND]
                api.GetDpiForWindow.restype = wintypes.UINT
                dpi = api.GetDpiForWindow(handle) or 96
            if hasattr(api, 'GetSystemMetricsForDpi'):
                api.GetSystemMetricsForDpi.argtypes = [ctypes.c_int, wintypes.UINT]
                metric = lambda index: api.GetSystemMetricsForDpi(index, dpi)
            else:
                metric = api.GetSystemMetrics
            # Tk geometry specifies client size and the outer frame's position.
            border_x = metric(32) + metric(92)
            border_y = metric(33) + metric(92)
            return DisplayArea(rect.left, rect.top,
                max(1, rect.right - rect.left - 2 * border_x),
                max(1, rect.bottom - rect.top - 2 * border_y - metric(4)))
    return DisplayArea(0, 32, window.winfo_screenwidth(), max(1, window.winfo_screenheight() - 64))


class WindowPlacement:
    def __init__(self, window, preferences, display=None):
        self.window = window
        self.preferences = preferences
        self.display = display or work_area(window)
        self.normal = preferences.load(self.display)
        self.window.minsize(round(self.display.width * .7), round(self.display.height * .7))
        self._apply_normal()
        if self.normal.maximized:
            self.set_size('大')
        window.bind('<Configure>', self._remember, add='+')

    def maximized(self):
        return self.window.state() == 'zoomed' if os.name == 'nt' else bool(self.window.attributes('-zoomed'))

    def _zoom(self, value):
        if os.name == 'nt':
            self.window.state('zoomed' if value else 'normal')
        else:
            self.window.attributes('-zoomed', value)

    def _apply_normal(self):
        state = self.normal
        self.window.geometry(f'{state.width}x{state.height}{state.x:+d}{state.y:+d}')

    def _remember(self, event):
        if event.widget is self.window and not self.maximized() and self.window.state() == 'normal':
            self.normal = replace(self.normal, width=event.width, height=event.height,
                                  x=self.window.winfo_x(), y=self.window.winfo_y())

    def set_size(self, name):
        if name == '大':
            self._zoom(True)
            return
        self._zoom(False)
        fraction = {'小': .7, '中': .85}[name]
        area = self.display
        self.normal = replace(self.normal, width=round(area.width * fraction),
            height=round(area.height * fraction), x=area.x + round(area.width * (1 - fraction) / 2),
            y=area.y + round(area.height * (1 - fraction) / 2))
        self._apply_normal()

    def save(self, work, tab):
        self.preferences.save(replace(self.normal, maximized=self.maximized(), work=work, tab=tab))
