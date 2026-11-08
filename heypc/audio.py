"""Microphone, wake word, speech detection, speech-to-text and the Right Alt hotkey."""
import queue
import re
import threading
import time
import winsound
from collections import deque

import comtypes
import numpy as np
import sherpa_onnx
import sounddevice as sd
from openwakeword.model import Model
from pycaw.constants import CLSID_MMDeviceEnumerator, DEVICE_STATE, EDataFlow, ERole
from pycaw.pycaw import IMMDeviceEnumerator
from pynput import keyboard as pynput_keyboard

from . import config
from .config import DOWNLOADED_MODELS, FRAME_SAMPLES, MODELS, SAMPLE_RATE

VAD_WINDOW = 512
LONG_AUDIO_SECONDS = 25
STOP_CHECK_FRAMES = 38  # about 3 seconds
HEADSET_WORDS = re.compile(r"headset|headphone|earphone|earbud|buds|hands-?\s?free|airpods|meta|ray-?\s?ban|bluetooth", re.I)
VK_RIGHT_ALT = 0xA5
VK_RIGHT_CTRL = 0xA3
KEY_INJECTED = 0x10  # keys Jarvis presses itself must not count as you pressing them
PRE_ROLL_FRAMES = 12  # about 1 second kept in memory, so the first word of voice typing isn't lost
KEY_DOWN_MESSAGES = {0x100, 0x104}


def chime(kind: str) -> None:
    tones = {"listen": [(880, 90)], "done": [(660, 70)], "error": [(220, 200)], "sleep": [(440, 90), (330, 120)], "end": [(520, 60)], "reminder": [(880, 160), (660, 160), (880, 200)]}
    def play():
        for frequency, length in tones[kind]:
            winsound.Beep(frequency, length)
    threading.Thread(target=play, daemon=True).start()


class Leveler:
    """Lifts a quiet voice to a normal level, so you can talk softly. Loud audio is left alone."""

    TARGET = 4000.0  # the loudness the speech models work best at
    MAX_GAIN = config.MIC_MAX_GAIN
    WINDOW_FRAMES = 62  # about 5 seconds

    def __init__(self, max_gain: float = MAX_GAIN) -> None:
        self.max_gain = max_gain
        self.recent: deque = deque(maxlen=self.WINDOW_FRAMES)
        self.level = 0.0  # 0 to 1, drives the on-screen animation

    def apply(self, frame: np.ndarray) -> np.ndarray:
        samples = frame.astype(np.float32)
        loudness = float(np.sqrt(np.mean(samples**2)))
        self.recent.append(loudness)
        gain = max(1.0, min(self.max_gain, self.TARGET / max(max(self.recent), 1.0)))
        self.level = min(1.0, loudness * gain / self.TARGET)
        return np.clip(samples * gain, -32768, 32767).astype(np.int16)


def input_devices() -> list[tuple[int, str]]:
    """Microphones Windows currently offers, without duplicates from other driver types."""
    return [
        (index, device["name"]) for index, device in enumerate(sd.query_devices())
        if device["max_input_channels"] > 0 and device["hostapi"] == sd.default.hostapi and "Sound Mapper" not in device["name"]
    ]


def choose_input(preferred: str, devices: list[tuple[int, str]]) -> int | None:
    """The microphone to use. None means the Windows default.

    In automatic mode a connected headset wins, because it sits right by your mouth.
    """
    if preferred:
        return next((index for index, name in devices if name == preferred), None)
    return next((index for index, name in devices if HEADSET_WORDS.search(name)), None)


def audio_device_state() -> str:
    """Changes whenever a headset connects or disconnects, or the Windows default changes."""
    enumerator = comtypes.CoCreateInstance(CLSID_MMDeviceEnumerator, IMMDeviceEnumerator, comtypes.CLSCTX_INPROC_SERVER)
    endpoints = enumerator.EnumAudioEndpoints(EDataFlow.eAll.value, DEVICE_STATE.ACTIVE.value)
    ids = [endpoints.Item(index).GetId() for index in range(endpoints.GetCount())]
    for flow in (EDataFlow.eCapture.value, EDataFlow.eRender.value):
        try:
            ids.append("default:" + enumerator.GetDefaultAudioEndpoint(flow, ERole.eConsole.value).GetId())
        except comtypes.COMError:
            ids.append("default:none")  # no device of this kind is connected
    return "|".join(sorted(ids))


class Mic:
    MAX_FRAMES = 375  # 30 s; on a very slow PC the oldest audio is dropped rather than growing forever

    def __init__(self, preferred: str = "") -> None:
        self.frames: queue.Queue = queue.Queue(self.MAX_FRAMES)
        self.gate = None  # returns True while the mic should be ignored
        self.leveler = Leveler()
        self.preferred = preferred
        self.stream = None
        self.last_frame_at = time.monotonic()
        self.recent: deque = deque(maxlen=PRE_ROLL_FRAMES)

    def _on_audio(self, data, _frames, _time, _status) -> None:
        self.last_frame_at = time.monotonic()
        if self.gate and self.gate():
            return
        if self.frames.full():
            self.frames.get_nowait()
        frame = self.leveler.apply(data[:, 0])
        self.recent.append((self.last_frame_at, frame))
        self.frames.put_nowait(frame)

    def take_since(self, moment: float) -> list:
        """Audio from a moment ago, and clears the queue so the same audio isn't read twice."""
        while not self.frames.empty():
            self.frames.get_nowait()
        return [frame for at, frame in list(self.recent) if at >= moment]

    def start(self) -> None:
        self.restart()

    def restart(self) -> None:
        """Re-reads the device list, which is how a newly connected headset gets noticed."""
        if self.stream is not None:
            self.stream.close(ignore_errors=True)
            self.stream = None
        sd._terminate()
        sd._initialize()
        self.last_frame_at = time.monotonic()
        choice = choose_input(self.preferred, input_devices())
        for device in dict.fromkeys((choice, None)):
            try:
                self.stream = sd.InputStream(
                    device=device, samplerate=SAMPLE_RATE, channels=1, dtype="int16",
                    blocksize=FRAME_SAMPLES, callback=self._on_audio,
                )
                self.stream.start()
                print(f"microphone: {sd.query_devices(self.stream.device)['name']}")
                return
            except Exception as error:
                print(f"   microphone {device} did not open: {error!r}")
                self.stream = None

    def read(self, timeout: float = 1.0):
        try:
            return self.frames.get(timeout=timeout)
        except queue.Empty:
            return None


class WakeWord:
    def __init__(self) -> None:
        self.model = Model(
            wakeword_models=[str(MODELS / "hey_jarvis_v0.1.onnx")],
            inference_framework="onnx",
            melspec_model_path=str(MODELS / "melspectrogram.onnx"),
            embedding_model_path=str(MODELS / "embedding_model.onnx"),
            ncpu=1,
        )
        self.in_a_row = 0

    def heard(self, frame) -> bool:
        """A real "Hey Jarvis" stays above the threshold for several frames; a stray sound only blips."""
        scores = self.model.predict(frame)
        self.in_a_row = self.in_a_row + 1 if max(scores.values()) >= config.WAKE_THRESHOLD else 0
        return self.in_a_row >= config.WAKE_FRAMES_IN_A_ROW

    def reset(self) -> None:
        self.model.reset()
        self.in_a_row = 0


class Hotkey:
    """Right Alt: hold to talk, or tap to speak hands-free. It is kept from reaching other apps."""

    def __init__(self) -> None:
        self.pressed = threading.Event()
        self.down = threading.Event()
        self.pressed_at = 0.0
        self.type_down = threading.Event()  # Right Ctrl: hold to type by voice
        self.type_pressed_at = 0.0
        self.type_cancelled = False
        self.alt_enabled = True
        self.listener = pynput_keyboard.Listener(win32_event_filter=self._filter)

    def start(self) -> None:
        self.listener.start()

    def typing_held(self) -> bool:
        return self.type_down.is_set() and not self.type_cancelled and time.monotonic() - self.type_pressed_at >= config.TYPE_HOLD_SECONDS

    def _watch_typing_key(self, message, data) -> bool:
        """Right Ctrl still reaches other apps. Pressing another key with it means a shortcut, so voice typing is off."""
        if data.flags & KEY_INJECTED:
            return False
        if data.vkCode == VK_RIGHT_CTRL:
            if message not in KEY_DOWN_MESSAGES:
                self.type_down.clear()
            elif not self.type_down.is_set():
                self.type_pressed_at = time.monotonic()
                self.type_cancelled = False
                self.type_down.set()
            return True
        if message in KEY_DOWN_MESSAGES and self.type_down.is_set():
            self.type_cancelled = True
        return False

    def _filter(self, message, data) -> None:
        if self._watch_typing_key(message, data) or data.vkCode != VK_RIGHT_ALT or not self.alt_enabled:
            return
        if message in KEY_DOWN_MESSAGES:
            if not self.down.is_set():
                self.pressed_at = time.monotonic()
                self.down.set()
                self.pressed.set()
        else:
            self.down.clear()
        self.listener.suppress_event()


class Recorder:
    def __init__(self, mic: Mic, hotkey: Hotkey) -> None:
        self.mic = mic
        self.hotkey = hotkey
        vad_config = sherpa_onnx.VadModelConfig()
        vad_config.silero_vad.model = str(MODELS / "silero_vad.onnx")
        vad_config.silero_vad.threshold = 0.5
        vad_config.silero_vad.min_silence_duration = 0.25
        vad_config.silero_vad.min_speech_duration = 0.15
        vad_config.silero_vad.window_size = VAD_WINDOW
        vad_config.silero_vad.max_speech_duration = 600
        vad_config.sample_rate = SAMPLE_RATE
        vad_config.num_threads = 1
        self.vad = sherpa_onnx.VoiceActivityDetector(vad_config, buffer_size_in_seconds=30)
        self.listening = False  # shown on screen
        self.woke = False

    def _speaking(self, samples: np.ndarray, leftover: np.ndarray) -> tuple[bool, np.ndarray]:
        joined = np.concatenate([leftover, samples])
        offset = 0
        while offset + VAD_WINDOW <= len(joined):
            self.vad.accept_waveform(joined[offset : offset + VAD_WINDOW])
            offset += VAD_WINDOW
        while not self.vad.empty():
            self.vad.pop()
        return self.vad.is_speech_detected(), joined[offset:]

    def record(self, *args, **kwargs):
        self.listening = True
        try:
            return self._capture(*args, **kwargs)
        finally:
            self.listening = False

    def _capture(self, start_timeout: float, silence: float, max_seconds: float, held: bool = False, stop_check=None, early=None, on_speech=None):
        """Returns the speech as floats, or None if nobody spoke, the hotkey interrupted or stop_check said so.

        stop_check is given the last few seconds of speech at each small pause.
        early sees every raw frame; if it returns True, recording ends and self.woke is set.
        """
        self.woke = False
        was_speaking = False
        self.vad.reset()
        before = deque(maxlen=6)  # catches the first syllable said before detection kicks in
        captured: list[np.ndarray] = []
        leftover = np.zeros(0, dtype=np.float32)
        began = time.monotonic()
        speech_at = None
        while True:
            frame = self.mic.read()
            now = time.monotonic()
            if frame is None:
                if now - began > start_timeout + max_seconds:
                    return None
                continue
            if early and early(frame):
                self.woke = True
                return None
            samples = frame.astype(np.float32) / 32768.0
            speaking, leftover = self._speaking(samples, leftover)
            just_paused = was_speaking and not speaking
            was_speaking = speaking

            if held:
                captured.append(samples)
                if not self.hotkey.down.is_set():
                    if now - self.hotkey.pressed_at >= config.HOLD_THRESHOLD:
                        return np.concatenate(captured)
                    held = False  # it was a tap: carry on and stop at the next pause
                    began = now
                    captured.clear()
                elif now - began > config.MAX_DICTATION_SECONDS:
                    return np.concatenate(captured)
                continue

            if self.hotkey.pressed.is_set() or self.hotkey.typing_held():
                return None
            if speech_at is None:
                if speaking:
                    speech_at = now
                    if on_speech:
                        on_speech()
                    captured.extend(before)
                    captured.append(samples)
                else:
                    before.append(samples)
                    if now - began > start_timeout:
                        return None
                continue
            captured.append(samples)
            if speaking:
                speech_at = now
            if stop_check and just_paused and stop_check(np.concatenate(captured[-STOP_CHECK_FRAMES:])):
                return None
            if now - speech_at >= silence or len(captured) * FRAME_SAMPLES >= max_seconds * SAMPLE_RATE:
                return np.concatenate(captured)


class Transcriber:
    def __init__(self) -> None:
        self.tier = config.speech_tier()
        threads = config.thread_count()
        if self.tier == "parakeet":
            self.recognizer = sherpa_onnx.OfflineRecognizer.from_transducer(
                encoder=str(DOWNLOADED_MODELS / "encoder.int8.onnx"),
                decoder=str(DOWNLOADED_MODELS / "decoder.int8.onnx"),
                joiner=str(DOWNLOADED_MODELS / "joiner.int8.onnx"),
                tokens=str(DOWNLOADED_MODELS / "tokens.txt"),
                model_type="nemo_transducer",
                num_threads=threads,
                decoding_method="greedy_search",
            )
        else:
            self.recognizer = sherpa_onnx.OfflineRecognizer.from_whisper(
                encoder=str(DOWNLOADED_MODELS / "tiny.en-encoder.int8.onnx"),
                decoder=str(DOWNLOADED_MODELS / "tiny.en-decoder.int8.onnx"),
                tokens=str(DOWNLOADED_MODELS / "tiny.en-tokens.txt"),
                language="en",
                task="transcribe",
                num_threads=threads,
            )

    def _one(self, samples: np.ndarray) -> str:
        stream = self.recognizer.create_stream()
        stream.accept_waveform(SAMPLE_RATE, samples)
        self.recognizer.decode_stream(stream)
        return stream.result.text.strip()

    def transcribe(self, samples: np.ndarray) -> str:
        parts = [self._one(chunk) for chunk in _split_long(samples)]
        text = " ".join(part for part in parts if part)
        return re.sub(r"[\[(][^\])]*[\])]", "", text).strip()  # Whisper's "[BLANK_AUDIO]" notes


def _split_long(samples: np.ndarray) -> list[np.ndarray]:
    """Cuts long dictation at the quietest moment near each limit, so no word is sliced."""
    limit = LONG_AUDIO_SECONDS * SAMPLE_RATE
    window = SAMPLE_RATE // 10
    chunks = []
    while len(samples) > limit:
        search_from = limit - 5 * SAMPLE_RATE
        tail = samples[search_from:limit]
        steps = max(1, len(tail) // window)
        energy = [float(np.abs(piece).mean()) for piece in np.array_split(tail, steps)]
        cut = search_from + int(np.argmin(energy)) * window
        chunks.append(samples[:cut])
        samples = samples[cut:]
    chunks.append(samples)
    return chunks
