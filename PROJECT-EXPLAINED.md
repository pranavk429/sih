# The Project, Explained Simply

**SIH 2026 — AI-Powered Real-Time Detection and Prevention of Voice Cloning Impersonation Attacks**

A plain-language reference. No jargon. Come back to this whenever you need clarity.
Last updated: 23 August 2026

---

## 1. The crime we're stopping

A criminal finds 30 seconds of your CEO's voice — a YouTube interview, a conference
talk, a WhatsApp voice note. They feed it into AI software. Now they can make that
voice say anything they type.

They call the finance officer at 6pm:

> *"This is me. I need ₹2 crore moved to this account tonight — the acquisition is
> closing. I'm going into a board meeting, don't call me back."*

The voice is perfect. The urgency is deliberate — it exists to stop the victim from
verifying. The money leaves.

The same crime, smaller and more common: a criminal clones a college student's voice
and calls their mother. *"Mum, I've had an accident, I need money right now, don't
tell Dad."*

---

## 2. What the government asked for

Software that listens to a phone call **while it is happening** and warns you if the
voice is AI-generated.

That's it. That's the problem statement. It sounds simple.

---

## 3. Four hard truths the problem statement doesn't mention

These are the reasons this is genuinely difficult, and the reasons most teams will
build something that doesn't work.

### Truth 1 — The detector goes blind against new tools

Imagine training a security guard to spot fake ID cards. You show him 1,000 fakes
made by one forger. He becomes brilliant — 99% accurate. Then a **different** forger
arrives with a different technique, and he's basically guessing.

AI voice detectors work exactly like this. They memorise the fingerprints of the
specific AI tools they were trained on. A new voice-cloning tool appears → the
detector fails. New tools appear every month.

*Measured reality: detectors scoring 99% on their training data drop to worse than
80% on voices they haven't seen before.*

### Truth 2 — The phone line destroys the evidence

The tell-tale signs of a fake voice live in extremely fine sound detail — like the
difference between an original painting and a printed copy, visible only up close.

A phone call is like viewing that painting through a dirty window from across the
street. Phone networks deliberately throw away most sound detail to save bandwidth.
**The evidence we need is often exactly the evidence the phone line deletes.**

### Truth 3 — A "99% accurate" alarm is useless in the real world ⭐

**This is the most important idea in the whole project.**

Picture a smoke alarm that is 99% accurate. Sounds excellent. Now install it in a
building where a real fire happens once every 5,000 days. That 1% error rate means
it screams falsely about **50 times before the one real fire**. By the third false
alarm, everyone ignores it. When the real fire comes, nobody moves.

A deepfake detector at a bank has exactly this shape. Real attacks are rare; calls
are constant. A "99% accurate" detector running on every call produces roughly
**50 false accusations for every real attack caught.** Staff switch it off within
a week.

*Measured reality: one real-world study found a system that caught 100% of deepfake
calls still had only 1 in 333 of its alerts be a genuine attack.*

**Almost every competing team will build exactly this useless thing**, because the
problem statement never mentions this and "99% accuracy" sounds like winning.

### Truth 4 — There are two different criminals, needing two different traps

| | **The Robot Caller** | **The Puppeteer** |
|---|---|---|
| How it works | A computer generates the whole conversation | A human speaks; software converts their voice live, like a filter |
| Can call thousands at once? | ✅ Yes | ❌ No — one criminal, one call |
| Holds a natural conversation? | ❌ Stumbles if interrupted or surprised | ✅ Perfect — a human is driving |
| Weakness we exploit | Response timing is subtly wrong; can't handle interruption | Speech *habits* belong to the criminal, not the person being faked |

You need both traps. A system that only catches one is half a system.

---

## 4. What we are building that the description didn't ask for

| | Description asks for | We are building |
|---|---|---|
| **The question** | "Is this voice fake?" | **"Is this the person we know?"** |
| **When it runs** | On every call, always | **Only when money or access is at stake** |
| **What it outputs** | A risk score | **A decision + evidence + "I'm not sure"** |
| **Threat model** | "AI-generated voices" | **Two criminal types, trapped differently** |

### Change 1 — Ask an easier question ⭐

Two very different questions:

- *"Is this stranger lying about who they are?"* — judge from nothing. **Very hard.**
- *"Is this my brother on the phone?"* — you've heard his voice a thousand times. **Easy.**

The description pushes us toward the first. But look at who criminals actually
impersonate: **CEOs and government officials** — exactly the people an organisation
already knows and could record in advance, with permission.

If we hold a genuine recording of the real person, the hard question becomes the easy
one. Published research puts this at roughly **10 to 20 times more accurate.**

The description does mention this — in one small buried line, phrased as optional.
Most teams will skip it because "universal deepfake detector" sounds more impressive
than "we compare against a recording."

**It is the winning move precisely because it is the unglamorous one.**

### Change 2 — Only listen when it matters

Instead of alarming on every call, the system quietly follows the conversation and
only wakes the serious checks when something valuable appears: a transfer instruction,
a password request, an urgent demand for approval.

This fixes the smoke-alarm problem, and it's the only way to deliver the word
**"Prevention"** in the title of the problem statement. Everyone else will build
Detection and hope nobody notices the title had two words in it.

### Change 3 — Catch both criminal types
### Change 4 — Say "I'm not sure" instead of guessing

A system that knows when it doesn't know is far more trustworthy than one that always
produces a confident number. It also protects us: if the live demo hits an ambiguous
case, that is our system **working correctly**, not failing.

---

## 5. How the system works — four layers

```
1. TRIGGER      Quietly follows the conversation. Cheap, always on.
                Wakes up on: transfer instruction · password request ·
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

## 6. The money

**Total realistic budget: ₹0 to ₹10,000.**

The expensive part of AI is training giant models from scratch. We are not doing that.
We take free, pre-built models and teach them one extra skill — like hiring an
experienced chef and teaching them one recipe, rather than raising a chef from birth.

| Item | Realistic | Ceiling |
|---|---|---|
| Computing power (GPU) | ₹0 | ₹5,000 |
| Voice-cloning tools (for our attack demo) | ₹0 — open source | ₹1,100 |
| AI service subscriptions | ₹0 — everything runs locally | ₹1,800 |
| Storage for datasets | ₹0 | ₹6,000 |
| Travel WiFi router for demo reliability | ₹0 | ₹2,000 |

**Free computing options, best first:**

1. **IndiaAI Compute Portal** (compute.indiaai.gov.in) — government-subsidised,
   ~₹65/hr, auto-approves up to 5,000 hours for students. We need ~150.
   *Bonus: "built on IndiaAI Mission compute" is itself a good line for the pitch.*
2. **Kaggle** — 30 free hours every week, no card needed. Covers us entirely.
3. **Modal** — $30 free credits, renewed monthly.
4. Paid backup: JarvisLabs ₹41/hr or E2E Networks ₹49/hr (Indian, UPI, no forex fees).

### ⚠️ The constraint that isn't money

**The demo must work with the internet unplugged.**

At the Grand Finale, hundreds of teams share one venue network. It will be slow or
down. If any part of the demo calls an online service, the demo can die on stage and
cannot be fixed in the moment.

So everything runs on our own laptop. This is cheaper *and* safer.

**Only real hardware requirement: one laptop with 16GB RAM.**

---

## 7. Things that are impossible — kill these ideas early

- ❌ **An app on a normal phone that listens to regular calls.** Google blocked apps
  from accessing call audio in 2019 and banned the workaround in 2022. If this
  appears on a slide, a judge will catch it. Our demo uses internet calling
  (VoIP), which we fully control.
- ❌ **Claiming 99% accuracy.** It would be dishonest, and against a knowledgeable
  judge it's fatal. Our honest, lower number on a harder test is a strength.
- ❌ **Building all 15 components in the description.** Four done properly beats
  fifteen done badly. Everything else becomes an architecture slide, clearly
  labelled "designed, not built" — which judges respect.

---

## 8. Glossary — words you'll hear me use

| Term | What it means in plain English |
|---|---|
| **Model** | The trained AI that makes the judgement |
| **Training / fine-tuning** | Teaching the AI by showing it examples |
| **Dataset** | The collection of example recordings we teach with |
| **Enrolment** | A genuine recording of a real person, saved in advance to compare against |
| **False positive** | Wrongly accusing an innocent, real person |
| **False negative** | Missing an actual attack |
| **EER (Equal Error Rate)** | One number summarising error. **Lower is better.** 5% is good; 20% is weak. |
| **Codec** | The compression a phone network applies, which destroys sound detail |
| **TTS (Text-to-Speech)** | The "Robot Caller" — computer reads typed text aloud |
| **Voice conversion / RVC** | The "Puppeteer" — converts a live human voice into someone else's |
| **Inference** | The AI actually running and making a decision (cheap) — as opposed to training (expensive) |
| **Latency** | Delay. How long between someone speaking and us deciding. |
| **VoIP / SIP** | Phone calls over the internet. What our demo uses. |

---

## 9. Numbers worth memorising for the pitch

- Detectors drop from **<1% error on lab data to over 20% on real-world audio**
- Best systems in the world's leading competition (ASVspoof 5): **9–20% error**
- Pindrop, the market leader, advertises 99% — but that figure is **self-reported**,
  and third-party reporting puts real performance at **60–75% on live VoIP calls**
- Comparing against a genuine enrolled recording: **error drops below 1%**
- A perfect detector in one real deployment still had **only 1 in 333 alerts be real**

**The one-line thesis:**

> *"Our accuracy number isn't the product. The architecture around the number is the
> product — because a 95% detector deployed naively produces 98% false alerts."*

---

## 10. Our own first experiment (23 Aug 2026 — pilot scale, on a laptop, no GPU)

We ran the actual three-number test described above, for real, on a small slice of
data, to prove the mechanism works before scaling it up on Kaggle.

| Question | Result |
|---|---|
| How good is a plain detector on clean audio? | **7.9% error** |
| How much does a simulated phone line hurt it? | **13.5% error** |
| How much does comparing against a real reference recording help? | **11.7% error** |

Read as: the phone line made things about 70% worse, and having a genuine reference
recording clawed back roughly a third of that damage — even using the crudest
possible way of combining the two signals. A properly trained combination (the
Kaggle run) should recover more.

**The most valuable thing this test found wasn't a number — it was a trap.**

Our first attempt used a free, ready-made "deepfake detector" downloaded from the
internet. It scored a suspicious **0% error on everything.** That's not excellence —
it's a red flag. We checked the raw scores and found the detector was giving nearly
identical answers regardless of the input, which is the fingerprint of a model that
had already memorised the exact test we were giving it, rather than one that had
actually learned to detect fakes. Its creator had almost certainly trained it on the
same data we were "testing" it with.

**We only caught this because we checked.** Most competing teams will download a
similar ready-made detector, see a great number, and never look closer. This is a
genuinely strong thing to say at the finale: *"we don't trust a number until we've
tried to break it."*
