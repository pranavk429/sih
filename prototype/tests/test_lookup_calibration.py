"""
The lookup threshold on screen must be the one the measurement produced.

Same rule as `test_calibration.py`: when `artifacts/lookup_calibration.json`
exists, `config.yaml` has to agree with it. Until the script has been run, the
config carries a loud PROVISIONAL comment and this test skips -- it does not
quietly pass a borrowed number.
"""
from __future__ import annotations

import json
import os

import pytest

from sentinel.config import ROOT, Config

CALIBRATION_PATH = os.path.join(ROOT, "artifacts", "lookup_calibration.json")


@pytest.fixture(scope="module")
def payload():
    if not os.path.exists(CALIBRATION_PATH):
        pytest.skip("scripts/calibrate_lookup.py has not been run yet")
    with open(CALIBRATION_PATH) as fh:
        return json.load(fh)


def test_configured_threshold_matches_the_calibration(payload, cfg):
    proposed = payload["proposed"]["accept_similarity"]
    assert cfg.lookup.accept_similarity == pytest.approx(proposed, abs=5e-5), (
        "config.yaml's lookup.accept_similarity does not match "
        "artifacts/lookup_calibration.json -- either re-run the calibration or "
        "update the config; do not leave the screen showing a different number "
        "from the one that was measured"
    )


def test_the_calibration_says_what_it_can_and_cannot_measure(payload):
    """Provenance is mandatory, the same as calibration.json."""
    for key in ("created_utc", "dataset", "reference", "proposed", "caveats"):
        assert payload.get(key), f"lookup calibration is missing {key!r}"
    caveats = " ".join(payload["caveats"]).lower()
    assert "pilot" in caveats, "the scale of the measurement must be stated"
    assert "margin" in caveats, (
        "a one-voice gallery cannot measure a runner-up margin, and the "
        "calibration must say so rather than imply the margin was measured"
    )


def test_the_rule_is_written_down(payload):
    assert payload["proposed"]["rule"]
    assert payload["proposed"]["genuine_n"] > 0
    assert payload["proposed"]["impostor_n"] > 0


def test_the_threshold_is_in_range_and_below_one(payload):
    accept = payload["proposed"]["accept_similarity"]
    assert 0.0 < accept < 1.0
    assert accept > payload["proposed"]["impostor_p50"], (
        "a threshold below the median impostor score would accept strangers"
    )
