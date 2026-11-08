"""Jarvis's listening loop: wake it, then keep talking until the conversation goes quiet."""
import time
from datetime import datetime, timedelta

import numpy as np

from . import commands, config, persona, routines, terminal, winctl
from . import settings as prefs
from .actions import Actions
from .clipboard import ClipboardHistory
from .audio import Hotkey, Mic, Recorder, Transcriber, WakeWord, audio_device_state, chime
from .commands import (
    Action, clean_dictation, drop_leading_words, is_cancel, is_stop_phrase, is_dismiss, is_send_mishearing, is_yes, parse, says_stop, split_send,
    strip_wake, text_after_wake_name,
)
from .reminders import Reminders
from .voice import Voice

SETTINGS_CHECK_SECONDS = 2.0
MIC_CHECK_SECONDS = 3.0
MIC_STALL_SECONDS = 4.0  # no audio for this long means the device went away


class Jarvis:
    def __init__(self) -> None:
        self.settings = prefs.load()
        self.settings_time = prefs.modified_at()
        self.checked_settings_at = 0.0
        commands.set_wake_name(self.settings.wake_name)
        print(f"Loading speech model ({config.speech_tier()})...")
        self.voice = Voice(self.settings.voice_speed, self.settings.voice)
        self.transcriber = Transcriber()
        self.wake = WakeWord()
        self.mic = Mic(self.settings.microphone)
        self.mic.gate = self.voice.mic_closed  # Jarvis must not hear itself
        self.hotkey = Hotkey()
        self.apply_hotkey_setting()
        self.recorder = Recorder(self.mic, self.hotkey)
        self.last_actions: list = []  # for "do that again"
        self.clipboard_history = ClipboardHistory()
        self.reminders = Reminders(self.on_reminder)
        self.notify = None  # shows a Windows notification, once the tray icon exists
        self.actions = Actions(
            ask=self.ask, hear=self.hear_dictation, say=self.say_result, speak=self.read_aloud, reminders=self.reminders,
            clipboard_history=self.clipboard_history,
        )
        self.long_reply = ""  # a summary being read out, which you can talk over
        self.asleep = False
        self.stopped = False  # set by "Jarvis stop"; ends the current conversation
        self.active = False  # a conversation is open, so the on-screen indicator shows
        self.typed_at = 0.0  # when unsent text was last typed, since "send it" is then the likely next words
        self.opening_text = ""  # the greeting just spoken, in case the mic picked it up
        self.checked_mic_at = time.monotonic()
        self.mic_state = ""
        self.last_greeted: datetime | None = None

    @property
    def name(self) -> str:
        return self.settings.user_name.strip() or "sir"

    def apply_hotkey_setting(self) -> None:
        """Right Alt is left alone on keyboards that need it to type symbols."""
        self.hotkey.alt_enabled = self.settings.use_right_alt and not winctl.right_alt_types_symbols()

    @property
    def just_typed(self) -> bool:
        return self.typed_at > 0 and time.monotonic() - self.typed_at < config.SEND_AFTER_TYPING_SECONDS

    def say(self, text: str) -> None:
        if self.settings.talk_back:
            self.voice.say(text)

    def say_result(self, what: str) -> None:
        self.say({"sent": persona.sent, "not_sent": persona.not_sent}[what]())

    def on_reminder(self, kind: str, text: str) -> None:
        """Always spoken, even with replies turned off: you asked to be told."""
        line = persona.reminder_due(kind, text)
        print(f"{datetime.now():%H:%M:%S} {line}")
        chime("reminder")
        self.voice.say(line)
        if self.notify:
            try:
                self.notify(line, "Jarvis")
            except Exception as error:
                print(f"   could not show a notification: {error!r}")

    def read_aloud(self, text: str) -> None:
        self.voice.say(text)
        self.long_reply = f"{self.long_reply} {text}".strip()

    def voice_typing(self) -> None:
        """Hold Right Ctrl and talk: your words are typed wherever the cursor is when you let go."""
        key = self.hotkey
        self.active = True
        self.recorder.listening = True
        try:
            self.voice.interrupt()
            chime("listen")
            frames = self.mic.take_since(key.type_pressed_at)
            started = time.monotonic()
            while key.type_down.is_set() and not key.type_cancelled and time.monotonic() - started < config.MAX_DICTATION_SECONDS:
                frame = self.mic.read(0.2)
                if frame is not None:
                    frames.append(frame)
            stop_at = time.monotonic() + config.TYPE_RELEASE_TAIL
            while time.monotonic() < stop_at:
                frame = self.mic.read(0.1)
                if frame is not None:
                    frames.append(frame)
            self.recorder.listening = False
            if key.type_cancelled or sum(map(len, frames)) < config.MIN_TYPING_SECONDS * config.SAMPLE_RATE:
                return
            heard = self.transcriber.transcribe(np.concatenate(frames).astype(np.float32) / 32768.0)
            print(f'voice typing heard: "{heard}"')
            if self.is_stop(heard) or not clean_dictation(heard):
                return
            text, wants_send = split_send(heard)
            if text:
                self.actions.type_text(text)
                chime("done")
            if wants_send or self.settings.enter_after_typing:
                self.actions.run(Action("press", "send"))
                self.typed_at = 0.0
            else:
                self.typed_at = time.monotonic()
        except Exception as error:
            print(f"   voice typing failed: {error!r}")
            chime("error")
        finally:
            self.recorder.listening = False
            self.active = False
            self.wake.reset()

    def display_state(self) -> tuple[str | None, float]:
        """What the on-screen indicator should show, and the current voice level."""
        if self.voice.busy():
            return "speaking", 0.0
        if not self.active:
            return None, 0.0
        return ("listening" if self.recorder.listening else "working"), self.mic.leveler.level

    def run(self) -> None:
        self.mic_state = self.read_device_state() or ""
        self.mic.start()
        self.hotkey.start()
        self.say(persona.online())
        self.voice.prepare(persona.all_lines(self.name))
        self.reminders.start()
        self.clipboard_history.start()
        print(f'Ready. Say "{self.settings.wake_name}", or tap or hold Right Alt.')
        while True:
            self.reload_settings()
            self.check_microphone()
            if self.hotkey.typing_held():
                self.voice_typing()
            elif self.hotkey.pressed.is_set():
                self.hotkey.pressed.clear()
                self.guarded(held=True)
            elif self.asleep:
                self.mic.read()
            else:
                self.listen_for_wake()

    def reload_settings(self) -> None:
        now = time.monotonic()
        if now - self.checked_settings_at < SETTINGS_CHECK_SECONDS:
            return
        self.checked_settings_at = now
        changed = prefs.modified_at()
        if changed != self.settings_time:
            self.settings_time = changed
            self.settings = prefs.load()
            self.apply_hotkey_setting()
            self.voice.speed = self.settings.voice_speed
            self.voice.name = self.settings.voice
            self.voice.prepare(persona.all_lines(self.name))
            commands.set_wake_name(self.settings.wake_name)
            print(f'settings updated: wake word "{self.settings.wake_name}", calling you "{self.name}"')
            if self.mic.preferred != self.settings.microphone:
                self.mic.preferred = self.settings.microphone
                self.mic.restart()

    def read_device_state(self) -> str | None:
        try:
            return audio_device_state()
        except Exception as error:
            print(f"   could not check audio devices: {error!r}")
            return None

    def check_microphone(self) -> None:
        """Follows earphones and glasses as they connect and disconnect, between conversations."""
        now = time.monotonic()
        if now - self.checked_mic_at < MIC_CHECK_SECONDS or self.voice.busy():
            return
        self.checked_mic_at = now
        state = self.read_device_state()
        if state is None:
            return
        stalled = now - self.mic.last_frame_at > MIC_STALL_SECONDS
        if state != self.mic_state or stalled:
            self.mic_state = state
            print("audio devices changed" if not stalled else "microphone stopped sending audio")
            self.mic.restart()

    def listen_for_wake(self) -> None:
        """Two ways to wake. The trained "Hey Jarvis" model is instant but can miss real voices and accents,
        so each phrase is also transcribed and checked. A custom name relies on the second way alone.
        """
        early = self.wake.heard if commands.uses_default_wake() else None
        audio = self.recorder.record(config.WAKE_POLL, config.COMMAND_SILENCE, config.WAKE_PHRASE_MAX_SECONDS, early=early)
        if self.recorder.woke:
            self.guarded()
            return
        if audio is None:
            return
        heard = self.transcriber.transcribe(audio)
        rest = text_after_wake_name(heard)
        if rest is not None:
            self.guarded(spoken=rest)
        elif self.just_typed and is_send_mishearing(heard):
            print(f'heard without the wake word: "{heard}"')
            self.guarded(spoken="send it")

    def guarded(self, held: bool = False, spoken: str | None = None) -> None:
        """One failed command, such as an app that will not launch, must not stop Jarvis."""
        self.active = True
        try:
            self.conversation(held, spoken)
        except Exception as error:
            print(f"   that failed: {error!r}")
            chime("error")
            self.say(persona.failed())
        finally:
            self.active = False
        self.wake.reset()

    def greeting_due(self) -> bool:
        return self.last_greeted is None or datetime.now() - self.last_greeted > timedelta(hours=config.GREETING_GAP_HOURS)

    def record_command(self, start_timeout: float, held: bool = False):
        if not held and self.voice.busy():
            return self.listen_over_speech(start_timeout, self.voice.recent_lines())  # so "Jarvis stop" works mid-reply
        self.voice.finish()
        return self.recorder.record(start_timeout, config.COMMAND_SILENCE, config.MAX_COMMAND_SECONDS, held)

    def stop_now(self) -> None:
        self.voice.interrupt()
        self.stopped = True
        print("   stopped listening")
        self.say(persona.cancelled())

    def is_stop(self, heard: str) -> bool:
        return says_stop(heard) or is_cancel(strip_wake(heard)) or is_stop_phrase(heard)

    def tail_says_stop(self, tail) -> bool:
        """Checked at each pause in dictation, so "Jarvis stop" works without waiting for silence."""
        if says_stop(self.transcriber.transcribe(tail)):
            self.stop_now()
            return True
        return False

    def listen_over_speech(self, seconds: float, spoken_text: str):
        """You can talk over Jarvis here: the moment you do, it stops speaking and takes your command."""
        self.opening_text = spoken_text
        self.voice.interruptible = True
        try:
            return self.recorder.record(
                seconds, config.COMMAND_SILENCE, config.MAX_COMMAND_SECONDS, on_speech=self.voice.interrupt,
            )
        finally:
            self.voice.interruptible = False

    def greet_and_listen(self):
        line = self.opening_line()
        self.say(line)
        return self.listen_over_speech(self.settings.listen_seconds, line)

    def conversation(self, held: bool, spoken: str | None) -> None:
        self.stopped = False
        self.opening_text = ""
        self.long_reply = ""
        print(f"{datetime.now():%H:%M:%S} woke ({'hotkey' if held else 'voice'})")
        chime("listen")
        audio = None
        typed_ahead = spoken or None
        if held:
            audio = self.record_command(config.START_TIMEOUT, held=True)
        elif not typed_ahead:
            # Spoken in one breath ("Hey Jarvis, open Chrome") skips the greeting and goes straight to work.
            audio = self.record_command(config.GREET_AFTER) if spoken is None else None
            if audio is None and not self.hotkey.pressed.is_set():
                audio = self.greet_and_listen()
        if audio is None and not typed_ahead:
            print("   nothing heard after waking")
            return

        deadline = time.monotonic() + self.settings.listen_seconds
        first = True
        while True:
            heard = typed_ahead or self.transcriber.transcribe(audio)
            typed_ahead = None
            print(f'heard: "{heard}"')
            if self.opening_text:
                heard = drop_leading_words(heard, self.opening_text)
                self.opening_text = ""
            command = strip_wake(heard)
            if self.is_stop(heard):
                self.stop_now()
                return
            if is_dismiss(command):
                self.say(persona.farewell())
                return
            actions = self.understand(command)
            if not actions and self.just_typed and is_send_mishearing(command):
                actions = [Action("press", "send")]
            if actions:
                if not self.perform(actions):
                    return
                reading_time = len(self.long_reply.split()) * config.SECONDS_PER_SPOKEN_WORD
                deadline = time.monotonic() + self.settings.listen_seconds + reading_time
            elif first and heard:
                print("   not a command I know")
                self.say(persona.didnt_catch())
            first = False
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            if self.long_reply:
                reply, self.long_reply = self.long_reply, ""
                audio = self.listen_over_speech(remaining, reply)
            else:
                audio = self.record_command(remaining)
            if audio is None:
                break
        chime("end")

    def understand(self, command: str) -> list:
        """Your own routines and terminal commands come first, then the built-in commands."""
        routine = routines.match(command)
        listed = terminal.match(command) if not routine else None
        if routine:
            actions = [Action("routine", routine)]
        elif listed:
            actions = [Action("terminal", listed[0].names[0], listed[1])]
        else:
            actions = parse(command)
        if len(actions) == 1 and actions[0].kind == "repeat":
            if not self.last_actions:
                self.say(persona.NOTHING_TO_REPEAT)
            return list(self.last_actions)
        if len(actions) == 1 and actions[0].kind == "correct":
            actions = self.apply_correction(actions[0])
        if actions:
            self.last_actions = actions
        return actions

    def apply_correction(self, correction: Action) -> list:
        """ "I meant Claude": remembers the mishearing and does what you wanted."""
        heard = correction.site or next((a.arg for a in reversed(self.last_actions) if a.kind == "open"), "")
        if not heard:
            self.say(persona.NOTHING_TO_CORRECT)
            return []
        corrected = commands.learn_name(heard, correction.arg)
        print(f'   learned: "{heard}" means "{corrected}"')
        self.say(persona.LEARNED)
        return [Action("open", corrected)] if not correction.site else []

    def opening_line(self) -> str:
        now = datetime.now()
        if self.greeting_due():
            self.last_greeted = now
            return persona.greeting(self.name, now)
        return persona.returning()

    def perform(self, actions) -> bool:
        """Runs the steps. Returns False when the conversation should end."""
        if self.settings.enter_after_typing and actions[-1].kind == "type":
            actions = [*actions, Action("press", "send")]
        if self.greeting_due():
            self.last_greeted = datetime.now()
            self.say(persona.salutation(self.name, self.last_greeted))
        self.say(persona.acknowledge(actions[0]))
        unsent_dictation = False
        for action in actions:
            if self.stopped:
                return False
            if action.kind == "sleep":
                self.asleep = True
                print("   asleep: use Right Alt and say wake up.")
                self.say(persona.going_to_sleep())
                chime("sleep")
                return False
            if action.kind == "wake":
                self.asleep = False
                print("   awake")
                self.say(persona.waking())
            elif action.kind == "chat":
                self.say(persona.chat(action.arg, commands.wake_core(), datetime.now()))
            elif action.kind == "dictate":
                unsent_dictation = self.dictate()
            elif self.actions.run(action):
                if action.kind in ("press", "type"):
                    chime("done")
            else:
                chime("error")
                self.say(persona.failed())
                break
        typed = actions[-1].kind == "type" or (actions[-1].kind == "dictate" and unsent_dictation)
        self.typed_at = time.monotonic() if typed else 0.0
        return not self.stopped

    def ask(self, question: str) -> bool:
        """Says the question and returns True only if the answer is a clear yes."""
        print(f"   {question}")
        self.voice.say(question)
        self.voice.finish()
        chime("listen")
        audio = self.recorder.record(config.CONFIRM_SECONDS, config.COMMAND_SILENCE, config.MAX_COMMAND_SECONDS)
        heard = self.transcriber.transcribe(audio) if audio is not None else ""
        print(f'   answer: "{heard}"')
        if self.is_stop(heard):
            self.stopped = True
        return is_yes(heard)

    def hear_dictation(self) -> str:
        self.say(persona.go_ahead())
        self.voice.finish()
        chime("listen")
        print("   listening for what to type...")
        audio = self.recorder.record(
            config.START_TIMEOUT * 2, config.DICTATION_SILENCE, config.MAX_DICTATION_SECONDS,
            stop_check=self.tail_says_stop,
        )
        if audio is None:
            if not self.stopped:
                print("   heard nothing to type")
            return ""
        heard = self.transcriber.transcribe(audio)
        if self.is_stop(heard):
            self.stop_now()
            return ""
        if not clean_dictation(heard):
            print("   nothing typed")
            return ""
        return heard

    def dictate(self) -> bool:
        """Returns True if text was typed and is still waiting to be sent."""
        heard = self.hear_dictation()
        if not heard:
            return False
        text, wants_send = split_send(heard)
        if text:
            self.actions.type_text(text)
            chime("done")
        if wants_send or self.settings.enter_after_typing:
            self.actions.run(Action("press", "send"))
            return False
        return bool(text)
