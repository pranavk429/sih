# Idea PPT — handover

**File:** `SIH2026-Idea-PPT-DRAFT.pptx` (6 slides, built on the official
SIH 2026 template, instruction slide 7 already deleted).

Rough previews of each slide are in `ppt-preview/`. They are approximations
drawn without PowerPoint — fonts and shapes are close but not exact. Trust the
real file over the previews.

---

## 1. Three things only you can fill in

Search the deck for `[` and you'll find all of them.

| Placeholder | Where | What goes there |
|---|---|---|
| `[ IDEA NAME ]` | Slide 2 title | Whatever the team agrees on. It appears once — one edit. |
| `[ FILL ]` (Team ID) | Slide 1 | Team ID, if your college has issued one |
| `[ FILL ]` (Team Name) | Slide 1 | Team name as registered |

**Already filled in from the official PS list** (`Smart India Hackathon-2.pdf`):

- Problem Statement ID: **SIH26104**
- Theme: **Miscellaneous** — *not* Blockchain & Cybersecurity. That's PS 105
  and 106. An earlier draft of the content plan guessed wrong; the deck is
  correct.
- PS Category: **Software**
- Organisation: AICTE · Portal deadline **20 September 2026** · cap 500 teams

Also on every slide: the small oval top-left still says **"Your Team Name"** —
that's the template's logo placeholder. Replace it with your team logo, or type
the team name into it.

---

## 2. What's on each slide

| # | Slide | The point it's making |
|---|---|---|
| 1 | Title | Required fields, on a white card so they read against the template's blue panel |
| 2 | Idea / Proposed Solution | The 4-stage pipeline, the PS checklist ticked off, and the comparison table — **this is the highest-scoring slide** (Innovation 25 + Relevance 25) |
| 3 | Technical Approach | Tech stack, the 4-layer architecture, and why we train on degraded phone audio |
| 4 | Feasibility | The three-number chart from our own experiment, budget, timeline, and 5 risk→strategy pairs |
| 5 | Impact and Benefits | Three audiences, four benefit categories, closing thesis line |
| 6 | Research and References | Eight sources, each with what it changed in our design |

**Every slide has speaker notes** (View → Notes) with the analogy or framing to
say out loud. You'll want these for the college round since you're presenting.

---

## 3. Before you submit

1. Fill the five placeholders above.
2. Replace the team-name oval with your logo.
3. **Export as PDF.** The SIH portal rejects .pptx, .doc and everything else.
4. Check the deck is still exactly 6 slides.

---

## 4. The one number that may change

Slide 4's chart shows **7.9% → 13.5% → 11.7%** — our pilot experiment run on
23 Aug, at pilot scale on a laptop.

If someone on the team runs the full-scale Kaggle job
(`detector/KAGGLE-RUNBOOK.md`, ~10 min of clicking then an hour unattended)
before you submit, send back `full_results.json` and I'll swap the three
numbers and the caption. If it doesn't happen in time, the current numbers are
honest and correctly labelled as a pilot — they can ship as they are.

---

## 5. Things I deliberately did not claim

Worth knowing, in case a judge probes:

- No "99% accuracy" anywhere. We name 9–20% as the state of the art and quote
  our own honest pilot figure. This is a strength, not a weakness — the deck
  says so explicitly.
- The PS components we are **not** building are labelled "designed, not claimed"
  on slide 4 rather than being quietly implied as built.
- Slide 3 states plainly that Android blocks call-audio capture and that the
  system therefore lives in the VoIP/SIP path. Getting caught on this later
  would be much worse than saying it up front.
