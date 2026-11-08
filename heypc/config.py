"""Settings you may want to change: timing, speech model choice, apps, sites and vocabulary."""
import ctypes
import os
import sys
from dataclasses import dataclass
from pathlib import Path

# The installed app keeps its models next to HeyPC.exe.
ROOT = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
MODELS = ROOT / "models"  # small models that ship with the app
if getattr(sys, "frozen", False) and not (MODELS / "encoder.int8.onnx").exists():
    DOWNLOADED_MODELS = Path(os.environ["LOCALAPPDATA"]) / "HeyPC" / "models"  # fetched once on first run
else:
    DOWNLOADED_MODELS = MODELS  # building from source, or an older install that already has them

SAMPLE_RATE = 16000
FRAME_SAMPLES = 1280  # 80 ms, the size the wake word model expects

# "auto" picks from the PC's RAM and cores. Force with "parakeet" (accurate) or "tiny" (low spec).
SPEECH_MODEL = "auto"
FULL_MODEL_MIN_RAM_GB = 7.5
FULL_MODEL_MIN_CORES = 4

WAKE_THRESHOLD = 0.5
WAKE_FRAMES_IN_A_ROW = 3  # about a quarter of a second above the threshold
MIC_MAX_GAIN = 16.0  # how much a quiet voice may be boosted

START_TIMEOUT = 5.0  # seconds to start speaking after "Hey Jarvis"
COMMAND_SILENCE = 0.7  # pause that ends a command
DICTATION_SILENCE = 1.8  # pause that ends dictation
MAX_COMMAND_SECONDS = 15
MAX_DICTATION_SECONDS = 180
GREET_AFTER = 1.4  # a pause this long after the wake word means you want a greeting first
TYPE_HOLD_SECONDS = 0.3  # Right Ctrl held this long starts voice typing
TYPE_RELEASE_TAIL = 0.25  # keep recording this long after release, so the last word isn't cut
MIN_TYPING_SECONDS = 0.4
SECONDS_PER_SPOKEN_WORD = 0.45
SEND_AFTER_TYPING_SECONDS = 60  # "send it" works without the wake word for this long after text is typed
GREETING_GAP_HOURS = 4  # "good morning" again only after this long; otherwise a short "yes, sir?"
WAKE_POLL = 5.0
WAKE_PHRASE_MAX_SECONDS = 10
CONFIRM_SECONDS = 12.0  # time to say "yes" before a message or risky click is cancelled
HOLD_THRESHOLD = 0.35  # Right Alt held longer than this is push-to-talk; shorter is a tap


@dataclass(frozen=True)
class App:
    exes: tuple = ()  # process names used to find an open window
    start_name: str = ""  # name in the Start menu
    url: str = ""  # browser fallback when the app is not installed
    title_word: str = ""  # finds an already open browser tab


APPS = {
    "claude": App(("claude.exe",), "Claude", "https://claude.ai", "Claude"),
    "codex": App(("codex.exe",), "Codex", "https://chatgpt.com/codex", "Codex"),
    "chatgpt": App(("chatgpt.exe",), "ChatGPT", "https://chatgpt.com", "ChatGPT"),
    "chrome": App(("chrome.exe",), "Google Chrome"),
    "edge": App(("msedge.exe",), "Microsoft Edge"),
    "vs code": App(("code.exe",), "Visual Studio Code"),
    "cursor": App(("cursor.exe",), "Cursor"),
    "file explorer": App(("explorer.exe",), "File Explorer"),
    "notepad": App(("notepad.exe",), "Notepad"),
    "terminal": App(("windowsterminal.exe",), "Terminal"),
    "settings": App((), "Settings"),
    "calculator": App((), "Calculator"),
    "word": App(("winword.exe",), "Word"),
    "excel": App(("excel.exe",), "Excel"),
    "powerpoint": App(("powerpnt.exe",), "PowerPoint"),
    "outlook": App(("outlook.exe", "olk.exe"), "Outlook (new)"),
    "whatsapp": App(("whatsapp.exe", "whatsapp.root.exe"), "WhatsApp", "https://web.whatsapp.com", "WhatsApp"),
    "slack": App(("slack.exe",), "Slack", "https://app.slack.com", "Slack"),
    "telegram": App(("telegram.exe",), "Telegram", "https://web.telegram.org", "Telegram"),
    "spotify": App(("spotify.exe",), "Spotify", "https://open.spotify.com", "Spotify"),
    "teams": App(("ms-teams.exe",), "Microsoft Teams", "https://teams.microsoft.com", "Teams"),
    "zoom": App(("zoom.exe",), "Zoom"),
}

# What speech recognition tends to hear instead of the app's name.
ALIASES = {
    "clawed": "claude", "cloud": "claude", "clod": "claude", "claud": "claude", "clawd": "claude",
    "glaude": "claude", "claude app": "claude", "claude ai": "claude",
    "codecs": "codex", "cortex": "codex", "code x": "codex", "kodex": "codex",
    "chat gpt": "chatgpt", "chat gbt": "chatgpt", "chad gpt": "chatgpt", "chat g p t": "chatgpt",
    "krome": "chrome", "google chrome": "chrome", "microsoft edge": "edge",
    "vscode": "vs code", "visual studio code": "vs code", "bs code": "vs code",
    "explorer": "file explorer", "files": "file explorer", "my files": "file explorer",
    "windows terminal": "terminal", "command prompt": "terminal", "microsoft teams": "teams",
    "whats app": "whatsapp", "what's app": "whatsapp", "you tube": "youtube", "g mail": "gmail",
    "git hub": "github", "linked in": "linkedin", "open code": "opencode",
    "closed": "claude", "clause": "claude", "claw": "claude", "claws": "claude",
    "floor": "claude", "throw": "claude", "clothes": "claude", "cloths": "claude", "clouds": "claude", "flawed": "claude",
}

# Keys that focus "find a chat": (desktop app, website). Empty means click the Search button.
MESSENGERS = {
    "whatsapp": ("ctrl+f", "ctrl+alt+/"),
    "slack": ("ctrl+k", "ctrl+k"),
    "telegram": ("ctrl+f", ""),
}
DEFAULT_MESSENGER = "whatsapp"
DEFAULT_PLAYER = "youtube"

AGENT_COMMANDS = {"claude": "claude", "codex": "codex", "opencode": "opencode"}
MAX_AGENTS = 8

FOLDERS = ("desktop", "downloads", "documents", "pictures", "music", "videos")

SITES = {
    "google": "https://www.google.com",
    "youtube": "https://www.youtube.com",
    "gmail": "https://mail.google.com",
    "google calendar": "https://calendar.google.com",
    "google drive": "https://drive.google.com",
    "google docs": "https://docs.google.com",
    "google sheets": "https://sheets.google.com",
    "google maps": "https://maps.google.com",
    "github": "https://github.com",
    "linkedin": "https://www.linkedin.com",
    "reddit": "https://www.reddit.com",
    "wikipedia": "https://www.wikipedia.org",
    "amazon": "https://www.amazon.in",
    "flipkart": "https://www.flipkart.com",
    "netflix": "https://www.netflix.com",
    "instagram": "https://www.instagram.com",
    "twitter": "https://x.com",
    "perplexity": "https://www.perplexity.ai",
    "gemini": "https://gemini.google.com",
}

SEARCH_URLS = {
    "google": "https://www.google.com/search?q={}",
    "youtube": "https://www.youtube.com/results?search_query={}",
    "amazon": "https://www.amazon.in/s?k={}",
    "flipkart": "https://www.flipkart.com/search?q={}",
    "github": "https://github.com/search?q={}",
    "wikipedia": "https://en.wikipedia.org/w/index.php?search={}",
    "reddit": "https://www.reddit.com/search/?q={}",
    "linkedin": "https://www.linkedin.com/search/results/all/?keywords={}",
}

# Fixed up in anything you dictate. Add your own names and jargon here.
VOCABULARY = {
    "clawed": "Claude",
    "codecs": "Codex",
    "chat gpt": "ChatGPT",
}


class _MemoryStatus(ctypes.Structure):
    _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong)] + [
        (name, ctypes.c_ulonglong)
        for name in ("total", "avail", "totalPage", "availPage", "totalVirtual", "availVirtual", "availExtended")
    ]


def total_ram_gb() -> float:
    status = _MemoryStatus()
    status.dwLength = ctypes.sizeof(status)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
    return status.total / 1024**3


def speech_tier() -> str:
    if SPEECH_MODEL != "auto":
        return SPEECH_MODEL
    strong = total_ram_gb() >= FULL_MODEL_MIN_RAM_GB and (os.cpu_count() or 1) >= FULL_MODEL_MIN_CORES
    return "parakeet" if strong else "tiny"


def thread_count() -> int:
    return min(4, max(1, (os.cpu_count() or 2) // 2))
