"""
The web front end: FastAPI, one WebSocket, no framework on the browser side.

    GET  /            the UI
    GET  /demos       what can be run, from the demo manifest
    GET  /state       what is running now (for a tab that joins late)
    POST /start       {demo, mode, fast} -> starts a run on a worker thread
    POST /stop        stops it
    WS   /stream      every event from the run, live

Three decisions worth stating, because each of them is a demo failure avoided:

MODELS LOAD ONCE, AT STARTUP. wav2vec2, Resemblyzer, MiniLM and faster-whisper
together take about ten seconds to load. Loading them per run would put that
pause in the middle of a live demo, immediately after the presenter clicks the
button. So `startup()` builds the runtime and every run reuses it.

THE RUN IS A THREAD, NOT A COROUTINE. The pipeline is synchronous and paces
itself against the wall clock (SPEC §7.2). Making it async would mean rewriting
the one part of the system that is already proven. It runs on a worker thread
and publishes into queues; the event loop only ever moves dictionaries.

EVERY CLIENT GETS ITS OWN QUEUE, PLUS THE HISTORY. Two tabs, or a tab opened
thirty seconds into a call, must both see the whole run -- a projector and a
laptop side by side is the normal case at a demo. So `RunSession` keeps the
event history and fans each new event out to every subscriber. A client that
connects mid-run is replayed the history first, then joins live.
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import contextlib
import datetime as dt
import json
import logging
import os
import re
import threading
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from fastapi import Body, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from sentinel.audio.live_source import LiveSource
from sentinel.audio.source import FileSource
from sentinel.config import Config
from sentinel.enrolment.gallery import Gallery
from sentinel.enrolment.store import EnrolmentStore
from sentinel.evidence.log import EvidenceLog
from sentinel.pipeline.events import EventQueue
from sentinel.types import Utterance

# How long a WebSocket read blocks a worker thread before looping to check
# whether the client has gone away. Events arrive by Condition notify, so this
# is a liveness check, not a poll interval -- it does not add latency.
_WS_POLL_S = 0.5

# A display name becomes a speaker id. EnrolmentStore enforces its own SAFE_ID
# pattern; this just makes the common path ("Coordinator's voice") produce a
# legal id, and the fallback keeps an empty name from erroring.
_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def _slug(text: str, fallback: str = "voice") -> str:
    slug = _SLUG_STRIP.sub("-", (text or "").strip().lower()).strip("-")
    return (slug or fallback)[:48]


class RunSession:
    """
    One call, running or finished, and everyone watching it.

    History plus fan-out. The history is what makes a late-joining tab see the
    whole call instead of the tail of it, and at ~250 events per run it costs
    nothing to keep.
    """

    def __init__(self, run_id: str, meta: Dict[str, Any], queue_size: int) -> None:
        self.run_id = run_id
        self.meta = meta
        self.queue_size = queue_size
        self.history: List[Dict[str, Any]] = []
        self.finished = False
        self.error: Optional[str] = None
        self._subscribers: List[EventQueue] = []
        self._lock = threading.Lock()

    def subscribe(self) -> Tuple["EventQueue", List[Dict[str, Any]]]:
        """
        Join the run: returns (live queue, everything so far), atomically.

        Taking the history and adding the subscriber under one lock is what
        makes a late-joining tab correct. Snapshot first and then subscribe and
        you lose whatever was published in between; subscribe first and then
        snapshot and you send those events twice. Neither is acceptable when the
        thing being duplicated might be the trigger.
        """
        queue = EventQueue(maxsize=self.queue_size)
        with self._lock:
            history = list(self.history)
            self._subscribers.append(queue)
        return queue, history

    def unsubscribe(self, queue: "EventQueue") -> None:
        with self._lock:
            if queue in self._subscribers:
                self._subscribers.remove(queue)
        queue.close()

    def publish(self, event: Dict[str, Any]) -> None:
        """Called from the pipeline thread, for every event the run emits."""
        event = dict(event)
        event["run_id"] = self.run_id
        with self._lock:
            self.history.append(event)
            subscribers = list(self._subscribers)
        for queue in subscribers:
            queue.put(event)

    def close(self, error: Optional[str] = None) -> None:
        self.finished = True
        self.error = error
        if error:
            self.publish({"type": "run_error", "message": error})
        self.publish({"type": "run_end", "run_id": self.run_id, "error": error})
        with self._lock:
            subscribers = list(self._subscribers)
        for queue in subscribers:
            queue.close()

    @property
    def dropped(self) -> int:
        with self._lock:
            return sum(q.dropped for q in self._subscribers)


class Runner:
    """
    Owns the one orchestrator and the one worker thread.

    Only one run at a time, deliberately: the orchestrator holds a single set of
    models and two concurrent runs would interleave on them. `start()` stops any
    run already going rather than refusing, because a presenter who clicks the
    button twice wants the second call, not an error dialog.
    """

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.orchestrator = None
        self.calibration = None
        self.session: Optional[RunSession] = None
        self.live_source: Optional[LiveSource] = None
        self._thread: Optional[threading.Thread] = None
        # Reentrant: start() stops any previous run while already holding it.
        self._lock = threading.RLock()
        self._n = 0

    # -- startup -----------------------------------------------------------
    def load(self, with_asr: bool = True) -> None:
        """Ten seconds of model loading, done once, before anyone is watching."""
        from sentinel.cli import build_runtime

        self.orchestrator, self.calibration = build_runtime(self.cfg, with_asr=with_asr)

    # -- the demo manifest -------------------------------------------------
    def manifest(self) -> Optional[Dict[str, Any]]:
        path = os.path.join(self.cfg.paths.demo_dir, "manifest.json")
        if not os.path.exists(path):
            return None
        with open(path) as fh:
            return json.load(fh)

    def demos(self) -> Dict[str, Any]:
        manifest = self.manifest()
        if manifest is None:
            return {"calls": [], "speaker_id": None, "honesty": None,
                    "error": "no demo manifest -- run scripts/make_demo_calls.py"}
        return {
            "speaker_id": manifest["speaker_id"],
            "dataset": manifest.get("dataset"),
            "honesty": manifest.get("honesty"),
            "calls": [
                {
                    "id": call["id"],
                    "title": call["title"],
                    "ground_truth": call["ground_truth"],
                    "duration_s": call["duration_s"],
                    "degraded": call.get("degraded", False),
                    "degrade_profile": call.get("degrade_profile"),
                    # Every segment and every repeat, so "where did 37 seconds
                    # come from?" has an answer on screen rather than in a file.
                    "segments": call.get("segments", []),
                    "source_clips": call.get("source_clips", []),
                }
                for call in manifest["calls"]
            ],
        }

    # -- voices ------------------------------------------------------------
    def voices(self) -> List[Dict[str, Any]]:
        """Everything in the enrolment store, for the UI's voices panel."""
        store = EnrolmentStore(self.cfg.paths.enrolments_dir)
        out = []
        for speaker_id in store.list():
            meta = store.meta(speaker_id) or {}
            out.append({
                "speaker_id": speaker_id,
                "display_name": meta.get("display_name") or speaker_id,
                "created_utc": meta.get("created_utc"),
                "duration_s": meta.get("duration_s"),
                "embedding_dim": meta.get("embedding_dim"),
                "model_id": meta.get("model_id"),
            })
        return out

    def enrol_voice(self, speaker_id: str, display_name: Optional[str],
                    pcm: np.ndarray, sr: int) -> Dict[str, Any]:
        """
        Embed one recording and persist the feature vector.

        Refused mid-run: the pipeline is reading the same encoder, and a demo
        that enrols a voice underneath a running verdict would make the verdict
        unattributable.
        """
        if self.is_running:
            raise RuntimeError("stop the run before enrolling a voice")
        if self.orchestrator is None:
            raise RuntimeError("models are still loading")
        store = EnrolmentStore(self.cfg.paths.enrolments_dir)
        return store.enrol(speaker_id, pcm, sr, self.orchestrator.spk,
                           display_name=display_name)

    def header(self) -> Dict[str, Any]:
        """
        What the UI shows before a run starts.

        SPEC §12: the calibration provenance is in the header always, not only
        once a number exists to sit beside. The live and lookup blocks do the
        same job for the new settings: a threshold on screen is never a mystery
        number.
        """
        cal = self.calibration
        return {
            "type": "hello",
            "calibration": cal.header() if cal is not None else None,
            "band": [self.cfg.decision.low_thr, self.cfg.decision.high_thr],
            "window_s": self.cfg.audio.window_s,
            "hop_s": self.cfg.audio.hop_s,
            "pre_roll_s": self.cfg.gating.pre_roll_s,
            "hold_s": self.cfg.gating.hold_s,
            "evidence_risk_floor": self.cfg.decision.evidence_risk_floor,
            "lag_warn_ms": self.cfg.server.lag_warn_ms,
            "default_mode": self.cfg.gating.mode,
            "live": {
                "max_session_s": self.cfg.live.max_session_s,
                "no_audio_warn_ms": self.cfg.live.no_audio_warn_ms,
            },
            "lookup": {
                "accept_similarity": self.cfg.lookup.accept_similarity,
                "min_margin": self.cfg.lookup.min_margin,
                "min_consecutive_windows": self.cfg.lookup.min_consecutive_windows,
            },
            "voices": self.voices(),
            "demos": self.demos(),
            "honesty": "Simulated live call — recorded audio streamed in real time.",
        }

    def state(self) -> Dict[str, Any]:
        session = self.session
        live = self.live_source
        return {
            "running": self.is_running,
            "run_id": session.run_id if session else None,
            "meta": session.meta if session else None,
            "finished": session.finished if session else None,
            "events": len(session.history) if session else 0,
            "dropped": session.dropped if session else 0,
            "live": live is not None,
            "audio_dropped_ms": live.dropped_ms if live is not None else 0,
        }

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # -- run control -------------------------------------------------------
    def start(self, demo: Optional[str] = None, audio: Optional[str] = None,
              mode: Optional[str] = None, fast: bool = False) -> Dict[str, Any]:
        if self.orchestrator is None:
            raise RuntimeError("models are still loading")

        with self._lock:
            self.stop(join=True)

            manifest = self.manifest()
            ground_truth = None
            title = None
            if audio:
                demo_root = os.path.realpath(self.cfg.paths.demo_dir)
                candidate = os.path.realpath(os.path.join(demo_root, audio))
                if os.path.commonpath([demo_root, candidate]) != demo_root:
                    raise KeyError(
                        f"audio path {audio!r} is outside the demo directory"
                    )
                path = candidate
            else:
                if manifest is None:
                    raise FileNotFoundError(
                        "no demo manifest -- run scripts/make_demo_calls.py"
                    )
                call = next(
                    (c for c in manifest["calls"] if c["id"] == demo), None
                )
                if call is None:
                    ids = ", ".join(c["id"] for c in manifest["calls"])
                    raise KeyError(f"unknown demo {demo!r}; available: {ids}")
                path = os.path.join(self.cfg.paths.demo_dir, call["file"])
                ground_truth = call["ground_truth"]
                title = call["title"]

            speaker_id = manifest["speaker_id"] if manifest else None
            reference = (
                EnrolmentStore(self.cfg.paths.enrolments_dir).get(speaker_id)
                if speaker_id else None
            )

            source = FileSource(
                path,
                sample_rate=self.cfg.audio.sample_rate,
                frame_ms=self.cfg.audio.frame_ms,
                realtime=not fast,
            )
            return self._launch(
                source, demo=demo, title=title, ground_truth=ground_truth,
                mode=mode, fast=fast, speaker_id=speaker_id, reference=reference,
                live=False, duration_s=round(source.duration_s, 2),
            )

    def start_live(self, mode: Optional[str] = None,
                   speaker_id: Optional[str] = None) -> Tuple[Dict[str, Any], LiveSource]:
        """
        Begin a call fed by the browser microphone.

        Returns the run meta AND the LiveSource, because the WebSocket handler
        that asked for the run is also the thing that pushes audio into it. The
        pipeline starts immediately and blocks on the source's queue: no audio
        has to exist yet, so there is no ordering race between "start the run"
        and "open the microphone".
        """
        if self.orchestrator is None:
            raise RuntimeError("models are still loading")

        with self._lock:
            self.stop(join=True)

            reference = None
            if speaker_id:
                reference = EnrolmentStore(self.cfg.paths.enrolments_dir).get(speaker_id)

            source = LiveSource(
                sample_rate=self.cfg.audio.sample_rate,
                frame_ms=self.cfg.audio.frame_ms,
                max_queue_frames=self.cfg.live.queue_frames,
                max_seconds=self.cfg.live.max_session_s,
            )
            self.live_source = source
            meta = self._launch(
                source, demo=None, title="Live microphone", ground_truth=None,
                mode=mode, fast=False, speaker_id=speaker_id, reference=reference,
                live=True, duration_s=None,
            )
            return meta, source

    def _launch(self, source, *, demo, title, ground_truth, mode, fast,
                speaker_id, reference, live, duration_s) -> Dict[str, Any]:
        """The tail start()/start_live() share: log, session, worker thread."""
        gallery = Gallery.load(
            EnrolmentStore(self.cfg.paths.enrolments_dir), self.cfg.lookup
        )

        self._n += 1
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        run_id = f"{stamp}-{self._n:03d}"
        log_path = os.path.join(self.cfg.paths.evidence_dir, f"run-{run_id}.jsonl")
        self.orchestrator.evidence = EvidenceLog(log_path)

        meta = {
            "run_id": run_id,
            "demo": demo,
            "title": title,
            "file": None if live else os.path.basename(getattr(source, "path", "")),
            "duration_s": duration_s,
            "ground_truth": ground_truth,
            "mode": mode or self.cfg.gating.mode,
            "fast": fast,
            "live": bool(live),
            "speaker_id": speaker_id,
            "enrolled": reference is not None,
            "gallery_size": len(gallery),
            "evidence_log": os.path.relpath(log_path, start=self.cfg.paths.evidence_dir),
            "started_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        }
        session = RunSession(run_id, meta, self.cfg.server.event_queue_size)
        session.publish({"type": "run_meta", **meta})
        self.session = session

        def worker() -> None:
            try:
                self.orchestrator.run(
                    source,
                    reference_embedding=reference,
                    speaker_id=speaker_id,
                    mode=mode,
                    ground_truth=ground_truth,
                    on_event=session.publish,
                    live=live,
                    gallery=gallery if len(gallery) else None,
                )
                session.close()
            except Exception as exc:  # noqa: BLE001 -- a crash must reach the screen
                session.close(error=f"{type(exc).__name__}: {exc}")
            finally:
                source.close()

        self._thread = threading.Thread(
            target=worker, name=f"sentinel-run-{run_id}", daemon=True
        )
        self._thread.start()
        return meta

    def stop(self, join: bool = True, timeout: float = 15.0) -> bool:
        """
        Stop the current run. Idempotent, and it really does join.

        The orchestrator checks its stop flag once per 20 ms frame, so this
        returns quickly. Joining matters: a thread still holding the models
        while the next run starts on them is the kind of bug that only shows up
        on stage.

        A live run may be blocked waiting for a chunk that will never arrive
        (the browser stopped sending). Closing the LiveSource makes frames()
        finish, which is what actually unblocks the loop -- the stop flag is
        only checked between frames.
        """
        with self._lock:
            if self.orchestrator is None:
                return False
            was_running = self.is_running
            self.orchestrator.stop()
            if self.live_source is not None:
                self.live_source.close()
            if join and self._thread is not None:
                self._thread.join(timeout=timeout)
                if self._thread.is_alive():
                    raise RuntimeError(
                        f"pipeline thread did not stop within {timeout}s -- "
                        "refusing to start another run on top of it"
                    )
                self._thread = None
            return was_running


def create_app(cfg: Optional[Config] = None, with_asr: bool = True,
               load_models: bool = True) -> FastAPI:
    cfg = cfg or Config.load()
    runner = Runner(cfg)
    static_dir = cfg.server.static_dir

    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI):
        if load_models:
            # Blocking, and about ten seconds of it. Off the event loop, so
            # uvicorn can answer /state while the models come up.
            await asyncio.get_running_loop().run_in_executor(
                None, lambda: runner.load(with_asr=with_asr)
            )
        yield
        # Ctrl-C during a run must not leave a thread holding the models.
        with contextlib.suppress(RuntimeError):
            runner.stop(join=True, timeout=5.0)

    app = FastAPI(title="Sentinel", docs_url=None, redoc_url=None, lifespan=lifespan)
    app.state.runner = runner
    app.state.cfg = cfg

    @app.get("/")
    def index():
        path = os.path.join(static_dir, "index.html")
        if not os.path.exists(path):
            return JSONResponse(
                {"error": f"UI not found at {path}. The API is up: "
                          "GET /demos, GET /hello, POST /start, WS /stream."},
                status_code=404,
            )
        return FileResponse(path)

    @app.get("/demos")
    def demos() -> Dict[str, Any]:
        return runner.demos()

    @app.get("/hello")
    def hello() -> Dict[str, Any]:
        return runner.header()

    @app.get("/state")
    def state() -> Dict[str, Any]:
        return runner.state()

    @app.post("/start")
    async def start(payload: Optional[Dict[str, Any]] = Body(default=None)):
        payload = payload or {}
        try:
            # The pipeline start does blocking work (reads and resamples the
            # WAV, joins any previous thread). Off the event loop it goes.
            meta = await asyncio.get_running_loop().run_in_executor(
                None,
                lambda: runner.start(
                    demo=payload.get("demo"),
                    audio=payload.get("audio"),
                    mode=payload.get("mode"),
                    fast=bool(payload.get("fast", False)),
                ),
            )
        except (KeyError, FileNotFoundError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=404)
        except RuntimeError as exc:
            return JSONResponse({"error": str(exc)}, status_code=409)
        return {"started": True, "meta": meta}

    @app.post("/stop")
    async def stop():
        was_running = await asyncio.get_running_loop().run_in_executor(
            None, lambda: runner.stop(join=True)
        )
        return {"stopped": was_running}

    # -- voices: live enrolment and lookup ----------------------------------
    @app.get("/voices")
    def voices() -> Dict[str, Any]:
        """Every enrolled voice. Feature vectors only -- see EnrolmentStore."""
        return {"voices": runner.voices()}

    @app.post("/voices")
    async def enrol_voice(payload: Optional[Dict[str, Any]] = Body(default=None)):
        """
        Enrol from a browser recording.

        The body is `pcm_int16_b64`: base64 of raw little-endian int16 mono at
        `sample_rate`. Int16 halves the payload against float32 and loses
        nothing that matters for an embedding -- the recording is speech aimed
        at a voice encoder, not a master.

        Nothing is written to disk except the 256-float vector and its metadata
        (SPEC §7.5). The PCM exists in this function's local variables and is
        dropped when it returns.
        """
        payload = payload or {}
        display_name = str(payload.get("display_name") or "").strip()[:64]
        encoded = payload.get("pcm_int16_b64")
        try:
            sample_rate = int(payload.get("sample_rate") or 0)
        except (TypeError, ValueError):
            sample_rate = 0

        if not display_name:
            return JSONResponse({"error": "display_name is required"}, status_code=400)
        if not encoded:
            return JSONResponse({"error": "pcm_int16_b64 is required"}, status_code=400)
        if not (8000 <= sample_rate <= 96000):
            return JSONResponse(
                {"error": f"sample_rate {sample_rate} is outside 8000-96000"},
                status_code=400,
            )
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError):
            return JSONResponse({"error": "pcm_int16_b64 is not valid base64"},
                                status_code=400)
        if len(raw) % 2:
            return JSONResponse({"error": "pcm_int16_b64 has an odd byte count"},
                                status_code=400)

        pcm = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
        seconds = len(pcm) / float(sample_rate)
        if seconds < 1.0:
            return JSONResponse(
                {"error": f"recording is {seconds:.1f}s; at least 1s is needed"},
                status_code=400,
            )
        if seconds > 30.0:
            return JSONResponse(
                {"error": f"recording is {seconds:.1f}s; 30s is the maximum"},
                status_code=400,
            )

        speaker_id = _slug(str(payload.get("speaker_id") or display_name))
        try:
            meta = await asyncio.get_running_loop().run_in_executor(
                None,
                lambda: runner.enrol_voice(speaker_id, display_name, pcm, sample_rate),
            )
        except RuntimeError as exc:
            return JSONResponse({"error": str(exc)}, status_code=409)
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        return {"enrolled": True, "meta": meta, "voices": runner.voices()}

    @app.delete("/voices/{speaker_id}")
    async def remove_voice(speaker_id: str):
        if runner.is_running:
            return JSONResponse({"error": "stop the run before changing voices"},
                                status_code=409)
        store = EnrolmentStore(cfg.paths.enrolments_dir)
        try:
            removed = store.remove(speaker_id)
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        return {"removed": removed, "voices": runner.voices()}

    # -- try a line: the trigger engine without audio ------------------------
    @app.post("/assess")
    async def assess(payload: Optional[Dict[str, Any]] = Body(default=None)):
        """
        Score a typed sentence with the trigger engine.

        This is the SAME `assess()` the pipeline calls on every transcribed
        utterance, so the box cannot disagree with the audio path. It is text
        in, and the response says so -- nothing here makes a claim about a
        voice.
        """
        payload = payload or {}
        text = str(payload.get("text") or "").strip()[:500]
        if not text:
            return JSONResponse({"error": "text is required"}, status_code=400)
        if runner.orchestrator is None:
            return JSONResponse({"error": "models are still loading"}, status_code=409)
        assessment, _event = runner.orchestrator.trigger_engine.assess(
            Utterance(text=text, t_start_ms=0, t_end_ms=0)
        )
        return {
            "text": text,
            "would_fire": bool(assessment.fired),
            "assessment": assessment.to_json(),
            "audio": False,
        }

    # -- the live microphone socket -----------------------------------------
    @app.websocket("/live/audio")
    async def live_audio(websocket: WebSocket) -> None:
        """
        Browser microphone in, events out over /stream.

        Protocol, in order:
            -> {"type": "start", "mode": "...", "speaker": "id", "sample_rate": 48000}
            <- {"type": "live_ready", "meta": {...}, "sample_rate": 48000}
            -> binary Float32 mono chunks (20 ms each, as captured)
            -> {"type": "stop"}            (optional; disconnect also ends it)
            <- {"type": "live_stopped"}

        The socket carries audio only. Run events keep flowing over /stream, so
        a second tab still sees everything and the UI has exactly one event
        path, live or recorded.
        """
        await websocket.accept()
        loop = asyncio.get_running_loop()
        source: Optional[LiveSource] = None
        sample_rate = 16000

        try:
            while True:
                message = await websocket.receive()
                if message.get("type") == "websocket.disconnect":
                    break

                data = message.get("bytes")
                if data:
                    if source is not None:
                        source.push(np.frombuffer(data, dtype="<f4"), sample_rate)
                    continue

                text = message.get("text")
                if not text:
                    continue
                payload = json.loads(text)
                kind = payload.get("type")

                if kind == "start":
                    try:
                        requested = int(payload.get("sample_rate") or 16000)
                    except (TypeError, ValueError):
                        requested = 16000
                    sample_rate = requested if 8000 <= requested <= 96000 else 16000
                    meta, source = await loop.run_in_executor(
                        None,
                        lambda: runner.start_live(
                            mode=payload.get("mode"),
                            speaker_id=payload.get("speaker"),
                        ),
                    )
                    await websocket.send_text(json.dumps({
                        "type": "live_ready",
                        "meta": meta,
                        "sample_rate": sample_rate,
                    }))
                elif kind == "stop":
                    if source is not None:
                        source.close()
                    await websocket.send_text(json.dumps({"type": "live_stopped"}))
                    break
        except WebSocketDisconnect:
            pass
        except ValueError as exc:
            with contextlib.suppress(Exception):
                await websocket.send_text(json.dumps({
                    "type": "live_error", "message": str(exc),
                }))
        except Exception:  # noqa: BLE001 -- a socket handler must not die silently
            logging.getLogger("sentinel.live").exception(
                "live audio handler failed; the run will be stopped"
            )
        finally:
            # A client that vanishes must not leave a run holding the models.
            if source is not None:
                source.close()

    @app.websocket("/stream")
    async def stream(websocket: WebSocket) -> None:
        """
        One client, for as long as it stays connected, across any number of runs.

        The socket outlives the run: a tab opened before the demo starts, or
        between two takes, stays connected and picks up the next run by itself.
        That is why the loop watches `runner.session` for a swap rather than
        ending when the run does.
        """
        await websocket.accept()
        loop = asyncio.get_running_loop()
        await websocket.send_text(json.dumps(runner.header()))

        session: Optional[RunSession] = None
        queue: Optional[EventQueue] = None

        async def attach(new_session: Optional[RunSession]):
            nonlocal session, queue
            if session is not None and queue is not None:
                session.unsubscribe(queue)
            session, queue = new_session, None
            if new_session is None:
                return
            queue, history = new_session.subscribe()
            for event in history:
                await websocket.send_text(json.dumps(event))
            if new_session.finished:
                await websocket.send_text(json.dumps({
                    "type": "run_end", "run_id": new_session.run_id,
                    "error": new_session.error, "replay": True,
                }))

        try:
            await attach(runner.session)
            while True:
                if runner.session is not session:
                    await attach(runner.session)
                    continue
                if queue is None:
                    await asyncio.sleep(0.1)   # nothing has run yet
                    continue
                event = await loop.run_in_executor(None, queue.get, _WS_POLL_S)
                if event is not None:
                    await websocket.send_text(json.dumps(event))
                elif queue.closed:
                    # The run is over AND its buffer is drained -- a closed
                    # queue still hands back what it holds, so this branch is
                    # only reached once the client has really seen everything.
                    await asyncio.sleep(0.1)
        except (WebSocketDisconnect, RuntimeError, asyncio.CancelledError):
            pass
        finally:
            if session is not None and queue is not None:
                session.unsubscribe(queue)

    if os.path.isdir(static_dir):
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    return app


def serve(cfg: Optional[Config] = None, host: Optional[str] = None,
          port: Optional[int] = None, with_asr: bool = True) -> None:
    import uvicorn

    cfg = cfg or Config.load()
    uvicorn.run(
        create_app(cfg, with_asr=with_asr),
        host=host or cfg.server.host,
        port=port or cfg.server.port,
        log_level="warning",
    )
