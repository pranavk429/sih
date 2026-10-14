# Sentinel 🛡️

> **AI-Powered Real-Time Voice Cloning Detection & Impersonation Prevention**  
> *Developed for Smart India Hackathon 2026 · Problem Statement SIH26104 (AICTE)*  
> *Theme: Miscellaneous · Category: Software*

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.9%2B-brightgreen.svg)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/Tests-254%20Passing-success.svg)](prototype/tests/)
[![Architecture](https://img.shields.io/badge/Architecture-Enrolment--First-orange.svg)](#the-architecture-in-four-layers)

---

## Overview

Voice cloning tools can now replicate a human voice from seconds of sample audio. Criminals weaponize this against corporations and individuals:
- **Corporate Fraud:** Calling finance teams impersonating CXOs: *"Transfer ₹2 crore tonight for the closing acquisition; I'm in a board meeting, don't call back."*
- **Family Distress Scams:** Calling parents in a child's voice: *"Mum, I've had an accident, please send money right now."*

Both attacks succeed through **engineered urgency to prevent verification**.

Most conventional systems attempt to score every call with a universal "deepfake detector". **In the real world, this naive approach collapses.** Sentinel takes a radically different approach: an **enrolment-first, intent-gated architecture** that asks *"Is this the specific person we enrolled?"* rather than *"Is this audio synthetic?"*, running deep checks only when money or sensitive access is on the line.

---

## Why Conventional Voice Detectors Fail

### 1. The Base-Rate Fallacy (The Smoke Alarm Problem)
In banks and enterprises, fraudulent calls are rare (e.g., 1 in 5,000 calls). A detector advertising **99% accuracy** (1% false positive rate) deployed continuously produces **~50 false alarms for every real attack caught**. Within a week, operators disable the system.

### 2. Telephony Destroys Acoustic Artifacts
The acoustic markers of synthetic speech reside in fine, high-frequency details. Real phone networks apply aggressive codecs (**Opus at 8 kbps, G.711 mu-law at 8 kHz**) and packet loss that systematically strip away the exact frequencies detectors rely on. In our experiments, simulated telephony degraded detector error by over **70%**.

### 3. Generalization Collapse & Benchmark Leakage
Universal detectors memorise the generation artifacts of the specific tools they were trained on. When confronted with unseen cloning architectures or unwatermarked audio, performance plummets. Furthermore, many public checkpoints suffer from benchmark data leakage, reporting artificially inflated accuracies.

### 4. Two Distinct Threat Models
| Vector | The Robot Caller (TTS) | The Puppeteer (Voice Conversion / RVC) |
|---|---|---|
| **Mechanism** | Automated generation from typed text | Live human speaker filtered through real-time voice conversion |
| **Scale** | Can call thousands simultaneously | One attacker per active call |
| **Weakness** | Latency gaps, stumbles when interrupted | Natural prosody/pauses belong to the *attacker*, not the victim |

Sentinel provides targeted countermeasures for both vectors.

---

## The Architecture in Four Layers

```
                     ┌───────────────────────────────────────────────────┐
                     │               1. TRIGGER LAYER                    │
                     │  Continuously monitors call transcript.           │
                     │  Fires only on high-stakes intents: transfers,    │
                     │  credential demands, urgency pressure.            │
                     └─────────────────────────┬─────────────────────────┘
                                               │ (Awakened on risk)
                                               ▼
                     ┌───────────────────────────────────────────────────┐
                     │               2. VERIFICATION LAYER               │
                     │  Enrolment Reference Available?                   │
                     │  ├── YES: Speaker-ID fusion + probe countermeasure│
                     │  └── NO : General acoustic probe + abstention     │
                     │  Identifies: Robot Caller vs. Puppeteer           │
                     └─────────────────────────┬─────────────────────────┘
                                               │ (Ambiguous / High Risk)
                                               ▼
                     ┌───────────────────────────────────────────────────┐
                     │               3. CHALLENGE LAYER                  │
                     │  Active liveness challenge: injects unexpected    │
                     │  conversational prompts to test dynamic latency   │
                     │  and interrupt handling.                          │
                     └─────────────────────────┬─────────────────────────┘
                                               │
                                               ▼
                     ┌───────────────────────────────────────────────────┐
                     │               4. EVIDENCE & AUDIT                 │
                     │  Tamper-evident logs with calibration hashes.     │
                     │  Zero raw audio stored (feature embeddings only). │
                     │  Clear UNCERTAIN verdict recommending callback.   │
                     └───────────────────────────────────────────────────┘
```

1. **Trigger Layer (Intent Gating):** Uses `sentence-transformers/all-MiniLM-L6-v2` with comparative margin scoring (`similarity(fraud_intent) - similarity(benign_anchor)`). This eliminates false triggers on benign lines like *"I'll transfer you to the manager"* while catching nuanced fraud prompts.
2. **Verification Layer (Enrolment-First):** Uses a task-naive frozen `facebook/wav2vec2-base` backbone with an audited linear probe, fused with `Resemblyzer` speaker embeddings.
3. **Challenge Layer (Active Prevention):** Tests the caller in near-real-time to trip conversational latency anomalies in automated TTS agents.
4. **Evidence & Audit Layer (Privacy & Compliance):** Complies with data protection standards (e.g. DPDP Act) by storing only numerical feature representations—never raw audio. When confidence falls in the margin band, the system outputs an **UNCERTAIN** verdict, recommending a 30-second callback rather than blocking legitimate business.

---

## Experimental Validation & Findings

All findings are fully reproducible on consumer hardware without GPU requirements:

| Scenario | Metric | Result |
|---|---|---|
| **Clean Baseline** | Probe Countermeasure EER | **7.9%** |
| **Degraded Telephony** | Opus 8 kbps + 5% packet loss | **13.5%** *(+70% degradation)* |
| **Degraded + Enrolment Fusion** | Untrained 50/50 score average | **11.7%** *(clawed back ~32% of loss)* |

### The Leakage Trap We Uncovered
During initial testing with an off-the-shelf checkpoint (`Gustking/wav2vec2-large-xlsr-deepfake-audio-classification`), we observed **0.0% EER across all tests**. Inspection revealed genuine clips had a score standard deviation of **0.003**—the model had memorised the test dataset rather than learning general synthesis artifacts.

We discarded that model and rebuilt the pipeline with:
- A task-naive foundation (`facebook/wav2vec2-base`) that had never seen spoof labels.
- A strictly enforced **speaker-disjoint split** (asserted in code, halting execution if fit and test speakers ever overlap).

See [`EXPERIMENT-REPORT.md`](EXPERIMENT-REPORT.md) for full data tables, distributions, and methodology.

---

## Repository Structure

```
├── README.md                           # Project documentation & architecture overview
├── LICENSE                             # Apache 2.0 License
├── requirements.txt                    # Python dependencies
├── EXPERIMENT-REPORT.md                # Complete record of experiments, data leakage, & calibration
├── TEAM-BRIEFING.md                    # Deep-dive briefing, design rationale, and Q&A handbook
├── PROJECT-EXPLAINED.md                # Plain-language explanation of core concepts
│
├── prototype/                          # Interactive prototype & real-time server
│   ├── config.yaml                     # Calibrated thresholds & model parameters
│   ├── sentinel/                       # Core package
│   │   ├── asr/                        # faster-whisper live transcription
│   │   ├── audio/                      # AudioWorklet stream & live buffer management
│   │   ├── decision/                   # Calibration engine, threshold bands, & fusion
│   │   ├── enrolment/                  # Voice gallery & speaker lookup
│   │   ├── evidence/                   # Tamper-evident JSONL logging
│   │   ├── models/                     # wav2vec2-base feature extraction & linear probe
│   │   ├── pipeline/                   # Orchestrator wiring audio, VAD, ASR, and CM
│   │   ├── server/                     # FastAPI app, WebSockets, & REST endpoints
│   │   └── trigger/                    # Semantic intent engine & benign anchor margins
│   ├── static/                         # Real-time operator web UI & PCM worklet
│   ├── scripts/                        # Benchmarks, calibration, & fixture generators
│   └── tests/                          # Comprehensive pytest suite (254 tests)
│
└── detector/                           # Experimental lab & evaluation harness
    ├── src/
    │   ├── channel_sim.py              # Telephony simulator (Opus, G.711, packet loss)
    │   ├── probe_model.py              # Task-naive linear probe extractor
    │   ├── speaker_id.py               # Resemblyzer speaker verification
    │   ├── fetch_data.py               # ASVspoof2019 LA pilot stream & cache
    │   └── run_experiment_v2.py        # Leak-free experimental harness
    ├── notebooks/
    │   └── kaggle_full_run.py          # Full-scale GPU runbook for Kaggle
    └── results/                        # Measured JSON outputs & raw scores
```

---

## Getting Started

### Prerequisites
- Python 3.9+ (Python 3.9, 3.10, or 3.11 recommended)
- `ffmpeg` installed on your system (for audio decoding and telephony simulation)

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/pranavk429/sih.git
   cd sih
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install --upgrade "setuptools<81" pip
   pip install -r requirements.txt
   ```

---

## Running Sentinel

### 1. Run the Test Suite
Sentinel features an automated test suite with 254 unit, integration, and offline-isolation tests:
```bash
cd prototype
python -m pytest tests/ -q
```

### 2. Launch the Interactive Operator Console
Start the real-time server:
```bash
cd prototype
python -m sentinel.cli serve
```
Open your browser and navigate to **`http://127.0.0.1:8000`**.

Features available in the UI:
- **Audio Source Selection:** Switch between recorded call simulations and live microphone input.
- **Voice Enrolment:** Record a speaker sample directly in browser, compute embedding, and register in the gallery.
- **Real-Time Visuals:** Live waveform visualizer, streaming transcript with intent margins, acoustic risk timeline, and instant verdict chips (**VERIFIED**, **SUSPICIOUS**, **UNCERTAIN**).
- **Try-a-Line Intent Sandbox:** Interactively test sentences against the trigger engine to observe semantic margins.

### 3. Reproduce the Leak-Free Experiment
To reproduce the pilot experiment on ASVspoof data:
```bash
cd detector
python src/fetch_data.py         # Downloads pilot slice
python src/run_experiment_v2.py  # Executes leak-free 3-pass evaluation
```
Results will be output to `detector/results/pilot_results_v2_leakfree.json`.

---

## Academic References

1. **ASVspoof 5 & ASVspoof 2019 Challenges:** Automatic Speaker Verification and Spoofing Countermeasures ([asvspoof.org](https://www.asvspoof.org)).
2. **SASV Challenge:** Joint Speaker Verification and Anti-spoofing evaluation protocols.
3. **RawBoost:** Telephony-robust data augmentation foundation (Tak et al., ICASSP 2022).
4. **Base-Rate Fallacy in Intrusion Detection:** Axelson, S. (2000), explaining why high accuracy detectors generate high false alarm ratios under low prevalence.
5. **The Watermark Shortcut:** Investigations into synthetic speech detector memorization of watermarking artifacts (arXiv:2606.23335).

---

## License

This project is licensed under the [Apache License, Version 2.0](LICENSE).
