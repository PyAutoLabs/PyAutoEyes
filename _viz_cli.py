"""Shared helpers for the visualization producers and simulators.

A deliberately small subset of ``autolens_profiling/_profile_cli.py``: this repo
renders figures, it does not time anything, so only the pieces the simulators and
the ``scripts/<domain>/visualization.py`` producers need are kept:

- ``repo_root()`` — walk up from any file to the directory holding ``ruff.toml``
  (the depth-proof repo-root sentinel), so scripts work from any nesting level.
- ``bootstrap_sys_path()`` — put the repo root and ``scripts/misc/`` on
  ``sys.path`` so ``instruments`` / ``_viz_cli`` / ``simulators`` import by name.
- ``dataset_path(dataset_type, instrument)`` — ``<root>/dataset/<type>/<instrument>``.
- ``auto_simulate_if_missing(...)`` — shell out to
  ``scripts/misc/simulators/<type>.py --instrument <name>`` when a dataset is absent.

Typical use at the top of a producer::

    import sys
    from pathlib import Path

    for _p in Path(__file__).resolve().parents:
        if (_p / "ruff.toml").exists():
            sys.path.insert(0, str(_p))
            break
    from _viz_cli import auto_simulate_if_missing, dataset_path, repo_root
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def repo_root(start: Path | None = None) -> Path:
    """Return the autolens_visualization root (the directory containing ``ruff.toml``)."""
    here = Path(start if start is not None else __file__).resolve()
    for p in [here, *here.parents]:
        if (p / "ruff.toml").exists():
            return p
    raise RuntimeError("autolens_visualization root (ruff.toml) not found")


def bootstrap_sys_path() -> Path:
    """Put the repo root and ``scripts/misc`` on ``sys.path``; return the root."""
    root = repo_root()
    for p in (root, root / "scripts" / "misc"):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    return root


def dataset_path(dataset_type: str, instrument: str) -> Path:
    """``<root>/dataset/<dataset_type>/<instrument>``."""
    return repo_root() / "dataset" / dataset_type / instrument


def auto_simulate_if_missing(
    dataset_dir: Path,
    *,
    dataset_type: str,
    instrument: str,
    workspace_root: Path | None = None,
) -> None:
    """If ``dataset_dir`` is missing, run the matching simulator script.

    ``dataset_type`` maps to ``scripts/misc/simulators/<dataset_type>.py``
    (``imaging`` / ``interferometer``).

    The gate is a plain ``data.fits`` existence check, deliberately NOT
    ``al.util.dataset.should_simulate``: that helper deletes datasets it judges to
    belong to the other ``PYAUTO_SMALL_DATASETS`` regime, and this repo's datasets
    are tracked in git so every figure is reproducible — a harness run with the
    env var set must never wipe them.
    """
    if (Path(dataset_dir) / "data.fits").exists():
        return

    root = workspace_root if workspace_root is not None else repo_root()
    simulator_script = root / "scripts" / "misc" / "simulators" / f"{dataset_type}.py"
    if not simulator_script.exists():
        raise FileNotFoundError(
            f"Auto-simulate could not find simulator script at {simulator_script}."
        )

    print(
        f"  [auto-simulate] {dataset_dir} missing; invoking "
        f"scripts/misc/simulators/{dataset_type}.py --instrument {instrument}"
    )
    subprocess.run(
        [
            sys.executable,
            str(simulator_script),
            "--instrument",
            instrument,
            "--output-root",
            str(root),
        ],
        check=True,
    )
