"""What Jarvis says, and how. Replies are short, because Jarvis can't hear you while it talks.

Your name is used only in the greeting; repeating it on every reply gets tiresome.
"""
import random
from datetime import datetime

from .commands import Action, canon

SPOKEN_NAMES = {
    "chatgpt": "ChatGPT", "vs code": "VS Code", "whatsapp": "WhatsApp", "youtube": "YouTube",
    "github": "GitHub", "linkedin": "LinkedIn", "opencode": "OpenCode",
}
COMMON_TARGETS = ("claude", "chatgpt", "codex", "chrome", "whatsapp", "gmail", "youtube", "spotify", "google")
PARTS_OF_DAY = ("morning", "afternoon", "evening")
GREETING_QUESTIONS = ("What are we going to do today?", "What's the plan today?", "What shall we work on?")

LINES = {
    "online": ["All systems online.", "Online and ready."],
    "returning": ["Yes?", "At your service.", "I'm listening.", "What can I do for you?"],
    "didnt_catch": ["I didn't catch that.", "Say that again?", "Sorry, could you repeat that?"],
    "failed": ["I'm afraid I couldn't do that.", "That didn't work.", "No luck with that one."],
    "farewell": ["Anytime.", "Always a pleasure.", "I'll be here."],
    "cancelled": ["Very well.", "As you wish."],
    "go_ahead": ["Go ahead.", "I'm listening.", "Ready when you are."],
    "sleep": ["Going quiet. Press the hotkey when you need me."],
    "waking": ["Back online.", "Right here."],
    "sent": ["Sent.", "Done. It's on its way."],
    "not_sent": ["Holding that. It hasn't been sent."],
    "status": ["All systems nominal.", "Running smoothly, thank you.", "Never better."],
    "confirm": ["Send this reply? Say yes to send."],
    "identity": ["I'm your personal assistant."],
}
ACKNOWLEDGE = {
    "open": ["Working on it.", "Right away.", "Opening {target}.", "On it."],
    "folder": ["Opening that folder.", "Right away."],
    "search": ["Searching now.", "Let me look that up.", "Working on it."],
    "play": ["Putting that on.", "Coming right up."],
    "mail": ["Right away.", "Working on it."],
    "calendar": ["Adding that to your calendar.", "Let me set that up."],
    "join": ["Getting you in.", "Joining now."],
    "new_chat": ["Starting a new chat.", "Fresh start."],
    "summarize": ["One moment.", "Let me read that."],
    "routine": ["Setting everything up.", "Getting your workspace ready."],
    "snap": ["On it."],
    "tab": ["Switching.", "On it."],
    "find": ["Looking for it."],
    "terminal": ["Running that."],
    "click": ["On it."],
    "nth": ["On it."],
}
PC_ACKNOWLEDGE = {
    "lock": "Locking the PC.", "sleep_pc": "Going to sleep.", "wifi_on": "Turning Wi-Fi on.", "wifi_off": "Turning Wi-Fi off.",
    "bluetooth_on": "Turning Bluetooth on.", "bluetooth_off": "Turning Bluetooth off.", "task_manager": "Opening Task Manager.",
    "brightness_up": "Brighter.", "brightness_down": "Dimmer.", "set_brightness": "Adjusting the brightness.",
}
SEND_ACKNOWLEDGE = ["Sent.", "Done.", "There it goes."]
CLEARED = "Cleared."
LEARNED = "Got it. I'll remember that."
NOTHING_TO_REPEAT = "There's nothing to repeat yet."
NOTHING_TO_CORRECT = "Tell me again what you'd like to open."


def _pick(lines: list[str], **values) -> str:
    return random.choice(lines).format(**values)


def _line(key: str) -> str:
    return _pick(LINES[key])


def spoken(target: str) -> str:
    key = canon(target)
    return SPOKEN_NAMES.get(key, key.title())


def part_of_day(hour: int) -> str:
    return "morning" if hour < 12 else "afternoon" if hour < 17 else "evening"


def salutation(name: str, now: datetime) -> str:
    return f"Good {part_of_day(now.hour)}, {name}."


def greeting(name: str, now: datetime) -> str:
    return f"{salutation(name, now)} {random.choice(GREETING_QUESTIONS)}"


def online() -> str:
    return _line("online")


def returning() -> str:
    return _line("returning")


def didnt_catch() -> str:
    return _line("didnt_catch")


def failed() -> str:
    return _line("failed")


def farewell() -> str:
    return _line("farewell")


def cancelled() -> str:
    return _line("cancelled")


def go_ahead() -> str:
    return _line("go_ahead")


def going_to_sleep() -> str:
    return _line("sleep")


def waking() -> str:
    return _line("waking")


def sent() -> str:
    return _line("sent")


def not_sent() -> str:
    return _line("not_sent")


def chat(topic: str, assistant: str, now: datetime) -> str:
    if topic == "time":
        return f"It's {now.strftime('%I:%M %p').lstrip('0')}."
    if topic == "date":
        return f"It's {now.strftime('%A, %B')} {now.day}."
    if topic == "identity":
        return f"I'm {assistant}. Your personal assistant."
    return _line("status")


def acknowledge(action: Action) -> str:
    """The reply as work begins. Quick key presses stay silent so Jarvis doesn't talk over you."""
    kind = action.kind
    if kind == "press":
        if action.arg == "clear_all":
            return CLEARED
        return _pick(SEND_ACKNOWLEDGE) if action.arg in ("send", "enter") else ""
    if kind == "pc":
        return PC_ACKNOWLEDGE.get(action.arg, "")
    if kind == "ask_ai":
        return f"Asking {spoken(action.site)}."
    if kind == "window":
        return f"Closing {spoken(action.arg)}." if action.site == "close" else "Done."
    if kind == "open":
        return _pick(ACKNOWLEDGE["open"], target=spoken(action.arg))
    if kind == "message":
        return f"Drafting that for {action.arg}."
    if kind == "agents":
        count = int(action.arg)
        return f"Spinning up {count} {spoken(action.site)} agent{'s' if count != 1 else ''}."
    if kind == "rename":
        return "Renaming that."
    if kind == "volume":
        return f"Volume to {action.arg}."
    return _pick(ACKNOWLEDGE[kind]) if kind in ACKNOWLEDGE else ""


def reminder_due(kind: str, text: str) -> str:
    return f"Time's up. Your {text} timer is done." if kind == "timer" else f"Reminder: {text}."


def all_lines(name: str) -> list[str]:
    """The usual replies, so they can be prepared ahead of time and play instantly."""
    lines = [CLEARED, LEARNED, NOTHING_TO_REPEAT, NOTHING_TO_CORRECT, "Asking Claude.", "Asking ChatGPT.", "Asking Codex.", *PC_ACKNOWLEDGE.values()]
    for part in PARTS_OF_DAY:
        lines.append(f"Good {part}, {name}.")
        lines += [f"Good {part}, {name}. {question}" for question in GREETING_QUESTIONS]
    for group in [*LINES.values(), *ACKNOWLEDGE.values(), SEND_ACKNOWLEDGE]:
        for template in group:
            if "{target}" in template:
                lines += [template.format(target=spoken(target)) for target in COMMON_TARGETS]
            else:
                lines.append(template)
    return list(dict.fromkeys(lines))
