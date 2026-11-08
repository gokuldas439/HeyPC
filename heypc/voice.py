"""Jarvis's spoken voice. Runs on this PC; replies play in the background while actions carry on.

Each line is saved after it is first produced, and the usual replies are prepared while idle, so they play instantly.
"""
import asyncio
import hashlib
import io
import queue
import shutil
import threading
import time
from collections import deque

import edge_tts
import numpy as np
import onnxruntime
import sounddevice as sd
import soundfile
from kokoro_onnx import Kokoro

from .config import DOWNLOADED_MODELS, thread_count
from .settings import DATA, Settings

MODEL_FILE = DOWNLOADED_MODELS / "kokoro" / "kokoro-v1.0.int8.onnx"
VOICES_FILE = DOWNLOADED_MODELS / "kokoro" / "voices-v1.0.bin"
CACHE = DATA / "voice-replies"
EARLIER_CACHE = DATA / "voice-cache"  # kept every line spoken, so it is removed
SAMPLE_RATE = 24000
RECENT_LINES = 4
ONLINE_VOICE_PREFIX = "en-"
OFFLINE_BACKUP_VOICE = "bm_george"
ONLINE_TIMEOUT = 6.0
ONLINE_ATTEMPTS = 3
FAILURES_BEFORE_PAUSE = 2
ONLINE_RETRY_SECONDS = 60.0  # after repeated failures, stay offline this long so replies aren't held up
ECHO_TAIL = 0.25 # the mic stays closed this long after speech ends
IDLE_CHECK_SECONDS = 0.2
BREATHER_SECONDS = 0.3  # between lines prepared in the background, so the PC stays responsive


def _fetch_online(text: str, voice: str, speed: float) -> tuple[np.ndarray, int]:
    """A natural voice from Microsoft's free read-aloud service. Only the sentence being spoken is sent."""

    async def collect() -> bytes:
        audio = bytearray()
        async for chunk in edge_tts.Communicate(text, voice, rate=f"{round((speed - 1) * 100):+d}%").stream():
            if chunk["type"] == "audio":
                audio += chunk["data"]
        return bytes(audio)

    for attempt in range(ONLINE_ATTEMPTS):  # the service occasionally returns nothing, and an immediate retry works
        try:
            data = asyncio.run(asyncio.wait_for(collect(), ONLINE_TIMEOUT))
            break
        except edge_tts.exceptions.NoAudioReceived:
            if attempt == ONLINE_ATTEMPTS - 1:
                raise
    samples, rate = soundfile.read(io.BytesIO(data), dtype="float32")
    return samples, rate


class Voice:
    def __init__(self, speed: float = Settings.voice_speed, name: str = Settings.voice) -> None:
        self.speed = speed
        self.name = name
        self.lines: queue.Queue = queue.Queue()
        self.to_prepare: deque = deque()
        self.standard_lines: set = set()  # only these are saved to disk; summaries and AI replies never are
        self.said: deque = deque(maxlen=RECENT_LINES)
        self.tail_until = 0.0
        self.engine = None
        self.interruptible = False  # while True the mic stays open during speech, so you can talk over Jarvis
        self.interrupted = False
        self.online_failed_at = -ONLINE_RETRY_SECONDS
        self.online_failures = 0
        self.playing = False
        threading.Thread(target=self._work, daemon=True).start()

    def say(self, text: str) -> None:
        if text:
            self.interrupted = False
            self.said.append(text)
            self.lines.put(text)

    def recent_lines(self) -> str:
        """What Jarvis has just said, so its own voice can be recognised if the mic picks it up."""
        return " ".join(self.said)

    def prepare(self, lines: list[str]) -> None:
        """Queues the usual replies for quiet moments."""
        self.standard_lines = set(lines)
        self.to_prepare = deque(lines)

    def busy(self) -> bool:
        return self.lines.unfinished_tasks > 0 or time.monotonic() < self.tail_until

    def finish(self) -> None:
        while self.busy():
            time.sleep(0.02)

    def mic_closed(self) -> bool:
        """Only while sound is really playing; preparing a line must not cost you what you're saying."""
        return (self.playing or time.monotonic() < self.tail_until) and not self.interruptible

    def interrupt(self) -> None:
        """You started talking, so stop at once and drop anything still waiting to be said."""
        self.interrupted = True
        while True:
            try:
                self.lines.get_nowait()
            except queue.Empty:
                break
            self.lines.task_done()
        sd.stop()

    def _folder(self):
        return CACHE / f"{self.name}_{self.speed:.2f}"

    def _load(self) -> Kokoro:
        options = onnxruntime.SessionOptions()
        options.intra_op_num_threads = thread_count()
        session = onnxruntime.InferenceSession(str(MODEL_FILE), options, providers=["CPUExecutionProvider"])
        return Kokoro.from_session(session, str(VOICES_FILE))

    def _online_available(self) -> bool:
        return self.name.startswith(ONLINE_VOICE_PREFIX) and time.monotonic() - self.online_failed_at > ONLINE_RETRY_SECONDS

    def _render_offline(self, text: str, voice: str) -> tuple[np.ndarray, int]:
        if self.engine is None:
            self.engine = self._load()
        british = voice[:1] == "b"
        return self.engine.create(text, voice=voice, speed=self.speed, lang="en-gb" if british else "en-us")

    def render(self, text: str) -> tuple[np.ndarray, int]:
        path = self._folder() / f"{hashlib.sha1(text.encode()).hexdigest()}.npy"
        if path.exists():
            return np.load(path), SAMPLE_RATE
        if self.name.startswith(ONLINE_VOICE_PREFIX):
            if not self._online_available():
                return self._render_offline(text, OFFLINE_BACKUP_VOICE)  # never cached, so the natural voice returns later
            try:
                samples, rate = _fetch_online(text, self.name, self.speed)
                self.online_failures = 0
            except Exception as error:
                print(f"   online voice unavailable, using the offline voice: {error!r}")
                self.online_failures += 1
                if self.online_failures >= FAILURES_BEFORE_PAUSE:
                    self.online_failed_at = time.monotonic()
                return self._render_offline(text, OFFLINE_BACKUP_VOICE)
        else:
            samples, rate = self._render_offline(text, self.name)
        if text not in self.standard_lines:
            return samples, rate
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.with_suffix(".tmp.npy")
        np.save(partial, samples)
        partial.replace(path)
        return samples, rate

    def _drop_other_voices(self) -> None:
        shutil.rmtree(EARLIER_CACHE, ignore_errors=True)
        if CACHE.exists():
            for folder in CACHE.iterdir():
                if folder != self._folder():
                    shutil.rmtree(folder, ignore_errors=True)

    def _prepare_one(self) -> None:
        if self.to_prepare and (self._online_available() or not self.name.startswith(ONLINE_VOICE_PREFIX)):
            try:
                self.render(self.to_prepare.popleft())
            except Exception as error:
                print(f"   could not prepare a reply: {error!r}")
            time.sleep(BREATHER_SECONDS)

    def _work(self) -> None:
        if not self.name.startswith(ONLINE_VOICE_PREFIX):
            try:
                self.engine = self._load()  # ready before the first line is needed
            except Exception as error:
                print(f"   voice did not load: {error!r}")
        self._drop_other_voices()
        current = (self.name, self.speed)
        while True:
            if (self.name, self.speed) != current:
                current = (self.name, self.speed)
                self._drop_other_voices()
            try:
                text = self.lines.get(timeout=IDLE_CHECK_SECONDS)
            except queue.Empty:
                self._prepare_one()
                continue
            try:
                samples, rate = self.render(text)
                if not self.interrupted:
                    self.playing = True
                    sd.play(samples, rate, blocking=True)
                    self.tail_until = time.monotonic() + ECHO_TAIL
            except Exception as error:
                print(f"   could not speak: {error!r}")
                _windows_voice(text)
            finally:
                self.playing = False
                self.lines.task_done()


def _windows_voice(text: str) -> None:
    try:
        import pythoncom
        import win32com.client

        pythoncom.CoInitialize()
        win32com.client.Dispatch("SAPI.SpVoice").Speak(text)
    except Exception as error:
        print(f"   Windows voice failed too: {error!r}")
