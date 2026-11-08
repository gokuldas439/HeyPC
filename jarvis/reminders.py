"""Reminders and timers. They are saved to disk, so they survive a restart and fire late rather than never."""
import json
import re
import threading
import time
from datetime import datetime, timedelta

from .commands import CLOCK_AT, CLOCK_MERIDIEM, CLOCK_NAMED, DAY_WORDS, WEEKDAY, parse_when
from .settings import DATA

FILE = DATA / "reminders.json"
CHECK_SECONDS = 1.0
WORD_NUMBERS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40, "forty five": 45,
    "fifty": 50, "sixty": 60,
}
_NUMBER = "|".join(sorted(map(re.escape, WORD_NUMBERS), key=len, reverse=True))
_AMOUNT = rf"\d+(?:\.\d+)?|half an|half a|{_NUMBER}"
_UNIT = r"hours?|hrs?|minutes?|mins?|seconds?|secs?"
PIECE = re.compile(rf"\b(?P<n>{_AMOUNT})\s*(?:-\s*)?(?P<u>{_UNIT})\b(?P<half>\s+and\s+a\s+half)?", re.I)
RELATIVE = re.compile(rf"\b(?:in|after)\s+(?:(?:{_AMOUNT})\s*(?:-\s*)?(?:{_UNIT})(?:\s+and\s+a\s+half)?(?:\s*,?\s*(?:and\s+)?)?)+", re.I)
TASK_LEAD = re.compile(r"^(?:to|that|about|for|of)\s+", re.I)


def _unit_seconds(unit: str) -> int:
    first = unit[0].lower()
    return 3600 if first == "h" else 60 if first == "m" else 1


def parse_duration(text: str) -> int | None:
    """Seconds in "1 hour 30 minutes", "half an hour", "an hour and a half". None if no length is given."""
    total = 0.0
    found = False
    for piece in PIECE.finditer(text):
        found = True
        word = piece["n"].lower()
        amount = 0.5 if word.startswith("half") else float(word) if word[0].isdigit() else WORD_NUMBERS[word]
        seconds = _unit_seconds(piece["u"])
        total += (amount + (0.5 if piece["half"] else 0)) * seconds
    return round(total) if found and total > 0 else None


def _has_clock_or_day(text: str) -> bool:
    return any(pattern.search(text) for pattern in (CLOCK_NAMED, CLOCK_MERIDIEM, CLOCK_AT, DAY_WORDS, WEEKDAY))


def _clean_task(text: str) -> str:
    task = TASK_LEAD.sub("", re.sub(r"\s+", " ", text).strip(" ,.!?-"))
    return task[:1].upper() + task[1:]


def parse_request(raw: str, now: datetime) -> tuple[str, datetime | None]:
    """Splits what follows "remind me" into the task and its due time. The time is None if you didn't give one."""
    if relative := RELATIVE.search(raw):
        seconds = parse_duration(relative[0])
        rest = raw[: relative.start()] + " " + raw[relative.end() :]
        return _clean_task(rest), now + timedelta(seconds=seconds)
    if _has_clock_or_day(raw):
        title, start, _minutes = parse_when(raw, now)
        return _clean_task(title), start
    return _clean_task(raw), None


def describe_duration(seconds: int) -> str:
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    parts = [(hours, "hour"), (minutes, "minute"), (secs, "second")]
    return " ".join(f"{value} {unit}{'s' if value != 1 else ''}" for value, unit in parts if value) or "0 seconds"


def describe_time(due: datetime, now: datetime) -> str:
    clock = due.strftime("%I:%M %p").lstrip("0")
    days = (due.date() - now.date()).days
    if days == 0:
        return f"at {clock}"
    if days == 1:
        return f"tomorrow at {clock}"
    return f"on {due.strftime('%A')} at {clock}"


class Reminders:
    def __init__(self, on_due, path=FILE) -> None:
        self.on_due = on_due
        self.path = path
        self.lock = threading.Lock()
        self.items = self._read()

    def _read(self) -> list[dict]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        partial = self.path.with_suffix(".tmp")
        partial.write_text(json.dumps(self.items, indent=2), encoding="utf-8")
        partial.replace(self.path)

    def start(self) -> None:
        threading.Thread(target=self._watch, daemon=True).start()

    def add(self, kind: str, text: str, due: datetime) -> None:
        with self.lock:
            self.items.append({"kind": kind, "text": text, "due": due.isoformat()})
            self._write()

    def cancel(self, kind: str) -> int:
        with self.lock:
            kept = [item for item in self.items if item["kind"] != kind]
            removed = len(self.items) - len(kept)
            self.items = kept
            self._write()
        return removed

    def upcoming(self) -> list[dict]:
        with self.lock:
            return sorted(self.items, key=lambda item: item["due"])

    def fire_due(self, now: datetime) -> None:
        with self.lock:
            due = [item for item in self.items if datetime.fromisoformat(item["due"]) <= now]
            if not due:
                return
            self.items = [item for item in self.items if item not in due]
            self._write()
        for item in sorted(due, key=lambda entry: entry["due"]):
            self.on_due(item["kind"], item["text"])

    def _watch(self) -> None:
        while True:
            try:
                self.fire_due(datetime.now())
            except Exception as error:
                print(f"   reminder check failed: {error!r}")
            time.sleep(CHECK_SECONDS)
