"""The first-run setup page: who you are, which voice, and what "Start work" should open."""
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, ttk

from . import routines, terminal
from . import settings as prefs
from .settings_ui import ACCENT, BACKGROUND, FIELD, MUTED, TEXT

ROUTINE_NAME = "start work"
EDITORS = {"Cursor": "cursor", "VS Code": "vscode"}
ONLINE_NOTE = (
    "Jarvis listens and understands you entirely on this PC. Online voices send only the sentence being spoken to "
    "Microsoft's free read-aloud service; the offline voices send nothing."
)


def _step_text(kind: str, value: str, chrome_names: dict) -> str:
    if kind in EDITORS.values():
        editor = next(name for name, key in EDITORS.items() if key == kind)
        return f"Open {Path(value).name} in {editor}"
    if kind == "chrome":
        return f"Open Chrome: {chrome_names.get(value, value)}"
    if kind == "url":
        return f"Open website: {value}"
    return f"Open {value}"


def _seed_terminal_projects(steps: list[tuple[str, str]]) -> None:
    """Project folders added here can also take voice commands such as "git status in my-project"."""
    if terminal.FILE.exists():
        return
    folders = [value for kind, value in steps if kind in EDITORS.values()]
    lines = "".join(f"{Path(folder).name.lower()} = {folder}\n" for folder in folders)
    terminal.write_text(terminal.TEMPLATE.replace("[projects]\n", f"[projects]\n{lines}"))


def run() -> int:
    current = prefs.load()
    profiles = prefs.chrome_profiles()
    chrome_names = {folder: name for folder, name in profiles}
    steps = list(routines.load().get(ROUTINE_NAME, []))

    root = tk.Tk()
    root.title("Welcome to Jarvis")
    root.configure(bg=BACKGROUND, padx=30, pady=24)
    root.resizable(False, False)
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure("TCombobox", fieldbackground=FIELD, background=FIELD, foreground=TEXT, arrowcolor=ACCENT)
    style.map("TCombobox", fieldbackground=[("readonly", FIELD)], foreground=[("readonly", TEXT)])
    root.option_add("*TCombobox*Listbox.background", FIELD)
    root.option_add("*TCombobox*Listbox.foreground", TEXT)

    tk.Label(root, text="Welcome to Jarvis", bg=BACKGROUND, fg=ACCENT, font=("Segoe UI Semibold", 20)).pack(anchor="w")
    tk.Label(root, text="A quick setup. You can change all of this later in Settings.", bg=BACKGROUND, fg=MUTED, font=("Segoe UI", 10)).pack(anchor="w", pady=(0, 10))

    def label(text: str, hint: str = "") -> None:
        tk.Label(root, text=text, bg=BACKGROUND, fg=TEXT, font=("Segoe UI Semibold", 10)).pack(anchor="w", pady=(10, 2))
        if hint:
            tk.Label(root, text=hint, bg=BACKGROUND, fg=MUTED, font=("Segoe UI", 9), wraplength=500, justify="left").pack(anchor="w", pady=(0, 3))

    def entry(parent, value: str = "", width: int = 54) -> tk.StringVar:
        variable = tk.StringVar(value=value)
        tk.Entry(parent, textvariable=variable, bg=FIELD, fg=TEXT, insertbackground=ACCENT, relief="flat", font=("Segoe UI", 11), width=width).pack(side="left", ipady=5)
        return variable

    def row() -> tk.Frame:
        frame = tk.Frame(root, bg=BACKGROUND)
        frame.pack(anchor="w", pady=(4, 0))
        return frame

    def small_button(parent, text: str, command, primary: bool = False) -> None:
        tk.Button(parent, text=text, command=command, relief="flat", cursor="hand2", padx=14, pady=5, font=("Segoe UI Semibold", 9),
                  bg=ACCENT if primary else FIELD, fg=BACKGROUND if primary else TEXT, activebackground=ACCENT, activeforeground=BACKGROUND).pack(side="left", padx=(8, 0))

    label("What should Jarvis call you?")
    user_name = entry(row(), "" if current.user_name == prefs.Settings.user_name else current.user_name)

    label("What do you want to call your AI?", 'This is the word that wakes it. We suggest "Jarvis", which responds best, but you can pick any name.')
    wake_name = entry(row(), current.wake_name)

    label("Voice", ONLINE_NOTE)
    voice_ids = {text: key for key, text in prefs.VOICES.items()}
    voice_row = row()
    voice_choice = tk.StringVar(value=prefs.VOICES.get(current.voice, next(iter(voice_ids))))
    ttk.Combobox(voice_row, textvariable=voice_choice, values=list(voice_ids), state="readonly", width=40, font=("Segoe UI", 10)).pack(side="left", ipady=3)
    status = tk.StringVar()

    def hear() -> None:
        status.set("Warming up the voice...")
        chosen = voice_ids[voice_choice.get()]
        name = user_name.get().strip() or "there"

        def speak() -> None:
            from . import persona
            from .voice import Voice

            voice = Voice(prefs.Settings.voice_speed, chosen)
            voice.say(persona.greeting(name, datetime.now()))
            voice.finish()
            root.after(0, lambda: status.set(""))

        threading.Thread(target=speak, daemon=True).start()

    small_button(voice_row, "Hear it", hear)

    label('What should "Start work" open?', 'Saying "Hey Jarvis, start work" opens everything in this list. You can leave it empty.')
    listing = tk.Listbox(root, height=5, width=68, bg=FIELD, fg=TEXT, relief="flat", font=("Segoe UI", 10), selectbackground=ACCENT, selectforeground=BACKGROUND, highlightthickness=0)
    listing.pack(anchor="w", ipady=2)

    def refresh() -> None:
        listing.delete(0, "end")
        for kind, value in steps:
            listing.insert("end", _step_text(kind, value, chrome_names))

    def add(kind: str, value: str) -> None:
        if value and (kind, value) not in steps:
            steps.append((kind, value))
            refresh()

    def remove() -> None:
        for index in reversed(listing.curselection()):
            del steps[index]
        refresh()

    editors = [name for name, key in EDITORS.items() if prefs.editor_path(key)]
    if editors:
        editor_row = row()
        editor_choice = tk.StringVar(value=editors[0])
        ttk.Combobox(editor_row, textvariable=editor_choice, values=editors, state="readonly", width=40, font=("Segoe UI", 10)).pack(side="left", ipady=3)

        def add_folder() -> None:
            folder = filedialog.askdirectory(parent=root, title="Choose a project folder")
            if folder:
                add(EDITORS[editor_choice.get()], str(Path(folder)))

        small_button(editor_row, "Add project folder", add_folder)

    if profiles:
        chrome_row = row()
        names = [f"{name} [{folder}]" for folder, name in profiles]
        chrome_choice = tk.StringVar(value=names[0])
        ttk.Combobox(chrome_row, textvariable=chrome_choice, values=names, state="readonly", width=40, font=("Segoe UI", 10)).pack(side="left", ipady=3)
        small_button(chrome_row, "Add Chrome profile", lambda: add("chrome", profiles[names.index(chrome_choice.get())][0]))

    other_row = row()
    other = entry(other_row, "", 41)

    def add_other() -> None:
        value = other.get().strip()
        if value:
            add("url" if value.startswith("http") else "open", value)
            other.set("")

    small_button(other_row, "Add app or website", add_other)
    small_button(other_row, "Remove selected", remove)
    refresh()

    start_up = tk.BooleanVar(value=prefs.starts_with_windows())
    tk.Checkbutton(root, text="Start Jarvis when Windows starts", variable=start_up, bg=BACKGROUND, fg=TEXT, selectcolor=FIELD, activebackground=BACKGROUND,
                   activeforeground=TEXT, font=("Segoe UI", 10), state="normal" if prefs.can_start_with_windows() else "disabled").pack(anchor="w", pady=(12, 0))

    tk.Label(root, textvariable=status, bg=BACKGROUND, fg=ACCENT, font=("Segoe UI", 9)).pack(anchor="w", pady=(6, 2))

    def finish() -> None:
        prefs.save(prefs.Settings(
            user_name=" ".join(user_name.get().split()) or prefs.Settings.user_name,
            wake_name=" ".join(wake_name.get().split()) or prefs.Settings.wake_name,
            voice=voice_ids[voice_choice.get()],
        ))
        if prefs.can_start_with_windows():
            prefs.set_start_with_windows(start_up.get())
        body = "\n".join(f"{kind} {value}" for kind, value in steps)
        routines.write_text(f"{routines.TEMPLATE}[{ROUTINE_NAME}]\n{body}\n")
        _seed_terminal_projects(steps)
        root.destroy()

    finish_row = tk.Frame(root, bg=BACKGROUND)
    finish_row.pack(anchor="w")
    tk.Button(finish_row, text="Finish setup", command=finish, relief="flat", cursor="hand2", padx=22, pady=8, font=("Segoe UI Semibold", 11), bg=ACCENT, fg=BACKGROUND,
              activebackground=ACCENT, activeforeground=BACKGROUND).pack(side="left")
    root.mainloop()
    return 0
