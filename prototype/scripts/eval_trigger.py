"""
Measure the trigger over the full corpus. A tool, not a gate.

IMPLEMENTATION-PLAN rule 3 and PLAN-LIVE §4: a sentence is promoted into
`intents.py` because this script says it works, not because it sounds right.
It prints, per sentence: fired or quiet, which stage fired, the margin, the
nearest intent family, and the nearest ordinary line -- so a near-miss can be
judged with the same information the UI shows.

Run it before and after touching the corpus:

    ../detector/venv/bin/python scripts/eval_trigger.py
    ../detector/venv/bin/python scripts/eval_trigger.py --candidates

Loads MiniLM, so allow it a few seconds.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sentinel.config import Config  # noqa: E402
from sentinel.trigger.engine import TriggerEngine  # noqa: E402
from sentinel.trigger.intents import (  # noqa: E402
    HARD_POSITIVES,
    HELD_OUT_NEGATIVES,
    INTENTS,
    LABELS,
    NEGATIVES,
    canonical_sentences,
)
from sentinel.types import Utterance  # noqa: E402

# ---------------------------------------------------------------------------
# Candidates from the PLAN-LIVE research pass. These are NOT in intents.py
# until this script says they pass, and each positive is measured next to its
# topical twin in TRAPS: a positive promoted without its trap is not evidence.
# ---------------------------------------------------------------------------
CANDIDATE_POSITIVES = (
    ("fund_transfer", "just move it over to the new details before close of business"),
    ("fund_transfer", "settle it against the alternate details on the note I sent"),
    ("fund_transfer", "that side needs to be empty by morning"),
    ("credential_request", "read me back whatever just came through on your handset"),
    ("credential_request", "I only need the three numbers off the back"),
    ("credential_request",
     "there's a message on your phone, stay on the line and read it out to me"),
    ("urgency_authority", "the window closes today, I would move now if I were you"),
    ("urgency_authority",
     "I have the commissioner holding on the other line, this needs to be done in "
     "the next few minutes"),
    ("bypass_verification", "let's not wake the second pair of eyes on this one"),
    ("bypass_verification",
     "put it through on your own authority, I'll sign off when I'm back"),
    ("no_callback", "if anyone from the branch rings, you were in a meeting"),
    ("no_callback", "I'd rather this didn't travel beyond the two of us"),
)

TRAPS = (
    "the account will be empty by the time the overnight sweep runs",
    "never share that code with anyone, not even if they say they're from the bank",
    "if you need anything else, please call us back on the number on the website",
    "for your security that needs both approvers, I can't action it on my own",
    "I'm putting you through to the fraud team, they'll verify a couple of details",
    "we'll settle the invoice automatically on the due date, nothing needed from you",
    "keep your PIN somewhere safe and never write it down",
    "take your time, there's no rush, we can sort it tomorrow",
)


def _utt(text: str) -> Utterance:
    return Utterance(text=text, t_start_ms=0, t_end_ms=3000)


def _row(engine: TriggerEngine, text: str) -> dict:
    assessment, event = engine.assess(_utt(text))
    return {
        "text": text,
        "fired": assessment.fired,
        "stage": assessment.stage,
        "margin": assessment.margin,
        "intent": assessment.intent_label,
        "benign": assessment.benign_text,
        "reason": assessment.reason,
        "terms": list(assessment.matched_terms),
        "engine": event is not None,
    }


def _print_group(title: str, rows, expect: str) -> tuple:
    print(f"\n{title}")
    print("-" * 100)
    ok = 0
    for row in rows:
        mark = "FIRE " if row["fired"] else "quiet"
        correct = (row["fired"] and expect == "fire") or \
                  ((not row["fired"]) and expect == "quiet")
        ok += 1 if correct else 0
        print(f"  {mark}  margin {row['margin']:+.2f}  [{row['stage']:8s}]  "
              f"{row['text'][:66]!r}")
        if row["fired"] != (expect == "fire"):
            print(f"          → {row['reason']}")
        elif row["fired"]:
            print(f"          → {row['intent']}"
                  + (f" · keywords {row['terms']}" if row["terms"] else " · no keyword overlap"))
    print(f"  {ok}/{len(rows)} as expected")
    return ok, len(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", action="store_true",
                        help="include the PLAN-LIVE candidate sentences")
    args = parser.parse_args()

    cfg = Config.load()
    print("loading the trigger encoder...")
    engine = TriggerEngine(cfg.trigger, cfg.models)
    print(f"margin threshold {cfg.trigger.semantic_margin:+.2f} · "
          f"keyword-confirm floor {cfg.trigger.lexical_confirm_floor:+.2f} · "
          f"min words {cfg.trigger.min_words}")

    totals = [0, 0]

    canonical, keys = canonical_sentences()
    rows = [_row(engine, text) for text in canonical]
    _print_group("1. Canonical intent sentences (must fire)", rows, "fire")

    rows = [_row(engine, text) for text in NEGATIVES]
    ok, n = _print_group("2. Curated ordinary banking talk (must stay quiet)", rows, "quiet")
    totals[0] += ok; totals[1] += n

    rows = [_row(engine, text) for text in HELD_OUT_NEGATIVES]
    ok, n = _print_group("3. HELD-OUT ordinary talk (never used for tuning)", rows, "quiet")
    totals[0] += ok; totals[1] += n

    rows = [_row(engine, text) for text in HARD_POSITIVES]
    _print_group("4. Paraphrases with no keyword overlap (must fire)", rows, "fire")

    if args.candidates:
        rows = [_row(engine, text) for _, text in CANDIDATE_POSITIVES]
        _print_group("5. PLAN-LIVE candidate positives (unpromoted)", rows, "fire")

    rows = [_row(engine, text) for text in TRAPS]
    ok, n = _print_group("6. Topical traps for the candidates (must stay quiet)", rows, "quiet")
    totals[0] += ok; totals[1] += n

    print(f"\nnegatives as expected: {totals[0]}/{totals[1]}")
    print("\nPromotion rule (PLAN-LIVE §4): a candidate sentence moves into "
          "intents.py only when it fires\nAND every trap above stays quiet AND "
          "test_trigger.py still passes. Anything else goes\ninto KNOWN_MISSES "
          "or KNOWN_FALSE_POSITIVES with the margin printed here.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
