# Sentinel — Implementation Plan

Read `SPEC.md` first. This is the ordered task list with acceptance criteria.

**Working directory:** `prototype/`
**Interpreter:** `../detector/venv/bin/python` (Python 3.9.6 — see SPEC §4)
**Total:** 4 working days + a ~3 hour prep block that can happen any time before.

---

## Rules for whoever builds this

1. **Every task below has an acceptance criterion. Run it. Don't assume.**
   If the criterion doesn't pass, the task isn't done.
2. **Build in the order given.** The order exists because each day ends with
   something demonstrable. If day 3 collapses, day 2's console demo is still a
   real deliverable you can show.
3. **No magic numbers outside `config.yaml`.** If you type a threshold into a
   module, you've created a bug that will be found on stage.
4. **Write the test in the same commit as the code.** Not after. The tests in
   SPEC §9 are the ones that matter; skip inventing others.
5. **Commit at the end of every task** with a message saying what now works.
6. If a task is going to blow its estimate by more than ~50%, **stop and flag
   it** rather than pushing into the next day's budget. Days 3 and 4 have no
   slack.

---

# Day 0 — Prep (~3 hours, do this before Day 1)

Can be done any time. Getting this out of the way means Day 1 starts on code.

### 0.1 — Environment
Add deps to the existing venv:
```
faster-whisper sentence-transformers fastapi "uvicorn[standard]"
websockets sounddevice pytest pytest-asyncio pyyaml
```
> ⚠️ If `sentence-transformers` fights Python 3.9, fall back to `MiniLM` via
> `transformers` directly (`AutoModel` + mean pooling) — same model, ~20 more
> lines, no new dependency. Do **not** upgrade the venv to solve this.

**Done when:** `python -c "import faster_whisper, fastapi, sentence_transformers"` succeeds.

### 0.2 — `scripts/prefetch_models.py`
Downloads and caches: `facebook/wav2vec2-base`, Resemblyzer weights,
faster-whisper `base.en`, MiniLM. Prints the cache path and total size.

**Done when:** it runs clean, and re-running it makes zero network calls.

### 0.3 — `scripts/fit_probe.py` — closes Gap 1
Reuse the exact fit logic from `detector/src/run_experiment_v2.py` (same
speaker-disjoint split, same assertion). Then persist:
- `artifacts/probe_head.npz` — `coef_`, `intercept_`
- `artifacts/calibration.json` — with the full provenance block from SPEC §5

**Done when:**
- Both files exist.
- Loading `probe_head.npz` and scoring the same test trials reproduces the
  experiment's `11.7%` fused EER to within 0.1pp. **Assert this in the script.**
  If it doesn't reproduce, something is wrong with the persistence — find it now,
  not on day 3.

### 0.4 — `scripts/make_demo_calls.py`
From `detector/data/pilot/`, pick a speaker with ≥1 spare bonafide clip
(enrolment), ≥1 more bonafide (genuine call), and ≥1 spoof (attack call).
Run genuine + attack through `channel_sim.degrade(profile="mobile_voip")`.
Write to `artifacts/demo/` with a `manifest.json` recording speaker id, source
files, and ground-truth label.

**Done when:** three WAVs exist and you can listen to them and hear phone-line
degradation.

> **Note on the demo script:** these clips say whatever ASVspoof speakers say —
> not "transfer two crore." The trigger won't fire on them. See Task 2.6 for how
> this is handled; it's expected, not a bug.

---

# Day 1 — The spine

**End-of-day deliverable:** a CLI that replays a WAV at real speed and prints a
live stream of timestamped risk scores.

### 1.1 — `config.py` + `config.yaml` (45 min)
One frozen dataclass tree: `AudioConfig`, `ModelConfig`, `TriggerConfig`,
`DecisionConfig`, `ServerConfig`. Loaded from YAML with defaults. Fail loudly
with the offending key name on unknown fields.

**Done when:** `Config.load("config.yaml")` round-trips, and a typo'd key raises
a readable error.

### 1.2 — `types.py` (30 min)
The frozen dataclasses from SPEC §6. Add `to_json()` on each — the evidence log
and the WebSocket both need it, and doing it once here prevents two
serialisation formats drifting apart.

**Done when:** every type serialises and the round-trip is lossless.

### 1.3 — `audio/source.py`, `resample.py`, `framing.py` (2 h)
- `AudioSource` Protocol: `frames() -> Iterator[Frame]`, `close()`
- `FileSource(path, realtime=True)` — yields 20 ms frames, **sleeps to track
  wall clock** when `realtime=True`, runs flat out when `False` (tests need this)
- `MicSource` via `sounddevice`
- `RtpSource` — stub class, `NotImplementedError`, docstring explaining it's the
  production path
- Resample to 16 kHz mono float32
- `Framer` — 3.0 s windows, 0.5 s hop, carrying correct `t_start_ms`

**Done when:** a 10 s WAV yields 500 frames; `realtime=True` takes 10 s ±0.3 s;
`realtime=False` takes under a second; window timestamps are contiguous and
correct.

### 1.4 — `audio/vad.py` — closes Gap 3 (45 min)
Energy-based gate: RMS over the window vs a configured floor, plus a minimum
voiced-frame ratio. Returns `bool`. Keep it simple; this is a crash guard, not
a research problem.

**Done when:** `test_vad_silence.py` passes — a silence window returns `False`,
a speech window returns `True`.

### 1.5 — `models/base.py` + adapters + `registry.py` (2 h)
```python
class CountermeasureModel(Protocol):
    model_id: str
    def risk(self, pcm: np.ndarray, sr: int) -> float: ...   # [0,1] higher = fake

class SpeakerEncoder(Protocol):
    model_id: str
    def embed(self, pcm: np.ndarray, sr: int) -> np.ndarray: ...
    def risk(self, ref: np.ndarray, test: np.ndarray) -> float: ...  # [0,1] higher = impostor
```
- `probe_cm.py` — `ProbeBackbone.embed()` + the persisted logistic head
- `resemblyzer_spk.py` — **does the `1.0 - similarity` inversion here and
  nowhere else** (Gap 2)
- `registry.py` — the *only* file that touches `sys.path` for `detector/src`

**Done when:** `test_score_orientation.py` passes — two clips of the same
speaker give **low** risk; a spoof clip gives higher risk than its genuine pair.

### 1.6 — `enrolment/store.py` (1 h)
`enrol(speaker_id, pcm, sr)`, `get(speaker_id)`, `list()`. Persists
`artifacts/enrolments/<id>.npy` + a manifest with `created_utc`, `model_id`,
`duration_s`. **Never writes audio.**

**Done when:** `test_privacy.py` passes — after enrolling, no `.wav`/`.flac`/
`.mp3` exists anywhere under `artifacts/`.

### 1.7 — `cli.py` skeleton: `enrol` and `scores` (1 h)
- `sentinel enrol --speaker <id> --audio <wav>`
- `sentinel scores --audio <wav>` — replays and prints
  `t=12.5s  spk_risk=0.18  cm_risk=—  vad=speech`

**✅ Day 1 acceptance:** `sentinel scores --audio artifacts/demo/genuine.wav`
runs for the true duration of the clip and prints a plausible score stream, with
speaker risk visibly lower for the genuine clip than the attack clip.

---

# Day 2 — The brain

**End-of-day deliverable:** a console demo showing the system deaf until a
trigger fires, then producing a verdict.

### 2.1 — `decision/calibration.py` (1 h)
Load `calibration.json`. Map raw score → calibrated risk using the stored
threshold and per-class stats. Expose `calibration_id` (hash of the file) for
the evidence log.

**Done when:** `test_calibration.py` passes — monotonic, clamped to [0,1], and a
missing file raises a clear error rather than silently defaulting.

### 2.2 — `decision/fusion.py` (45 min)
`FusionStrategy` protocol. `MeanFusion` (matches the experiment today) and
`LogisticFusion` (reads weights from calibration; used after the Kaggle run).
Selected by config.

**Done when:** `MeanFusion` reproduces the experiment's fused score exactly on a
handful of stored score pairs.

### 2.3 — `decision/engine.py` — **the most important module** (2 h)
Pure `decide()` per SPEC §7.4. No I/O, no clock, no globals.

**Done when:** `test_decision_engine.py` covers every branch in the SPEC table
— not triggered, enrolled/not, below/between/above thresholds, SILENT, ERROR —
and `reasons` is non-empty in every case.

### 2.4 — `decision/gating.py` (1 h)
`TriggeredGating(pre_roll_s, hold_s)` and `AlwaysOnGating`. **Pre-roll needs a
rolling window buffer** — by the time the trigger fires, the audio you want to
score has already passed. Keep `pre_roll_s` of windows in memory and score
backwards.

**Done when:** a unit test proves that a trigger at t=10 s causes windows from
t=7 s onward to be scored.

### 2.5 — `asr/transcriber.py` (2 h)
faster-whisper `base.en`, int8, on its own thread per SPEC §7.2. Consumes a
bounded frame queue, emits `Utterance(text, t_start_ms, t_end_ms)`. Chunk on
silence using the VAD from 1.4.

**Done when:** replaying a 30 s speech WAV produces a readable transcript with
timestamps within ~±500 ms of the truth.

### 2.6 — `trigger/intents.py` + `engine.py` (2 h)
Two-stage per SPEC §8.

> **Demo-audio note:** ASVspoof clips don't contain financial instructions, so
> the trigger will never fire on them naturally. Handle this with a
> `config.yaml` option `trigger.scripted_overlay` — a list of
> `(t_ms, text)` utterances injected into the transcript stream for demo audio,
> **clearly labelled in the UI as a scripted overlay.** This is honest: we are
> demonstrating the trigger mechanism on audio that isn't a real fraud call.
> On day 4's teammate-cloned audio (which *will* say the transfer line), the
> overlay is switched off and the trigger fires for real.
> **Never ship the overlay silently. It must be visible on screen.**

**Done when:** `test_trigger.py` passes, including paraphrases with zero keyword
overlap (*"push the funds across tonight"* must fire; *"I'll transfer to the
other line"* must not).

### 2.7 — `evidence/log.py` (1 h)
Append-only JSONL, `prev_hash` chaining, `model_id` + `calibration_id` on every
verdict record.

**Done when:** a chain-verification function passes on a clean log and detects a
hand-edited record.

**✅ Day 2 acceptance:** `sentinel run --audio artifacts/demo/attack.wav --console`
prints: monitoring… → TRIGGER FIRED (with the matched intent) → CM scoring
engages → verdict, and writes a valid evidence log. **The core idea is now
demonstrable without any UI.**

---

# Day 3 — The screen

**End-of-day deliverable:** the demo, watchable.

### 3.1 — `pipeline/orchestrator.py` + `events.py` (2.5 h)
The sequential loop with wall-clock pacing. ASR thread. Event queue with drop
counter. `pipeline_lag_ms` computed and emitted.

**Done when:** `test_pipeline_golden.py` passes — fixed WAV, fixed seed,
`realtime=False`, snapshot of the event sequence is stable across runs.

### 3.2 — `server/app.py` (1.5 h)
FastAPI. `GET /` serves the UI. `WS /stream` drains the queue and pushes events.
`POST /start`, `POST /stop`, `GET /demos` (list from the demo manifest).

**Done when:** two browser tabs both receive the stream; stopping mid-run leaves
no orphan thread.

### 3.3 — `server/static/` — the UI (4 h)

**No CDN. No build step. Everything vendored.** Plain HTML + one JS file + one
CSS file. Canvas for the timeline.

Panels:
1. **Header** — demo name, *"Simulated live call — recorded audio streamed in
   real time"*, calibration provenance (dataset + EER), `pipeline_lag_ms`
2. **Transcript** — scrolling, with triggering utterance highlighted and any
   scripted-overlay lines visibly marked
3. **Risk timeline** — canvas; speaker risk and CM risk as two lines; gated
   region shaded; trigger marked with a vertical rule
4. **Verdict panel** — the three states, `UNCERTAIN` styled with equal weight
5. **Evidence panel** — suspicious segments with timestamps, both scores,
   model + calibration ids, recommended action
6. **Mode toggle** — Sentinel vs Naive, with the false-alarm counter

**Done when:** a full run is watchable start to finish and every panel updates
live.

**✅ Day 3 acceptance:** open the browser, pick the genuine demo → `VERIFIED`.
Pick the attack demo → trigger fires, `LIKELY IMPERSONATION`, evidence panel
populated. **This is the deliverable that goes on slide 3.**

---

# Day 4 — Make it survive contact

**End-of-day deliverable:** something you can present without fear.

### 4.1 — Naive-mode comparison (1.5 h)
Wire `AlwaysOnGating` to the toggle. In naive mode, count every window over the
threshold on a **genuine** call as a false alarm and display the running count.

**Done when:** running the genuine call in naive mode visibly accumulates false
alarms; in Sentinel mode the count stays at zero. *This is the money shot.*

### 4.2 — CHALLENGE layer (1.5 h)
On `UNCERTAIN`, surface a challenge panel: the prompt to inject, and the
recommended operator action (*"call back on the registered number"*). Scripted,
not interactive — and **labelled as scripted in the UI**.

**Done when:** the uncertain path reaches a visible, sensible recommendation.

### 4.3 — Offline hardening (1 h)
`test_offline.py` with network access blocked. Fix anything that reaches out.

**Done when:** the full demo runs with WiFi off. **Physically turn it off and
test. Do not simulate this.**

### 4.4 — Latency measurement (45 min)
`bench_latency.py` — measure end-of-trigger-phrase → verdict-on-screen across
10 runs. Record median and p95 in `artifacts/latency.json`.

**Done when:** you have a real number to quote. Whatever it is, quote *that*.

### 4.5 — Capture the artifacts (1 h)
- Screen recording of a successful end-to-end run
- Stills: trigger firing, verdict, evidence panel, naive-vs-sentinel counter
- Save to `artifacts/media/`

**Done when:** the stills are good enough to drop onto slide 3.

### 4.6 — Stretch only if 4.1–4.5 are done: teammate voice clone (2 h)
Record 30 s of a teammate, clone with open-source TTS, script both calls to
include the transfer instruction, run through `channel_sim`, add to the demo
manifest, switch the scripted overlay off.

**Hard rule: this never replaces the ASVspoof demo.** Both stay in the manifest.
If it fails, you lose nothing.

### 4.7 — `README.md` (30 min)
How to run the demo, in five lines, written for someone who has never seen the
repo — because at the finale, that person might be a teammate at 2am.

---

## Risk register

| Risk | Likelihood | Mitigation |
|---|---|---|
| `sentence-transformers` fights Python 3.9 | Medium | Use `transformers` + MiniLM directly (Task 0.1 note) |
| faster-whisper slower than expected | Low | Drop to `tiny.en`; or pre-transcribe and replay with simulated timing |
| Persisted probe doesn't reproduce 11.7% | Medium | **Caught on Day 0 by design.** Fix before building on it. |
| Resemblyzer crashes on edge-case windows | Medium | VAD gate (1.4) + `SILENT` status; never let it raise into the loop |
| Voice-cloning toolchain eats a day | High | It's Task 4.6, last, stretch-only, never on the critical path |
| UI eats more than 4 h | Medium | Day 2's console demo is already a real deliverable. Ship that. |
| Someone "improves" the architecture mid-build | Medium | SPEC §3 non-goals. Point at it. |

## Definition of done for the whole prototype

- [ ] Genuine demo call → `VERIFIED`, no false alarms
- [ ] Attack demo call → trigger fires → `LIKELY IMPERSONATION` with evidence
- [ ] Naive mode visibly accumulates false alarms on the genuine call
- [ ] Runs with WiFi physically off
- [ ] Evidence log validates its own hash chain
- [ ] All tests in SPEC §9 pass
- [ ] Measured latency recorded in `artifacts/latency.json`
- [ ] Screen recording + stills captured
- [ ] Every number on screen traceable to `calibration.json`
