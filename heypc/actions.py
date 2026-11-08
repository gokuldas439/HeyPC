"""Carries out parsed commands."""
import os
import re
import shutil
import subprocess
import time
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path

from . import settings as prefs
from . import calc, files, pc, routines, summary, terminal, uia, winctl
from . import reminders as reminder_rules
from .commands import Action, canon, clean_dictation, is_risky, learn_name, parse_when, sounds_like
from .persona import spoken as persona_spoken
from .config import (
    AGENT_COMMANDS, APPS, DEFAULT_PLAYER, FOLDERS, MAX_AGENTS, MESSENGERS, SEARCH_URLS, SITES,
)

DOMAIN = re.compile(r"^[a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,}(?:/\S*)?$", re.I)
MEETING_LINK = re.compile(r"https?://[^\s\"'<>]*(?:meet\.google\.com/|zoom\.us/j/|teams\.microsoft\.com/l/meetup)[^\s\"'<>]*", re.I)
SEARCH_BOX = re.compile(r"search|find|jump|switcher|start a new chat", re.I)
LAUNCH_WAIT = 25.0
WEB_LOAD_WAIT = 5.0
CONTACT_WAIT = 1.5
JOIN_BUTTONS = ["Join now", "Join", "Join meeting", "Join with Google Meet", "Join Zoom Meeting"]
MAIL_BUTTONS = {"reply": "Reply", "reply_all": "Reply all", "forward": "Forward", "archive": "Archive"}
OUTLOOK_KEYS = {"reply": "ctrl+r", "reply_all": "ctrl+shift+r", "forward": "ctrl+f", "archive": "backspace"}
OUTLOOK_EXES = {"olk.exe", "outlook.exe"}
BAD_NAME_CHARS = re.compile(r'[<>:"/\\|?*]')
SKIP_DIRS = {"appdata", "node_modules", "__pycache__"}
AI_APPS = ("claude", "chatgpt", "codex")
NEW_CHAT_BUTTONS = ["New chat", "New conversation", "New session", "New thread", "New task", "New"]
NEW_CHAT_SETTLE = 0.6
ASK_SETTLE = 0.25
ROUTINE_STEP_GAP = 0.8
MIN_APP_NAME = 3
NEVER_CONTROL = {"jarvis.exe", "textinputhost.exe", "applicationframehost.exe", "searchhost.exe", "startmenuexperiencehost.exe"}
TAB_SETTLE = 0.2
MAX_CLIPS_READ = 3
CLIP_PREVIEW = 60
TERMINAL_TIMEOUT = 120
MAX_REMINDERS_READ = 3
SNAP_SETTLE = 0.5
PC_CONFIRM = {
    "shut_down": ("Shut down the PC? Say yes.", pc.shut_down),
    "restart": ("Restart the PC? Say yes.", pc.restart),
    "sign_out": ("Sign out of Windows? Say yes.", pc.sign_out),
}
PAGE_READ_TRIES = 4
PAGE_READ_WAIT = 0.8


class Actions:
    def __init__(self, ask=None, hear=None, say=None, speak=None, reminders=None, clipboard_history=None) -> None:
        self.clipboard_history = clipboard_history
        self.last_opened = ""
        self.speak = speak or (lambda _text: None)  # reads longer text aloud
        self.reminders = reminders
        self.start_menu = winctl.StartMenu()
        self.ask = ask  # says a question and returns True only on a spoken yes
        self.hear = hear  # listens and returns dictated text
        self.say = say or (lambda _what: None)  # reports "sent" or "not_sent" aloud

    def run(self, action: Action) -> bool:
        handlers = {
            "open": lambda: self.open(action.arg),
            "search": lambda: self.search(action.arg, action.site or "google"),
            "type": lambda: self.type_text(action.arg),
            "press": lambda: self.press(action.arg),
            "message": lambda: self.message(action.arg, action.site, action.text),
            "mail": lambda: self.mail(action.arg, action.text),
            "click": lambda: self.click(action.arg),
            "nth": lambda: self.click_nth(int(action.arg), action.site),
            "play": lambda: self.play(action.arg, action.site or DEFAULT_PLAYER),
            "calendar": lambda: self.calendar(action.arg),
            "join": lambda: self.join(action.arg, action.site),
            "agents": lambda: self.agents(int(action.arg), action.site, action.text),
            "folder": lambda: self.open_folder(action.arg),
            "rename": lambda: self.rename(action.arg),
            "volume": lambda: self.set_volume(int(action.arg)),
            "new_chat": lambda: self.new_chat(action.arg),
            "summarize": self.summarize,
            "window": lambda: self.control_app(action.arg, action.site),
            "tab": lambda: self.switch_tab(action.arg, action.site == "close"),
            "clip": lambda: self.clip(action.site, action.arg),
            "calc": lambda: self.calculate(action.arg),
            "find": lambda: self.find_file(action.arg, action.site == "open"),
            "latest": lambda: self.open_latest(action.arg),
            "terminal": lambda: self.run_terminal(action.arg, action.site),
            "ask_ai": lambda: self.ask_ai(action.site, action.arg),
            "routine": lambda: self.routine(action.arg),
            "remind": lambda: self.remind(action.arg),
            "timer": lambda: self.timer(action.arg),
            "reminders": lambda: self.manage_reminders(action.arg),
            "pc": lambda: self.pc_control(action.arg, action.site),
            "snap": lambda: self.snap(action.arg, action.site),
            "erase": lambda: self.erase(action.site, action.arg),
        }
        handler = handlers.get(action.kind)
        return handler() if handler else False

    def press(self, name: str) -> bool:
        if name == "forward" and self._front_is_mail():
            return self.mail("forward", "")
        winctl.press_named(name)
        print(f"   pressed {name}")
        return True

    def open(self, spoken: str) -> bool:
        target = canon(spoken)
        if target in APPS:
            return self._open_app(target, APPS[target])
        if target in SITES:
            return self._browse(SITES[target])
        if target in FOLDERS:
            return self.open_folder(target)
        address = re.sub(r"\s*\bdot\b\s*", ".", target).replace(" ", "")
        if DOMAIN.match(address):
            return self._browse(f"https://{address}")
        return self._open_other(target)

    def _open_app(self, name: str, app) -> bool:
        self.last_opened = name
        if app.exes and (hwnd := winctl.find_window(app.exes)):
            print(f"   switching to {name}")
            return winctl.focus(hwnd)
        if name == "chrome" and winctl.open_chrome(prefs.chosen_chrome_profile()):
            print("   launching chrome")  # a named profile avoids Chrome's "Who's using Chrome?" screen
            self._wait_and_focus(app.exes)
            return True
        if app_id := self.start_menu.exact(app.start_name):
            print(f"   launching {name}")
            winctl.launch(app_id)
            self._wait_and_focus(app.exes)
            return True
        if app.title_word and (hwnd := winctl.find_browser_tab(app.title_word)):
            print(f"   {name} is open in the browser, switching to it")
            return winctl.focus(hwnd)
        if app.url:
            print(f"   {name} is not installed, opening it in the browser")
            return self._browse(app.url)
        print(f"   {name} is not installed")
        return False

    def _wait_and_focus(self, exes) -> None:
        if not exes:
            time.sleep(1.5)
            return
        deadline = time.monotonic() + LAUNCH_WAIT
        while time.monotonic() < deadline:
            if hwnd := winctl.find_window(exes):
                winctl.focus(hwnd)
                time.sleep(0.6)  # lets the chat box finish appearing before any typing
                return
            time.sleep(0.25)

    def _open_other(self, target: str) -> bool:
        match = self.start_menu.closest(target)
        if not match:
            return self._open_best_guess(target)
        name, app_id = match
        stem = re.sub(r"\W+", "", name)
        if hwnd := winctl.find_window([f"{stem}.exe"]):
            print(f"   switching to {name}")
            return winctl.focus(hwnd)
        print(f"   launching {name}")
        winctl.launch(app_id)
        time.sleep(1.5)
        return True

    def _open_best_guess(self, target: str) -> bool:
        """The name wasn't found. Open it if it clearly sounds like a known app, otherwise ask and remember the answer."""
        sounds = sounds_like(target, [*APPS, *SITES])
        if sounds:
            print(f"   {target!r} sounds like {sounds}")
            return self.open(sounds)
        guess = self.last_opened or AI_APPS[0]
        if self._confirm(f"Did you mean {persona_spoken(guess)}?"):
            learn_name(target, guess)
            print(f"   learned: {target!r} means {guess}")
            return self.open(guess)
        print(f"   could not find an app or site called {target!r}")
        return False

    def _browse(self, url: str) -> bool:
        print(f"   opening {url}")
        if not (winctl.default_browser_is_chrome() and winctl.open_chrome(prefs.chosen_chrome_profile(), url)):
            webbrowser.open(url)
        time.sleep(0.8)
        return True

    def search(self, query: str, site: str) -> bool:
        return self._browse(SEARCH_URLS[site].format(urllib.parse.quote_plus(query)))

    def type_text(self, text: str) -> bool:
        cleaned = clean_dictation(text)
        if not cleaned:
            return False
        print(f"   typing: {cleaned}")
        return winctl.paste_text(cleaned)

    def ask_ai(self, app: str, question: str) -> bool:
        """Sends your question to ChatGPT or Claude. The reply is only read out if you ask for a summary."""
        question = question or (self.hear() if self.hear else "")
        if not question:
            return True
        if app not in AI_APPS or not self.open(app):
            return False
        time.sleep(NEW_CHAT_SETTLE)
        if winctl.front_exe() in winctl.BROWSERS:
            time.sleep(WEB_LOAD_WAIT)
        uia.focus_message_box()
        time.sleep(ASK_SETTLE)
        if not self.type_text(question):
            return False
        time.sleep(ASK_SETTLE)
        winctl.press_named("send")
        return True

    def _ai_app_in_front(self) -> str | None:
        exe, title = winctl.front_exe(), winctl.front_title()
        for name in AI_APPS:
            app = APPS[name]
            if exe in app.exes or (exe in winctl.BROWSERS and re.search(rf"\b{app.title_word}\b", title, re.I)):
                return name
        return None

    def _bring_up_ai_app(self) -> str | None:
        """The AI app you used most recently, or Claude if none is open."""
        for _hwnd, exe, _title in winctl.app_windows():
            for name in AI_APPS:
                if exe in APPS[name].exes:
                    return name if self.open(name) else None
        return "claude" if self.open("claude") else None

    def new_chat(self, app: str) -> bool:
        """Starts a new chat in the named app, or else in whichever AI app you're using."""
        if app:
            if app not in AI_APPS:
                print(f"   new chat works in Claude, ChatGPT and Codex, not {app!r}")
                return False
            if not self.open(app):
                return False
            target = app
        else:
            target = self._ai_app_in_front() or self._bring_up_ai_app()
            if not target:
                return False
        time.sleep(NEW_CHAT_SETTLE)
        if uia.click_first(NEW_CHAT_BUTTONS):
            print(f"   new chat in {target}")
        elif winctl.front_exe() in winctl.BROWSERS:
            return self._browse(APPS[target].url)
        else:
            winctl.press_combo("ctrl+n")
            print(f"   new chat in {target} with Ctrl+N")
        time.sleep(NEW_CHAT_SETTLE)
        return True

    def _copied_latest_reply(self, items: list) -> str:
        button = summary.lowest_copy_button(items)
        return uia.keeping_focus(lambda: winctl.text_copied_by(lambda: uia.activate(button))) if button else ""

    def _answer_on_page(self) -> str:
        """A browser can take a moment to expose a page's text, so look again before giving up."""
        for attempt in range(PAGE_READ_TRIES):
            if attempt:
                time.sleep(PAGE_READ_WAIT)
            blocks = summary.text_blocks(uia.scan())
            if text := summary.ai_overview(blocks) or summary.page_text(blocks):
                return text
        return ""

    def summarize(self) -> bool:
        """Reads a short summary of the latest chat reply, Google's AI answer, or the page on screen."""
        text = None
        if self._ai_app_in_front():
            items = uia.scan()
            text = self._copied_latest_reply(items) or summary.labelled_reply(items)
        short = summary.summarize_text(self._answer_on_page() if text is None else text)
        if not short:
            print("   could not find a response to summarize")
            return False
        print(f"   summary: {short}")
        self.speak(short)
        return True

    def erase(self, mode: str, value: str) -> bool:
        changes = {
            "words": lambda text: _without_last_words(text, int(value)),
            "sentence": _without_last_sentence,
            "named": lambda text: _without_word(text, value),
        }
        if winctl.edit_focused_text(changes[mode]):
            print("   text updated")
            return True
        print("   nothing to remove there")
        return False

    def _windows_of(self, spoken: str) -> list:
        target = canon(spoken)
        windows = winctl.app_windows()
        if target in APPS and APPS[target].exes:
            exes = set(APPS[target].exes)
            return [hwnd for hwnd, exe, _ in windows if exe in exes]
        wanted = re.sub(r"\W+", "", target)
        if len(wanted) < MIN_APP_NAME:
            return []
        return [
            hwnd for hwnd, exe, title in windows
            if exe not in NEVER_CONTROL and exe not in winctl.BROWSERS and (wanted in re.sub(r"\W+", "", exe[:-4]) or re.sub(r"\W+", "", title).lower() == wanted)
        ]

    def control_app(self, spoken: str, what: str) -> bool:
        windows = self._windows_of(spoken)
        if not windows:
            print(f"   {spoken} doesn't have an open window")
            return False
        if what == "maximize":
            winctl.maximize_window(windows[0])
        else:
            for hwnd in windows:
                (winctl.close_window if what == "close" else winctl.minimize_window)(hwnd)
        print(f"   {what}: {spoken} ({len(windows)} window(s))")
        return True

    def switch_tab(self, spoken: str, close: bool) -> bool:
        front = winctl.user32.GetForegroundWindow()
        browsers = [hwnd for hwnd, exe, _ in winctl.app_windows() if exe in winctl.BROWSERS and hwnd != front]
        for hwnd in [front, *browsers]:
            if not uia.best_tab(spoken, uia.scan(hwnd)):
                continue
            winctl.focus(hwnd)
            time.sleep(TAB_SETTLE)
            tab = uia.best_tab(spoken, uia.scan(hwnd))  # positions change if the window was minimized
            if not tab:
                continue
            print(f"   tab: {tab.name[:70]}")
            uia.activate(tab)
            if close:
                time.sleep(TAB_SETTLE)
                winctl.press_combo("ctrl+w")
            return True
        print(f"   no tab matching {spoken!r}")
        return False

    def clip(self, how: str, value: str) -> bool:
        history = self.clipboard_history
        if how == "list":
            recent = [re.sub(r"\s+", " ", item)[:CLIP_PREVIEW] for item in list(history.items)[:MAX_CLIPS_READ]]
            self.speak("; ".join(f"{index}: {text}" for index, text in enumerate(recent, 1)) if recent else "Your clipboard history is empty.")
            return True
        text = history.nth(int(value)) if how == "nth" else history.containing(value)
        if not text:
            self.speak("I don't have that in your clipboard history.")
            return True
        print(f"   pasting from history: {text[:60]}")
        return winctl.paste_text(text)

    def calculate(self, expression: str) -> bool:
        answer = calc.evaluate(expression)
        if answer is None:
            return False
        self.speak(f"That's {calc.spoken_number(answer)}.")
        return True

    def find_file(self, spoken: str, open_it: bool) -> bool:
        words, types = files.split_query(spoken)
        if not words and not types:
            return False
        found = files.search(words, types)
        if not found:
            self.speak("I couldn't find that file.")
            return True
        self._present_file(found[0], open_it, len(found) - 1)
        return True

    def open_latest(self, kind: str) -> bool:
        path = files.latest(kind)
        if not path:
            self.speak(f"I couldn't find a {kind}.")
            return True
        self._present_file(path, True, 0)
        return True

    def _present_file(self, path: str, open_it: bool, others: int) -> None:
        name = files.spoken_name(path)
        print(f"   file: {path}")
        if open_it and files.can_open(path):
            os.startfile(path)
            self.speak(f"Opening {name}.")
            return
        files.show_in_folder(path)
        if open_it:
            self.speak(f"For safety, I've shown {name} in its folder instead of opening it.")
        else:
            self.speak(f"Found {name}." + (f" {others} more match, and this is the newest." if others == 1 else f" {others} more match, and this is the newest." if others else ""))

    def run_terminal(self, name: str, project: str) -> bool:
        setup = terminal.load()
        command = terminal.find(name, project, setup)
        folder = setup.projects.get(project)
        if not command or not folder or not Path(folder).is_dir():
            print(f"   can't run {name!r} in {project!r}")
            return False
        if (command.ask or terminal.needs_confirmation(command.line)) and not self._confirm(f"Run {name} in {project}? Say yes."):
            print("   cancelled")
            return True
        print(f"   {project}> {command.line}")
        if command.in_terminal:
            winctl.open_terminal(f"{project} {name}", command.line, folder)
            return True
        try:
            result = subprocess.run(
                command.line, shell=True, cwd=folder, capture_output=True, encoding="utf-8", errors="replace",
                timeout=TERMINAL_TIMEOUT, creationflags=winctl.NO_WINDOW,
            )
        except subprocess.TimeoutExpired:
            self.speak("That's taking too long, so I stopped it.")
            return False
        output = result.stdout + result.stderr
        self.speak(terminal.spoken_result(command.line, result.returncode, output))
        return result.returncode == 0

    def routine(self, name: str) -> bool:
        steps = routines.load().get(name, [])
        failures = 0
        for kind, value in steps:
            print(f"   {name}: {kind} {value}")
            try:
                done = self._routine_step(kind, value)
            except Exception as error:
                print(f"   that step failed: {error!r}")
                done = False
            failures += not done
            time.sleep(ROUTINE_STEP_GAP)
        return bool(steps) and failures < len(steps)

    def _routine_step(self, kind: str, value: str) -> bool:
        if kind in ("cursor", "vscode"):
            if not Path(value).is_dir():
                print(f"   no such folder: {value}")
                return False
            return winctl.open_in_editor(kind, value)
        if kind == "chrome":
            parts = value.rsplit(" ", 1)
            url = parts[1] if len(parts) == 2 and parts[1].startswith("http") else ""
            profile = prefs.find_chrome_profile(parts[0] if url else value)
            return bool(profile) and winctl.open_chrome(profile, url)
        if kind == "url":
            return self._browse(value)
        if kind == "wait":
            time.sleep(float(value))
            return True
        return self.open(value)

    def remind(self, raw: str) -> bool:
        now = datetime.now()
        task, due = reminder_rules.parse_request(raw, now)
        if not due:
            self.speak("When should I remind you? For example, in 20 minutes.")
            return True
        self.reminders.add("reminder", task or "You asked me to remind you", due)
        self.speak(f"I'll remind you {reminder_rules.describe_time(due, now)}.")
        return True

    def timer(self, raw: str) -> bool:
        seconds = reminder_rules.parse_duration(raw)
        if not seconds:
            self.speak("How long should the timer run?")
            return True
        length = reminder_rules.describe_duration(seconds)
        self.reminders.add("timer", length, datetime.now() + timedelta(seconds=seconds))
        self.speak(f"Timer set for {length}.")
        return True

    def manage_reminders(self, what: str) -> bool:
        if what in ("cancel_timer", "cancel_reminder"):
            kind = "timer" if what == "cancel_timer" else "reminder"
            count = self.reminders.cancel(kind)
            self.speak(f"Cancelled {count} {kind}{'s' if count != 1 else ''}." if count else f"You have no {kind}s set.")
            return True
        now = datetime.now()
        items = self.reminders.upcoming()
        if not items:
            self.speak("You have nothing coming up.")
            return True
        parts = []
        for item in items[:MAX_REMINDERS_READ]:
            due = datetime.fromisoformat(item["due"])
            if item["kind"] == "timer":
                parts.append(f"a timer with {reminder_rules.describe_duration(max(1, round((due - now).total_seconds())))} left")
            else:
                parts.append(f"{item['text']} {reminder_rules.describe_time(due, now)}")
        self.speak("Coming up: " + "; ".join(parts) + ".")
        return True

    def pc_control(self, op: str, value: str) -> bool:
        if op in PC_CONFIRM:
            question, action = PC_CONFIRM[op]
            if not self._confirm(question):
                print("   cancelled")
                return True
            action()
            return True
        if op == "battery":
            self.speak(pc.battery_report())
            return True
        if op in ("wifi_on", "wifi_off", "bluetooth_on", "bluetooth_off"):
            kind, state = op.split("_")
            return pc.set_radio(kind, state == "on")
        if op == "task_manager":
            winctl.press_combo("ctrl+shift+esc")
            return True
        if op == "lock":
            pc.lock()
            return True
        if op == "sleep_pc":
            pc.sleep_pc()
            return True
        if op == "set_brightness":
            return pc.set_brightness(int(value))
        return pc.change_brightness(pc.BRIGHTNESS_STEP if op == "brightness_up" else -pc.BRIGHTNESS_STEP)

    def snap(self, app: str, side: str) -> bool:
        if app and not self.open(app):
            return False
        if app:
            time.sleep(SNAP_SETTLE)
        winctl.press_combo(f"cmd+{side}")
        print(f"   snapped to the {side}")
        return True

    def _confirm(self, question: str) -> bool:
        return bool(self.ask and self.ask(question))

    def message(self, who: str, app: str, body: str) -> bool:
        """Opens the chat by contact name. Nothing is sent without a spoken yes."""
        if not self.open(app):
            return False
        time.sleep(0.5)
        in_browser = winctl.front_exe() in winctl.BROWSERS
        if in_browser:
            time.sleep(WEB_LOAD_WAIT)
        desktop_keys, web_keys = MESSENGERS[app]
        keys = web_keys if in_browser else desktop_keys
        if keys:
            winctl.press_combo(keys)
        elif not uia.click_first(["Search"]):
            print(f"   could not find the search box in {app}")
            return False
        time.sleep(0.6)
        if not SEARCH_BOX.search(uia.focused_label()):
            # Without this, Enter below could post the contact's name into whichever chat is open.
            print(f"   stopped: {app}'s search box did not take focus, so nothing was typed")
            return False
        winctl.press_named("select_all")  # replaces any leftover search text
        winctl.paste_text(who)
        time.sleep(CONTACT_WAIT)
        winctl.press_combo("enter")
        time.sleep(0.8)
        if SEARCH_BOX.search(uia.focused_label()):
            print(f"   could not find a chat for {who} on {app}")
            return False
        print(f"   chat with {who} is open")
        body = body or (self.hear() if self.hear else "")
        if not body:
            return True
        if not self.type_text(body):
            return False
        return self._send_if_confirmed(f"Send this to {who} on {app}? Say yes to send.", "enter")

    def _send_if_confirmed(self, question: str, send_keys: str) -> bool:
        if self._confirm(question):
            winctl.press_combo(send_keys)
            print("   sent")
            self.say("sent")
        else:
            print("   not sent; your text is still in the box")
            self.say("not_sent")
        return True

    def _front_is_mail(self) -> bool:
        exe = winctl.front_exe()
        return exe in OUTLOOK_EXES or (exe in winctl.BROWSERS and bool(re.search(r"gmail|outlook", winctl.front_title(), re.I)))

    def mail(self, what: str, body: str) -> bool:
        if uia.click_first([MAIL_BUTTONS[what]]):
            print(f"   clicked {MAIL_BUTTONS[what]}")
        elif winctl.front_exe() in OUTLOOK_EXES:
            winctl.press_combo(OUTLOOK_KEYS[what])
        else:
            print(f"   could not see a {MAIL_BUTTONS[what]} button here")
            return False
        if not body:
            return True
        time.sleep(1.0)
        if not self.type_text(body):
            return False
        return self._send_if_confirmed("Send this reply? Say yes to send.", "ctrl+enter")

    def click(self, spoken: str) -> bool:
        item = uia.find(spoken)
        if not item and spoken.lower() == "send":
            return self.press("send")  # many chat boxes have only an icon, and Enter sends there
        if not item:
            print(f"   could not see {spoken!r} on screen")
            return False
        if (is_risky(spoken) or is_risky(item.name)) and not self._confirm(f"{item.name}. Are you sure? Say yes."):
            print("   cancelled")
            return True
        print(f"   clicking {item.name}")
        uia.activate(item)
        return True

    def click_nth(self, number: int, noun: str) -> bool:
        item = uia.nth(number, noun)
        if not item:
            print(f"   could not find {noun} number {number}")
            return False
        print(f"   opening {item.name[:70]}")
        uia.activate(item)
        return True

    def play(self, query: str, site: str) -> bool:
        if site == "spotify":
            return self._play_spotify(query)
        quoted = urllib.parse.quote_plus(query)
        video = _first_youtube_video(quoted)
        return self._browse(f"https://www.youtube.com/watch?v={video}" if video else SEARCH_URLS["youtube"].format(quoted))

    def _play_spotify(self, query: str) -> bool:
        if not self.start_menu.exact(APPS["spotify"].start_name):
            return self._browse(f"https://open.spotify.com/search/{urllib.parse.quote(query)}")
        os.startfile(f"spotify:search:{urllib.parse.quote(query)}")
        self._wait_and_focus(APPS["spotify"].exes)
        time.sleep(2.5)  # results take a moment to appear
        if item := uia.first_starting("Play "):
            print(f"   {item.name}")
            uia.activate(item)
        else:
            print("   showing the results; could not find a Play button")
        return True

    def calendar(self, spoken: str) -> bool:
        return self._browse(calendar_url(spoken, datetime.now()))

    def join(self, code: str, kind: str) -> bool:
        compact = re.sub(r"[\s-]+", "", code).lower()
        if compact.isdigit() and len(compact) >= 9 and kind != "meet":
            os.startfile(f"zoommtg://zoom.us/join?confno={compact}")
            return True
        if compact.isalpha() and len(compact) == 10:
            return self._browse(f"https://meet.google.com/{compact[:3]}-{compact[3:7]}-{compact[7:]}")
        if link := MEETING_LINK.search(winctl.read_clipboard_text()):
            return self._browse(link[0])
        if uia.click_first(JOIN_BUTTONS):
            print("   clicked Join")
            return True
        print("   no meeting code, no meeting link on the clipboard, and no Join button on screen")
        return False

    def agents(self, count: int, tool: str, folder_name: str) -> bool:
        command = AGENT_COMMANDS.get(tool)
        if not command or not shutil.which(command.split()[0]):
            print(f"   {tool} is not installed as a terminal command")
            return False
        folder = find_folder(folder_name) if folder_name else None
        if folder_name and not folder:
            print(f"   could not find a folder called {folder_name!r}")
            return False
        count = max(1, min(count, MAX_AGENTS))
        if shutil.which("wt.exe"):
            subprocess.Popen(winctl.terminal_tabs_args(count, tool, command, folder))
        else:
            for number in range(1, count + 1):
                winctl.open_terminal(f"{tool} {number}", command, folder)
        print(f"   started {count} {tool} agent(s)" + (f" in {folder}" if folder else ""))
        return True

    def open_folder(self, spoken: str) -> bool:
        folder = find_folder(spoken)
        if not folder:
            print(f"   could not find a folder called {spoken!r}")
            return False
        print(f"   opening {folder}")
        os.startfile(folder)
        return True

    def rename(self, spoken: str) -> bool:
        if winctl.front_exe() != "explorer.exe":
            print("   renaming only works with a file selected in File Explorer")
            return False
        name = BAD_NAME_CHARS.sub("", spoken).strip(" .")
        if not name:
            return False
        winctl.press_combo("f2")
        time.sleep(0.3)
        winctl.paste_text(name)
        winctl.press_combo("enter")
        print(f"   renamed to {name}")
        return True

    def set_volume(self, percent: int) -> bool:
        winctl.set_volume(max(0, min(percent, 100)))
        print(f"   volume {percent}%")
        return True


def _without_word(text: str, word: str) -> str:
    """Removes the most recent use of the word, which is usually the one you just noticed."""
    matches = list(re.finditer(rf"\b{re.escape(word.strip(' .,!?'))}\b", text, re.I))
    if not matches:
        return text
    last = matches[-1]
    joined = text[: last.start()].rstrip(" ") + " " + text[last.end() :].lstrip(" ")
    return re.sub(r"\s+([,.!?])", r"\1", joined).strip()


def _without_last_words(text: str, count: int) -> str:
    """Counts real words, so a final full stop isn't mistaken for one."""
    words = list(re.finditer(r"[\w'-]+", text))
    return text[: words[-count].start()].rstrip(" ,;:") if count < len(words) else ""


def _without_last_sentence(text: str) -> str:
    sentences = re.findall(r"[^.!?\n]+[.!?]*\s*|\n+", text)
    while sentences and not sentences[-1].strip():
        sentences.pop()
    return "".join(sentences[:-1]).rstrip()


def _first_youtube_video(quoted_query: str) -> str | None:
    request = urllib.request.Request(SEARCH_URLS["youtube"].format(quoted_query), headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(request, timeout=6) as response:
            page = response.read().decode("utf-8", "ignore")
    except OSError:
        return None
    match = re.search(r'"videoId":"([\w-]{11})"', page)
    return match[1] if match else None


def calendar_url(spoken: str, now: datetime) -> str:
    """A prefilled Google Calendar page; you press Save, or say "click save"."""
    title, start, minutes = parse_when(spoken, now)
    stamp = "%Y%m%dT%H%M%S"
    dates = f"{start.strftime(stamp)}/{(start + timedelta(minutes=minutes)).strftime(stamp)}"
    query = urllib.parse.urlencode({"action": "TEMPLATE", "text": title, "dates": dates})
    return f"https://calendar.google.com/calendar/render?{query}"


def find_folder(spoken: str) -> str | None:
    """Known folders first, then folders up to two levels under your home folder."""
    wanted = re.sub(r"[^a-z0-9]+", "", spoken.lower())
    home = Path.home()
    if spoken.lower() in FOLDERS:
        return str(home / spoken.title())
    if not wanted:
        return None
    candidates = []
    for parent in [home, *_subfolders(home)]:
        candidates += _subfolders(parent)
    squashed = {path: re.sub(r"[^a-z0-9]+", "", path.name.lower()) for path in candidates}
    exact = [path for path, name in squashed.items() if name == wanted]
    if exact:
        return str(min(exact, key=lambda p: len(p.parts)))
    near = [(SequenceMatcher(None, wanted, name).ratio(), path) for path, name in squashed.items()]
    near = [(ratio, path) for ratio, path in near if ratio >= 0.85]
    return str(max(near, key=lambda pair: pair[0])[1]) if near else None


def _subfolders(parent: Path) -> list[Path]:
    try:
        return [
            Path(entry.path) for entry in os.scandir(parent)
            if entry.is_dir(follow_symlinks=False) and not entry.name.startswith(".") and entry.name.lower() not in SKIP_DIRS
        ]
    except OSError:
        return []
