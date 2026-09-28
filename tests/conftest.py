"""Hermetic fixtures: a fabricated project repo, its manifest and a registry."""

import hashlib
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eyes import context as context_mod  # noqa: E402
from eyes import manifest as manifest_mod  # noqa: E402

ROW = {
    "name": "demo",
    "repo": "demo_visualization",
    "path": "demo/demo_visualization",
    "github": "PyAutoLabs/demo_visualization",
    "library": "PyAutoDemo",
    "import_name": "autodemo",
    "manifest": "gallery/viz_manifest.yaml",
    "images_base_url": "https://raw.githubusercontent.com/PyAutoLabs/demo_visualization/main/",
    "gallery": "GALLERY.md",
    "dispatch_event": "pyautodemo-release",
}

FIGURES = [
    ("scripts/imaging/images/visualization/dataset.png", "imaging", ""),
    ("scripts/imaging/images/visualization/parametric/fit.png", "imaging", "parametric"),
    ("scripts/interferometer/images/visualization/delaunay/fit.png", "interferometer", "delaunay"),
]


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """No test may reach the network; tests that need a response stub it."""

    def refuse(url):
        raise OSError(f"network disabled in tests: {url}")

    monkeypatch.setattr(manifest_mod, "_http_get", refuse)
    monkeypatch.setattr(manifest_mod.urllib.request, "urlopen", lambda *a, **k: refuse(a[0]))


REAL_MIND_ROOT = context_mod.mind_root  # for the one test of the resolver itself


@pytest.fixture(autouse=True)
def no_local_organs(monkeypatch):
    """No test reads the real PyAutoMind or asks the real PyAutoBrain; tests
    that need either fabricate it and pass it in."""
    monkeypatch.setattr(context_mod, "mind_root", lambda root=None: None)
    monkeypatch.setattr(context_mod, "brain_cli", lambda: None)


EYES_SURVEY = {
    "kind": "EyesSurvey",
    "workspace": "/somewhere/on/a/laptop/demo_visualization",
    "domains": ["imaging", "interferometer"],
    "records": [
        {"domain": "imaging", "script": "visualization", "n_png": 2, "newest_png_mtime": 1.0},
        {"domain": "interferometer", "script": "visualization", "n_png": 1},
        {"domain": "interferometer", "script": "visualization_jax", "n_png": 0},
    ],
    "gaps": ["interferometer/visualization_jax"],
    "orphans": [],
    "stale_renders": ["imaging/visualization"],
}


@pytest.fixture
def fake_brain(tmp_path):
    """A stand-in ``pyauto-brain`` that prints a fabricated EyesSurvey and
    logs its argv, so the survey path runs end to end with no Brain."""
    import json
    import stat

    log = tmp_path / "brain_calls.log"
    payload = tmp_path / "eyes_survey.json"
    payload.write_text(json.dumps(EYES_SURVEY))
    script = tmp_path / "pyauto-brain"
    script.write_text(f'#!/usr/bin/env bash\necho "$@" >> "{log}"\ncat "{payload}"\n')
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return [str(script)], log


@pytest.fixture
def mind(tmp_path):
    """A fabricated PyAutoMind with drafts that do and do not mention demo."""
    root = tmp_path / "PyAutoMind"
    drafts = {
        "draft/feature/demo/restyle_fit.md": "# Restyle the -- fit panel\n\nIn demo_visualization.\n",
        "draft/bug/other/unrelated.md": "# Unrelated\n\nNothing to see.\n",
        "draft/feature/x/review_line.md": (
            "# From a review\n\n/eyes review demo scripts/imaging/images/a.png\n"
        ),
        "active/in_flight.md": "# Already issued\n\ndemo_visualization\n",
    }
    for rel, text in drafts.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return root


@pytest.fixture
def project(tmp_path):
    """A fabricated ``demo_visualization`` checkout with PNGs and a valid manifest."""
    root = tmp_path / "demo_visualization"
    figures = []
    for i, (file, domain, source) in enumerate(FIGURES):
        data = f"png-bytes-{i}".encode()
        path = root / file
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        figures.append(
            {
                "file": file,
                "producer": f"scripts/{domain}/visualization.py",
                "domain": domain,
                "source": source,
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )
    doc = {
        "schema": 1,
        "generated": "2026-09-28",
        "rendered_with": {"autodemo": "2026.9.1.1", "autofit": "2026.9.1.1"},
        "figure_count": len(figures),
        "figures": figures,
    }
    (root / "gallery").mkdir(parents=True)
    (root / "gallery" / "viz_manifest.yaml").write_text("# generated\n" + yaml.safe_dump(doc))
    return root


@pytest.fixture
def registry_file(tmp_path):
    path = tmp_path / "registry.yaml"
    path.write_text(yaml.safe_dump({"schema": 1, "instances": [dict(ROW)]}))
    return path
