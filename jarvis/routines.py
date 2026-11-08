"""Named routines such as "start work", kept in a plain text file you can edit from Settings."""
import re

from .settings import DATA

FILE = DATA / "routines.txt"
TEMPLATE = """# Say a name in [brackets] and Jarvis does each step below it. Lines starting with # are ignored.
# Steps:
#   cursor C:\\path\\to\\project       opens a folder in Cursor
#   vscode C:\\path\\to\\project       opens a folder in VS Code
#   chrome Profile name              opens Chrome in that profile (add a web address after it for a page)
#   open Spotify                     opens any app or site Jarvis knows
#   url https://example.com          opens a web page
#   wait 2                           pauses for that many seconds

"""
STEP_KINDS = {"cursor", "vscode", "chrome", "open", "url", "wait"}
SPOKEN_FILLER = re.compile(r"\b(?:lets|let us|please|okay|ok|hey|jarvis|can you|could you|time to|my|the|our)\b")


def read_text() -> str:
    try:
        return FILE.read_text(encoding="utf-8")
    except OSError:
        return TEMPLATE


def write_text(text: str) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    FILE.write_text(text, encoding="utf-8")


def parse_text(text: str) -> dict[str, list[tuple[str, str]]]:
    routines: dict[str, list[tuple[str, str]]] = {}
    current = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1].strip()
            routines[current] = []
        elif current is not None:
            kind, _, value = line.partition(" ")
            if kind.lower() in STEP_KINDS and value.strip():
                routines[current].append((kind.lower(), value.strip()))
            else:
                print(f"   ignoring routine step: {line!r}")
    return routines


def load() -> dict[str, list[tuple[str, str]]]:
    return parse_text(read_text())


def _normal(phrase: str) -> str:
    plain = re.sub(r"[^\w\s]", "", phrase).lower()
    return " ".join(SPOKEN_FILLER.sub(" ", plain).split())


def match(heard: str, routines: dict | None = None) -> str | None:
    """The routine you asked for, or None."""
    wanted = _normal(heard)
    if not wanted:
        return None
    for name in load() if routines is None else routines:
        if _normal(name) == wanted:
            return name
    return None
