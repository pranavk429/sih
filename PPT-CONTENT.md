# SIH 2026 Idea PPT — Full Content

Copy-paste ready. Build order: text first, boxes second, colours last.

---

## Design basics (30 seconds of setup)

**Safe area.** Slide is 13.33 × 7.5 in. The template has a blue bar at the
bottom and the SIH logo top-right.
Keep all content between **x = 0.4 → 12.9** and **y = 1.2 → 6.8**.
Nothing below 6.85 or it collides with the blue bar.

**Colours** (use these five, nothing else):
| Use | Hex |
|---|---|
| Headings / dark text | `1F497D` navy |
| Accent / links / our-side | `0070C0` blue |
| Attack / risk / problem | `B32D2D` red |
| Our answer / benefit | `1B7A43` green |
| Card fill | `EEF3F9` pale blue |

**Fonts.** Arial throughout. Titles 28–36 bold, section headers 12–14 bold,
body 10–11, table cells 9–10. Nothing smaller than 9.

**One repeating element.** Every required template heading becomes a **navy bar
with white bold text**, ~0.33 in tall, sitting above its content. Same on every
slide. That single repetition is what makes a deck look designed.

**Two rules that fix most alignment problems:**
1. Select boxes → Format → Align → *Align Top* / *Distribute Horizontally*.
   Never drag by eye.
2. Pick one gap (0.15 in) between cards and one (0.45 in) between sections.
   Use only those two numbers.

---

# SLIDE 1 — Title Page

The template's title slide has a **solid blue panel from x = 1.67 rightward**.
Dark text on it reads badly. Put a **white rounded rectangle** behind your
text block (roughly x 0.3, y 2.0, w 6.8, h 2.6) and the text on top of it.

**Text:**

```
Problem Statement ID – SIH26104

Problem Statement Title – AI-Powered Real-Time Detection and Prevention
of Voice Cloning Impersonation Attacks

Theme – Miscellaneous

PS Category – Software

Team ID – [FILL]

Team Name (Registered on portal) – [FILL]
```

Labels bold navy, values regular. Also replace the "Your Team Name" oval
top-left with your logo.

---

# SLIDE 2 — Idea Title / Proposed Solution

**The highest-scoring slide.** Innovation (25) + Relevance (25) both live here.

### Title area (top centre)

```
[ YOUR IDEA NAME ]
Verify the speaker — don't just guess at the audio
```
Name 28pt bold navy. Tagline 13pt italic blue underneath.

---

### Section 1 — "Proposed Solution — detailed explanation"
*Navy bar, full width, at y ≈ 1.2*

One line underneath (12pt, bold lead-in):

```
A tiered voice-integrity gate for high-stakes calls: verify enrolled
speakers directly, trigger deep checks only when money or access is at
stake, and never output a bare score — always evidence plus a defensible
decision.
```

**Then a 4-box flow across the full width** (four equal boxes, y ≈ 2.3,
each ~3.0 in wide, 1.1 in tall, small blue arrow between each):

| Box | Heading (bold, coloured) | Body (9.5pt grey) |
|---|---|---|
| 1 | **1 TRIGGER** *(blue)* | Follows the call cheaply. Wakes on transfer, OTP, urgency + authority. |
| 2 | **2 VERIFY** *(navy)* | Enrolled voice on file? Match against it directly. Robot caller or puppeteer? |
| 3 | **3 CHALLENGE** *(amber `C16C0A`)* | Still unsure? Interrupt and test live — prevention, not just observation. |
| 4 | **4 EVIDENCE** *(green)* | Which seconds, which artefact, tamper-proof log. No raw audio stored. |

---

### Section 2 — "How it addresses the problem"
*Navy bar, left column (~4 in wide), y ≈ 3.7*

Green ticks, 10.5pt:

```
✓ Multi-layer voice authenticity analysis
✓ Real-time risk scoring engine
✓ Alerting & user-interaction layer
✓ Privacy by design — on-device inference, feature-only logs
✓ API- and telephony-ready, multilingual
```

Small italic line under it:
```
Full PS coverage — plus four things it never asked for.
```

Then a small **amber-bordered box** at the bottom of this column:
```
The clause most teams will skip
The problem statement mentions enrolment in a single buried line.
Building the whole architecture around it is the unglamorous move —
which is exactly why it wins.
```

---

### Section 3 — "Innovation and uniqueness of the solution"
*Navy bar, right column (~8.3 in wide), y ≈ 3.7*

**A two-column table, 4 rows.** Left column header grey
("The obvious build — what most teams will do"), right column header navy with
white text ("What we build instead"). Left cells pale grey, right cells pale
blue with a blue border and **bold** text.

| The obvious build | What we build instead |
|---|---|
| "Is this audio fake?" — open-world blind detection | "Is this the person we enrolled?" — speaker verification, ~10–20× lower error |
| Score every single call | Semantic trigger fires deep checks only at high-stakes moments — kills alert fatigue |
| One detector for every attack | Two-branch defence: AI robot caller vs. live human puppeteer (RVC) |
| A confident number, always | Honest "not sure — escalate to a human" when the evidence is weak |

---

# SLIDE 3 — Technical Approach

Two columns: left ~4.5 in, right ~7.8 in.

### Left — "Technologies to be used"
*Navy bar at y ≈ 1.2*

Bold lead-in, grey detail, 10.5pt:

```
Speech AI — wav2vec2-XLSR multilingual encoder (Apache-2.0);
            ECAPA-TDNN speaker embeddings
Verification — learned fusion of enrolled-reference similarity +
            spoof countermeasure score
Trigger — lightweight intent model over the live call transcript
            (Whisper-small, streaming)
Serving — ONNX Runtime, INT8 quantised — real on-device inference,
            not a slide claim
Telephony — WebRTC / SIP via Asterisk; RTP stream tapped frame-by-frame
Build — Python, PyTorch, FastAPI; free GPU on Kaggle / IndiaAI Compute Portal
```

**Amber box below it:**
```
Constraint we designed around
Android blocks call-audio capture (2019, closed 2022). Any app claiming to
listen to normal phone calls is not shippable — so the system sits in the
VoIP/SIP path, where it is legal and controllable.
```

**Blue box below that:**
```
How the demo runs
Two laptops on a local SIP server. We clone a volunteer's voice with
open-source tools, place the call, and the system triggers, challenges and
produces evidence live — with the venue internet unplugged, so a dead
network cannot kill the demo.
```

---

### Right — "Methodology and process for implementation"
*Navy bar at y ≈ 1.2*

**Four stacked rows**, each = a small coloured label box (1.4 in) + a wide pale
text box, with a small down-arrow between rows:

| Label (white on colour) | Text (9.5pt) |
|---|---|
| **TRIGGER** *(blue)* | Always-on, cheap. Listens for a transfer instruction, credential request, or urgency + authority pressure. Nothing escalates until stakes are real. |
| **VERIFY** *(navy)* | Enrolled reference on file → direct speaker match. No reference → countermeasure model + honest low-confidence flag. Branches TTS vs. live voice conversion. |
| **CHALLENGE** *(amber)* | Suspicious? Inject an unexpected prompt and measure the response. This is the step that turns detection into prevention. |
| **EVIDENCE** *(green)* | Timestamped suspicious segments, artefact type, tamper-evident log. Mathematical features only — no raw call audio retained. |

**Green box underneath:**
```
Trained against simulated Indian telephony — not studio audio
Opus 8 kbps (VoIP / WhatsApp) · G.711 (PSTN and bank call-centre trunks) ·
5% packet loss. The fine detail that betrays a synthetic voice is exactly
the detail a phone network throws away, so we degrade the training data the
same way the network will.
```

---

# SLIDE 4 — Feasibility and Viability

Two columns: left ~6.0 in, right ~6.2 in.

### Left — "Analysis of the feasibility of the idea"

**A 3-bar chart.** Insert → Chart → Clustered Column, delete legend, gridlines
and axis. Bars sitting on one thin grey baseline. Value labels above each bar
in the bar's colour, 14pt bold.

```
Header above chart (10.5pt bold navy):
We already ran the experiment — equal error rate, lower is better

Bar 1: Clean audio            7.9%   (blue)
Bar 2: After a phone line    13.5%   (red)
Bar 3: + Enrolled reference  11.7%   (green)
```

Caption under the chart, 8.5pt italic grey:
```
Our own pilot, 23 Aug 2026 · leak-free protocol, speaker-disjoint split,
n=119 trials. The line hurts; enrolment claws back a third of the damage
using the crudest possible fusion. Full-scale GPU run in progress.
```

Then bullets, 10pt:
```
Budget: Rs 0–10,000 total. GPU compute is free — Kaggle (30 h/week) or the
   government's own IndiaAI Compute Portal.
Hardware: One 16 GB laptop. The demo runs fully offline, so a dead venue
   network cannot kill it.
Timeline: Building now (Sept) → idea screening (Oct–Nov) → 36-hour Grand
   Finale build (Dec). Already underway, not a promise.
Scope discipline: Four layers built properly; remaining PS components are
   designed and labelled as designed, not claimed.
```

**Blue box at the bottom:**
```
Already built — a repository, not a plan
Leak-free evaluation harness · telephony channel simulator (Opus / G.711 /
packet loss) · enrolment-fusion scoring · full-scale GPU run scripted and queued.
```

---

### Right — "Potential challenges, risks & strategies to overcome"

**Two-column table, 5 rows.** Left header grey "Risk", right header navy
"Strategy". Left cells pale red (`FCF1F1`) with red text; right cells pale blue
with bold dark text.

| Risk | Strategy |
|---|---|
| Detectors go blind against cloning tools they were never trained on | Enrolment-first design sidesteps open-world detection entirely |
| Phone codecs destroy the fine detail the detector depends on | Channel-hardened training on simulated Indian network conditions |
| A naive always-on alarm produces ~50 false accusations per real attack | Semantic trigger — escalate only when money or access is on the line |
| A live human driving voice-conversion software defeats liveness tests | Two-branch detection with a different signal for each attack type |
| Free "deepfake detector" checkpoints are often contaminated | We caught one scoring a fake 0.0% — we validate before we trust a number |

---

# SLIDE 5 — Impact and Benefits

### Top — "Potential impact on the target audience"
*Navy bar full width, y ≈ 1.2*

**Three equal cards across** (~4.1 in each), each with a coloured header bar and
a pale body. Inside each body: a small red "The attack" label, then text, then a
small green "What we give them" label, then text.

**Card 1 — Individuals & families** *(blue header)*
```
The attack
"Mum, I've had an accident, I need money now." Cloned-relative emergency
scams target the people least equipped to verify — parents and elderly
relatives.

What we give them
Enrolled family voices on a personal device; the alert reaches the person
being scammed, in their language.
```

**Card 2 — Banks & enterprises** *(navy header)*
```
The attack
CXO impersonation on fund-transfer and access-approval calls. Thirty seconds
of public audio is enough to clone an executive.

What we give them
Verification fires exactly at the transfer instruction — the moment that
matters — not on every call.
```

**Card 3 — Telecom & government** *(green header)*
```
The attack
No shared defence layer exists today; each institution improvises its own.

What we give them
A reusable voice-integrity API that drops into existing call infrastructure
— the PS's own stated Expected Outcome.
```

---

### Middle — "Benefits of the solution (social, economic, environmental)"
*Navy bar full width*

**Four equal cards across** (~3.1 in each). Small coloured category label, bold
headline, grey body:

```
SOCIAL  (blue label)
Restores trust in the voice call
Voice is India's default channel for banking, government and family contact.
Once it can no longer be trusted, the cost is borne first by the people with
the fewest alternatives.

ECONOMIC  (navy label)
Fraud losses cut at the point of transfer
AI-driven impersonation fraud reported up 148% in a single year. Because we
act at the transfer instruction rather than after the fact, the money never
leaves.

OPERATIONAL  (amber label)
An alarm staff will still trust in week two
A 99%-accurate detector run on every call yields roughly 50 false accusations
per real attack, and gets switched off. Triggering only on high-stakes
moments is what makes it survivable in production.

ENVIRONMENTAL  (green label)
No always-on cloud processing
Inference runs on the edge device, so calls are not streamed to a datacentre
for continuous scoring — a materially smaller footprint than a cloud-first
design, and better privacy for the same reason.
```

---

### Bottom — closing strip
**One full-width navy bar**, centred white text, ~12.5pt:

```
Our accuracy number is not the product. The architecture around the number
is the product — because a 95% detector deployed naively produces 98%
false alerts.
```

---

# SLIDE 6 — Research and References

*Navy bar full width: "Details / Links of the reference and research work"*

Intro line, 10pt italic:
```
Every design decision on the previous slides traces to one of these. The
numbers we quote are other people's measurements or our own — none are
estimates.
```

**Eight small cards, two columns of four.** Each: bold navy title, blue italic
link if there is one, grey one-line explanation.

**Left column:**
```
ASVspoof 5 Challenge   asvspoof.org
State-of-the-art anti-spoofing benchmark. Best systems land at 9–20% EER —
the reason we refuse to claim 99%.

SASV Challenge — Spoofing-Aware Speaker Verification
The fusion research our enrolment-first architecture is built on: combine a
countermeasure with a speaker-verification score rather than choosing one.

RawBoost (Tak et al., ICASSP 2022)
Telephony-robust data augmentation. The basis for our codec + packet-loss
degradation pipeline.

ASVspoof 2019 LA dataset
Speaker-paired bonafide/spoof data — what made our own enrolment experiment
possible at pilot scale.
```

**Right column:**
```
Base-rate fallacy in intrusion detection   arxiv.org/pdf/2203.08801
Why a highly accurate detector still drowns operators in false alerts. The
single reason we built a trigger layer.

"The Watermark Shortcut"   arxiv.org/html/2606.23335v1
Provenance watermarks contaminate deepfake detectors into learning the
watermark, not the fake. A trap we screen for.

IndicSynth
Multilingual Indian-language synthetic-speech dataset — our path to testing
beyond English benchmarks.

Independent testing of commercial detectors
Vendors advertise 99% (self-reported); third-party reporting puts real
performance at 60–75% on live VoIP.
```

**Full-width strip at the bottom:**
```
Our own work: leak-free probe methodology (task-naive backbone,
speaker-disjoint fit/test split, asserted in code) · telephony channel
simulator · full experiment log and results — reproducible end to end, not
quoted from a blog post.
```

---

## Before you submit

1. Delete slide 7 (the template says to).
2. Check it's exactly 6 slides.
3. **Export as PDF** — the portal rejects .pptx.
4. Replace the "Your Team Name" oval on every slide.
