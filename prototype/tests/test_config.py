"""
Config sections that config.yaml leaves out still have to be BUILT, not
defaulted.

SPEC's rule is that every number on screen is traceable to a file. The
corollary for paths is that they are traceable to a *place* -- resolved against
ROOT -- rather than to whatever directory the process happened to start in.
"""
from __future__ import annotations

import os

from sentinel.config import ROOT, Config


def _write(tmp_path, text: str) -> str:
    path = tmp_path / "config.yaml"
    path.write_text(text)
    return str(path)


def test_an_omitted_section_still_resolves_its_paths(tmp_path):
    """
    The regression: with `models:` absent from the YAML, ModelConfig was taken
    straight from its dataclass defaults and never went through _build, so
    probe_head_path stayed the literal relative string "artifacts/...". It then
    resolved against the process's cwd -- correct only when the caller happened
    to launch from prototype/, and a file-not-found anywhere else.
    """
    cfg = Config.load(_write(tmp_path, "audio:\n  frame_ms: 20\n"))

    assert os.path.isabs(cfg.models.probe_head_path)
    assert cfg.models.probe_head_path.startswith(ROOT)
    assert os.path.isabs(cfg.paths.demo_dir)
    assert cfg.paths.demo_dir.startswith(ROOT)


def test_an_empty_config_resolves_every_path(tmp_path):
    """No section present at all -- every path field still comes out absolute."""
    cfg = Config.load(_write(tmp_path, "{}\n"))

    for path in (
        cfg.models.probe_head_path,
        cfg.models.calibration_path,
        cfg.paths.enrolments_dir,
        cfg.paths.demo_dir,
        cfg.paths.evidence_dir,
        cfg.server.static_dir,
    ):
        assert os.path.isabs(path), f"{path} is relative to the caller's cwd"


def test_an_overridden_section_is_unaffected(tmp_path):
    """The fix must not stop an explicit override from winning."""
    cfg = Config.load(_write(tmp_path, "paths:\n  demo_dir: somewhere/else\n"))

    assert cfg.paths.demo_dir == os.path.join(ROOT, "somewhere/else")
    assert os.path.isabs(cfg.paths.evidence_dir), "sibling default still resolves"
