"""
Download every model Sentinel needs, once, so the demo runs with WiFi off.

SPEC §4: "Everything must work with the network unplugged. All models download
once during setup, then run from local cache."

Run this while you still have internet. After it succeeds, re-running it must
make zero network calls -- that is the acceptance criterion, and it is checked
by running the second pass with HF_HUB_OFFLINE=1.

    python scripts/prefetch_models.py

Four models:
  facebook/wav2vec2-base                    countermeasure backbone (~360 MB)
  Resemblyzer pretrained.pt                 speaker encoder (~17 MB, vendored in the wheel)
  faster-whisper base.en (CTranslate2 int8) ASR (~145 MB)
  sentence-transformers/all-MiniLM-L6-v2    trigger semantics (~90 MB)
"""
from __future__ import annotations

import os
import sys
import time

# Import the package for its cache-path constants without pulling in torch yet.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _dir_size_mb(path: str) -> float:
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            fp = os.path.join(root, name)
            if not os.path.islink(fp):
                total += os.path.getsize(fp)
    return total / (1024 * 1024)


def _step(n: int, total: int, label: str) -> float:
    print(f"\n[{n}/{total}] {label}")
    return time.time()


def _done(t0: float) -> None:
    print(f"      ok ({time.time() - t0:.1f}s)")


def main() -> int:
    from sentinel.config import Config

    cfg = Config.load()
    total = 4

    from huggingface_hub import constants as hf_constants

    hf_cache = cfg.models.hf_cache() or hf_constants.HF_HUB_CACHE

    print("=" * 68)
    print("Sentinel model prefetch")
    print("=" * 68)
    print(f"HF cache : {hf_cache}")
    print(f"ASR cache: {cfg.models.asr_cache_dir}")
    os.makedirs(hf_cache, exist_ok=True)
    os.makedirs(cfg.models.asr_cache_dir, exist_ok=True)

    # 1. wav2vec2-base — the countermeasure backbone.
    t0 = _step(1, total, f"countermeasure backbone: {cfg.models.cm_backbone_id}")
    from transformers import AutoFeatureExtractor, AutoModel

    AutoFeatureExtractor.from_pretrained(
        cfg.models.cm_backbone_id, cache_dir=cfg.models.hf_cache()
    )
    AutoModel.from_pretrained(cfg.models.cm_backbone_id, cache_dir=cfg.models.hf_cache())
    _done(t0)

    # 2. Resemblyzer — weights ship inside the wheel, so this is a presence check,
    #    not a download. Verifying it here means an offline run can't surprise us.
    t0 = _step(2, total, "speaker encoder: Resemblyzer pretrained.pt")
    import resemblyzer

    weights = os.path.join(os.path.dirname(resemblyzer.__file__), "pretrained.pt")
    if not os.path.exists(weights):
        print(f"      MISSING: {weights}", file=sys.stderr)
        return 1
    print(f"      vendored in wheel: {weights} ({os.path.getsize(weights) / 1e6:.0f} MB)")
    _done(t0)

    # 3. faster-whisper — CTranslate2 conversion of Whisper, int8 on CPU.
    t0 = _step(3, total, f"ASR: faster-whisper {cfg.models.asr_model_id} ({cfg.models.asr_compute_type})")
    from faster_whisper import WhisperModel

    WhisperModel(
        cfg.models.asr_model_id,
        device=cfg.models.asr_device,
        compute_type=cfg.models.asr_compute_type,
        download_root=cfg.models.asr_cache_dir,
    )
    _done(t0)

    # 4. MiniLM — stage 2 of the trigger.
    t0 = _step(4, total, f"trigger semantics: {cfg.models.trigger_encoder_id}")
    from sentence_transformers import SentenceTransformer

    SentenceTransformer(
        cfg.models.trigger_encoder_id, cache_folder=cfg.models.hf_cache()
    )
    _done(t0)

    print("\n" + "=" * 68)
    print(f"HF cache  : {hf_cache}  ({_dir_size_mb(hf_cache):.0f} MB)")
    print(f"ASR cache : {cfg.models.asr_cache_dir}  ({_dir_size_mb(cfg.models.asr_cache_dir):.0f} MB)")
    print("\nAll models cached. Verify offline operation with:")
    print("    ../detector/venv/bin/python -m pytest tests/test_offline.py -v")
    print("=" * 68)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
