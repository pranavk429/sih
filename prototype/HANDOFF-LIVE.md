# Sentinel — the live build, and how to run it

**Sprint L is built.** The microphone path, live voice enrolment and lookup, the
trigger reasoning panel and the try-a-line box all exist and are tested. This is
the handoff: what changed, how to run the live demo, what is measured and what
is still provisional, and the things that will bite you.

Read `PLAN-LIVE.md` for the design and the ordered tasks; this file is the state
of them.

---

## How to run it

```bash
cd /Users/pranav1296/SIH/prototype
P=../detector/venv/bin/python

$P -m pytest tests/ -q          # the full suite
$P -m sentinel.cli serve        # UI at http://127.0.0.1:8000
```

The browser needs microphone permission **once**. On the demo laptop, click
*Live mic → Record 10s voice* before the first real run: that is the prompt, and
getting it out of the way early means the demo never shows a permission dialog
to the audience.

The UI itself is checked end to end — source switch, recorded call, live mic,
voices, try-a-line, prompt cards, theme — by driving a real Chromium with a fake
microphone (no human, no device). It needs Playwright, so it is optional tooling
and not part of the pytest suite:

```bash
python3 scripts/browser_e2e.py          # screenshots land in a temp dir it prints
python3 scripts/browser_e2e.py --headful   # watch it happen
```

### The 3-minute demo script

1. **Voices panel → Record 10s voice.** Say a sentence or two. Name it.
   *The rail says: a 256-number fingerprint is stored, the recording is not.*
2. **Audio source → Live mic.** Pick the voice you just recorded as the
   reference. **Start listening.**
3. **Ordinary call.** Read a neutral line from *suggested lines*:
   *"I'll transfer you to the other line, please hold."*
   Watch: live captions, the margin chip next to the line stays low and grey,
   the verdict stays `MONITORING`, and the timeline shows the voice check
   running while the artifact check is **not** running. That contrast is the
   thesis on screen.
4. **Indirect instruction.** *"If anyone from the branch rings, you were in a
   meeting."* (measured +0.53, semantic only — no keyword overlap; *"Let's not
   wake the second pair of eyes on this one."* is the +0.80 alternative).
   Watch: the chip turns amber, crosses the line, the trigger fires, the gated
   region opens on the timeline, deep verification runs, and a verdict lands.
   **Do not** use *"just move it over to the new details before close of
   business"* — it is a measured miss (`KNOWN_MISSES`, −0.05); it is on the
   card screen under *measured misses* precisely so nobody reads it expecting a
   trigger.
5. **A second person speaks.** The lookup chip goes to *unknown voice*, with
   the best score printed below the threshold. The system does not accept the
   words just because it heard them.
6. **Play the clone asset** (see the measurement section for which one).
   `attack.wav` is a synthesised voice of the **dataset speaker** (LA_0022), not
   of the person you just enrolled — so say that: it demonstrates that a
   synthetic voice is caught, not that *your* voice was cloned. The countermeasure
   flags it; the numbers are in the clone report.
7. **Hand the keyboard over.** Anyone can type into *try a line* and watch the
   same engine score it. That is the answer to "is it just keywords?"

---

## What changed

| Area | Where | What it does |
|---|---|---|
| Live audio in | `sentinel/audio/live_source.py`, `WS /live/audio` | Browser microphone → 16 kHz frames, bounded queue, drop-oldest with a counter, stream time from received samples |
| Browser capture | `static/live.js`, `static/pcm-worklet.js` | getUserMedia → AudioWorklet → 20 ms Float32 chunks over the socket; records enrolment clips too |
| Voice lookup | `sentinel/enrolment/gallery.py` | Open-set identification against every enrolment, threshold + runner-up margin + two-window debounce |
| Voice storage | `POST/GET/DELETE /voices` | Enrol from the browser; fingerprints only, never audio |
| Trigger reasoning | `trigger/engine.py::assess`, transcript chips, `POST /assess` | Every utterance gets a margin and the families it was closest to — including the last lines the ASR flushes after the source has ended, which the post-loop drain now assesses like any other; the typed box runs the same code |
| Live controls | `static/index.html`, `static/app.js`, `static/style.css` | Source switch, mic meter, voices panel, try-a-line, prompt cards (including a group for the two measured misses, so no card promises a trigger the system does not deliver), live honesty banner |
| Scripts | `calibrate_lookup.py`, `eval_trigger.py`, `make_clone_assets.py`, `make_clone_report.py` | The measurements; none of them run during the demo |
| CLI | `run --mic`, `enrol --mic` | The headless live path via `sounddevice`, for when the browser is the problem |

Not changed on purpose: `decision/`, fusion, gating, the calibration band. The
voice lookup is a **separate visible signal**, deliberately not fused into the
verdict — fusing an unmeasured score would be a statistical claim we have not
earned.

---

## Measured, provisional, and how to tell

| Number | Where | State |
|---|---|---|
| Lookup `accept_similarity` = 0.8998 | `config.yaml: lookup.*`, `artifacts/lookup_calibration.json` | **MEASURED** (`scripts/calibrate_lookup.py`, 2026-09-23): the impostor p99 over 258 different-speaker trials. Same-speaker mobile-degraded pairs reach 0.8777–0.8995, so the two sets **overlap** — 2 of 4 genuine pairs accepted, 3 of 258 impostors. Pilot scale, one speaker; the caveats are in the report. `tests/test_lookup_calibration.py` fails if config and report disagree |
| Trigger corpus (indirect positives + traps) | `intents.py`, `tests/test_trigger.py` | **MEASURED** (`scripts/eval_trigger.py --candidates`, 2026-09-23): 36/36 canonical fire; 15/15 curated negatives and 8/8 topical traps stay quiet; held-out ordinary talk 11/12 (the one miss is the documented `KNOWN_FALSE_POSITIVES` line); 7 of the 12 PLAN-LIVE candidates promoted, 5 named in `KNOWN_MISSES` with their margins. The prompt cards' group labels are checked by the browser E2E |
| Clone assets: which are caught | `artifacts/clone_report.json` | **MEASURED** (2026-09-23): the three `say` TTS assets land mean fused 0.51–0.57 (caught; CM 0.88–0.94), the ASVspoof spoof 0.48 (caught), the genuine call 0.33 (below the band, correctly). Step 6 plays `attack.wav`; the `say` assets demo "machine speech is caught at all" |
| Live latency | `pipeline_lag_ms` on screen, `scripts/bench_latency.py` | Reported, never asserted. The green browser E2E runs kept the lag chip hidden (i.e. under the 500 ms warn line) on this laptop; `bench_latency.py` covers the recorded path (median 852 ms trigger → verdict) |

Every number the UI shows is still either from `calibration.json`, this table,
or an event the server sent. The UI never recomputes anything.

---

## The clone demo: what to play and why

`PROJECT-EXPLAINED.md` Truth 1: a detector is only as good as the attacks it
has seen. Our countermeasure was fitted on ASVspoof2019-LA.

**Measured 2026-09-23** (`scripts/make_clone_report.py` →
`artifacts/clone_report.json`, per-file mean fused risk over voiced windows):

| asset | truth | windows | mean fused | mean CM | verdict |
|---|---|---|---|---|---|
| `say-samantha` | synthetic TTS | 16 | 0.529 | 0.897 | caught (above the band) |
| `say-daniel` | synthetic TTS | 17 | 0.572 | 0.943 | caught |
| `say-karen` | synthetic TTS | 16 | 0.513 | 0.878 | caught |
| `attack.wav` | ASVspoof spoof | 68 | 0.480 | 0.800 | caught |
| `genuine.wav` | bonafide | 47 | 0.327 | 0.514 | below the band — correct, it is genuine |

- **What step 6 plays: `artifacts/demo/attack.wav`** — an in-distribution
  ASVspoof spoof of the enrolled speaker, measured caught. Safe, always
  available, and the number on screen comes from the report.
- `artifacts/clones/` — the three `say` assets. They are **synthetic TTS but not
  a clone of any enrolled person**, so demo them as *"can it hear machine speech
  at all"* (measured: yes, CM 0.88–0.94), never as "someone's voice cloned".
- Tier A/B in `PLAN-LIVE.md` §2 — a real clone of a consenting person — needs
  their recording. Generate it offline, add it with
  `make_clone_assets.py --from-file`, then run `make_clone_report.py` **before**
  claiming anything on stage.

If a modern clone slips past the pilot countermeasure, that is a real finding,
not a demo failure. Say the measured number and put it on the limitations
slide; that is the same standard this project applies to other people's
detectors.

---

## Things that will bite you

1. **The microphone is a new channel.** Enrolment in the demo is from the same
   microphone as the call, which is the best case. A voice enrolled from one
   device and heard through another will score lower; the threshold was
   calibrated on dataset audio, not on this room. The browser E2E measured
   same-microphone TTS at **0.85–0.99** across runs against an accept line of
   0.8998 — so a genuine speaker can occasionally be shown as *unknown voice*.
   That is the measured overlap in `config.yaml: lookup.*`, not a bug, and the
   demo should say so if it happens rather than hiding the number.
2. **`LiveSource` drops oldest, ASR blocks.** That ordering is deliberate:
   a growing, invisible delay is worse than a visible gap. `audio_dropped_ms`
   climbs in the footer when it happens. On the demo laptop it should stay 0.
   Whisper is the one stage that can fall behind real time on a busy machine
   (the browser E2E saw exactly that when other apps were competing): the ASR
   queue then blocks, the live queue starts dropping, and the lag chip says so.
   Close other apps before the demo; the numbers on screen are how you know.
   A speaker who never pauses for 500 ms gets cut at `asr.max_utterance_ms`
   (12 s) and the words can fragment — the demo lines all have natural pauses.
3. **macOS denies the microphone by returning silence.** The UI watches the
   level and says *no audio — check the microphone permission* instead of
   looking healthy. If you see it, fix the permission before continuing.
4. **The golden test compares stats keys.** `SENTINEL_UPDATE_GOLDEN=1` and read
   the diff, as always.
5. **Enrolment is refused during a run** (409) — the pipeline is reading the
   same encoder. Stop, enrol, start again.
6. **The scripted overlay is off in live mode, always.** Config cannot turn it
   back on. Putting words in a live speaker's mouth would make the demo
   dishonest.
7. **`tests/test_live_pipeline.py` is the one that proves the live path is the
   same pipeline.** If it fails, the live path has started diverging — do not
   "fix" the test.

---

## Where the build stands

- [x] Browser microphone → pipeline, with the file path's exact event stream
- [x] Live enrolment (fingerprint only) and open-set lookup with debounce
- [x] Assessment on every utterance; typed try-a-line box sharing the same engine
- [x] Prompt cards, live honesty banner, mic meter, no-audio warning
- [x] Measurements scripted and gated by tests on the config
- [x] Lookup threshold measured and pasted (`M1`)
- [x] Trigger corpus measured and promoted (`M3`)
- [x] Clone assets generated and reported (`M4`)
- [x] Browser E2E: a real Chromium with a fake microphone runs the whole demo
      path (39 checks) — `scripts/browser_e2e.py`. A human speaking into the
      demo laptop's microphone is the last manual step, and a screen recording
      of it is still worth taking.
