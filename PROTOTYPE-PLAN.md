# Can we build a working prototype in 4 days?

**Short answer: yes — but not the thing you're probably picturing, and not
before the college round.**

Read the three sections below and then decide.

---

## 1. What 4 days actually buys you

### ✅ Realistic — high confidence

A **vertical slice**: one complete path through all four layers, running
end-to-end on a real audio stream, on one laptop, with the internet unplugged.

On screen, a judge would see:

- A call playing, with a **live transcript** appearing as it's spoken
- The system sitting quietly — deliberately doing nothing expensive
- The moment the caller says *"transfer two crore to this account tonight"*,
  the **TRIGGER fires** and lights up on screen
- Deep **VERIFY** kicks in: enrolled-voice match score + synthesis-artifact
  score, computed on a rolling 3-second window
- A **risk timeline** filling in live
- A **verdict panel** landing on one of three states:
  `VERIFIED` · `NOT SURE — ESCALATE` · `LIKELY IMPERSONATION`
- An **EVIDENCE panel**: which exact seconds were suspicious, the scores, and
  the recommended action (*"call back on the registered number"*)

Then you run it a second time with the cloned voice of the same speaker and it
lands on a different verdict. **That's the demo.**

### ❌ Not realistic in 4 days — don't promise these

| Thing | Why not |
|---|---|
| A real phone call over SIP/Asterisk | Telephony stack setup alone eats a full day, and venue networks break it |
| Fine-tuned / trained models | Needs the Kaggle GPU run first, then iteration cycles. Weeks, not days. |
| Real TTS-vs-RVC two-branch classification | Needs training data we don't have yet |
| Indian-language support | Needs the multilingual evaluation we've scoped but not run |
| Sub-second guaranteed latency | We can measure latency, not guarantee it |
| Real prosody/behavioural analysis | Designed, not buildable in the window |

### ⚠️ The honest label

Call it a **"simulated live call"**: we stream a recorded call through the
pipeline in real time, exactly the way a live stream would arrive. That is
honest and judges accept it without blinking.

**Never call it a live phone call.** If a judge asks "is this a real call?" and
the answer is no, you want to have said so first.

---

## 2. Why 4 days is enough — most of it already exists

This isn't a from-scratch build. The scoring core is already written and tested
in `detector/src/`:

| Already built | What it does |
|---|---|
| `probe_model.py` | Speech encoder + our own trained artifact detector |
| `speaker_id.py` | Voice embedding + similarity — the enrolment match |
| `channel_sim.py` | Makes clean audio sound like a real phone line |
| `metrics.py` | Scoring |
| `run_experiment_v2.py` | The leak-free experiment harness |

What's missing is the **plumbing around it**: streaming instead of batch, a
transcript, a trigger, and a screen. That's the 4 days.

### Day by day

| Day | Build | You can see |
|---|---|---|
| **1** | Turn the batch scorer into a **streaming** one — sliding 3-second window emitting scores twice a second. Build the enrolment step. Prepare two demo calls (genuine + cloned, same speaker) run through the phone-line simulator. | Numbers streaming in a terminal |
| **2** | **Transcript + TRIGGER.** Speech-to-text running live on CPU; intent detection for transfer instructions, credential requests, urgency+authority. Wire it so deep verification only wakes when the trigger fires. | Console demo of the gating behaviour — the core idea, visible |
| **3** | **The screen.** Web dashboard: live transcript, trigger events, risk timeline, verdict panel, evidence panel. | The actual demo |
| **4** | **CHALLENGE layer** (scripted), the "not sure" abstention logic, threshold tuning, offline test, and a **screen recording as backup**. | Demo + video + screenshots for the slides |

### Where the demo audio comes from

Two options — do the safe one first.

- **Safe (use this):** we already have ASVspoof data downloaded, which contains
  genuine and cloned recordings **of the same speakers**, with ground truth.
  Zero setup risk. Works today.
- **Dramatic (only if Day 1–3 go smoothly):** record a teammate for 30 seconds,
  clone their voice with open-source software, and demo on a voice the judges
  just heard live. Much more impactful, but voice-cloning toolchains are
  fragile and can burn half a day. **Treat it as a bonus, never as the plan.**

---

## 3. When to do it — this is the part that matters

**Do not build this before the college round.**

Here's the calendar:

```
~27 Aug   College internal round            ← 2 days away. The PPT is what's scored.
20 Sept   SIH portal idea deadline          ← 26 days away
Oct–Nov   Idea screening
Dec       36-hour Grand Finale
```

Four days of prototype work misses the college round by about two days, and
trying to squeeze it in would put the presentation — the thing actually being
scored right now — at risk. **The presentation is the deliverable this week.
The prototype is the deliverable next week.**

Start the prototype the day after the college round. It's ready around
**29 Aug – 2 Sept**, giving you nearly three weeks of buffer before the portal
deadline.

### Why that timing is genuinely valuable

Look at the official template's own wording for slide 3:

> *"Methodology and process for implementation (Flow Charts/Images/**working
> prototype**)"*

**The template explicitly invites a working prototype into the idea
submission.** Almost no team will have one at the idea stage. A screenshot of a
live risk timeline on slide 3 of the portal submission is a very large
differentiator for very little slide real estate — and I can swap it in without
touching anything else.

It then carries straight into the Oct–Nov screening and gives you a running
head start on the December finale, where you'll have 36 hours and everyone else
will be starting from zero.

---

## 4. Run these two things in parallel — they don't conflict

**Right now, before anything else:** hand `detector/KAGGLE-RUNBOOK.md` to one
teammate. Ten minutes of clicking, then it runs unattended for about an hour on
a free GPU. That produces the real full-scale number for slide 4. It costs
nobody any real time and it is the single cheapest upgrade available to the
deck.

**After the college round:** the 4-day prototype build above.

---

## 5. My recommendation, plainly

1. **This week:** finish and submit the presentation. Nothing else.
2. **In parallel, today:** one person runs the Kaggle job. Send me
   `full_results.json` and slide 4 gets the real number.
3. **Day after the college round:** start the 4-day prototype. Target the
   safe ASVspoof demo path; treat teammate voice-cloning as a stretch goal.
4. **Around 2 Sept:** screenshot goes onto slide 3, and the portal submission
   goes in well ahead of 20 September.

You asked whether the prototype is necessary. It isn't — the idea round doesn't
require it. But you're right that it lifts you well clear of the field, and the
timing works comfortably **as long as it doesn't collide with the presentation
you're submitting this week.**
