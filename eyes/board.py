"""Build the dashboard (``dashboard.md`` + ``dashboard.html``) from the registry.

For each instance, the board shows the figure count, the stack the figures were
rendered with, the manifest's generated date, freshness against the library's
latest release, the Brain Eyes conductor's survey of the local checkout
(PNGs on disk, gaps, orphans, stale renders), the open PyAutoMind drafts that
mention the instance, and a thumbnail grid. Every thumbnail links to the raw
PNG in the project repo. Each figure carries its critique route: a copyable
``/eyes review <instance> <figure>`` line and a pre-filled "new issue" link on
the project repo. The board embeds no image bytes, copies no files and files
nothing itself. The head of ``dashboard.md`` is a counts table (instances,
figures, behind, critiques) that the Brain board's Eyes strip reads.

The output is deterministic: it has no wall-clock stamp, so a re-render on
unchanged inputs changes nothing and the daily refresh commits nothing. Each
instance section carries an ``eyes:instance`` marker with the manifest digest,
and ``check`` uses that marker to tell whether the committed dashboard is
current.
"""

from __future__ import annotations

import html
import json
import re
import urllib.error
import urllib.parse
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from eyes import ORGAN_ROOT
from eyes import context as context_mod
from eyes import manifest as manifest_mod
from eyes.registry import Instance

PAGES_URL = "https://pyautolabs.github.io/PyAutoEyes/"
PYPI_JSON = "https://pypi.org/pypi/{name}/json"
MARKER = re.compile(r"<!-- eyes:instance name=(\S+) manifest=(\S+) -->")
CRITIQUE_LABEL = "eyes-critique"  # the label the pre-filled issue carries


@dataclass
class InstanceView:
    instance: Instance
    manifest: manifest_mod.Manifest | None
    error: str | None
    latest: str | None  # latest released library version, None if unknown
    context: context_mod.Context = field(default_factory=context_mod.Context)

    @property
    def behind(self) -> bool:
        return self.freshness.startswith("behind")

    @property
    def digest(self) -> str:
        return self.manifest.digest if self.manifest else "unavailable"

    @property
    def rendered(self) -> str | None:
        if not self.manifest:
            return None
        return self.manifest.rendered_with.get(self.instance.import_name)

    @property
    def freshness(self) -> str:
        if not self.manifest:
            return "unknown (no manifest)"
        if self.latest is None:
            return "unknown (release lookup offline)"
        if self.rendered is None:
            return f"unknown (manifest has no {self.instance.import_name} version)"
        if self.rendered == self.latest:
            return f"current ({self.latest})"
        if _version_key(self.rendered) > _version_key(self.latest):
            return f"ahead of release (rendered {self.rendered}, released {self.latest})"
        return f"behind (rendered {self.rendered}, released {self.latest})"


def _version_key(version: str):
    return tuple(int(p) if p.isdigit() else -1 for p in re.split(r"[.+-]", version))


def latest_release(import_name: str) -> str | None:
    """The library's latest version on PyPI, or None when the lookup fails."""
    try:
        data = json.loads(manifest_mod._http_get(PYPI_JSON.format(name=import_name)))
        return str(data["info"]["version"])
    except (urllib.error.URLError, OSError, ValueError, KeyError, TypeError):
        return None


def collect(
    instances,
    sources=None,
    offline=False,
    release_lookup=latest_release,
    context_lookup=None,
    previous=None,
):
    """Read every instance's manifest (and its latest release, when online).

    ``context_lookup(inst, checkout, previous_context)`` returns the
    instance's survey + critiques context (``eyes.context.gather`` in the
    CLI); None skips it, carrying forward whatever ``previous`` (the
    committed dashboard.md text) recorded.
    """
    sources = sources or {}
    before = context_mod.recorded(previous) if previous else {}
    views = []
    for inst in instances:
        try:
            man = manifest_mod.load(inst, sources.get(inst.name), offline=offline)
            error = None
        except manifest_mod.ManifestError as exc:
            man, error = None, str(exc)
        latest = None if offline else release_lookup(inst.import_name)
        prior = before.get(inst.name)
        if context_lookup is not None:
            checkout = _checkout(inst, sources.get(inst.name))
            ctx = context_lookup(inst, checkout, prior)
        else:
            ctx = prior or context_mod.Context()
        views.append(InstanceView(inst, man, error, latest, ctx))
    return views


def _checkout(inst: Instance, source) -> Path | None:
    """The checkout to survey: a ``--from`` checkout dir, else the local one."""
    if source is not None:
        source = Path(source)
        if source.is_dir():
            return source
        depth = len(Path(inst.manifest).parts)
        return source.resolve().parents[depth - 1]
    return inst.local_checkout()


def review_line(inst: Instance, fig) -> str:
    return f"/eyes review {inst.name} {fig.file}"


def issue_title(fig) -> str:
    return f"figure: {fig.domain}/{_figure_label(fig)}"


def issue_body(inst: Instance, man, fig) -> str:
    rendered = man.rendered_with.get(inst.import_name, "unknown")
    return "\n".join(
        [
            f"Figure: `{fig.file}`",
            f"Raw PNG: {inst.image_url(fig.file)}",
            f"Instance: {inst.name} ({inst.github}, manifest `{inst.manifest}`, "
            f"generated {man.generated}, rendered with {inst.import_name} {rendered})",
            f"Producer: `{fig.producer}`",
            "",
            "Suggested improvement:",
            "",
            "",
            "<!-- Say what should change and why. A maintainer turns an accepted "
            "critique into a PyAutoMind intake prompt and routes it through start_dev; "
            f"to review it with Claude, copy: {review_line(inst, fig)} -->",
        ]
    )


def issue_url(inst: Instance, man, fig) -> str:
    """A pre-filled "new issue" link on the project repo. It files nothing."""
    query = urllib.parse.urlencode(
        {
            "title": issue_title(fig),
            "body": issue_body(inst, man, fig),
            "labels": CRITIQUE_LABEL,
        },
        quote_via=urllib.parse.quote,
    )
    return f"{inst.github_url}/issues/new?{query}"


def survey_cell(v) -> str:
    s = v.context.survey
    if s is None:
        return "not run"
    return f"{s.png} png · {len(s.gaps)} gaps · {len(s.orphans)} orphans · {len(s.stale)} stale"


def critiques_count(v) -> str:
    c = v.context.critiques
    return "—" if c is None else str(len(c))


def counts(views) -> list[tuple[str, int]]:
    """The head-of-page counts the Brain board's Eyes strip reads."""
    return [
        ("Instances", len(views)),
        ("Figures", sum(len(v.manifest.figures) for v in views if v.manifest)),
        ("Behind", sum(1 for v in views if v.behind)),
        ("Critiques", sum(len(v.context.critiques or ()) for v in views)),
    ]


def _names(items) -> str:
    return ", ".join(f"`{x}`" for x in items) if items else "none"


def _survey_lines(v) -> list[str]:
    s = v.context.survey
    if s is None:
        return [f"**Survey:** {v.context.survey_note or 'not run'}."]
    per = ", ".join(f"{d} {n}" for d, n in s.domains.items()) or "none"
    lines = [
        f"**Survey** (Brain Eyes conductor, local checkout): {s.png} PNGs on disk ({per}); "
        f"gaps {_names(s.gaps)}; orphans {_names(s.orphans)}; stale renders {_names(s.stale)}."
    ]
    if v.manifest and s.png != len(v.manifest.figures):
        lines.append(
            f"The checkout holds {s.png} PNGs but the manifest lists "
            f"{len(v.manifest.figures)}: re-run the project repo's gallery builder."
        )
    return lines


def _critique_link(v, path: str) -> str:
    base = v.context.mind_url
    return f"{base}/blob/main/{path}" if base else ""


def _grouped(man):
    groups = defaultdict(list)
    for fig in man.figures:
        groups[fig.domain].append(fig)
    return groups


def _figure_label(fig) -> str:
    name = Path(fig.file).name
    return f"{fig.source}/{name}" if fig.source else name


# ------------------------------------------------------------------ markdown ---


def _critique_lines(v) -> list[str]:
    c = v.context.critiques
    if c is None:
        return [f"**Open critiques:** {v.context.critiques_note or 'not read'}."]
    if not c:
        return ["**Open critiques** (PyAutoMind drafts mentioning this instance): none."]
    lines = ["**Open critiques** (PyAutoMind drafts mentioning this instance):", ""]
    for title, path in c:
        link = _critique_link(v, path)
        lines.append(f"- [{title}]({link}) (`{path}`)" if link else f"- {title} (`{path}`)")
    return lines


def render_markdown(views) -> str:
    out = [
        "# PyAutoEyes — visualization dashboard",
        "",
        "<!-- Generated by `bin/pyauto-eyes board` from registry.yaml and each instance's "
        "tracked manifest. Do not edit by hand. -->",
        "",
        "The cross-project view of the organism's figures. Each `<lib>_visualization` "
        "project repo makes, stores and tracks its figures. This page reads each repo's "
        "tracked manifest and links to the PNGs where they live: it copies nothing, "
        "renders nothing and judges nothing.",
        f"Thumbnails and one-tap copy: [{PAGES_URL}]({PAGES_URL}).",
        "",
        "| Where | Count |",
        "|-------|------:|",
        *[f"| [{label}](#instances) | {n} |" for label, n in counts(views)],
        "",
        "## Instances",
        "",
        "| Instance | Library | Figures | Rendered with | Generated | Freshness | Survey "
        "| Critiques | Gallery |",
        "|----------|---------|--------:|---------------|-----------|-----------|--------"
        "|----------:|---------|",
    ]
    for v in views:
        inst = v.instance
        if v.manifest:
            count = str(len(v.manifest.figures))
            rendered = f"`{inst.import_name} {v.rendered}`" if v.rendered else "—"
            generated = v.manifest.generated
        else:
            count, rendered, generated = "—", "—", "—"
        out.append(
            f"| [{inst.name}](#{inst.name}) | {inst.library} | {count} | {rendered} | "
            f"{generated} | {v.freshness} | {survey_cell(v)} | {critiques_count(v)} | "
            f"[{inst.gallery}]({inst.gallery_url}) |"
        )
    out += [
        "",
        "To suggest an improvement to a figure, use its **suggest** link: it opens a "
        f"pre-filled issue on the project repo (label `{CRITIQUE_LABEL}`). Or copy its "
        "`/eyes review` line into a Claude Code session. The dashboard files nothing "
        "itself, and accepted critiques route through PyAutoMind intake to start_dev.",
    ]
    for v in views:
        inst = v.instance
        out += [
            "",
            f"## {inst.name}",
            "",
            f"<!-- eyes:instance name={inst.name} manifest={v.digest} -->",
            context_mod.marker(inst.name, v.context),
            f"{inst.library} figures from [{inst.github}]({inst.github_url}) "
            f"(manifest `{inst.manifest}`; re-rendered on `{inst.dispatch_event}`).",
            "",
        ]
        out += _survey_lines(v) + [""]
        out += _critique_lines(v) + [""]
        if not v.manifest:
            out.append(f"**Manifest unavailable:** {v.error}")
            continue
        stack = ", ".join(f"{k} {val}" for k, val in v.manifest.rendered_with.items())
        out += [f"Rendered with {stack}; generated {v.manifest.generated}.", ""]
        for domain, figs in _grouped(v.manifest).items():
            out += [
                f"### {inst.name} / {domain}",
                "",
                "| Figure | Review | Suggest |",
                "|--------|--------|---------|",
            ]
            for fig in figs:
                out.append(
                    f"| [{_figure_label(fig)}]({inst.image_url(fig.file)}) "
                    f"| `{review_line(inst, fig)}` "
                    f"| [suggest]({issue_url(inst, v.manifest, fig)}) |"
                )
            out.append("")
    return "\n".join(out).rstrip("\n") + "\n"


# ---------------------------------------------------------------------- html ---

CSS = """
:root{--bg:#ffffff;--fg:#1f2328;--muted:#59636e;--card:#f6f8fa;--line:#d1d9e0;
--accent:#7d6300;--hero1:#2e2503;--hero2:#000000;--glow:#ffc933;--ok:#1a7f37;--warn:#9a6700}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#0d1117;--fg:#e6edf3;
--muted:#9198a1;--card:#151b23;--line:#3d444d;--accent:#f5c518;--ok:#3fb950;--warn:#d29922}}
:root[data-theme="dark"]{--bg:#0d1117;--fg:#e6edf3;--muted:#9198a1;--card:#151b23;
--line:#3d444d;--accent:#f5c518;--ok:#3fb950;--warn:#d29922}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif}
main{max-width:1200px;margin:0 auto;padding:0 16px 48px}
.hero{background:radial-gradient(circle at 30% 20%,var(--hero1),var(--hero2));color:#fff;
padding:28px 16px 22px;text-align:center}
.hero h1{margin:0;font-size:28px;letter-spacing:.5px}.hero h1 span{color:var(--glow)}
.hero p{margin:6px 0 0;color:#d8c9bb;font-size:13px;letter-spacing:2px;text-transform:uppercase}
h2,h3{color:var(--accent)}h2{border-bottom:1px solid var(--line);padding-bottom:4px;margin-top:32px}
a{color:var(--accent)}
.lede{color:var(--muted)}
.tablewrap{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:14px}
th,td{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}
.ok{color:var(--ok)}.warn{color:var(--warn)}.muted{color:var(--muted)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:12px}
.fig{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:8px;
display:flex;flex-direction:column;gap:6px;min-width:0}
.fig img{width:100%;height:140px;object-fit:contain;background:#fff;border-radius:4px}
.fig .name{font-size:13px;word-break:break-all}
.fig button{font:12px ui-monospace,SFMono-Regular,Menlo,monospace;text-align:left;
background:var(--bg);color:var(--fg);border:1px solid var(--line);border-radius:6px;
padding:4px 6px;cursor:pointer;word-break:break-all}
.fig button.copied{border-color:var(--ok)}
.fig a.suggest{font-size:12px}
.stats{display:flex;flex-wrap:wrap;gap:12px;margin:16px 0}
.stats div{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:8px 14px}
.stats b{display:block;font-size:20px;color:var(--accent)}.stats span{font-size:12px;color:var(--muted)}
code{color:var(--accent)}
"""

JS = """
document.querySelectorAll('button[data-copy]').forEach(function(b){
  b.addEventListener('click',function(){
    var t=b.getAttribute('data-copy');
    var done=function(){b.classList.add('copied');setTimeout(function(){b.classList.remove('copied')},1200)};
    if(navigator.clipboard){navigator.clipboard.writeText(t).then(done,function(){})}
  });
});
"""


def _e(value) -> str:
    return html.escape(str(value), quote=True)


def _freshness_class(text: str) -> str:
    if text.startswith("current"):
        return "ok"
    if text.startswith("behind"):
        return "warn"
    return "muted"


def _html_survey(v) -> str:
    return "".join(f"<p class='muted'>{_md_inline(line)}</p>" for line in _survey_lines(v))


def _html_critiques(v) -> str:
    c = v.context.critiques
    if not c:
        return f"<p class='muted'>{_md_inline(_critique_lines(v)[0])}</p>"
    items = []
    for title, path in c:
        link = _critique_link(v, path)
        name = f"<a href='{_e(link)}'>{_e(title)}</a>" if link else _e(title)
        items.append(f"<li>{name} <code>{_e(path)}</code></li>")
    return (
        "<p class='muted'><b>Open critiques</b> (PyAutoMind drafts mentioning this instance):</p>"
        f"<ul>{''.join(items)}</ul>"
    )


def _md_inline(text: str) -> str:
    """Escape, then honour the two inline marks the survey lines use."""
    out = _e(text)
    out = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", out)
    return re.sub(r"`(.+?)`", r"<code>\1</code>", out)


def render_html(views) -> str:
    rows = []
    for v in views:
        inst = v.instance
        count = str(len(v.manifest.figures)) if v.manifest else "—"
        rendered = f"{inst.import_name} {v.rendered}" if v.rendered else "—"
        generated = v.manifest.generated if v.manifest else "—"
        rows.append(
            f"<tr><td><a href='#{_e(inst.name)}'>{_e(inst.name)}</a></td><td>{_e(inst.library)}</td>"
            f"<td>{count}</td><td><code>{_e(rendered)}</code></td><td>{_e(generated)}</td>"
            f"<td class='{_freshness_class(v.freshness)}'>{_e(v.freshness)}</td>"
            f"<td>{_e(survey_cell(v))}</td><td>{_e(critiques_count(v))}</td>"
            f"<td><a href='{_e(inst.gallery_url)}'>{_e(inst.gallery)}</a></td></tr>"
        )
    stat_tiles = "".join(
        f"<div><b>{n}</b><span>{_e(label)}</span></div>" for label, n in counts(views)
    )
    sections = []
    for v in views:
        inst = v.instance
        head = (
            f"<h2 id='{_e(inst.name)}'>{_e(inst.name)} · {_e(inst.library)}</h2>"
            f"<p class='lede'>Figures from <a href='{_e(inst.github_url)}'>{_e(inst.github)}</a>, "
            f"manifest <code>{_e(inst.manifest)}</code>, re-rendered on "
            f"<code>{_e(inst.dispatch_event)}</code>.</p>" + _html_survey(v) + _html_critiques(v)
        )
        if not v.manifest:
            sections.append(head + f"<p class='warn'>Manifest unavailable: {_e(v.error)}</p>")
            continue
        stack = ", ".join(f"{k} {val}" for k, val in v.manifest.rendered_with.items())
        body = [
            head,
            f"<p class='muted'>Rendered with {_e(stack)}; generated {_e(v.manifest.generated)}.</p>",
        ]
        for domain, figs in _grouped(v.manifest).items():
            cards = []
            for fig in figs:
                url = inst.image_url(fig.file)
                line = review_line(inst, fig)
                cards.append(
                    "<div class='fig'>"
                    f"<a href='{_e(url)}' target='_blank' rel='noopener'>"
                    f"<img loading='lazy' src='{_e(url)}' alt='{_e(fig.file)}'></a>"
                    f"<span class='name'>{_e(_figure_label(fig))}</span>"
                    f"<button type='button' data-copy='{_e(line)}' title='Copy for Claude'>{_e(line)}</button>"
                    f"<a class='suggest' href='{_e(issue_url(inst, v.manifest, fig))}' "
                    "target='_blank' rel='noopener'>Suggest an improvement</a>"
                    "</div>"
                )
            body.append(f"<h3>{_e(domain)}</h3><div class='grid'>{''.join(cards)}</div>")
        sections.append("".join(body))
    return (
        "<!doctype html>\n<html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>PyAutoEyes dashboard</title>"
        "<!-- Generated by `bin/pyauto-eyes board`. Do not edit by hand. -->"
        f"<style>{CSS}</style></head><body>"
        "<header class='hero'><h1>PyAuto<span>Eyes</span></h1><p>See. Compare. Improve.</p></header>"
        "<main><p class='lede'>The cross-project view of the organism's figures. Each "
        "<code>&lt;lib&gt;_visualization</code> project repo makes, stores and tracks its figures. "
        "This page links to them where they live. Tap a thumbnail for the full-size PNG, "
        "tap its line to copy a review request for Claude, or use "
        "<b>Suggest an improvement</b> to open a pre-filled issue on the project repo "
        f"(label <code>{CRITIQUE_LABEL}</code>). The page files nothing itself.</p>"
        f"<div class='stats'>{stat_tiles}</div>"
        "<div class='tablewrap'><table><thead><tr><th>Instance</th><th>Library</th><th>Figures</th>"
        "<th>Rendered with</th><th>Generated</th><th>Freshness</th><th>Survey</th>"
        "<th>Critiques</th><th>Gallery</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div>"
        f"{''.join(sections)}</main><script>{JS}</script></body></html>\n"
    )


def render_badge(views) -> dict:
    """The one-line headline (shields.io endpoint shape) other boards read."""
    figures = sum(len(v.manifest.figures) for v in views if v.manifest)
    unavailable = sum(1 for v in views if not v.manifest)
    behind = sum(1 for v in views if v.behind)
    if unavailable:
        message, color = f"{unavailable} manifest(s) unavailable", "red"
    elif behind:
        message, color = f"{figures} figures · {behind} behind", "yellow"
    else:
        message, color = f"{figures} figures", "brightgreen"
    return {"schemaVersion": 1, "label": "eyes", "message": message, "color": color}


# -------------------------------------------------------------------- output ---


def write(views, out_dir: Path = ORGAN_ROOT) -> list[Path]:
    out_dir = Path(out_dir)
    md, page, badge = (
        out_dir / "dashboard.md",
        out_dir / "dashboard.html",
        out_dir / "badge.json",
    )
    md.write_text(render_markdown(views))
    page.write_text(render_html(views))
    badge.write_text(json.dumps(render_badge(views), indent=2) + "\n")
    return [md, page, badge]


def markers(text: str) -> dict[str, str]:
    """``{instance name: manifest digest}`` as recorded in a rendered dashboard.md."""
    return dict(MARKER.findall(text))
