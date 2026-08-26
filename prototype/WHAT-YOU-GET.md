# What the prototype gives you — plain language

For Pranav. No jargon. If a word needs explaining, it gets explained.

---

## 1. The one-paragraph version

The prototype is **the plumbing, not the brain**. It builds the whole machine —
audio comes in, a transcript appears, the trigger fires, the voice gets checked,
a verdict comes out with evidence — using the detector we already have, which is
decent but not great. **Fine-tuning is a completely separate job that makes the
brain better.** The clever part of the design is that these two jobs don't touch
each other: when the better brain is ready, it drops into the finished machine
by replacing two files. Nothing gets rebuilt.

---

## 2. What "prototype" covers, and what it doesn't

| Part of the system | Prototype | Notes |
|---|---|---|
| Audio streaming in, live | ✅ Built | From a recorded call, played at real speed |
| Live transcript on screen | ✅ Built | |
| TRIGGER — spotting the dangerous moment | ✅ Built | Understands meaning, not just keywords |
| VERIFY — enrolled voice match | ✅ Built | This is our main path |
| VERIFY — synthetic artifact detection | ✅ Built | Uses today's detector, not a fine-tuned one |
| Combining the two scores | ✅ Built | Crudely for now; properly after the Kaggle run |
| "Not sure — escalate" | ✅ Built | A real outcome, not an error |
| CHALLENGE — interrupt and test | ⚠️ Scripted | Shown on screen, clearly labelled as scripted |
| EVIDENCE — timestamps, scores, tamper-proof log | ✅ Built | |
| Privacy — no audio stored, only fingerprints | ✅ Built | With a test that proves it |
| Runs with the internet off | ✅ Built | Tested with WiFi physically off |
| **Naive-vs-ours comparison on screen** | ✅ Built | See §3 — this is the best part |
| Better detector accuracy | ❌ Fine-tuning | Separate track |
| Indian languages | ❌ Later | Needs the multilingual evaluation |
| Real phone/SIP calls | ❌ Later | Days of setup, breaks on venue WiFi |
| Telling apart robot-caller vs puppeteer | ❌ Later | Needs training data we don't have |
| Rhythm/pausing analysis | ❌ Later | Designed, not built. We say so. |

**The honest label:** we call it a *"simulated live call"* — a recorded call
streamed through the system in real time, exactly the way a live one would
arrive. Never call it a live phone call. If a judge asks, we want to have said
it first.

---

## 3. The feature that wins the argument

There's a toggle on screen with two settings:

- **Naive mode** — score every second of every call, the way the problem
  statement literally describes
- **Sentinel mode** — our design, which stays quiet until money is on the line

Play a **genuine, innocent call** in naive mode and a false-alarm counter starts
climbing on screen. Same call in Sentinel mode: the counter stays at **zero**.

That's the smoke-alarm argument — our single strongest point — turned from a
claim on a slide into something a judge *watches happen in front of them*. No
competing team will have thought about this, let alone shown it.

I've marked it as a required feature, not a nice-to-have.

---

## 4. What fine-tuning actually is

### What we have right now

Two pieces stacked on top of each other:

**A borrowed ear.** An AI that has listened to thousands of hours of speech and
learned what human speech *sounds like*. Crucially, **nobody ever told it which
recordings were fake.** It has no opinion about fakes at all. We chose it that
way deliberately — a model that had already studied fakes might have secretly
memorised the exact test we planned to give it. (That's the trap we caught
ourselves in, the "0% error" story.)

**A tiny judge.** A very simple decision-maker we trained ourselves, on **117
examples**, that listens to what the ear reports and says "fake" or "genuine".

Think of it as: we hired someone with extraordinary hearing who has never
studied forgery, then showed them 117 forged recordings the night before the
exam. They do okay. They are not great.

### What fine-tuning changes

Instead of leaving the ear untouched and only training the tiny judge, we let
**the ear itself change** while showing it tens of thousands of examples —
including recordings we deliberately damage first so they sound like they came
down a bad phone line.

Same analogy: instead of a 117-example crash course the night before, we send
the person with the extraordinary hearing to forgery school for a year, with
25,000 examples, and we make sure most of what they hear is played through a
terrible phone connection — because that's how they'll hear it on the job.

---

## 5. What we expect fine-tuning to actually deliver

"Error" below is **EER** — one number for how often the system is wrong.
**Lower is better.** 5% is good, 20% is weak.

| Stage | What it is | Error on phone-quality audio |
|---|---|---|
| **Now** — our pilot | Frozen ear + tiny judge (117 examples), crude score combining | **11.7%** ← measured, ours |
| **Kaggle full run** (already scripted) | Same ear, judge trained on ~25,000 examples, combining properly trained | expect **7–10%** |
| **After real fine-tuning** | Ear itself retrained, with phone-damage training | expect **4–7%** |
| Same model, on a **cloning tool it has never heard** | — | often falls back to **10–20%** |
| **Enrolment path** (person is on file) | Voice matching does the heavy lifting | **this is the number that stays low** |

> ⚠️ **The middle two rows are expectations based on published research on
> similar setups. They are not promises, and you must not present them as our
> results.** Only the 11.7% is ours. If a judge asks what we expect, say
> "we expect", and say why.

---

## 6. The thing fine-tuning cannot fix — and why that's the whole point

Look at row four in that table. A fine-tuned detector gets much better at the
fakes it studied, and **only slightly better at fakes made by a tool it has
never encountered.** New cloning tools appear every month. That gap never
closes. It's the security-guard-and-the-new-forger problem.

So here's the thing to understand, and it's the core of our whole pitch:

> **Fine-tuning makes our backup plan better. It doesn't make our main plan
> necessary.**

Our main plan — *"is this the person we have a recording of?"* — doesn't care
which cloning tool made the fake, because we're not trying to recognise the
tool. We're recognising the **person**. That path doesn't degrade when a new
tool appears.

Everyone else is betting their whole project on the row that has a wall in front
of it. We're betting on the row that doesn't.

---

## 7. What fine-tuning costs

| | |
|---|---|
| **Money** | ₹0. Kaggle gives 30 GPU-hours free every week. IndiaAI Compute Portal is the backup. |
| **The full-scale run already queued** | ~1 hour of computer time. This is the Kaggle job in the runbook. |
| **Actual fine-tuning** | 6–15 hours of computer time per attempt, and you need 3–5 attempts to get it right |
| **Calendar time** | 2–3 weeks of evenings — and it's mostly *waiting*, not working |
| **Who's needed** | One person to start jobs and report numbers back. Not a full-time job. |

---

## 8. Why the two tracks don't collide

This is the part worth understanding, because it's why the plan is safe.

The prototype touches the detector in exactly **two files**:

- one holding the trained judge
- one holding the thresholds and a record of where they came from

That's it. When fine-tuning finishes, someone replaces those two files and the
whole machine is instantly better. **No code changes. No rebuild. No risk.**

Which means the prototype build and the fine-tuning work can run **at the same
time, by different people, without ever blocking each other.**

I designed it that way on purpose. It's also the honest answer to *"how would
this scale?"* — because the same seam is how a real product would ship model
updates.

There's one more nice consequence: every verdict the system produces records
*which* version of the detector made it. So if we improve the model and a number
changes, we can always say exactly why. That's what keeps us honest as the
project grows.

---

## 9. The order things should happen

1. **This week** — finish and submit the presentation. Nothing else.
2. **Today, in parallel** — one person runs the Kaggle job (10 minutes of
   clicking, then it runs itself). That upgrades slide 4's number and costs
   nobody any real time.
3. **Day after the college round** — start the 4-day prototype build. It does
   **not** need fine-tuning to be finished, and it does not need to wait for
   anything.
4. **Around 2 September** — a screenshot goes onto slide 3 of the portal
   submission, well before the 20 September deadline.
5. **September evenings** — fine-tuning, in the background, by one person.
6. **December finale** — you arrive with a working system and a better brain,
   while most teams arrive with slides.

---

## 10. What to say if someone asks "is it real?"

> *"It's a working vertical slice — the whole path from audio to verdict, running
> live, on a real audio stream, offline. The detector inside it is our pilot
> model, not a fine-tuned one, and we'll tell you exactly what that costs us in
> accuracy. What we're showing you is that the architecture works end to end —
> including the part nobody else has thought about, which is knowing when to
> stay quiet."*

That answer is true, it's specific, and it's stronger than claiming more.
