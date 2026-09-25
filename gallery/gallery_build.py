"""
Gallery: Visualization Contact Sheet, Manifest and GALLERY.md
=============================================================

Builds the three views of every figure the ``scripts/<domain>/visualization*.py``
producers have written under ``scripts/<domain>/images/<script>/**``:

    GALLERY.md                        — TRACKED, GitHub-navigable markdown gallery
                                        (relative image links; domain -> script ->
                                        group -> figure; table of contents; header
                                        with the PyAutoLens version + figure count)
    output/gallery/gallery.html       — contact sheet (gitignored), Eyes-agent contract
    output/gallery/viz_manifest.yaml  — {domain: {script: [{file, kind, group}]}}
                                        (gitignored), Eyes-agent contract

Adapted from ``autolens_workspace_test/gallery/gallery_build.py``; the GALLERY.md
writer and its staleness check are new here.

Usage (from the repo root):

    python gallery/gallery_build.py           # build all three
    python gallery/gallery_build.py --check   # rebuild output/gallery/, then FAIL if
                                              # the committed GALLERY.md differs from
                                              # what would be regenerated, or any
                                              # manifest entry does not resolve
    python gallery/gallery_build.py --embed   # also write a self-contained
                                              # output/gallery/gallery_embedded.html

``--check`` never rewrites GALLERY.md. It compares everything except the version
header line (``Rendered with PyAutoLens ...``), so a PR built against library mains
is not failed by the version string the released-stack render workflow stamped; the
figure set, grouping and links must match exactly. There is no timestamp anywhere.
"""

from __future__ import annotations

import argparse
import base64
import html
import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]

GALLERY_MD = "GALLERY.md"
VERSION_LINE_PREFIX = "Rendered with PyAutoLens"

CSS = """
body { font-family: sans-serif; margin: 1.5rem; background: #111; color: #ddd; }
h1 { font-size: 1.4rem; } h2 { font-size: 1.2rem; border-bottom: 1px solid #444; padding-bottom: 0.2rem; margin-top: 2rem; }
h3 { font-size: 1.0rem; color: #aaa; margin-top: 1.2rem; }
.grid { display: flex; flex-wrap: wrap; gap: 0.8rem; }
figure { margin: 0; width: 320px; }
figure img { width: 100%; background: #fff; border-radius: 4px; }
figcaption { font-size: 0.75rem; color: #999; word-break: break-all; padding-top: 0.2rem; }
.counts { color: #888; font-size: 0.85rem; }
"""


def scan_images(root: Path = REPO_ROOT) -> dict:
    """Manifest dict from the on-disk image trees: domain -> script -> entries.

    ``group`` is the sub-directory within the script's image dir (e.g. the per-source
    subfolders ``parametric`` / ``delaunay``), "" at the top level. Paths are POSIX and
    relative to ``root``.
    """
    manifest: dict = {}
    for images_dir in sorted(root.glob("scripts/*/images")):
        domain = images_dir.parent.name
        for script_dir in sorted(p for p in images_dir.iterdir() if p.is_dir()):
            entries = []
            for f in sorted(script_dir.rglob("*")):
                if f.suffix not in (".png", ".fits"):
                    continue
                group = f.parent.relative_to(script_dir).as_posix()
                entries.append(
                    {
                        "file": f.relative_to(root).as_posix(),
                        "kind": f.suffix.lstrip("."),
                        "group": "" if group == "." else group,
                    }
                )
            if entries:
                manifest.setdefault(domain, {})[script_dir.name] = entries
    return manifest


def _pngs(entries):
    return [e for e in entries if e["kind"] == "png"]


def _count(manifest, kind):
    return sum(
        1
        for scripts in manifest.values()
        for es in scripts.values()
        for e in es
        if e["kind"] == kind
    )


def render_html(manifest: dict, root: Path = REPO_ROOT, embed: bool = False) -> str:
    lines = [
        "<meta charset='utf-8'><title>PyAutoLens Visualization Gallery</title>",
        f"<style>{CSS}</style>",
        "<h1>PyAutoLens Visualization Gallery</h1>",
        f"<p class='counts'>{_count(manifest, 'png')} figures (.png) · "
        f"{_count(manifest, 'fits')} data products (.fits, listed in the manifest only) · "
        f"source: <code>scripts/&lt;domain&gt;/images/</code></p>",
    ]
    for domain, scripts in manifest.items():
        lines.append(f"<h2>{html.escape(domain)}</h2>")
        for script, entries in scripts.items():
            pngs = _pngs(entries)
            if not pngs:
                continue
            lines.append(f"<h3>{html.escape(script)} ({len(pngs)} figures)</h3>")
            lines.append("<div class='grid'>")
            for e in pngs:
                if embed:
                    data = base64.b64encode((root / e["file"]).read_bytes()).decode()
                    src = f"data:image/png;base64,{data}"
                else:
                    src = "../../" + e["file"]
                caption = (e["group"] + "/" if e["group"] else "") + Path(e["file"]).name
                lines.append(
                    f"<figure><img loading='lazy' src='{html.escape(src)}'>"
                    f"<figcaption>{html.escape(caption)}</figcaption></figure>"
                )
            lines.append("</div>")
    return "\n".join(lines) + "\n"


def _anchor(text: str) -> str:
    """GitHub's heading-anchor slug: lowercase, drop punctuation, spaces -> '-'."""
    slug = re.sub(r"[^\w\- ]", "", text.strip().lower())
    return slug.replace(" ", "-")


def _group_title(group: str) -> str:
    return f"{group}/" if group else "top level"


def render_markdown(manifest: dict, version: str) -> str:
    """The tracked GALLERY.md: one H2 per domain, H3 per script, H4 per group, H5 per
    figure. Headings carry a ``domain / script`` prefix so every anchor is unique."""
    n_png = _count(manifest, "png")
    lines = [
        "# PyAutoLens Visualization Gallery",
        "",
        "<!-- Generated by gallery/gallery_build.py from scripts/<domain>/images/. "
        "Do not edit by hand: rerun `bash gallery/gallery_run.sh --all`. -->",
        "",
        f"{VERSION_LINE_PREFIX} `{version}` · {n_png} figures.",
        "",
        "Every figure below is what `VisualizerImaging` / `VisualizerInterferometer` write "
        "to a model-fit's `image/` folder, rendered on this repo's datasets with the true "
        "model. See [README.md](README.md) for how to improve one.",
        "",
        "## Contents",
        "",
    ]
    body: list[str] = []
    for domain, scripts in manifest.items():
        lines.append(f"- [{domain}](#{_anchor(domain)})")
        body += ["", f"## {domain}"]
        for script, entries in scripts.items():
            pngs = _pngs(entries)
            if not pngs:
                continue
            h3 = f"{domain} / {script}"
            lines.append(f"  - [{script}](#{_anchor(h3)}) ({len(pngs)} figures)")
            body += ["", f"### {h3}"]
            groups: dict[str, list] = {}
            for e in pngs:
                groups.setdefault(e["group"], []).append(e)
            for group in sorted(groups, key=lambda g: (g != "", g)):
                h4 = f"{domain} / {script} / {_group_title(group)}"
                lines.append(f"    - [{_group_title(group)}](#{_anchor(h4)})")
                body += ["", f"#### {h4}"]
                for e in groups[group]:
                    name = Path(e["file"]).stem
                    body += ["", f"##### {name}", "", f"![{name}]({e['file']})"]
    return "\n".join(lines + body) + "\n"


def _normalise_version_line(text: str) -> str:
    return "\n".join(
        f"{VERSION_LINE_PREFIX} <version>" + line.split("`", 2)[-1]
        if line.startswith(VERSION_LINE_PREFIX)
        else line
        for line in text.splitlines()
    )


def autolens_version() -> str:
    try:
        import autolens

        return autolens.__version__
    except Exception:  # noqa: BLE001 — a missing stack must not block a --check
        return "unknown"


def check(manifest: dict, root: Path = REPO_ROOT) -> list[str]:
    """Problems: unresolvable manifest entries, on-disk images missing from the
    manifest, and a committed GALLERY.md that differs from a regeneration."""
    problems = []
    listed = set()
    for scripts in manifest.values():
        for entries in scripts.values():
            for e in entries:
                listed.add(e["file"])
                if not (root / e["file"]).is_file():
                    problems.append(f"manifest entry missing on disk: {e['file']}")
    on_disk = {
        f.relative_to(root).as_posix()
        for f in root.glob("scripts/*/images/**/*")
        if f.suffix in (".png", ".fits")
    }
    for f in sorted(on_disk - listed):
        problems.append(f"on disk but not in manifest: {f}")

    md_path = root / GALLERY_MD
    if not md_path.is_file():
        problems.append(f"{GALLERY_MD} missing — run python gallery/gallery_build.py")
    else:
        expected = render_markdown(manifest, version="<version>")
        if _normalise_version_line(md_path.read_text()) != _normalise_version_line(expected):
            problems.append(
                f"{GALLERY_MD} is stale (figure set changed) — rerun "
                "python gallery/gallery_build.py and commit it"
            )
    return problems


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--embed", action="store_true")
    parser.add_argument(
        "--root", type=Path, default=REPO_ROOT, help="Repo root to scan (default: this repo)."
    )
    parser.add_argument(
        "--version-string",
        default=None,
        help="PyAutoLens version for the GALLERY.md header (default: autolens.__version__).",
    )
    args = parser.parse_args(argv)
    root = args.root.resolve()

    manifest = scan_images(root)
    if not manifest:
        print("No images found under scripts/*/images — run gallery/gallery_run.sh first.")
        return 1

    gallery_path = root / "output" / "gallery"
    gallery_path.mkdir(parents=True, exist_ok=True)
    (gallery_path / "viz_manifest.yaml").write_text(yaml.safe_dump(manifest, sort_keys=True))
    (gallery_path / "gallery.html").write_text(render_html(manifest, root))
    if args.embed:
        (gallery_path / "gallery_embedded.html").write_text(render_html(manifest, root, embed=True))

    if not args.check:
        version = args.version_string or autolens_version()
        (root / GALLERY_MD).write_text(render_markdown(manifest, version))

    for domain, scripts in manifest.items():
        for script, entries in scripts.items():
            n_png = sum(1 for e in entries if e["kind"] == "png")
            n_fits = sum(1 for e in entries if e["kind"] == "fits")
            print(f"{domain}/{script}: {n_png} png, {n_fits} fits")
    print(f"\nGallery:  {gallery_path / 'gallery.html'}")
    print(f"Manifest: {gallery_path / 'viz_manifest.yaml'}")
    if not args.check:
        print(f"Markdown: {root / GALLERY_MD}")

    if args.check:
        problems = check(manifest, root)
        if problems:
            print("\nCHECK FAILED:")
            for p in problems:
                print(f"  {p}")
            return 1
        print("check: manifest resolves on disk and GALLERY.md is current.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
