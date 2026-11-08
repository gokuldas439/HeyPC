"""Finds an answer on screen and boils it down to a couple of sentences. Runs entirely on this PC.

It picks the answer's most important existing sentences; it does not rewrite them.
"""
import re
from collections import Counter

from . import uia

MAX_SUMMARY_WORDS = 45
MIN_SENTENCE_WORDS = 4
MIN_PARAGRAPH_WORDS = 8
CHAT_FURNITURE = re.compile(r"can make mistakes|double-check|please check|Reply to|^Thinking|^Searching|Sonnet|Opus|GPT-\d", re.I)
MAX_FILLER_WORDS = 8 # "Sure, here you go" is filler; a long sentence starting "Here are" can be the answer
PAGE_FURNITURE = re.compile(r"skip to main content|accessibility help|filter\. not selected", re.I)
MAX_INLINE_LINK_WORDS = 4  # short links sit inside sentences; long ones are page titles
FIRST_SENTENCE_BONUS = 1.6
COPY_BUTTON = re.compile(r"^copy(?:\s+(?:response|message|answer|text|reply))?$", re.I)
OVERVIEW_END = re.compile(r"AI responses may include mistakes|^Show more|^People also ask|^Dive deeper|^Things to know", re.I)
FILLER_OPENING = re.compile(r"^(?:sure|certainly|of course|great question|absolutely|okay|here(?:'s| is| are))\b", re.I)
SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(₹])")
COMMON_WORDS = set(
    "a an and are as at be but by can do for from has have how i if in is it its of on or so that the their them there "
    "these they this to was we were what when which while who will with you your".split()
)


def clean_markdown(text: str) -> str:
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"^\s*(?:#+\s*|>\s*|[-*•]\s+|\d+[.)]\s+)", "", text, flags=re.M)
    text = re.sub(r"^\s*\|.*\|\s*$", "", text, flags=re.M)
    return re.sub(r"[*_`]+", "", text)


def _sentences(text: str) -> list[str]:
    found = []
    for line in clean_markdown(text).splitlines():
        for sentence in SENTENCE_END.split(line.strip()):
            sentence = sentence.strip()
            size = len(sentence.split())
            is_title = "|" in sentence or sentence.endswith(("...", "…"))
            is_filler = size <= MAX_FILLER_WORDS and FILLER_OPENING.match(sentence)
            if size >= MIN_SENTENCE_WORDS and not sentence.endswith(":") and not is_title and not is_filler:
                found.append(re.sub(r"\s+([,.!?])", r"\1", sentence))
    return found


def _content_words(sentence: str) -> list[str]:
    return [word for word in re.findall(r"[a-z0-9']+", sentence.lower()) if word not in COMMON_WORDS]


def summarize_text(text: str, max_words: int = MAX_SUMMARY_WORDS) -> str:
    """The opening sentence, plus the sentences that best represent the rest, in their original order."""
    sentences = _sentences(text)
    if not sentences:
        return ""
    frequency = Counter(word for sentence in sentences for word in _content_words(sentence))

    def score(index: int) -> float:
        words = _content_words(sentences[index])
        value = sum(frequency[word] for word in words) / (len(words) + 3)
        return value * (FIRST_SENTENCE_BONUS if index == 0 else 1)

    chosen: list[int] = []
    total = 0
    for index in sorted(range(len(sentences)), key=score, reverse=True):
        size = len(sentences[index].split())
        if not chosen or total + size <= max_words:
            chosen.append(index)
            total += size
    if 0 not in chosen and len(sentences[0].split()) <= max_words:
        while chosen and total + len(sentences[0].split()) > max_words:
            total -= len(sentences[chosen.pop()].split())
        chosen.append(0)
    return " ".join(sentences[index] for index in sorted(chosen))


def text_blocks(items: list[uia.Item]) -> list[str]:
    """Rebuilds paragraphs from the many small pieces of text a web page reports."""
    area = uia.web_area(items)
    pieces = [
        i for i in items
        if (i.kind == uia.TEXT or (i.kind == uia.HYPERLINK and len(i.name.split()) <= MAX_INLINE_LINK_WORDS))
        and (not area or (i.top >= area.top and i.bottom <= area.bottom))
    ]
    blocks: list[str] = []
    current: list[str] = []
    previous = None
    for piece in pieces:
        if previous and piece.top - previous.bottom > (previous.bottom - previous.top) * 0.9:
            blocks.append(" ".join(current))
            current = []
        current.append(piece.name)
        previous = piece
    if current:
        blocks.append(" ".join(current))
    return [re.sub(r"\s+", " ", block).strip() for block in blocks]


def ai_overview(blocks: list[str]) -> str:
    """The text of Google's AI Overview, or an empty string if the page has none."""
    start = next((index for index, block in enumerate(blocks) if block.lower().startswith("ai overview")), None)
    if start is None:
        return ""
    answer = []
    first = re.sub(r"^ai overview\s*", "", blocks[start], flags=re.I)
    for block in [first, *blocks[start + 1 :]]:
        if OVERVIEW_END.search(block):
            break
        answer.append(block)
    return "\n".join(answer)


def page_text(blocks: list[str]) -> str:
    return "\n".join(block for block in blocks if len(block.split()) >= MIN_PARAGRAPH_WORDS and not PAGE_FURNITURE.search(block))


def _trim_reply(tail: str) -> str:
    """Drops the app's own notices one sentence at a time, because they can share a line with the reply."""
    kept = []
    for line in tail.splitlines():
        parts = [part for part in SENTENCE_END.split(line.strip()) if part and not CHAT_FURNITURE.search(part)]
        if parts:
            kept.append(" ".join(parts))
    return "\n".join(kept).lstrip(" ?.!\n")


def reply_text(blocks: list[str], question: str, before: set[str]) -> str:
    """The AI's reply so far: what appears after your question, or failing that, whatever is new on screen."""
    words = re.findall(r"[a-z0-9']+", question.lower())
    text = "\n".join(blocks)
    matches = list(re.finditer(r"\W+".join(map(re.escape, words)), text, re.I)) if words else []
    if matches:
        return _trim_reply(text[matches[-1].end() :])
    return _trim_reply("\n".join(block for block in blocks if block not in before))


def finished_sentences(reply: str, final: bool) -> list[str]:
    """Sentences that are safe to read out: while a reply is still arriving, the last part may be half a sentence."""
    if not final:
        endings = [position for position in (reply.rfind(mark) for mark in ".!?\n") if position >= 0]
        reply = reply[: max(endings) + 1] if endings else ""
    return [sentence for sentence in _sentences(reply) if not CHAT_FURNITURE.search(sentence)]


def lowest_copy_button(items: list[uia.Item]) -> uia.Item | None:
    """Chat apps put a Copy button under each reply, so the lowest one belongs to the latest reply."""
    buttons = [i for i in items if i.kind in uia.CLICKABLE and COPY_BUTTON.match(i.name.strip())]
    return max(buttons, key=lambda i: i.top, default=None)
