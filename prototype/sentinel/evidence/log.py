"""
The evidence log: append-only JSONL, hash-chained, tamper-evident.

This file IS the "tamper-proof record" the slides claim. Each record carries
`prev_hash`, the SHA-256 of the previous record's canonical form, so the log is
a chain: altering any record invalidates every hash after it, and truncating the
log leaves a chain that no longer reaches its stated head.

Be precise about what that does and does not give you, because a judge may ask.
It is TAMPER-EVIDENT, not tamper-proof: someone with write access to the file
can rewrite the whole chain from the edit onward. What it makes impossible is a
QUIET edit -- changing one verdict after the fact without recomputing everything
downstream of it. For the real property you would anchor the head hash somewhere
the operator does not control, which is a deployment decision and not a
prototype one. `head_hash` is exposed here so that anchoring is a later addition
rather than a rewrite.

Every verdict record carries `model_id` and `calibration_id`. When the Kaggle
run replaces calibration.json, the log still says which calibration decided
what.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from typing import Any, Dict, Iterator, List, Optional, Tuple

GENESIS = "0" * 64


def _canonical(payload: Dict[str, Any]) -> bytes:
    """Stable bytes for hashing: sorted keys, no incidental whitespace."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def record_hash(record: Dict[str, Any]) -> str:
    """
    A record's own hash, computed over everything except the hash field itself.

    `prev_hash` IS included -- that is what chains the records together.
    """
    body = {k: v for k, v in record.items() if k != "hash"}
    return hashlib.sha256(_canonical(body)).hexdigest()


class EvidenceLog:
    """Append-only JSONL with a hash chain. One file per run."""

    def __init__(self, path: str) -> None:
        self.path = path
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self._prev_hash = GENESIS
        self._n = 0
        if os.path.exists(path):
            records = list(read(path))
            if records:
                self._prev_hash = records[-1]["hash"]
                self._n = len(records)

    @property
    def head_hash(self) -> str:
        """
        The hash of the most recent record.

        Publishing this somewhere the operator cannot rewrite is what would turn
        tamper-evidence into tamper-proofing. Out of scope for the prototype,
        exposed so it does not have to be retrofitted.
        """
        return self._prev_hash

    @property
    def count(self) -> int:
        return self._n

    def append(self, kind: str, payload: Dict[str, Any], t_ms: Optional[int] = None) -> Dict[str, Any]:
        record = {
            "seq": self._n,
            "kind": kind,
            # Wall clock here is correct and deliberate: this is an audit record
            # of when we observed something, not a stream event. Stream time
            # lives in t_ms alongside it (SPEC §7.1).
            "logged_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "t_ms": t_ms,
            "prev_hash": self._prev_hash,
            "payload": payload,
        }
        record["hash"] = record_hash(record)
        with open(self.path, "a") as fh:
            fh.write(json.dumps(record, sort_keys=True) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        self._prev_hash = record["hash"]
        self._n += 1
        return record

    def append_verdict(self, verdict, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload = verdict.to_json()
        if extra:
            payload.update(extra)
        return self.append("verdict", payload, t_ms=verdict.t_ms)


def read(path: str) -> Iterator[Dict[str, Any]]:
    if not os.path.exists(path):
        return
    with open(path) as fh:
        for line_no, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no} is not valid JSON ({exc})") from exc


def verify(path: str) -> Tuple[bool, List[str]]:
    """
    Walk the chain. Returns (ok, problems) with a readable reason per break.

    Checks three things, because they fail differently:
      - each record's own hash still matches its contents  (edited record)
      - each prev_hash matches the previous record's hash  (broken/reordered chain)
      - seq numbers are contiguous from zero               (deleted record)
    """
    problems: List[str] = []
    prev = GENESIS
    expected_seq = 0

    for record in read(path):
        seq = record.get("seq")
        if seq != expected_seq:
            problems.append(f"record {expected_seq}: seq is {seq} -- a record was removed or reordered")
        if record.get("prev_hash") != prev:
            problems.append(
                f"record {seq}: prev_hash does not match the previous record's hash "
                "-- the chain is broken here"
            )
        recomputed = record_hash(record)
        if recomputed != record.get("hash"):
            problems.append(
                f"record {seq}: contents do not match its stored hash -- this record was edited"
            )
        prev = record.get("hash", prev)
        expected_seq = (seq if isinstance(seq, int) else expected_seq) + 1

    return (not problems), problems
