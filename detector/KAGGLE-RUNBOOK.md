# Running the full-scale experiment on Kaggle — step by step

For whoever on the team is doing this. No coding knowledge needed — this is
copy, paste, click, wait.

## Before you start

- Takes about **10 minutes of your active time**, then it runs by itself
  for 45-70 minutes. You can close your laptop while it runs (Kaggle runs
  it on their servers, not yours) — just check back later.
- It's completely free. No credit card needed.

## Steps

1. Go to **kaggle.com** and make a free account (or sign in with Google).

2. Click **Create → New Notebook**.

3. On the right sidebar, find **Accelerator** and change it from "None" to
   **GPU T4 x2**. Click **Save**. (This is the free computing power —
   without this step, the run will be much slower or fail.)

4. Open the file `detector/notebooks/kaggle_full_run.py` (ask Pranav for it
   if you don't have it, or find it in the project folder).

5. That file is split into sections marked `# %% CELL 1`, `# %% CELL 2`,
   and so on, each followed by a block of code inside triple quotes
   (`"""..."""`). For each cell, **copy only the code between the triple
   quotes** (not the quotes themselves, not the comment above it) into a
   new cell in your Kaggle notebook.

6. Run each cell **one at a time**, in order, by clicking the ▶ button on
   the left of the cell (or pressing Shift+Enter). Wait for one to finish
   (the ▶ turns into a number when done) before running the next.

7. **Cells 1-7 and 10 should just work** — they use a method already
   tested and proven. **Cells 8 and 9 are experimental** — if either one
   prints an error message and stops, that's fine, don't worry about it.
   It says so right in the cell. Just skip to the next cell.

8. When Cell 10 finishes, it prints a block of results and saves a file.
   On the right side of the Kaggle screen, find the **Output** panel and
   look for `full_results.json`. Download it.

9. Send that file back — that's the real number for the presentation.

## If something looks wrong

- **"GPU not detected" error in Cell 2**: go back to step 3, make sure
  Accelerator is set to GPU T4 x2, and re-run from Cell 1.
- **A cell just hangs for a very long time (10+ minutes) with no output**:
  that's unusual for Cells 1-7. Stop it (■ button) and just report back
  what cell it was stuck on — don't guess or try to fix the code yourself.
- **Anything else**: copy the error message (the red text) and send it
  back rather than trying to debug it. That's genuinely the fastest way
  to fix it.

## What this is actually doing (if you're curious)

It's the same experiment already run once on a laptop (see
`PROJECT-EXPLAINED.md` section 10) — testing whether the fake-voice
detector still works after a phone call squishes the audio, and whether
comparing against a real reference recording helps — just done properly,
on a real GPU, with much more data, instead of a quick laptop test.
