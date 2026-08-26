# Sentinel

Voice-cloning call-fraud defence — trigger → verify → challenge → evidence. SIH26104.

    cd prototype
    ../detector/venv/bin/python -m sentinel.cli serve   # UI at http://127.0.0.1:8000

That path is the only Python that has the models installed — do not `pip install` into a new venv.
Pick a call, hit Run call. To sanity-check the build first: `../detector/venv/bin/python -m pytest tests/ -q`.
Numbers, honesty rules, what's real vs. scripted: `SPEC.md`. Where the build currently stands: `HANDOFF-DAY4.md`.
