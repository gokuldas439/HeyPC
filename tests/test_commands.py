import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

from heypc import actions, app, audio, calc, clipboard, commands, config, files, persona, reminders, routines, setup_ui, summary, terminal, uia
from heypc import settings as prefs
from heypc.commands import (
    Action, canon, clean_dictation, is_dismiss, is_risky, is_send_mishearing, is_yes, parse, parse_when, split_send,
)


def open_(name):
    return Action("open", name)


def press(name):
    return Action("press", name)


class ParseTests(unittest.TestCase):
    def check(self, heard, *expected):
        self.assertEqual(parse(heard), list(expected), heard)

    def test_open(self):
        self.check("Open Claude.", open_("Claude"))
        self.check("Hey Jarvis, open Codex.", open_("Codex"))
        self.check("Can you please open the Claude app?", open_("Claude"))
        self.check("Switch to Chrome.", open_("Chrome"))
        self.check("Claude kholo", open_("Claude"))

    def test_mishearings(self):
        self.assertEqual(canon(parse("Open clawed.")[0].arg), "claude")
        self.assertEqual(canon(parse("Open cortex.")[0].arg), "codex")
        self.assertEqual(canon(parse("Open chat GPT.")[0].arg), "chatgpt")

    def test_type(self):
        self.check("Type.", Action("dictate"))
        self.check("Hey Jarvis, type", Action("dictate"))
        self.check("Tie.", Action("dictate"))
        self.check("Type fix the tests and open the logs.", Action("type", "fix the tests and open the logs."))
        self.check("Type hello there and send it.", Action("type", "hello there"), press("send"))

    def test_search(self):
        self.check("Go to open Google and search this thing.", Action("search", "this thing", "google"))
        self.check("Open Google and search for best 3D printers.", Action("search", "best 3D printers", "google"))
        self.check("Open YouTube and search lo-fi music.", Action("search", "lo-fi music", "youtube"))
        self.check("Search YouTube for cat videos.", Action("search", "cat videos", "youtube"))
        self.check("Search cats and dogs.", Action("search", "cats and dogs", ""))
        self.check("Google weather in Bangalore.", Action("search", "weather in Bangalore", ""))
        self.check("Best phones search karo", Action("search", "Best phones", ""))

    def test_chains(self):
        self.check("Open Claude and type hello world.", open_("Claude"), Action("type", "hello world."))
        self.check("Open Claude, then type.", open_("Claude"), Action("dictate"))
        self.check("Open Claude. Type how are you?", open_("Claude"), Action("type", "how are you?"))
        self.check("Open Chrome and new tab.", open_("Chrome"), press("new_tab"))

    def test_keys(self):
        self.check("Send it.", press("send"))
        self.check("Sent it.", press("send"))
        self.check("Hey Jarvis send it", press("send"))
        self.check("Undo that.", press("undo"))
        self.check("Scroll down please.", press("scroll_down"))
        self.check("Go back.", press("back"))
        self.check("Bhej do", press("send"))

    def test_sleep(self):
        self.check("Go to sleep.", Action("sleep"))
        self.check("Wake up.", Action("wake"))

    def test_ignored(self):
        self.check("")
        self.check("Never mind.")
        self.check("I was thinking about lunch today.")
        self.check("What a nice day.")

    def test_dictation_cleanup(self):
        self.assertEqual(clean_dictation("um fix the tests, uh, please"), "Fix the tests, please")
        self.assertEqual(clean_dictation("ask clawed about chat gpt"), "Ask Claude about ChatGPT")


class FeatureTests(unittest.TestCase):
    def check(self, heard, *expected):
        self.assertEqual(parse(heard), list(expected), heard)

    def test_messages(self):
        hello = Action("message", "Rahul", "whatsapp", "hello there")
        self.check("Message Rahul on WhatsApp saying hello there", hello)
        self.check("Message Rahul saying hello there on WhatsApp.", hello)
        self.check("Send hello there to Rahul on WhatsApp.", hello)
        self.check("WhatsApp Rahul saying hello there", hello)
        self.check("Rahul ko WhatsApp pe bolo hello there", hello)
        self.check("Message Rahul saying hello there", hello)
        self.check("Message Priya on Slack.", Action("message", "Priya", "slack"))
        self.check("Tell Priya on Slack that the build and tests passed.", Action("message", "Priya", "slack", "the build and tests passed."))
        self.check("Open Chrome and message Rahul saying hi and bye", open_("Chrome"), Action("message", "Rahul", "whatsapp", "hi and bye"))

    def test_mail(self):
        self.check("Reply.", Action("mail", "reply"))
        self.check("Reply all.", Action("mail", "reply_all"))
        self.check("Reply to this email saying thanks and regards.", Action("mail", "reply", text="thanks and regards."))
        self.check("Forward this email.", Action("mail", "forward"))
        self.check("Archive this.", Action("mail", "archive"))
        self.check("Forward.", press("forward"))

    def test_click(self):
        self.check("Click sign in.", Action("click", "sign in"))
        self.check("Click on the compose button.", Action("click", "compose"))
        self.check("Press submit.", Action("click", "submit"))
        self.check("Compose pe click karo", Action("click", "Compose"))
        self.check("Click Terms and Conditions.", Action("click", "Terms and Conditions"))
        self.check("Press enter.", press("enter"))
        self.check("Select all.", press("select_all"))

    def test_nth(self):
        self.check("Open the first email.", Action("nth", "1", "email"))
        self.check("Third result.", Action("nth", "3", "result"))
        self.check("Click the 2nd link.", Action("nth", "2", "link"))
        self.check("Result number four.", Action("nth", "4", "result"))

    def test_play(self):
        self.check("Play Arijit Singh on YouTube.", Action("play", "Arijit Singh", "youtube"))
        self.check("Play Coldplay on Spotify.", Action("play", "Coldplay", "spotify"))
        self.check("Play rock and roll.", Action("play", "rock and roll"))
        self.check("Kesariya Spotify pe bajao", Action("play", "Kesariya", "spotify"))
        self.check("Play.", press("play_pause"))
        self.check("Set volume to 40.", Action("volume", "40"))

    def test_calendar_and_join(self):
        self.check("Schedule a meeting with Rahul and Priya tomorrow at 3 PM.", Action("calendar", "meeting with Rahul and Priya tomorrow at 3 PM"))
        self.check("Add dentist to my calendar on Friday at 5.", Action("calendar", "dentist on Friday at 5"))
        self.check("Join meet abc def ghij.", Action("join", "abc def ghij", "meet"))
        self.check("Join Zoom 123 456 7890.", Action("join", "123 456 7890", "zoom"))
        self.check("Join the meeting.", Action("join"))

    def test_when(self):
        now = datetime(2026, 11, 8, 14, 20)  # a Sunday
        self.assertEqual(parse_when("meeting with Rahul tomorrow at 3 PM for 30 minutes", now), ("Meeting with Rahul", datetime(2026, 11, 9, 15, 0), 30))
        self.assertEqual(parse_when("dentist on Friday at 5", now), ("Dentist", datetime(2026, 11, 13, 17, 0), 60))
        self.assertEqual(parse_when("call at 9:30 a.m. for half an hour", now), ("Call", datetime(2026, 11, 9, 9, 30), 30))
        self.assertEqual(parse_when("standup", now), ("Standup", datetime(2026, 11, 8, 15, 0), 60))

    def test_agents_folders_rename(self):
        self.check("Start 3 Claude agents.", Action("agents", "3", "claude"))
        self.check("Open four clawed agents in voice jarvis.", Action("agents", "4", "claude", "voice jarvis"))
        self.check("Launch a Codex terminal.", Action("agents", "1", "codex"))
        self.check("Open the downloads folder.", Action("folder", "downloads"))
        self.check("Voice Jarvis folder kholo", Action("folder", "Voice Jarvis"))
        self.check("Rename this to Final Report.", Action("rename", "Final Report"))

    def test_confirmation_words(self):
        for word in ("Yes.", "Yeah", "yes, send it", "Haan", "Send it."):
            self.assertTrue(is_yes(word), word)
        for word in ("", "No.", "Not yet", "Yes but change it", "What"):
            self.assertFalse(is_yes(word), word)
        self.assertTrue(is_risky("Delete account"))
        self.assertTrue(is_risky("Sign out"))
        self.assertFalse(is_risky("Compose"))


class SendingTests(unittest.TestCase):
    def check(self, heard, *expected):
        self.assertEqual(parse(heard), list(expected), heard)

    def test_every_way_of_asking_for_enter(self):
        for phrase in ("Click enter.", "Can you click Ender?", "Press enter.", "Hit the enter key.", "Enter.", "Click on enter.", "Press the enter button."):
            self.check(phrase, press("enter"))

    def test_every_way_of_asking_to_send(self):
        for phrase in ("Send it.", "Send a message.", "Hey Jarvis, send a message.", "Send the prompt.", "Send this message."):
            self.check(phrase, press("send"))

    def test_real_click_targets_still_click(self):
        self.check("Click enter details.", Action("click", "enter details"))
        self.check("Click send.", Action("click", "send"))

    def test_messaging_still_works(self):
        self.check("Send a message to Rahul on WhatsApp saying hi.", Action("message", "Rahul", "whatsapp", "hi."))

    def test_send_at_the_end_of_dictation(self):
        self.assertEqual(split_send("fix the login page and press enter."), ("fix the login page", True))
        self.assertEqual(split_send("fix the login page and enter"), ("fix the login page", True))
        self.assertEqual(split_send("Fix the login page. Press enter."), ("Fix the login page.", True))
        self.assertEqual(split_send("Fix the login page. Send it."), ("Fix the login page.", True))
        self.assertEqual(split_send("Fix the login page. Enter."), ("Fix the login page.", True))
        self.assertEqual(split_send("please enter your password"), ("please enter your password", False))
        self.assertEqual(split_send("this is my day send it"), ("this is my day", True))
        self.assertEqual(split_send("this is my day, send it."), ("this is my day", True))
        self.assertEqual(split_send("how do I send this"), ("how do I send this", False))

    def test_inline_type_with_enter(self):
        self.check("Type this is my day and press enter.", Action("type", "this is my day"), press("send"))

    def test_own_greeting_is_removed_from_what_was_heard(self):
        greeting = "Good evening, Sam. How may I help you?"
        self.assertEqual(commands.drop_leading_words("help you", greeting), "")
        self.assertEqual(commands.drop_leading_words("may I help you open Chrome.", greeting), "open Chrome.")
        self.assertEqual(commands.drop_leading_words("How are you?", greeting), "How are you?")
        self.assertEqual(commands.drop_leading_words("Open Chrome.", greeting), "Open Chrome.")

    def test_mishearings_only_count_as_words_alone(self):
        for phrase in ("Same.", "Send it.", "Seems good, sense since.", "Okay, send.", "Sent it"):
            self.assertTrue(is_send_mishearing(phrase), phrase)
        for phrase in ("Same as before", "Okay, sir.", "Uh", "It's the same app which I made.", "", "Maybe you don't."):
            self.assertFalse(is_send_mishearing(phrase), phrase)
        self.assertEqual(parse("Uh open Google."), [open_("Google")])
        self.assertEqual(parse("Um, close Spotify."), [Action("window", "Spotify", "close")])
        self.assertEqual(parse("Type this is my day send it."), [Action("type", "this is my day"), press("send")])
        self.assertEqual(canon(parse("Open closed.")[0].arg), "claude")

    def test_click_ignores_words_inside_long_descriptions(self):
        def item(name, kind=uia.BUTTON):
            return uia.Item(name, kind, 0, 0, 10, 10, True, None)

        description = item("Arrow keys move the tile. Perpendicular arrows preview a split; press Enter to commit or Escape to cancel.")
        self.assertIsNone(uia.best_match("enter", [description]))
        self.assertEqual(uia.best_match("settings", [item("Open settings menu")]).name, "Open settings menu")


class RemovingTextTests(unittest.TestCase):
    def test_remove_everything(self):
        for phrase in ("Remove all text.", "Clear all.", "Delete everything.", "Remove all the text.", "Clear the text."):
            self.assertEqual(parse(phrase), [press("clear_all")], phrase)

    def test_remove_part(self):
        self.assertEqual(parse("Remove the last word."), [Action("erase", "1", "words")])
        self.assertEqual(parse("Delete that word."), [Action("erase", "1", "words")])
        self.assertEqual(parse("Delete last three words."), [Action("erase", "3", "words")])
        self.assertEqual(parse("Remove the last sentence."), [Action("erase", site="sentence")])
        self.assertEqual(parse("Remove the word actually."), [Action("erase", "actually", "named")])
        self.assertEqual(parse("Remove that."), [press("undo")])

    def test_text_changes(self):
        self.assertEqual(actions._without_word("I am actually very actually happy.", "actually"), "I am actually very happy.")
        self.assertEqual(actions._without_word("Fix this, please.", "please"), "Fix this,.")
        self.assertEqual(actions._without_word("Nothing here.", "missing"), "Nothing here.")
        self.assertEqual(actions._without_last_sentence("First one. Second one. Third one."), "First one. Second one.")
        self.assertEqual(actions._without_last_sentence("Only one"), "")
        self.assertEqual(actions._without_last_words("Hello there world.", 1), "Hello there")
        self.assertEqual(actions._without_last_words("First sentence. Second part here.", 2), "First sentence. Second")
        self.assertEqual(actions._without_last_words("Two words", 5), "")

    def test_page_furniture_is_not_an_answer(self):
        blocks = ["Skip to main content Accessibility help Go to Google Home Sign in Shopping Images", "A classic steel watch with a clean blue dial and great water resistance."]
        self.assertEqual(summary.page_text(blocks), blocks[1])


class SummaryTests(unittest.TestCase):
    ANSWER = (
        "Sure! Here are some options:\n\n"
        "## Best watches\n\n"
        "The Titan Neo is the best watch under 10,000 rupees for most people. "
        "It has a sapphire crystal and a two year warranty.\n\n"
        "- **Fossil Grant** is a stylish watch with a leather strap.\n"
        "- The Casio Edifice is a sporty watch that keeps accurate time.\n\n"
        "```python\nprint('ignore me')\n```\n"
        "Overall, the Titan Neo watch offers the best value under 10,000 rupees."
    )

    def test_asking(self):
        for phrase in ("Summarize the response.", "Summarise this.", "Summarize.", "Give me a summary.", "What's the summary?", "Read the response."):
            self.assertEqual(parse(phrase), [Action("summarize")], phrase)

    def test_summary_is_short_and_starts_with_the_answer(self):
        short = summary.summarize_text(self.ANSWER)
        self.assertTrue(short.startswith("The Titan Neo"), short)
        self.assertLessEqual(len(short.split()), summary.MAX_SUMMARY_WORDS)
        for unwanted in ("Sure", "##", "**", "print", "options:"):
            self.assertNotIn(unwanted, short)

    def test_nothing_to_summarize(self):
        self.assertEqual(summary.summarize_text(""), "")
        self.assertEqual(summary.summarize_text("Too short."), "")

    def test_google_ai_overview_is_picked_out(self):
        blocks = ["Search results", "AI Overview", "The Titan Neo is a great watch.", "AI responses may include mistakes.", "Other result text here"]
        self.assertEqual(summary.ai_overview(blocks).strip(), "The Titan Neo is a great watch.")
        self.assertEqual(summary.ai_overview(["No overview on this page"]), "")

    def test_latest_copy_button_is_the_lowest(self):
        def button(name, top):
            return uia.Item(name, uia.BUTTON, 0, top, 10, top + 10, True, None)

        found = summary.lowest_copy_button([button("Copy", 100), button("Share", 900), button("Copy", 600)])
        self.assertEqual(found.top, 600)


class ReleaseSafetyTests(unittest.TestCase):
    def test_private_lines_stay_out_of_the_log(self):
        written = []
        stream = type("S", (), {"write": lambda self, t: written.append(t), "flush": lambda self: None})()
        log = app._PrivateLog(stream, keep_everything=False)
        for line in ('heard: "my password is hunter2"', "   typing: secret note", "   summary: private", "Ready. Say Jarvis"):
            print(line, file=log)
        self.assertEqual("".join(written), "Ready. Say Jarvis\n")

    def test_detailed_log_keeps_everything_when_chosen(self):
        written = []
        stream = type("S", (), {"write": lambda self, t: written.append(t), "flush": lambda self: None})()
        print('heard: "hello"', file=app._PrivateLog(stream, keep_everything=True))
        self.assertIn("heard", "".join(written))

    def test_routines_support_vs_code(self):
        self.assertEqual(routines.parse_text("[a]\nvscode C:\\x\n")["a"], [("vscode", "C:\\x")])

    def test_right_alt_can_be_left_alone(self):
        hotkey = audio.Hotkey()
        hotkey.alt_enabled = False
        hotkey._filter(0x100, type("K", (), {"vkCode": audio.VK_RIGHT_ALT, "flags": 0})())
        self.assertFalse(hotkey.pressed.is_set())

    def test_nothing_personal_in_the_defaults(self):
        self.assertEqual(prefs.Settings().chrome_profile, "")
        self.assertFalse(prefs.Settings().keep_debug_log)

    def test_setup_lists_steps_in_plain_words(self):
        self.assertEqual(setup_ui._step_text("vscode", r"C:\work\shop", {}), "Open shop in VS Code")
        self.assertEqual(setup_ui._step_text("chrome", "Profile 1", {"Profile 1": "Sam"}), "Open Chrome: Sam")


class RecognitionTests(unittest.TestCase):
    def test_real_mishearings_from_your_logs(self):
        for heard in ("Open closed.", "Open cloud.", "Open floor.", "Open throw.", "Open clothes.", "Open clawed."):
            self.assertEqual(canon(parse(heard)[0].arg), "claude", heard)

    def test_sounds_like(self):
        names = ["claude", "codex", "chatgpt", "chrome", "cursor", "gmail", "spotify", "whatsapp"]
        self.assertEqual(commands.sounds_like("klawd", names), "claude")
        self.assertEqual(commands.sounds_like("kursor", names), "cursor")
        self.assertEqual(commands.sounds_like("spotifi", names), "spotify")
        self.assertIsNone(commands.sounds_like("banana", names))
        self.assertIsNone(commands.sounds_like("table", names))

    def test_misheard_open(self):
        self.assertEqual(parse("Hopper Google"), [open_("Google")])
        self.assertEqual(parse("Oben Chrome."), [open_("Chrome")])
        self.assertEqual(parse("Copper government"), [])
        self.assertEqual(parse("Hopper something else"), [])

    def test_app_name_alone(self):
        self.assertEqual(parse("Claude."), [open_("Claude")])
        self.assertEqual(parse("Chat GPT."), [open_("Chat GPT")])
        self.assertEqual(parse("Maybe you don't."), [])
        self.assertEqual(parse("Okay."), [])


class AskAiTests(unittest.TestCase):
    def test_commands(self):
        self.assertEqual(parse("Ask Claude what is an SIP and how does it work?"), [Action("ask_ai", "what is an SIP and how does it work?", "claude")])
        self.assertEqual(parse("Ask ChatGPT, which is the best place in Thailand?"), [Action("ask_ai", "which is the best place in Thailand?", "chatgpt")])
        self.assertEqual(parse("Tell Claude to fix the login bug."), [Action("ask_ai", "fix the login bug.", "claude")])
        self.assertEqual(parse("Ask cloud about mutual funds."), [Action("ask_ai", "mutual funds.", "claude")])
        self.assertEqual(parse("Ask Claude."), [Action("ask_ai", "", "claude")])
        self.assertEqual(parse("Tell Priya on Slack that the build passed."), [Action("message", "Priya", "slack", "the build passed.")])

    def test_reply_is_what_comes_after_the_question(self):
        blocks = ["Earlier question", "Earlier answer here for you.", "What is an SIP?", "An SIP is a way to invest regularly.", "Claude can make mistakes."]
        self.assertEqual(summary.reply_text(blocks, "what is an SIP?", set()), "An SIP is a way to invest regularly.")

    def test_question_and_reply_merged_into_one_block(self):
        blocks = ["Earlier answer here. What is an SIP and how does it work? An SIP is a way to invest regularly."]
        self.assertEqual(summary.reply_text(blocks, "What is an SIP and how does it work", set()), "An SIP is a way to invest regularly.")

    def test_long_question_is_not_read_back(self):
        question = "one two three four five six seven eight nine ten eleven"
        self.assertEqual(summary.reply_text([f"{question.title()}?\nThe real reply is here."], question, set()), "The real reply is here.")

    def test_new_text_used_when_question_not_found(self):
        self.assertEqual(summary.reply_text(["Old text", "New reply text"], "something else", {"Old text"}), "New reply text")

    def test_half_finished_sentences_wait(self):
        reply = "An SIP is a way to invest regularly. It lets you put in"
        self.assertEqual(summary.finished_sentences(reply, False), ["An SIP is a way to invest regularly."])
        self.assertEqual(summary.finished_sentences(reply, True), ["An SIP is a way to invest regularly.", "It lets you put in"])
        self.assertEqual(summary.finished_sentences("It is a", False), [])


class VoiceTypingTests(unittest.TestCase):
    class Key:
        def __init__(self, vk, flags=0):
            self.vkCode, self.flags = vk, flags

    DOWN, UP = 0x100, 0x101

    def setUp(self):
        self.hotkey = audio.Hotkey()

    def send(self, message, vk, flags=0):
        return self.hotkey._filter(message, self.Key(vk, flags))

    def test_holding_right_ctrl_starts_typing_and_it_still_reaches_other_apps(self):
        self.assertIsNone(self.send(self.DOWN, audio.VK_RIGHT_CTRL))
        self.assertFalse(self.hotkey.typing_held())
        self.hotkey.type_pressed_at -= 1
        self.assertTrue(self.hotkey.typing_held())
        self.send(self.UP, audio.VK_RIGHT_CTRL)
        self.assertFalse(self.hotkey.typing_held())

    def test_a_shortcut_does_not_start_typing(self):
        self.send(self.DOWN, audio.VK_RIGHT_CTRL)
        self.send(self.DOWN, 0x43)  # Ctrl+C
        self.hotkey.type_pressed_at -= 1
        self.assertFalse(self.hotkey.typing_held())

    def test_keys_jarvis_presses_are_ignored(self):
        self.send(self.DOWN, audio.VK_RIGHT_CTRL, audio.KEY_INJECTED)
        self.assertFalse(self.hotkey.type_down.is_set())

    def test_spoken_edits(self):
        self.assertEqual(clean_dictation("first line new line second line"), "First line\nsecond line")
        self.assertEqual(clean_dictation("one. New paragraph. two"), "One\n\ntwo")
        self.assertEqual(clean_dictation("Send the report. Scratch that. Send the invoice."), "Send the invoice.")
        self.assertEqual(clean_dictation("keep this. send the report, scratch that, hello there"), "Keep this. hello there")


class RepeatAndLearningTests(unittest.TestCase):
    def test_repeat(self):
        for phrase in ("Do that again.", "Repeat that.", "Again.", "One more time."):
            self.assertEqual(parse(phrase), [Action("repeat")], phrase)

    def test_correction_phrases(self):
        self.assertEqual(parse("I meant Claude."), [Action("correct", "Claude")])
        self.assertEqual(parse("No, I said ChatGPT."), [Action("correct", "ChatGPT")])
        self.assertEqual(parse("I meant to open Spotify."), [Action("correct", "Spotify")])
        self.assertEqual(parse("When I say klaud, I mean Claude."), [Action("correct", "Claude", "klaud")])

    def test_learning_survives_and_applies(self):
        with tempfile.TemporaryDirectory() as folder:
            original_file, original_cache = commands.LEARNED_FILE, commands._learned_cache
            commands.LEARNED_FILE, commands._learned_cache = Path(folder) / "learned.json", None
            try:
                self.assertEqual(canon("zzclawdee"), "zzclawdee")
                self.assertEqual(commands.learn_name("zzclawdee", "Clawed"), "claude")
                commands._learned_cache = None  # as after a restart
                self.assertEqual(canon("Zzclawdee."), "claude")
            finally:
                commands.LEARNED_FILE, commands._learned_cache = original_file, original_cache


class WindowAndTabTests(unittest.TestCase):
    def check(self, heard, *expected):
        self.assertEqual(parse(heard), list(expected), heard)

    def test_apps(self):
        self.check("Close Spotify.", Action("window", "Spotify", "close"))
        self.check("Quit the Claude app.", Action("window", "Claude", "close"))
        self.check("Minimize Chrome.", Action("window", "Chrome", "minimize"))
        self.check("Maximise Cursor.", Action("window", "Cursor", "maximize"))

    def test_built_in_phrases_still_win(self):
        self.check("Close this tab.", press("close_tab"))
        self.check("Close this window.", press("close_window"))
        self.check("Minimize this window.", press("minimize"))
        self.check("Minimize everything.", press("desktop"))
        self.check("Open a new tab.", press("new_tab"))
        self.check("Next tab.", press("next_tab"))

    def test_tabs(self):
        self.check("Go to the Gmail tab.", Action("tab", "Gmail", "go"))
        self.check("Switch to YouTube tab.", Action("tab", "YouTube", "go"))
        self.check("Close the Gmail tab.", Action("tab", "Gmail", "close"))

    def test_tab_matching(self):
        def tab(name, kind=uia.TABITEM):
            return uia.Item(name, kind, 0, 0, 10, 10, False, None)

        tabs = [tab("Inbox (3) - sam@example.com - Example Mail - Memory usage - 80 MB"), tab("Gmail - Sign in"), tab("Pull requests - GitHub"), tab("Gmail", uia.BUTTON)]
        self.assertEqual(uia.best_tab("Gmail", tabs).name, "Gmail - Sign in")
        self.assertEqual(uia.best_tab("pull requests", tabs).name, "Pull requests - GitHub")
        self.assertIsNone(uia.best_tab("Reddit", tabs))
        self.assertEqual(uia.best_tab("git hub", tabs).name, "Pull requests - GitHub")


class ClipboardHistoryTests(unittest.TestCase):
    def test_commands(self):
        for phrase, number in (("Paste the second last thing I copied.", "2"), ("Paste the third one.", "3"), ("Paste the previous copy.", "2"), ("Paste the last thing I copied.", "1"), ("Paste clipboard item 4.", "4"), ("Paste from clipboard number two.", "2")):
            self.assertEqual(parse(phrase), [Action("clip", number, "nth")], phrase)
        self.assertEqual(parse("Paste the one about invoice."), [Action("clip", "invoice", "about")])
        self.assertEqual(parse("Show clipboard history."), [Action("clip", site="list")])
        self.assertEqual(parse("Paste that."), [press("paste")])

    def test_history_order(self):
        history = clipboard.ClipboardHistory()
        for text in ("first", "second invoice", "third", "first"):
            history.remember(text)
        self.assertEqual(list(history.items), ["first", "third", "second invoice"])
        self.assertEqual(history.nth(2), "third")
        self.assertIsNone(history.nth(9))
        self.assertEqual(history.containing("INVOICE"), "second invoice")
        history.remember("   ")
        self.assertEqual(len(history.items), 3)


class CalculatorTests(unittest.TestCase):
    def test_sums(self):
        for text, answer in (("18 percent of 2500", 450), ("25 times 40", 1000), ("1,200 divided by 8", 150), ("100 plus 18%", 118), ("500 minus 10 percent", 450), ("two lakh plus fifty thousand", 250000), ("add 5 and 6", 11), ("subtract 3 from 10", 7), ("multiply 7 by 8", 56), ("divide 9 by 3", 3), ("square root of 144", 12), ("12 squared", 144), ("twenty five times four", 100), ("2 lakh into 3", 600000)):
            self.assertAlmostEqual(calc.evaluate(text), answer, msg=text)

    def test_not_sums_or_unsafe(self):
        for text in ("the date", "the capital of France", "42", "__import__('os')", "9 ** 9 ** 9", "1 divided by 0", "open chrome"):
            self.assertIsNone(calc.evaluate(text), text)

    def test_commands(self):
        self.assertEqual(parse("What's 18 percent of 2500?"), [Action("calc", "18 percent of 2500")])
        self.assertEqual(parse("Calculate 25 times 40."), [Action("calc", "25 times 40")])
        self.assertEqual(parse("25 times 40."), [Action("calc", "25 times 40")])
        self.assertEqual(parse("What time is it?"), [Action("chat", "time")])

    def test_spoken_answers(self):
        self.assertEqual(calc.spoken_number(450.0), "450")
        self.assertEqual(calc.spoken_number(1 / 3), "0.3333")


class FileTests(unittest.TestCase):
    def test_commands(self):
        self.assertEqual(parse("Find the invoice PDF."), [Action("find", "invoice PDF", "show")])
        self.assertEqual(parse("Where is my resume?"), [Action("find", "resume", "show")])
        self.assertEqual(parse("Open the budget file."), [Action("find", "budget", "open")])
        self.assertEqual(parse("Open my tax document."), [Action("find", "tax document", "open")])
        self.assertEqual(parse("Open my latest download."), [Action("latest", "download")])
        self.assertEqual(parse("Show me the last screenshot."), [Action("latest", "screenshot")])

    def test_web_and_app_commands_are_unchanged(self):
        self.assertEqual(parse("Find cats on YouTube."), [Action("search", "cats", "youtube")])
        self.assertEqual(parse("Open Google Sheets."), [Action("open", "Google Sheets")])
        self.assertEqual(parse("Open Word."), [Action("open", "Word")])

    def test_query_split(self):
        self.assertEqual(files.split_query("the invoice PDF"), (["invoice"], (".pdf",)))
        self.assertEqual(files.split_query("my latest videos"), ([], files.KINDS["video"]))
        self.assertEqual(files.split_query("budget"), (["budget"], ()))
        self.assertEqual(files.split_query("it's; drop table"), (["it", "s", "drop", "table"], ()))

    def test_programs_are_never_launched(self):
        for path in ("setup.exe", "run.BAT", "a.ps1", "b.lnk"):
            self.assertFalse(files.can_open(path), path)
        self.assertTrue(files.can_open("report.pdf"))


class TerminalTests(unittest.TestCase):
    TEXT = (
        "[projects]\nfrontend = C:\\f\nbackend = C:\\b\n\n[commands]\n"
        "git status | status = git status --short --branch\n"
        "git push = ask: git push\n"
        "start | run [frontend] = terminal: npm start\n"
        "start | run [backend] = terminal: npm run serve:apis:local\n"
        "broken line without equals\n"
    )

    def setUp(self):
        self.setup = terminal.parse_text(self.TEXT)

    def match(self, heard):
        found = terminal.match(heard, self.setup)
        return (found[0].line, found[1]) if found else None

    def test_flags(self):
        self.assertTrue(terminal.find("git push", "backend", self.setup).ask)
        self.assertTrue(terminal.find("run", "backend", self.setup).in_terminal)

    def test_ways_of_saying_it(self):
        status = "git status --short --branch"
        self.assertEqual(self.match("Git status in backend."), (status, "backend"))
        self.assertEqual(self.match("status of the frontend"), (status, "frontend"))
        self.assertEqual(self.match("Backend git status"), (status, "backend"))
        self.assertEqual(self.match("Get status in backend."), (status, "backend"))

    def test_each_project_gets_its_own_start(self):
        self.assertEqual(self.match("Start frontend."), ("npm start", "frontend"))
        self.assertEqual(self.match("Run the backend."), ("npm run serve:apis:local", "backend"))

    def test_only_listed_commands_can_run(self):
        for heard in ("delete everything in backend", "rm backend", "open Chrome", "Start Chrome", "format frontend drive", ""):
            self.assertIsNone(self.match(heard), heard)

    def test_spoken_results(self):
        status = "git status --short --branch"
        self.assertEqual(terminal.spoken_result(status, 0, "## develop...origin/develop\n"), "On develop. Nothing to commit.")
        self.assertEqual(terminal.spoken_result(status, 0, "## main...origin/main [behind 2]\n M a.ts\n?? b.ts\n"), "On main. Behind 2. 2 files changed.")
        self.assertEqual(terminal.spoken_result("git pull", 0, "Already up to date.\n"), "Already up to date.")
        self.assertEqual(terminal.spoken_result("git pull", 1, "fatal: not a repo\n"), "That failed. fatal: not a repo")
        self.assertEqual(terminal.spoken_result("x", 0, ""), "Done.")


class RoutineTests(unittest.TestCase):
    TEXT = "# a comment\n[start work]\ncursor C:\\a\\frontend\ncursor C:\\a\\backend\nchrome Profile 2\nnonsense line\n\n[wind down]\nopen Spotify\n"

    def test_file_format(self):
        found = routines.parse_text(self.TEXT)
        self.assertEqual(found["start work"], [("cursor", "C:\\a\\frontend"), ("cursor", "C:\\a\\backend"), ("chrome", "Profile 2")])
        self.assertEqual(found["wind down"], [("open", "Spotify")])

    def test_ways_of_saying_it(self):
        found = routines.parse_text(self.TEXT)
        for phrase in ("Start work.", "Let's start work.", "Start my work", "Okay, start work please", "Jarvis start work"):
            self.assertEqual(routines.match(phrase, found), "start work", phrase)
        self.assertIsNone(routines.match("Start Chrome", found))
        self.assertIsNone(routines.match("", found))


class ReminderTests(unittest.TestCase):
    NOW = datetime(2026, 11, 8, 14, 20)

    def request(self, raw):
        return reminders.parse_request(raw, self.NOW)

    def test_commands(self):
        self.assertEqual(parse("Remind me in 20 minutes to call Rahul and Priya."), [Action("remind", "in 20 minutes to call Rahul and Priya")])
        for phrase, length in (("Set a timer for 10 minutes.", "10 minutes"), ("Timer 5 minutes", "5 minutes"), ("10 minute timer", "10 minute"), ("Start a timer for one hour.", "one hour")):
            self.assertEqual(parse(phrase), [Action("timer", length)], phrase)
        self.assertEqual(parse("Cancel the timer."), [Action("reminders", "cancel_timer")])
        self.assertEqual(parse("Jarvis cancel all reminders."), [Action("reminders", "cancel_reminder")])
        self.assertEqual(parse("How much time is left?"), [Action("reminders", "list")])
        self.assertFalse(commands.says_stop("Jarvis cancel the timer"))
        self.assertTrue(commands.says_stop("Jarvis cancel"))

    def test_relative_times(self):
        self.assertEqual(self.request("in 20 minutes to call Rahul"), ("Call Rahul", datetime(2026, 11, 8, 14, 40)))
        self.assertEqual(self.request("to call Rahul in 20 minutes"), ("Call Rahul", datetime(2026, 11, 8, 14, 40)))
        self.assertEqual(self.request("after an hour to drink water"), ("Drink water", datetime(2026, 11, 8, 15, 20)))
        self.assertEqual(self.request("in half an hour to stretch"), ("Stretch", datetime(2026, 11, 8, 14, 50)))
        self.assertEqual(self.request("in 1 hour and 30 minutes to leave"), ("Leave", datetime(2026, 11, 8, 15, 50)))

    def test_clock_times(self):
        self.assertEqual(self.request("at 5 PM to call Rahul"), ("Call Rahul", datetime(2026, 11, 8, 17, 0)))
        self.assertEqual(self.request("tomorrow at 9 a.m. to pay rent"), ("Pay rent", datetime(2026, 11, 9, 9, 0)))
        self.assertEqual(self.request("to pay rent tomorrow"), ("Pay rent", datetime(2026, 11, 9, 10, 0)))

    def test_no_time_given(self):
        self.assertEqual(self.request("to call Rahul"), ("Call Rahul", None))

    def test_durations(self):
        for text, seconds in (("10 minutes", 600), ("one hour", 3600), ("half an hour", 1800), ("an hour and a half", 5400), ("1 hour 30 minutes", 5400), ("90 seconds", 90), ("10 minute", 600), ("twenty minutes", 1200)):
            self.assertEqual(reminders.parse_duration(text), seconds, text)
        self.assertIsNone(reminders.parse_duration("a while"))

    def test_descriptions(self):
        self.assertEqual(reminders.describe_duration(5400), "1 hour 30 minutes")
        self.assertEqual(reminders.describe_time(datetime(2026, 11, 8, 17, 5), self.NOW), "at 5:05 PM")
        self.assertEqual(reminders.describe_time(datetime(2026, 11, 9, 9, 0), self.NOW), "tomorrow at 9:00 AM")

    def test_saved_and_fired(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "r.json"
            fired = []
            first = reminders.Reminders(lambda kind, text: fired.append((kind, text)), path)
            first.add("reminder", "Call Rahul", self.NOW)
            first.add("timer", "5 minutes", self.NOW + timedelta(hours=1))
            reloaded = reminders.Reminders(lambda kind, text: fired.append((kind, text)), path)
            reloaded.fire_due(self.NOW)
            self.assertEqual(fired, [("reminder", "Call Rahul")])
            reloaded.fire_due(self.NOW)
            self.assertEqual(len(fired), 1)
            self.assertEqual(reloaded.cancel("timer"), 1)
            self.assertEqual(reloaded.upcoming(), [])


class PcControlTests(unittest.TestCase):
    def test_commands(self):
        for phrase, op in (("Lock my PC.", "lock"), ("Shut down.", "shut_down"), ("Restart the computer.", "restart"), ("What's my battery?", "battery"),
                           ("Increase the brightness.", "brightness_up"), ("Dim the screen.", "brightness_down"), ("Open Task Manager.", "task_manager"),
                           ("Turn on Wi-Fi.", "wifi_on"), ("Turn Bluetooth off.", "bluetooth_off"), ("Wi-Fi off.", "wifi_off"), ("Put my laptop to sleep.", "sleep_pc")):
            self.assertEqual(parse(phrase), [Action("pc", op)], phrase)
        self.assertEqual(parse("Set brightness to 40."), [Action("pc", "set_brightness", "40")])

    def test_going_to_sleep_still_means_jarvis(self):
        self.assertEqual(parse("Go to sleep."), [Action("sleep")])

    def test_windows(self):
        self.assertEqual(parse("Snap left."), [Action("snap", "", "left")])
        self.assertEqual(parse("Move this window to the right."), [Action("snap", "", "right")])
        self.assertEqual(parse("Put Chrome on the left."), [Action("snap", "Chrome", "left")])

    def test_power_actions_always_ask_first(self):
        self.assertEqual(set(actions.PC_CONFIRM), {"shut_down", "restart", "sign_out"})


class NewChatTests(unittest.TestCase):
    def check(self, heard, *expected):
        self.assertEqual(parse(heard), list(expected), heard)

    def test_new_chat_in_the_current_app(self):
        for phrase in ("New chat.", "Open new chat.", "Okay, open a new chat.", "Start a new session.", "Open a new conversation."):
            self.check(phrase, Action("new_chat"))

    def test_new_chat_in_a_named_app(self):
        self.check("Open new chat in Claude.", Action("new_chat", "claude"))
        self.check("Start a new chat on ChatGPT.", Action("new_chat", "chatgpt"))
        self.check("Open Codex new session.", Action("new_chat", "codex"))
        self.check("New chat in clawed.", Action("new_chat", "claude"))

    def test_chains(self):
        self.check("Enter and open new chat.", press("enter"), Action("new_chat"))
        self.check("Open new chat and type hello there.", Action("new_chat"), Action("type", "hello there."))

    def test_tabs_are_not_chats(self):
        self.check("Open a new tab.", press("new_tab"))

    def test_replies_are_prepared_ahead(self):
        lines = persona.all_lines("Sam")
        self.assertIn("Good morning, Sam. What are we going to do today?", lines)
        self.assertIn("Opening Claude.", lines)
        self.assertFalse([line for line in lines if "{" in line])
        self.assertIn(persona.acknowledge(Action("new_chat")), ("Starting a new chat.", "Fresh start."))


class MicrophoneChoiceTests(unittest.TestCase):
    LAPTOP = (1, "Microphone Array (Realtek(R) Au")

    def test_automatic_prefers_a_connected_headset(self):
        for name in ("Headset (Meta Ray-Ban Hands-Fr", "Headphones (OnePlus Buds)", "Earphone Mic (USB)", "Hands-Free AG Audio"):
            self.assertEqual(audio.choose_input("", [self.LAPTOP, (2, name)]), 2, name)

    def test_automatic_without_headset_uses_windows_default(self):
        self.assertIsNone(audio.choose_input("", [self.LAPTOP]))

    def test_named_microphone_wins_and_falls_back_when_gone(self):
        headset = (2, "Headset (Buds)")
        self.assertEqual(audio.choose_input(self.LAPTOP[1], [self.LAPTOP, headset]), 1)
        self.assertIsNone(audio.choose_input("Unplugged Mic", [self.LAPTOP]))

    def test_leveler_lifts_quiet_speech_and_leaves_loud_alone(self):
        quiet = np.full(1280, 200, dtype=np.int16)
        self.assertGreater(audio.Leveler().apply(quiet).max(), 2000)
        loud = np.full(1280, 12000, dtype=np.int16)
        self.assertEqual(audio.Leveler().apply(loud).max(), 12000)


class PersonalityTests(unittest.TestCase):
    def tearDown(self):
        commands.set_wake_name("Jarvis")

    def test_greeting(self):
        line = persona.greeting("Sam Lee", datetime(2026, 11, 8, 9, 0))
        self.assertTrue(line.startswith("Good morning, Sam Lee. "), line)
        self.assertTrue(line.endswith("?"), line)
        self.assertIn("afternoon", persona.salutation("sir", datetime(2026, 11, 8, 14, 0)))
        self.assertIn("evening", persona.salutation("sir", datetime(2026, 11, 8, 20, 0)))

    def test_every_spoken_action_gets_a_reply_and_keys_stay_silent(self):
        self.assertTrue(persona.acknowledge(Action("open", "Claude")))
        self.assertTrue(persona.acknowledge(Action("agents", "3", "claude")))
        self.assertEqual(persona.acknowledge(Action("press", "scroll_down")), "")

    def test_your_name_appears_only_in_the_greeting(self):
        without_greetings = [line for line in persona.all_lines("Sam") if not line.startswith("Good ")]
        self.assertTrue(without_greetings)
        self.assertFalse([line for line in without_greetings if "Sam" in line])

    def test_custom_wake_name(self):
        commands.set_wake_name("Hey Friday")
        self.assertFalse(commands.uses_default_wake())
        self.assertEqual(commands.text_after_wake_name("Hey Friday, open Chrome."), "open Chrome.")
        self.assertEqual(commands.text_after_wake_name("Friday."), "")
        self.assertEqual(commands.text_after_wake_name("Fryday open Chrome"), "open Chrome")
        self.assertIsNone(commands.text_after_wake_name("What a nice day"))
        self.assertEqual(parse("Hey Friday, open Chrome."), [open_("Chrome")])

    def test_stop(self):
        for phrase in ("Jarvis stop.", "Hey Jarvis, stop", "fix the login page, Jarvis stop", "Jarvis, stop listening.", "Jarvis please stop"):
            self.assertTrue(commands.says_stop(phrase), phrase)
        for phrase in ("Stop the build", "Jarvis open Chrome", "Don't stop"):
            self.assertFalse(commands.says_stop(phrase), phrase)
        self.assertEqual(parse("Stop listening."), [])
        commands.set_wake_name("Friday")
        self.assertTrue(commands.says_stop("Friday stop."))
        self.assertFalse(commands.says_stop("Jarvis stop."))

    def test_misheard_stop_on_its_own(self):
        for phrase in ("Service stop.", "Jervis stop", "Travis stop.", "Jarvis stops.", "Davis stop", "Hey, Javis, stop.", "Jarvis stopped", "Jarvis stop listening."):
            self.assertTrue(commands.is_stop_phrase(phrase) or commands.says_stop(phrase), phrase)
        for phrase in ("Bus stop.", "Open Chrome", "Stop the build", "Please wait a bit longer then stop", "", "Service"):
            self.assertFalse(commands.is_stop_phrase(phrase), phrase)

    def test_stop_inside_dictation_stays_strict(self):
        self.assertFalse(commands.says_stop("the customer service stop working yesterday"))
        self.assertTrue(commands.says_stop("fix the page, Jarvis stop"))
        self.assertTrue(commands.says_stop("fix the page, Travis stop"))

    def test_misheard_stop_follows_a_custom_name(self):
        commands.set_wake_name("Friday")
        self.assertTrue(commands.is_stop_phrase("Fryday stop."))
        self.assertFalse(commands.is_stop_phrase("Service stop."))

    def test_two_word_wake_name(self):
        commands.set_wake_name("Mister Robot")
        self.assertEqual(commands.text_after_wake_name("Hey Mister Robot, go back."), "go back.")

    def test_dismiss_and_chat(self):
        for phrase in ("Thank you.", "Thank you, Jarvis.", "That's all.", "Goodbye."):
            self.assertTrue(is_dismiss(phrase), phrase)
        self.assertFalse(is_dismiss("Open Claude"))
        self.assertEqual(parse("What time is it?"), [Action("chat", "time")])
        self.assertEqual(parse("How are you?"), [Action("chat", "status")])


if __name__ == "__main__":
    unittest.main()
