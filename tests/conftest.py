"""Hermetic fixtures: a fabricated project repo, its manifest and a registry."""

import hashlib
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

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
