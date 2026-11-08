"""Writes docs/HeyPC-Commands.pdf and the command section of README.md from one list.

Needs reportlab, which the app itself does not:  pip install reportlab
"""
import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import BaseDocTemplate, Frame, FrameBreak, KeepTogether, NextPageTemplate, PageTemplate, Paragraph, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parent.parent
PDF = ROOT / "docs" / "HeyPC-Commands.pdf"
README = ROOT / "README.md"

BASICS = [
    ('"Hey Jarvis"', "Wakes it. It greets you, then listens."),
    ('"Hey Jarvis, open Chrome"', "Say it in one breath to skip the greeting."),
    ("Tap or hold Right Alt", "Same as the wake word, without speaking it."),
    ("Hold Right Ctrl and talk", "Types your words wherever the cursor is."),
    ("Keep talking", "After each command it keeps listening, so no wake word is needed."),
    ('"Thank you" or "That\'s all"', "Ends the conversation."),
    ('"Jarvis stop"', "Stops at once, even mid-reply or mid-dictation."),
    ('The small icon above the taskbar', "Blue bars: listening. Amber spinner: working. Green wave: speaking."),
]

SECTIONS = [
    ("Apps and windows", [
        ('"Open Claude"', "Shows the app, even if minimized, or launches it"),
        ('"Close Spotify"', "Closes the app; it can still ask to save"),
        ('"Minimize Chrome" / "Maximize Cursor"', "Resizes that app"),
        ('"Minimize everything"', "Shows the desktop"),
        ('"Snap left" / "Put Chrome on the right"', "Moves a window to one side"),
        ('"Do that again"', "Repeats your last command"),
        ('"I meant Claude"', "Corrects a misheard name and remembers it"),
    ]),
    ("Typing", [
        ('"Type" (pause, then speak)', "Types what you say next"),
        ('"Type hello there"', "Types those words straight away"),
        ('"Send it" / "Enter"', "Presses Enter"),
        ('"...and send it" at the end', "Types, then sends"),
        ('"Remove all text"', "Clears the box"),
        ('"Remove the last word" / "last three words"', "Deletes those words"),
        ('"Remove the last sentence"', "Deletes the last sentence"),
        ('"Remove the word actually"', "Deletes that word"),
        ('"Undo"', "Takes back the last action"),
        ('"New line" / "Scratch that"', "While dictating: line break / delete that bit"),
    ]),
    ("Web and browser", [
        ('"Search for best laptops"', "Google search"),
        ('"Search YouTube for lo-fi"', "Searches that site"),
        ('"Go to the Gmail tab"', "Jumps to a tab by name"),
        ('"Close the Gmail tab"', "Closes it by name"),
        ('"New tab" / "Next tab" / "Close this tab"', "Tab controls"),
        ('"Go back" / "Refresh" / "Scroll down"', "Page controls"),
        ('"Click sign in"', "Clicks an item by its name"),
        ('"Open the third result"', "Opens a result or email by number"),
    ]),
    ("ChatGPT and Claude", [
        ('"Ask Claude what is an SIP"', "Sends it. Say \"Summarize the response\" to hear it"),
        ('"Ask ChatGPT ..."', "Same, in ChatGPT"),
        ('"New chat" / "New chat in ChatGPT"', "Starts a fresh chat"),
        ('"Summarize the response"', "Reads a short summary aloud"),
    ]),
    ("Work", [
        ('"Start work"', "Opens what you chose during setup"),
        ('"Git status in backend"', "Runs a listed command, reads the result"),
        ('"Run frontend"', "Starts it in a terminal tab"),
        ('"Start 3 Claude agents"', "Opens that many terminals (up to 8)"),
    ]),
    ("Reminders and timers", [
        ('"Remind me in 20 minutes to call Rahul"', 'Also "at 5 PM" or "tomorrow at 9"'),
        ('"Set a timer for 10 minutes"', "Chimes and speaks when done"),
        ('"How much time is left?"', "Reads what's coming up"),
        ('"Cancel the timer" / "Cancel all reminders"', "Removes them"),
    ]),
    ("PC controls", [
        ('"Lock my PC"', "Locks straight away"),
        ('"Shut down" / "Restart"', "Asks for a spoken yes first"),
        ('"What\'s my battery?"', "Reads the percentage"),
        ('"Set brightness to 40" / "Volume up"', "Screen and sound"),
        ('"Turn off Wi-Fi" / "Turn on Bluetooth"', "Switches them"),
        ('"Take a screenshot"', "Opens the snipping tool"),
    ]),
    ("Files and tools", [
        ('"Find the invoice PDF"', "Shows the newest match in its folder"),
        ('"Open the budget file"', "Opens it; programs are never launched"),
        ('"Open my latest download"', 'Also "last screenshot"'),
        ('"Open the downloads folder"', "Opens a folder"),
        ('"Rename this to Final Report"', "Renames the selected file"),
        ('"What\'s 18 percent of 2500?"', "Calculator"),
        ('"Paste the second last thing I copied"', "Clipboard history"),
    ]),
    ("Messages, meetings and music", [
        ('"Message Rahul on WhatsApp saying hi"', "Drafts it; sends after a spoken yes"),
        ('"Reply saying thanks" / "Archive this"', "Works on the open email"),
        ('"Schedule a meeting tomorrow at 3 PM"', "Opens a filled-in calendar event"),
        ('"Join the meeting"', "Uses a link you copied or a Join button"),
        ('"Play Coldplay on Spotify"', "Also YouTube"),
        ('"Pause" / "Next song"', "Media controls"),
    ]),
]
TIPS = 'Say "I meant Claude" to fix a misheard name. Change the wake word, voice and Start work list in Settings (right-click the ring icon).'

INK, MUTED, ACCENT, RULE, BAND = (colors.HexColor(c) for c in ("#0b1220", "#5a6b85", "#0a7ea4", "#d9e2ee", "#f1f5fa"))
HEAD = ParagraphStyle("head", fontName="Helvetica-Bold", fontSize=9.6, leading=12, textColor=ACCENT, spaceAfter=2)
SAY = ParagraphStyle("say", fontName="Helvetica-Bold", fontSize=7.5, leading=9.3, textColor=INK, alignment=TA_LEFT)
DOES = ParagraphStyle("does", fontName="Helvetica", fontSize=7.5, leading=9.3, textColor=MUTED, alignment=TA_LEFT)
TITLE = ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=22, leading=25, textColor=INK)
LEAD = ParagraphStyle("lead", fontName="Helvetica", fontSize=9.5, leading=12.5, textColor=MUTED)
TIP = ParagraphStyle("tip", fontName="Helvetica", fontSize=7.8, leading=10.4, textColor=MUTED)


def escaped(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;")


def table(rows: list, width: float) -> Table:
    data = [[Paragraph(escaped(say), SAY), Paragraph(escaped(does), DOES)] for say, does in rows]
    built = Table(data, colWidths=[width * 0.54, width * 0.46])
    built.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 1.7), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.7),
        ("LINEBELOW", (0, 0), (-1, -2), 0.3, RULE),
    ]))
    return built


def write_pdf() -> None:
    page_w, page_h = A4
    margin = 13 * mm
    gap = 7 * mm
    column = (page_w - 2 * margin - gap) / 2
    header = 68 * mm
    body = page_h - 2 * margin
    first = PageTemplate(id="first", frames=[
        Frame(margin, page_h - margin - header, page_w - 2 * margin, header, 0, 0, 0, 0, id="top"),
        Frame(margin, margin, column, body - header - 3 * mm, 0, 0, 0, 0, id="c1"),
        Frame(margin + column + gap, margin, column, body - header - 3 * mm, 0, 0, 0, 0, id="c2"),
    ])
    rest = PageTemplate(id="rest", frames=[
        Frame(margin, margin, column, body, 0, 0, 0, 0, id="r1"),
        Frame(margin + column + gap, margin, column, body, 0, 0, 0, 0, id="r2"),
    ])
    doc = BaseDocTemplate(str(PDF), pagesize=A4, title="HeyPC voice commands", author="HeyPC open-source project", subject="Command cheat sheet")
    doc.addPageTemplates([first, rest])

    story = [NextPageTemplate("rest"), Paragraph("HeyPC voice commands", TITLE), Spacer(1, 2), Paragraph("Your AI is called Jarvis until you rename it. Say these in your own words. " + escaped(TIPS), LEAD), Spacer(1, 8)]
    data = [[Paragraph(escaped(say), SAY), Paragraph(escaped(does), DOES)] for say, does in BASICS]
    basics = Table(data, colWidths=[62 * mm, page_w - 2 * margin - 62 * mm])
    basics.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), BAND), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 2.6), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.6),
        ("LINEBELOW", (0, 0), (-1, -2), 0.3, RULE),
    ]))
    story += [Paragraph("Getting started", HEAD), Spacer(1, 2), basics, FrameBreak()]

    for name, rows in SECTIONS:
        story.append(KeepTogether([Paragraph(name, HEAD), table(rows, column), Spacer(1, 4)]))
    doc.build(story)


def write_readme() -> None:
    def rows(entries) -> str:
        return "\n".join(f"| {say} | {does} |" for say, does in entries)

    parts = ["## Commands\n", "**[Download the one-page command sheet (PDF)](docs/HeyPC-Commands.pdf)**\n"]
    parts.append("### Getting started\n\n| Say or do | What happens |\n|---|---|\n" + rows(BASICS) + "\n")
    for name, entries in SECTIONS:
        parts.append(f"### {name}\n\n| Say | What happens |\n|---|---|\n" + rows(entries) + "\n")
    parts.append(f"**Tips.** {TIPS}\n\n")
    text = README.read_text(encoding="utf-8")
    README.write_text(re.sub(r"## (?:What it does|Commands)\n.*?(?=## Install)", lambda _m: "\n".join(parts), text, count=1, flags=re.S), encoding="utf-8")


if __name__ == "__main__":
    write_pdf()
    write_readme()
    print(f"wrote {PDF} and {README}")
