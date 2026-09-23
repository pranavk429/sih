#!/usr/bin/env python3
"""
The browser end-to-end check (PLAN-LIVE.md L3).

The pytest suite covers the WebSocket protocol; it cannot cover `getUserMedia`,
the AudioWorklet, or a single line of the DOM. This script does:

    sentinel serve  ->  real Chromium  ->  the real UI  ->  a fake microphone
    (Chrome's --use-file-for-fake-audio-capture plays a WAV as the mic input,
     so the whole capture path runs with no human and no real device)

It walks the demo's exact click path -- source switch, recorded call, voices,
live mic, try-a-line, prompt cards, theme -- and asserts what the screen shows
after each. Screenshots land in a directory it prints.

This is deliberately NOT part of `pytest tests/`: it needs a Chromium and the
Playwright package, neither of which is a runtime dependency. Run it with any
Python 3 that has Playwright:

    python3 scripts/browser_e2e.py                 # headless
    python3 scripts/browser_e2e.py --headful       # watch it happen
    python3 scripts/browser_e2e.py --voice-a x.wav --voice-b y.wav

On macOS the two fake-microphone WAVs are generated with `say` + `afconvert`
(16-bit PCM only -- Chrome parses 24-bit as silence) unless you pass them.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROTO = HERE.parent                       # prototype/ when run from scripts/
VENV_PY = PROTO.parent / "detector" / "venv" / "bin" / "python"

# The spoken script for the fake microphone. Voice A is the enrolled speaker and
# says a line that must trigger; voice B is a different person and says nothing
# high risk. Both are TTS, which the countermeasure will flag -- honestly, since
# the audio IS synthetic. That is not what this script asserts about.
VOICE_A_SCRIPT = (
    "Hello, this is a routine call about your account. "
    "I need you to transfer two crore to this account tonight. "
    "Please do not call the branch about this."
)
# Voice B is the second speaker: one high-risk sentence only, so the VAD cut
# cannot merge a benign opener into the same utterance and dilute the margin.
VOICE_B_SCRIPT = (
    "I need you to move the funds across to this beneficiary immediately."
)

TRIGGER_LINE = "transfer two crore to this account tonight"
BENIGN_LINE = "I'll transfer you to the other line, please hold"

# Verdicts the demo can legitimately land on, exactly as the UI renders them
# (SPEC §12: abstention is an outcome). These are display labels, not the
# server's enum -- the UI maps MONITORING/VERIFIED/... to human words.
VERDICTS = ["Verified", "Uncertain — escalate", "Likely impersonation"]


# ---------------------------------------------------------------- reporting
class Report:
    def __init__(self) -> None:
        self.rows = []
        self.failures = []

    def step(self, name: str, ok: bool, detail: str = "") -> None:
        mark = "ok  " if ok else "FAIL"
        self.rows.append((mark, name, detail))
        print(f"  [{mark}] {name}" + (f" — {detail}" if detail else ""), flush=True)
        if not ok:
            self.failures.append(name)


# ---------------------------------------------------------------- fixtures
def make_voice_wav(path: Path, text: str, voice: str, force: bool = False) -> None:
    """
    macOS `say` -> 16 kHz mono 16-bit PCM WAV. Chrome ignores other formats.

    `force` is on for the fixtures this script generates itself: a WAV left in
    the output directory by an older version of the script would otherwise be
    reused, and the run would be testing last week's sentence. Files passed
    with --voice-a/--voice-b are never touched.
    """
    if path.exists() and not force:
        return
    if not shutil.which("say") or not shutil.which("afconvert"):
        raise SystemExit(
            f"no {path.name} and no `say`/`afconvert` to build one.\n"
            "Pass --voice-a/--voice-b with 16-bit PCM WAV files."
        )
    aiff = path.with_suffix(".aiff")
    subprocess.run(["say", "-v", voice, "-r", "175", "-o", str(aiff), text],
                   check=True)
    subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16@16000", "-c", "1",
                    str(aiff), str(path)], check=True)
    if aiff.exists():
        aiff.unlink()


def find_chromium(explicit: str | None) -> str | None:
    if explicit:
        return explicit
    roots = [
        Path.home() / "Library" / "Caches" / "ms-playwright",
        Path.home() / ".cache" / "ms-playwright",
    ]
    patterns = [
        "chromium-*/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing",
        "chromium-*/chrome-mac-x64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing",
        "chromium-*/chrome-linux/chrome",
        "chromium-*/chrome-linux64/chrome",
        "chromium-*/chrome-mac/Chromium.app/Contents/MacOS/Chromium",
    ]
    for root in roots:
        for pattern in patterns:
            hits = sorted(glob.glob(str(root / pattern)))
            if hits:
                return hits[-1]
    return None                       # let Playwright use its own default


def fake_mic_args(wav: Path) -> list:
    """
    Chromium flags that make a WAV the microphone.

    `%noloop` matters: without it the file repeats forever, sentences run
    together with no pause for the VAD to cut on, the transcriber hits its
    12 s maximum and mangles the words, and the ASR backlog shows up as
    pipeline lag. A person pauses at the end of a sentence; the fixture must.
    """
    return [
        "--use-fake-ui-for-media-stream",
        "--use-fake-device-for-media-stream",
        f"--use-file-for-fake-audio-capture={wav}%noloop",
        "--autoplay-policy=no-user-gesture-required",
        "--mute-audio",
    ]


# ---------------------------------------------------------------- the server
def port_in_use(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/state", timeout=1):
            return True
    except Exception:  # noqa: BLE001
        return False


def start_server(port: int) -> subprocess.Popen:
    if not VENV_PY.exists():
        raise SystemExit(f"no interpreter at {VENV_PY}")
    if port_in_use(port):
        raise SystemExit(
            f"port {port} is already serving something — stop it or pass --port"
        )
    log_path = Path(tempfile.gettempdir()) / "sentinel-e2e-server.log"
    log = open(log_path, "w")
    proc = subprocess.Popen(
        [str(VENV_PY), "-m", "sentinel.cli", "serve", "--port", str(port)],
        cwd=str(PROTO), stdout=log, stderr=subprocess.STDOUT,
    )
    started = time.time()
    while time.time() - started < 180:
        if proc.poll() is not None:
            raise SystemExit(
                f"sentinel serve exited with {proc.returncode}; see {log_path}"
            )
        try:
            with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/hello", timeout=2) as response:
                hello = json.load(response)
            if hello.get("calibration"):
                print(f"  server up on :{port} after {time.time() - started:.0f}s "
                      f"(models loaded)", flush=True)
                return proc
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
            pass
        time.sleep(0.5)
    proc.terminate()
    raise SystemExit(f"server never loaded its models within 180s; see {log_path}")


def api(port: int, method: str, path: str, body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}", data=data, method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


# ---------------------------------------------------------------- page helpers
def wait_js(page, expression: str, timeout: float, what: str):
    try:
        page.wait_for_function(expression, timeout=timeout * 1000)
    except Exception as exc:  # noqa: BLE001 - re-raised with the step's name
        raise AssertionError(f"{what} (waited {timeout:.0f}s)") from exc


def text_of(page, selector: str) -> str:
    return page.text_content(selector) or ""


def console_hook(page, sink: list) -> None:
    page.on("pageerror", lambda err: sink.append(f"pageerror: {err}"))
    page.on("console", lambda msg: sink.append(f"console.{msg.type}: {msg.text}")
            if msg.type == "error" else None)


def wait_for_hello(page, timeout: float = 30) -> None:
    """
    Wait until /hello has been applied: calibration in the rail, voices known.

    Without this a run can start before the voice list arrives, which silently
    turns "check against the enrolled speaker" into "lookup only" -- and the
    E2E would be asserting about a run nobody asked for.
    """
    wait_js(page,
            "() => document.getElementById('prov-id').textContent !== '—'",
            timeout, "the server's hello never reached the page")


def wait_for_new_run_ui(page, timeout: float = 30) -> None:
    """
    Wait until the transcript has been rebuilt for the run that just started.

    The DOM from the previous run lingers for a frame or two; asserting on
    `.tag.trig` before the rebuild would pass on the old run's trigger.
    """
    wait_js(page,
            "() => document.querySelectorAll('#transcript .line').length === 0",
            timeout, "the transcript never cleared for the new run")


# ---------------------------------------------------------------- the flows
def drive_recorded_call(page, report: Report, shot) -> str:
    """Source stays on Recorded: pick the attack call, run it at fast replay."""
    wait_js(page,
            "() => document.getElementById('chip-conn').textContent === 'connected'",
            30, "the event socket never connected")
    wait_for_hello(page)
    page.select_option("#demo", "attack")
    page.check("#fast")
    page.click("#run")
    wait_js(page, "() => document.getElementById('run').disabled", 15,
            "the run button never went disabled")
    wait_js(page, "() => document.getElementById('chip-clock').textContent.includes('/')",
            30, "the recorded run never started")
    # Wait for the run to END, then read the verdict. Waiting for the label to
    # change mid-run is not reliable: two runs can land on the same word, and a
    # fast replay can render its first frame after the final verdict exists.
    wait_js(page, "() => !document.getElementById('run').disabled", 300,
            "the recorded call never ended")
    verdict = text_of(page, "#verdict-state")
    report.step("recorded call reaches a verdict", verdict in VERDICTS, verdict)
    # The overlay disclosure must be visible while scripted lines are on screen
    # for a recorded run. The live run later asserts the opposite.
    report.step("recorded run discloses the scripted overlay",
                page.is_visible("#overlay-note"))
    shot("recorded-verdict")
    return verdict


def drive_voice_enrolment(page, report: Report, shot, port: int) -> str:
    page.once("dialog", lambda dialog: dialog.accept("Playwright Coordinator"))
    page.click("#voice-record")
    wait_js(page,
            "() => document.getElementById('voice-status').textContent.startsWith('saved')",
            120, "the voice was never enrolled")
    status = text_of(page, "#voice-status")
    # The store may already hold the demo speaker; find the one just recorded.
    voices = api(port, "GET", "/voices")["voices"]
    mine = next((v for v in voices if v["display_name"] == "Playwright Coordinator"), None)
    report.step("live enrolment stores a voice", mine is not None, status)
    speaker_id = mine["speaker_id"] if mine else ""
    dim = mine.get("embedding_dim") if mine else None
    report.step("the fingerprint is 256-dim, no audio", dim == 256, f"dim={dim}")

    # Privacy, on disk: .npy + .json only, exactly the pytest rule.
    files = sorted(os.listdir(PROTO / "artifacts" / "enrolments"))
    audio = [f for f in files if f.endswith((".wav", ".flac", ".ogg", ".raw"))]
    report.step("nothing audio-bearing reached the enrolment store",
                not audio, ", ".join(files))
    shot("voice-enrolled")
    return speaker_id


def drive_live_run(page, report: Report, shot, expect: str,
                   speaker_id: str | None) -> None:
    """expect is 'known' or 'unknown' -- what the lookup chip must say."""
    page.click("#src-live")
    wait_js(page,
            "() => document.getElementById('src-live').getAttribute('aria-checked') === 'true'",
            10, "the source switch never reached live")
    wait_for_hello(page)
    if speaker_id:
        page.select_option("#speaker", speaker_id)
    page.click("#run")
    wait_js(page,
            "() => document.getElementById('mic-note').textContent === 'listening'",
            30, "the microphone never started")
    report.step("live microphone starts", True)
    # `live` in the clock only becomes true from the run_meta event, so the
    # transcript that follows this is the new run's, not the last run's.
    wait_js(page, "() => /· live/.test(document.getElementById('chip-clock').textContent)",
            30, "the live run never announced itself")
    wait_for_new_run_ui(page)

    wait_js(page, "() => document.querySelectorAll('#transcript .line').length > 0",
            150, "no live caption ever appeared")
    wait_js(page, "() => document.querySelectorAll('#transcript .mchip').length > 0",
            150, "no transcript line carried a margin assessment")
    report.step("live captions carry an assessment", True)

    try:
        wait_js(page,
                "() => document.querySelectorAll('#transcript .tag.trig').length > 0",
                240, "the spoken instruction never fired the trigger")
    except AssertionError:
        # If this ever fails, the interesting thing is what the transcriber
        # actually heard -- a pipeline that fell behind shows up as fragments.
        lines = page.eval_on_selector_all(
            "#transcript .line", "els => els.map(e => e.textContent).slice(-5)")
        report.step("transcript at the timeout", False, " | ".join(lines))
        raise
    report.step("the live trigger fires", True)

    # The lookup runs on every window while the microphone is live, so read it
    # before stopping -- that is when it is the point of the screen.
    wait_js(page,
            "() => { const c = document.getElementById('chip-lookup');"
            " return c.hidden === false && c.dataset.state !== undefined; }",
            180, "the lookup chip never appeared")
    if expect == "known":
        # The threshold is the impostor p99 (config.yaml lookup.*). A genuine
        # same-mic pair can land under it -- the measured sets overlap -- and
        # that is a documented miss, not a UI failure. What must hold is that
        # the lookup ran and its best candidate is the enrolled voice; a score
        # below the line is reported, never hidden.
        chip = text_of(page, "#chip-lookup")
        state = page.get_attribute("#chip-lookup", "data-state")
        near_miss = state == "unknown" and "Playwright Coordinator" in chip
        report.step("the lookup names the enrolled voice (or reports the miss)",
                    state == "known" or near_miss, chip)
    else:
        wait_js(page,
                "() => { const c = document.getElementById('chip-lookup');"
                f" return c.dataset.state === {json.dumps(expect)}; }}",
                180, f"the lookup chip never said {expect!r}")
        report.step(f"the lookup reports {expect}", True, text_of(page, "#chip-lookup"))

    # SPEC §12: the live banner is not the recorded one.
    title = text_of(page, "#honesty-title")
    report.step("the live banner says microphone, not phone call",
                "microphone" in title.lower(), title)
    report.step("the live run does not claim a scripted overlay",
                not page.is_visible("#overlay-note"))
    report.step("pipeline lag stays under the warn line",
                not page.is_visible("#chip-lag"))

    shot(f"live-{expect}")
    page.click("#stop")
    wait_js(page, "() => /ended/.test(document.getElementById('chip-clock').textContent)",
            60, "stop never ended the live run")
    wait_js(page, "() => !document.getElementById('run').disabled", 60,
            "the run button never came back after stop")
    report.step("stop ends the live run cleanly", True)
    # Wait for the run's OWN final event before reading the verdict. Stop sets
    # `running=false` in the browser immediately, so the run button comes back
    # before the server's final verdict has rendered; the footer's stats line
    # is written only by the `final` event, which makes it the honest marker.
    wait_js(page,
            "() => /wall clock for/.test(document.getElementById('footer-stats').textContent)",
            60, "the live run never produced its final stats")
    verdict = text_of(page, "#verdict-state")
    report.step("the live run reaches a verdict", verdict in VERDICTS, verdict)


def drive_prompt_cards(page, report: Report) -> None:
    """
    Each card's group label is a claim the engine has to honour.

    "should trigger" must fire; every other group must stay quiet. The lines
    were measured before they were written down, and this keeps them true after
    any corpus change -- a card that promises a trigger the system does not
    deliver would be the demo lying about itself.
    """
    page.click("#prompts > summary")
    groups = page.eval_on_selector_all(
        ".prompt-group",
        "els => els.map(g => ({"
        " label: g.querySelector('b').textContent,"
        " lines: [...g.querySelectorAll('.prompt')].map(b => b.textContent)"
        "}))")
    for index, group in enumerate(groups):
        should_fire = "should trigger" in group["label"]
        for card in range(len(group["lines"])):
            before = text_of(page, "#assess-out")
            page.locator(".prompt-group").nth(index).locator(".prompt").nth(card).click()
            # Wait for a CHANGED result, not merely a visible box: the box is
            # already visible from the previous card, so reading it immediately
            # would report the previous line's score.
            wait_js(page,
                    "() => document.getElementById('assess-out').textContent"
                    f" !== {json.dumps(before)}",
                    30, "a prompt card did not score")
            fired = "FIRES" in text_of(page, "#assess-out")
            report.step(
                f"card ({group['label'].split(' — ')[0]}): {group['lines'][card][:44]}…",
                fired == should_fire,
                "fired" if fired else "quiet")


def drive_try_a_line(page, report: Report, shot) -> None:
    # The prompt cards live in the live source's rail (that is where a
    # presenter reads them), so score them before switching back. Nothing is
    # injected into a run; the click just types the line into the same box.
    drive_prompt_cards(page, report)

    page.click("#src-file")            # the rail stays usable after a live run
    wait_js(page,
            "() => document.getElementById('src-file').getAttribute('aria-checked') === 'true'",
            10, "could not switch back to the recorded source")

    page.fill("#assess-text", TRIGGER_LINE)
    page.click("#assess-go")
    wait_js(page, "() => !document.getElementById('assess-out').hidden", 30,
            "try-a-line never returned")
    wait_js(page, "() => /FIRES/.test(document.getElementById('assess-out').textContent)",
            30, "the typed trigger line did not fire")
    report.step("try-a-line fires the same sentence", True)

    page.fill("#assess-text", BENIGN_LINE)
    page.click("#assess-go")
    wait_js(page, "() => /stays quiet/.test(document.getElementById('assess-out').textContent)",
            30, "the benign twin did not stay quiet")
    report.step("try-a-line keeps the benign twin quiet", True)

    report.step("text-in is labelled as text-in",
                "no audio claim" in text_of(page, "#assess-note"))
    shot("try-a-line")


def drive_theme(page, report: Report) -> None:
    before = page.evaluate("() => document.documentElement.dataset.theme || 'auto'")
    after = page.evaluate(
        "() => { document.getElementById('theme').click();"
        " return document.documentElement.dataset.theme; }"
    )
    report.step("theme toggle switches", after != before, f"{before} -> {after}")


def drive_delete_voice(page, report: Report, port: int, speaker_id: str) -> None:
    """Delete the voice this run enrolled -- never the demo speaker's own."""
    row = page.locator(f".voice:has-text('{speaker_id}')")
    row.locator(".vdel").click()
    # Scope the wait to the voice rows: the status line ("saved <id>") keeps the
    # id in the body text on purpose, so a whole-body check would never pass.
    wait_js(page,
            "() => ![...document.querySelectorAll('.voice')]"
            f".some(r => r.textContent.includes('{speaker_id}'))",
            30, "the voice was not removed from the panel")
    ids = [v["speaker_id"] for v in api(port, "GET", "/voices")["voices"]]
    report.step("a voice can be deleted", speaker_id not in ids, ", ".join(ids))


# ---------------------------------------------------------------- main
def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8123)
    parser.add_argument("--proto", default=None,
                        help="path to the prototype/ directory (default: the "
                             "script's own repo)")
    parser.add_argument("--voice-a", help="WAV played as the enrolled speaker's mic")
    parser.add_argument("--voice-b", help="WAV played as a different speaker's mic")
    parser.add_argument("--out", help="screenshot directory (default: a temp dir)")
    parser.add_argument("--headful", action="store_true", help="show the browser")
    parser.add_argument("--chromium", help="explicit Chromium/Chrome executable")
    parser.add_argument("--skip-recorded", action="store_true",
                        help="skip the recorded-call smoke test")
    args = parser.parse_args()

    global PROTO, VENV_PY
    if args.proto:
        PROTO = Path(args.proto).resolve()
        VENV_PY = PROTO.parent / "detector" / "venv" / "bin" / "python"

    out = Path(args.out) if args.out else Path(tempfile.gettempdir()) / "sentinel-e2e"
    out.mkdir(parents=True, exist_ok=True)
    voice_a = Path(args.voice_a) if args.voice_a else out / "voice-a.wav"
    voice_b = Path(args.voice_b) if args.voice_b else out / "voice-b.wav"
    make_voice_wav(voice_a, VOICE_A_SCRIPT, "Samantha", force=not args.voice_a)
    # Rishi (en_IN) for the second speaker: "crore" is a normal word for that
    # voice, so the transcriber hears it. The same line through Daniel (en_GB)
    # came back as "transfer to crawl to" -- an ASR miss, not a trigger bug.
    make_voice_wav(voice_b, VOICE_B_SCRIPT, "Rishi", force=not args.voice_b)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise SystemExit(
            "Playwright is not importable from this interpreter. Install it "
            "with `pip install playwright` (any Python 3), or run this script "
            "with one that already has it."
        )

    chromium = find_chromium(args.chromium)
    python = sys.executable
    report = Report()
    shots = {"n": 0}

    def shooter(page):
        def shot(name: str):
            shots["n"] += 1
            path = out / f"{shots['n']:02d}-{name}.png"
            try:
                page.screenshot(path=str(path))
            except Exception:  # noqa: BLE001 - a screenshot is evidence, not a gate
                pass
        return shot

    print(f"Sentinel browser E2E — screenshots in {out}", flush=True)
    server = start_server(args.port)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=not args.headful, executable_path=chromium,
                args=fake_mic_args(voice_a),
            )
            context = browser.new_context(permissions=["microphone"])
            page = context.new_page()
            errors: list = []
            console_hook(page, errors)
            shot = shooter(page)
            page.goto(f"http://127.0.0.1:{args.port}/")

            if not args.skip_recorded:
                drive_recorded_call(page, report, shot)

            speaker_id = drive_voice_enrolment(page, report, shot, args.port)
            drive_live_run(page, report, shot, expect="known",
                           speaker_id=speaker_id)
            drive_try_a_line(page, report, shot)
            drive_theme(page, report)
            drive_delete_voice(page, report, args.port, speaker_id)

            page.screenshot(path=str(out / "99-first-browser-final.png"))
            report.step("the first browser's console is clean", not errors,
                        "; ".join(errors[:3]))
            context.close()
            browser.close()

            # A second browser, microphone fed by a different speaker. The same
            # gallery must say "unknown voice" -- and show the best score below
            # the threshold rather than a name (PLAN-LIVE F2).
            browser = p.chromium.launch(
                headless=not args.headful, executable_path=chromium,
                args=fake_mic_args(voice_b),
            )
            context = browser.new_context(permissions=["microphone"])
            page = context.new_page()
            errors = []
            console_hook(page, errors)
            shot = shooter(page)
            page.goto(f"http://127.0.0.1:{args.port}/")
            drive_live_run(page, report, shot, expect="unknown", speaker_id=None)
            page.screenshot(path=str(out / "99-second-browser-final.png"))
            report.step("the second browser's console is clean", not errors,
                        "; ".join(errors[:3]))
            context.close()
            browser.close()
    finally:
        try:
            api(args.port, "POST", "/stop")
        except Exception:  # noqa: BLE001
            pass
        server.terminate()
        try:
            server.wait(timeout=15)
        except subprocess.TimeoutExpired:
            server.kill()

    print()
    if report.failures:
        print(f"FAILED: {len(report.failures)} — {', '.join(report.failures)}")
        return 1
    print(f"All {len(report.rows)} checks passed. Screenshots: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
