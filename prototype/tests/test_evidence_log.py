"""
IMPLEMENTATION-PLAN 2.7: the chain verifier must pass on a clean log and detect
a hand-edited record.

This file IS the "tamper-proof record" claim on the slides. Be precise about the
claim: the chain is tamper-EVIDENT, not tamper-proof. Someone with write access
can rewrite it from the edit onward. What it makes impossible is a QUIET edit.
"""
from __future__ import annotations

import json

import pytest

from sentinel.evidence.log import EvidenceLog, read, verify


@pytest.fixture
def log(tmp_path):
    path = str(tmp_path / "run.jsonl")
    ev = EvidenceLog(path)
    ev.append("trigger", {"intent": "Fund transfer instruction", "margin": 0.56}, t_ms=21000)
    ev.append("verdict", {"state": "LIKELY_IMPERSONATION", "risk": 0.478}, t_ms=21500)
    ev.append("verdict", {"state": "LIKELY_IMPERSONATION", "risk": 0.482}, t_ms=36600)
    return ev


def test_a_clean_chain_verifies(log):
    ok, problems = verify(log.path)
    assert ok, problems
    assert log.count == 3


def test_records_are_linked_to_their_predecessor(log):
    records = list(read(log.path))
    assert records[0]["prev_hash"] == "0" * 64
    for previous, current in zip(records, records[1:]):
        assert current["prev_hash"] == previous["hash"]


def test_an_edited_record_is_detected(log):
    """The core claim: change a verdict after the fact and the log says so."""
    records = list(read(log.path))
    records[1]["payload"]["state"] = "VERIFIED"  # the edit a fraudster would want
    with open(log.path, "w") as fh:
        for record in records:
            fh.write(json.dumps(record, sort_keys=True) + "\n")

    ok, problems = verify(log.path)
    assert not ok
    assert any("was edited" in p for p in problems)


def test_a_deleted_record_is_detected(log):
    records = list(read(log.path))
    del records[1]
    with open(log.path, "w") as fh:
        for record in records:
            fh.write(json.dumps(record, sort_keys=True) + "\n")

    ok, problems = verify(log.path)
    assert not ok
    assert any("removed or reordered" in p or "chain is broken" in p for p in problems)


def test_reordered_records_are_detected(log):
    records = list(read(log.path))
    records[1], records[2] = records[2], records[1]
    with open(log.path, "w") as fh:
        for record in records:
            fh.write(json.dumps(record, sort_keys=True) + "\n")

    ok, problems = verify(log.path)
    assert not ok


def test_appending_to_an_existing_log_continues_the_chain(log):
    reopened = EvidenceLog(log.path)
    assert reopened.count == 3
    assert reopened.head_hash == list(read(log.path))[-1]["hash"]
    reopened.append("verdict", {"state": "VERIFIED"}, t_ms=40000)
    ok, problems = verify(log.path)
    assert ok, problems


def test_verdicts_carry_their_calibration_and_models(tmp_path, cfg):
    """Every decision must stay attributable to what produced it."""
    from sentinel.decision.calibration import Calibration
    from sentinel.types import Verdict

    cal = Calibration.load(cfg.models.calibration_path)
    ev = EvidenceLog(str(tmp_path / "run.jsonl"))
    verdict = Verdict(
        state="LIKELY_IMPERSONATION",
        risk=0.48,
        confidence=0.04,
        reasons=["because"],
        t_ms=21000,
        calibration_id=cal.calibration_id,
        model_ids=["probe-cm:x", "resemblyzer-voice-encoder-v1"],
    )
    record = ev.append_verdict(verdict, extra={"mode": "triggered"})
    assert record["payload"]["calibration_id"] == cal.calibration_id
    assert record["payload"]["model_ids"]
    assert record["payload"]["mode"] == "triggered"


def test_verifying_a_missing_log_is_not_a_crash(tmp_path):
    ok, problems = verify(str(tmp_path / "nope.jsonl"))
    assert ok and problems == []
