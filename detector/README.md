# Detector pilot — the three-number experiment

This proves the enrollment thesis from `PROJECT-EXPLAINED.md` with real data,
at pilot scale, on a laptop with no GPU. It is the mechanism proof, not the
final slide-one number.

**Use `run_experiment_v2.py` and `pilot_results_v2_leakfree.json`.**
`run_experiment.py` (v1) is kept in the repo as a documented cautionary tale —
see "Known issue" below before touching it.

## Results (pilot scale — read the honesty notes before quoting these anywhere)

| # | Question | Result |
|---|---|---|
| 1 | Clean baseline EER (probe CM only) | **7.9%** |
| 2 | Degraded EER — Opus 8kbps + 5% packet loss (probe CM only) | **13.5%** |
| 3 | Degraded + enrollment fusion EER | **11.7%** |

n=119 test trials, 25 test speakers, fit on 117 examples from 40 disjoint
speakers. Direction matches the thesis: the phone line hurts (+5.6pp), and
enrollment recovers about a third of that loss even with *untrained* fusion
(simple averaging, not a learned combiner — see notes below). The full-scale
Kaggle run should show a larger recovery once fusion is actually trained.

## What this measures

| # | Question | Script step |
|---|---|---|
| 1 | How good is a blind detector on clean audio? | probe CM alone |
| 2 | How much does an Indian phone line hurt it? | + `channel_sim.py` |
| 3 | How much does enrollment recover? | + `speaker_id.py` fusion |

## ⚠️ Known issue: v1 was leaking, don't reuse its numbers

`run_experiment.py` (v1) used a pretrained checkpoint
(`Gustking/wav2vec2-large-xlsr-deepfake-audio-classification`) as the CM
model. It reported **0.0% EER on all three passes** — which is not a real
result. Inspecting raw scores showed bonafide clips clustered at
mean=0.069, **std=0.003** — near-zero variance, the signature of a model
that memorized this exact benchmark rather than learning to detect
synthesis artifacts. That checkpoint's author almost certainly fine-tuned
on ASVspoof2019 without respecting the official speaker-disjoint
train/eval protocol, so our "eval" was actually testing on data the model
had already seen.

**This is worth keeping in the pitch, not hiding.** Free "deepfake
detector" checkpoints on Hugging Face cannot be trusted at face value —
several report inflated accuracy from exactly this mistake. Most competing
teams will grab one, get a suspiciously perfect number, and never check why.

**The fix (`run_experiment_v2.py`, `probe_model.py`):** discard the
Gustking checkpoint's classification head *and* its encoder (fine-tuning
contaminates the encoder too, not just the head — reusing it as a "frozen
feature extractor" doesn't remove the leak). Instead:

1. Use `facebook/wav2vec2-base` — a self-supervised backbone that has
   **never seen a bonafide/spoof label or the ASVspoof task at all.**
2. Fit our own logistic-regression probe on a **FIT speaker group** (40
   speakers, 117 files) with **zero speaker overlap** with the **TEST
   speaker group** (25 speakers) used for every reported number.
   Disjointness is asserted in code, not just claimed.

This is standard "linear probing" methodology and is genuinely leak-free
with respect to the deepfake-detection task.

## Honesty notes — read before quoting a number anywhere

- **Pilot scale.** 25 test speakers, 119 trials. Enough to prove the
  mechanism (does the number move in the predicted direction, by roughly
  how much) — not enough for a tight, publication-grade EER estimate.
  Confidence intervals on ~119 trials are wide; a handful of flipped
  trials would shift these numbers by several points.
- **English-centric benchmark.** ASVspoof2019 LA, not Indian languages. It's
  the dataset with speaker-ID pairing already built in, which is what makes
  the enrollment experiment possible without weeks of data prep. The
  Indian-language slice (IndicSynth) is in the Kaggle notebook, not here —
  it's 845GB, no bonafide class of its own, and needs pairing against
  IndicSUPERB. That's a full-scale job.
- **wav2vec2-base, not XLSR.** English-only, 95M params — chosen because it
  downloads fast and is definitely task-naive. The Kaggle full run should
  probe a multilingual self-supervised XLSR checkpoint instead (the
  *pretrained* one, e.g. `facebook/wav2vec2-xls-r-300m` — NOT any
  ASVspoof fine-tune of it) for the Indian-language test.
- **Only 117 fit examples.** Thin for a linear probe; fit-set training
  accuracy was 94%, which is fine for a probe (it doesn't need to be
  perfect on fit data) but the probe itself is weaker than a properly
  regularized one trained on thousands of examples. Kaggle's full ASVspoof
  train partition (25,380 utterances) fixes this.
- **Unweighted mean fusion.** The pilot fuses CM score and speaker-similarity
  score by simple averaging — no dev set to learn proper fusion weights on.
  The Kaggle run fits a real logistic regression on held-out speakers. Don't
  be surprised if the full-scale fused number is meaningfully better than
  this pilot's — untrained fusion is a conservative (pessimistic) estimate.
- **Channel simulation covers Opus + G.711 + packet loss**, not AMR (this
  Mac's ffmpeg build lacks a free AMR encoder — it's patent-encumbered and
  usually excluded). Opus dominates VoIP/WhatsApp/mobile-data calls; G.711
  dominates PSTN and bank call-center trunks. Between them they cover the
  realistic channel space for the demo.
- **Speaker embeddings**: Resemblyzer (MIT). Lightweight stand-in for a
  production ECAPA-TDNN model — good enough to prove the mechanism, not
  what you'd ship.

## Running it

```bash
cd detector
source venv/bin/activate
python src/fetch_data.py         # streams ~260 pilot clips from Hugging Face, caches locally
python src/run_experiment_v2.py  # leak-free: fits its own probe, runs all three passes
```

Results land in `results/pilot_results_v2_leakfree.json`.

## Going to full scale (Kaggle)

See `notebooks/kaggle_full_run.py` — 10 cells, copy-paste ready, clearly
marked CONFIRMED WORKING vs BEST-EFFORT (see that file's header for what
that distinction means and why). Non-technical runbook: `KAGGLE-RUNBOOK.md`.

Same leak-free methodology as the pilot (task-naive backbone, speaker-
disjoint fit/test split, verified in code not just claimed), but at real
scale: full ASVspoof eval set (71,237 utterances, not our 261-file sample),
a multilingual backbone (`wav2vec2-xls-r-300m` vs the pilot's English-only
`wav2vec2-base`), a properly **trained** fusion classifier (not the pilot's
unweighted-mean placeholder), and two best-effort extensions — the official
train/eval protocol split, and a Hindi cross-lingual generalization check.

**This is the run whose numbers go on the idea-PPT slide** — not the pilot.
Expected runtime: 45-70 minutes on a free Kaggle T4, comfortably inside the
30 free GPU-hours/week quota.

## Files

```
src/
  channel_sim.py      telephony degradation (G.711 / Opus / packet loss)
  cm_model.py          Gustking pretrained classifier wrapper — DO NOT
                        trust its scores directly, see "known issue" above.
                        Kept for reference / as a worked example of the
                        leakage check.
  probe_model.py        task-naive wav2vec2-base frozen feature extractor
  speaker_id.py           Resemblyzer speaker embedding + similarity
  metrics.py               EER computation
  fetch_data.py           pulls + caches the pilot data slice
  run_experiment.py        v1, LEAKING — kept as a documented cautionary tale
  run_experiment_v2.py      v2, leak-free — use this one
notebooks/
  kaggle_full_run.py   copy-paste cells for the full-scale GPU run
results/
  pilot_results.json             v1 output — 0.0% EER, don't use
  pilot_results_v2_leakfree.json  v2 output — use this one
```
