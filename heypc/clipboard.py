"""Remembers recent text you copied. Kept in memory only and never written to disk."""
import threading
import time
from collections import deque

import win32clipboard

from . import winctl

MAX_ITEMS = 30
MAX_TEXT = 20000
CHECK_SECONDS = 0.5
SETTLE_SECONDS = 0.05
# Password managers set these to ask clipboard tools not to keep what they copy.
PRIVATE_FORMATS = ("ExcludeClipboardContentFromMonitorProcessing", "CanIncludeInClipboardHistory")


class ClipboardHistory:
    def __init__(self) -> None:
        self.items: deque = deque(maxlen=MAX_ITEMS)
        self.private = [win32clipboard.RegisterClipboardFormat(name) for name in PRIVATE_FORMATS]
        self.seen = winctl.user32.GetClipboardSequenceNumber()

    def start(self) -> None:
        threading.Thread(target=self._watch, daemon=True).start()

    def remember(self, text: str) -> None:
        text = text.strip("\u0000")
        if not text.strip() or len(text) > MAX_TEXT:
            return
        if text in self.items:
            self.items.remove(text)
        self.items.appendleft(text)

    def check(self) -> None:
        current = winctl.user32.GetClipboardSequenceNumber()
        if current == self.seen:
            return
        self.seen = current
        if winctl.clipboard_in_use() or any(win32clipboard.IsClipboardFormatAvailable(fmt) for fmt in self.private):
            return
        time.sleep(SETTLE_SECONDS)
        self.remember(winctl.read_clipboard_text())

    def _watch(self) -> None:
        while True:
            try:
                self.check()
            except Exception as error:
                print(f"   clipboard check failed: {error!r}")
            time.sleep(CHECK_SECONDS)

    def nth(self, number: int) -> str | None:
        """1 is the most recent copy."""
        return self.items[number - 1] if 0 < number <= len(self.items) else None

    def containing(self, words: str) -> str | None:
        wanted = words.lower().split()
        return next((item for item in self.items if all(word in item.lower() for word in wanted)), None)
