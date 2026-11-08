"""What you choose in the Settings window, saved in %APPDATA%\\Jarvis."""
import json
import os
import shutil
import sys
import winreg
from dataclasses import asdict, dataclass, fields
from pathlib import Path

DATA = Path(os.environ["APPDATA"]) / "HeyPC"
_EARLIER_DATA = Path(os.environ["APPDATA"]) / "Jarvis"  # the app's name before it became HeyPC
FILE = DATA / "settings.json"
LOG = DATA / "jarvis.log"
CHECK_LOG = DATA / "check.log"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "HeyPC"
CHROME_STATE = Path(os.environ["LOCALAPPDATA"]) / "Google" / "Chrome" / "User Data" / "Local State"
MIN_LISTEN, MAX_LISTEN = 5, 120
MIN_SPEED, MAX_SPEED = 0.9, 1.6
EDITOR_PROGRAMS = {"cursor": ("cursor", "Cursor.exe", "cursor"), "vscode": ("code", "Code.exe", "Microsoft VS Code")}
VOICES = {
    "en-US-AndrewMultilingualNeural": "Andrew (American man, warm)",
    "en-US-BrianMultilingualNeural": "Brian (American man, casual)",
    "en-GB-RyanNeural": "Ryan (British man)",
    "en-IN-PrabhatNeural": "Prabhat (Indian man)",
    "en-US-AvaMultilingualNeural": "Ava (American woman, warm)",
    "en-US-EmmaMultilingualNeural": "Emma (American woman, cheerful)",
    "en-GB-SoniaNeural": "Sonia (British woman)",
    "en-IN-NeerjaExpressiveNeural": "Neerja (Indian woman, expressive)",
    "bm_george": "George (British man, offline)",
    "af_heart": "Heart (American woman, offline)",
}


if _EARLIER_DATA.exists() and not DATA.exists():
    try:
        shutil.copytree(_EARLIER_DATA, DATA, ignore=shutil.ignore_patterns("voice-cache", "*.log"))
    except OSError:
        pass  # starts with defaults instead


@dataclass
class Settings:
    user_name: str = "sir"  # what Jarvis calls you
    wake_name: str = "Jarvis"  # what you call Jarvis
    talk_back: bool = True  # spoken replies
    listen_seconds: int = 15  # how long Jarvis waits for your next command
    voice: str = "en-US-AndrewMultilingualNeural"
    voice_speed: float = 1.0  # 1.0 is the voice's natural pace
    enter_after_typing: bool = False  # press Enter by itself once dictation is typed
    use_right_alt: bool = True  # the talk hotkey; automatically off on keyboards where Right Alt types symbols
    keep_debug_log: bool = False  # also write what was heard to the log, for troubleshooting
    microphone: str = ""  # empty means automatic: a headset when connected, otherwise the Windows default
    chrome_profile: str = ""  # folder name of a Chrome profile; empty means the first one


def is_saved() -> bool:
    return FILE.exists()


def modified_at() -> float:
    try:
        return FILE.stat().st_mtime
    except OSError:
        return 0.0


def load() -> Settings:
    try:
        saved = json.loads(FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Settings()
    known = {field.name for field in fields(Settings)}
    return Settings(**{key: value for key, value in saved.items() if key in known})


def save(settings: Settings) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    partial = FILE.with_suffix(".tmp")
    partial.write_text(json.dumps(asdict(settings), indent=2), encoding="utf-8")
    partial.replace(FILE)


def chrome_profiles() -> list[tuple[str, str]]:
    """(folder, display name) in Chrome's own order, so the first entry is your first profile."""
    try:
        profile = json.loads(CHROME_STATE.read_text(encoding="utf-8"))["profile"]
    except (OSError, ValueError, KeyError):
        return []
    info = profile.get("info_cache", {})
    order = [folder for folder in profile.get("profiles_order", []) if folder in info]
    order += [folder for folder in info if folder not in order]
    return [(folder, info[folder].get("name") or folder) for folder in order]


def editor_path(kind: str) -> str | None:
    """The program for a code editor ("cursor" or "vscode"), or None if it isn't installed."""
    command, exe_name, folder_name = EDITOR_PROGRAMS[kind]
    if found := shutil.which(command):
        beside_command = Path(found).parents[1] / exe_name  # the command lives one folder below the program
        for candidate in (beside_command, Path(found).parents[3] / exe_name):
            if candidate.exists():
                return str(candidate)
    for root in (Path(os.environ["LOCALAPPDATA"]) / "Programs", Path(os.environ.get("ProgramFiles", r"C:\Program Files"))):
        if (root / folder_name / exe_name).exists():
            return str(root / folder_name / exe_name)
    return None


def find_chrome_profile(wanted: str) -> str | None:
    """The profile folder for a folder name or display name."""
    lowered = wanted.lower()
    return next((folder for folder, name in chrome_profiles() if lowered in (folder.lower(), name.lower())), None)


def chosen_chrome_profile() -> str:
    chosen = load().chrome_profile
    profiles = chrome_profiles()
    if chosen and any(folder == chosen for folder, _ in profiles):
        return chosen
    return profiles[0][0] if profiles else ""


def can_start_with_windows() -> bool:
    return bool(getattr(sys, "frozen", False))


def starts_with_windows() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, APP_NAME)
        return True
    except OSError:
        return False


def set_start_with_windows(enabled: bool) -> None:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, f'"{sys.executable}"')
        elif starts_with_windows():
            winreg.DeleteValue(key, APP_NAME)
