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
import contextlib
import datetime as dt
import json
import os
import threading
from typing import Any, Dict, List, Optional, Tuple

from fastapi import Body, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from sentinel.audio.source import FileSource
from sentinel.config import Config
from sentinel.enrolment.store import EnrolmentStore
from sentinel.evidence.log import EvidenceLog
from sentinel.pipeline.events import EventQueue

# How long a WebSocket read blocks a worker thread before looping to check
# whether the client has gone away. Events arrive by Condition notify, so this
# is a liveness check, not a poll interval -- it does not add latency.
_WS_POLL_S = 0.5


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

    def header(self) -> Dict[str, Any]:
        """
        What the UI shows before a run starts.

        SPEC §12: the calibration provenance is in the header always, not only
        once a number exists to sit beside.
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
            "default_mode": self.cfg.gating.mode,
            "demos": self.demos(),
            "honesty": "Simulated live call — recorded audio streamed in real time.",
        }

    def state(self) -> Dict[str, Any]:
        session = self.session
        return {
            "running": self.is_running,
            "run_id": session.run_id if session else None,
            "meta": session.meta if session else None,
            "finished": session.finished if session else None,
            "events": len(session.history) if session else 0,
            "dropped": session.dropped if session else 0,
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
                path = audio
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

            self._n += 1
            stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
            run_id = f"{stamp}-{self._n:03d}"
            log_path = os.path.join(self.cfg.paths.evidence_dir, f"run-{run_id}.jsonl")
            self.orchestrator.evidence = EvidenceLog(log_path)

            meta = {
                "run_id": run_id,
                "demo": demo,
                "title": title,
                "file": os.path.basename(path),
                "duration_s": round(source.duration_s, 2),
                "ground_truth": ground_truth,
                "mode": mode or self.cfg.gating.mode,
                "fast": fast,
                "speaker_id": speaker_id,
                "enrolled": reference is not None,
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
        """
        with self._lock:
            if self.orchestrator is None:
                return False
            was_running = self.is_running
            self.orchestrator.stop()
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
