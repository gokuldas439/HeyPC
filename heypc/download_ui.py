"""The window shown while the speech models download on first run."""
import shutil
import threading
import tkinter as tk
from tkinter import ttk

from . import downloads
from .settings_ui import ACCENT, BACKGROUND, FIELD, MUTED, TEXT

SPARE_SPACE = 200 * 1024 * 1024
MEGABYTE = 1024 * 1024
WINDOW_WIDTH, WINDOW_HEIGHT = 500, 270
SCREEN_MARGIN = 60
PRIVACY_NOTE = (
    "Downloading the speech recognition model to this PC. This only happens once. "
    "It runs right here on your computer, so your voice is never uploaded or saved."
)


def run() -> int:
    """Returns 0 once everything is ready, or 1 if the window was closed first."""
    files = downloads.needed()
    if not files:
        return 0
    total = sum(file.size for file in files)
    outcome = {"code": 1}

    root = tk.Tk()
    root.title("Getting HeyPC ready")
    root.configure(bg=BACKGROUND, padx=26, pady=22)
    root.resizable(False, False)
    x = root.winfo_screenwidth() - WINDOW_WIDTH - SCREEN_MARGIN
    y = root.winfo_screenheight() - WINDOW_HEIGHT - SCREEN_MARGIN * 2
    root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}+{x}+{y}")

    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure("Bar.Horizontal.TProgressbar", troughcolor=FIELD, background=ACCENT, bordercolor=FIELD, lightcolor=ACCENT, darkcolor=ACCENT)

    tk.Label(root, text="Getting HeyPC ready", bg=BACKGROUND, fg=ACCENT, font=("Segoe UI Semibold", 15)).pack(anchor="w")
    tk.Label(root, text=PRIVACY_NOTE, bg=BACKGROUND, fg=MUTED, font=("Segoe UI", 10), wraplength=446, justify="left").pack(anchor="w", pady=(4, 14))
    bar = ttk.Progressbar(root, style="Bar.Horizontal.TProgressbar", length=446, maximum=total)
    bar.pack(anchor="w")
    status = tk.StringVar(value="Starting...")
    tk.Label(root, textvariable=status, bg=BACKGROUND, fg=TEXT, font=("Segoe UI", 10)).pack(anchor="w", pady=(10, 8))
    retry_button = tk.Button(root, text="Try again", relief="flat", cursor="hand2", padx=16, pady=5, font=("Segoe UI Semibold", 10), bg=ACCENT, fg=BACKGROUND)

    def on_progress(done: int) -> None:
        def show() -> None:
            bar["value"] = done
            status.set(f"{done // MEGABYTE} MB of {total // MEGABYTE} MB")

        root.after(0, show)

    def finished() -> None:
        outcome["code"] = 0
        root.destroy()

    def failed() -> None:
        status.set("The download stopped. Check your internet connection.")
        retry_button.pack(anchor="w")

    def work() -> None:
        try:
            downloads.download_all(downloads.needed(), on_progress)
        except Exception as error:
            print(f"   model download failed: {type(error).__name__}")
            root.after(0, failed)
        else:
            root.after(0, finished)

    def start() -> None:
        retry_button.pack_forget()
        downloads.DOWNLOADED_MODELS.mkdir(parents=True, exist_ok=True)
        if shutil.disk_usage(downloads.DOWNLOADED_MODELS).free < total + SPARE_SPACE:
            status.set(f"You need about {(total + SPARE_SPACE) // MEGABYTE} MB of free disk space.")
            retry_button.pack(anchor="w")
            return
        status.set("Starting...")
        threading.Thread(target=work, daemon=True).start()

    retry_button.configure(command=start)
    start()
    root.mainloop()
    return outcome["code"]
