"""
The countermeasure is a frozen backbone plus a logistic head fit on that exact
backbone's embeddings. Nothing about the head's numbers announces which
backbone produced them, so the pairing has to be checked at load time.
"""
from __future__ import annotations

import os

import pytest

from sentinel.models.probe_cm import ProbeCountermeasure


def test_a_backbone_that_does_not_match_the_head_is_refused(cfg):
    """
    The regression: models.cm_backbone_id was read from config.yaml, passed to
    fit_probe.py, and then IGNORED at runtime -- ProbeCountermeasure always
    built the registry's default backbone. Point the config at a different
    encoder and the head would be applied to embeddings from a model it was
    never fit on. That does not raise; it returns confident, meaningless
    probabilities, which is the failure mode this project exists to argue about.

    The guard runs before the backbone is loaded, so this test costs no model.
    """
    if not os.path.exists(cfg.models.probe_head_path):
        pytest.skip("probe head missing -- run scripts/fit_probe.py")

    with pytest.raises(ValueError) as excinfo:
        ProbeCountermeasure(
            cfg.models.probe_head_path,
            cfg.models.device,
            backbone_id="facebook/wav2vec2-large-960h",
        )

    message = str(excinfo.value)
    assert "cm_backbone_id" in message
    assert "fit_probe.py" in message, "the error must say how to fix it"


def test_the_configured_backbone_is_the_one_the_head_was_fit_on(cfg):
    """
    Config and artifact agree today. If someone edits cm_backbone_id without
    re-fitting, the guard above fires at startup -- but this says it plainly.
    """
    if not os.path.exists(cfg.models.probe_head_path):
        pytest.skip("probe head missing -- run scripts/fit_probe.py")

    from sentinel.models.probe_cm import LogisticHead

    head = LogisticHead.load(cfg.models.probe_head_path)
    assert head.meta.get("backbone") == cfg.models.cm_backbone_id
