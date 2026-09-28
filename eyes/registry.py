"""Read and validate ``registry.yaml``, the one-row-per-instance registry."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from eyes import ORGAN_ROOT

REGISTRY_PATH = ORGAN_ROOT / "registry.yaml"
REGISTRY_SCHEMA = 1

FIELDS = (
    "name",
    "repo",
    "path",
    "github",
    "library",
    "import_name",
    "manifest",
    "images_base_url",
    "gallery",
    "dispatch_event",
)

_NAME = re.compile(r"^[a-z][a-z0-9_-]*$")
_GITHUB = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class RegistryError(ValueError):
    """``registry.yaml`` is malformed; the message lists every problem."""


@dataclass(frozen=True)
class Instance:
    name: str
    repo: str
    path: str
    github: str
    library: str
    import_name: str
    manifest: str
    images_base_url: str
    gallery: str
    dispatch_event: str

    @property
    def manifest_url(self) -> str:
        return self.images_base_url + self.manifest

    @property
    def github_url(self) -> str:
        return f"https://github.com/{self.github}"

    @property
    def gallery_url(self) -> str:
        return f"{self.github_url}/blob/main/{self.gallery}"

    def image_url(self, file: str) -> str:
        return self.images_base_url + file

    def local_checkout(self, root: Path | None = None) -> Path | None:
        """The instance's local checkout, or None when it is not on this machine.

        Tries the grouped layout (``<root>/<path>``) and then the flat task-bundle
        layout (``<root>/<repo>``), for each candidate workspace root.
        """
        for base in workspace_roots(root):
            for candidate in (base / self.path, base / self.repo):
                if candidate.is_dir():
                    return candidate
        return None


def workspace_roots(root: Path | None = None) -> list[Path]:
    """Candidate workspace roots, most specific first."""
    if root is not None:
        return [Path(root)]
    roots = []
    env = os.environ.get("PYAUTO_ROOT")
    if env:
        roots.append(Path(env))
    # organs/PyAutoEyes (grouped canonical) or <bundle>/PyAutoEyes (flat bundle).
    roots += [ORGAN_ROOT.parent.parent, ORGAN_ROOT.parent]
    return roots


def validate(data) -> list[str]:
    """Return every problem with a parsed registry document (empty = valid)."""
    if not isinstance(data, dict):
        return ["registry is not a mapping"]
    problems = []
    if data.get("schema") != REGISTRY_SCHEMA:
        problems.append(f"schema must be {REGISTRY_SCHEMA}, got {data.get('schema')!r}")
    rows = data.get("instances")
    if not isinstance(rows, list) or not rows:
        return problems + ["instances must be a non-empty list"]
    seen = set()
    for i, row in enumerate(rows):
        where = f"instances[{i}]"
        if not isinstance(row, dict):
            problems.append(f"{where} is not a mapping")
            continue
        where = f"instance {row.get('name', i)!r}"
        for field in FIELDS:
            value = row.get(field)
            if not isinstance(value, str) or not value.strip():
                problems.append(f"{where}: {field} is missing or empty")
        unknown = sorted(set(row) - set(FIELDS))
        if unknown:
            problems.append(f"{where}: unknown field(s) {', '.join(unknown)}")
        name = row.get("name")
        if isinstance(name, str):
            if not _NAME.match(name):
                problems.append(f"{where}: name must match {_NAME.pattern}")
            if name in seen:
                problems.append(f"{where}: duplicate name")
            seen.add(name)
        github = row.get("github")
        if isinstance(github, str) and not _GITHUB.match(github):
            problems.append(f"{where}: github must be owner/repo")
        base = row.get("images_base_url")
        if isinstance(base, str) and not (base.startswith("https://") and base.endswith("/")):
            problems.append(f"{where}: images_base_url must be an https:// URL ending in /")
        for field in ("path", "manifest", "gallery"):
            value = row.get(field)
            if isinstance(value, str) and (value.startswith("/") or ".." in value.split("/")):
                problems.append(f"{where}: {field} must be a relative path inside the repo")
    return problems


def load(path: Path | str = REGISTRY_PATH) -> list[Instance]:
    """Parse and validate the registry; raise RegistryError on any problem."""
    path = Path(path)
    try:
        data = yaml.safe_load(path.read_text())
    except (OSError, yaml.YAMLError) as exc:
        raise RegistryError(f"{path}: {exc}") from exc
    problems = validate(data)
    if problems:
        raise RegistryError(f"{path}:\n  " + "\n  ".join(problems))
    return [Instance(**{f: row[f] for f in FIELDS}) for row in data["instances"]]


def get(instances: list[Instance], name: str) -> Instance:
    for instance in instances:
        if instance.name == name:
            return instance
    known = ", ".join(i.name for i in instances)
    raise RegistryError(f"no instance {name!r} in the registry (known: {known})")
