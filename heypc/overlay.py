"""The small animated pill above the taskbar. It never takes focus and clicks pass straight through it.

There is no text: listening is bars that follow your voice, working is a spinning arc, speaking is a flowing wave.
"""
import ctypes
import math
import threading
import time
from ctypes import wintypes

import numpy as np
import win32api
import win32con
import win32gui
from PIL import Image, ImageDraw

WIDTH, HEIGHT = 58, 26
GAP_ABOVE_TASKBAR = 10
FRAME_SECONDS = 1 / 30
IDLE_SECONDS = 0.04
FADE_STEP = 45
COLOURS = {"listening": (79, 209, 255), "working": (255, 200, 87), "speaking": (150, 240, 200)}
LISTENING_BARS = 5
SPEAKING_BARS = 7
AC_SRC_OVER, AC_SRC_ALPHA, ULW_ALPHA = 0, 1, 2
MDT_EFFECTIVE_DPI = 0
EX_STYLE = (
    win32con.WS_EX_LAYERED | win32con.WS_EX_TOPMOST | win32con.WS_EX_TOOLWINDOW
    | win32con.WS_EX_NOACTIVATE | win32con.WS_EX_TRANSPARENT
)

gdi32 = ctypes.WinDLL("gdi32")
gdi32.CreateDIBSection.restype = wintypes.HBITMAP
gdi32.CreateDIBSection.argtypes = [
    wintypes.HDC, ctypes.c_void_p, wintypes.UINT, ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD,
]
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]


class _BitmapHeader(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD), ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class Painter:
    """Draws frames at one screen scale. Shapes are drawn oversized, then reduced for smooth edges."""

    OVERSAMPLE = 3

    def __init__(self, scale: float) -> None:
        self.size = (round(WIDTH * scale), round(HEIGHT * scale))
        self.unit = scale * self.OVERSAMPLE
        self.pill = self._pill()

    def _pill(self) -> Image.Image:
        factor = 4
        big = (self.size[0] * factor, self.size[1] * factor)
        image = Image.new("RGBA", big, (0, 0, 0, 0))
        ImageDraw.Draw(image).rounded_rectangle((0, 0, big[0] - 1, big[1] - 1), radius=big[1] // 2, fill=(11, 18, 32, 235))
        return image.resize(self.size, Image.LANCZOS)

    def frame(self, state: str, level: float, now: float) -> Image.Image:
        layer = Image.new("RGBA", (self.size[0] * self.OVERSAMPLE, self.size[1] * self.OVERSAMPLE), (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer)
        {"listening": self._listening, "working": self._working, "speaking": self._speaking}[state](draw, layer, level, now)
        return Image.alpha_composite(self.pill, layer.resize(self.size, Image.BILINEAR))

    def _bar(self, draw, layer, x: float, height: float, width: float, colour) -> None:
        """height is 0 to 1 of the pill's inner height, centred vertically."""
        u = self.unit
        middle = layer.height / 2
        half = max(width / 2 * u, height * 8.5 * u)
        draw.rounded_rectangle(
            (x - width / 2 * u, middle - half, x + width / 2 * u, middle + half),
            radius=round(width / 2 * u), fill=(*colour, 255),
        )

    def _listening(self, draw, layer, level: float, now: float) -> None:
        """Dots that breathe in silence and jump up as you talk, like a recorder's level meter."""
        voice = min(1.0, level * 2.4)
        for index in range(LISTENING_BARS):
            ripple = 0.5 + 0.5 * math.sin(now * 11 + index * 1.7)
            height = 0.14 + 0.05 * math.sin(now * 3 + index) + voice * (0.35 + 0.5 * ripple)
            x = layer.width / 2 + (index - (LISTENING_BARS - 1) / 2) * 7 * self.unit
            self._bar(draw, layer, x, height, 3.4, COLOURS["listening"])

    def _working(self, draw, layer, _level: float, now: float) -> None:
        """A spinning arc: Jarvis is busy."""
        u = self.unit
        x, y, radius = layer.width / 2, layer.height / 2, 7.5 * u
        start = (now * 400) % 360
        sweep = 200 + 70 * math.sin(now * 3)
        draw.arc((x - radius, y - radius, x + radius, y + radius), start, start + sweep, fill=(*COLOURS["working"], 255), width=round(2.4 * u))

    def _speaking(self, draw, layer, _level: float, now: float) -> None:
        """A wave that flows out from the centre: Jarvis is talking."""
        centre = (SPEAKING_BARS - 1) / 2
        for index in range(SPEAKING_BARS):
            distance = abs(index - centre)
            envelope = 1.0 - distance / (centre + 1.2)
            height = 0.12 + envelope * (0.3 + 0.5 * (0.5 + 0.5 * math.sin(now * 9 - distance * 1.3)))
            x = layer.width / 2 + (index - centre) * 5.4 * self.unit
            self._bar(draw, layer, x, height, 2.6, COLOURS["speaking"])


def _premultiplied_bgra(image: Image.Image) -> bytes:
    pixels = np.asarray(image, dtype=np.uint16)
    alpha = pixels[..., 3:4]
    out = np.concatenate([pixels[..., 2::-1] * alpha // 255, alpha], axis=2)
    return out.astype(np.uint8).tobytes()


def _monitor_area() -> tuple[tuple[int, int, int, int], float]:
    """The usable area (which excludes the taskbar) of the screen you're working on, and its scale."""
    monitor = win32api.MonitorFromWindow(win32gui.GetForegroundWindow(), win32con.MONITOR_DEFAULTTOPRIMARY)
    dpi_x, dpi_y = wintypes.UINT(), wintypes.UINT()
    ctypes.windll.shcore.GetDpiForMonitor(int(monitor), MDT_EFFECTIVE_DPI, ctypes.byref(dpi_x), ctypes.byref(dpi_y))
    return win32api.GetMonitorInfo(monitor)["Work"], dpi_x.value / 96


class Overlay:
    def __init__(self, status) -> None:
        self.status = status  # returns (state or None, voice level)
        self.painters: dict[float, Painter] = {}
        self.hwnd = 0
        self.memory_dc = None
        self.bits = ctypes.c_void_p()
        self.bitmap_size = (0, 0)
        self.bitmap = None

    def start(self) -> None:
        threading.Thread(target=self._safe_run, daemon=True).start()

    def _safe_run(self) -> None:
        try:
            self._run()
        except Exception as error:
            print(f"   the on-screen indicator stopped: {error!r}")  # the rest of HeyPC carries on

    def _create_window(self) -> None:
        window_class = win32gui.WNDCLASS()
        window_class.lpszClassName = "JarvisOverlay"
        window_class.lpfnWndProc = lambda hwnd, message, w, l: win32gui.DefWindowProc(hwnd, message, w, l)
        window_class.hInstance = win32api.GetModuleHandle(None)
        atom = win32gui.RegisterClass(window_class)
        self.hwnd = win32gui.CreateWindowEx(EX_STYLE, atom, "", win32con.WS_POPUP, 0, 0, 1, 1, 0, 0, window_class.hInstance, None)
        self.memory_dc = gdi32.CreateCompatibleDC(None)

    def _bitmap_for(self, size: tuple[int, int]) -> None:
        if size == self.bitmap_size:
            return
        header = _BitmapHeader(ctypes.sizeof(_BitmapHeader), size[0], -size[1], 1, 32, 0, 0, 0, 0, 0, 0)
        new = gdi32.CreateDIBSection(self.memory_dc, ctypes.byref(header), 0, ctypes.byref(self.bits), None, 0)
        gdi32.SelectObject(self.memory_dc, new)
        if self.bitmap:
            gdi32.DeleteObject(self.bitmap)
        self.bitmap, self.bitmap_size = new, size

    def _run(self) -> None:
        self._create_window()
        opacity = 0
        shown_state = "listening"
        position = (0, 0)
        painter = None
        while True:
            win32gui.PumpWaitingMessages()
            state, level = self.status()
            if opacity == 0 and not state:
                time.sleep(IDLE_SECONDS)
                continue
            if opacity == 0:
                (left, _top, right, bottom), scale = _monitor_area()
                painter = self.painters.setdefault(scale, Painter(scale))
                position = ((left + right - painter.size[0]) // 2, bottom - painter.size[1] - round(GAP_ABOVE_TASKBAR * scale))
                self._bitmap_for(painter.size)
                win32gui.ShowWindow(self.hwnd, win32con.SW_SHOWNOACTIVATE)
            shown_state = state or shown_state
            opacity = min(255, opacity + FADE_STEP) if state else max(0, opacity - FADE_STEP)
            image = _premultiplied_bgra(painter.frame(shown_state, level, time.monotonic()))
            ctypes.memmove(self.bits, image, len(image))
            screen_dc = win32gui.GetDC(0)
            win32gui.UpdateLayeredWindow(
                self.hwnd, screen_dc, position, painter.size, self.memory_dc, (0, 0), 0,
                (AC_SRC_OVER, 0, opacity, AC_SRC_ALPHA), ULW_ALPHA,
            )
            win32gui.ReleaseDC(0, screen_dc)
            if opacity == 0:
                win32gui.ShowWindow(self.hwnd, win32con.SW_HIDE)
            time.sleep(FRAME_SECONDS)
