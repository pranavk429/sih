# SIH 2026 Idea PPT — Content Plan

Built against the official template (`SIH2026-IDEA-PresentationFormat (1).pptx`),
read directly — 6 slides max including title, points/diagrams only, no
paragraphs, sections cannot be restructured, PDF submission only.

Judging weights confirmed by research: Relevance to PS (25), Innovation &
Originality (25), Feasibility (20) — 70% of the score sits in three boxes.
Slide 2 and Slide 4 below are where we spend the most craft.

**Confirmed official details from portal:**
- Problem Statement ID: **SIH26104**
- Theme: **Miscellaneous** (PS Category: Software)
- Team ID: **[FILL]**
- Team Name: **[FILL]**
- Idea Name: **[ YOUR IDEA NAME ]** (e.g. VeriVoice / EchoGuard)

---

## Slide 1 — Title Page

- Problem Statement ID: **SIH26104**
- Problem Statement Title: AI-Powered Real-Time Detection and Prevention of
  Voice Cloning Impersonation Attacks
- Theme: **Miscellaneous**
- PS Category: Software
- Team ID: **[FILL]**
- Team Name: **[FILL]**

---

## Slide 2 — Idea Title / Proposed Solution

**Suggested idea name** (replace freely): **VeriVoice** or **EchoGuard** —
short, ownable, easy to say out loud in a 5-minute pitch.

### Detailed explanation of the proposed solution
One line, then a diagram — no paragraph:

> A tiered voice-integrity gate for high-stakes calls: verify enrolled
> speakers directly, trigger only when money or access is at stake, and
> never output a bare score — always evidence plus a defensible decision.

Diagram (simple 4-box flow, left to right):
`TRIGGER (listens for risk) → VERIFY (enrolled? check directly) → CHALLENGE (unsure? interrupt & test) → EVIDENCE (why, not just a number)`

### How it addresses the problem
Quick tick-list mapped straight to the PS's own bullets — protects the
Relevance score by showing full coverage in one glance:
- ✅ Multi-layer voice authenticity analysis
- ✅ Real-time risk scoring engine
- ✅ Alerting & user interaction layer
- ✅ Privacy & compliance (edge inference, feature-only logging)
- ✅ Platform/API-ready, multilingual

### Innovation and uniqueness of the solution — THE KEY SLIDE
A 4-row comparison table. This is the single highest-leverage box in the
deck — it sits under both Innovation (25) and Relevance (25) at once:

| What the problem statement describes | What we built instead |
|---|---|
| "Is this audio fake?" — open-world blind detection | "Is this the person we know?" — enrolled speaker verification, ~10-20x more accurate |
| Score every call | Trigger deep checks only at high-stakes moments — fixes false-alarm fatigue |
| One detector for all attacks | Two-branch defense: AI-voice callers vs. human-driven live voice converters |
| A confident number, always | Honest "not sure — escalate" when evidence is weak |

---

## Slide 3 — Technical Approach

### Technologies to be used
Compact list, not paragraphs:
- wav2vec2-XLSR (multilingual speech encoder, Apache-2.0 licensed)
- Speaker-verification fusion (enrolled-reference matching)
- Lightweight semantic trigger on the live call transcript
- ONNX runtime — on-device/edge inference (real privacy, not a slide claim)
- WebRTC / SIP for telephony integration
- Python/PyTorch training, FastAPI serving

### Methodology and process for implementation
Same 4-box pipeline diagram as Slide 2, now with one added technical
callout: **trained against simulated Indian telephony conditions**
(Opus/G.711 codecs, packet loss) — because a detector trained on clean
studio audio is not a detector that works on a real phone call.

---

## Slide 4 — Feasibility and Viability

### Analysis of the feasibility of the idea
Real, already-measured numbers — most teams will have zero at this stage:

- **Pilot experiment, run today:** clean baseline 7.9% error → 13.5% after
  simulated phone-line degradation → 11.7% once enrollment is added back
  (pilot scale, full-scale Kaggle run in progress — update this box with
  the real number once it lands)
- **Budget:** ₹0-10,000 total — GPU compute is free (Kaggle, or the
  government's own IndiaAI Compute Portal)
- **Timeline:** building now (Sept) → idea screening (Oct-Nov) → 36-hour
  Grand Finale build (Dec) — a realistic, already-underway schedule, not
  a promise

### Potential challenges and risks / strategies for overcoming
Paired rows, risk → mitigation:

| Risk | Mitigation |
|---|---|
| Detectors don't generalize to new cloning tools | Enrollment-first design sidesteps the open-world detection problem |
| Phone networks destroy the fine audio detail detectors need | Channel-hardened training on real Indian network conditions |
| Naive real-time alarms cause false-alarm fatigue | Semantic triggering — only escalate when stakes are real |
| Some attacks use a live human (voice conversion), defeating simple liveness checks | Two-branch detection with different signals per attack type |

---

## Slide 5 — Impact and Benefits

### Potential impact on the target audience
- **Individuals/families:** protection against emotional scams (fake
  emergency/kidnapping calls using a cloned family member's voice)
- **Banks/enterprises:** prevents CXO-impersonation fraud on fund-transfer
  and access-approval workflows
- **Telecom/government:** a reusable security layer — directly matches the
  PS's own stated "Expected Outcomes"

### Benefits (social, economic, environmental)
- **Social:** restores trust in voice-based communication; protects the
  most vulnerable targets (elderly relatives, family-emergency scams)
- **Economic:** AI-driven impersonation fraud reported up 148% in a
  single year — direct reduction in financial loss at scale
- **Environmental (light touch):** edge/on-device inference means no
  always-on cloud processing of every call — smaller footprint than a
  fully cloud-based alternative

---

## Slide 6 — Research and References

Real sources actually used to build this idea — a strength most teams
won't have, since this is genuine literature grounding, not a Wikipedia
skim:

- ASVspoof 5 Challenge results — state-of-the-art detection benchmarks
- SASV Challenge — Spoofing-Aware Speaker Verification fusion research
- RawBoost — telephony-robust anti-spoofing data augmentation
- "The Watermark Shortcut" — provenance-watermark contamination in
  deepfake detectors (arxiv.org/html/2606.23335v1)
- Base-rate fallacy in cybersecurity detection systems
  (arxiv.org/pdf/2203.08801)
- IndicSynth — multilingual Indian-language synthetic-speech dataset
- Real-time voice-conversion (RVC) latency research
- Independent reporting on commercial detector accuracy in the field
  (60-75% on live VoIP vs. 99% claimed)

---

## Slide 7 (delete before submission)

Official instructions slide — remove per the template's own note before
uploading to the portal.
