# Sentinel — build handoff

**Status: Day 0, Day 1 and Day 2 of `IMPLEMENTATION-PLAN.md` are done and
committed. Day 3 (the screen) and Day 4 (survive contact) remain.**

Read `SPEC.md` and `IMPLEMENTATION-PLAN.md` first. This file is only the state
of play and the things a fresh session cannot infer from the code.

---

## How to run anything

```bash
cd /Users/pranav1296/SIH/prototype
P=../detector/venv/bin/python        # Python 3.9.6 — do NOT create a new venv

$P -m pytest tests/ -q                            # 135 tests, ~13s
$P -m sentinel.cli run --demo attack   --fast     # the demo, console
$P -m sentinel.cli run --demo genuine  --fast
$P -m sentinel.cli run --demo genuine  --fast --mode always_on   # naive comparison
$P -m sentinel.cli verify                         # evidence hash chain
```

Drop `--fast` to replay at true speed (~37s). Everything runs offline; models
are in the standard HF cache plus `artifacts/models/asr`.

## Where things are

| | |
|---|---|
| Repo | `/Users/pranav1296/SIH` — git initialised this session, commit per task |
| Interpreter | `../detector/venv/bin/python` (3.9.6) |
| Config | `config.yaml` — **every** tunable number, with the measurement that chose it |
| Artifacts | `artifacts/{probe_head.npz, calibration.json, demo/, enrolments/, evidence/}` |
| Reused core | `detector/src/` via `sentinel/models/registry.py` — the only `sys.path` touch |

## Current numbers (all reproducible)

```
calibration     EER 11.68% on 119 trials, threshold 0.4220   (0.000pp drift vs experiment)
abstention band [0.3636, 0.4575]  = eer_threshold -/+ 0.5 sigma per class

attack  call -> LIKELY_IMPERSONATION  risk 0.478   3 triggers   47/69 windows deep
genuine call -> VERIFIED              risk 0.363   0 false alarms
genuine call, naive mode ------------ risk 0.329   7 FALSE ALARMS   <- the money shot
```

---

## Day 3 — the screen (next)

Tasks 3.1–3.3 in `IMPLEMENTATION-PLAN.md`. **3.1 is already built**:
`pipeline/orchestrator.py` and `pipeline/events.py` exist and work. What remains
of 3.1 is only `tests/test_pipeline_golden.py`.

So Day 3 is really:

1. **`tests/test_pipeline_golden.py`** — fixed WAV, `realtime=False`, snapshot
   the event sequence. `FileSource(realtime=False)` is already deterministic and
   all event times are stream time, so this should be stable. Use `--no-asr`
   (whisper is the one non-deterministic stage) or snapshot only non-ASR events.
2. **`server/app.py`** — FastAPI. `GET /`, `WS /stream`, `POST /start`,
   `POST /stop`, `GET /demos`. Build models ONCE at startup via
   `cli.build_runtime(cfg)` and reuse across runs — reloading wav2vec2 between
   takes puts a 10s pause in the middle of a live demo. Run the orchestrator on
   a worker thread, push `on_event` payloads into `EventQueue`, drain in the WS
   handler.
3. **`server/static/`** — six panels per plan 3.3. No CDN, no build step.

### The event stream is already complete

`orchestrator.run(on_event=...)` emits everything the UI needs. Every payload has
a `type`:

| `type` | when | notable fields |
|---|---|---|
| `run_start` | once | `calibration` (full provenance header), `band`, `mode`, `ground_truth`, `scripted_overlay`, `honesty` |
| `utterance` | per transcript line | `text`, `t_start_ms`, `t_end_ms`, **`scripted`** |
| `trigger` | per trigger | `intent`, `stage`, `margin`, `description`, `scripted` |
| `risk_score` | per window per model | `kind` (`cm`/`speaker`), `value`, `status` (`OK`/`SILENT`/`ERROR`), `seq`, `voiced_ratio` |
| `verdict` | per window | `state`, `risk`, `confidence`, `reasons[]`, `segments[]`, `recommended_action`, `pipeline_lag_ms`, `alerts`, `false_alarms`, `mode` |
| `final` | once | verdict fields plus `stats` |

`gating.active_regions(triggers)` gives merged `[start_ms, end_ms]` spans for
shading the timeline. It is not currently emitted — add it to the `verdict`
payload if the UI wants it.

### UI honesty rules (SPEC §12 — non-negotiable)

- Header always shows calibration provenance (dataset + EER) next to the risk.
- Banner: **"Simulated live call — recorded audio streamed in real time."**
- `scripted: true` utterances **must** render with a visible marker.
- `UNCERTAIN` styled with the same visual weight as the other two, not greyed.
- Show `pipeline_lag_ms` when it exceeds real time.

---

## Day 4 — remaining

4.1 naive toggle (backend done — `mode=always_on`; needs the UI toggle and
counter) · 4.2 CHALLENGE panel on `UNCERTAIN` · 4.3 `test_offline.py` +
**physically turn WiFi off** · 4.4 `bench_latency.py` → `artifacts/latency.json`
· 4.5 screen recording + stills (**needs a human**) · 4.6 teammate voice clone
(**stretch, needs a human**) · 4.7 `README.md`.

---

## Things that will bite you

**1. The genuine call verdict is uncomfortably tight.** Risk 0.363 against
`low_thr` 0.3636 — it lands VERIFIED by 0.0006, with confidence 0.00. It is
correct and the thresholds are honestly derived, but a slightly different demo
clip would flip it to UNCERTAIN on stage. Options, in order of honesty: (a)
present it as-is and use it to explain the abstention band, (b) regenerate demo
calls with a different speaker via `scripts/make_demo_calls.py --speaker`, (c)
re-derive the band from a full Kaggle run. **Do not hand-tune `low_thr` and then
claim the calibration produced it** — `test_calibration.py` asserts config
matches `calibration.json` and will fail.

**2. Resemblyzer does not crash on silence — it lies.** Fed silence it returns a
well-formed unit-norm embedding scoring 0.31 risk, i.e. *below* `low_thr`:
untreated, the system reports VERIFIED while listening to nothing. No post-hoc
check can detect it. The guard is `audio.min_embed_rms` on input energy, behind
the VAD. Pinned by
`test_vad_silence.py::test_unguarded_resemblyzer_confidently_verifies_silence`.
Do not "simplify" it away.

**3. Trigger stage 2 scores a MARGIN, not a similarity.** Raw cosine similarity
does not separate the classes (paraphrases 0.44–0.65, innocent talk 0.25–0.61 —
they overlap). It scores `sim(nearest fraud intent) − sim(nearest benign
anchor)`. `BENIGN_ANCHORS` must include **generic conversational English**, not
just banking talk, or the trigger fires on ordinary transcript output. That bug
was live until the first end-to-end run.

**4. Known limits are recorded, not hidden.** `intents.py` has `KNOWN_MISSES`
(1 paraphrase stage 2 cannot catch) and `KNOWN_FALSE_POSITIVES` (1 of 12
held-out sentences). Both are asserted with their *current* behaviour — if a
change fixes one, the test tells you to promote it. Held-out false-positive
rate is 1/12; quote that number, not "zero".

**5. The demo calls are concatenated with repeats.** ASVspoof clips are 1–8s, so
a ~37s call cycles the speaker's pool 3–4 times. Every segment and repeat is in
`artifacts/demo/manifest.json`. If asked where 37 seconds came from, show it.

**6. The speaker signal barely separates on this data** (genuine 0.139 vs attack
0.161). Expected: ASVspoof spoofs are voice-converted *to the target speaker*.
The countermeasure does the work (0.514 vs 0.800). Say so rather than implying
enrolment is carrying the result.

**7. The scripted overlay applies to BOTH demo calls, deliberately.** If the
trigger only fired on the attack call the demo would be rigged. Both trigger;
what differs is what verification finds. Keep it that way.
