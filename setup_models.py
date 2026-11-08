"""Downloads the models this PC needs into ./models. Safe to re-run; finished files are skipped."""
import sys
import urllib.request

from jarvis.config import MODELS, speech_tier

PARAKEET = "https://huggingface.co/csukuangfj/sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8/resolve/main"
TINY = "https://huggingface.co/csukuangfj/sherpa-onnx-whisper-tiny.en/resolve/main"
WAKE = "https://github.com/dscripka/openWakeWord/releases/download/v0.5.1"
VAD = "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models"
VOICE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"

COMMON = {
    "silero_vad.onnx": f"{VAD}/silero_vad.onnx",
    "hey_jarvis_v0.1.onnx": f"{WAKE}/hey_jarvis_v0.1.onnx",
    "melspectrogram.onnx": f"{WAKE}/melspectrogram.onnx",
    "embedding_model.onnx": f"{WAKE}/embedding_model.onnx",
    "kokoro/kokoro-v1.0.int8.onnx": f"{VOICE}/kokoro-v1.0.int8.onnx",
    "kokoro/voices-v1.0.bin": f"{VOICE}/voices-v1.0.bin",
}
TIERS = {
    "parakeet": {
        "tokens.txt": f"{PARAKEET}/tokens.txt",
        "joiner.int8.onnx": f"{PARAKEET}/joiner.int8.onnx",
        "decoder.int8.onnx": f"{PARAKEET}/decoder.int8.onnx",
        "encoder.int8.onnx": f"{PARAKEET}/encoder.int8.onnx",
    },
    "tiny": {
        "tiny.en-tokens.txt": f"{TINY}/tiny.en-tokens.txt",
        "tiny.en-encoder.int8.onnx": f"{TINY}/tiny.en-encoder.int8.onnx",
        "tiny.en-decoder.int8.onnx": f"{TINY}/tiny.en-decoder.int8.onnx",
    },
}


def download(name: str, url: str) -> None:
    target = MODELS / name
    if target.exists():
        print(f"have {name}")
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + ".part")
    print(f"downloading {name}", flush=True)
    urllib.request.urlretrieve(url, partial)
    partial.replace(target)
    print(f"done {name} ({target.stat().st_size / 1e6:.1f} MB)", flush=True)


def main() -> int:
    MODELS.mkdir(exist_ok=True)
    tier = sys.argv[1] if len(sys.argv) > 1 else speech_tier()
    print(f"speech model: {tier}")
    for name, url in {**COMMON, **TIERS[tier]}.items():
        download(name, url)
    print("all models ready")
    return 0


if __name__ == "__main__":
    sys.exit(main())
