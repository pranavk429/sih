"""
SPEC §9: monotonicity, boundary behaviour, missing-file handling.

The point of calibration.py is that no number reaches a screen without
provenance. A missing or malformed file must fail loudly -- silently defaulting
to "0.5 seems fine" would let the demo show confident risk scores backed by
nothing, which is the single most damaging thing this project could do.
"""
from __future__ import annotations

import json
import os

import pytest

from sentinel.decision.calibration import Calibration, CalibrationError


@pytest.fixture(scope="module")
def cal(cfg):
    if not os.path.exists(cfg.models.calibration_path):
        pytest.skip("calibration missing -- run scripts/fit_probe.py")
    return Calibration.load(cfg.models.calibration_path)


def test_missing_file_raises_rather_than_defaulting(tmp_path):
    with pytest.raises(CalibrationError) as exc:
        Calibration.load(str(tmp_path / "nope.json"))
    assert "fit_probe" in str(exc.value), "the error should say how to fix it"


def test_malformed_file_raises(tmp_path):
    path = tmp_path / "cal.json"
    path.write_text("{not json")
    with pytest.raises(CalibrationError):
        Calibration.load(str(path))


def test_missing_required_key_raises(tmp_path):
    path = tmp_path / "cal.json"
    path.write_text(json.dumps({"dataset": "something"}))
    with pytest.raises(CalibrationError) as exc:
        Calibration.load(str(path))
    assert "eer" in str(exc.value)


def test_apply_is_monotonic_and_clamped(cal):
    values = [i / 100.0 for i in range(0, 101)]
    mapped = [cal.apply(v) for v in values]
    assert all(b >= a for a, b in zip(mapped, mapped[1:])), "mapping must be monotonic"
    assert all(0.0 <= m <= 1.0 for m in mapped)
    assert cal.apply(-5.0) == 0.0
    assert cal.apply(5.0) == 1.0


def test_calibration_id_tracks_file_contents(tmp_path, cal):
    """A different file must mean a different id -- that is the whole audit trail."""
    original = json.loads(open(cal.path).read())
    assert Calibration.load(cal.path).calibration_id == cal.calibration_id

    edited = dict(original)
    edited["eer"] = original["eer"] + 0.01
    path = tmp_path / "cal.json"
    path.write_text(json.dumps(edited))
    assert Calibration.load(str(path)).calibration_id != cal.calibration_id


def test_provenance_is_present_and_honest(cal):
    header = cal.header()
    for key in ("dataset", "eer", "eer_threshold", "n_test_trials", "calibration_id"):
        assert header.get(key) not in (None, ""), f"header is missing {key}"
    assert "PILOT" in cal.notes.upper(), (
        "calibration.json must say out loud that it is pilot scale"
    )
    assert 0.0 < cal.eer < 0.5
    assert 0.0 < cal.eer_threshold < 1.0


def test_sigma_above_genuine_is_signed_and_sane(cal):
    """A score at the genuine mean is 0 sigma; a higher score is positive."""
    stats = cal.score_stats["fused"]["bonafide"]
    assert cal.sigma_above_genuine("fused", stats["mean"]) == pytest.approx(0.0, abs=1e-6)
    assert cal.sigma_above_genuine("fused", stats["mean"] + stats["std"]) == pytest.approx(
        1.0, abs=1e-6
    )
    assert cal.sigma_above_genuine("fused", stats["mean"] - stats["std"]) < 0
    assert cal.sigma_above_genuine("nonexistent-kind", 0.5) is None


def test_config_thresholds_match_the_calibration(cal, cfg):
    """
    config.yaml claims its band comes from calibration.json. Check that.

    config stays authoritative -- an operator may widen the band deliberately --
    but a silent divergence between the numbers we calibrated and the numbers we
    decide with is exactly what a judge is entitled to catch us on.
    """
    warning = cal.check_band(cfg.decision.low_thr, cfg.decision.high_thr)
    assert warning is None, warning


def test_check_band_tolerance_is_rounding_only(cal):
    """
    BAND_TOLERANCE exists to forgive a 4-decimal round-trip through YAML, not
    to forgive real drift. A gap within it must pass silently; a gap clearly
    outside it (an order of magnitude bigger) must be reported.
    """
    within = cal.band_low + cal.BAND_TOLERANCE * 0.9
    assert cal.check_band(within, cal.band_high) is None

    drifted = cal.band_low + cal.BAND_TOLERANCE * 10
    warning = cal.check_band(drifted, cal.band_high)
    assert warning is not None, "a real threshold drift was not reported"


def test_spoof_scores_higher_than_genuine_in_the_calibration(cal):
    """Sanity on the stored statistics: the classes are the right way round."""
    for kind in ("cm", "fused"):
        stats = cal.score_stats[kind]
        assert stats["spoof"]["mean"] > stats["bonafide"]["mean"], (
            f"{kind}: spoof mean is not above bonafide mean -- the calibration "
            "was built with an inverted score"
        )
