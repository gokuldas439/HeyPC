"""Terminal commands by voice. Only commands listed in your file can run; spoken words never become commands."""
import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from .settings import DATA

FILE = DATA / "terminal.txt"
FUZZY_MATCH = 0.86
MAX_SPOKEN_WORDS = 20
TEMPLATE = """# Say a command and a project, such as "git status in backend". Only what is listed here can run.
# Under [commands], write:  spoken name | another name = the command
#   Add [project] after the names to limit a line to one project.
#   Start the command with  terminal:  to open it in a visible terminal tab, for things that keep running.
#   Start the command with  ask:  to make HeyPC ask for a spoken yes first.

[projects]

[commands]
git status | status = git status --short --branch
git pull | pull latest | pull = git pull
current branch | branch = git branch --show-current
git push | push = ask: git push
start | run | serve = terminal: npm start
tests | run tests | test = terminal: npm test
install | npm install | install packages = terminal: npm install
"""
FILLER = re.compile(r"\b(?:the|my|please|a|in|on|for|of|at|jarvis)\b")


@dataclass(frozen=True)
class Command:
    names: tuple
    project: str | None
    line: str
    in_terminal: bool
    ask: bool


@dataclass
class Setup:
    projects: dict
    commands: list


def read_text() -> str:
    try:
        return FILE.read_text(encoding="utf-8")
    except OSError:
        return TEMPLATE


def write_text(text: str) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    FILE.write_text(text, encoding="utf-8")


def _command(left: str, right: str) -> Command:
    restricted = re.search(r"\[([^\]]+)\]\s*$", left)
    names = left[: restricted.start()] if restricted else left
    ask = in_terminal = False
    line = right.strip()
    while prefix := re.match(r"(terminal|ask):\s*", line, re.I):
        in_terminal = in_terminal or prefix[1].lower() == "terminal"
        ask = ask or prefix[1].lower() == "ask"
        line = line[prefix.end() :]
    return Command(tuple(n.strip().lower() for n in names.split("|") if n.strip()), restricted[1].strip().lower() if restricted else None, line, in_terminal, ask)


def parse_text(text: str) -> Setup:
    setup = Setup({}, [])
    section = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]") and "=" not in line:
            section = line[1:-1].strip().lower()
            continue
        left, separator, right = line.partition("=")
        if not separator or not right.strip():
            print(f"   ignoring terminal line: {line!r}")
        elif section == "projects":
            setup.projects[left.strip().lower()] = right.strip()
        elif section == "commands":
            setup.commands.append(_command(left, right))
    return setup


def load() -> Setup:
    return parse_text(read_text())


def _normal(phrase: str) -> str:
    plain = re.sub(r"[^\w\s]", "", phrase).lower()
    return " ".join(FILLER.sub(" ", plain).split())


def _phrases(setup: Setup):
    for command in setup.commands:
        for name in command.names:
            for project in setup.projects:
                if command.project in (None, project):
                    yield _normal(f"{name} {project}"), command, project
                    yield _normal(f"{project} {name}"), command, project


def match(heard: str, setup: Setup | None = None) -> tuple[Command, str] | None:
    """The listed command and project you asked for, tolerating small mishearings like "get status"."""
    setup = load() if setup is None else setup
    wanted = _normal(heard)
    if not wanted:
        return None
    best, best_score = None, 0.0
    for phrase, command, project in _phrases(setup):
        if phrase == wanted:
            return command, project
        score = SequenceMatcher(None, wanted, phrase).ratio()
        if score > best_score:
            best, best_score = (command, project), score
    return best if best_score >= FUZZY_MATCH else None


def find(name: str, project: str, setup: Setup | None = None) -> Command | None:
    setup = load() if setup is None else setup
    return next((c for c in setup.commands if name in c.names and c.project in (None, project)), None)


def _shorten(line: str) -> str:
    words = line.split()
    return " ".join(words[:MAX_SPOKEN_WORDS]) + ("..." if len(words) > MAX_SPOKEN_WORDS else "")


def spoken_result(line: str, return_code: int, output: str) -> str:
    """Terminal output boiled down to something worth saying aloud."""
    lines = [text.strip() for text in output.splitlines() if text.strip()]
    if return_code:
        return "That failed. " + (_shorten(lines[-1]) if lines else "")
    if "--short" in line and "--branch" in line and lines and lines[0].startswith("##"):
        branch = re.match(r"##\s+([^.\s]+)", lines[0])
        behind = re.search(r"\[(.+)\]", lines[0])
        changed = len(lines) - 1
        parts = [f"On {branch[1] if branch else 'this branch'}."]
        if behind:
            parts.append(f"{behind[1].capitalize()}.")
        parts.append(f"{changed} file{'s' if changed != 1 else ''} changed." if changed else "Nothing to commit.")
        return " ".join(parts)
    return _shorten(lines[-1]) if lines else "Done."
