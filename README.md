# HeyPC

A free, open-source voice assistant for Windows. Name your AI anything you like (it's called Jarvis until you do), then control your PC, dictate into any app, talk to ChatGPT and Claude hands-free, and hear natural replies. No subscription, no account, no API keys.

**[Website](https://gokuldas439.github.io/HeyPC-landing/) · [See it work](https://gokuldas439.github.io/HeyPC-landing/demo.html) · [Download for Windows](https://github.com/gokuldas439/HeyPC/releases/latest)**

## Commands

**[Download the one-page command sheet (PDF)](docs/HeyPC-Commands.pdf)**

### Getting started

| Say or do | What happens |
|---|---|
| "Hey Jarvis" | Wakes it. It greets you, then listens. |
| "Hey Jarvis, open Chrome" | Say it in one breath to skip the greeting. |
| Tap or hold Right Alt | Same as the wake word, without speaking it. |
| Hold Right Ctrl and talk | Types your words wherever the cursor is. |
| Keep talking | After each command it keeps listening, so no wake word is needed. |
| "Thank you" or "That's all" | Ends the conversation. |
| "Jarvis stop" | Stops at once, even mid-reply or mid-dictation. |
| The small icon above the taskbar | Blue bars: listening. Amber spinner: working. Green wave: speaking. |

### Apps and windows

| Say | What happens |
|---|---|
| "Open Claude" | Shows the app, even if minimized, or launches it |
| "Close Spotify" | Closes the app; it can still ask to save |
| "Minimize Chrome" / "Maximize Cursor" | Resizes that app |
| "Minimize everything" | Shows the desktop |
| "Snap left" / "Put Chrome on the right" | Moves a window to one side |
| "Do that again" | Repeats your last command |
| "I meant Claude" | Corrects a misheard name and remembers it |

### Typing

| Say | What happens |
|---|---|
| "Type" (pause, then speak) | Types what you say next |
| "Type hello there" | Types those words straight away |
| "Send it" / "Enter" | Presses Enter |
| "...and send it" at the end | Types, then sends |
| "Remove all text" | Clears the box |
| "Remove the last word" / "last three words" | Deletes those words |
| "Remove the last sentence" | Deletes the last sentence |
| "Remove the word actually" | Deletes that word |
| "Undo" | Takes back the last action |
| "New line" / "Scratch that" | While dictating: line break / delete that bit |

### Web and browser

| Say | What happens |
|---|---|
| "Search for best laptops" | Google search |
| "Search YouTube for lo-fi" | Searches that site |
| "Go to the Gmail tab" | Jumps to a tab by name |
| "Close the Gmail tab" | Closes it by name |
| "New tab" / "Next tab" / "Close this tab" | Tab controls |
| "Go back" / "Refresh" / "Scroll down" | Page controls |
| "Click sign in" | Clicks an item by its name |
| "Open the third result" | Opens a result or email by number |

### ChatGPT and Claude

| Say | What happens |
|---|---|
| "Ask Claude what is an SIP" | Asks, then reads the start of the reply |
| "Ask ChatGPT ..." | Same, in ChatGPT |
| "New chat" / "New chat in ChatGPT" | Starts a fresh chat |
| "Summarize the response" | Reads a short summary aloud |

### Work

| Say | What happens |
|---|---|
| "Start work" | Opens what you chose during setup |
| "Git status in backend" | Runs a listed command, reads the result |
| "Run frontend" | Starts it in a terminal tab |
| "Start 3 Claude agents" | Opens that many terminals (up to 8) |

### Reminders and timers

| Say | What happens |
|---|---|
| "Remind me in 20 minutes to call Rahul" | Also "at 5 PM" or "tomorrow at 9" |
| "Set a timer for 10 minutes" | Chimes and speaks when done |
| "How much time is left?" | Reads what's coming up |
| "Cancel the timer" / "Cancel all reminders" | Removes them |

### PC controls

| Say | What happens |
|---|---|
| "Lock my PC" | Locks straight away |
| "Shut down" / "Restart" | Asks for a spoken yes first |
| "What's my battery?" | Reads the percentage |
| "Set brightness to 40" / "Volume up" | Screen and sound |
| "Turn off Wi-Fi" / "Turn on Bluetooth" | Switches them |
| "Take a screenshot" | Opens the snipping tool |

### Files and tools

| Say | What happens |
|---|---|
| "Find the invoice PDF" | Shows the newest match in its folder |
| "Open the budget file" | Opens it; programs are never launched |
| "Open my latest download" | Also "last screenshot" |
| "Open the downloads folder" | Opens a folder |
| "Rename this to Final Report" | Renames the selected file |
| "What's 18 percent of 2500?" | Calculator |
| "Paste the second last thing I copied" | Clipboard history |

### Messages, meetings and music

| Say | What happens |
|---|---|
| "Message Rahul on WhatsApp saying hi" | Drafts it; sends after a spoken yes |
| "Reply saying thanks" / "Archive this" | Works on the open email |
| "Schedule a meeting tomorrow at 3 PM" | Opens a filled-in calendar event |
| "Join the meeting" | Uses a link you copied or a Join button |
| "Play Coldplay on Spotify" | Also YouTube |
| "Pause" / "Next song" | Media controls |

**Tips.** Say "I meant Claude" to fix a misheard name. Change the wake word, voice and Start work list in Settings (right-click the ring icon).

## Install

1. Download `HeyPC-Setup.exe` from [Releases](https://github.com/gokuldas439/HeyPC/releases/latest) (about 700 MB, because the speech models are included).
2. If Windows shows "Windows protected your PC", choose **More info**, then **Run anyway**. The installer isn't code-signed because signing certificates cost money.
3. Finish the setup page. Look for the ring icon in the system tray.

Tested on Windows 11. It needs a microphone and about 2 GB of free RAM; 4 cores and 8 GB are recommended.

## Privacy

- **Listening and understanding happen on your PC.** Audio is never uploaded or saved.
- **Online voices** (the default) send only the sentence HeyPC is about to say to Microsoft's read-aloud service. Pick an "offline" voice in Settings to send nothing.
- **Clipboard history** stays in memory, disappears when you quit, and skips anything password managers mark as private.
- **Logs** don't record what you say unless you turn on the detailed log in Settings.
- There are no accounts, analytics or telemetry.

## Safety

Voice commands can act on your PC, so HeyPC is cautious by design:

- Messages, emails with text, shutdown, restart, and clicks on words like "delete" or "pay" need a spoken "yes".
- Terminal commands come only from a list you control in Settings; spoken words never become commands.
- Asking to open a file never launches a program. Those are shown in their folder instead.

Please report security problems privately through [GitHub security advisories](https://github.com/gokuldas439/HeyPC/security/advisories/new).

## Good to know

- Bluetooth earphones usually drop to call-quality audio while their microphone is in use.
- On keyboards where Right Alt types symbols (AltGr), HeyPC automatically leaves that key alone. The wake word and Right Ctrl still work.
- Commands are matched by rules, so unusual phrasing may not work. If a name is misheard, say "I meant Claude" and it will remember.
- Speech recognition is English-only.
- The online voices use an unofficial service that could change; HeyPC falls back to its offline voice if so.

## Build from source

Requires Windows, Python 3.14, and [Inno Setup 6](https://jrsoftware.org/isinfo.php) for the installer.

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt pyinstaller
.venv\Scripts\python.exe setup_models.py parakeet
.venv\Scripts\python.exe setup_models.py tiny
.venv\Scripts\python.exe -m unittest tests.test_commands
.venv\Scripts\python.exe -m heypc.app
powershell -ExecutionPolicy Bypass -File packaging\build.ps1
```

## License

[GPL-3.0](LICENSE). Bundled models and libraries have their own terms, listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). In particular, the wake-word models are for **non-commercial use only**.

HeyPC is an independent project and is not affiliated with Marvel or Disney.
