"""Fetches the large models once, on first run. Every file is checked against a fingerprint before it's used."""
import hashlib
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .config import DOWNLOADED_MODELS, speech_tier

CHUNK = 1024 * 1024
TIMEOUT = 30
ATTEMPTS = 6
RETRY_WAIT = 3
BACKUP_RELEASE = "https://github.com/gokuldas439/HeyPC/releases/download/models-v1/"


@dataclass(frozen=True)
class ModelFile:
    name: str
    url: str
    size: int
    sha256: str


BUNDLED = (  # small enough to ship inside the installer
    ModelFile("silero_vad.onnx", "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad.onnx", 643854, "9e2449e1087496d8d4caba907f23e0bd3f78d91fa552479bb9c23ac09cbb1fd6"),
    ModelFile("hey_jarvis_v0.1.onnx", "https://github.com/dscripka/openWakeWord/releases/download/v0.5.1/hey_jarvis_v0.1.onnx", 1271370, "94a13cfe60075b132f6a472e7e462e8123ee70861bc3fb58434a73712ee0d2cb"),
    ModelFile("melspectrogram.onnx", "https://github.com/dscripka/openWakeWord/releases/download/v0.5.1/melspectrogram.onnx", 1087958, "ba2b0e0f8b7b875369a2c89cb13360ff53bac436f2895cced9f479fa65eb176f"),
    ModelFile("embedding_model.onnx", "https://github.com/dscripka/openWakeWord/releases/download/v0.5.1/embedding_model.onnx", 1326578, "70d164290c1d095d1d4ee149bc5e00543250a7316b59f31d056cff7bd3075c1f"),
)
SPEECH = {
    "parakeet": (
    ModelFile("tokens.txt", "https://huggingface.co/csukuangfj/sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8/resolve/main/tokens.txt", 9384, "ec182b70dd42113aff6c5372c75cac58c952443eb22322f57bbd7f53977d497d"),
    ModelFile("joiner.int8.onnx", "https://huggingface.co/csukuangfj/sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8/resolve/main/joiner.int8.onnx", 1739080, "77a29f3e5ac7d37074e0af465391b80f314015d5b97f0f90c6c7767f1d56f428"),
    ModelFile("decoder.int8.onnx", "https://huggingface.co/csukuangfj/sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8/resolve/main/decoder.int8.onnx", 7257753, "4d097bae3bac5c96018d5293ba39f1b657296102b142affda40378f38b020f41"),
    ModelFile("encoder.int8.onnx", "https://huggingface.co/csukuangfj/sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8/resolve/main/encoder.int8.onnx", 652282309, "92a10bd9c23936ea0566c29f963bc57c2a5df4261b6a8921c39abea66557ca8b"),
    ),
    "tiny": (
    ModelFile("tiny.en-tokens.txt", "https://huggingface.co/csukuangfj/sherpa-onnx-whisper-tiny.en/resolve/main/tiny.en-tokens.txt", 835554, "306cd27f03c1a714eca7108e03d66b7dc042abe8c258b44c199a7ed9838dd930"),
    ModelFile("tiny.en-encoder.int8.onnx", "https://huggingface.co/csukuangfj/sherpa-onnx-whisper-tiny.en/resolve/main/tiny.en-encoder.int8.onnx", 12937772, "0ce578b827c94a961aacb8fa14b02f096504b337e5c94be37c36238cbe3e8bc6"),
    ModelFile("tiny.en-decoder.int8.onnx", "https://huggingface.co/csukuangfj/sherpa-onnx-whisper-tiny.en/resolve/main/tiny.en-decoder.int8.onnx", 89853865, "06c0e6ff6348d427e51839219d1c886c18cfdf411e629e33f5e1679bff9c1527"),
    ),
}
OFFLINE_VOICE = (
    ModelFile("kokoro/kokoro-v1.0.int8.onnx", "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.int8.onnx", 92361271, "6e742170d309016e5891a994e1ce1559c702a2ccd0075e67ef7157974f6406cb"),
    ModelFile("kokoro/voices-v1.0.bin", "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin", 28214398, "bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d"),
)


def needed(tier: str | None = None) -> list[ModelFile]:
    """The files this PC still has to download."""
    wanted = [*SPEECH[tier or speech_tier()], *OFFLINE_VOICE]
    return [file for file in wanted if not (DOWNLOADED_MODELS / file.name).exists()]


def _fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        while chunk := source.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def backup_url(file: ModelFile) -> str:
    return BACKUP_RELEASE + Path(file.name).name


def fetch(file: ModelFile, folder: Path, on_bytes, url: str | None = None) -> None:
    """Downloads one file, carrying on from where an earlier attempt stopped."""
    target = folder / file.name
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".part")
    have = partial.stat().st_size if partial.exists() else 0
    if have >= file.size:
        partial.unlink()
        have = 0
    request = urllib.request.Request(url or file.url, headers={"User-Agent": "HeyPC", **({"Range": f"bytes={have}-"} if have else {})})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        if have and response.status != 206:  # the server won't resume, so start this file over
            have = 0
        on_bytes(have)
        with open(partial, "ab" if have else "wb") as output:
            while chunk := response.read(CHUNK):
                output.write(chunk)
                on_bytes(len(chunk))
    if partial.stat().st_size < file.size:
        raise ConnectionError("the download ended early")
    if _fingerprint(partial) != file.sha256:
        partial.unlink()  # never keep a corrupted or altered file
        raise ValueError(f"{file.name} failed its fingerprint check")
    os.replace(partial, target)


def download_all(files: list[ModelFile], on_progress, folder: Path | None = None) -> None:
    """Calls on_progress(bytes done so far). Retries alternate with the backup copy, which has the same fingerprints."""
    folder = folder or DOWNLOADED_MODELS
    finished = 0
    for file in files:
        sources = (file.url, backup_url(file))
        for attempt in range(1, ATTEMPTS + 1):
            current = [0]

            def count(amount: int) -> None:
                current[0] += amount
                on_progress(finished + current[0])

            try:
                fetch(file, folder, count, sources[(attempt - 1) % len(sources)])
                break
            except (OSError, ValueError, urllib.error.URLError):
                if attempt == ATTEMPTS:
                    raise
                time.sleep(RETRY_WAIT * attempt)
        finished += file.size
