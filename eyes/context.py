"""Per-instance context the dashboard shows beside the figures.

Two readings, both local and both optional:

* **survey**: the Brain Eyes conductor's ``EyesSurvey`` of the instance's
  local checkout (``pyauto-brain eyes --json survey <checkout>``), reduced to
  what the dashboard shows: PNGs on disk per domain, never-rendered gaps,
  orphan image trees and stale renders. The organ does not re-derive any of
  it. It only asks the conductor.
* **critiques**: the open PyAutoMind drafts (``draft/**/*.md``) that mention
  the instance, as ``(title, path)``. Titles only, and the dashboard links to
  each draft on GitHub.

A reading that cannot run here, because there is no checkout, no Brain or no
Mind (as on the CI runner that refreshes the dashboard), is **carried forward**
from the committed dashboard. Each instance section records its context in an
``<!-- eyes:context name=… {json} -->`` marker, so a render without the local
inputs reproduces the last local reading rather than erasing it. The
dashboard therefore stays deterministic and never flaps between a laptop render
and a CI render.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from eyes import ORGAN_ROOT
from eyes.registry import Instance, workspace_roots

MIND_REPO = "PyAutoMind"  # an organ name, not an instance fact
CONTEXT_MARKER = re.compile(r"<!-- eyes:context name=(\S+) (\{.*?\}) -->")
SURVEY_TIMEOUT = 120


@dataclass
class Survey:
    """The conductor's survey of one checkout, as the dashboard shows it."""

    domains: dict[str, int] = field(default_factory=dict)  # domain -> PNGs on disk
    gaps: list[str] = field(default_factory=list)
    orphans: list[str] = field(default_factory=list)
    stale: list[str] = field(default_factory=list)

    @property
    def png(self) -> int:
        return sum(self.domains.values())

    def to_json(self) -> dict:
        return {
            "domains": self.domains,
            "gaps": self.gaps,
            "orphans": self.orphans,
            "stale": self.stale,
        }

    @classmethod
    def from_json(cls, doc: dict) -> Survey:
        return cls(
            domains={str(k): int(v) for k, v in (doc.get("domains") or {}).items()},
            gaps=[str(x) for x in doc.get("gaps") or []],
            orphans=[str(x) for x in doc.get("orphans") or []],
            stale=[str(x) for x in doc.get("stale") or []],
        )

    @classmethod
    def from_eyes_survey(cls, doc: dict) -> Survey:
        """Reduce a conductor ``EyesSurvey`` (never its paths or mtimes)."""
        domains: dict[str, int] = {}
        for rec in doc.get("records") or []:
            domains[rec["domain"]] = domains.get(rec["domain"], 0) + int(rec.get("n_png", 0))
        return cls(
            domains=dict(sorted(domains.items())),
            gaps=sorted(doc.get("gaps") or []),
            orphans=sorted(doc.get("orphans") or []),
            stale=sorted(doc.get("stale_renders") or []),
        )


@dataclass
class Context:
    survey: Survey | None = None
    survey_note: str = ""  # why there is no survey, when there is none
    critiques: list[tuple[str, str]] | None = None  # (title, Mind-relative path)
    critiques_note: str = ""
    mind_url: str | None = None  # https://github.com/<owner>/PyAutoMind, when known

    def to_json(self) -> dict:
        return {
            "survey": self.survey.to_json() if self.survey else None,
            "survey_note": self.survey_note,
            "critiques": [list(c) for c in self.critiques] if self.critiques is not None else None,
            "critiques_note": self.critiques_note,
            "mind_url": self.mind_url,
        }

    @classmethod
    def from_json(cls, doc: dict) -> Context:
        survey = doc.get("survey")
        critiques = doc.get("critiques")
        return cls(
            survey=Survey.from_json(survey) if isinstance(survey, dict) else None,
            survey_note=str(doc.get("survey_note") or ""),
            critiques=[(str(t), str(p)) for t, p in critiques]
            if isinstance(critiques, list)
            else None,
            critiques_note=str(doc.get("critiques_note") or ""),
            mind_url=doc.get("mind_url") or None,
        )


def marker(name: str, ctx: Context) -> str:
    # "--" may not appear inside an HTML comment; - is the same JSON text.
    blob = json.dumps(ctx.to_json(), sort_keys=True, separators=(",", ":"))
    blob = blob.replace("--", "-\\u002d")
    return f"<!-- eyes:context name={name} {blob} -->"


def recorded(text: str) -> dict[str, Context]:
    """``{instance: Context}`` from a rendered dashboard.md's context markers."""
    out = {}
    for name, blob in CONTEXT_MARKER.findall(text or ""):
        try:
            out[name] = Context.from_json(json.loads(blob))
        except (ValueError, TypeError, AttributeError):
            continue
    return out


# --------------------------------------------------------------- survey ---


def brain_cli() -> list[str] | None:
    """The ``pyauto-brain`` to ask, or None when there is none here."""
    candidates = []
    if os.environ.get("PYAUTO_BRAIN"):
        candidates.append(Path(os.environ["PYAUTO_BRAIN"]) / "bin" / "pyauto-brain")
    candidates.append(ORGAN_ROOT.parent / "PyAutoBrain" / "bin" / "pyauto-brain")
    for c in candidates:
        if c.is_file():
            return [str(c)]
    found = shutil.which("pyauto-brain")
    return [found] if found else None


def run_survey(checkout: Path, brain: list[str] | None = None) -> tuple[Survey | None, str]:
    """Ask the Brain Eyes conductor to survey ``checkout``: (survey, note)."""
    brain = brain if brain is not None else brain_cli()
    if not brain:
        return None, "no pyauto-brain here (set PYAUTO_BRAIN)"
    try:
        proc = subprocess.run(
            [*brain, "eyes", "--json", "survey", str(checkout)],
            capture_output=True,
            text=True,
            timeout=SURVEY_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"pyauto-brain eyes survey failed ({exc})"
    if proc.returncode != 0:
        why = (proc.stderr or proc.stdout).strip().splitlines()
        return None, f"pyauto-brain eyes survey exited {proc.returncode}" + (
            f": {why[-1]}" if why else ""
        )
    try:
        return Survey.from_eyes_survey(json.loads(proc.stdout)), ""
    except (ValueError, KeyError, TypeError) as exc:
        return None, f"unreadable EyesSurvey ({exc})"


# ------------------------------------------------------------ critiques ---


def mind_root(root: Path | None = None) -> Path | None:
    """The PyAutoMind checkout: ``$PYAUTO_MIND``, else beside this organ or
    under a workspace root (grouped ``organs/`` or flat)."""
    env = os.environ.get("PYAUTO_MIND")
    if env:
        path = Path(env).expanduser()
        return path if (path / "draft").is_dir() else None
    bases = [ORGAN_ROOT.parent, *workspace_roots(root)]
    for base in bases:
        for candidate in (base / MIND_REPO, base / "organs" / MIND_REPO):
            if (candidate / "draft").is_dir():
                return candidate
    return None


def mind_github_url(mind: Path) -> str | None:
    """``https://github.com/<owner>/<repo>`` from the Mind checkout's origin."""
    try:
        url = subprocess.run(
            ["git", "-C", str(mind), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(r"github\.com[:/]([^/\s]+)/([^/\s]+?)(?:\.git)?$", url)
    return f"https://github.com/{m[1]}/{m[2]}" if m else None


def _title(text: str, fallback: str) -> str:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def find_critiques(mind: Path, inst: Instance) -> list[tuple[str, str]]:
    """Open Mind drafts that mention the instance: its repo name, or a
    ``/eyes review <instance> `` line. Sorted by path."""
    needles = (inst.repo.lower(), f"/eyes review {inst.name} ")
    found = []
    for path in sorted((mind / "draft").rglob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        low = text.lower()
        if any(n in low for n in needles):
            rel = path.relative_to(mind).as_posix()
            found.append((_title(text, path.stem), rel))
    return found


# --------------------------------------------------------------- gather ---


def gather(
    inst: Instance,
    checkout: Path | None,
    previous: Context | None = None,
    survey: bool = True,
    mind: Path | None | bool = True,
    brain: list[str] | None = None,
) -> Context:
    """Read an instance's context, carrying forward what cannot be read here.

    ``checkout`` is the instance's local checkout (None when absent);
    ``mind`` is a Mind checkout, True to resolve one, or False/None to skip.
    """
    ctx = Context()
    if survey and checkout is not None:
        ctx.survey, ctx.survey_note = run_survey(checkout, brain)
    elif not survey:
        ctx.survey_note = "not run (--no-survey)"
    else:
        ctx.survey_note = f"not run: no local checkout of {inst.path}"
    if ctx.survey is None and previous is not None and previous.survey is not None:
        ctx.survey, ctx.survey_note = previous.survey, previous.survey_note

    mind_path = mind_root() if mind is True else (mind or None)
    if mind_path is not None:
        ctx.critiques = find_critiques(mind_path, inst)
        ctx.mind_url = mind_github_url(mind_path)
    elif previous is not None and previous.critiques is not None:
        ctx.critiques, ctx.mind_url = previous.critiques, previous.mind_url
        ctx.critiques_note = previous.critiques_note
    else:
        ctx.critiques_note = "not read: no PyAutoMind checkout here"
    return ctx
