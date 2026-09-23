# Sentinel

Voice-cloning call-fraud defence — trigger → verify → challenge → evidence. SIH26104.

    cd prototype
    ../detector/venv/bin/python -m sentinel.cli serve   # UI at http://127.0.0.1:8000

That path is the only Python that has the models installed — do not `pip install` into a new venv.
Pick a call, hit Run call. To sanity-check the build first: `../detector/venv/bin/python -m pytest tests/ -q`.

**The live path.** Switch **audio source** to *Live mic*, record a voice in the
voices panel, pick it as the reference, then **Start listening** and talk. The
system transcribes, scores every window, fires on indirect high-risk intent and
shows who it is hearing. The 3-minute demo script is in `PLAN-LIVE.md`; the
current state and the numbers are in `HANDOFF-LIVE.md`.

The UI is checked end to end (a real Chromium with a fake microphone) by
`python3 scripts/browser_e2e.py` — optional tooling; it needs Playwright and is
not part of the pytest suite.

Numbers, honesty rules, what's real vs. scripted: `SPEC.md`. The recorded-call
build: `HANDOFF-DAY4.md`.
