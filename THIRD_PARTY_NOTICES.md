# Third-party notices

Jarvis is released under the GNU General Public License v3.0 (see `LICENSE`). It bundles or downloads the components below, each under its own terms. The source code for Jarvis is at <https://github.com/gokuldas439/voice-jarvis>.

## Models

| Model | Use | License | Source |
|---|---|---|---|
| NVIDIA Parakeet TDT 0.6b v2 | Speech recognition | CC BY 4.0 | <https://huggingface.co/nvidia/parakeet-tdt-0.6b-v2> |
| OpenAI Whisper tiny.en (sherpa-onnx export) | Speech recognition on low-spec PCs | MIT | <https://github.com/openai/whisper> |
| openWakeWord "hey jarvis" and feature models | Wake word | **CC BY-NC-SA 4.0 (non-commercial)** | <https://github.com/dscripka/openWakeWord> |
| Silero VAD | Detecting speech | MIT | <https://github.com/snakers4/silero-vad> |
| Kokoro v1.0 | Offline voice | Apache 2.0 | <https://huggingface.co/hexgrad/Kokoro-82M> |

The openWakeWord pre-trained models may not be used commercially. Anyone who wants to sell a product based on Jarvis must replace them. The rest of the code does not depend on them: a custom wake word in Settings works without that model's detection path.

## Libraries

| Library | License |
|---|---|
| espeak-ng (via espeakng-loader) | GPL-3.0-or-later |
| phonemizer-fork | GPL-3.0-or-later |
| edge-tts | LGPL-3.0 |
| pynput, pystray | LGPL-3.0 |
| sherpa-onnx, openWakeWord code, kokoro-onnx | Apache 2.0 / MIT |
| ONNX Runtime, sounddevice, comtypes, pycaw | MIT |
| NumPy, SciPy, scikit-learn, soundfile | BSD |
| Pillow | MIT-CMU |
| pywin32 | PSF |
| aiohttp | Apache 2.0 and MIT |
| certifi | MPL 2.0 |

## Online voices

The default voices use Microsoft's Edge read-aloud service through the community `edge-tts` library. This is not an official Microsoft API, may change or stop working, and is not affiliated with or endorsed by Microsoft. When it is unavailable, Jarvis falls back to the offline voice.

## Trademarks

Jarvis is an independent open-source project. It is not affiliated with, endorsed by, or sponsored by Marvel, Disney, Microsoft, OpenAI, Anthropic, Google, or any other company named in this project. All trademarks belong to their owners.
