"""Windows plumbing: finding and focusing windows, launching apps, pasting text and pressing keys."""
import ctypes
import functools
import json
import os
import re
import shutil
import subprocess
import time
import winreg
from ctypes import wintypes
from difflib import SequenceMatcher
from pathlib import Path

import win32clipboard
import win32con
from . import settings as prefs
from pynput.keyboard import Controller, Key
from pynput.mouse import Controller as Mouse

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindow.restype = wintypes.HWND
user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsIconic.argtypes = [wintypes.HWND]
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.BringWindowToTop.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD),
]

EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
GW_OWNER = 4
SW_RESTORE = 9
SW_SHOW = 5
SW_MINIMIZE = 6
SW_MAXIMIZE = 3
PROCESS_QUERY_LIMITED = 0x1000
NO_WINDOW = 0x08000000
BROWSERS = {"chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe"}
ALTGR_STATE = 0x06  # Ctrl and Alt together
ALTGR_TEST_CHARACTERS = "@#[]{}\\|~€"
COPY_WAIT_STEPS = 20
WM_CLOSE = 0x10
DESKTOP_SHELL_TITLE = "Program Manager"  # the desktop itself, owned by explorer.exe but not a folder window

keyboard = Controller()
mouse = Mouse()


def _exe_name(hwnd) -> str:
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED, False, pid.value)
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(1024)
        buffer = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return os.path.basename(buffer.value).lower()
        return ""
    finally:
        kernel32.CloseHandle(handle)


def _title(hwnd) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value


def app_windows() -> list[tuple]:
    """Top-level app windows, including minimized ones, most recently used first."""
    found = []

    def visit(hwnd, _):
        if user32.IsWindowVisible(hwnd) and not user32.GetWindow(hwnd, GW_OWNER):
            title = _title(hwnd)
            if title and title != DESKTOP_SHELL_TITLE:
                found.append((hwnd, _exe_name(hwnd), title))
        return True

    user32.EnumWindows(EnumProc(visit), 0)
    return found


def find_window(exes) -> int | None:
    wanted = {exe.lower() for exe in exes}
    return next((hwnd for hwnd, exe, _ in app_windows() if exe in wanted), None)


def find_browser_tab(word: str) -> int | None:
    pattern = re.compile(rf"\b{re.escape(word)}\b", re.I)
    return next((hwnd for hwnd, exe, title in app_windows() if exe in BROWSERS and pattern.search(title)), None)


def focus(hwnd) -> bool:
    user32.ShowWindow(hwnd, SW_RESTORE if user32.IsIconic(hwnd) else SW_SHOW)
    # Windows only lets the app with the latest input take focus, so make that us for a moment.
    keyboard.tap(Key.f24)
    current = kernel32.GetCurrentThreadId()
    foreground = user32.GetForegroundWindow()
    other = user32.GetWindowThreadProcessId(foreground, None) if foreground else 0
    attached = bool(other and other != current and user32.AttachThreadInput(current, other, True))
    try:
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    finally:
        if attached:
            user32.AttachThreadInput(current, other, False)
    for _ in range(20):
        if user32.GetForegroundWindow() == hwnd:
            return True
        time.sleep(0.02)
    return False


def _chrome_path() -> str | None:
    key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"
    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(root, key_path) as key:
                return winreg.QueryValue(key, None)
        except OSError:
            continue
    return None


def default_browser_is_chrome() -> bool:
    key_path = r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https\UserChoice"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            return winreg.QueryValueEx(key, "ProgId")[0].startswith("ChromeHTML")
    except OSError:
        return False


def open_chrome(profile: str, url: str = "") -> bool:
    """Opens Chrome in one profile, or returns False if Chrome or its profiles cannot be found."""
    path = _chrome_path()
    if not path or not profile:
        return False
    subprocess.Popen([path, f"--profile-directory={profile}", *([url] if url else [])], creationflags=NO_WINDOW)
    return True


def open_in_editor(kind: str, folder: str) -> bool:
    path = prefs.editor_path(kind)
    if not path:
        print(f"   {kind} is not installed")
        return False
    subprocess.Popen([path, folder], creationflags=NO_WINDOW)
    return True


def right_alt_types_symbols() -> bool:
    """On many non-US keyboards Right Alt is AltGr, needed for characters like @ and the euro sign."""
    return any((user32.VkKeyScanW(ord(character)) >> 8) & ALTGR_STATE == ALTGR_STATE for character in ALTGR_TEST_CHARACTERS)


def open_terminal(title: str, command: str, folder: str | None) -> None:
    """A visible terminal running the command, in Windows Terminal when it is available."""
    if shutil.which("wt.exe"):
        subprocess.Popen(terminal_tabs_args(1, title, command, folder))
    else:
        subprocess.Popen(["cmd.exe", "/c", "start", title, "cmd.exe", "/k", command], cwd=folder)


def terminal_tabs_args(count: int, label: str, command: str, folder: str | None) -> list[str]:
    args = ["wt.exe", "-w", "new"]
    for number in range(1, count + 1):
        if number > 1:
            args.append(";")
        args += ["new-tab", "--title", f"{label} {number}", "--suppressApplicationTitle"]
        if folder:
            args += ["-d", folder]
        args += ["cmd", "/k", command]
    return args


def front_exe() -> str:
    hwnd = user32.GetForegroundWindow()
    return _exe_name(hwnd) if hwnd else ""


def front_title() -> str:
    hwnd = user32.GetForegroundWindow()
    return _title(hwnd) if hwnd else ""


def close_window(hwnd) -> None:
    """Asks politely, so the app can still offer to save your work."""
    user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)


def minimize_window(hwnd) -> None:
    user32.ShowWindow(hwnd, SW_MINIMIZE)


def maximize_window(hwnd) -> None:
    focus(hwnd)
    user32.ShowWindow(hwnd, SW_MAXIMIZE)


def resize_front(show_command: int) -> None:
    hwnd = user32.GetForegroundWindow()
    if hwnd:
        user32.ShowWindow(hwnd, show_command)


class StartMenu:
    """Installed apps as Windows lists them. Re-read on a miss so new installs are found."""

    REFRESH_GAP = 20.0

    def __init__(self) -> None:
        self.apps: dict[str, str] = {}
        self.read_at = 0.0
        self.refresh()

    def refresh(self) -> None:
        script = "[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-StartApps | ConvertTo-Json -Compress"
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, encoding="utf-8", creationflags=NO_WINDOW, timeout=30,
        )
        self.read_at = time.monotonic()
        if result.returncode != 0 or not result.stdout.strip():
            return
        rows = json.loads(result.stdout)
        rows = [rows] if isinstance(rows, dict) else rows
        self.apps = {row["Name"].lower(): row["AppID"] for row in rows}

    def exact(self, name: str) -> str | None:
        if name.lower() not in self.apps and time.monotonic() - self.read_at > self.REFRESH_GAP:
            self.refresh()
        return self.apps.get(name.lower())

    def closest(self, name: str) -> tuple[str, str] | None:
        if found := self.exact(name):
            return name, found
        wanted = re.sub(r"\W+", "", name.lower())
        if len(wanted) < 3:
            return None
        usable = [n for n in self.apps if not re.search(r"uninstall|readme|help|documentation", n)]
        squashed = {n: re.sub(r"\W+", "", n) for n in usable}
        same = [n for n, s in squashed.items() if s == wanted]
        starts = [n for n, s in squashed.items() if s.startswith(wanted) and len(wanted) >= 4]
        words = [n for n in usable if wanted in n.split() and len(wanted) >= 4]
        for group in (same, starts, words):
            if group:
                best = min(group, key=len)
                return best, self.apps[best]
        near = [n for n, s in squashed.items() if SequenceMatcher(None, wanted, s).ratio() >= 0.86]
        if near:
            best = max(near, key=lambda n: SequenceMatcher(None, wanted, squashed[n]).ratio())
            return best, self.apps[best]
        return None


def launch(app_id: str) -> None:
    os.startfile(f"shell:AppsFolder\\{app_id}")


_internal_clipboard_uses = 0


def clipboard_in_use() -> bool:
    """True while Jarvis itself is borrowing the clipboard, so that doesn't count as you copying something."""
    return _internal_clipboard_uses > 0


def _borrows_clipboard(function):
    @functools.wraps(function)
    def wrapper(*args, **kwargs):
        global _internal_clipboard_uses
        _internal_clipboard_uses += 1
        try:
            return function(*args, **kwargs)
        finally:
            _internal_clipboard_uses -= 1

    return wrapper


def _open_clipboard() -> bool:
    for _ in range(10):
        try:
            win32clipboard.OpenClipboard()
            return True
        except Exception:
            time.sleep(0.03)
    return False


def _read_clipboard() -> dict:
    saved = {}
    if not _open_clipboard():
        return saved
    try:
        for fmt in (win32con.CF_UNICODETEXT, win32con.CF_DIB):
            if win32clipboard.IsClipboardFormatAvailable(fmt):
                saved[fmt] = win32clipboard.GetClipboardData(fmt)
    finally:
        win32clipboard.CloseClipboard()
    return saved


def _write_clipboard(items: dict) -> bool:
    if not _open_clipboard():
        return False
    try:
        win32clipboard.EmptyClipboard()
        for fmt, value in items.items():
            win32clipboard.SetClipboardData(fmt, value)
        return True
    finally:
        win32clipboard.CloseClipboard()


@_borrows_clipboard
def paste_text(text: str) -> bool:
    """Pastes into the focused box, then puts your clipboard back."""
    saved = _read_clipboard()
    if not _write_clipboard({win32con.CF_UNICODETEXT: text}):
        return False
    press(Key.ctrl, "v")
    time.sleep(0.4)
    if _read_clipboard().get(win32con.CF_UNICODETEXT) == text:
        if saved:
            _write_clipboard(saved)
        elif _open_clipboard():
            try:
                win32clipboard.EmptyClipboard()
            finally:
                win32clipboard.CloseClipboard()
    return True


def read_clipboard_text() -> str:
    return _read_clipboard().get(win32con.CF_UNICODETEXT) or ""


@_borrows_clipboard
def text_copied_by(copy_action) -> str:
    """Runs something that copies text and returns that text, leaving your clipboard as it was."""
    saved = _read_clipboard()
    marker = "⁣jarvis-waiting⁣"
    if not _write_clipboard({win32con.CF_UNICODETEXT: marker}):
        return ""
    try:
        copy_action()
        for _ in range(COPY_WAIT_STEPS):
            time.sleep(0.05)
            text = read_clipboard_text()
            if text and text != marker:
                return text
        return ""
    finally:
        _write_clipboard(saved) if saved else _write_clipboard({})


def edit_focused_text(change) -> bool:
    """Rewrites the text in the focused box. Returns False if the box was empty or nothing changed."""
    text = text_copied_by(lambda: (press(Key.ctrl, "a"), press(Key.ctrl, "c")))
    new_text = change(text) if text else text
    if not text or new_text == text:
        press(Key.right)  # drops the selection
        return False
    if new_text:
        paste_text(new_text)
    else:
        press(Key.backspace)
    return True


def press(*keys) -> None:
    for key in keys[:-1]:
        keyboard.press(key)
    keyboard.tap(keys[-1])
    for key in reversed(keys[:-1]):
        keyboard.release(key)


def press_combo(combo: str) -> None:
    """Presses keys written like "ctrl+shift+r" or "f2"."""
    press(*[getattr(Key, part) if len(part) > 1 else part for part in combo.split("+")])


def set_volume(percent: int) -> None:
    """Windows has no absolute volume key, so go to zero and step up in its 2% increments."""
    for _ in range(50):
        keyboard.tap(Key.media_volume_down)
    for _ in range(percent // 2):
        keyboard.tap(Key.media_volume_up)


KEYS = {
    "send": (Key.enter,),
    "enter": (Key.enter,),
    "new_tab": (Key.ctrl, "t"),
    "close_tab": (Key.ctrl, "w"),
    "next_tab": (Key.ctrl, Key.tab),
    "prev_tab": (Key.ctrl, Key.shift, Key.tab),
    "back": (Key.alt, Key.left),
    "forward": (Key.alt, Key.right),
    "reload": (Key.f5,),
    "top": (Key.ctrl, Key.home),
    "bottom": (Key.ctrl, Key.end),
    "copy": (Key.ctrl, "c"),
    "paste": (Key.ctrl, "v"),
    "cut": (Key.ctrl, "x"),
    "select_all": (Key.ctrl, "a"),
    "undo": (Key.ctrl, "z"),
    "redo": (Key.ctrl, "y"),
    "delete": (Key.backspace,),
    "escape": (Key.esc,),
    "close_window": (Key.alt, Key.f4),
    "desktop": (Key.cmd, "d"),
    "switch_app": (Key.alt, Key.tab),
    "screenshot": (Key.cmd, Key.shift, "s"),
    "play_pause": (Key.media_play_pause,),
    "next_track": (Key.media_next,),
    "prev_track": (Key.media_previous,),
    "mute": (Key.media_volume_mute,),
}


def press_named(name: str) -> None:
    if name == "scroll_down":
        mouse.scroll(0, -6)
    elif name == "scroll_up":
        mouse.scroll(0, 6)
    elif name == "volume_up":
        for _ in range(5):
            keyboard.tap(Key.media_volume_up)
    elif name == "volume_down":
        for _ in range(5):
            keyboard.tap(Key.media_volume_down)
    elif name == "clear_all":
        press(Key.ctrl, "a")
        press(Key.backspace)
    elif name == "minimize":
        resize_front(SW_MINIMIZE)
    elif name == "maximize":
        resize_front(SW_MAXIMIZE)
    else:
        press(*KEYS[name])
