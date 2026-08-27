"""
SPEC §9 / IMPLEMENTATION-PLAN 4.3: the offline smoke test.

SPEC §4: "Everything must work with the network unplugged. All models
download once during setup, then run from local cache." This is the
automated half of that claim. It blocks every outbound socket connection at
the transport layer -- underneath requests, urllib3 and huggingface_hub, so
it covers whichever of them ends up doing the connecting -- then loads every
model (including ASR, which is off everywhere else in this suite because it
is the one non-deterministic stage: see test_pipeline_golden.py) and replays
a full demo call. If anything on that path needs the network to start or to
run, this fails loudly and names the address it tried to reach, instead of
that surfacing for the first time on stage with the WiFi off.

The other half is manual and this file cannot substitute for it: physically
turn the WiFi off and run `sentinel serve` end to end. See HANDOFF-DAY4.md
4.3 -- do not treat 4.3 as done on the strength of this file alone.
"""
from __future__ import annotations

import errno
import json
import os
import socket

import pytest

LOOPBACK = {"127.0.0.1", "::1", "localhost"}


@pytest.fixture
def blocked_sockets(monkeypatch):
    """
    Every new outbound TCP connection fails as ENETUNREACH -- the OSError a
    real "WiFi off" produces, not an arbitrary exception. That distinction
    matters: huggingface_hub and requests catch connection-level OSErrors
    specifically and fall back to the local cache, which is the exact
    behaviour SPEC §4 depends on. Raising some other exception type here
    would make model loading fail in a way physically unplugging the network
    never would, and this test would be reporting a bug that does not exist.

    Loopback is let through because it is not "the network" -- pytest, and
    any local server this process has open, both use it.
    """
    real_connect = socket.socket.connect

    def guarded_connect(self, address, *a, **kw):
        host = address[0] if isinstance(address, tuple) else address
        if host not in LOOPBACK:
            raise OSError(errno.ENETUNREACH, f"Network is unreachable (offline test: {address!r})")
        return real_connect(self, address, *a, **kw)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    yield


# --------------------------------------------------------------------------
# 1. Model construction -- the from_pretrained() calls are the actual risk.
# --------------------------------------------------------------------------
def test_model_loading_does_not_reach_the_network(blocked_sockets, cfg):
    """
    Builds fresh instances rather than reusing conftest's session-scoped
    fixtures -- reusing them would test nothing, since another test file may
    already have loaded the real objects before this one runs and blocking
    sockets afterwards would not exercise from_pretrained() at all.
    """
    from sentinel.models import registry

    if not os.path.exists(cfg.models.probe_head_path):
        pytest.skip("probe head missing -- run scripts/fit_probe.py")

    cm, spk = registry.build_models(cfg)
    assert cm.model_id
    assert spk.model_id


def test_trigger_semantics_loading_does_not_reach_the_network(blocked_sockets, cfg):
    from huggingface_hub.errors import LocalEntryNotFoundError

    from sentinel.trigger.engine import TriggerEngine

    try:
        engine = TriggerEngine(cfg.trigger, cfg.models)
    except LocalEntryNotFoundError:
        pytest.skip(
            f"{cfg.models.trigger_encoder_id} not in the local cache -- "
            "run scripts/prefetch_models.py"
        )
    assert engine.matcher.model_id


def test_asr_loading_does_not_reach_the_network(blocked_sockets, cfg):
    from huggingface_hub.errors import LocalEntryNotFoundError

    from sentinel.asr.transcriber import Transcriber

    try:
        transcriber = Transcriber(cfg.models)
    except LocalEntryNotFoundError:
        pytest.skip(
            f"{cfg.models.asr_model_id} not in the local cache -- "
            "run scripts/prefetch_models.py"
        )
    assert transcriber.model_id


# --------------------------------------------------------------------------
# 2. The whole point: a real call, start to finish, offline.
# --------------------------------------------------------------------------
def test_a_full_call_runs_with_the_network_blocked(blocked_sockets, cfg, demo_dir):
    from sentinel.audio.source import FileSource
    from sentinel.cli import build_runtime
    from sentinel.enrolment.store import EnrolmentStore

    with open(os.path.join(demo_dir, "manifest.json")) as fh:
        manifest = json.load(fh)
    reference = EnrolmentStore(cfg.paths.enrolments_dir).get(manifest["speaker_id"])
    if reference is None:
        pytest.skip(
            f"{manifest['speaker_id']} is not enrolled -- run: "
            "python -m sentinel.cli enrol --demo enrol"
        )

    orchestrator, _cal = build_runtime(cfg, with_asr=True)
    source = FileSource(
        os.path.join(demo_dir, "attack.wav"),
        sample_rate=cfg.audio.sample_rate,
        frame_ms=cfg.audio.frame_ms,
        realtime=False,
    )
    try:
        stats = orchestrator.run(
            source,
            reference_embedding=reference,
            speaker_id=manifest["speaker_id"],
            ground_truth="spoof",
        )
    finally:
        source.close()

    assert stats.verdict is not None
    assert stats.triggers > 0, "the scripted overlay did not fire with the network blocked"
