"""Turns what was heard into actions. Rules only, so it costs almost no memory or CPU."""
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from difflib import SequenceMatcher

from . import calc
from .config import ALIASES, APPS, DEFAULT_MESSENGER, MESSENGERS, SEARCH_URLS, SITES, VOCABULARY
from .settings import DATA

LEARNED_FILE = DATA / "learned-names.json"
SOUND_MATCH = 0.8
MIN_SOUND_KEY = 3
MISHEARD_OPEN = re.compile(r"^(?:hopper|hoppen|oben|opened|opening|upon|open\s+up\s+a|op\s+in)\W+(?P<t>.+?)\W*$", re.I)
BARE_NAMES = {"claude", "chatgpt", "codex", "chrome", "cursor", "gmail", "youtube", "spotify", "whatsapp"}
ASK_AI = re.compile(r"^(?:ask|tell)\s+(?P<app>claude|clawed|cloud|closed|chat\s*gpt|chat\s*gbt|codex|codecs|cortex)\b[\s,:]*(?:(?:to|about|that|if|whether)\s+)?(?P<q>.*)$", re.I | re.S)


@dataclass(frozen=True)
class Action:
    # open, search, type, dictate, press, sleep, wake, message, mail, click, nth, play,
    # calendar, join, agents, folder, rename, volume, chat, new_chat, summarize, erase,
    # routine, remind, timer, reminders, pc, snap, repeat, correct, window, tab, clip, calc, find, latest, terminal, ask_ai
    kind: str
    arg: str = ""
    site: str = ""
    text: str = ""


STOP_NAME_SPELLINGS = "jarvish|javais|jarves|jarvees|travis|davis"
STOP_SOUNDS = {"stop", "stops", "stopped", "stopping", "stock", "stuck", "top", "shop", "step"}
STOP_LEAD_WORDS = {"hey", "hi", "ok", "okay", "please", "uh", "um", "a", "the"}
MIN_STOP_PHRASE, MAX_STOP_PHRASE = 2, 3
STOP_NAME_MATCH = 0.75
WAKE_LEAD_WORDS = {"hey", "hi", "hello", "ok", "okay", "yo"}
DEFAULT_WAKE = "jarvis"
WAKE_MATCH = 0.75  # how close a heard word must be to a custom wake name
_wake_core = DEFAULT_WAKE
_wake_word = re.compile("")
_stop_order = re.compile("")


def wake_core() -> str:
    return _wake_core.title()


def uses_default_wake() -> bool:
    return _wake_core.lower() == DEFAULT_WAKE


def set_wake_name(name: str) -> None:
    """Accepts "Friday" or "Hey Friday"; the greeting word is optional when you speak either way."""
    global _wake_core, _wake_word, _stop_order
    words = [word for word in re.findall(r"[\w']+", name)]
    while len(words) > 1 and words[0].lower() in WAKE_LEAD_WORDS:
        words.pop(0)
    _wake_core = " ".join(words) or DEFAULT_WAKE
    spoken = r"\W+".join(re.escape(word) for word in _wake_core.split())
    if uses_default_wake():
        spoken = "jarvis|jarvice|jervis|javis"
    _wake_word = re.compile(rf"^\W*(?:(?:hey|hi|hello|ok|okay|yo)\W+)?(?:{spoken})\b\W*", re.I)
    stop_names = f"{spoken}|{STOP_NAME_SPELLINGS}" if uses_default_wake() else spoken
    _stop_order = re.compile(rf"\b(?:{stop_names})\W+(?:please\W+)?(?:stop(?:\W+listening)?|cancel)\b(?!\W+(?:(?:the|my|all)\W+)?(?:timers?|reminders?))", re.I)


def is_stop_phrase(heard: str) -> bool:
    """A short phrase on its own like "Service stop.": something that sounds like the wake name, then stop.

    Only for whole phrases. Inside dictation, "customer service stop" must stay ordinary text.
    """
    words = [word for word in re.findall(r"[\w']+", heard.lower()) if word not in STOP_LEAD_WORDS]
    if words and words[-1] == "listening":
        words.pop()
    if not MIN_STOP_PHRASE <= len(words) <= MAX_STOP_PHRASE or words[-1] not in STOP_SOUNDS:
        return False
    said, wanted = sound_key("".join(words[:-1]))[1:], sound_key(_wake_core)[1:]
    return bool(said and wanted) and SequenceMatcher(None, said, wanted).ratio() >= STOP_NAME_MATCH


def says_stop(heard: str) -> bool:
    """ "Jarvis stop" anywhere in what was heard, even in the middle of dictation."""
    return bool(_stop_order.search(heard))


def strip_wake(heard: str) -> str:
    return _wake_word.sub("", heard.strip(), count=1).strip()


def text_after_wake_name(heard: str) -> str | None:
    """What follows a custom wake name, tolerant of mishearing; None if the phrase doesn't start with it."""
    tokens = list(re.finditer(r"[\w']+", heard))
    if tokens and len(tokens) > 1 and tokens[0][0].lower() in WAKE_LEAD_WORDS:
        tokens = tokens[1:]
    size = len(_wake_core.split())
    if len(tokens) < size:
        return None
    said = "".join(token[0] for token in tokens[:size]).lower()
    wanted = _wake_core.replace(" ", "").lower()
    if SequenceMatcher(None, said, wanted).ratio() < WAKE_MATCH:
        return None
    return heard[tokens[size - 1].end() :].lstrip(" ,.!?:;-")


LEAD = re.compile(
    r"^(?:(?:hey|hi|okay|ok|so|now|then|please|kindly|just|and|uh+|um+|umm+|hmm+|erm)\W+"
    r"|(?:can|could|would|will) you(?: please)?\W+"
    r"|i (?:want|need) (?:you )?to\W+|i'd like (?:you )?to\W+|go ahead and\W+)+",
    re.I,
)
TRAIL = re.compile(r"(?:[\s,]+(?:please|for me|thanks|thank you|now|yaar))+$", re.I)
JOIN = re.compile(r"\s*,?\s+(?:and then|after that|then|and)\s+|\s*[,;.]\s+", re.I)

TYPE = re.compile(r"^(?:type|dictate|write down)\b[\s,:.\-]*(.*)$", re.I | re.S)
TYPE_MISHEARD = re.compile(r"^(?:tie|thai|tape|tight|typed|types)\W*$", re.I)
SEND_AT_END = re.compile(
    r"\s*,?\s*\b(?:(?:and(?: then)?|then)\s+(?:(?:press|hit|click)\s+)?(?:send|submit|enter)(?:\s+(?:it|that))?"
    r"|(?:press|hit|click)\s+enter|send\s+it)[.!]?$",
    re.I,
)
SEND_AFTER_SENTENCE = re.compile(r"(?<=[.!?,])\s*(?:send it|send|submit|enter)[.!]?$", re.I)
# Only counted right after typing, when "send it" is the obvious next step. These all come from real sessions.
SEND_SOUNDS = {"send", "sends", "sent", "sense", "since", "scent", "cents", "sand", "same", "end", "inter", "center", "enter", "ender", "sending", "sand it"}
SCRATCH_THAT = re.compile(r"[\s,]*\bscratch that\b[\s,.!?]*", re.I)
MAX_SEND_SOUNDS = 2
SEND_FILLER = {
    "okay", "ok", "uh", "um", "now", "please", "so", "yes", "yeah", "good", "seems", "fine", "jarvis", "hey", "and", "then",
    "just", "it", "that", "this", "in",
}

ENGINES = "|".join(sorted(SEARCH_URLS, key=len, reverse=True))
SEARCH_RULES = [
    (re.compile(rf"^(?:search|look up|find)\s+(?:on\s+|in\s+)?(?P<site>{ENGINES})\s+(?:for\s+)?(?P<q>.+)$", re.I)),
    (re.compile(rf"^(?:search(?: for)?|look up|look for|find|google)\s+(?P<q>.+?)\s+(?:on|in)\s+(?P<site>{ENGINES})$", re.I)),
    (re.compile(r"^(?:search(?: for)?|look up|look for|google)\s+(?P<q>.+)$", re.I)),
    (re.compile(rf"^(?P<site>{ENGINES})\s+(?:pe|par|mein|me)\s+(?P<q>.+?)\s+(?:search karo|search kar do|dhundo|dhoondo)$", re.I)),
    (re.compile(r"^(?P<q>.+?)\s+(?:search karo|search kar do|google karo|dhundo|dhoondo)$", re.I)),
]

OPEN_RULES = [
    re.compile(
        r"^(?:(?:(?:go (?:to |and )?)?(?:open up|open|launch|start|show me|show|switch over to|switch to|bring up|pull up))"
        r"|go to|go on|take me to|head to)\s+(?:the\s+|my\s+)?(?P<t>.+?)"
        r"(?:\s+(?:app|application|website|site|window))?$",
        re.I,
    ),
    re.compile(r"^(?P<t>.+?)\s+(?:kholo|khol do|open karo|open kar do)$", re.I),
]

PHRASES = {
    "send": (
        "send it|send|send that|send this|sent it|send it now|submit|submit it|bhej do|bhejo"
        "|send a message|send the message|send this message|send message|send the prompt|send this prompt|send prompt"
    ),
    "enter": (
        "enter|press enter|hit enter|new line|enter it|tap enter|click enter|click on enter|click the enter|click enter key"
        "|click the enter key|click the enter button|click enter button|press the enter|press enter key|press the enter key"
        "|press the enter button|hit the enter|hit enter key|hit the enter key"
        "|ender|click ender|click on ender|press ender|hit ender|click inter|press inter|hit inter"
    ),
    "new_tab": "new tab|open a new tab|open new tab",
    "close_tab": "close tab|close this tab|close the tab|tab band karo",
    "next_tab": "next tab",
    "prev_tab": "previous tab|last tab|prev tab",
    "back": "go back|back|take me back|peeche jao",
    "forward": "go forward|forward",
    "reload": "reload|refresh|reload the page|refresh the page|reload this page|refresh this page",
    "scroll_down": "scroll down|scroll|go down|neeche jao",
    "scroll_up": "scroll up|go up|upar jao",
    "top": "go to the top|scroll to the top|top of the page",
    "bottom": "go to the bottom|scroll to the bottom|bottom of the page",
    "copy": "copy|copy that|copy this",
    "paste": "paste|paste that|paste it",
    "cut": "cut|cut that",
    "select_all": "select all|select everything",
    "undo": "undo|undo that|take that back|remove that|remove what i typed|remove the last thing",
    "clear_all": (
        "remove all text|remove all the text|remove the text|remove all|remove everything|clear all|clear all text"
        "|clear all the text|clear the text|clear text|clear everything|delete all|delete all text|delete all the text"
        "|delete everything|delete the text|erase all|erase all text|erase everything|sab hata do|sab delete karo"
    ),
    "redo": "redo|redo that",
    "delete": "delete that|delete this",
    "escape": "escape|press escape",
    "minimize": "minimize|minimize this|minimize this window|minimise|minimise this|minimise this window",
    "maximize": "maximize|maximize this|maximize this window|maximise|maximise this|maximise this window",
    "close_window": "close this window|close the window|close this app|close this application|close it|close app",
    "desktop": "show desktop|show the desktop|go to desktop|minimize all|minimize everything|minimize all windows|minimise all|minimise everything",
    "switch_app": "switch app|switch apps|previous app|last app",
    "screenshot": "take a screenshot|screenshot|take screenshot|screenshot lo",
    "play_pause": "play|pause|resume|play music|pause music|pause the music|play the music",
    "next_track": "next song|next track|skip song|skip this song|agla gaana",
    "prev_track": "previous song|previous track|pichla gaana",
    "volume_up": "volume up|turn it up|increase volume|increase the volume|louder|awaaz badhao|awaz badhao",
    "volume_down": "volume down|turn it down|decrease volume|decrease the volume|quieter|awaaz kam karo|awaz kam karo",
    "mute": "mute|unmute|mute the sound",
}
PRESS = {phrase: name for name, phrases in PHRASES.items() for phrase in phrases.split("|")}
SLEEP = {"go to sleep", "sleep"}
WAKE_UP = {"wake up", "start listening"}
NOTHING = {"cancel", "cancel that", "never mind", "nevermind", "forget it", "stop", "stop it", "stop listening"}
DISMISS = {
    "thanks", "thank you", "thanks a lot", "thank you so much", "ok thanks", "okay thanks", "okay thank you",
    "thats all", "that is all", "that will be all", "thatll be all", "nothing else", "goodbye", "bye", "bye bye", "dismissed",
}
CHAT = {
    "time": "what time is it|whats the time|what is the time|tell me the time|time batao|kitna baja hai",
    "date": "whats the date|what is the date|whats todays date|what day is it|todays date|aaj kya date hai",
    "status": "how are you|how are you doing|status report|whats up|kaise ho",
    "identity": "who are you|what is your name|whats your name",
}
CHAT_PHRASES = {phrase: topic for topic, phrases in CHAT.items() for phrase in phrases.split("|")}
YES = {
    "yes", "yeah", "yep", "yes please", "yes send", "yes send it", "yes do it", "send", "send it", "do it",
    "go ahead", "confirm", "okay", "ok", "haan", "han", "ha", "haan bhej do", "bhej do",
}

MESSENGER_NAMES = "|".join(sorted({*MESSENGERS, "whats app"}, key=len, reverse=True))
_SAY = r"(?:saying|that|to say|and say)\b[\s,:]*"
_MSG = r"(?:send (?:a |an )?)?(?:message|msg|text|ping|dm)(?: to)?"
_ENDS = r"[.!?]*$"
MESSAGE_RULES = [
    re.compile(rf"^{_MSG}\s+(?P<who>.+?)[\s,]+(?:on\s+(?P<app>{MESSENGER_NAMES})[\s,]+)?{_SAY}(?P<body>.+?)(?:\s+on\s+(?P<app2>{MESSENGER_NAMES})[.!?]*)?$", re.I | re.S),
    re.compile(rf"^{_MSG}\s+(?P<who>.+?)\s+on\s+(?P<app>{MESSENGER_NAMES}){_ENDS}", re.I),
    re.compile(rf"^send\s+(?P<body>.+?)\s+to\s+(?P<who>.+?)\s+on\s+(?P<app>{MESSENGER_NAMES}){_ENDS}", re.I | re.S),
    re.compile(rf"^(?P<app>{MESSENGER_NAMES})\s+(?P<who>.+?)(?:[\s,]+{_SAY}(?P<body>.+))?{_ENDS}", re.I | re.S),
    re.compile(rf"^tell\s+(?P<who>.+?)\s+(?:on\s+(?P<app>{MESSENGER_NAMES})\s+)?(?:that|to)\s+(?P<body>.+)$", re.I | re.S),
    re.compile(rf"^(?P<who>.+?)\s+ko\s+(?:(?P<app>{MESSENGER_NAMES})\s+(?:pe|par)\s+)?(?:message\s+|msg\s+)?(?:bhejo|bhej do|bolo|kaho)[\s,:]*(?P<body>.*)$", re.I | re.S),
    re.compile(rf"^{_MSG}\s+(?P<who>[\w ]{{1,40}}?){_ENDS}", re.I),
]
REPLY = re.compile(
    rf"^(?P<what>reply to all|reply all|reply|respond)(?:\s+to\s+(?:this|that|the)(?:\s+(?:email|mail|message))?)?"
    rf"(?:[\s,]+(?:saying|that|with)\b[\s,:]*(?P<body>.+))?{_ENDS}",
    re.I | re.S,
)
MAIL_PHRASES = {
    "forward this": "forward", "forward this email": "forward", "forward this mail": "forward",
    "forward email": "forward", "forward the email": "forward",
    "archive": "archive", "archive this": "archive", "archive this email": "archive",
    "archive this mail": "archive", "archive email": "archive", "archive the email": "archive",
}

NUMBER_WORDS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
}
ORDINALS = {
    "first": 1, "1st": 1, "second": 2, "2nd": 2, "third": 3, "3rd": 3, "fourth": 4, "4th": 4, "fifth": 5, "5th": 5,
    "sixth": 6, "6th": 6, "seventh": 7, "7th": 7, "eighth": 8, "8th": 8, "ninth": 9, "9th": 9, "tenth": 10, "10th": 10,
}
_ORD = "|".join(ORDINALS)
_NOUN = "result|link|email|mail|message|chat|conversation|video|song|item|row|option|one"
NTH_RULES = [
    re.compile(rf"^(?:(?:open|click(?: on)?|select|choose|go to|show(?: me)?|play)\s+)?(?:the\s+)?(?P<o>{_ORD})\s+(?P<n>{_NOUN})$", re.I),
    re.compile(rf"^(?:(?:open|click(?: on)?|select|choose|go to|show(?: me)?|play)\s+)?(?:the\s+)?(?P<n>{_NOUN})\s+number\s+(?P<o>\d{{1,2}}|{'|'.join(k for k in NUMBER_WORDS if len(k) > 2)})$", re.I),
]
CLICK_RULES = [
    re.compile(r"^(?:click(?: on)?(?: karo)?|tap(?: on)?|press|hit|select|choose)\s+(?:on\s+)?(?:the\s+)?(?P<n>.+?)(?:\s+(?:button|link|tab|icon|option|menu))?$", re.I),
    re.compile(r"^(?P<n>.+?)\s+(?:pe|par)\s+click\s+karo$", re.I),
]
PLAY_RULES = [
    re.compile(r"^(?:play|chalao|bajao|lagao|laga do)\s+(?P<q>.+?)(?:\s+(?:on|in|pe|par)\s+(?P<site>spotify|youtube|you tube))?$", re.I),
    re.compile(r"^(?P<q>.+?)(?:\s+(?P<site>spotify|youtube|you tube)\s+(?:pe|par))?\s+(?:bajao|chalao|lagao|laga do|play karo)$", re.I),
]
CALENDAR_RULES = [
    re.compile(r"^(?:schedule|book|set up|create|add|plan|fix)\s+(?:(?:a|an|the|new|calendar)\s+)*(?P<t>(?:meeting|event|call|appointment)\b.*)$", re.I),
    re.compile(r"^add\s+(?P<t>.+?)\s+to\s+(?:my\s+)?calendar(?P<w>\s+.+)?$", re.I),
]
JOIN_MEETING = re.compile(
    r"^join\s+(?:(?:my|the|next)\s+)*(?:(?P<kind>google meet|meet|zoom)\b\s*)?(?:(?:meeting|call)\b\s*)?(?:(?:id|code|number)\b\s*)?(?P<code>[\w\s-]*)$",
    re.I,
)
AGENTS = re.compile(
    r"^(?:start|open|launch|spawn|run|create)\s+(?P<n>\d{1,2}|a|an|one|two|three|four|five|six|seven|eight)\s+(?P<tool>.+?)\s+"
    r"(?:agents?|terminals?|sessions?|instances?)(?:\s+in\s+(?:the\s+|my\s+)?(?P<f>.+?)(?:\s+folder)?)?$",
    re.I,
)
NEW_CHAT = re.compile(
    r"^(?:(?:open|start|create|begin|make|launch|go to)\s+)?(?:(?P<before>claude|clawed|cloud|chat gpt|chatgpt|codex|codecs)\s+)?"
    r"(?:(?:a|the|another)\s+)?(?:new|fresh)\s+(?:chat|chart|session|conversation|thread)(?:\s+(?:in|on|with|for)\s+(?P<after>.+?))?$",
    re.I,
)
SUMMARIZE = re.compile(
    r"^(?:summari[sz]ed?(?:\s+.*)?|(?:give|tell|read)(?:\s+me)?\s+(?:a\s+|the\s+)?summary(?:\s+.*)?|what(?:'s| is)\s+the\s+summary"
    r"|what\s+(?:did|does)\s+it\s+say|(?:read|tell)(?:\s+me)?\s+the\s+(?:response|answer))$",
    re.I,
)
ERASE_WORDS = re.compile(
    r"^(?:remove|delete|erase)\s+(?:(?:the\s+)?last\s+(?:(?P<n>\d{1,2}|two|three|four|five|six|seven|eight|nine|ten)\s+)?words?|that\s+word)$",
    re.I,
)
ERASE_SENTENCE = re.compile(r"^(?:remove|delete|erase)\s+(?:the\s+)?last\s+(?:sentence|line)$", re.I)
ERASE_NAMED_WORD = re.compile(r"^(?:remove|delete|erase)\s+(?:the\s+)?word\s+(?P<w>.+)$", re.I)
REPEAT_PHRASES = {"do that again", "do it again", "repeat that", "repeat", "again", "one more time", "same again", "do the same again"}
CORRECTION = re.compile(r"^(?:(?:no|not that|sorry|nope|wrong)\W+)*i\s+(?:meant|mean|said)\s+(?:to\s+)?(?:open\s+)?(?P<m>.+)$", re.I)
TEACH_NAME = re.compile(r"^when\s+i\s+say\s+(?P<h>.+?),?\s+i\s+mean\s+(?P<m>.+)$", re.I)
WINDOW_APP = re.compile(
    r"^(?P<v>close|quit|exit|minimi[sz]e|maximi[sz]e)\s+(?:the\s+|my\s+)?(?P<app>.+?)(?:\s+(?:app|application|window|windows))?$", re.I,
)
SWITCH_TAB = re.compile(r"^(?:go\s+to|switch\s+to|open|show(?:\s+me)?|take\s+me\s+to|jump\s+to)\s+(?:the\s+|my\s+)?(?P<t>.+?)\s+tab$", re.I)
CLOSE_TAB = re.compile(r"^close\s+(?:the\s+|my\s+)?(?P<t>.+?)\s+tab$", re.I)
_CLIP_ORD = "|".join(ORDINALS)
PASTE_NTH = re.compile(
    rf"^paste\s+(?:the\s+|my\s+)?(?P<o>{_CLIP_ORD}|last|latest|previous)(?:\s+(?:last|latest|recent))?(?:\s+(?:thing|item|one|copy|clip|text))?"
    r"(?:\s+(?:i\s+copied|from\s+(?:the\s+)?clipboard(?:\s+history)?))?$",
    re.I,
)
PASTE_NUMBER = re.compile(r"^paste\s+(?:from\s+)?(?:the\s+|my\s+)?(?:clipboard|copy|clip|item|number)(?:\s+history)?(?:\s+(?:item|number))*\s+(?P<n>\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten)$", re.I)
PASTE_ABOUT = re.compile(r"^paste\s+(?:the\s+)?(?:one|thing|text|copy)\s+(?:about|with|containing|that\s+says|saying)\s+(?P<q>.+)$", re.I)
CLIP_LIST = {"clipboard history", "show clipboard history", "read clipboard history", "open clipboard history", "whats in my clipboard", "whats on my clipboard"}
CALCULATE = re.compile(r"^(?:calculate|compute|solve|how\s+much\s+is|what(?:'s|s)?(?:\s+is)?)\s+(?P<e>.+)$", re.I)
ARITHMETIC_FORM = re.compile(r"^(?:add|subtract|multiply|divide|\d|square\s+root)", re.I)
LATEST_FILE = re.compile(r"^(?:open|show(?:\s+me)?)\s+(?:the\s+|my\s+)?(?:latest|last|newest|most\s+recent|recent)\s+(?P<k>download|downloaded\s+file|screenshot)$", re.I)
OPEN_NAMED_FILE = re.compile(r"^open\s+(?:the\s+|my\s+)?(?P<q>.+?)\s+file$", re.I)
OPEN_KIND_FILE = re.compile(r"^open\s+(?:the\s+|my\s+)?(?P<q>.+?\s+(?:pdf|document|spreadsheet|presentation|photo|image|video|csv))$", re.I)
FIND_FILE = re.compile(r"^(?:find|locate|where\s+is|where's)\s+(?:the\s+|my\s+|a\s+)?(?P<q>.+?)$", re.I)
REMIND = re.compile(r"^(?:remind me|set (?:a |an )?reminder|add (?:a |an )?reminder|create (?:a |an )?reminder)\b[\s,:]*(?P<r>.*)$", re.I | re.S)
TIMER = re.compile(
    r"^(?:(?:set|start|put|create)\s+)?(?:(?:a|an|the|my)\s+)?(?:timer\s+(?:for\s+|of\s+)?(?P<after>.+)|(?P<before>.+?)\s+timer)$",
    re.I,
)
REMINDER_PHRASES = {
    "cancel timer": "cancel_timer", "cancel the timer": "cancel_timer", "cancel my timer": "cancel_timer", "stop timer": "cancel_timer",
    "stop the timer": "cancel_timer", "cancel all timers": "cancel_timer", "cancel timers": "cancel_timer",
    "cancel reminder": "cancel_reminder", "cancel the reminder": "cancel_reminder", "cancel my reminder": "cancel_reminder",
    "cancel reminders": "cancel_reminder", "cancel my reminders": "cancel_reminder", "cancel all reminders": "cancel_reminder",
    "clear reminders": "cancel_reminder", "clear all reminders": "cancel_reminder", "delete all reminders": "cancel_reminder",
    "what are my reminders": "list", "whats on my reminders": "list", "list reminders": "list", "list my reminders": "list",
    "show reminders": "list", "show my reminders": "list", "any reminders": "list", "do i have any reminders": "list",
    "how much time is left": "list", "how much time left": "list", "time left": "list", "check timer": "list", "check the timer": "list",
}
PC_GROUPS = {
    "lock": "lock my pc|lock the pc|lock pc|lock computer|lock my computer|lock the computer|lock my laptop|lock the laptop|lock the screen|lock screen|lock my screen",
    "sleep_pc": "put the pc to sleep|put my pc to sleep|put the computer to sleep|put my computer to sleep|put the laptop to sleep|put my laptop to sleep|sleep my pc|sleep the pc",
    "shut_down": "shut down|shutdown|shut down the pc|shut down my pc|shut down the computer|shut down my computer|shut down the laptop|shut down my laptop|turn off the pc|turn off my pc|turn off the computer|turn off my computer|turn off the laptop|turn off my laptop|power off",
    "restart": "restart|restart the pc|restart my pc|restart the computer|restart my computer|restart the laptop|restart my laptop|reboot",
    "sign_out": "sign out of windows|log out of windows|sign out of the pc",
    "battery": "battery|battery level|battery status|battery percentage|whats my battery|whats the battery|whats the battery level|how much battery|how much battery is left|how much battery do i have|how much charge is left",
    "brightness_up": "brightness up|increase brightness|increase the brightness|raise brightness|raise the brightness|brighter|make it brighter|make the screen brighter",
    "brightness_down": "brightness down|decrease brightness|decrease the brightness|reduce brightness|reduce the brightness|lower brightness|lower the brightness|dimmer|dim the screen|make it dimmer",
    "task_manager": "open task manager|task manager|show task manager",
}
PC_PHRASES = {phrase: op for op, phrases in PC_GROUPS.items() for phrase in phrases.split("|")}
SET_BRIGHTNESS = re.compile(r"^(?:set\s+)?(?:the\s+)?brightness\s+(?:to\s+|at\s+)?(?P<n>\d{1,3})(?:\s*(?:percent|%))?$", re.I)
RADIO_RULES = [
    re.compile(r"^(?:turn|switch)\s+(?P<s>on|off)\s+(?:the\s+|my\s+)?(?P<r>wifi|wi fi|bluetooth)$"),
    re.compile(r"^(?:turn|switch)\s+(?:the\s+|my\s+)?(?P<r>wifi|wi fi|bluetooth)\s+(?P<s>on|off)$"),
    re.compile(r"^(?P<r>wifi|wi fi|bluetooth)\s+(?P<s>on|off)$"),
]
SNAP_WINDOW = re.compile(r"^(?:snap|move|put)\s+(?:(?:this|the)\s+)?(?:window\s+|it\s+)?(?:to\s+|on\s+)?(?:the\s+)?(?P<s>left|right)(?:\s+side)?$", re.I)
SNAP_APP = re.compile(r"^(?:snap|move|put)\s+(?P<app>.+?)\s+(?:to|on)\s+(?:the\s+)?(?P<s>left|right)(?:\s+side)?$", re.I)
FOLDER_RULES = [
    re.compile(r"^(?:open|go to|show(?: me)?|take me to)\s+(?:the\s+|my\s+)?(?P<n>.+?)\s+folder$", re.I),
    re.compile(r"^(?P<n>.+?)\s+folder\s+(?:kholo|khol do|open karo)$", re.I),
]
RENAME = re.compile(r"^rename\s+(?:(?:this|it|that|the|file|folder|item)\s+)*(?:to|as)\s+(?P<n>.+)$", re.I)
SET_VOLUME = re.compile(r"^(?:set\s+(?:the\s+)?)?volume\s+(?:to\s+|at\s+)?(?P<n>\d{1,3})(?:\s*(?:percent|%))?$", re.I)
RISKY = re.compile(
    r"\b(?:delete|remove|pay|payment|buy|purchase|order|checkout|check out|transfer|sign out|signout|log out|logout|unsubscribe|uninstall|format)\b",
    re.I,
)


def sound_key(word: str) -> str:
    """A rough spelling of how a word sounds, so "clawed", "cloud" and "Claude" compare as equal."""
    text = re.sub(r"c(?=[eiy])", "s", re.sub(r"[^a-z]", "", word.lower()))  # the soft c in "service"
    for written, sound in (("ph", "f"), ("th", "t"), ("ch", "k"), ("ck", "k"), ("c", "k"), ("q", "k"), ("x", "ks"), ("z", "s"), ("d", "t"), ("b", "p"), ("v", "f"), ("g", "k")):
        text = text.replace(written, sound)
    consonants = re.sub(r"[aeiouyhw]", "", text)
    return re.sub(r"(.)\1+", r"\1", consonants)


def sounds_like(heard: str, names) -> str | None:
    """The one known name that sounds like what was heard, or None if nothing is close or it's a tie."""
    key = sound_key(heard)
    if len(key) < MIN_SOUND_KEY:
        return None
    scored = []
    for name in names:
        other = sound_key(name)
        if other and other[0] == key[0]:
            scored.append((SequenceMatcher(None, key, other).ratio(), name))
    scored.sort(reverse=True)
    if not scored or scored[0][0] < SOUND_MATCH or (len(scored) > 1 and scored[1][0] == scored[0][0]):
        return None
    return scored[0][1]


def repair_verb(text: str) -> str:
    """ "Hopper Google" is "Open Google": only when what follows is a name Jarvis knows."""
    match = MISHEARD_OPEN.match(text)
    if match and canon(match["t"]) in {*APPS, *SITES}:
        return f"Open {match['t']}"
    return text


def _plain_name(name: str) -> str:
    return re.sub(r"[^\w\s'.-]", "", name).strip(" .").lower()


def canon(name: str) -> str:
    name = _plain_name(name)
    return _learned().get(name) or ALIASES.get(name, name)


_learned_cache: dict | None = None


def _learned() -> dict:
    global _learned_cache
    if _learned_cache is None:
        try:
            _learned_cache = json.loads(LEARNED_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _learned_cache = {}
    return _learned_cache


def learn_name(heard: str, meant: str) -> str:
    """Remembers that a misheard name means something else, and returns the corrected name."""
    corrected = canon(meant)
    _learned()[_plain_name(heard)] = corrected
    DATA.mkdir(parents=True, exist_ok=True)
    LEARNED_FILE.write_text(json.dumps(_learned(), indent=2), encoding="utf-8")
    return corrected


def is_risky(text: str) -> bool:
    return bool(RISKY.search(text))


def is_yes(heard: str) -> bool:
    return re.sub(r"[^\w\s]", "", heard).strip().lower() in YES


def _strip_lead(text: str) -> str:
    return LEAD.sub("", text.strip(" \t\r\n,;:")).strip()


def _number(word: str) -> int:
    word = word.lower()
    return int(word) if word.isdigit() else ORDINALS.get(word) or NUMBER_WORDS[word]


def _feature(core: str, phrase: str) -> Action | None:
    if phrase in MAIL_PHRASES:
        return Action("mail", MAIL_PHRASES[phrase])
    if phrase in REPEAT_PHRASES:
        return Action("repeat")
    if match := TEACH_NAME.match(core):
        return Action("correct", match["m"].strip(), match["h"].strip())
    if match := CORRECTION.match(core):
        return Action("correct", match["m"].strip())
    if match := CLOSE_TAB.match(core):
        return Action("tab", match["t"].strip(), "close")
    if match := SWITCH_TAB.match(core):
        return Action("tab", match["t"].strip(), "go")
    if match := WINDOW_APP.match(core):
        verb = match["v"].lower()
        return Action("window", match["app"].strip(), "minimize" if verb.startswith("minimi") else "maximize" if verb.startswith("maximi") else "close")
    if phrase in CLIP_LIST:
        return Action("clip", site="list")
    if match := PASTE_ABOUT.match(core):
        return Action("clip", match["q"].strip(), "about")
    if match := PASTE_NUMBER.match(core):
        return Action("clip", str(_number(match["n"])), "nth")
    if match := PASTE_NTH.match(core):
        word = match["o"].lower()
        return Action("clip", str(1 if word in ("last", "latest") else 2 if word == "previous" else ORDINALS[word]), "nth")
    if match := LATEST_FILE.match(core):
        return Action("latest", "screenshot" if "screenshot" in match["k"].lower() else "download")
    if match := OPEN_NAMED_FILE.match(core) or OPEN_KIND_FILE.match(core):
        return Action("find", match["q"].strip(), "open")
    expression = match["e"] if (match := CALCULATE.match(core)) else core if ARITHMETIC_FORM.match(core) else ""
    if expression and calc.evaluate(expression) is not None:
        return Action("calc", expression)
    if phrase in REMINDER_PHRASES:
        return Action("reminders", REMINDER_PHRASES[phrase])
    if match := REMIND.match(core):
        return Action("remind", match["r"].strip())
    if match := TIMER.match(core):
        return Action("timer", (match["after"] or match["before"]).strip())
    if phrase in PC_PHRASES:
        return Action("pc", PC_PHRASES[phrase])
    if match := SET_BRIGHTNESS.match(core):
        return Action("pc", "set_brightness", match["n"])
    for rule in RADIO_RULES:
        if match := rule.match(phrase):
            return Action("pc", f"{match['r'].replace(' ', '')}_{match['s']}")
    if match := SNAP_WINDOW.match(core):
        return Action("snap", "", match["s"].lower())
    if match := SNAP_APP.match(core):
        return Action("snap", match["app"].strip(), match["s"].lower())
    if SUMMARIZE.match(core):
        return Action("summarize")
    if match := ERASE_WORDS.match(core):
        return Action("erase", str(_number(match["n"] or "1")), "words")
    if ERASE_SENTENCE.match(core):
        return Action("erase", site="sentence")
    if match := ERASE_NAMED_WORD.match(core):
        return Action("erase", match["w"].strip(), "named")
    if match := NEW_CHAT.match(core):
        app = match["before"] or match["after"]
        return Action("new_chat", canon(app) if app else "")
    if match := AGENTS.match(core):
        return Action("agents", str(_number(match["n"])), canon(match["tool"]), (match["f"] or "").strip())
    if match := JOIN_MEETING.match(core):
        return Action("join", (match["code"] or "").strip(), (match["kind"] or "").lower())
    for rule in CALENDAR_RULES:
        if match := rule.match(core):
            groups = match.groupdict()
            return Action("calendar", (groups["t"] + (groups.get("w") or "")).strip())
    for rule in NTH_RULES:
        if match := rule.match(core):
            return Action("nth", str(_number(match["o"])), match["n"].lower())
    if match := RENAME.match(core):
        return Action("rename", match["n"].strip())
    if match := SET_VOLUME.match(core):
        return Action("volume", match["n"])
    for rule in CLICK_RULES:
        if match := rule.match(core):
            return Action("click", match["n"].strip())
    for rule in PLAY_RULES:
        if match := rule.match(core):
            return Action("play", match["q"].strip(), canon(match["site"] or ""))
    for rule in FOLDER_RULES:
        if match := rule.match(core):
            return Action("folder", match["n"].strip())
    return None


def _single(text: str) -> Action | None:
    core = _strip_lead(text)
    core = TRAIL.sub("", core.rstrip(" .,!?;:")).strip()
    if not core:
        return None
    phrase = re.sub(r"[^\w\s]", "", core).lower()
    if phrase in PRESS:
        return Action("press", PRESS[phrase])
    if phrase in SLEEP:
        return Action("sleep")
    if phrase in WAKE_UP:
        return Action("wake")
    if phrase in CHAT_PHRASES:
        return Action("chat", CHAT_PHRASES[phrase])
    if feature := _feature(core, phrase):
        return feature
    for rule in SEARCH_RULES:
        if match := rule.match(core):
            groups = match.groupdict()
            return Action("search", groups["q"].strip(), (groups.get("site") or "").lower())
    if match := FIND_FILE.match(core):
        return Action("find", match["q"].strip(), "show")
    for rule in OPEN_RULES:
        if match := rule.match(core):
            return Action("open", match["t"].strip())
    if canon(core) in BARE_NAMES:
        return Action("open", core)
    return None


def split_send(text: str) -> tuple[str, bool]:
    """Separates "...and press enter" from the words to be typed."""
    for rule in (SEND_AT_END, SEND_AFTER_SENTENCE):
        without = rule.sub("", text)
        if without != text:
            return without.strip(), True
    return text.strip(), False


def drop_leading_words(heard: str, spoken: str) -> str:
    """Removes the start of what was heard if it is just Jarvis's own voice picked up by the mic."""
    own = {word.lower() for word in re.findall(r"[\w']+", spoken)}
    words = list(re.finditer(r"[\w']+", heard))
    count = 0
    while count < len(words) and words[count][0].lower() in own:
        count += 1
    if count == len(words):
        return ""
    return heard[words[count].start() :] if count >= 2 else heard  # one shared word could be your own ("how are you")


def is_send_mishearing(heard: str) -> bool:
    """A short phrase that sounds like "send it", ignoring filler such as "okay" or "seems good"."""
    words = [word for word in re.sub(r"[^\w\s]", "", heard).lower().split() if word not in SEND_FILLER]
    return 1 <= len(words) <= MAX_SEND_SOUNDS and all(word in SEND_SOUNDS for word in words)


def _typing(text: str) -> list[Action] | None:
    if TYPE_MISHEARD.match(text):
        return [Action("dictate")]
    match = TYPE.match(text)
    if not match:
        return None
    body = match[1].strip()
    if not re.search(r"\w", body):
        return [Action("dictate")]
    text_only, send = split_send(body)
    if not text_only:
        return [Action("dictate")]
    return [Action("type", text_only), Action("press", "send")] if send else [Action("type", body)]


def _writing(text: str) -> list[Action] | None:
    """Messages and replies carry free text, so words like "and" inside them must not split the command."""
    if match := ASK_AI.match(text):
        question = match["q"].strip()
        return [Action("ask_ai", question if re.search(r"\w", question) else "", canon(match["app"]))]
    if match := REPLY.match(text):
        what = "reply_all" if "all" in match["what"].lower() else "reply"
        return [Action("mail", what, text=(match["body"] or "").strip())]
    for rule in MESSAGE_RULES:
        if match := rule.match(text):
            groups = match.groupdict()
            app = groups.get("app") or groups.get("app2") or DEFAULT_MESSENGER
            who = groups["who"].strip(" ,.")
            return [Action("message", who, canon(app), (groups.get("body") or "").strip())]
    return None


def _chain(text: str) -> list[Action]:
    text = _strip_lead(text)
    typed = _typing(text)
    if typed is not None:
        return typed
    written = _writing(text)
    if written is not None:
        return written
    for join in JOIN.finditer(text):
        left = _single(text[: join.start()])
        if left:
            rest = _chain(text[join.end() :])
            if rest:
                return [left, *rest]
    single = _single(text)
    return [single] if single else []


def _collapse(actions: list[Action]) -> list[Action]:
    """"open youtube and search cats" is one action: search YouTube for cats."""
    result: list[Action] = []
    for action in actions:
        previous = result[-1] if result else None
        if action.kind == "search" and not action.site and previous and previous.kind == "open":
            site = canon(previous.arg)
            if site in SEARCH_URLS:
                result[-1] = Action("search", action.arg, site)
                continue
        result.append(action)
    return result


def parse(heard: str) -> list[Action]:
    text = repair_verb(_strip_lead(strip_wake(heard)))
    if re.sub(r"[^\w\s]", "", text).lower() in NOTHING:
        return []
    return _collapse(_chain(text))


def is_cancel(heard: str) -> bool:
    return re.sub(r"[^\w\s]", "", heard).strip().lower() in NOTHING


def is_dismiss(heard: str) -> bool:
    """ "Thank you, Jarvis" and "that's all" end the conversation."""
    phrase = re.sub(r"[^\w\s]", "", heard).strip().lower()
    return phrase.removesuffix(_wake_core.lower()).strip() in DISMISS


set_wake_name(DEFAULT_WAKE)


def _apply_spoken_edits(text: str) -> str:
    """ "Scratch that" removes what came just before it; "new line" and "new paragraph" break the text."""
    while match := SCRATCH_THAT.search(text):
        before = text[: match.start()].rstrip()
        cut = max((before.rfind(mark, 0, len(before) - 1) for mark in ".!?\n"), default=-1)
        text = before[: cut + 1] + " " + text[match.end() :]
    text = re.sub(r"[,.]?\s*\bnew paragraph\b[,.]?\s*", "\n\n", text, flags=re.I)
    return re.sub(r"[,.]?\s*\bnew line\b[,.]?\s*", "\n", text, flags=re.I)


def clean_dictation(text: str) -> str:
    text = _apply_spoken_edits(text)
    text = re.sub(r"(^|[\s,.])(?:um+|uh+|erm|hmm+)(?=[\s,.!?]|$)[,.]?", r"\1", text, flags=re.I)
    for heard, meant in VOCABULARY.items():
        text = re.sub(rf"\b{re.escape(heard)}\b", meant, text, flags=re.I)
    text = re.sub(r"[ \t]+([,.!?])", r"\1", re.sub(r"[ \t]+", " ", text)).strip()
    text = re.sub(r" ?\n ?", "\n", text)
    return text[:1].upper() + text[1:]


_HOUR = r"\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve"
DURATION = re.compile(r"\bfor\s+(?P<n>half an|half a|an|a|one|\d+(?:\.\d+)?)\s*(?P<u>hours?|hrs?|minutes?|mins?)\b", re.I)
DAY_WORDS = re.compile(r"\b(?P<w>day after tomorrow|tomorrow|kal|today|aaj)\b", re.I)
WEEKDAY = re.compile(r"\b(?:(?:on|next|this)\s+)*(?P<d>monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", re.I)
WEEKDAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
CLOCK_MERIDIEM = re.compile(rf"\b(?:at\s+)?(?P<h>{_HOUR})(?::(?P<m>\d{{2}}))?\s*(?P<p>[ap])\.?\s*m\b\.?", re.I)
CLOCK_AT = re.compile(rf"\bat\s+(?P<h>{_HOUR})(?::(?P<m>\d{{2}}))?\b", re.I)
CLOCK_NAMED = re.compile(r"\b(?:at\s+)?(?P<w>noon|midnight)\b", re.I)


def _cut(text: str, match: re.Match) -> str:
    return f"{text[: match.start()]} {text[match.end() :]}"


def parse_when(text: str, now: datetime) -> tuple[str, datetime, int]:
    """Splits "meeting with Rahul tomorrow at 3 pm for 30 minutes" into title, start and minutes."""
    rest = text
    minutes = 60
    if match := DURATION.search(rest):
        amount = match["n"].lower()
        value = 0.5 if amount.startswith("half") else 1.0 if amount in ("a", "an", "one") else float(amount)
        minutes = int(value * (60 if match["u"].lower().startswith("h") else 1))
        rest = _cut(rest, match)

    day = None
    if match := DAY_WORDS.search(rest):
        word = match["w"].lower()
        day = now.date() + timedelta(days=2 if word.startswith("day") else 1 if word in ("tomorrow", "kal") else 0)
        rest = _cut(rest, match)
    elif match := WEEKDAY.search(rest):
        ahead = (WEEKDAY_NAMES.index(match["d"].lower()) - now.weekday()) % 7 or 7
        day = now.date() + timedelta(days=ahead)
        rest = _cut(rest, match)

    clock = None
    if match := CLOCK_NAMED.search(rest):
        clock = (12 if match["w"].lower() == "noon" else 0, 0)
        rest = _cut(rest, match)
    elif match := CLOCK_MERIDIEM.search(rest):
        hour = _hour(match["h"]) % 12 + (12 if match["p"].lower() == "p" else 0)
        clock = (hour, int(match["m"] or 0))
        rest = _cut(rest, match)
    elif match := CLOCK_AT.search(rest):
        hour = _hour(match["h"])
        clock = (hour + 12 if 1 <= hour <= 7 else hour, int(match["m"] or 0))
        rest = _cut(rest, match)

    today = now.replace(second=0, microsecond=0)
    if clock is None:
        if day is None:
            start = today.replace(minute=0) + timedelta(hours=1)
        else:
            start = datetime.combine(day, today.replace(hour=10, minute=0).time())
    else:
        start = datetime.combine(day or today.date(), today.replace(hour=clock[0], minute=clock[1]).time())
        if day is None and start <= now:
            start += timedelta(days=1)

    title = re.sub(r"\s+", " ", rest).strip(" ,.-")
    title = re.sub(r"\s+(?:on|at|for|from)$", "", title, flags=re.I)
    return title[:1].upper() + title[1:], start, minutes


def _hour(word: str) -> int:
    return int(word) if word.isdigit() else NUMBER_WORDS[word.lower()]
