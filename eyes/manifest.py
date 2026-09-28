"""Read a project repo's tracked figure manifest (the contract in REFERENCE.md).

A manifest is read from a local checkout, from a local file, or from its raw
GitHub URL. The reader validates the schema versions in ``SUPPORTED_SCHEMAS``
and ignores keys it does not know, so project repos can add fields without
waiting for the organ.
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import yaml

from eyes.registry import Instance

SUPPORTED_SCHEMAS = (1,)
FIGURE_FIELDS = ("file", "producer", "domain", "source", "bytes", "sha256")
LIBRARIES = ("autolens", "autogalaxy", "autoarray", "autofit")
TIMEOUT = 20
USER_AGENT = "pyauto-eyes (+https://github.com/PyAutoLabs/PyAutoEyes)"

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ManifestError(ValueError):
    """A manifest is unreachable, unparseable or breaks the contract."""


@dataclass(frozen=True)
class Figure:
    file: str
    producer: str
    domain: str
    source: str
    bytes: int
    sha256: str


@dataclass(frozen=True)
class Manifest:
    doc: dict
    origin: str  # where it was read from: a local path or a URL
    local_root: Path | None  # the checkout the figure paths are relative to, if local

    @property
    def schema(self) -> int:
        return self.doc["schema"]

    @property
    def generated(self) -> str:
        return str(self.doc["generated"])

    @property
    def rendered_with(self) -> dict:
        return {str(k): str(v) for k, v in self.doc["rendered_with"].items()}

    @property
    def figures(self) -> list[Figure]:
        return [Figure(**{f: fig[f] for f in FIGURE_FIELDS}) for fig in self.doc["figures"]]

    @property
    def digest(self) -> str:
        """A short content digest of the manifest (comments and key order ignored).

        The dashboard records it per instance, so ``check`` can tell whether the
        committed dashboard was built from the manifest currently published.
        """
        blob = json.dumps(self.doc, sort_keys=True, default=str).encode()
        return hashlib.sha256(blob).hexdigest()[:16]


def validate(doc) -> list[str]:
    """Return every contract violation in a parsed manifest (empty = valid)."""
    if not isinstance(doc, dict):
        return ["manifest is not a mapping"]
    schema = doc.get("schema")
    if schema not in SUPPORTED_SCHEMAS:
        return [f"unsupported schema {schema!r} (this organ reads {list(SUPPORTED_SCHEMAS)})"]
    problems = []
    if not doc.get("generated"):
        problems.append("generated is missing")
    rw = doc.get("rendered_with")
    if not isinstance(rw, dict) or not rw:
        problems.append("rendered_with must be a non-empty mapping of package -> version")
    figures = doc.get("figures")
    if not isinstance(figures, list):
        return problems + ["figures must be a list"]
    count = doc.get("figure_count")
    if not isinstance(count, int) or isinstance(count, bool):
        problems.append("figure_count must be an integer")
    elif count != len(figures):
        problems.append(f"figure_count is {count} but {len(figures)} figures are listed")
    seen = set()
    for i, fig in enumerate(figures):
        if not isinstance(fig, dict):
            problems.append(f"figures[{i}] is not a mapping")
            continue
        where = f"figures[{i}] ({fig.get('file', '?')})"
        for field in FIGURE_FIELDS:
            if field not in fig:
                problems.append(f"{where}: {field} is missing")
        file = fig.get("file")
        if isinstance(file, str):
            if not file.endswith(".png"):
                problems.append(f"{where}: file must be a .png")
            if file.startswith("/") or ".." in file.split("/"):
                problems.append(f"{where}: file must be relative to the repo root")
            if file in seen:
                problems.append(f"{where}: duplicate file")
            seen.add(file)
        size = fig.get("bytes")
        if "bytes" in fig and (not isinstance(size, int) or isinstance(size, bool) or size < 0):
            problems.append(f"{where}: bytes must be a non-negative integer")
        sha = fig.get("sha256")
        if "sha256" in fig and not (isinstance(sha, str) and _SHA256.match(sha)):
            problems.append(f"{where}: sha256 must be 64 lowercase hex characters")
    return problems


def _http_get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return response.read()


def parse(text: str, origin: str, local_root: Path | None = None) -> Manifest:
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ManifestError(f"{origin}: not valid YAML ({exc})") from exc
    problems = validate(doc)
    if problems:
        raise ManifestError(f"{origin}:\n  " + "\n  ".join(problems))
    return Manifest(doc=doc, origin=origin, local_root=local_root)


def load_local(instance: Instance, path: Path | str) -> Manifest:
    """Read a manifest from a local checkout directory or a manifest file."""
    path = Path(path)
    if path.is_dir():
        root, file = path, path / instance.manifest
    else:
        # A file path: the checkout is the directory the manifest path sits under.
        file = path
        depth = len(Path(instance.manifest).parts)
        root = path.resolve().parents[depth - 1] if depth else path.parent
    try:
        text = file.read_text()
    except OSError as exc:
        raise ManifestError(f"{file}: {exc}") from exc
    return parse(text, str(file), local_root=root)


def load_remote(instance: Instance) -> Manifest:
    """Fetch a manifest from the instance's raw GitHub URL."""
    url = instance.manifest_url
    try:
        text = _http_get(url).decode()
    except (urllib.error.URLError, OSError, UnicodeDecodeError) as exc:
        raise ManifestError(f"{url}: unreachable ({exc})") from exc
    return parse(text, url)


def load(instance: Instance, source: Path | str | None = None, offline: bool = False) -> Manifest:
    """Read an instance's manifest.

    ``source`` (a checkout or a manifest file) wins. With ``offline`` and no
    source, the instance's local checkout (see ``Instance.local_checkout``) is
    read instead of the network.
    """
    if source is not None:
        return load_local(instance, source)
    if offline:
        checkout = instance.local_checkout()
        if checkout is None:
            raise ManifestError(
                f"{instance.name}: offline and no local checkout at {instance.path} "
                f"(pass --from {instance.name}=<checkout>)"
            )
        return load_local(instance, checkout)
    return load_remote(instance)


def resolve_figures(instance: Instance, manifest: Manifest) -> list[str]:
    """Check that every listed PNG resolves. Return the problems (empty = all resolve).

    Local manifest: the file exists and its size and sha256 match the manifest.
    Remote manifest: an HTTP HEAD on the raw URL succeeds.
    """
    problems = []
    for fig in manifest.figures:
        if manifest.local_root is not None:
            path = manifest.local_root / fig.file
            if not path.is_file():
                problems.append(
                    f"{instance.name}: {fig.file} is missing from {manifest.local_root}"
                )
                continue
            data = path.read_bytes()
            if len(data) != fig.bytes or hashlib.sha256(data).hexdigest() != fig.sha256:
                problems.append(f"{instance.name}: {fig.file} does not match its manifest entry")
        else:
            url = instance.image_url(fig.file)
            request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})
            try:
                with urllib.request.urlopen(request, timeout=TIMEOUT):
                    pass
            except (urllib.error.URLError, OSError) as exc:
                problems.append(f"{instance.name}: {url} does not resolve ({exc})")
    return problems
