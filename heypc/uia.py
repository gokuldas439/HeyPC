"""Reads what is on screen through Windows UI Automation, so items can be clicked by name."""
import re
import time
from dataclasses import dataclass
from difflib import SequenceMatcher

import comtypes
import comtypes.client
from pynput.mouse import Button, Controller as Mouse

from . import winctl

NAME, CONTROL_TYPE, RECT, OFFSCREEN, ENABLED, INVOKABLE = 30005, 30003, 30001, 30022, 30010, 30031
INVOKE_PATTERN = 10000
TREE_SCOPE_DESCENDANTS = 4

BUTTON, CHECKBOX, COMBOBOX, HYPERLINK, LISTITEM, MENUITEM, RADIO = 50000, 50002, 50003, 50005, 50007, 50011, 50013
TABITEM, TEXT, TREEITEM, GROUP, DATAITEM, DOCUMENT, SPLITBUTTON = 50019, 50020, 50024, 50026, 50029, 50030, 50031
CLICKABLE = {BUTTON, CHECKBOX, COMBOBOX, HYPERLINK, LISTITEM, MENUITEM, RADIO, TABITEM, TREEITEM, DATAITEM, SPLITBUTTON}
LAST_RESORT = {TEXT, GROUP}
ROWS = {DATAITEM, LISTITEM, TREEITEM}
ROW_NOUNS = {"email", "mail", "message", "chat", "conversation", "item", "row"}

MIN_ITEMS = 8  # fewer than this usually means a browser is still switching its accessibility on
SCAN_TRIES = 4
MIN_RESULT_NAME = 12
MIN_RESULT_WIDTH = 180
FUZZY_MATCH = 0.82
MAX_WORDS_IN_A_NAME = 6
EDIT = 50004
TOOLBAR = 50021
MESSAGE_BOX = re.compile(r"prompt|message|reply|ask|chat|write", re.I)
NOT_RESULTS = re.compile(r"^(?:skip to|accessibility|feedback|sign in|learn more)", re.I)

mouse = Mouse()
_client = None


@dataclass
class Item:
    name: str
    kind: int
    left: int
    top: int
    right: int
    bottom: int
    invokable: bool
    element: object


def _uia():
    global _client
    if _client is None:
        comtypes.client.GetModule("UIAutomationCore.dll")
        from comtypes.gen import UIAutomationClient as lib

        _client = comtypes.client.CreateObject(lib.CUIAutomation, interface=lib.IUIAutomation)
    return _client


def _collect(auto, root, request) -> list[Item]:
    found = root.FindAllBuildCache(TREE_SCOPE_DESCENDANTS, auto.ControlViewCondition, request)
    items = []
    for index in range(found.Length if found else 0):
        element = found.GetElement(index)
        name = (element.CachedName or "").strip()
        rect = element.CachedBoundingRectangle
        if not name or element.CachedIsOffscreen or not element.CachedIsEnabled or rect.right <= rect.left:
            continue
        items.append(
            Item(name, element.CachedControlType, rect.left, rect.top, rect.right, rect.bottom,
                 bool(element.GetCachedPropertyValue(INVOKABLE)), element)
        )
    return items


def scan(hwnd=None) -> list[Item]:
    """Everything named and visible in a window (the front one by default), in one fast cross-process call."""
    auto = _uia()
    request = auto.CreateCacheRequest()
    for prop in (NAME, CONTROL_TYPE, RECT, OFFSCREEN, ENABLED, INVOKABLE):
        request.AddProperty(prop)
    root = auto.ElementFromHandle(hwnd or winctl.user32.GetForegroundWindow())
    items: list[Item] = []
    for attempt in range(SCAN_TRIES):
        items = _collect(auto, root, request)
        if len(items) >= MIN_ITEMS:
            break
        if attempt < SCAN_TRIES - 1:
            time.sleep(0.5)
    return items


def _squash(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _score(wanted: str, name: str) -> float:
    if name == wanted:
        return 4
    if name.startswith(wanted + " "):
        return 3
    if f" {wanted} " in f" {name} ":
        # A word inside a long description ("press Enter to commit") is not that control's name.
        return 2 if len(name.split()) <= MAX_WORDS_IN_A_NAME else 0
    ratio = SequenceMatcher(None, wanted, name).ratio()
    return ratio if ratio >= FUZZY_MATCH else 0


def best_match(spoken: str, items: list[Item]) -> Item | None:
    """Prefers real controls; plain text is tried only when no control matches."""
    wanted = _squash(spoken)
    if not wanted:
        return None
    for allowed in (CLICKABLE, LAST_RESORT):
        scored = [(s, item) for item in items if item.kind in allowed and (s := _score(wanted, _squash(item.name)))]
        if scored:
            top = max(s for s, _ in scored)
            return min((item for s, item in scored if s == top), key=lambda i: (i.top, i.left))
    return None


def find(spoken: str) -> Item | None:
    return best_match(spoken, scan())


def web_area(items: list[Item]) -> Item | None:
    documents = [i for i in items if i.kind == DOCUMENT]
    return max(documents, key=lambda i: (i.right - i.left) * (i.bottom - i.top), default=None)


def nth_item(number: int, noun: str, items: list[Item]) -> Item | None:
    """"Third email" and "first result": list rows or result links, top to bottom."""
    area = web_area(items)
    inside = [i for i in items if not area or (i.top >= area.top and i.left >= area.left and i.bottom <= area.bottom)]
    links = [
        i for i in inside
        if i.kind == HYPERLINK and len(i.name) >= MIN_RESULT_NAME and i.right - i.left >= MIN_RESULT_WIDTH
        and not NOT_RESULTS.match(i.name)
    ]
    with_address = [i for i in links if "http" in i.name or "›" in i.name]  # search pages show the site in the link
    if noun == "result" and len(with_address) >= number:
        links = with_address
    rows = _one_per_line([i for i in inside if i.kind in ROWS])
    pool = (rows or links) if noun in ROW_NOUNS else (links or rows)
    pool.sort(key=lambda i: (i.top, i.left))
    return pool[number - 1] if 0 < number <= len(pool) else None


def _one_per_line(items: list[Item]) -> list[Item]:
    """A row and the cells inside it are all reported, but they count as one row on screen."""
    kept: list[Item] = []
    for item in sorted(items, key=lambda i: (i.top, i.left - i.right)):
        if not kept or item.top >= kept[-1].bottom - 2:
            kept.append(item)
    return kept


def nth(number: int, noun: str) -> Item | None:
    return nth_item(number, noun, scan())


def _word_found(word: str, name_words: list[str]) -> bool:
    return any(word == other or SequenceMatcher(None, word, other).ratio() >= FUZZY_MATCH for other in name_words)


def best_tab(spoken: str, items: list[Item]) -> Item | None:
    """The tab whose title contains every word you said, preferring one where they come earliest."""
    wanted = [word for word in _squash(spoken).split() if word != "the"]
    if not wanted:
        return None
    best, best_position = None, None
    for item in items:
        if item.kind != TABITEM:
            continue
        name_words = _squash(item.name).split()
        if all(_word_found(word, name_words) for word in wanted):
            position = next(index for index, other in enumerate(name_words) if _word_found(wanted[0], [other]))
        elif "".join(wanted) in "".join(name_words):  # "git hub" for GitHub
            position = len(name_words)
        else:
            continue
        if best is None or position < best_position:
            best, best_position = item, position
    return best


def first_starting(prefix: str) -> Item | None:
    matches = [i for i in scan() if i.kind in CLICKABLE and i.name.lower().startswith(prefix.lower())]
    return min(matches, key=lambda i: (i.top, i.left), default=None)


def activate(item: Item) -> None:
    """Uses the control's own action when it has one, so the mouse pointer stays where it is."""
    if item.invokable:
        import comtypes.gen.UIAutomationClient as lib

        item.element.GetCurrentPattern(INVOKE_PATTERN).QueryInterface(lib.IUIAutomationInvokePattern).Invoke()
        return
    position = mouse.position
    mouse.position = ((item.left + item.right) // 2, (item.top + item.bottom) // 2)
    mouse.click(Button.left)
    time.sleep(0.05)
    mouse.position = position


def click_first(names: list[str]) -> bool:
    """Clicks the first of these exact names that is on screen."""
    items = scan()
    for name in names:
        wanted = _squash(name)
        matches = [i for i in items if i.kind in CLICKABLE and _squash(i.name) == wanted]
        if matches:
            activate(min(matches, key=lambda i: (i.top, i.left)))
            return True
    return False


def focus_message_box() -> bool:
    """Puts the keyboard in a chat app's message box, which is the lowest text field on screen."""
    boxes = [item for item in scan() if item.kind == EDIT]
    named = [item for item in boxes if MESSAGE_BOX.search(item.name)]
    pick = max(named or boxes, key=lambda item: item.top, default=None)
    if pick is None:
        return False
    pick.element.SetFocus()
    return True


def keeping_focus(action):
    """Runs something that clicks a button, then puts the keyboard back where you were typing."""
    focused = _uia().GetFocusedElement()
    result = action()
    try:
        focused.SetFocus()
    except comtypes.COMError:
        pass  # that control went away, which is harmless
    return result


def focused_label() -> str:
    """The name of whatever currently has keyboard focus."""
    scan()  # makes browsers and web-based apps publish their accessibility data first
    element = _uia().GetFocusedElement()
    return " ".join(part for part in (element.CurrentName, element.CurrentAutomationId) if part)
