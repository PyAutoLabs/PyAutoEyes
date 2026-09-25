"""Hermetic tests for ``gallery/gallery_build.py``.

A fabricated ``scripts/alpha/images/visualization/{a.png, sub/b.png}`` tree in a tmp
dir stands in for real producer output. No PyAutoLens import (the version header is
passed explicitly), no real figures: the point is the manifest shape, the relative
links in GALLERY.md, and that ``--check`` catches a figure set that drifted from the
committed GALLERY.md.

The module is loaded straight off its path (``gallery/`` is not a package).

Run::

    cd autolens_visualization
    python -m pytest scripts/misc/test/test_gallery_build.py
"""

from __future__ import annotations

import importlib.util
import sys as _sys
from pathlib import Path as _Path

import pytest
import yaml


def _repo_root() -> _Path:
    for _p in _Path(__file__).resolve().parents:
        if (_p / "ruff.toml").exists():
            return _p
    raise RuntimeError("autolens_visualization root (ruff.toml) not found")


ROOT = _repo_root()
_MODULE_PATH = ROOT / "gallery" / "gallery_build.py"
_spec = importlib.util.spec_from_file_location("gallery_build_under_test", _MODULE_PATH)
gb = importlib.util.module_from_spec(_spec)
_sys.modules[_spec.name] = gb
_spec.loader.exec_module(gb)

PNG_BYTES = b"\x89PNG\r\n\x1a\n"  # a header is enough: the builder never decodes


@pytest.fixture
def tree(tmp_path):
    img = tmp_path / "scripts" / "alpha" / "images" / "visualization"
    (img / "sub").mkdir(parents=True)
    (img / "a.png").write_bytes(PNG_BYTES)
    (img / "sub" / "b.png").write_bytes(PNG_BYTES)
    return tmp_path


def _build(root, *extra):
    return gb.main(["--root", str(root), "--version-string", "9.9.9", *extra])


def test_manifest_content(tree):
    assert _build(tree) == 0
    manifest = yaml.safe_load((tree / "output" / "gallery" / "viz_manifest.yaml").read_text())
    assert manifest == {
        "alpha": {
            "visualization": [
                {
                    "file": "scripts/alpha/images/visualization/a.png",
                    "kind": "png",
                    "group": "",
                },
                {
                    "file": "scripts/alpha/images/visualization/sub/b.png",
                    "kind": "png",
                    "group": "sub",
                },
            ]
        }
    }
    assert (tree / "output" / "gallery" / "gallery.html").is_file()


def test_gallery_md_links_and_header(tree):
    assert _build(tree) == 0
    md = (tree / "GALLERY.md").read_text()
    assert "![a](scripts/alpha/images/visualization/a.png)" in md
    assert "![b](scripts/alpha/images/visualization/sub/b.png)" in md
    assert "Rendered with PyAutoLens `9.9.9` · 2 figures." in md
    assert "## alpha" in md
    assert "### alpha / visualization" in md
    assert "#### alpha / visualization / sub/" in md
    assert "- [alpha](#alpha)" in md


def test_check_passes_after_build_and_ignores_version(tree):
    assert _build(tree) == 0
    assert _build(tree, "--check") == 0
    # A different version stamp alone is not staleness.
    assert gb.main(["--root", str(tree), "--version-string", "0.0.1", "--check"]) == 0


def test_check_fails_after_extra_png(tree):
    assert _build(tree) == 0
    (tree / "scripts" / "alpha" / "images" / "visualization" / "c.png").write_bytes(PNG_BYTES)
    assert _build(tree, "--check") == 1
    # Rebuilding brings GALLERY.md back in line.
    assert _build(tree) == 0
    assert _build(tree, "--check") == 0


def test_check_fails_without_gallery_md(tree):
    assert _build(tree, "--check") == 1


def test_check_never_rewrites_gallery_md(tree):
    assert _build(tree) == 0
    before = (tree / "GALLERY.md").read_text()
    (tree / "scripts" / "alpha" / "images" / "visualization" / "c.png").write_bytes(PNG_BYTES)
    _build(tree, "--check")
    assert (tree / "GALLERY.md").read_text() == before
