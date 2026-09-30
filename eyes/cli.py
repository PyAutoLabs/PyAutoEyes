"""``pyauto-eyes``: the organ's command line (board, check, survey)."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

from eyes import ORGAN_ROOT, board, manifest, registry
from eyes import context as context_mod


def _sources(values, instances) -> dict[str, Path]:
    """Parse ``--from`` values: ``<instance>=<path>``, or a bare ``<path>``.

    A bare path is matched to the instance whose repo name is the path's
    basename, or to the only instance when the registry has just one.
    """
    names = {i.name for i in instances}
    out = {}
    for value in values or []:
        name, sep, path = value.partition("=")
        if sep and name in names:
            out[name] = Path(path).expanduser()
            continue
        path = Path(value).expanduser()
        base = path.resolve().name if path.is_dir() else None
        match = [i.name for i in instances if i.repo == base]
        if not match and len(instances) == 1:
            match = [instances[0].name]
        if len(match) != 1:
            raise SystemExit(f"pyauto-eyes: cannot tell which instance --from {value} is for")
        out[match[0]] = path
    return out


def _load(args):
    instances = registry.load(args.registry)
    return instances, _sources(getattr(args, "sources", None), instances)


def _context_lookup(args, instances=None):
    """The survey + critiques reader for ``board`` (see eyes/context.py)."""
    mind = Path(args.mind).expanduser() if args.mind else True

    def lookup(inst, checkout, previous):
        return context_mod.gather(
            inst,
            checkout,
            previous,
            survey=not args.no_survey,
            mind=mind,
            instances=instances,
        )

    return lookup


def cmd_board(args) -> int:
    instances, sources = _load(args)
    previous_md = Path(args.out) / "dashboard.md"
    views = board.collect(
        instances,
        sources,
        offline=args.offline,
        context_lookup=_context_lookup(args, instances),
        previous=previous_md.read_text() if previous_md.is_file() else None,
    )
    for path in board.write(views, args.out):
        print(f"wrote {path}")
    for v in views:
        if v.error:
            print(f"warning: {v.instance.name}: {v.error}", file=sys.stderr)
        else:
            print(f"{v.instance.name}: {len(v.manifest.figures)} figures; {v.freshness}")
        ctx = v.context
        survey = board.survey_cell(v) if ctx.survey else (ctx.survey_note or "not run")
        critiques = board.critiques_count(v) if ctx.critiques is not None else ctx.critiques_note
        print(f"{v.instance.name}: survey {survey}; critiques {critiques}")
    return 0


def _state_validator():
    """The Brain's cockpit-feed validator (board/_state.py), or None.

    Looked for at $PYAUTO_BRAIN, then beside this organ (flat or grouped
    ``organs/`` layouts both put PyAutoBrain next to PyAutoEyes).
    """
    candidates = []
    if os.environ.get("PYAUTO_BRAIN"):
        candidates.append(Path(os.environ["PYAUTO_BRAIN"]).expanduser())
    candidates.append(ORGAN_ROOT.parent / "PyAutoBrain")
    for root in candidates:
        path = root / "board" / "_state.py"
        if path.is_file():
            spec = importlib.util.spec_from_file_location("_brain_state", path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
    return None


def _check_state(path: Path) -> list[str]:
    """state.json exists, parses, and (when the Brain is here) meets contract v1.

    Its content is not compared to a fresh render: ``updated`` is a render
    stamp, and the badge is not compared either. Staleness is the dashboard
    marker check's job.
    """
    if not path.is_file():
        print("FAIL state: state.json missing — run `pyauto-eyes board`")
        return ["state.json missing"]
    try:
        state = json.loads(path.read_text())
    except ValueError as exc:
        print(f"FAIL state: state.json unreadable ({exc})")
        return [f"state.json unreadable: {exc}"]
    validator = _state_validator()
    if validator is None:
        print("skip state: no PyAutoBrain here to validate state.json (set PYAUTO_BRAIN)")
        return []
    errors = validator.validate_state(state)
    if errors:
        print(f"FAIL state: {'; '.join(errors)}")
        return [f"state.json: {e}" for e in errors]
    print(f"ok   state: valid against the Brain contract ({state['status']}, {state['headline']})")
    return []


def cmd_check(args) -> int:
    problems = []
    try:
        instances, sources = _load(args)
    except registry.RegistryError as exc:
        print(f"FAIL registry: {exc}")
        return 1
    print(f"ok   registry: {len(instances)} instance(s) ({', '.join(i.name for i in instances)})")
    digests = {}
    for inst in instances:
        try:
            man = manifest.load(inst, sources.get(inst.name), offline=args.offline)
        except manifest.ManifestError as exc:
            problems.append(f"{inst.name}: manifest: {exc}")
            print(f"FAIL {inst.name}: manifest: {exc}")
            continue
        digests[inst.name] = man.digest
        print(
            f"ok   {inst.name}: manifest schema {man.schema}, {len(man.figures)} figures ({man.origin})"
        )
        bad = manifest.resolve_figures(inst, man)
        where = "local files match size + sha256" if man.local_root else "raw URLs resolve"
        if bad:
            problems += bad
            print(f"FAIL {inst.name}: {len(bad)} of {len(man.figures)} figures do not resolve")
            for line in bad[:10]:
                print(f"       {line}")
        else:
            print(f"ok   {inst.name}: all {len(man.figures)} figures resolve ({where})")
    out = Path(args.out)
    md, page = out / "dashboard.md", out / "dashboard.html"
    if not md.is_file() or not page.is_file():
        problems.append("dashboard.md / dashboard.html missing")
        print("FAIL dashboard: dashboard.md / dashboard.html missing — run `pyauto-eyes board`")
    else:
        recorded = board.markers(md.read_text())
        stale = sorted(
            n for n in {i.name for i in instances} if n in digests and recorded.get(n) != digests[n]
        )
        extra = sorted(set(recorded) - {i.name for i in instances})
        if stale or extra:
            problems.append(f"dashboard stale: {stale + extra}")
            print(f"FAIL dashboard: stale for {', '.join(stale + extra)} — run `pyauto-eyes board`")
        else:
            print("ok   dashboard: current with every manifest")
    problems += _check_state(out / "state.json")
    print("check: " + ("FAIL" if problems else "OK"))
    return 1 if problems else 0


def _brain_cli() -> list[str]:
    found = context_mod.brain_cli()
    if not found:
        raise SystemExit("pyauto-eyes: cannot find pyauto-brain (set PYAUTO_BRAIN)")
    return found


def cmd_survey(args) -> int:
    instances = registry.load(args.registry)
    if args.all:
        chosen = instances
    elif args.instance:
        chosen = [registry.get(instances, args.instance)]
    elif len(instances) == 1:
        chosen = instances
    else:
        raise SystemExit("pyauto-eyes survey: name an instance or pass --all")
    brain = _brain_cli()
    rc = 0
    for inst in chosen:
        checkout = inst.local_checkout()
        if checkout is None:
            print(f"{inst.name}: no local checkout at {inst.path} — skipped", file=sys.stderr)
            rc = 1
            continue
        print(f"== {inst.name}: pyauto-brain eyes survey {checkout}", flush=True)
        rc |= subprocess.call([*brain, "eyes", "survey", str(checkout)])
    return rc


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="pyauto-eyes",
        description="PyAutoEyes: the cross-project visualization dashboard organ.",
    )
    parser.add_argument("--registry", default=str(registry.REGISTRY_PATH), help=argparse.SUPPRESS)
    sub = parser.add_subparsers(dest="cmd", required=True)

    def reading(p):
        p.add_argument(
            "--offline",
            action="store_true",
            help="read manifests from local checkouts, never the network",
        )
        p.add_argument(
            "--from",
            dest="sources",
            action="append",
            metavar="[INSTANCE=]PATH",
            help="read an instance's manifest from this checkout or manifest file",
        )
        p.add_argument("--out", default=str(ORGAN_ROOT), help=argparse.SUPPRESS)

    p = sub.add_parser(
        "board", help="render dashboard.md + dashboard.html + badge.json + state.json"
    )
    reading(p)
    p.add_argument(
        "--no-survey",
        action="store_true",
        help="do not run the Brain Eyes survey (carry the last recorded one forward)",
    )
    p.add_argument(
        "--mind",
        metavar="PATH",
        help="the PyAutoMind checkout to read open critiques from "
        "(default: $PYAUTO_MIND, else beside this organ)",
    )
    p.set_defaults(func=cmd_board)
    p = sub.add_parser(
        "check",
        help="registry valid, manifests parse, every PNG resolves, dashboard current",
    )
    reading(p)
    p.set_defaults(func=cmd_check)
    p = sub.add_parser("survey", help="run the Brain Eyes survey on registered instances")
    p.add_argument("instance", nargs="?")
    p.add_argument("--all", action="store_true")
    p.set_defaults(func=cmd_survey)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except registry.RegistryError as exc:
        print(f"pyauto-eyes: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
