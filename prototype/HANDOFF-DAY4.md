# Sentinel — handoff for the Day 4 session

**Day 3 is done and committed. Day 4 is 4.1–4.7, and part of it needs Pranav
rather than you.**

Read `SPEC.md` and `IMPLEMENTATION-PLAN.md` first. `HANDOFF.md` is the Day 3
handoff — still accurate except for items 1 and 2, which this file supersedes.
Invoke the `executing-plans` skill before you start; that is the process this
build has followed since Day 0.

---

## How to run anything

```bash
cd /Users/pranav1296/SIH/prototype
P=../detector/venv/bin/python        # Python 3.9.6 — do NOT create a new venv

$P -m pytest tests/ -q                              # 157 tests, ~51s
$P -m sentinel.cli serve                            # the UI, http://127.0.0.1:8000
$P -m sentinel.cli run --demo attack  --fast        # console
$P -m sentinel.cli run --demo genuine --fast --mode always_on   # the money shot
$P -m sentinel.cli verify                           # evidence hash chain
```

Drop `--fast` for true speed (~37 s). Everything runs offline.

---

## Current numbers — these changed on Day 3, use these

```
calibration     EER 11.68% on 119 trials, threshold 0.4220   (unchanged)
abstention band [0.3636, 0.4575]                             (unchanged)

attack  call            -> LIKELY_IMPERSONATION  risk 0.478  conf 0.04  47 deep
genuine call            -> VERIFIED              risk 0.317  conf 0.13  30 deep
genuine call, naive     -> VERIFIED              risk 0.329  7 FALSE ALARMS
```

**The genuine call is no longer on a knife edge.** HANDOFF.md item 1 warned it
landed VERIFIED by 0.0006. It now clears `low_thr` by 0.0466. That was a bug
fix, not a tuning change — see below — and `test_calibration.py` still asserts
config matches `calibration.json`.

---

## What Day 3 delivered

| | |
|---|---|
| `tests/test_pipeline_golden.py` + `tests/golden/pipeline_attack.json` | replay determinism + a committed snapshot |
| `sentinel/server/app.py` | FastAPI, WebSocket, run lifecycle |
| `sentinel/server/static/` | the six panels |
| `sentinel/cli.py` | gained `serve` |

Verified in a real headless browser, console clean:
attack → LIKELY IMPERSONATION with 30 evidence segments · genuine → VERIFIED,
0 false alarms · genuine in naive mode → 7 false alarms.

### The bug Day 3 found

Putting the evidence panel on screen showed the **genuine** call, verdict
VERIFIED, listing seven windows at 0.99 artifact risk with no voice-match score
beside them.

`_score_window` checked the VAD before scoring. `_backfill` — the pre-roll —
called `_run_deep` directly and did not. Fed a window with no speech, the probe
does not crash and does not abstain: nine silent windows of the genuine call
were scored, eight above 0.86, one at 0.17. Same lesson as HANDOFF item 2 with
the models swapped — **a model handed no speech still returns a confident
number, and the number is about nothing.** The 0.17 is the important one: no
threshold rescues a score computed on silence, so the gate has to come first.

The VAD gate now lives inside `Orchestrator._run_deep`, which is the only place
the countermeasure is called from. Refused windows get a `SILENT` score —
recorded and shown, not omitted — and stay out of the aggregate. Pinned by
`test_pipeline_golden.py::test_the_pre_roll_never_scores_a_window_the_vad_refused`
and `test_vad_silence.py::test_unguarded_countermeasure_confidently_flags_silence`.

**Do not "simplify" the gate back to the caller.** Two callers, one gate.

---

## Your work — Day 4

4.1 and 4.2 are the only ones that touch the UI. 4.5 and 4.6 need a human.

### 4.1 — Naive-mode comparison — **mostly already done**
Backend, UI toggle and false-alarm counter all work and are verified in a
browser: 0 in Sentinel mode, 7 in Naive mode on the genuine call. The counter
switches to counting *alerts* on the attack call and says so, because calling a
true positive a "false alarm" would be the sleight of hand this project argues
against.

**What remains:** a test. There is no automated assertion that naive mode
accumulates false alarms on the genuine call and Sentinel mode does not — the
demo's single most important claim is currently checked only by eye. Add it to
`tests/test_pipeline_golden.py`; the `_replay()` helper there already takes a
`mode` argument.

### 4.2 — CHALLENGE panel on UNCERTAIN — **not started**
`decision/engine.py` already produces the recommended action ("Do not action
this instruction on the strength of the voice. Call back on the registered
number…") and the UI already renders it in the verdict panel. What is missing
is the challenge *prompt* — the thing to say to the caller — surfaced as its own
panel when `state == UNCERTAIN`, and **labelled as scripted**.

Note neither demo call currently lands on UNCERTAIN, so you will need a way to
exercise it. Options, cheapest first: a `?state=UNCERTAIN` preview flag in the
UI; or run with `--speaker` set to an unenrolled id, which takes the
`not enrolled -> UNCERTAIN` branch honestly.

### 4.3 — `tests/test_offline.py` — **not started**
Block sockets, run the pipeline, fix anything that reaches out. Then
**Pranav physically turns the WiFi off and runs it.** Do not simulate that half
and do not claim it passed until they have.

### 4.4 — `scripts/bench_latency.py` — **not started**
End-of-trigger-phrase → verdict-on-screen, 10 runs, median and p95 into
`artifacts/latency.json`. The trigger fires at a known stream time (16 000 ms /
21 000 ms / 26 000 ms from `config.yaml`'s `scripted_overlay`), so this is
measurable without instrumenting the UI. Report whatever number you get.

### 4.5 — screen recording + stills — **needs Pranav**
### 4.6 — teammate voice clone — **needs Pranav, stretch, never replaces ASVspoof**

### 4.7 — `README.md` — **not started**
Five lines, for a teammate who has never seen the repo, at 2am.

---

## Conventions (unchanged)

- Interpreter `../detector/venv/bin/python`. Do NOT create a new venv.
- Every tunable number in `config.yaml`, with the measurement that chose it.
- Test in the same commit as the code. Commit per task, saying what now works.
- Run every acceptance criterion. Don't assume.
- SPEC §12 honesty rules are non-negotiable.

## Things that will bite you

1. **`tests/golden/pipeline_attack.json` is a committed snapshot.** If you
   change framing, VAD, gating, fusion or the decision engine it will fail and
   name the event. That is the alarm working. Regenerate deliberately with
   `SENTINEL_UPDATE_GOLDEN=1 ... pytest tests/test_pipeline_golden.py -q` and
   **read the diff** before committing it.
2. **The golden test runs with ASR off.** faster-whisper is the one
   non-deterministic stage. Keep it that way.
3. **`tests/test_server.py` stubs the orchestrator** so it runs in 5 s. It tests
   the server, not wav2vec2. Don't "improve" it into an integration test.
4. **Models load once, at startup** (13.2 s). Anything that reloads them per run
   puts that pause in the middle of a live demo.
5. **The UI never recomputes a number.** Every value on screen arrives in an
   event. If the UI derived risks of its own, the screen and the evidence log
   could disagree, and the log is what we claim is authoritative.
6. **Held-out trigger false-positive rate is 1/12.** Quote that, not "zero".
   `intents.py` has `KNOWN_MISSES` and `KNOWN_FALSE_POSITIVES`.
7. **The scripted overlay runs on BOTH demo calls, deliberately.** If it only
   fired on the attack call the demo would be rigged. Both trigger; what differs
   is what verification finds.
8. **The speaker signal barely separates on this data** (genuine 0.14 vs attack
   0.16) — ASVspoof spoofs are voice-converted *to the target speaker*. The
   countermeasure does the work (0.52 vs 0.80). Say so rather than implying
   enrolment is carrying the result.
