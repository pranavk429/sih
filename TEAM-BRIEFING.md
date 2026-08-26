# What We're Building — Team Briefing

**SIH 2026 · PS SIH26104 · AICTE · Software · Theme: Miscellaneous**
**"AI-Powered Real-Time Detection and Prevention of Voice Cloning Impersonation Attacks"**
Idea submission deadline on the portal: **20 September 2026**. Cap: 500 teams.

Read this once, fully. After it you should be able to explain the project to
anyone and survive a hostile question. No prior AI knowledge needed.

---

## 0. The 60-second version

A criminal takes 30 seconds of your CEO's voice off YouTube, clones it with free
AI software, phones the finance officer, and says *"move ₹2 crore tonight, I'm
going into a board meeting, don't call me back."* The money leaves.

AICTE asked for software that listens to a live call and warns you if the voice
is AI-generated.

**Almost every team will build a "fake voice detector" that scores every call.
That thing does not work in the real world, and we can prove why.**

We build something different: a system that asks *"is this the specific person
we have a recording of?"* instead of *"is this audio fake?"*, and that only wakes
up when money or access is actually on the line. Same problem statement, four
changes, all four defensible with evidence.

---

## 1. The crime we're stopping

Two versions, and you should be able to tell both.

**The corporate one.** A finance officer gets a call at 6pm. It's the CEO's
voice — perfect, familiar. Urgent acquisition, funds must move tonight, don't
call back, I'm in a meeting. Every part of that is engineered: the urgency
exists *specifically to stop the victim from verifying*. The voice was cloned
from a conference talk.

**The one that hurts more.** A mother gets a call. It's her son's voice.
*"Mum, I've had an accident, I need money right now, don't tell Dad."* It costs
the criminal nothing to run this a thousand times.

Note what both have in common: **the attack works by preventing verification.**
Hold onto that — it's the whole reason our design works.

---

## 2. What AICTE actually asked for

You need to know the official document well enough to quote it. Here's what it
says, decoded.

### Background (their words, shortened)
Generative AI can clone a voice from a few seconds of audio. Attackers
impersonate CXOs and government officials to trigger fraudulent transfers and
bypass verification. Caller ID, manual call-back and "I recognise the voice" are
no longer sufficient. Attacks run over VoIP, mobile networks and enterprise
collaboration platforms.

### The problem they state
Telephony ecosystems have no AI mechanism to detect cloned or synthetic speech
*during a live call*. Existing solutions rarely analyse acoustic artifacts,
prosody and generation patterns at a granular level, and can't give an
actionable risk score **while the conversation is ongoing**.

They ask for something that is:
- real-time (they actually say "near real time" — remember that, it matters)
- privacy-preserving
- scalable across telecom and enterprise
- **multilingual, with diverse Indian accents and dialects**

### The five Key Components they list

| # | Component | What it means in plain English |
|---|---|---|
| 1 | **Multi-Layer Voice Authenticity Analysis** | (a) look for synthesis artifacts in the sound, (b) analyse rhythm/pitch/pauses, (c) **compare against historical genuine samples where available** |
| 2 | **Real-Time Risk Scoring Engine** | continuously compute a risk score; configurable thresholds; enrich with context like transaction details and call origin |
| 3 | **Alerting and User Interaction Layer** | notify staff; **recommend secondary verification** (call-back, MFA, supervisor); configurable workflows |
| 4 | **Privacy and Compliance Module** | minimal audio retention, on-device/edge inference, feature-only logging |
| 5 | **Platform and Integration APIs** | REST/gRPC APIs and SDKs for banks, contact centres, telecom; multiple Indian languages |

### Expected outcomes
Less fraud; restored trust in voice channels; early detection of AI social
engineering; a reusable security layer for telecom and enterprises.

> **Two lines in that document matter more than the rest. Highlight them:**
>
> 1. *"Cross-session consistency checks comparing ongoing call features against
>    **historical genuine samples (where available)**"* — buried in component 1c.
> 2. *"Pre-transaction warning prompts **recommending secondary verification**
>    such as call-back, multifactor authentication, or escalation."* — component 3.
>
> Line 1 is the strongest technique in the whole document, demoted to an
> optional sub-bullet. **We promote it to the main path.**
> Line 2 says the system's job is to *recommend a second check*, not to accuse
> anyone. That single line answers half the hostile questions you'll get.

---

## 3. The trap — what happens if you build exactly what's described

Four hard truths. The PS mentions none of them. **Most of the other teams will
walk straight into all four.**

### Truth 1 — The detector goes blind against new tools

Train a security guard on 1,000 fake IDs from one forger and he becomes
brilliant — 99% accurate. A *different* forger shows up with a different
technique and he's guessing.

AI voice detectors work exactly like this. They memorise the fingerprints of
the specific cloning tools they were trained on. New cloning tools appear every
month.

*Measured reality:* detectors scoring 99% on their training data fall below 80%
on cloning tools they haven't seen. This is called **generalisation failure**.

### Truth 2 — The phone line destroys the evidence

The tell-tale signs of a synthetic voice live in extremely fine sound detail —
like the difference between an original painting and a printed copy, visible
only up close.

A phone call is that painting seen through a dirty window from across the
street. Phone networks deliberately throw away sound detail to save bandwidth
(that's what a **codec** does). **The evidence we need is often exactly the
evidence the phone line deletes.**

The PS says "works over VoIP and mobile networks" but never mentions this. It's
the single most common reason lab results don't survive contact with a real call.

### Truth 3 — A "99% accurate" alarm is useless in the real world ⭐

**This is the most important idea in the project. Everyone must be able to
explain it.**

A smoke alarm that is 99% accurate sounds excellent. Install it in a building
where a real fire happens once every 5,000 days. That 1% error rate means it
screams falsely about **50 times before the one real fire.** By the third false
alarm everyone ignores it. When the real fire comes, nobody moves.

A deepfake detector at a bank has exactly this shape: attacks are rare, calls
are constant. A "99% accurate" detector running on *every* call produces roughly
**50 false accusations for every real attack caught.** Staff switch it off
within a week.

*Measured reality:* one real deployment caught 100% of deepfake calls and still
had **only 1 in 333 of its alerts be genuine.**

The name for this is the **base-rate fallacy**. Note that the PS explicitly asks
for *"continuous computation of a risk score"* — that is precisely the design
that produces this failure. We fix it.

### Truth 4 — There are two different criminals, needing two different traps

| | **The Robot Caller** (TTS) | **The Puppeteer** (voice conversion / RVC) |
|---|---|---|
| How it works | A computer generates the whole conversation | A human speaks; software converts their voice live, like a filter |
| Can call thousands at once? | ✅ Yes | ❌ No — one criminal, one call |
| Handles surprises? | ❌ Stumbles if interrupted | ✅ Perfect — a human is driving |
| Weakness we exploit | Timing is subtly wrong; can't handle interruption | Speech *habits* belong to the criminal, not the person being faked |

A system that only catches one is half a system. The PS says "cloned **or
manipulated** voices" — that word "manipulated" is the Puppeteer, and it gets
one word of attention.

---

## 4. What we build instead — the four changes

**Say this clearly and often: we did not drop anything from the problem
statement. We re-prioritised it and added what was missing.** SIH scores
"Relevance to the problem statement" at 25 marks. Never let a judge think we
went off-brief.

| | What the PS pushes you toward | What we build | Why |
|---|---|---|---|
| **1. The question** | "Is this audio fake?" | **"Is this the person we enrolled?"** | Far easier question, far lower error |
| **2. When it runs** | Continuously, on every call | **Only when money or access is at stake** | Fixes the false-alarm collapse |
| **3. What it does** | Observes and scores | **Interrupts and tests when unsure** | Delivers the word "Prevention" in the title |
| **4. What it outputs** | A confident number, always | **A decision, evidence, or an honest "not sure"** | Trustworthy, and legally defensible |

### Change 1 — Ask an easier question ⭐

Two very different questions:

- *"Is this stranger lying about who they are?"* — judge from nothing. **Very hard.**
- *"Is this my brother on the phone?"* — you've heard his voice a thousand times. **Easy.**

The PS pushes you toward the first. But look at **who criminals actually
impersonate**: CXOs and government officials — exactly the people an
organisation already knows and could record in advance, with consent.

If we hold a genuine recording of the real person, the hard question becomes
the easy one. This is called **speaker verification** (as opposed to blind
**deepfake detection**). Published research puts speaker verification roughly
**10 to 20 times more accurate** in error terms.

The PS *does* mention it — as component 1c, "(where available)". **Most teams
will skip it, because "universal deepfake detector" sounds more impressive than
"we compare against a recording."**

**It is the winning move precisely because it is the unglamorous one.**

⚠️ **Careful with this number.** The 10–20× figure comes from published
literature, not from our own experiment. Our own pilot showed a smaller gain
because we used a crude, untrained way of combining the two signals. Quote the
literature as literature and our pilot as our pilot — never mix them.

### Change 2 — Only listen when it matters

Instead of alarming on every call, the system quietly follows the conversation
and only wakes the expensive checks when something valuable appears: a transfer
instruction, a credential request, an urgent demand for approval.

This directly fixes Truth 3. And it is **not** a deviation — the PS itself says
thresholds should be *"configurable for different risk scenarios (for example,
high-value transaction calls, privileged access approvals)"* and asks for
*"contextual enrichment using... transaction context."* We are doing what it
asked for, taken seriously.

### Change 3 — Interrupt and test (this is "Prevention")

The PS title has two words in it: **Detection *and* Prevention**. Everything the
PS describes is passive — analyse, score, alert. Nothing in it ever acts.

If our verification is uncertain, the system injects an unexpected prompt into
the call and measures the response. A Robot Caller stumbles on a surprise; a
human doesn't. That's an **active liveness challenge**, and it's the step that
turns detection into prevention.

*(Honest note: this catches the Robot Caller, not the Puppeteer — a human
driving the software answers surprises fine. That's why we need Change 4 and
the two-branch design.)*

### Change 4 — Say "I'm not sure" instead of guessing

A system that knows when it doesn't know is more trustworthy than one that always
produces a confident number. It also protects us on stage: **if the live demo
hits an ambiguous case and says "not sure — escalate", that is our system
working correctly, not failing.** Rehearse saying that.

---

## 5. The system, in four layers

Learn this. It's the diagram on slides 2 and 3, and it's how you answer "what
did you actually build?"

```
1. TRIGGER      Quietly follows the conversation. Cheap, always on.
                Wakes on: transfer instruction · credential request ·
                urgency + authority pressure.
                → This is what makes the alarm trustworthy.

2. VERIFY       Do we have a genuine recording of this person?
                  YES → compare against it. Very accurate.
                  NO  → general fake-detection + honest "not sure"
                Also decides: Robot Caller or Puppeteer?

3. CHALLENGE    If suspicious: interrupt and test.
                Ask something unexpected. Measure the response.
                → This is intervention, not just observation.

4. EVIDENCE     Which exact seconds were suspicious · what kind of
                artificial artefact · a tamper-proof record.
                No raw audio stored — only mathematical fingerprints.
                → Makes it legal to deploy and defensible in court.
```

---

## 6. The proof we already have

Most teams will have zero measurements at the idea stage. We ran a real
experiment on 23 August 2026.

| Question | Result |
|---|---|
| How good is a plain detector on clean audio? | **7.9% error** |
| How much does a simulated phone line hurt it? | **13.5% error** |
| How much does comparing against a real reference help? | **11.7% error** |

Read it as: **the phone line made things about 70% worse (Truth 2 confirmed),
and having a genuine reference recording clawed back about a third of that
damage — using the crudest possible way of combining the two signals.** A
properly trained combination should recover more. That full-scale run is
scripted and waiting on a free GPU.

"Error" here is **EER (Equal Error Rate)** — one number summarising how often
the system is wrong. **Lower is better.** 5% is good, 20% is weak.

### The most valuable thing we found wasn't a number — it was a trap

Our first attempt used a free, ready-made "deepfake detector" downloaded from
the internet. It scored a suspicious **0% error on everything.**

That's not excellence, it's a red flag. We inspected the raw scores and found
the model giving nearly identical answers regardless of input — the fingerprint
of a model that had **memorised the exact test** rather than learned to detect
fakes. Its creator had almost certainly trained it on the same data we were
"testing" with.

We threw it out and rebuilt using a model that has never seen this task, with
the training and testing voices kept strictly separate — *checked in code, not
just claimed*.

**Most competing teams will download a similar detector, see a great number, and
never look closer.** This is one of the strongest things we can say out loud:
*"we don't trust a number until we've tried to break it."*

---

## 7. Coverage map — every PS component, and what we do about it

Keep this handy. If a judge says "you ignored X", find X here.

| PS component | Our answer |
|---|---|
| 1a. Acoustic/spectral artifact detection | Built — self-supervised speech model + our own trained probe |
| 1b. Prosody & behavioural analysis | Designed — rhythm/pitch/pause features; also the signal that catches the Puppeteer |
| 1c. Cross-session checks vs. genuine samples | **Built, and promoted to our primary path** |
| 2. Real-time risk scoring | Built — but *gated by the trigger* rather than run continuously, and we say why |
| 2. Contextual enrichment (transaction context) | This *is* our semantic trigger |
| 2. Configurable thresholds per scenario | Designed — the PS's own "high-value transaction" example is our trigger |
| 3. Multi-channel alerting | Designed — demo shows the operator UI path |
| 3. Recommend secondary verification | **Core to our design** — we recommend, we never auto-block |
| 3. Configurable workflows | Designed |
| 4. Minimal retention / edge inference | Built into the architecture — on-device inference, feature-only logs |
| 5. REST/gRPC APIs and SDKs | Designed — the scoring core is already a service |
| 5. Indian languages and accents | Partly — multilingual speech model chosen for this; full evaluation is the next milestone. **Say this honestly.** |

---

## 8. What we are NOT building — and why we say so out loud

Four components done properly beats fifteen done badly. Everything below is
labelled **"designed, not built"** on the slides, deliberately.

- ❌ **An app on a normal phone that listens to regular calls.** Google blocked
  apps from accessing call audio in 2019 and closed the workaround in 2022. If
  this appears on a slide, a knowledgeable judge will catch it. We work in the
  VoIP/SIP path, which we control — and the PS itself names VoIP first.
- ❌ **Claiming 99% accuracy.** It would be dishonest and, against a
  knowledgeable judge, fatal. Our honest lower number on a harder test is a
  strength. Say so.
- ❌ **Full Indian-language coverage today.** We chose a multilingual model and
  scoped the evaluation. We do not claim it's done.
- ❌ **Real telecom-operator integration.** That's a deployment partnership, not
  a hackathon deliverable.

---

## 9. Words you must be able to use

| Term | Plain English |
|---|---|
| **Model** | The trained AI that makes the judgement |
| **Training / fine-tuning** | Teaching the AI by showing it examples |
| **Dataset** | The collection of example recordings we teach with |
| **Enrolment** | A genuine recording of a real person, saved in advance to compare against |
| **Speaker verification** | "Is this the person we enrolled?" — the easy question |
| **Deepfake detection** | "Is this audio synthetic?" — the hard question |
| **False positive** | Wrongly accusing an innocent, real person |
| **False negative** | Missing an actual attack |
| **EER (Equal Error Rate)** | One number for how wrong the system is. **Lower is better.** |
| **Base-rate fallacy** | Why a 99% accurate alarm still produces mostly false alarms when attacks are rare |
| **Codec** | The compression a phone network applies, which destroys sound detail |
| **TTS (Text-to-Speech)** | The "Robot Caller" — computer reads typed text aloud |
| **Voice conversion / RVC** | The "Puppeteer" — converts a live human voice into someone else's |
| **Inference** | The AI running and making a decision (cheap) — vs training (expensive) |
| **Latency** | Delay between someone speaking and us deciding |
| **VoIP / SIP** | Phone calls over the internet. What our demo uses. |
| **Generalisation** | Whether it still works on cloning tools it never saw in training |

---

## 10. The three sentences everyone on the team must be able to say

1. *"The problem statement pushes you toward 'is this audio fake?' — an
   open-world question that is genuinely hard. We ask 'is this the person we
   enrolled?', which the literature puts at roughly 10–20 times lower error.
   The problem statement does mention enrolment — buried in one optional
   sub-bullet that most teams will skip."*

2. *"A 99%-accurate detector run on every call produces about 50 false
   accusations for every real attack, and gets switched off in a week. That's
   why we only run deep verification at high-stakes moments — which is also
   what the problem statement's own 'configurable for high-value transaction
   calls' line asks for."*

3. *"Our accuracy number is not the product. The architecture around the number
   is the product — because a 95% detector deployed naively produces 98% false
   alerts."*

---

# 11. BRUTAL Q&A

Assume the judge is smart, skeptical, and short on time. **If you don't know,
say "I don't know, here's how we'd find out" — that scores better than a
confident wrong answer, especially for us, because "we don't trust numbers we
haven't checked" is our whole story.**

---

## A. Attacking the core idea

**Q1. "Your whole system depends on having a recording of the real person.
What happens when you don't?"**
> We fall back to the general detector the PS describes, plus an honest
> low-confidence flag, plus the challenge layer. We're not worse than the
> standard approach in that case — we're the standard approach. We're
> dramatically better in the case that actually matters, because the people
> criminals impersonate — CXOs, officials, family members — are precisely the
> people you *can* enrol in advance.

**Q2. "So you've just built speaker verification. That's a 20-year-old solved
problem. What's novel?"**
> Speaker verification alone fails against a good clone — a clone is *designed*
> to match the speaker. The novelty is the **fusion**: a speaker-match score
> AND a synthesis-artifact score combined, gated by a semantic trigger, with an
> active challenge and an abstention option. Any one of those parts is old. The
> architecture, and the reasoning about *when* to run it, is the contribution.

**Q3. "If enrolment is so much better, why doesn't the industry do it?"**
> Enrolment needs consent, storage and governance — it's an operational cost,
> not a technical one, and it doesn't demo as well as a universal detector.
> Vendors sell "works on any caller" because it's easier to sell. AICTE clearly
> knew about it — it's in component 1c — but hedged it as "where available".

**Q4. "Your semantic trigger is just keyword matching. A criminal will avoid
the keywords."**
> Fair, and that's why it's an intent model over the transcript, not a keyword
> list. But take the objection seriously: to avoid triggering, the attacker must
> avoid ever asking for a transfer, a credential or an approval — which is the
> only reason they called. **Evading the trigger means abandoning the attack.**
> That's the property we designed for.

**Q5. "What if the attacker builds trust over five calls and never says
anything triggering?"**
> Then on call five they still have to ask for the thing, and that's when we
> fire. Our system is not trying to detect suspicious *conversation*, it's
> protecting the *sensitive action*. Slow-burn social engineering still has to
> pass through the same door.

**Q6. "Isn't the enrolled recording itself the attack surface? Steal it and you
have perfect cloning material."**
> Good question, and the answer is why we store **feature-only** representations,
> never raw audio — a mathematical fingerprint that can verify a voice but can't
> be played back or used to train a cloner. That's the PS's own "anonymization
> or feature-only logging" requirement, and it happens to close this hole.

---

## B. Attacking the numbers

**Q7. "11.7% error means roughly 1 in 9 is wrong. That's useless in a bank."**
> It would be, if we ran it on every call and auto-blocked. We do neither. We
> run it at a tiny fraction of moments — only at the transfer instruction — and
> our output is *"recommend a call-back"*, not *"this person is a fraudster."*
> The PS itself specifies exactly this: "pre-transaction warning prompts
> recommending secondary verification." **The cost of our error is a 30-second
> call-back, not a blocked CEO.**

**Q8. "119 trials is statistically meaningless."**
> Agreed, and we say so on the slide. It's a **mechanism proof** — does the
> number move in the predicted direction, roughly how much — not a
> publication-grade estimate. The confidence interval on 119 trials is wide. The
> full-scale run on 71,000 utterances is scripted and queued. We'd rather show a
> small honest experiment than a big unchecked claim.

**Q9. "You tested on English data. India has 22 official languages."**
> Correct, and that's our biggest open gap. It's the reason we chose a
> multilingual speech model rather than an English one, and the reason the
> Indian-language dataset is in our plan. We are not claiming Indian-language
> performance today. We're claiming a design that can get there and a schedule
> to prove it.

**Q10. "Pindrop claims 99%. Why is yours so much worse?"**
> Because 99% is self-reported on their own data. Independent testing puts real
> performance at 60–75% on live VoIP calls. The best systems in the world's
> leading academic challenge (ASVspoof 5) sit at 9–20% error under honest
> conditions. **Our number isn't worse than theirs — it's measured differently.
> We're quoting a hard test; they're quoting a marketing figure.**

**Q11. "You said enrolment gives 10–20× improvement, but your own experiment
went from 13.5% to 11.7%. That's not 10×. Explain."** ⚠️ *(the sharpest question
you'll get — know this one cold)*
> Two different things. The 10–20× figure is from published literature comparing
> speaker verification to blind detection under proper conditions. Our 13.5→11.7
> is our own pilot using the **crudest possible fusion — a plain average of the
> two scores, with no training on how to weight them** — because we had no
> held-out data to learn the weights on at pilot scale. That's a deliberately
> pessimistic estimate. The direction is confirmed; the magnitude is not yet
> ours to claim. The full-scale run trains a real combiner. We are careful not
> to present the literature number as our result.

**Q12. "Your detector got 0% error at first and you threw it away. Why should we
believe your second number?"**
> Because of exactly *how* we threw it away. We inspected the raw scores, saw
> near-zero variance — the fingerprint of memorisation — and rebuilt with a
> model that has never seen this task, with training and test voices strictly
> separated and the separation **asserted in code**. The first number was a
> lesson in why free checkpoints can't be trusted. The second was built to
> survive that lesson.

---

## C. Attacking feasibility

**Q13. "Real-time means real-time. What's your latency?"**
> Our target is a decision within about a second of the triggering phrase, which
> is well within the window before a human acts on an instruction. Note the PS
> itself says "**near** real time". We're honest that the trigger layer runs
> continuously and cheaply, and the expensive verification runs in bursts —
> that's what makes the latency budget achievable at all.

**Q14. "Android blocks call-audio capture. So this never ships."**
> Correct for consumer phone calls, and we say so on slide 3 rather than hiding
> it. That's why we target the **VoIP/SIP and enterprise-platform path** — which
> is the first channel the PS names, and where banks, contact centres and
> government actually run their high-value approval calls. We're not pretending
> to a capability the platform forbids.

**Q15. "Six students, no GPU budget. Google has thousands of engineers. Why
hasn't this been solved?"**
> It hasn't been solved because it's an *arms race*, not a puzzle — every new
> cloning tool resets a blind detector. Our answer isn't more compute, it's a
> better question: enrolment-based verification doesn't degrade when a new
> cloning tool appears, because we're not trying to recognise the tool. That's a
> design advantage, not a compute advantage.

**Q16. "What's the business model? Who pays?"**
> Banks and enterprises, per-seat or per-call, on the fraud-prevention budget
> they already have — the ROI case is one prevented transfer. The PS asks for a
> "reusable security layer for telecom operators and enterprises", which is
> exactly that shape. For individuals, the same engine runs on-device.

**Q17. "Your demo needs the internet. Venue WiFi will be dead."**
> It doesn't. Everything runs locally on one 16 GB laptop — that was a hard
> design constraint from day one, precisely because venue networks fail. We can
> unplug the network and run the demo. Ask us to.

---

## D. Attacking privacy, ethics and law

**Q18. "You're storing people's voices. Isn't that a DPDP Act nightmare?"**
> We store mathematical feature representations, not audio. They can verify a
> voice but can't be played back. Inference runs on-device or at the edge so
> audio doesn't travel to a datacentre. Enrolment is explicit, consented and
> revocable. This maps directly to the PS's Privacy and Compliance Module.

**Q19. "What happens when you falsely flag a real CEO and block a legitimate
₹2 crore transfer?"**
> We never block. Our output is a recommendation to verify by a second channel —
> the PS's own words are "recommending secondary verification such as call-back,
> multifactor authentication, or escalation to supervisors." **The worst case of
> a false positive is a 30-second call-back.** Designing it that way is what
> makes an imperfect detector deployable.

**Q20. "Could this be used to surveil employees?"**
> The trigger design limits it: the system is deliberately deaf until a
> high-stakes phrase appears, and it retains features rather than content. A
> continuous-scoring design — the one the PS literally describes — would be far
> more invasive. Our change reduces the surveillance surface as a side effect.

**Q21. "Who enrols? What if the CEO refuses?"**
> Then that person falls back to the general detector path with lower
> confidence, and the workflow escalates more often. Enrolment is an
> organisational policy decision. Our system degrades gracefully rather than
> breaking.

---

## E. Attacking the technology

**Q22. "You said voice conversion defeats liveness tests. So how do you catch
the Puppeteer?"**
> Not with liveness — a human handles surprises fine. We catch it on **speech
> habits**: rhythm, pausing, filler patterns and prosody belong to the criminal
> driving the software, not to the person being impersonated. Voice conversion
> changes the timbre, not the behaviour. That's why the two branches use
> different signals, and it's why a single-detector design is half a system.

**Q23. "What if the attacker knows your system exists and adapts?"**
> Some parts are adaptable-around, some aren't. They can try to sound less
> urgent — but they still have to ask for the transfer, which is what triggers
> us. They can improve the clone's audio — but that doesn't help against an
> enrolled-reference check, because the clone still isn't the enrolled person's
> actual voice production. The trigger and the enrolment path are the hardest
> parts to evade, which is why they're the two things we made central.

**Q24. "Watermarking is coming. Won't that make your work obsolete?"**
> Watermarks only cover cooperative generators — a criminal will use a model
> that doesn't watermark. Worse, there's published work ("The Watermark
> Shortcut") showing detectors trained on watermarked data learn to detect the
> *watermark* rather than the fake, and then collapse on unwatermarked attacks.
> We actively screen for that contamination.

**Q25. "Why this model and not a bigger one?"**
> Because it has to run on-device for the privacy requirement, and because a
> bigger model that has already seen the benchmark is worse than a smaller one
> that hasn't. We deliberately chose a **task-naive** backbone — one that has
> never seen a spoof/genuine label — so our results can't be contaminated.

---

## F. Attacking scope and the team

**Q26. "The PS lists five components with fifteen sub-parts. You built four
things. Why score you well?"**
> Because we built the four that carry the risk, measured them, and clearly
> labelled the rest as designed rather than claimed. Anyone can put fifteen
> boxes on a slide. We'd rather show you three real numbers and tell you which
> parts we haven't proven yet. *(Then point at the coverage map in section 7.)*

**Q27. "What did you actually build versus download?"**
> Downloaded: the speech encoder and the speaker-embedding model — standard,
> openly licensed. Built: the leak-free evaluation harness, the telephony
> channel simulator, the trigger layer, the fusion scoring, and the evidence
> pipeline. Also built: the check that caught a popular public detector cheating.

**Q28. "This is a lot of theory. Show me it working."**
> *(Depends on prototype status — see the plan. If you have it: run it. If not:)*
> Today we can show you the experiment, the code and the results. The live
> pipeline is scheduled for [date]. We chose to measure before we demo, because
> a demo that only works on one rehearsed clip is worth less than a number that
> survives a hard test.

**Q29. "What's the single biggest weakness of your approach?"** *(Answer this
honestly — dodging it is worse than the weakness.)*
> Coverage. Enrolment only protects people who have been enrolled. For a
> completely unknown caller we're back to the hard problem with everyone else.
> We think that's the right trade, because the high-value attacks target known
> individuals — but it is a real limitation and we don't hide it.

**Q30. "If I gave you six more months and a budget, what would you do first?"**
> Indian-language evaluation at scale, and a live pilot with a real contact
> centre to measure the false-alarm rate on genuine traffic — because that's the
> number that decides whether the system survives contact with real operators,
> and it's the one number no lab test can give us.

---

## Final note

The reason this project is strong is not that we found a cleverer algorithm.
It's that we **read the problem statement more carefully than the people who
will compete against us**, noticed the strongest technique had been demoted to
an optional sub-bullet, noticed that "continuous risk scoring" is a trap, and
noticed that the title says *Prevention* and the body only describes *Detection*.

Then we checked our own work hard enough to catch ourselves being fooled once.

That's the story. Tell it in that order.
