"""The Settings window."""
import threading
import tkinter as tk
from datetime import datetime
from tkinter import ttk

from . import routines, terminal
from . import settings as prefs

BACKGROUND = "#0b1220"
FIELD = "#16213a"
TEXT = "#e6f1ff"
MUTED = "#8ba3c7"
ACCENT = "#4fd1ff"
FIRST_PROFILE = "First profile"


def run() -> int:
    current = prefs.load()
    root = tk.Tk()
    root.title("Jarvis Settings")
    root.configure(bg=BACKGROUND, padx=28, pady=24)
    root.resizable(False, False)

    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure("TCombobox", fieldbackground=FIELD, background=FIELD, foreground=TEXT, arrowcolor=ACCENT)
    style.map("TCombobox", fieldbackground=[("readonly", FIELD)], foreground=[("readonly", TEXT)])
    root.option_add("*TCombobox*Listbox.background", FIELD)
    root.option_add("*TCombobox*Listbox.foreground", TEXT)

    tk.Label(root, text="JARVIS", bg=BACKGROUND, fg=ACCENT, font=("Segoe UI Semibold", 20)).pack(anchor="w")
    tk.Label(root, text="Make it yours.", bg=BACKGROUND, fg=MUTED, font=("Segoe UI", 10)).pack(anchor="w", pady=(0, 14))

    def label(text: str, hint: str = "") -> None:
        tk.Label(root, text=text, bg=BACKGROUND, fg=TEXT, font=("Segoe UI Semibold", 10)).pack(anchor="w", pady=(10, 2))
        if hint:
            tk.Label(root, text=hint, bg=BACKGROUND, fg=MUTED, font=("Segoe UI", 9), wraplength=400, justify="left").pack(anchor="w", pady=(0, 3))

    def entry(value: str) -> tk.StringVar:
        variable = tk.StringVar(value=value)
        tk.Entry(root, textvariable=variable, bg=FIELD, fg=TEXT, insertbackground=ACCENT, relief="flat",
                 font=("Segoe UI", 11), width=42).pack(anchor="w", ipady=6)
        return variable

    label("What should Jarvis call you?", "For example: your name, sir, boss.")
    user_name = entry(current.user_name)

    label("What do you call Jarvis?", 'The word that wakes it. "Jarvis" is the most accurate; another name works but uses a bit more CPU.')
    wake_name = entry(current.wake_name)

    label("How long should it wait for your next command?", "Seconds to keep listening after each command, so you don't repeat the wake word.")
    seconds = tk.IntVar(value=current.listen_seconds)
    tk.Spinbox(root, from_=prefs.MIN_LISTEN, to=prefs.MAX_LISTEN, textvariable=seconds, width=6, bg=FIELD, fg=TEXT,
               buttonbackground=FIELD, relief="flat", insertbackground=ACCENT, font=("Segoe UI", 11)).pack(anchor="w", ipady=4)

    import sounddevice as sd

    automatic = "Automatic (headset when connected)"
    default_host = sd.default.hostapi
    microphones = [
        device["name"] for device in sd.query_devices()
        if device["max_input_channels"] > 0 and device["hostapi"] == default_host and "Sound Mapper" not in device["name"]
    ]
    label("Microphone", "Automatic switches to earphones or glasses as soon as they connect.")
    mic_names = [automatic, *microphones, *([current.microphone] if current.microphone and current.microphone not in microphones else [])]
    microphone = tk.StringVar(value=current.microphone or automatic)
    ttk.Combobox(root, textvariable=microphone, values=mic_names, state="readonly", width=44, font=("Segoe UI", 10)).pack(anchor="w", ipady=3)

    label("Voice", 'Pick one, then use "Hear greeting" below.')
    voice_ids = {text: key for key, text in prefs.VOICES.items()}
    voice_choice = tk.StringVar(value=prefs.VOICES.get(current.voice, next(iter(voice_ids))))
    ttk.Combobox(root, textvariable=voice_choice, values=list(voice_ids), state="readonly", width=44, font=("Segoe UI", 10)).pack(anchor="w", ipady=3)

    label("How fast should Jarvis speak?", 'Higher is quicker. Use "Hear greeting" below to try it.')
    speed = tk.DoubleVar(value=current.voice_speed)
    tk.Scale(root, from_=prefs.MIN_SPEED, to=prefs.MAX_SPEED, resolution=0.05, orient="horizontal", variable=speed, length=380,
             bg=BACKGROUND, fg=TEXT, troughcolor=FIELD, activebackground=ACCENT, highlightthickness=0, relief="flat",
             font=("Segoe UI", 9)).pack(anchor="w")

    profiles = prefs.chrome_profiles()
    names = [FIRST_PROFILE + (f" ({profiles[0][1]})" if profiles else "")]
    choices = {names[0]: ""}
    for folder, display in profiles:
        text = f"{display} [{folder}]"
        names.append(text)
        choices[text] = folder
    label("Chrome profile", "Which profile opens when you ask for Chrome.")
    selected = next((text for text, folder in choices.items() if folder == current.chrome_profile), names[0])
    profile = tk.StringVar(value=selected)
    ttk.Combobox(root, textvariable=profile, values=names, state="readonly", width=44, font=("Segoe UI", 10)).pack(anchor="w", ipady=3)

    talk_back = tk.BooleanVar(value=current.talk_back)
    enter_after = tk.BooleanVar(value=current.enter_after_typing)
    right_alt = tk.BooleanVar(value=current.use_right_alt)
    debug_log = tk.BooleanVar(value=current.keep_debug_log)
    start_up = tk.BooleanVar(value=prefs.starts_with_windows())

    def check(text: str, variable: tk.BooleanVar, enabled: bool = True) -> None:
        tk.Checkbutton(root, text=text, variable=variable, bg=BACKGROUND, fg=TEXT, selectcolor=FIELD, activebackground=BACKGROUND,
                       activeforeground=TEXT, font=("Segoe UI", 10), state="normal" if enabled else "disabled").pack(anchor="w", pady=(10, 0))

    check("Talk back to me", talk_back)
    check("Press Enter automatically after typing", enter_after)
    check("Use Right Alt as the talk key", right_alt)
    check("Keep a detailed log for troubleshooting (records what you say)", debug_log)
    check("Start Jarvis when Windows starts", start_up, prefs.can_start_with_windows())

    status = tk.StringVar()
    tk.Label(root, textvariable=status, bg=BACKGROUND, fg=ACCENT, font=("Segoe UI", 9)).pack(anchor="w", pady=(14, 4))
    row = tk.Frame(root, bg=BACKGROUND)
    row.pack(anchor="w")

    def clean_name(variable: tk.StringVar, fallback: str) -> str:
        return " ".join(variable.get().split()) or fallback

    def save() -> None:
        try:
            listen = max(prefs.MIN_LISTEN, min(int(seconds.get()), prefs.MAX_LISTEN))
        except (tk.TclError, ValueError):
            listen = prefs.Settings.listen_seconds
        prefs.save(prefs.Settings(
            user_name=clean_name(user_name, "sir"),
            wake_name=clean_name(wake_name, "Jarvis"),
            talk_back=talk_back.get(),
            listen_seconds=listen,
            voice=voice_ids[voice_choice.get()],
            voice_speed=round(speed.get(), 2),
            enter_after_typing=enter_after.get(),
            use_right_alt=right_alt.get(),
            keep_debug_log=debug_log.get(),
            microphone="" if microphone.get() == automatic else microphone.get(),
            chrome_profile=choices.get(profile.get(), ""),
        ))
        if prefs.can_start_with_windows():
            prefs.set_start_with_windows(start_up.get())
        root.destroy()

    def test_voice() -> None:
        status.set("Warming up the voice...")
        chosen_speed = round(speed.get(), 2)
        chosen_voice = voice_ids[voice_choice.get()]

        def speak() -> None:
            from . import persona
            from .voice import Voice

            voice = Voice(chosen_speed, chosen_voice)
            voice.say(persona.greeting(clean_name(user_name, "sir"), datetime.now()))
            voice.finish()
            root.after(0, lambda: status.set(""))

        threading.Thread(target=speak, daemon=True).start()

    def button(text: str, command, primary: bool = False) -> None:
        tk.Button(row, text=text, command=command, relief="flat", cursor="hand2", padx=18, pady=7, font=("Segoe UI Semibold", 10),
                  bg=ACCENT if primary else FIELD, fg=BACKGROUND if primary else TEXT,
                  activebackground=ACCENT, activeforeground=BACKGROUND).pack(side="left", padx=(0, 10))

    def edit_file(title: str, module) -> None:
        window = tk.Toplevel(root, bg=BACKGROUND, padx=18, pady=16)
        window.title(title)
        editor = tk.Text(window, width=86, height=24, bg=FIELD, fg=TEXT, insertbackground=ACCENT, relief="flat", font=("Consolas", 10))
        editor.insert("1.0", module.read_text())
        editor.pack()

        def save_file() -> None:
            module.write_text(editor.get("1.0", "end-1c"))
            window.destroy()

        tk.Button(window, text="Save", command=save_file, relief="flat", cursor="hand2", padx=18, pady=7,
                  font=("Segoe UI Semibold", 10), bg=ACCENT, fg=BACKGROUND).pack(anchor="w", pady=(12, 0))

    button("Save", save, primary=True)
    button("Hear greeting", test_voice)
    button("Routines", lambda: edit_file("Jarvis Routines", routines))
    button("Terminal", lambda: edit_file("Jarvis Terminal Commands", terminal))
    root.mainloop()
    return 0
