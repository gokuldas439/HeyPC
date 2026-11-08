"""For building from source: downloads every model this PC needs into ./models. Safe to re-run."""
import sys

from heypc.config import MODELS, speech_tier
from heypc.downloads import BUNDLED, OFFLINE_VOICE, SPEECH, fetch


def main() -> int:
    tier = sys.argv[1] if len(sys.argv) > 1 else speech_tier()
    print(f"speech model: {tier}")
    for file in (*BUNDLED, *SPEECH[tier], *OFFLINE_VOICE):
        if (MODELS / file.name).exists():
            print(f"have {file.name}")
        else:
            print(f"downloading {file.name}", flush=True)
            fetch(file, MODELS, lambda _amount: None)
    print("all models ready")
    return 0


if __name__ == "__main__":
    sys.exit(main())
