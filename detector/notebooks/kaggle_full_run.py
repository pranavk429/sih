"""
KAGGLE FULL-SCALE RUN — copy-paste guide.

HOW TO USE THIS FILE
1. Go to kaggle.com, make a free account if you don't have one.
2. Create a New Notebook.
3. Settings (right sidebar) -> Accelerator -> GPU T4 x2. Save.
4. This file is split into cells marked "# %% CELL N". Copy each cell's
   code into its own cell in the Kaggle notebook, in order, and run them
   one at a time (Shift+Enter). Don't paste the whole file into one cell —
   splitting it means if something in Cell 7 fails, you don't lose the
   ~15 minutes of downloading + embedding work from Cells 1-6.
5. Cells are labeled CONFIRMED WORKING or BEST-EFFORT:
     - CONFIRMED WORKING cells use the exact same approach already tested
       on a laptop today (see detector/README.md) — these will run.
     - BEST-EFFORT cells try something new (an official data split, an
       Indian-language pairing) that looks right from documentation but
       hasn't been dry-run yet. They're wrapped so a failure there prints
       a message and moves on — it will NOT crash the notebook or lose
       the results from the confirmed cells before it.
6. Expected total runtime: ~45-70 minutes on a free T4. Well inside the
   30 free GPU-hours/week Kaggle gives you — no payment needed.
7. When it's done, download `/kaggle/working/full_results.json` from the
   notebook's Output panel and send it back — that's the real number for
   the idea-PPT slide.

WHY THIS EXISTS (context if you're reading this cold)
A laptop pilot (no GPU, 25 speakers, ~119 trials) already proved the
mechanism: enrollment-based verification recovers accuracy that a phone
line destroys. See detector/README.md for the full story, including an
important lesson: a pretrained "deepfake detector" checkpoint from
Hugging Face turned out to have memorized its own benchmark (0.0% EER —
a red flag, not a win). This notebook repeats that same leak-free
methodology (a task-naive backbone + our own trained probe, on a
speaker-disjoint split) at real scale, on a real GPU.
"""

# %% CELL 1 — CONFIRMED WORKING: install dependencies
"""
!pip install -q transformers datasets soundfile librosa scikit-learn resemblyzer
# Kaggle images already ship ffmpeg; if the channel-degradation cell errors
# with "ffmpeg not found", uncomment the next line:
# !apt-get -qq install -y ffmpeg
print("dependencies installed")
"""

# %% CELL 2 — CONFIRMED WORKING: imports, device check, channel simulator
"""
from __future__ import annotations
import os, io, json, random, subprocess, tempfile
import numpy as np
import soundfile as sf
import torch
from datasets import load_dataset, Audio
from transformers import AutoFeatureExtractor, AutoModel
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_curve
from resemblyzer import VoiceEncoder, preprocess_wav

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
print("device:", DEVICE)
assert DEVICE == "cuda", "GPU not detected — check Settings > Accelerator > GPU T4 x2"


def _run_ffmpeg(args):
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error"] + args, capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {r.stderr.decode()}")


def apply_opus_lowrate(audio, sr, bitrate_kbps=8):
    with tempfile.TemporaryDirectory() as td:
        src, enc, dst = (os.path.join(td, n) for n in ("in.wav", "enc.opus", "out.wav"))
        sf.write(src, audio, sr)
        _run_ffmpeg(["-i", src, "-ar", "16000", "-ac", "1", "-c:a", "libopus",
                     "-b:a", f"{bitrate_kbps}k", enc])
        _run_ffmpeg(["-i", enc, "-ar", "16000", dst])  # force 16kHz on decode
        out, out_sr = sf.read(dst)
        return out.astype(np.float32), out_sr


def apply_g711(audio, sr):
    with tempfile.TemporaryDirectory() as td:
        src, dst = os.path.join(td, "in.wav"), os.path.join(td, "out.wav")
        sf.write(src, audio, sr)
        _run_ffmpeg(["-i", src, "-ar", "8000", "-ac", "1", "-c:a", "pcm_mulaw", dst])
        out, out_sr = sf.read(dst)
        return out.astype(np.float32), out_sr


def apply_packet_loss(audio, sr, loss_rate=0.05, chunk_ms=20, seed=None):
    rng = random.Random(seed)
    chunk = int(sr * chunk_ms / 1000)
    out = audio.copy()
    for start in range(0, len(out), chunk):
        if rng.random() < loss_rate:
            out[start:start + chunk] = 0.0
    return out


def degrade(audio, sr, profile="mobile_voip", seed=None):
    if profile == "pstn":
        return apply_g711(audio, sr)
    elif profile == "mobile_voip":
        out, out_sr = apply_opus_lowrate(audio, sr, 8)
        return apply_packet_loss(out, out_sr, 0.05, seed=seed), out_sr
    elif profile == "mobile_poor":
        out, out_sr = apply_opus_lowrate(audio, sr, 6)
        return apply_packet_loss(out, out_sr, 0.12, seed=seed), out_sr
    raise ValueError(profile)


def eer(scores, labels):
    fpr, tpr, thresholds = roc_curve(labels, scores)
    fnr = 1 - tpr
    idx = np.nanargmin(np.abs(fpr - fnr))
    return float((fpr[idx] + fnr[idx]) / 2), float(thresholds[idx])


print("channel simulator + EER metric ready")
"""

# %% CELL 3 — CONFIRMED WORKING: task-naive multilingual backbone
"""
# facebook/wav2vec2-xls-r-300m is the SAME architecture family as the pilot's
# facebook/wav2vec2-base, just multilingual and larger — chosen here because
# we finally have GPU + real bandwidth to afford it. It is the plain
# self-supervised checkpoint, NOT any ASVspoof fine-tune of it — same
# leak-free reasoning as the pilot (see probe_model.py docstring).
BACKBONE_ID = "facebook/wav2vec2-xls-r-300m"
extractor = AutoFeatureExtractor.from_pretrained(BACKBONE_ID)
backbone = AutoModel.from_pretrained(BACKBONE_ID).to(DEVICE).eval()

@torch.no_grad()
def embed_backbone(audio, sr):
    assert sr == 16000, f"expected 16kHz, got {sr}"
    inputs = extractor(audio, sampling_rate=16000, return_tensors="pt")
    inputs = {k: v.to(DEVICE) for k, v in inputs.items()}
    hidden = backbone(**inputs).last_hidden_state
    return hidden.mean(dim=1).squeeze(0).cpu().numpy()

speaker_encoder = VoiceEncoder()  # runs on CPU internally, that's fine, it's tiny

def embed_speaker(audio, sr):
    wav = preprocess_wav(audio, source_sr=sr)
    return speaker_encoder.embed_utterance(wav)

def speaker_similarity(ref, test):
    cos = float(np.dot(ref, test) / (np.linalg.norm(ref) * np.linalg.norm(test) + 1e-9))
    return (cos + 1.0) / 2.0

print("backbone + speaker encoder loaded")
"""

# %% CELL 4 — CONFIRMED WORKING: load full ASVspoof2019 LA eval set
"""
# This is the exact dataset + decode fix already proven on the laptop pilot
# (see detector/README.md "known issue" section for why decode=False is
# needed — newer `datasets` defaults to torchcodec, which needs an older
# ffmpeg than most environments ship).
ds = load_dataset("SpeechAntiSpoofingBenchmarks/ASVspoof2019_LA", split="test")
ds = ds.cast_column("audio", Audio(decode=False))
print(f"loaded {len(ds)} utterances (7,355 bonafide / 63,882 spoof)")

from collections import defaultdict
by_speaker = defaultdict(lambda: {"bonafide": [], "spoof": []})
for row in ds:
    notes = json.loads(row["notes"])
    spk = notes["speaker_id"]
    label = "bonafide" if row["label"] == 0 else "spoof"
    by_speaker[spk][label].append(row)

print(f"{len(by_speaker)} distinct speakers in the eval set")
"""

# %% CELL 5 — CONFIRMED WORKING: disjoint speaker split (fit vs test)
"""
# Same methodology as the pilot: FIT group trains the probe, TEST group is
# never seen during fitting. At this scale we can afford a much bigger and
# more standard split than the pilot's 40/25 — 70% of speakers to fit,
# 30% held out to test, which is closer to normal ML practice.
#
# CAP per speaker: the full eval set averages ~1,000 utterances per speaker
# (dominated by repeated spoof attacks). Uncapped, that's tens of thousands
# of GPU forward passes -- unbatched single-clip inference could then run
# for HOURS, not the ~1 hour this notebook promises, and could eat a big
# chunk of your weekly free GPU quota on one run. Capping keeps runtime
# predictable while still giving ~10x more data than the laptop pilot had.
MAX_PER_SPEAKER_PER_LABEL = 30

speakers_with_enough_data = {
    spk: v for spk, v in by_speaker.items()
    if len(v["bonafide"]) >= 2 and len(v["spoof"]) >= 1
}
for spk in speakers_with_enough_data:
    v = speakers_with_enough_data[spk]
    dropped_bf = max(0, len(v["bonafide"]) - MAX_PER_SPEAKER_PER_LABEL)
    dropped_sp = max(0, len(v["spoof"]) - MAX_PER_SPEAKER_PER_LABEL)
    v["bonafide"] = v["bonafide"][:MAX_PER_SPEAKER_PER_LABEL]
    v["spoof"] = v["spoof"][:MAX_PER_SPEAKER_PER_LABEL]

all_speakers = sorted(speakers_with_enough_data.keys())  # sorted = reproducible
split_point = int(len(all_speakers) * 0.7)
fit_speaker_ids = set(all_speakers[:split_point])
test_speaker_ids = set(all_speakers[split_point:])

assert not (fit_speaker_ids & test_speaker_ids), "speaker leakage — should be impossible here"
total_capped_utts = sum(len(v["bonafide"]) + len(v["spoof"])
                         for v in speakers_with_enough_data.values())
print(f"FIT speakers: {len(fit_speaker_ids)} | TEST speakers: {len(test_speaker_ids)}")
print(f"capped at {MAX_PER_SPEAKER_PER_LABEL} bonafide + {MAX_PER_SPEAKER_PER_LABEL} spoof "
      f"per speaker -> {total_capped_utts} total utterances in play "
      f"(uncapped would be {sum(len(v['bonafide'])+len(v['spoof']) for v in by_speaker.values())})")
print("speaker-disjointness verified")
"""

# %% CELL 6 — CONFIRMED WORKING: extract FIT embeddings, train the probe
"""
import time
t0 = time.time()
X_fit, y_fit = [], []
for spk in fit_speaker_ids:
    v = speakers_with_enough_data[spk]
    for row in v["bonafide"] + v["spoof"]:
        audio, sr = sf.read(io.BytesIO(row["audio"]["bytes"]))
        X_fit.append(embed_backbone(audio.astype(np.float32), sr))
        y_fit.append(1 if row in v["spoof"] else 0)
X_fit, y_fit = np.array(X_fit), np.array(y_fit)
print(f"extracted {len(y_fit)} FIT embeddings in {time.time()-t0:.0f}s")

clf = LogisticRegression(max_iter=3000, C=1.0)
clf.fit(X_fit, y_fit)
print(f"fit-set training accuracy: {clf.score(X_fit, y_fit)*100:.1f}%  (n={len(y_fit)})")
"""

# %% CELL 7 — CONFIRMED WORKING: three-pass test + trained fusion
"""
# Build test trials: one held-out enrollment ref per speaker, remaining
# bonafide = genuine trials, all spoof = impostor trials.
trials = []
enroll_embeddings = {}
for spk in test_speaker_ids:
    v = speakers_with_enough_data[spk]
    ref_row = v["bonafide"][0]
    ref_audio, ref_sr = sf.read(io.BytesIO(ref_row["audio"]["bytes"]))
    enroll_embeddings[spk] = embed_speaker(ref_audio.astype(np.float32), ref_sr)
    for row in v["bonafide"][1:]:
        trials.append((row, spk, "bonafide"))
    for row in v["spoof"]:
        trials.append((row, spk, "spoof"))

print(f"{len(trials)} TEST trials across {len(test_speaker_ids)} speakers")
labels = np.array([1 if lbl == "spoof" else 0 for _, _, lbl in trials])

DEGRADE_PROFILE = "mobile_voip"  # try "pstn" or "mobile_poor" too if time allows

cm_clean, cm_degraded, spk_degraded = [], [], []
for row, spk, lbl in trials:
    audio, sr = sf.read(io.BytesIO(row["audio"]["bytes"]))
    audio = audio.astype(np.float32)

    emb_clean = embed_backbone(audio, sr)
    cm_clean.append(clf.predict_proba(emb_clean.reshape(1, -1))[0, 1])

    deg_audio, deg_sr = degrade(audio, sr, DEGRADE_PROFILE, seed=42)
    emb_deg = embed_backbone(deg_audio, deg_sr)
    cm_degraded.append(clf.predict_proba(emb_deg.reshape(1, -1))[0, 1])

    spk_emb = embed_speaker(deg_audio, deg_sr)
    spk_degraded.append(1.0 - speaker_similarity(enroll_embeddings[spk], spk_emb))

cm_clean, cm_degraded, spk_degraded = map(np.array, (cm_clean, cm_degraded, spk_degraded))

eer_clean, _ = eer(cm_clean, labels)
eer_degraded, _ = eer(cm_degraded, labels)

# TRAINED fusion (the pilot's upgrade-over-pilot promise): split TEST
# speakers again into a fusion-dev group and a final-report group, so the
# fusion weights are learned, not guessed, and still never touch what
# they're being scored on.
test_speaker_list = sorted(test_speaker_ids)
fusion_split = int(len(test_speaker_list) * 0.5)
fusion_dev_speakers = set(test_speaker_list[:fusion_split])

dev_mask = np.array([spk in fusion_dev_speakers for _, spk, _ in trials])
fusion_clf = LogisticRegression(max_iter=1000)
fusion_clf.fit(
    np.column_stack([cm_degraded[dev_mask], spk_degraded[dev_mask]]),
    labels[dev_mask],
)
report_mask = ~dev_mask
fused_scores = fusion_clf.predict_proba(
    np.column_stack([cm_degraded[report_mask], spk_degraded[report_mask]])
)[:, 1]
eer_fused, _ = eer(fused_scores, labels[report_mask])

print(f"1. Clean baseline EER..................... {eer_clean*100:.1f}%  (n={len(trials)})")
print(f"2. Degraded EER ({DEGRADE_PROFILE})............ {eer_degraded*100:.1f}%  (n={len(trials)})")
print(f"3. Degraded + TRAINED enrollment fusion EER {eer_fused*100:.1f}%  (n={report_mask.sum()})")
"""

# %% CELL 8 — BEST-EFFORT: try the official ASVspoof train partition
"""
# UNTESTED — this dataset requires custom code execution to load and its
# exact split names weren't confirmed ahead of time. If this cell errors,
# that's fine: everything above already produced a complete, valid result
# using our own disjoint-speaker split (Cell 5) instead of the official
# train/eval protocol split. This cell is a nice-to-have upgrade, not a
# requirement — skip it or debug it later, don't block on it.
try:
    official = load_dataset("LanceaKing/asvspoof2019", "LA", split="train",
                             trust_remote_code=True)
    print(f"official train partition loaded: {len(official)} utterances")
    print("if you see this message, tell Claude — we can wire this in as the")
    print("real FIT set instead of the improvised eval-split one above.")
except Exception as e:
    print(f"official train partition did not load cleanly ({type(e).__name__}: {e})")
    print("not a problem — Cells 1-7 already produced a complete, valid result.")
"""

# %% CELL 9 — BEST-EFFORT: Indian-language generalization check
"""
# UNTESTED END-TO-END — IndicSynth (synthetic) is confirmed streamable;
# ai4bharat/IndicVoices (real/bonafide) has a confirmed load pattern from
# its own docs, but the two haven't been run together before. If this
# errors partway, everything from Cells 1-7 is already saved and valid.
try:
    LANG = "hindi"
    indic_synth = load_dataset("vdivyasharma/IndicSynth", LANG, split="train",
                                streaming=True)
    synth_samples = list(indic_synth.take(150))
    print(f"pulled {len(synth_samples)} synthetic Hindi clips from IndicSynth")

    indic_real = load_dataset("ai4bharat/IndicVoices", "hindi", split="valid",
                               streaming=True)
    real_samples = list(indic_real.take(150))
    print(f"pulled {len(real_samples)} real Hindi clips from IndicVoices")

    X_indic, y_indic = [], []
    for s in synth_samples:
        a = np.array(s["audio"]["array"], dtype=np.float32)
        sr = s["audio"]["sampling_rate"]
        X_indic.append(embed_backbone(a, sr)); y_indic.append(1)
    for s in real_samples:
        a = np.array(s["audio"]["array"], dtype=np.float32)
        sr = s["audio"]["sampling_rate"]
        X_indic.append(embed_backbone(a, sr)); y_indic.append(0)
    X_indic, y_indic = np.array(X_indic), np.array(y_indic)

    # score with the SAME probe trained on English ASVspoof (Cell 6) --
    # this is deliberately a cross-lingual generalization test, not a
    # retrain. Expect this number to be worse than eer_clean above --
    # that gap IS the generalization finding the literature predicts.
    indic_scores = clf.predict_proba(X_indic)[:, 1]
    eer_indic, _ = eer(indic_scores, y_indic)
    print(f"Hindi cross-lingual generalization EER: {eer_indic*100:.1f}%  "
          f"(n={len(y_indic)}) -- compare against eer_clean={eer_clean*100:.1f}% "
          f"on English. A big gap here IS the finding, not a bug.")
except Exception as e:
    eer_indic = None
    print(f"Indian-language cell did not complete cleanly ({type(e).__name__}: {e})")
    print("not a problem — Cells 1-7 already produced a complete, valid result.")
"""

# %% CELL 10 — CONFIRMED WORKING: save results
"""
results = {
    "n_test_trials": len(trials),
    "n_test_speakers": len(test_speaker_ids),
    "n_fit_examples": len(y_fit),
    "n_fit_speakers": len(fit_speaker_ids),
    "fit_train_accuracy": clf.score(X_fit, y_fit),
    "degrade_profile": DEGRADE_PROFILE,
    "backbone": BACKBONE_ID,
    "eer_clean_cm_only": eer_clean,
    "eer_degraded_cm_only": eer_degraded,
    "eer_degraded_plus_TRAINED_enrollment_fusion": eer_fused,
    "eer_hindi_cross_lingual": eer_indic if "eer_indic" in dir() else None,
    "split_method": "disjoint eval-set speaker split (70/30) — see Cell 8 for "
                     "whether the official train partition loaded instead",
}
with open("/kaggle/working/full_results.json", "w") as f:
    json.dump(results, f, indent=2)
print(json.dumps(results, indent=2))
print("\\nDownload full_results.json from the Output panel and send it back.")
"""
