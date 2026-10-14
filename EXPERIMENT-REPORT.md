# What we tested before we built anything — the complete record

**For: the SIH 2026 team · Presentation source material**
**Covers: the detector pilot (23 Aug 2026) and the four findings from the build (26–28 Aug 2026)**

Everything in this document is reproducible from files in this repository. No number
here is quoted from a blog post, a vendor page, or a paper. Where a number comes from
published literature instead of from us, it says so explicitly.

---

## Part 0 — The one-paragraph version

Before writing a single line of the actual product, we ran a small experiment to answer
three questions with real data. The first attempt handed us a **perfect score — 0% error
on everything.** Instead of celebrating, we checked *why*, and found that the free
"deepfake detector" we had downloaded had effectively memorised the answer key to the
exam we were giving it. We threw the model away, rebuilt the experiment so that cheating
was structurally impossible, and got honest numbers instead: **7.9% error on clean audio,
13.5% after a simulated phone line, 11.7% once we compared the voice against an enrolled
reference recording.** Those three numbers are the reason our architecture is shaped the
way it is. Then, during the build, we caught four more of our own mistakes — including a
second model that was answering a different question from the one we thought we were
asking it.

**The headline for the pitch is not the number. It is that we tried to break our own
result and succeeded.**

---

# PART 1 — THE EXPERIMENT WE RAN

## 1.1 Why we ran it

Our whole strategy rests on one claim: *asking "is this the person we enrolled?" beats
asking "is this audio fake?"* — especially over a real phone line.

That claim came from published research. Before betting a six-month competition on it,
we wanted to see it happen with our own data on our own machine. So we designed a
three-question test:

| # | The question, in plain English | What it tells us |
|---|---|---|
| 1 | How good is an ordinary fake-detector on clean studio audio? | Our starting point |
| 2 | How much does a real phone line damage it? | The problem nobody demos |
| 3 | How much do we get back by comparing against a genuine reference recording? | Whether our whole thesis holds |

**Analogy:** Question 1 is "can this guard spot a forged signature in good light?"
Question 2 is "can he still do it looking through a dirty window?" Question 3 is "does it
help if we hand him the real signature to compare against?"

## 1.2 The setup

- **Data:** ASVspoof2019 LA — the standard academic benchmark for this exact task.
  We streamed **261 audio files across 65 speakers** from Hugging Face and cached them
  locally (`detector/src/fetch_data.py`, log in `detector/fetch_data.log`).
- **Why this dataset specifically:** it is the only easily-available set where every
  speaker has *both* genuine recordings *and* fake recordings impersonating them. Without
  that pairing, question 3 is impossible to ask at all.
- **Hardware:** one laptop. No GPU. Entirely offline after the download.
- **The phone line:** we wrote our own telephony simulator (`detector/src/channel_sim.py`)
  rather than pretending phone audio is clean. It applies:
  - **Opus at 8 kbps** — the codec WhatsApp calls and mobile-data VoIP use
  - **G.711 mu-law at 8 kHz** — the codec bank call-centre trunks and landlines use
  - **5% packet loss** in 20ms chunks — a shaky mobile signal dropping bits of speech
  - Three named profiles: `pstn`, `mobile_voip` (what we reported), `mobile_poor`
- **The measurement:** EER — Equal Error Rate. One number, lower is better. It is the
  metric every anti-spoofing paper uses, which is what lets our number be compared to
  theirs honestly.

---

# PART 2 — THE TRAP: THE MODEL THAT LIED TO US

**This is the part you asked about, and it is the strongest story in the whole project.**

## 2.1 What we did

For the fake-detector itself, we did what any team would do: we went to Hugging Face
(the public library where AI models are shared for free) and downloaded a ready-made one
that advertised itself as a deepfake audio detector:

> `Gustking/wav2vec2-large-xlsr-deepfake-audio-classification`

It was correctly licensed (Apache-2.0, commercially safe), the documentation looked
right, and it loaded without trouble. We wrapped it (`detector/src/cm_model.py`), even
added a sanity assertion that its "real/fake" labels hadn't been swapped upstream, and
ran the three-question experiment.

## 2.2 What it told us

```
1. Clean baseline EER (CM only)........... 0.0%
2. Degraded EER (CM only)................. 0.0%
3. Degraded + enrollment fusion EER....... 0.0%
```

*(the real log: `detector/run_experiment.log`, results: `detector/results/pilot_results.json`)*

**Zero percent error. On all three passes. Perfect, including on audio we had
deliberately mangled through an 8kbps codec with 5% of the packets thrown away.**

## 2.3 Why we didn't believe it

A perfect score is not a good sign — it is a smell. Nothing in this field gets 0%. The
world's best systems in the leading academic challenge (ASVspoof 5) sit at **9–20% error**
under honest conditions. A random model off the internet beating them by 20 points, on
degraded telephone audio, is not a breakthrough. It is a bug.

So we opened up the raw scores instead of just reading the summary. Here is the tell:

> **Genuine human clips scored: mean = 0.069, standard deviation = 0.003.**

**Analogy:** imagine a doctor who examines 44 different patients and gives every single
one a temperature reading of 36.9°C, 36.9°C, 36.9°C… He is not a brilliant diagnostician.
He isn't looking at the patients at all — he already knows what he's supposed to say.

Standard deviation of 0.003 means the model gave *nearly the identical answer* to every
genuine clip regardless of who was speaking or what they said. A model that had genuinely
learned "what does synthetic speech sound like" would produce a spread — some clips
obviously human, some borderline. Near-zero spread is the fingerprint of **memorisation,
not learning.**

## 2.4 The diagnosis

The model's author had almost certainly fine-tuned it on ASVspoof2019 — **the same
dataset we were testing it with** — without respecting the official speaker-disjoint
train/evaluation split. So when we thought we were giving it an exam, we were handing it
questions it had already been given the answers to.

**The technical term is data leakage.** Our test set had leaked into its training set.

**Analogy:** we hired a security guard, showed him a stack of signatures, and he
identified every forgery perfectly. Then we discovered he had been trained on that exact
stack of signatures the week before. He hasn't learned to spot forgery. He has learned
this specific pile of paper.

## 2.5 Why this matters far beyond our project

Free "deepfake detector" checkpoints on public model hubs **cannot be trusted at face
value.** Several published ones report inflated accuracy from exactly this mistake.

**Most competing SIH teams will download one of these, see a spectacular number, put it
on a slide, and never look closer.** We know, because we nearly did.

---

# PART 3 — THE FIX: HOW WE REBUILT IT SO CHEATING WAS IMPOSSIBLE

## 3.1 The non-obvious insight

The tempting fix is: *"keep the model, just throw away its final decision layer and use
the rest as a feature extractor."* That's the standard move, and **it does not work here.**

That model was fine-tuned **end-to-end** — meaning the contamination soaked into the
entire model, not just its last layer. Reusing its body as a "frozen feature extractor"
carries the leak straight through. **You have to throw the whole thing away.**

*(This reasoning is written into `detector/src/probe_model.py` as the module's docstring
— it is not a claim we made afterward.)*

## 3.2 What we replaced it with

**1. A model that has never heard of this task.**
We switched to `facebook/wav2vec2-base` — a *self-supervised* model. It was trained only
to understand the general structure of speech. **It has never seen a "real vs fake" label
in its life, and has never encountered the ASVspoof task at all.** It cannot have
memorised an answer key it was never shown.

**2. We trained our own detector on top, ourselves, in the open.**
A simple logistic-regression classifier sitting on frozen features from that model. This
is standard, well-understood methodology called *linear probing*. Because we trained it,
we control exactly what data it saw.

**3. We split the speakers so a leak is structurally impossible.**

| Group | Speakers | Files | Purpose |
|---|---|---|---|
| **FIT** | 40 | 117 | The only data our detector is allowed to learn from |
| **TEST** | 25 | 119 trials | Every reported number comes from here. Never seen during training. |

**Zero speaker overlap.** And critically — this is not a claim in a README, it is
**asserted in the code and would crash the experiment if it were ever false**:

```python
overlap = set(r["speaker_id"] for r in fit_rows) & set(test_speakers)
assert not overlap, f"speaker leakage between fit/test: {overlap}"
print("speaker-disjointness verified: no leakage between fit and test sets")
```

**Analogy:** we didn't just promise the exam questions were new. We built the exam hall
so that a student who had seen the paper physically could not sit the test.

## 3.3 The proof the fix worked

The same diagnostic that exposed the fraud now shows a healthy model:

| | Old (leaking) model | New (leak-free) probe |
|---|---|---|
| Genuine clips | mean 0.069, **std 0.003** | mean 0.246, **std 0.180** |
| Fake clips | — | mean 0.808, **std 0.182** |
| Reported EER | 0.0% (impossible) | 7.9% (plausible) |

The spread is back. The model is now actually looking at the audio: some clips it is sure
about, some it finds borderline — which is what real judgement looks like.

---

# PART 4 — THE HONEST NUMBERS

```
LEAK-FREE PILOT RESULTS  (n=119 test trials, 25 test speakers, 117 fit examples)
============================================================
1. Clean baseline EER (probe CM only)..... 7.9%
2. Degraded EER (probe CM only)........... 13.5%
3. Degraded + enrollment fusion EER....... 11.7%
============================================================
```

*(`detector/run_experiment_v2.log`, `detector/results/pilot_results_v2_leakfree.json`)*

**How to read these three numbers out loud:**

1. **7.9% on clean audio** — a reasonable detector, in line with the honest academic
   range. Not magic, not fraud.
2. **13.5% after the phone line** — putting it through a real mobile codec with packet
   loss made it **about 70% worse.** This is the number nobody demos, because everyone
   demos on clean studio audio. **A phone call is where this attack actually happens.**
3. **11.7% with an enrolled reference** — comparing against a genuine recording of the
   real person **clawed back roughly a third of the damage the phone line did.**

**And the crucial honesty flag on number 3:** we combined the two signals in the crudest
way possible — a plain 50/50 average, with no training on how to weight them, because at
pilot scale we had no held-out data to learn the weights from. **That is a deliberately
pessimistic estimate.** A properly trained combiner should do better. We report the
pessimistic number because it is the one we actually measured.

---

# PART 5 — HOW THIS CHANGED OUR ARCHITECTURE

This is the part that matters most for the pitch: **the experiment was not a
box-ticking exercise. Five concrete design decisions came out of it.**

### 5.1 It confirmed the enrolment-first thesis — so we built the product around it

Question 3 moved in the predicted direction with real data on our own machine. That
justified the central architectural bet: **the system's primary question is "is this the
person we enrolled?", not "is this audio synthetic?"** Blind detection becomes the
supporting signal, not the star. Almost every competing team will build it the other way
round.

### 5.2 It made telephony degradation a first-class part of the system, not a demo trick

Seeing 7.9% → 13.5% with our own eyes is why the channel simulator is baked into the
product's evaluation path rather than being a slide bullet. We do not report clean-audio
numbers as if they were field numbers.

### 5.3 It produced the UNCERTAIN verdict — the single most defensible feature we have

This is the most direct architecture consequence, and it is worth knowing precisely.

The prototype does not use a made-up threshold. It uses **the score distributions this
experiment measured.** From `prototype/artifacts/calibration.json`:

- Equal-error threshold: **0.4220**
- Decision band: **low = 0.3636, high = 0.4575**
- The rule, stated in the file itself: `eer_threshold -/+ 0.5 * per-class fused std`

Anything landing **between** those two numbers is declared **UNCERTAIN** — and the system
escalates to a human call-back instead of pronouncing a verdict.

**Analogy:** a smoke alarm that either screams or stays silent will eventually be
unplugged. Ours is allowed to say "I smell something, go check the kitchen."

The band width came from the measured spread of real scores. **We could not have designed
this feature without having run the experiment**, and it is our answer to the hardest
question a judge can ask: *"what happens when you wrongly flag a real CEO?"* — nothing
gets blocked, a 30-second call-back gets recommended.

### 5.4 The pilot's numbers became the product's calibration file — and it is checked

The prototype does not just cite the experiment; it **loads its output.**
`calibration.json` carries a `reproduction_check` block confirming the prototype
reproduces the pilot's 11.68% EER with **0.0 percentage points of drift**. Every verdict
the system writes to its evidence log is stamped with the `calibration_id` it was decided
under, so an old decision stays attributable to the calibration that produced it.

### 5.5 It installed a standing rule: never trust a model's confident number

"Check whether the model is actually looking at the input" became a habit. **It is
directly why we caught three more bugs during the build — see Part 6.** That rule is
worth more than the 11.7%.

---

# PART 6 — THE JOURNEY CONTINUED: THREE MORE THINGS WE CAUGHT ON OURSELVES

The pilot was 23 August. These came out of the build itself, 26–29 August. Together they
make the "we try to break our own work" narrative a *pattern* rather than a one-off.

## 6.1 The models that confidently analysed silence

**Found:** the moment we put the evidence panel on screen, the *genuine* call — correctly
verdicted VERIFIED — was listing **seven windows at 0.99 "artifact risk"**, with no
voice-match score beside them.

**Cause:** one code path was scoring windows of audio that contained **no speech at all.**

**What the models did with silence:** they did not crash. They did not abstain. Fed nine
silent windows, the fake-detector scored **eight of them between 0.86 and 0.99
"synthetic"** — and the ninth at **0.17, "clean."** The speaker-verification model does
the same thing in mirror image: handed silence, it returns a well-formed embedding
scoring 0.31, i.e. "verified."

**The lesson, and it is the important one:** that stray 0.17 proves **no threshold can
rescue a score computed on nothing.** You cannot tune your way out of it. The check for
"is there actually a voice here?" has to come *first*, structurally — not as a filter
applied afterward.

**Fix and effect:** the voice-activity gate moved so that it is the single entry point to
deep scoring. Refused windows are recorded and displayed as SILENT rather than silently
dropped. Result on the genuine call: risk **0.363 → 0.317**. That matters because
0.363587 was the VERIFIED threshold — **the call had been passing by a margin of 0.0006.**
After the fix the margin is 0.0466, roughly 78× safer. **No threshold was changed to
achieve this.** Pinned by two regression tests so it can never come back.

## 6.2 The comparison that proves the trigger layer earns its place

Same genuine call, same audio, same models, two gating policies:

| Mode | False alarms on a genuine call |
|---|---|
| **Naive** (score every moment, what most teams build) | **7** |
| **Sentinel** (score only at high-stakes moments) | **0** |

The **7** is a measurement, recorded from a real browser run in commit `e7b9f34`. What the
automated test pins is the *comparison* — Sentinel exactly 0, naive strictly greater than
0 — deliberately, so that a change to the demo audio makes the test fail honestly instead
of failing on a hard-coded 7. **If a judge asks "is the 7 locked down?", the answer is:
the zero is, and the gap is; the exact 7 is a reading from one call, not a law.**

## 6.3 The offline failure that would have killed the live demo

We wrote a test that blocks every outbound network connection and then runs the whole
system. First run found it: with no network, three separate libraries each tried to reach
the internet before falling back to their local copies — three retry-and-backoff
sequences that **stalled model loading for minutes instead of the usual ~13 seconds.**

**A demo laptop with the venue WiFi genuinely switched off would have hit this on stage.**
Fixed by forcing offline mode before each loader.

## 6.4 Latency: measured, not claimed

From the end of a trigger phrase to a verdict on screen, 10 runs:
**median 852 ms, p95 1274 ms**, against a target of under 1500 ms.
The raw samples are stored, not just the summary (`prototype/artifacts/latency.json`).

## 6.5 The trigger design that didn't work — and the measurement that proved it

**This is the same story as the leaking detector, told about a different model, and it is
the second-strongest thing in this document.**

The trigger is the part that decides *when* to run deep verification — it listens to the
transcript and fires on a high-stakes instruction ("transfer two crore tonight"). The
obvious way to build it, and the way most teams will: take a sentence-embedding model
(`sentence-transformers/all-MiniLM-L6-v2`), measure how similar each spoken line is to a
list of fraud sentences, and fire above a threshold.

**We built that. Then we measured it, and it does not work.**

| What was said | Similarity to fraud sentences |
|---|---|
| High-risk paraphrases (what we want to catch) | **0.44 – 0.65** |
| Ordinary banking talk (what must stay quiet) | **0.25 – 0.61** |

The two ranges **overlap**, so no threshold exists anywhere. The clearest single pair:

- *"Please visit the branch at your convenience with the documents"* → **0.61** (harmless)
- *"Push the funds across tonight"* → **0.44** (fraud)

**The harmless sentence scores higher than the fraud one.** Any threshold either fires on
both or neither.

**Why — and this is the insight:** a general-purpose sentence encoder measures *topical
relatedness*. **Everything said on a banking call is related to banking.** The model was
answering a different question from the one we thought we were asking. Exactly the same
class of mistake as the leaking detector: a confident number that is not about the thing
you believe it is about.

**The fix — ask a comparative question instead of an absolute one.** We added a second
list: `BENIGN_ANCHORS`, the sentences a *normal* banking call contains. Then:

```
margin = similarity(nearest fraud intent) − similarity(nearest benign anchor)
```

Not *"is this like fraud?"* but *"is this **more** like fraud than like normal call
content?"* That question separates cleanly where the first one could not:

| | Margin |
|---|---|
| 15 clear positives | **+0.28 to +0.73** |
| 4 hard paraphrases | +0.08 to +0.22 |
| 15 curated negatives | **−0.59 to −0.01** |
| 12 **held-out** negatives never used for tuning | −0.30 to +0.15 |

**Analogy:** "does this smell like smoke?" fails in a kitchen, because a kitchen always
smells of something. "Does this smell *more* like smoke than like dinner?" works.

**What it buys in the demo, in one line:** *"I'll transfer you to the other line"* contains
the keyword "transfer". A keyword matcher fires on it. Ours does not — its margin is
**−0.10**, so it is closer to normal call content than to fraud, and the trigger stays
quiet. **That single sentence is the answer to "isn't this just keyword matching?"**

**And the honesty flag:** of the 12 held-out sentences, **one still misfires** — *"the
branch manager will call you back tomorrow morning"*. It is not tuned away. It is written
into the code as `KNOWN_FALSE_POSITIVES` and asserted by a test, alongside a matching
`KNOWN_MISSES` list. **We keep a written record of what our own trigger gets wrong.**

*(Reasoning and all numbers: `prototype/sentinel/trigger/engine.py` module docstring,
`prototype/sentinel/trigger/intents.py`, `prototype/config.yaml` → `trigger:`, pinned by
`prototype/tests/test_trigger.py`.)*

---

# PART 6B — EVERY MODEL WE DOWNLOADED, AND WHAT HAPPENED TO IT

You asked specifically about the models. There are five. **One of them we threw away** —
that is the story in Part 2. The other four are in the shipping system.

| # | Model | Job | Verdict |
|---|---|---|---|
| 1 | `Gustking/wav2vec2-large-xlsr-deepfake-audio-classification` | Off-the-shelf fake-detector | ❌ **DISCARDED.** Had memorised the benchmark. Kept in the repo as a documented cautionary tale (`detector/src/cm_model.py`), never used for a reported number. |
| 2 | `facebook/wav2vec2-base` + **our own** logistic-regression head | The replacement fake-detector | ✅ Task-naive backbone; we trained the head ourselves on a speaker-disjoint fit set. Produces the 7.9 / 13.5 / 11.7 numbers. |
| 3 | **Resemblyzer** voice encoder v1 | "Is this the enrolled person?" — the enrolment signal | ✅ Shipping. ⚠️ Lightweight stand-in for a production ECAPA-TDNN. **Caught returning a confident "verified" on pure silence** — see 6.1. |
| 4 | **faster-whisper `base.en`** (int8, CPU) | Transcribes the call so the trigger can read it | ✅ Shipping. Runs locally; no audio leaves the laptop. |
| 5 | `sentence-transformers/all-MiniLM-L6-v2` | Decides *when* a moment is high-stakes | ✅ Shipping — but **only after its obvious usage was measured and rejected.** See 6.5. |

**The pattern across the whole table, and the line worth saying out loud:**

> **"Of the five models in this system, we measured every one of them doing something
> confidently wrong. One we deleted. Two we had to redesign the way we ask them
> questions. That is the work."**

---

# PART 7 — HOW TO USE THIS IN THE PRESENTATION

## 7.1 The single best slide in the deck

Give the trap its own slide. Suggested title:

> ### We got a perfect score. We threw it away.

Three beats, nothing more:

1. **We downloaded a free deepfake detector and tested it. It scored 0% error — perfect,
   even on damaged phone audio.**
2. **We checked why. Every genuine clip got nearly the same score — std 0.003. The model
   wasn't listening to the audio; it had memorised the test.**
3. **We threw the whole model away, rebuilt the experiment so leakage was structurally
   impossible, and published the honest number instead: 7.9% / 13.5% / 11.7%.**

Closing line to say out loud:

> **"Most teams in this hall will download that same detector, get that same perfect
> number, and put it on a slide. We don't trust a number until we've tried to break it."**

**Why this wins:** it converts a *weaker* number into a *credibility* advantage. Any team
can claim 99%. Almost none can show the moment they refused a number that flattered them.

## 7.2 The three-bar chart (already specified in `PPT-CONTENT.md`)

```
Clean audio             7.9%   (blue)
After a phone line     13.5%   (red)
+ Enrolled reference   11.7%   (green)
```
Caption: *Our own pilot, 23 Aug 2026 · leak-free protocol, speaker-disjoint split,
n=119 trials.*

Narrate it in one sentence: **"the line hurts, and enrolment claws back a third of the
damage — using the crudest possible way of combining the signals."**

## 7.3 Lines that are ready to say

- *"Our accuracy number isn't the product. The architecture around the number is."*
- *"7.9% clean, 13.5% through a phone line. That second number is the one that's real,
  and it's the one nobody demos."*
- *"We built the exam hall so a student who'd seen the paper couldn't sit the test — and
  that's asserted in code, not promised in a README."*
- *"Both of our models will confidently analyse pure silence. We know, because we checked.
  That's why the voice-activity gate comes first instead of being a filter afterward."*
- *"Naive scoring: 7 false alarms on a genuine call. Ours: zero. Same audio, same models."*
- *"'Please visit the branch at your convenience' scores 0.61 for fraud. 'Push the funds
  across tonight' scores 0.44. The harmless sentence scores higher. That's why we don't
  use a similarity threshold — we ask whether it's closer to fraud than to normal talk."*
- *"Ask a keyword matcher about 'I'll transfer you to the other line' and it fires. Ours
  doesn't — margin minus 0.10. That one sentence is our answer to 'isn't this just
  keyword matching?'"*
- *"We keep a written list of the sentences our own trigger gets wrong, asserted by a
  test. One in twelve held-out negatives still misfires. We didn't tune it away."*

## 7.4 Questions you will get, and the answers

**"119 trials is statistically meaningless."**
> Agreed, and it's on the slide. It's a mechanism proof — does the number move in the
> predicted direction, roughly how much — not a publication-grade estimate. The full-scale
> run on 71,000 utterances is scripted and queued. We'd rather show a small honest
> experiment than a big unchecked claim.

**"11.7% error means 1 in 9 is wrong. That's useless in a bank."**
> It would be, if we ran on every call and auto-blocked. We do neither. We run at a tiny
> fraction of moments — the transfer instruction — and our output is *"recommend a
> call-back,"* not *"this person is a fraudster."* **The cost of our error is a 30-second
> call-back, not a blocked CEO.**

**"You claim enrolment gives 10–20×, but your own experiment went 13.5 → 11.7."** ⚠️ *sharpest question*
> Two different things, and we're careful never to blend them. The 10–20× is published
> literature. Our 13.5 → 11.7 is our own pilot using a **plain unweighted average of the
> two scores**, because at pilot scale we had no held-out data to learn fusion weights
> from. That's deliberately pessimistic. **The direction is confirmed; the magnitude is
> not yet ours to claim.**

**"Pindrop claims 99%. Why is yours worse?"**
> 99% is self-reported on their own data; independent testing puts real performance at
> 60–75% on live VoIP. The best systems in ASVspoof 5 sit at 9–20% under honest
> conditions. **Ours isn't worse — it's measured differently. We quote a hard test; they
> quote a marketing figure.**

**"You tested on English data."**
> Correct, and it's our biggest open gap. It's why we chose a multilingual speech model
> and why the Indian-language dataset is in the plan. **We are not claiming
> Indian-language performance today.** We're claiming a design that can get there and a
> schedule to prove it.

## 7.5 Things you must NOT say

- ❌ Do not quote the v1 numbers (0% EER) as anything except the cautionary tale.
- ❌ Do not present the 10–20× literature figure as our result. Ours is 13.5 → 11.7.
- ❌ Do not claim Indian-language performance. We have not measured it.
- ❌ Do not say "99% accurate" about anything. That phrase is the tell of a team that
  hasn't tested honestly, and a technical judge will hear it that way.
- ❌ Do not describe the full-scale Kaggle run as *done*. It is **written and queued.**

---

# PART 8 — BLUNT ASSESSMENT: WHERE THIS IS WEAK

You asked for no sugarcoating, so:

1. **The full-scale Kaggle run has not been executed.** The notebook is written, the
   runbook is written, `full_results.json` does not exist anywhere in this repository.
   **This is the biggest hole in the story and the highest-value thing anyone on the team
   can go do — it's free, takes ~10 minutes of active effort plus an hour of waiting, and
   it upgrades every number in the deck.** If a judge asks "why didn't you just run it?",
   there is no good answer other than "we're running it."
2. **119 trials is genuinely small.** A handful of flipped trials moves these numbers by
   several points. Say so before a judge says it for you — volunteering the limitation
   is what makes the rest of the deck credible.
3. **English-only benchmark.** ASVspoof2019 LA. The Indian-language work is planned, not
   done.
4. **117 training examples is thin** for the probe. Fit-set accuracy was 94%, fine for a
   probe, but it's weaker than one trained on thousands.
5. **The fusion is untrained** — a 50/50 average. This is why our gain looks modest.
6. **Resemblyzer is a lightweight stand-in**, not the production-grade speaker model
   (ECAPA-TDNN) you'd actually ship.
7. **No AMR codec** in the simulator — this Mac's ffmpeg lacks a free AMR encoder
   (patent-encumbered). Opus and G.711 cover the realistic space, but AMR is what 2G/3G
   voice calls use.

**None of these sink the pitch, because every one of them is already written on the
slides.** A team that lists its own seven weaknesses reads as more competent than a team
claiming 99% — but only if you say them first, in your own words, before you're asked.

---

## Appendix — where every number in this document lives

| Claim | File |
|---|---|
| 0.0% EER, the leaking result | `detector/results/pilot_results.json`, `detector/run_experiment.log` |
| std=0.003 diagnosis + the fix reasoning | `detector/src/probe_model.py` (docstring), `detector/README.md` |
| 7.9 / 13.5 / 11.7 | `detector/results/pilot_results_v2_leakfree.json`, `detector/run_experiment_v2.log` |
| Speaker-disjointness assertion | `detector/src/run_experiment_v2.py` |
| Telephony simulator | `detector/src/channel_sim.py` |
| Decision band 0.3636 / 0.4575, 0.0pp drift check | `prototype/artifacts/calibration.json` |
| Silence bug + 0.363 → 0.317 | commit `e7b9f34`, `test_vad_silence.py`, `test_pipeline_golden.py` |
| 7 vs 0 false alarms | commit `4ca5a5a`, `test_pipeline_golden.py` |
| Offline stall | commit `59fe084`, `tests/test_offline.py` |
| Latency 852 ms / 1274 ms | `prototype/artifacts/latency.json` |
| Similarity ranges overlap (0.44–0.65 vs 0.25–0.61) | `prototype/sentinel/trigger/engine.py` (docstring), `prototype/config.yaml` → `trigger:` |
| Margins +0.28..+0.73 / −0.59..−0.01, held-out −0.30..+0.15 | `prototype/config.yaml` → `trigger:`, `prototype/tests/test_trigger.py` |
| "transfer you to the other line" margin −0.10 | `prototype/sentinel/trigger/engine.py`, `prototype/sentinel/trigger/intents.py` |
| The one admitted false positive | `intents.py` → `KNOWN_FALSE_POSITIVES`, asserted in `test_trigger.py` |
| The five-model roster | `detector/src/{cm_model,probe_model}.py`, `prototype/config.yaml` → `models:` |
| Full-scale run (written, not executed) | `detector/notebooks/kaggle_full_run.py`, `detector/KAGGLE-RUNBOOK.md` |
