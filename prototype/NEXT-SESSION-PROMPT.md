# Continue the Sentinel live-demo sprint

Paste this whole file as your first message in the new session.

## Where you are

Repo: `/Users/pranav1296/SIH`, work in `/Users/pranav1296/SIH/prototype`.
Read, in this order: `PLAN-LIVE.md` (the sprint design + task list), `HANDOFF-LIVE.md`
(the live runbook + what is measured), `SPEC.md` (the system contract, especially
§12 honesty rules), `HANDOFF-DAY4.md` (the recorded-call build).

Interpreter: `../detector/venv/bin/python` (Python 3.9.6). **Do not create a new
venv and do not `pip install` anywhere else.** The venv was rebuilt from scratch
last session and all four models are cached (`facebook/wav2vec2-base`, MiniLM,
Resemblyzer, faster-whisper base.en) — it runs with the WiFi off.

    cd /Users/pranav1296/SIH/prototype
    ../detector/venv/bin/python -m pytest tests/ -q        # 252 passed, ~2 min
    ../detector/venv/bin/python -m sentinel.cli serve      # UI at 127.0.0.1:8000

## What was built last session (all committed nowhere yet — see below)

The sprint added the live path on top of the recorded-call demo, per PLAN-LIVE:

1. **Live microphone in**: `sentinel/audio/live_source.py` (bounded queue,
   drop-oldest + counter, stream time from received samples, drops the partial
   tail to match `FileSource` exactly), `WS /live/audio`,
   `static/pcm-worklet.js`, `static/live.js` (AudioWorklet capture, recording
   for enrolment, level meter, silence watchdog, teardown race fixed).
   `tests/test_live_pipeline.py` proves a live stream produces **byte-identical
   events** to the same audio through the file path. That test is the contract:
   if it fails, the live path has diverged — fix the code, not the test.
2. **Live voice enrolment + open-set lookup**: `sentinel/enrolment/gallery.py`
   (threshold + runner-up margin + two-window debounce), `GET/POST/DELETE /voices`,
   `voice_lookup` events, UI voices panel + lookup chip.
   Threshold was **measured** (`scripts/calibrate_lookup.py`) on the pilot slice:
   `accept_similarity: 0.8998` (impostor p99). Same/different-speaker
   distributions **overlap** on this data (mobile-degraded genuine 0.8777–0.8995
   vs impostor tail p99 0.8998 / max 0.9183) — config.yaml carries the full
   table and `tests/test_lookup_calibration.py` fails if config and
   `artifacts/lookup_calibration.json` disagree.
3. **Trigger reasoning**: `TriggerEngine.assess()` returns an
   `IntentAssessment` for **every** utterance (fired or not); the transcript
   shows a margin chip, the trigger detail names the top families and the
   nearest benign line, and `POST /assess` powers a typed "try a line" box that
   shares the same code. Presenter prompt cards in the rail.
4. **Trigger corpus measured** (`scripts/eval_trigger.py --candidates`): 7
   indirect positives promoted into `intents.py` (now 36 canonical, all fire),
   8 topical traps added to `tests/test_trigger.py::TRAPS` and quiet, 5
   `KNOWN_MISSES` documented, the one pre-existing held-out false positive
   unchanged. Benign anchors grew a protective-advice section and two
   reminiscing lines — that is what made the traps quiet; do not remove them
   without re-running the eval script.
5. Suite: **252 passed**, golden snapshot regenerated deliberately (diff was
   only the two new stats keys `voice_lookups`, `audio_dropped_ms`; trigger
   margins were unchanged by the anchor work).

## What is left, in priority order

1. **Browser end-to-end is NOT yet done.** The UI code (`app.js`, `live.js`,
   `index.html`, `style.css`) has only been syntax-checked and its element ids
   cross-checked; no one has clicked the buttons. Serve, open the UI in Chrome,
   and exercise: source switch → recorded call → verdict; voices → record →
   save → list → delete; live mic → start → talk → stop (real mic available on
   this Mac); try-a-line and prompt cards; theme toggle; console clean.
   The pytest suite covers the WS protocol, not `getUserMedia`.
   Chrome flags that make this testable headlessly (16-bit PCM WAV only):
   `--use-fake-ui-for-media-stream --use-fake-device-for-media-stream
   --use-file-for-fake-audio-capture=/abs/speech.wav%noloop`.
2. **Clone assets + report** (`scripts/make_clone_assets.py --say`, then
   `scripts/make_clone_report.py`). Decide from `artifacts/clone_report.json`
   what the clone demo plays; put anything that evades the pilot CM on the
   limitations slide with its measured number. A real clone of a *person*
   (PLAN-LIVE §2 Tier A/B) needs a volunteer's consenting recording — ask the
   user for it; do not fake it with `say` and call it a clone.
3. **Fill in the numbers** in `HANDOFF-LIVE.md` (the "Measured, provisional"
   table and the checklist at the bottom) and mark L1–L8 status in
   `PLAN-LIVE.md`.
4. **Commit.** Repo convention: one commit per task, tests in the same commit,
   message says what now works. Suggested split: (a) live audio path + tests,
   (b) voices/lookup + calibration + tests, (c) trigger assessment + corpus +
   tests, (d) UI, (e) docs. `EXPERIMENT-REPORT.md` at the repo root is the
   user's own untracked file — leave it out of your commits.
5. Optional: live latency number (`pipeline_lag_ms` is on screen; the existing
   `scripts/bench_latency.py` covers the recorded path), screen recording.

## Gotchas discovered last session (do not rediscover)

- **setuptools must be <81** in the venv or `resemblyzer` fails to import
  (`webrtcvad` imports `pkg_resources`, removed in 81+). Already pinned.
- `Runner.start_live()` calls `stop()` first; any orchestrator stub **must
  reset its own stop flag at the top of `run()`** — the real one does.
- `test_server.py` and `test_live_endpoint.py` stubs mirror the orchestrator
  signature `run(..., live=False, gallery=None)`. Keep them in sync.
- `LiveSource` drops the oldest audio when the queue overflows *except* for the
  close sentinel (a bug fixed last session), and it deliberately drops the
  sub-frame tail so a live replay is event-identical to a file replay.
- `tests/test_privacy.py` now also asserts the live source is memory-only.
- The honesty banner follows the source; live mode **always** disables the
  scripted overlay (config cannot re-enable it) and never calls itself a call.

## Constraints that still apply

No new runtime dependency, no build step, no CDN, no Docker, no telephony;
everything runs offline; every tunable number in `config.yaml` with the
measurement that chose it; the UI never recomputes a server number; SPEC §12
honesty rules are non-negotiable.
