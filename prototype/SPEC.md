# Sentinel — Prototype Specification

**SIH 2026 · PS SIH26104 · the working prototype for the voice-cloning defence**

Audience: the engineer/agent building this. Read `WHAT-YOU-GET.md` first if you
want the non-technical framing, and `../TEAM-BRIEFING.md` for why the design is
shaped this way.

---

## 1. What this is

A **vertical slice**: one complete path through all four layers of the system
(TRIGGER → VERIFY → CHALLENGE → EVIDENCE), running end-to-end on a real audio
stream, on one 16 GB laptop, with the network unplugged.

It is not a product. It is the smallest thing that is genuinely *the system*
rather than a mock of it.

### The demo it must produce

1. A call plays. A live transcript appears as words are spoken.
2. The system sits visibly quiet — deliberately not scoring.
3. The caller says *"transfer two crore to this account tonight."*
   **The trigger fires** and lights up.
4. Deep verification engages: enrolled-voice match + synthesis-artifact score
   over a rolling window.
5. A risk timeline fills in live.
6. A verdict lands: `VERIFIED` · `UNCERTAIN — ESCALATE` · `LIKELY IMPERSONATION`.
7. An evidence panel shows which seconds were suspicious, both scores, the
   model and calibration IDs, and the recommended action.
8. Run again with a cloned voice of the same speaker → different verdict.

### The demo feature that wins the argument

A toggle: **"Naive mode (score every call)"** vs **"Sentinel mode (triggered)"**.

In naive mode, run the same detector continuously over the whole call and show
a running **false-alarm counter** climbing on genuine calls. In Sentinel mode,
it stays at zero because the system never speaks until stakes are real.

This turns the base-rate argument — our strongest point, and the one thing
competing teams will not have thought about — from a claim on a slide into
something a judge watches happen. **Treat this as a required feature, not a
stretch goal.**

---

## 2. Design principle

> Separate the parts that will change from the parts that won't.

Exactly three things will change after the prototype:

| Will change | Interface that absorbs it |
|---|---|
| Where audio comes from (file → mic → SIP/RTP) | `AudioSource` protocol |
| Which models score it (pilot probe → fine-tuned) | `CountermeasureModel` / `SpeakerEncoder` protocols |
| What the thresholds are (pilot → full-scale calibration) | `calibration.json`, loaded, never hardcoded |

**Those three get abstractions. Nothing else does.** No plugin system, no
database, no dependency-injection framework, no build step. Every other
abstraction you are tempted to add is speculative and will cost more than it
saves.

---

## 3. Non-goals — do not build these

| Not building | Why |
|---|---|
| Real SIP/Asterisk telephony | Days of setup, and it breaks on venue networks. `RtpSource` is a stub with a docstring. |
| Model training / fine-tuning | Separate track. This consumes model artifacts, it does not produce them. |
| Indian-language support | Needs the multilingual evaluation. Demo audio is English. |
| TTS-vs-RVC branch classification | Needs training data we don't have. The `attack_type` field exists in the types and is always `UNKNOWN`. |
| Prosody / behavioural analysis | PS component 1b. Designed, not built. Do not fake it. |
| Database, auth, multi-tenancy | JSONL is the evidence log. There is one user. |
| React / any build step | A single vendored HTML+JS+CSS. A build step is a failure mode on stage. |
| Docker | Another failure mode on stage. |

If you find yourself building any of these, stop.

---

## 4. Environment

**Use the existing `detector/venv` (Python 3.9.6). Do not create a new one.**

This is deliberate. `torch 2.8`, `transformers 4.57`, and `resemblyzer` already
install and work there. Re-solving that on Python 3.12 risks the `webrtcvad`
compile step that Resemblyzer pulls in, and buys nothing in a 4-day window.

Constraints this imposes — all trivial:
- `from __future__ import annotations` at the top of every module (the existing
  code already does this)
- No `match` statements, no `tomllib`
- Use `typing.Protocol`, `Literal`, `Optional` rather than 3.10+ syntax at runtime

**Hardware assumed:** Apple Silicon (arm64), 16 GB RAM, `ffmpeg` on PATH,
Metal (MPS) available to torch. `ProbeBackbone` already selects MPS
automatically.

**New dependencies to add:**

```
faster-whisper        # ASR. CTranslate2 backend, int8, CPU-fast on M-series.
sentence-transformers # trigger semantics (MiniLM-L6-v2, ~80 MB)
fastapi uvicorn[standard] websockets
sounddevice           # optional, mic source only
pytest pytest-asyncio
```

**Everything must work with the network unplugged.** All models download once
during setup, then run from local cache. Add a `scripts/prefetch_models.py`
that pulls every model and a `--offline` smoke test that fails loudly if
anything tries to reach the network at run time.

---

## 5. Reusing the existing code

`detector/src/` already contains the algorithms, and they are clean:

| Module | What it gives us | Gap to close |
|---|---|---|
| `probe_model.py` | `ProbeBackbone.embed()` — task-naive wav2vec2 features | none |
| `speaker_id.py` | `embed()`, `similarity()` — Resemblyzer | orientation, see below |
| `channel_sim.py` | `degrade()` — Opus/G.711/packet loss | none |
| `metrics.py` | `eer()` → `(eer, threshold)` | none |
| `run_experiment_v2.py` | fits the logistic probe | **fits at runtime, never saves it** |

Import them by adding `detector/src` to `sys.path` in one place
(`sentinel/models/registry.py`). Do **not** copy-paste them — a divergent copy
is how the experiment and the demo start disagreeing about what the system does.

*(Later, promote `detector/src` to an installable `voiceguard_core` package that
both depend on. Not now — refactoring mid-crunch is how deadlines are missed.)*

### Three gaps you must close first

**Gap 1 — the probe is never persisted.** `run_experiment_v2.py` fits a
`LogisticRegression` in memory and throws it away. The live system cannot refit
on startup. Write `scripts/fit_probe.py` that fits it exactly as the experiment
does and saves:

```
artifacts/probe_head.npz      coef_, intercept_
artifacts/calibration.json    eer_threshold, per-class score mean/std,
                              fusion weights, and provenance
```

`calibration.json` provenance block is mandatory:

```json
{
  "created_utc": "2026-08-29T...",
  "dataset": "ASVspoof2019-LA pilot slice",
  "n_fit_examples": 117,
  "n_test_trials": 119,
  "backbone": "facebook/wav2vec2-base",
  "eer": 0.117,
  "eer_threshold": 0.53,
  "fusion": {"strategy": "mean", "weights": [0.5, 0.5]},
  "notes": "PILOT SCALE. Replace when the Kaggle full run lands."
}
```

Every verdict written to the evidence log carries `calibration_id`. When the
Kaggle run lands, you drop in a new file and the log records which calibration
produced which decision. That is what keeps us honest, and it costs ten lines.

**Gap 2 — score orientation is inconsistent.** `similarity()` returns *higher =
same person*. The CM returns *higher = fake*. `run_experiment_v2.py` fixes it
inline with `1.0 - sim`. In a streaming system that inline flip will get lost
and produce a silently inverted verdict.

> **Convention, enforced at the adapter boundary and stated in one place:
> every score in this system is a RISK in `[0, 1]` where higher = more
> suspicious.**

The `SpeakerEncoder` adapter does the inversion once. Nothing downstream ever
thinks about it. Add a test that asserts an identical-voice pair produces a
*low* risk.

**Gap 3 — silence will crash Resemblyzer.** `preprocess_wav()` runs VAD
internally and can return an empty array on a silent window, which then blows
up `embed_utterance`. A streaming system hits silent windows constantly
(pauses, hold, line noise). Gate every window on a cheap energy/VAD check
before scoring, and emit an explicit `SILENT` score rather than a crash or a
fake number.

---

## 6. Architecture

```
  AudioSource (file | mic | rtp-stub)
        │  Frame(pcm, sr, t_start_ms, seq)   — 20 ms frames
        ▼
  Framer ──► sliding windows (3.0 s, hop 0.5 s)
        │
        │                                    ┌──────────────────────┐
        ├───────────────────────────────────►│  ASR thread          │
        │        (bounded queue, blocks)     │  faster-whisper      │
        │                                    └──────────┬───────────┘
        │                                        Utterance
        │  ┌─────────────────────────────────────────┘
        │  ▼
        │  TriggerEngine  (lexical prefilter → semantic confirm)
        │       │  TriggerEvent
        │       ▼
        │  GatingPolicy ──────────┐
        ▼                         │
   ══ PIPELINE THREAD (sequential) ══
    VAD ──► SpeakerScore (always) ──► CmScore (only if gated on)
                          │
                          ▼
                   DecisionEngine   (PURE: scores + config → Verdict)
                          │
        ┌─────────────────┴──────────────────┐
        ▼                                    ▼
  EvidenceLog                          queue.Queue
  (hash-chained JSONL)                       │
                                             ▼
                                    WebSocket ──► UI
```

### Package layout

```
prototype/
  sentinel/
    __init__.py
    config.py            one dataclass, loaded from config.yaml.
                         NO magic numbers anywhere else in the codebase.
    types.py             Frame, Window, RiskScore, Utterance,
                         TriggerEvent, Verdict, Evidence — frozen dataclasses

    audio/
      source.py          AudioSource protocol; FileSource, MicSource, RtpSource(stub)
      framing.py         frames → sliding windows
      vad.py             energy gate — is there speech here?
      resample.py        → 16 kHz

    models/
      base.py            CountermeasureModel, SpeakerEncoder protocols
      probe_cm.py        wraps ProbeBackbone + persisted logistic head
      resemblyzer_spk.py wraps speaker_id, DOES THE RISK INVERSION
      registry.py        build_models(config) — the only place sys.path is touched

    enrolment/
      store.py           EnrolmentStore — feature vectors only, never audio

    asr/
      transcriber.py     faster-whisper → Utterance events

    trigger/
      intents.py         canonical high-risk intent sentences
      engine.py          stage 1 lexical prefilter → stage 2 semantic similarity

    decision/
      calibration.py     raw score → calibrated risk
      fusion.py          FusionStrategy: MeanFusion | LogisticFusion
      engine.py          PURE decide(). No I/O. Fully unit-tested.
      gating.py          GatingPolicy: TriggeredGating | AlwaysOnGating

    evidence/
      log.py             append-only hash-chained JSONL

    pipeline/
      events.py          thread-safe event queue + drop counter
      asr_thread.py      the one background thread (ASR only)
      orchestrator.py    the sequential pipeline loop; wall-clock pacing

    server/
      app.py             FastAPI + WebSocket
      static/            index.html, app.js, style.css — NO CDN, all vendored

    cli.py               sentinel enrol | run | calibrate | demo

  scripts/
    fit_probe.py         fit + persist probe head and calibration.json
    make_demo_calls.py   build genuine + cloned demo audio
    prefetch_models.py   download every model once, for offline operation

  artifacts/             probe_head.npz, calibration.json, enrolments/
  tests/
  config.yaml
```

### Core types

```python
@dataclass(frozen=True)
class Frame:
    pcm: np.ndarray      # float32 mono
    sr: int
    t_start_ms: int      # STREAM time, never wall clock
    seq: int

@dataclass(frozen=True)
class RiskScore:
    kind: str            # "cm" | "speaker" | "fused"
    value: float         # [0,1], higher = more suspicious. ALWAYS.
    t_start_ms: int
    t_end_ms: int
    model_id: str
    status: str          # "OK" | "SILENT" | "ERROR"

@dataclass(frozen=True)
class Verdict:
    state: str           # MONITORING | VERIFIED | UNCERTAIN | LIKELY_IMPERSONATION
    risk: float
    confidence: float
    reasons: List[str]   # human-readable, shown in the evidence panel
    t_ms: int
    calibration_id: str
```

---

## 7. Contracts that matter

### 7.1 Stream time, never wall clock

Every event carries `t_*_ms` measured from stream start. This is what makes a
file replay and a live mic run produce **identical event logs**, which is what
makes the golden test in §9 possible. Wall-clock timestamps anywhere in the
event path will destroy both.

### 7.2 Concurrency — keep it boring

**Do not build three async workers.** Run the numbers first:

| Stage | Cost | Frequency |
|---|---|---|
| Speaker embed | 30–60 ms | every 0.5 s hop |
| CM embed | 40–80 ms | only when gated on |
| ASR | 300–600 ms | once per utterance (~every 3 s) |

Against a 0.5 s hop budget, that fits in a **single sequential loop** with room
to spare. Three async workers, a bus, and three queue policies would be
speculative complexity solving a problem we do not have.

**The design:**

- **One pipeline thread** runs the loop synchronously: read frame → window →
  VAD → speaker → (gated) CM → decide → emit. It sleeps to track wall clock so
  a file replays at true speed.
- **ASR on its own thread**, because it is the only stage whose worst case
  (600 ms) exceeds the hop. It consumes from a bounded queue and publishes
  `Utterance` events back. This is the one place concurrency earns its cost.
- **A single thread-safe `queue.Queue` of events** drained by the FastAPI
  WebSocket handler. That is the entire transport.

Two overflow policies, both stated in `config.yaml`:

| Queue | Bound | Overflow | Why |
|---|---|---|---|
| ASR input | ~200 frames | **block** | the transcript must be complete; a gap is a missed trigger |
| Event → UI | 1000 events | drop oldest, count drops | the UI is a view; losing a frame of it is harmless |

Emit `pipeline_lag_ms` to the UI. If we fall behind real time, say so on screen
rather than silently claiming to be real-time.

*If profiling later proves the loop can't keep up, splitting the speaker and CM
stages out is a contained change — they already sit behind the model protocols.
Do not pre-emptively split them.*

### 7.3 Gating

```python
class GatingPolicy(Protocol):
    def should_run_deep(self, t_ms: int, triggers: Sequence[TriggerEvent]) -> bool: ...
```

- `TriggeredGating` — deep CM scoring runs only inside a window
  (`pre_roll_s` before → `hold_s` after) around a trigger. **Pre-roll matters:**
  by the time the trigger fires the incriminating audio has already gone past,
  so keep a rolling buffer and score backwards.
- `AlwaysOnGating` — runs continuously. This is the naive design the PS
  describes; it exists so the demo can show it failing.

The speaker check runs **always** (it's cheap and it's our primary signal). The
CM check is what's gated. That ordering is our thesis expressed in code.

### 7.4 The decision engine is pure

```python
def decide(
    cm: Optional[RiskScore],
    spk: Optional[RiskScore],
    enrolled: bool,
    triggered: bool,
    cal: Calibration,
    cfg: DecisionConfig,
) -> Verdict
```

No I/O, no clock, no globals. Every branch table-driven-testable. This is where
the logic that a judge will interrogate actually lives, so it is the one module
that must be provably right.

Required behaviour:
- Not triggered → `MONITORING`, regardless of scores.
- Triggered + enrolled + fused risk below `low_thr` → `VERIFIED`
- Triggered + enrolled + fused risk above `high_thr` → `LIKELY_IMPERSONATION`
- Anything between, **or** not enrolled, **or** either score `SILENT`/`ERROR`
  → `UNCERTAIN` with a reason string
- `reasons` is never empty. The evidence panel shows it verbatim.

**Abstention is a first-class outcome, not an error path.** If the demo lands on
`UNCERTAIN` on stage, that is the system working correctly — and the presenter
should say so.

### 7.5 Privacy is a code property, not a slide claim

`EnrolmentStore` persists **feature vectors only**. No `.wav`, no PCM, ever.
There is a test that walks the output directory after a full run and fails if
any audio-bearing file exists (§9). We claim this on slide 2; the test is what
makes the claim true.

### 7.6 Evidence log

Append-only JSONL. Each record includes `prev_hash` = SHA-256 of the previous
record, making the chain tamper-evident. Records carry `model_id` and
`calibration_id`. This file *is* the "tamper-proof record" on the slides.

---

## 8. Trigger design

Two stages, and the two-stage structure is itself the answer to *"isn't this
just keyword matching?"*

**Stage 1 — lexical prefilter.** Cheap regex/keyword pass over the rolling
transcript. Catches the obvious, costs nothing, runs on every utterance.

**Stage 2 — semantic confirmation.** Embed the utterance with MiniLM and
compare against a curated set of canonical high-risk intent sentences:

- fund transfer instruction
- credential / OTP / password request
- urgency combined with authority pressure
- request to bypass an existing verification procedure
- instruction not to call back or not to tell anyone

Fire when cosine similarity to any canonical intent exceeds a threshold, **or**
when stage 1 hits and stage 2 does not contradict it.

Stage 2 is what makes paraphrases work — *"push the funds across tonight"* has
no keyword overlap with *"transfer money"* but sits close to it in embedding
space. Test that specific property (§9). It's ~30 lines and it converts a
weakness into a talking point.

---

## 9. Testing strategy

Test what will actually break or be challenged. Not coverage theatre.

| Test | What it protects |
|---|---|
| `test_decision_engine.py` | Table-driven over every branch of `decide()`. The logic a judge will interrogate. |
| `test_calibration.py` | Monotonicity, boundary behaviour, missing-file handling. |
| `test_score_orientation.py` | Identical voices → **low** risk. Guards Gap 2 forever. |
| `test_trigger.py` | ~30 sentences, 15 triggering / 15 not, **including paraphrases with zero keyword overlap**. This test *is* the answer to the keyword criticism. |
| `test_privacy.py` | Run the pipeline, walk the output tree, fail if any audio file was persisted. Makes the slide claim true. |
| `test_pipeline_golden.py` | Fixed WAV + fixed seed → snapshot the event sequence. Catches regressions across the whole spine. |
| `test_vad_silence.py` | A silent window yields `SILENT`, not a crash and not a fabricated score. |
| `test_offline.py` | Runs with network access blocked. Fails loudly if anything reaches out. |
| `bench_latency.py` | Measures and reports. Does **not** assert a hard number — it's a measurement tool, not a gate. |

---

## 10. Latency budget

State this openly; a judge will ask, and "we measured it" beats "it's fast".

| Stage | Expected (M-series, MPS) |
|---|---|
| Frame → window | 20 ms frames, 3.0 s window, 0.5 s hop |
| wav2vec2-base embed (3 s) | 40–80 ms |
| Resemblyzer embed (3 s) | 30–60 ms |
| faster-whisper `base.en` int8, 2–4 s utterance | 300–600 ms |
| Trigger (MiniLM) | ~10 ms |
| Decision + emit | < 5 ms |
| **End of triggering phrase → verdict on screen** | **target < 1.5 s** |

The PS says *"near real time"*. We meet that comfortably and we report the
measured number rather than a claimed one.

---

## 11. Demo audio

Two paths. **Build the safe one first and get the whole demo working on it.**

**Safe (required).** `detector/data/pilot/` already holds ASVspoof2019-LA
clips: genuine and spoofed recordings **of the same speakers**, with ground
truth. Pick a speaker with a clean enrolment clip plus one genuine and one
spoofed test clip. Run both through `channel_sim.degrade()` so they sound like
a real phone call. Zero setup risk. Works today.

**Dramatic (stretch, day 4 only, and only if days 1–3 landed).** Record a
teammate for 30 s, clone their voice with open-source TTS, demo on a voice the
judges heard live thirty seconds earlier. Far more impactful — and voice-cloning
toolchains are fragile and can eat half a day.

> **Hard rule: the stretch path never replaces the safe path.** Both demo calls
> stay in `artifacts/demo/` and the UI can switch between them. If the clone
> path fails at 2am, the demo still works.

Also required: a **screen recording of a successful run**, saved before the
event. Never present live without a recorded fallback.

---

## 12. Honesty rules for the UI

These are non-negotiable, because the whole project's credibility rests on them.

- The UI header always shows the **calibration provenance** — dataset and EER —
  next to the risk number. The number is never presented naked.
- The demo mode banner reads **"Simulated live call — recorded audio streamed
  in real time."** Never call it a live phone call.
- `UNCERTAIN` is styled as a *legitimate outcome*, in the same visual weight as
  the other two. Not as an error, not greyed out.
- If `pipeline_lag_ms` exceeds real-time, show it. Do not hide falling behind.
