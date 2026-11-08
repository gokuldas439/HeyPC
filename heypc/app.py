"""Starts HeyPC. Heavy libraries load only when needed, so the Settings window opens quickly."""
import ctypes
import re
import subprocess
import sys

from . import downloads
from . import settings as prefs

MUTEX_NAME = "VoiceJarvisSingleInstance"
ERROR_ALREADY_EXISTS = 183
PER_MONITOR_AWARE = 2
SAFE_LINE = re.compile(r"\s*(?:Loading speech model|microphone:|microphone \S+ did not open|Ready\.|audio devices changed|microphone stopped|\d\d:\d\d:\d\d woke|that failed|voice typing failed|voice did not load|could not speak|online voice unavailable|could not check audio|could not prepare|could not show a notification|the on-screen indicator stopped|reminder check failed|clipboard check failed|model download failed|window items readable|audio devices:|voice produced|CHECK OK)")


def self_command(*args: str) -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, *args]
    return [sys.executable, "-m", "heypc.app", *args]


def open_settings() -> None:
    subprocess.Popen(self_command("--settings"))


def _models_ready() -> bool:
    return not downloads.needed() or subprocess.run(self_command("--models")).returncode == 0


def open_setup() -> None:
    subprocess.Popen(self_command("--setup"))


class _PrivateLog:
    """Leaves out anything you said or typed, unless you turned on the detailed log in Settings."""

    def __init__(self, stream, keep_everything: bool) -> None:
        self.stream = stream
        self.keep_everything = keep_everything
        self.skipping = False

    def write(self, text: str) -> None:
        if text == "\n":
            if not self.skipping:
                self.stream.write(text)
            self.skipping = False
            return
        self.skipping = not self.keep_everything and not SAFE_LINE.match(text)
        if not self.skipping:
            self.stream.write(text if self.keep_everything else text.split("(", 1)[0])  # error details can quote what you said

    def flush(self) -> None:
        self.stream.flush()


def _log_to_file(path) -> None:
    """An installed app has no console, so printing has to go somewhere."""
    prefs.DATA.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.replace(path.with_suffix(".previous.log"))  # keeps the last session for troubleshooting
    log = _PrivateLog(open(path, "w", encoding="utf-8", buffering=1, errors="replace"), prefs.load().keep_debug_log)
    sys.stdout = log
    sys.stderr = log


def _check() -> int:
    """Used after packaging: proves the bundled models and libraries really load."""
    from . import uia
    from .audio import Transcriber, WakeWord, audio_device_state
    from .overlay import Painter
    from .voice import Voice

    Transcriber()
    WakeWord()
    samples, rate = Voice().render("Systems check.")
    print(f"voice produced {len(samples) / rate:.2f}s of audio")
    print("window items readable:", len(uia.scan()))
    print("audio devices:", len(audio_device_state()) > 0, "| indicator frame:", Painter(1.0).frame("listening", 0.5, 1.0).size)
    print("CHECK OK")
    return 0


def main() -> int:
    if "--models" in sys.argv:
        from .download_ui import run

        return run()
    if "--setup" in sys.argv:
        from .setup_ui import run

        return run()
    if "--settings" in sys.argv:
        from .settings_ui import run

        return run()
    # Real pixel coordinates: keeps the indicator sharp and click-by-name accurate on scaled displays.
    ctypes.windll.shcore.SetProcessDpiAwareness(PER_MONITOR_AWARE)
    if "--check" in sys.argv:
        _log_to_file(prefs.CHECK_LOG)
        return _check()

    mutex = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if ctypes.windll.kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        open_settings()  # launching it again from the Start menu should do something visible
        return 1
    if getattr(sys, "frozen", False):
        _log_to_file(prefs.LOG)
    if not prefs.is_saved():
        prefs.save(prefs.load())
        open_setup()
    if not _models_ready():
        return 1

    from .main import Jarvis
    from .overlay import Overlay
    from .tray import start_tray

    try:
        jarvis = Jarvis()
        jarvis.notify = start_tray(jarvis, open_settings, open_setup).notify
        Overlay(jarvis.display_state).start()
        jarvis.run()
    except KeyboardInterrupt:
        print("Stopped.")
    finally:
        ctypes.windll.kernel32.CloseHandle(mutex)
    return 0


if __name__ == "__main__":
    sys.exit(main())
