# Sentinel — the live demo plan (Sprint L)

**Why this exists.** Coordinator feedback on the Day 5 build: the demo reads as
"watching a transcript being transcribed". They want to *talk to the system* and
watch it react in real time — a real person speaking into a live microphone, the
system flagging as they speak, malicious intent arriving indirectly rather than
as a keyword, and a live voice enrolment/lookup flow. The recorded-call demo
stays; this sprint adds the live path beside it.

Companion docs: `SPEC.md` (the system), `IMPLEMENTATION-PLAN.md` (how days 0–4
were built), `HANDOFF-DAY4.md` (where the build stands). This file is the
ordered task list for Sprint L, in the same style: every task has an acceptance
criterion, and every tunable number lives in `config.yaml` with the measurement
that chose it.

**Interpreter:** `../detector/venv/bin/python` (Python 3.9.6 — SPEC §4).
**Hard limits that still apply:** no build step, no CDN, no Docker, no telephony,
no new runtime dependency, runs with the WiFi off.

---

## 1. The story the demo must tell, in 3 minutes

| # | On stage | What the audience sees |
|---|---|---|
| 1 | `voices → record 10 s`, name it "Coordinator" | A fingerprint is stored; the UI says no audio is kept. |
| 2 | Source: **live microphone** → talk normally | Live captions appear; the intent margin sits low; the system stays quiet. The timeline shows the voice check running on every window and the artifact check *not* running. |
| 3 | Slip in an indirect instruction — *"if anyone from the branch rings, you were in a meeting"* (measured +0.53, semantic only). The research pass's original candidate, *"just move it over to the new details before close of business"*, was measured as a **miss** (−0.05) and now lives in `KNOWN_MISSES` | The margin climbs on screen, crosses the line, and the **trigger fires** on a sentence with no fraud keyword. Deep verification opens; a verdict lands with evidence. |
| 4 | Hand the mic to a second person and repeat the line | Voice lookup: **unknown voice** (best match shown below the accept threshold). The verdict does not blindly accept the words. |
| 5 | Play the **clone** of the enrolled speaker into the call | Same voice to the ear, `LIKELY_IMPERSONATION` to the system. |
| 6 | A judge types anything into **try a line** | The trigger's reasoning is on screen, live: nearest intent family, nearest benign anchor, margin. |

Step 5 is the voice-cloning money shot and needs a synthetic asset; §2 deals with
that honestly. Steps 1–4 and 6 need no synthetic voice at all.

---

## 2. The clone problem — what a live human cannot demonstrate

A real person speaking live is a **genuine** voice. The correct output for step 2
is `VERIFIED`, and that is the point of the system (it does not accuse real
people). Cloning detection therefore needs a synthetic voice, and there are
exactly three honest ways to get one:

**Tier A — pre-generated clone of a teammate (build now, safe path).**
Record 30–60 s of a consenting teammate. Generate a cloned WAV offline with an
open-source zero-shot cloner. Ship it in `artifacts/demo/` with a manifest entry
that records: source speaker, consent, generator + version, and
`ground_truth: spoof`. Generated once, played as a file forever after. No live
toolchain, no stage risk.

**Tier B — clone the coordinator/teacher from audio they send ahead (best
story).** Same as Tier A, but the reference is the person the judges will watch.
The demo becomes: *they* speak live → verified; a clone of *their own voice*
plays → flagged. Needs their 1–2 minutes of clean audio and written consent
before the event. Generation happens offline, days before — not on stage.

**Tier C — generate the clone at the venue (dramatic, optional, never the
critical path).** A script that clones from a recording made minutes earlier
while other things happen. If the tooling misbehaves, Tier A is still on disk and
the demo loses nothing. This is Task L8, last, only if L1–L7 have landed.

### The measurement gate that makes step 5 honest

The countermeasure was fitted on ASVspoof2019-LA — 2019-era TTS/VC. A modern
neural-codec clone is exactly the "new tool" from Truth 1 in
`PROJECT-EXPLAINED.md`, and detectors are known to degrade on attacks they were
not trained against. **We do not know yet whether our CM catches an XTTS-class
clone, so we will measure it before anyone claims it.**

`scripts/make_clone_report.py` runs every clone asset and every genuine
recording through the real pipeline (same framing, VAD, probe head,
calibration) and writes `artifacts/clone_report.json`: per-file
`cm_risk`, `speaker_risk`, `fused`, and which side of the band it falls. The
demo plays the assets the report says are caught. Assets that evade the pilot CM
are listed on the limitations slide with their measured scores — that is the
"we don't trust a number until we've tried to break it" line this project
already makes about other people's detectors, turned on ourselves.

If the modern clone evades the pilot CM, the fallback for step 5 is the existing
ASVspoof spoof (`attack.wav`), which is in-distribution and already produces
`LIKELY_IMPERSONATION` with 30 evidence segments. The live-human steps are
unaffected either way.

### What we deliberately do not build

Real-time cloning on stage, and a "detect any new TTS" claim. Both are research
projects; claiming them is the failure mode Truth 1 describes. We demo a
measured attack and say exactly which one it is.

---

## 3. Features

### F1 — Live microphone
The browser captures the mic (AudioWorklet), streams 20 ms PCM frames over a
WebSocket, and the server feeds them to the **same** `Orchestrator` that the
recorded calls use. Every downstream panel — transcript, risk timeline, gated
regions, verdict, evidence, challenge, latency chip — works unchanged, because
nothing downstream knows the source changed. That is what the `AudioSource`
protocol bought in SPEC §2.

Acceptance:
- Talk into the mic; captions appear within ~2 s of each sentence ending.
- Saying a high-risk line fires the trigger and produces a verdict, live.
- `pipeline_lag_ms` stays under the warn threshold on an M-series laptop.
- Stabbing Stop ends the run cleanly and reaches a `final` event.
- No audio file exists anywhere in `artifacts/` after a live run.

### F2 — Live voice enrolment + lookup
Enrol from the browser (`record 10 s → POST /voices`), stored as a 256-dim
fingerprint through the existing `EnrolmentStore`. During any run, every scored
window is compared against the whole gallery and the UI shows who is speaking,
how similar, and whether it clears the accept threshold — or "unknown voice".

Acceptance:
- Enrolling live then speaking gives "matches <name>"; a different person gives
  "unknown voice" with the best score shown below the threshold.
- The privacy rule holds: `.npy` + `.json` only, `test_privacy.py` still passes.
- The lookup states its calibration provenance next to the number, like the
  verdict does.

### F3 — Trigger reasoning and the try-a-line box
The trigger already computes a margin (`sim(fraud intent) − sim(benign anchor)`)
on every utterance and throws it away when it does not fire. Keep it instead:
every transcript line shows its margin, the trigger event carries the top intent
families and the nearest benign anchor, and a `POST /assess` box lets anyone type
a sentence and watch the same engine score it. Text-in is labelled as text-in —
it is not an audio claim.

Acceptance:
- A transcript line that nearly fired is visibly "considered, not confirmed".
- The typed box returns the same numbers the audio path produces for the same
  sentence (same engine, no second implementation).
- Indirect phrasings in §4 fire; the benign traps in §4 stay quiet.

### F4 — Prompt cards
A rail panel of suggested lines for the presenter: innocuous lines, then
indirect high-risk lines, grouped by intent family. Labelled **suggested lines —
the system decides for real**; nothing is injected into the transcript, no
`scripted` flag is used, and the overlay stays off in live mode.

Acceptance: a person who has never used the system can run steps 2–4 from the
card alone.

### F5 — Honesty for the live path (SPEC §12 additions)
- Live banner: **"Live microphone on this machine — audio is analysed in
  memory and never written to disk."** Never "phone call".
- If the browser sends silence for the first ~700 ms, say "no audio — check the
  microphone permission" rather than showing a quiet, working-looking screen.
- The voice lookup is a similarity against a threshold, not a probability of
  identity. Show the threshold and the calibration that chose it.
- If the pipeline drops live audio to keep up, count it and show it. Do not
  silently compress time.
- The clone asset is labelled with what generated it, on screen.

---

## 4. Trigger corpus — measured expansion

The existing engine (`trigger/engine.py`) is unchanged in mechanism. The
expansion is data, and it is promoted by measurement, not by taste:

1. Add the candidate indirect sentences and benign traps to
   `scripts/eval_trigger.py` (new) as a held-out stress set.
2. Run it. Print: positives fired, negatives quiet, which stage fired each,
   held-out false-positive rate.
3. Promote only the sentences that pass into `intents.py`. Anything that
   misfires or misses goes into `KNOWN_MISSES` / `KNOWN_FALSE_POSITIVES` with
   its measured margin, and `test_trigger.py` asserts the current behaviour so a
   later model change is caught.
4. Re-run `test_trigger.py` and the full suite.

Candidate indirect positives (from the research pass; all tested before use):
- *"just move it over to the new details before close of business"* (the
  existing KNOWN_MISS — promote only if it now fires)
- *"read me back whatever just came through on your handset"*
- *"I only need the three numbers off the back"*
- *"put it through on your own authority, I'll sign off when I'm back"*
- *"let's not wake the second pair of eyes on this one"*
- *"if anyone from the branch rings, you were in a meeting"*
- *"I'd rather this didn't travel beyond the two of us"*
- *"there's a message on your phone — stay on the line and read it out to me"*
- *"the window closes today — I'd move now if I were you"*

Benign traps that must stay quiet (each is the topical twin of a positive above):
- *"the account will be empty by the time the overnight sweep runs"*
- *"never share that code with anyone, not even if they say they're from the bank"*
- *"if you need anything else, please call us back on the number on the website"*
- *"for your security that needs both approvers — I can't action it on my own"*
- *"I'm putting you through to the fraud team — they'll verify a couple of
  details with you"*

The whole point of stage 2 is that it catches the positives **and** refuses the
traps. A positive promoted without its trap measured next to it is not evidence.

---

## 5. Architecture — what changes

```
  BROWSER                          SERVER (unchanged pipeline)
  mic ─► AudioWorklet ─► WS /live/audio ─► LiveSource ─► Orchestrator
                                                │            │
  /stream ◄──────────── events ─────────────────┘            │
                                                             ▼
  POST /voices ──► EnrolmentStore (fingerprints only) ──► Gallery ──► voice_lookup events
  POST /assess ──► TriggerEngine.assess(text) ──► assessment (no audio, labelled)
```

New files:

| File | What it is |
|---|---|
| `sentinel/audio/live_source.py` | `LiveSource` — an `AudioSource` fed by the server's WebSocket handler. Bounded queue, drop-oldest with a counter, stream time from received samples. |
| `sentinel/enrolment/gallery.py` | `Gallery.load(store, cfg)` + `LookupTracker` — open-set identification over the enrolments, with z-normalisation, a margin gate and debounce. |
| `sentinel/server/static/live.js` | Mic capture: AudioWorklet setup, 20 ms chunking, WS send, record-for-enrolment, level meter. |
| `sentinel/server/static/pcm-worklet.js` | The worklet processor. Zero-gain sink — a `numberOfOutputs: 0` node is never pulled and silently produces nothing. |
| `scripts/make_clone_assets.py` | Build-time only. Records are supplied; it generates the cloned WAV(s) offline with the chosen local tool and writes provenance into the demo manifest. Never runs during the demo, never imported by `sentinel/`. |
| `scripts/make_clone_report.py` | Runs every clone asset through the real pipeline and writes `artifacts/clone_report.json`. The gate for §2. |
| `scripts/eval_trigger.py` | Prints the trigger's behaviour over the full candidate corpus. The gate for §4. |

Changed files:

| File | Change |
|---|---|
| `sentinel/types.py` | `VoiceMatch`/`voice_lookup` event; `IntentAssessment` serialisation. |
| `sentinel/audio/source.py` | Nothing — `MicSource` already exists; `LiveSource` is a sibling, not a replacement. |
| `sentinel/pipeline/orchestrator.py` | Per-run `gallery`, one embedding per window reused by reference-risk and lookup; attach the assessment to the utterance event; `live=True` skips the scripted overlay. |
| `sentinel/trigger/engine.py` | `assess()` returning a frozen `Assessment`; `evaluate()` delegates to it, so there is still one implementation. |
| `sentinel/asr/transcriber.py` | The three utterance-boundary numbers move to `config.yaml` (`asr.*`) so a live cut can be shortened without editing a module. |
| `sentinel/server/app.py` | `WS /live/audio`; `Runner.start_live()`; `GET/POST/DELETE /voices`; `POST /assess`; live config in `/hello`. |
| `sentinel/cli.py` | `run --mic` (the headless live path, `sounddevice`), `enrol --mic`. Both fallbacks, not the demo path. |
| `sentinel/server/static/*` | Source switch, live controls, level meter, voices panel, try-a-line box, margin chips, live banner. |
| `config.yaml` | `live:`, `lookup:`, `asr:` sections, all seeded from measurements below. |

Not changed: `decision/`, `evidence/`, fusion, gating, the calibration band. The
verdict logic is not touched by this sprint. The lookup is a separate visible
signal, deliberately **not** fused into the risk — fusing an unvalidated score
into the verdict would be a statistical claim we have not measured.

### Concurrency, kept boring

The browser sends ~50 messages/second. The WS handler never touches a model: it
packs bytes onto `LiveSource`'s queue and returns. The one pipeline thread
consumes. That is the same shape as today, with the file reader swapped for a
socket. The ASR input queue keeps its block-don't-drop policy; the live input
queue drops oldest when full and counts it, because in live audio the present
matters more than the past, and a growing lag is worse than a gap.

### Live capture specifics that are easy to get wrong

- `new AudioContext({sampleRate: 16000})` is reliable on Chrome 74+/Firefox
  61+/Safari 14.1+; if the browser hands back a different rate, the client sends
  that rate and the server resamples with the existing `audio.resample`.
- The worklet emits exactly-sized chunks with sample counting in the audio
  thread — never `setTimeout`, which background tabs throttle.
- One WS binary message per 20 ms chunk, Float32 mono. On loopback the payload
  size is irrelevant; correctness is not.
- Chrome's `--use-fake-device-for-media-stream` +
  `--use-file-for-fake-audio-capture=<wav>` (16-bit PCM only; 24-bit parses as
  silence) makes the whole path testable headlessly, which is how the
  end-to-end test will run in CI.

---

## 6. Measurements to take before the demo

| # | What | Where it lands |
|---|---|---|
| M1 | Same-speaker vs different-speaker similarity distributions on the pilot data, for the accept threshold and margin | `artifacts/lookup_calibration.json`; `config.yaml: lookup.*` with the numbers in comments |
| M2 | End-of-speech → verdict-on-screen, 10 live runs | `artifacts/latency.json` (extended with the live path) |
| M3 | Trigger corpus: positives fired / negatives quiet, curated + held out | `scripts/eval_trigger.py` output, quoted in the docs |
| M4 | Clone assets: per-file CM/speaker/fused risk | `artifacts/clone_report.json`; decides what step 5 plays |

Every one of these prints what it measured. Nothing in the UI shows a number
that is not in one of these files or `calibration.json`.

---

## 7. Tasks, in order

### Where the tasks stand (2026-09-23)

| # | Task | State |
|---|---|---|
| L1 | Restore the runtime | **done** — venv rebuilt from scratch, four models cached, suite green with the WiFi off |
| L2 | `LiveSource` + `/live/audio` + lifecycle | **done** — `test_live_source.py`, `test_live_endpoint.py`, and `test_live_pipeline.py`: a live stream produces byte-identical events to the same audio through the file path |
| L3 | Browser capture + live UI | **done, headless** — `scripts/browser_e2e.py` drives a real Chromium with a fake microphone through the whole demo path (39 checks, screenshots included). The one thing left is a human speaking into the demo laptop's own microphone |
| L4 | Voices: enrolment + lookup | **done** — browser enrolment, fingerprint-only storage, open-set lookup with threshold + margin + two-window debounce |
| L5 | Lookup calibration (M1) | **done** — `artifacts/lookup_calibration.json`, and `test_lookup_calibration.py` fails if config and report disagree |
| L6 | Trigger assessment + try-a-line + corpus (M3) | **done** — `assess()` on every utterance, `POST /assess`, corpus promoted by `scripts/eval_trigger.py`; the cards' group labels are checked by the browser E2E |
| L7 | Prompt cards + clone report (M4) + docs | **done** — cards, `artifacts/clone_report.json`, runbook in `HANDOFF-LIVE.md`. A real clone of a *person* still needs a consenting volunteer's recording (Tier A/B); do not fake one with `say` |
| L8 | Optional: venue-day clone (Tier C) | **not built** — optional and off the critical path |

### L1 — Restore the runtime (blocking)
Rebuild `detector/venv` (it was deleted; it is gitignored), prefetch
`facebook/wav2vec2-base`, `all-MiniLM-L6-v2`, Resemblyzer and faster-whisper.
Run the existing 157 tests to a green baseline before touching anything.

**Done when:** `pytest tests/ -q` is green and `sentinel serve` renders the
existing UI. *No sprint work starts on an unverified baseline.*

### L2 — `LiveSource` + `/live/audio` + server lifecycle
`LiveSource` with its unit tests (framing, resampling, drop-oldest accounting,
stop). Server endpoint; `Runner.start_live`; stop path; stats fields
(`live_seconds`, `audio_dropped_ms`, `no_audio_warned`). A pytest client that
streams `genuine.wav` over the socket and reads the resulting events off
`/stream`.

**Done when:** the test drives a WAV through the live socket and gets a
transcript, a trigger and a verdict; `/stop` ends it cleanly; no orphan thread.

### L3 — Browser capture + live UI
`pcm-worklet.js`, `live.js`, source switch, live run controls, level meter,
live banner, clock counts up instead of down.

**Done when:** headless Chrome with fake audio capture runs a live call
end-to-end and the screenshots show captions, a trigger and a verdict. Manual
mic test by a human, on the actual demo laptop.

### L4 — Voices: live enrolment + lookup
Storage endpoints; `Gallery` + `LookupTracker`; orchestrator wiring; lookup
events; voices panel; the header shows who is speaking.

**Done when:** enrol live → speak → matched name; second speaker → unknown;
privacy test still green.

### L5 — Lookup calibration (M1)
`scripts/calibrate_lookup.py` over the pilot data; numbers into `config.yaml`
and `artifacts/lookup_calibration.json` with provenance.

**Done when:** the threshold on screen is the one the script measured, and the
provenance line names the dataset, the trial counts and the caveat.

### L6 — Trigger assessment + try-a-line + corpus (M3, §4)
`assess()`; utterance chips; the box; the corpus evaluation and promotion.

**Done when:** the box and the audio path agree on the same sentence, and the
promoted corpus passes `test_trigger.py` with the traps quiet.

### L7 — Live prompt cards + clone report (M4) + docs
Prompt cards; `make_clone_report.py`; README/HANDOFF update; demo runbook with
the exact click path.

**Done when:** someone who has not seen the repo can run the demo from the card;
the clone report exists and the demo assets are chosen from it.

### L8 — Optional: venue-day clone (Tier C) — only if L1–L7 are done
A script that takes a fresh recording and produces a clone offline, for the
"clone them while you talk" moment.

**Done when:** it works twice in a row on the demo laptop. If it does not, it is
not on the critical path and nothing else changes.

---

## 8. Testing

New tests follow SPEC §9's rule — test what will break, not coverage theatre:

| Test | Protects |
|---|---|
| `test_live_source.py` | framing, resampling, drop accounting, clean stop, no fabricated frames |
| `test_live_endpoint.py` | the real server + the real pipeline over the live socket (models stubbed where the golden test already stubs them) |
| `test_voice_lookup.py` | same speaker accepted, different speaker rejected, margin gate, debounce, silent windows produce no match |
| `test_trigger_assessment.py` | `assess()` and the typed box agree; promoted indirect positives fire; traps stay quiet; KNOWN_MISSES still named |
| `test_live_privacy.py` | after a live run, no audio-bearing file exists anywhere under `artifacts/` |

The existing suite stays green. The golden snapshot is **unaffected** by the new
utterance field: `_digest_event` only reads the keys it names. If that changes,
regenerate deliberately and read the diff.

---

## 9. Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Modern clone evades the pilot CM | Medium–high | M4 gate; fall back to the in-distribution ASVspoof spoof; put the measured miss on the limitations slide |
| Live toolchain eats the sprint | Medium | Tier A clone assets are pre-generated; L8 is optional and last |
| Venue mic permission denied | Medium | Browser capture uses the browser's existing grant; the UI says "no audio" explicitly; screen recording fallback stays |
| Browser tab backgrounded mid-run | Low | Capture lives in the worklet, not timers; the run stays alive while audio is flowing |
| Live latency worse than the file path | Medium | Measure (M2) and show `pipeline_lag_ms`; shorten the ASR cut in `config.yaml` for live only |
| Scope creep into telephony/translation | Medium | SPEC §3 still applies: RTP stays a stub; captions are English; no MT model |

---

## 10. Definition of done

- [x] A person can enrol their voice live, speak live, and watch the system react.
      (Checked end to end by `scripts/browser_e2e.py` with a fake microphone; a
      human on the demo laptop is the last manual step.)
- [x] Indirect high-risk lines fire; benign twins stay quiet; both rates printed
      (`scripts/eval_trigger.py`, pinned in `tests/test_trigger.py`).
- [x] A second speaker gets an honest "unknown voice"; the first gets their name
      (browser E2E: 0.97 for the enrolled voice, 0.73 for the second speaker
      against an accept line of 0.8998 — and a genuine voice below the line is
      reported, not hidden).
- [x] The clone asset plays and the verdict matches the measured clone report
      (`artifacts/clone_report.json`; the in-distribution ASVspoof spoof is the
      demo asset until a real cloned voice of a consenting person exists).
- [x] Every new number on screen is traceable to a calibration or a measurement.
- [x] The WiFi-off run still works, and no audio is written to disk
      (`tests/test_privacy.py`; the browser E2E re-checks the enrolment store).
- [x] The full test suite passes; the golden snapshot is either unchanged or
      regenerated deliberately, and the diff was read.
