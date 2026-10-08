"""Build the dashboard (``dashboard.md`` + ``dashboard.html``, plus ``badge.json``
and the ``state.json`` organ-cockpit feed) from the registry.

The overview shows figure counts, rendering versions and concise freshness.
Library and dataset disclosures lead to a single selected figure, loaded on demand
and enlarged within the dashboard. Its review prompt and suggestion link always
follow the selection. Figures remain hosted in their project repositories.
Survey evidence is preserved in the context markers and machine-readable feeds.
The head of ``dashboard.md`` retains the counts table consumed by Brain.

The output is deterministic: the pages have no wall-clock stamp, and
``state.json``'s ``updated`` stamp moves only when the feed's content does, so
a re-render on unchanged inputs changes nothing and the daily refresh commits
nothing. Each
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
from datetime import UTC, datetime
from pathlib import Path

from eyes import ORGAN_ROOT
from eyes import context as context_mod
from eyes import manifest as manifest_mod
from eyes.registry import Instance
from eyes.theme import theme

PAGES_URL = "https://pyautolabs.github.io/PyAutoEyes/"
PYPI_JSON = "https://pypi.org/pypi/{name}/json"
MARKER = re.compile(r"<!-- eyes:instance name=(\S+) manifest=(\S+) -->")
CRITIQUE_LABEL = "eyes-critique"  # the label the pre-filled issue carries
STATE_SCHEMA_VERSION = 1  # the organ-cockpit feed contract (PyAutoBrain/board/state_schema.json)

CHECKIN_PROMPT = (
    "Use the eyes skill and treat this chat as an ongoing place to inspect and improve "
    "figures across PyAutoLabs. Read PyAutoEyes/AGENTS.md, its registry and the relevant "
    "project manifests and review records. Check figure availability, rendering versions and "
    "freshness before drawing conclusions.\n\n"
    "When I give no particular direction, review registered visualization projects for stale "
    "or missing figures, coverage gaps, orphan figures and outstanding critiques. Summarize "
    "each project’s position and suggest a manageable set of figures to review together.\n\n"
    "When I name a figure, project or presentation concern, make that the main focus. Open "
    "and inspect the actual images. Help me assess readability, layout, labels, units, "
    "legends, color scales, consistency and suitability for the intended audience. Bring in "
    "related figures where comparison helps; do not repeat the full project review on every "
    "follow-up.\n\n"
    "Discuss what we see and turn my feedback into specific proposed changes. Distinguish "
    "visible presentation problems from suspected data or scientific issues that need "
    "separate investigation. Do not infer scientific correctness from appearance alone.\n\n"
    "Help me refine a critique, compare alternative presentations or define what an improved "
    "figure should achieve. Keep suggestions distinct from changes I have accepted. Link each "
    "accepted critique to the relevant figure, producer and evidence.\n\n"
    "Keep figure production and rendering in the visualization project repositories, with "
    "Brain responsible for critique judgment. Route accepted implementation through intake "
    "and the development workflow, checking existing critiques and tasks before creating "
    "overlapping work. Launch renders when requested or required by an approved "
    "implementation and validation plan.\n\n"
    "Carry clearly authorized work through its workflow, retaining approvals already given in "
    "this conversation. After changes, inspect the rendered output and compare it with the "
    "agreed criteria. Report what improved, what was verified and what still needs attention."
)


@dataclass
class InstanceView:
    instance: Instance
    manifest: manifest_mod.Manifest | None
    error: str | None
    latest: str | None  # latest released library version, None if unknown
    context: context_mod.Context = field(default_factory=context_mod.Context)

    captured_at: str | None = None  # successful manifest collection, never figure evidence

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
    captured_at=None,
):
    """Read every instance's manifest (and its latest release, when online).

    ``context_lookup(inst, checkout, previous_context)`` returns the
    instance's survey + critiques context (``eyes.context.gather`` in the
    CLI); None skips it, carrying forward whatever ``previous`` (the
    committed dashboard.md text) recorded.
    """
    capture_time = captured_at or _utc_now()
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
        views.append(InstanceView(inst, man, error, latest, ctx, capture_time if man else None))
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
    return f"Use the eyes skill. review {inst.name} {fig.file}"


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
            f"to review it with an AI assistant, copy: {review_line(inst, fig)} -->",
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
        return []
    lines = ["**Open critiques:**", ""]
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
        f"[Dashboard]({PAGES_URL})",
        "",
        "| Where | Count |",
        "|-------|------:|",
        *[f"| [{label}](#instances) | {n} |" for label, n in counts(views)],
        "",
        "## Instances",
        "",
        "| Library | Figures | Rendered with | Freshness |",
        "|---------|--------:|---------------|-----------|",
    ]
    for v in views:
        inst = v.instance
        count = str(len(v.manifest.figures)) if v.manifest else "—"
        rendered = f"`{v.rendered}`" if v.rendered else "—"
        out.append(
            f"| [{inst.library}](#{inst.name}) | {count} | {rendered} | {compact_freshness(v)} |"
        )
    for v in views:
        inst = v.instance
        out += [
            "",
            f'<a id="{_e(inst.name)}"></a>',
            "",
            f"## {inst.library}",
            "",
            f"<!-- eyes:instance name={inst.name} manifest={v.digest} -->",
            context_mod.marker(inst.name, v.context),
            "",
        ]
        out += _critique_lines(v) + [""]
        if not v.manifest:
            out.append(f"**Manifest unavailable:** {v.error}")
            continue
        for domain, figs in _grouped(v.manifest).items():
            out += [
                f"### {domain}",
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
main{padding-bottom:48px}
h2,h3{color:var(--accent)}h2{border-bottom:1px solid var(--line);padding-bottom:4px;margin-top:32px}
a{color:var(--accent)}
.lede{color:var(--muted)}
.tablewrap{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:14px}
th,td{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}
.ok{color:var(--ok)}.warn{color:var(--warn)}.muted{color:var(--muted)}
.dataset{margin:12px 0;min-width:0}
.dataset>summary{cursor:pointer;padding:12px;font-weight:600}
.figure-browser{padding:12px;min-width:0}
.figure-browser select{display:block;width:100%;max-width:100%;min-width:0;margin:8px 0 16px;
font:inherit;padding:10px;background:var(--card);color:var(--fg);border:1px solid var(--line)}
.figure-image{display:block;width:100%;padding:0;border:0;background:#fff;cursor:zoom-in}
.figure-image img{display:block;width:100%;max-height:75vh;object-fit:contain}
.figure-actions{display:flex;flex-wrap:wrap;align-items:center;gap:12px;margin:12px 0}
.figure-actions button,.figure-dialog button{font:inherit;padding:10px;cursor:pointer;
background:var(--card);color:var(--fg);border:1px solid var(--line);border-radius:6px}
.figure-actions button.copied{border-color:var(--ok)}
.figure-dialog{box-sizing:border-box;width:calc(100% - 24px);max-width:1600px;
max-height:calc(100dvh - 24px);padding:12px;background:var(--bg);color:var(--fg);
border:1px solid var(--line);overflow:auto}
.figure-dialog::backdrop{background:#000b}
.figure-dialog img{display:block;width:100%;height:auto;background:white}
.figure-dialog header{display:flex;justify-content:space-between;align-items:center;gap:12px}
.figure-dialog h2{margin:0;font-size:1rem;border:0;overflow-wrap:anywhere}
[hidden]{display:none!important}
.stats{display:flex;flex-wrap:wrap;gap:12px;margin:16px 0}
.stats div{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:8px 14px}
.stats b{display:block;font-size:20px;color:var(--accent)}.stats span{font-size:12px;color:var(--muted)}
code{color:var(--accent)}
"""

# Match the shared theme clipboard budget while retaining the figure-copy controls.
MAX_PROMPT_CHARS = 50_000
JS = """
document.querySelectorAll('button[data-copy]').forEach(function(b){
  b.addEventListener('click',function(){
    var t=b.getAttribute('data-copy');
    if(Array.from(t).length>__MAX_PROMPT_CHARS__){
      var status=b.parentNode.querySelector('.copy-budget');
      if(!status){status=document.createElement('p');status.className='copy-budget';
        status.setAttribute('role','status');b.insertAdjacentElement('afterend',status);}
      if(status.dataset.url)URL.revokeObjectURL(status.dataset.url);
      status.textContent='Not copied: request exceeds 50,000 characters. '+
        'Download the complete request and attach it to your coding chat. ';
      var link=document.createElement('a');
      link.href=URL.createObjectURL(new Blob([t],{type:'text/plain;charset=utf-8'}));
      status.dataset.url=link.href;link.download='dashboard-request.txt';
      link.textContent='Download complete request';status.appendChild(link);return;
    }
    var done=function(){b.classList.add('copied');setTimeout(function(){b.classList.remove('copied')},1200)};
    if(navigator.clipboard){navigator.clipboard.writeText(t).then(done,function(){})}
  });
});
""".replace("__MAX_PROMPT_CHARS__", str(MAX_PROMPT_CHARS))


VIEWER_JS = """
(function(){
  var dialog=document.querySelector('.figure-dialog');
  var opener;
  var close=dialog.querySelector('button');
  close.addEventListener('click',function(){dialog.close()});
  // Keep keyboard focus inside the modal even when the board is embedded.
  dialog.addEventListener('keydown',function(event){
    if(event.key==='Tab'){event.preventDefault();close.focus()}
  });
  dialog.addEventListener('close',function(){
    dialog.querySelector('img').removeAttribute('src');
    if(opener)opener.focus();
  });
  document.querySelectorAll('.figure-browser').forEach(function(browser){
    var select=browser.querySelector('select');
    var image=browser.querySelector('.figure-image img');
    var imageButton=browser.querySelector('.figure-image');
    var status=browser.querySelector('[role=status]');
    var actions=browser.querySelector('.figure-actions');
    var copy=actions.querySelector('[data-copy]');
    var suggest=actions.querySelector('.suggest');
    var retry=browser.querySelector('.figure-retry');
    var revision=0;
    function loadSelected(){
      var option=select.selectedOptions[0];
      var current=++revision;
      imageButton.hidden=true;actions.hidden=true;retry.hidden=true;
      image.removeAttribute('src');
      if(!option.value){status.textContent='Choose a figure to view.';return}
      copy.dataset.copy=option.dataset.review;
      copy.title=option.dataset.review;
      suggest.href=option.dataset.suggest;
      actions.hidden=false;
      status.textContent='Loading figure…';
      // A new image object prevents an older response from replacing a newer selection.
      var next=new Image();
      next.alt=option.textContent;
      next.onload=function(){
        if(current!==revision)return;
        image.replaceWith(next);image=next;imageButton.hidden=false;
        status.textContent='Click the image to enlarge.';
      };
      next.onerror=function(){
        if(current!==revision)return;
        status.textContent='Could not load this figure.';retry.hidden=false;
      };
      next.src=option.value;
    }
    select.addEventListener('change',loadSelected);
    retry.addEventListener('click',loadSelected);
    imageButton.addEventListener('click',function(){
      opener=imageButton;
      dialog.querySelector('h2').textContent=image.alt;
      var enlarged=dialog.querySelector('img');
      enlarged.alt=image.alt;enlarged.src=image.src;
      dialog.showModal();
    });
  });
  // One dataset viewer at a time, including across different libraries.
  document.querySelectorAll('.dataset').forEach(function(dataset){
    dataset.addEventListener('toggle',function(){
      if(dataset.open)document.querySelectorAll('.dataset').forEach(function(other){
        if(other!==dataset)other.open=false;
      });
    });
  });
})();
"""


def compact_freshness(view) -> str:
    """Presentation only: retain detailed evidence in the state feed."""
    return {"current": "Current", "behind": "Behind", "ahead": "Ahead"}.get(
        view.freshness.split()[0], "Unknown"
    )


def _figure_browser(inst, man, domain, figs, identifier):
    options = ["<option value=''>Choose a figure…</option>"]
    fallback = []
    for fig in figs:
        url = _e(inst.image_url(fig.file))
        label = _e(_figure_label(fig))
        options.append(
            f"<option value='{url}' data-review='{_e(review_line(inst, fig))}' "
            f"data-suggest='{_e(issue_url(inst, man, fig))}'>{label}</option>"
        )
        fallback.append(f"<li><a href='{url}'>{label}</a></li>")
    return (
        f"<details class='dataset'><summary>{_e(domain)}</summary>"
        "<div class='figure-browser'>"
        f"<label for='{identifier}'>Figure</label>"
        f"<select id='{identifier}'>{''.join(options)}</select>"
        "<p role='status' aria-live='polite'>Choose a figure to view.</p>"
        "<button class='figure-retry' type='button' hidden>Retry loading</button>"
        "<button class='figure-image' type='button' aria-label='Enlarge figure' hidden>"
        "<img alt=''></button>"
        "<div class='figure-actions' hidden>"
        "<button type='button' data-copy=''>Copy review prompt</button>"
        "<a class='suggest' target='_blank' rel='noopener'>Suggest an improvement</a>"
        "</div>"
        f"<noscript><p>Figure links (JavaScript is disabled):</p><ul>{''.join(fallback)}</ul>"
        "</noscript></div></details>"
    )


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
        return ""
    items = []
    for title, path in c:
        link = _critique_link(v, path)
        name = f"<a href='{_e(link)}'>{_e(title)}</a>" if link else _e(title)
        items.append(f"<li>{name}</li>")
    return (
        f"<details><summary>Open critiques ({len(c)})</summary><ul>{''.join(items)}</ul></details>"
    )


def _md_inline(text: str) -> str:
    """Escape, then honour the two inline marks the survey lines use."""
    out = _e(text)
    out = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", out)
    return re.sub(r"`(.+?)`", r"<code>\1</code>", out)


def render_html(views) -> str:
    shared = theme()
    # The registry owns project destinations; the checkout remote owns this
    # organ's destination. Pages hosting is never used as a work repository.
    work_links = [{"label": v.instance.repo, "href": v.instance.github_url} for v in views]
    owner_url = context_mod.mind_github_url(ORGAN_ROOT)
    if owner_url:
        work_links.append({"label": ORGAN_ROOT.name, "href": owner_url})
    panel = shared.orchestration_panel(
        "eyes",
        "",
        "",
        CHECKIN_PROMPT,
        work_links=work_links,
        organ="eyes",
        refreshed_at=(
            min(v.captured_at for v in views)
            if views and all(v.manifest and v.captured_at for v in views)
            else None
        ),
        refresh_url=(owner_url + "/actions/workflows/dashboard_refresh.yml") if owner_url else None,
    )
    rows = []
    for v in views:
        inst = v.instance
        count = str(len(v.manifest.figures)) if v.manifest else "—"
        rendered = v.rendered or "—"
        rows.append(
            f"<tr><td><a href='#{_e(inst.name)}'>{_e(inst.library)}</a></td>"
            f"<td>{count}</td><td><code>{_e(rendered)}</code></td>"
            f"<td class='{_freshness_class(v.freshness)}'>{compact_freshness(v)}</td></tr>"
        )
    sections = []
    for index, v in enumerate(views):
        inst = v.instance
        head = f"<h2 id='{_e(inst.name)}'>{_e(inst.library)}</h2>" + _html_critiques(v)
        if not v.manifest:
            sections.append(head + f"<p class='warn'>Manifest unavailable: {_e(v.error)}</p>")
            continue
        body = [head]
        for group, (domain, figs) in enumerate(_grouped(v.manifest).items()):
            body.append(_figure_browser(inst, v.manifest, domain, figs, f"figure-{index}-{group}"))
        if not v.manifest.figures:
            body.append("<p>No figures available.</p>")
        sections.append("".join(body))
    return shared.section_layout(
        "<!doctype html>\n<html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>PyAutoEyes dashboard</title>"
        "<!-- Generated by `bin/pyauto-eyes board`. Do not edit by hand. -->"
        f"<style>{shared.css('eyes')}{CSS}</style></head><body>"
        + shared.hero(
            "eyes",
            "Visualization dashboard",
            navigation=[
                {"href": "#overview", "label": "Projects", "count": len(views)},
                *(
                    {
                        "href": "#" + v.instance.name,
                        "label": v.instance.library,
                        "count": len(v.manifest.figures) if v.manifest else None,
                        "context": "Figures" if v.manifest else "Manifest unavailable",
                    }
                    for v in views
                ),
            ],
        )
        + panel
        + "<main>"
        "<h2 id='overview'>Projects</h2>"
        "<div class='tablewrap' role='region' aria-label='Project overview' tabindex='0'>"
        "<table><thead><tr><th>Library</th><th>Figures</th>"
        "<th>Rendered with</th><th>Freshness</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div>"
        f"{''.join(sections)}</main>"
        "<dialog class='figure-dialog' aria-labelledby='enlarged-title'>"
        "<header><h2 id='enlarged-title'>Figure</h2>"
        "<button type='button' autofocus>Close</button></header><img alt=''></dialog>"
        f"<script>{shared.JS}{JS}{VIEWER_JS}</script></body></html>\n"
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


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _survey_counts(v) -> tuple[int, int, int]:
    s = v.context.survey
    if s is None:
        return 0, 0, 0
    return len(s.gaps), len(s.stale), len(s.orphans)


def render_state(views, updated: str | None = None) -> dict:
    """The organ-cockpit feed (state.json, contract v1 in PyAutoBrain/board).

    status: red when any instance's manifest is unavailable; yellow when any
    instance is behind the latest release, has open critiques, or its survey
    shows gaps, stale renders or orphans; else green. The headline is the
    badge message (", all current" appended when green), so the cockpit and
    the badge say the same thing. Items are the rows that ask something of a
    human, most urgent first: red (manifest unavailable), yellow (behind,
    open critiques), info (survey gaps / stale / orphans). Pure apart from the
    clock default for ``updated``.
    """
    red, yellow, info = [], [], []
    for v in views:
        inst = v.instance
        survey_prompt = f"Use the eyes skill. survey --instance {inst.name}"
        if not v.manifest:
            red.append(
                {
                    "severity": "red",
                    "text": f"{inst.name}: manifest unavailable",
                    "url": inst.github_url,
                    "prompt": survey_prompt,
                }
            )
        if v.behind:
            yellow.append(
                {
                    "severity": "yellow",
                    "text": f"{inst.name}: {v.freshness}",
                    "url": inst.github_url,
                    "prompt": survey_prompt,
                }
            )
        critiques = v.context.critiques or []
        if critiques:
            link = _critique_link(v, critiques[0][1])
            n = len(critiques)
            yellow.append(
                {
                    "severity": "yellow",
                    "text": f"{inst.name}: {n} open critique{'' if n == 1 else 's'}",
                    "url": link if link.startswith(("https://", "http://")) else None,
                    "prompt": f"Use the eyes skill. review --instance {inst.name}",
                }
            )
        gaps, stale, orphans = _survey_counts(v)
        if gaps or stale or orphans:
            info.append(
                {
                    "severity": "info",
                    "text": f"{inst.name}: {gaps} gaps · {stale} stale · {orphans} orphans",
                    "url": None,
                    "prompt": survey_prompt,
                }
            )
    if red:
        status = "red"
    elif yellow or info:
        status = "yellow"
    else:
        status = "green"
    headline = render_badge(views)["message"]
    if status == "green":
        headline += ", all current"
    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "organ": "eyes",
        "repo": "PyAutoEyes",
        "status": status,
        "headline": " ".join(headline.split()),
        "updated": updated or _utc_now(),
        "pages_url": PAGES_URL,
        "items": red + yellow + info,
    }


# -------------------------------------------------------------------- output ---


def _carried_updated(path: Path, state: dict) -> str | None:
    """The committed state.json's ``updated`` when nothing else changed.

    Keeps the render deterministic (a re-render on unchanged inputs changes no
    file, so the daily refresh commits nothing): ``updated`` moves only when
    the feed's content does.
    """
    try:
        prior = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(prior, dict) or not isinstance(prior.get("updated"), str):
        return None
    same = {k: val for k, val in prior.items() if k != "updated"} == {
        k: val for k, val in state.items() if k != "updated"
    }
    return prior["updated"] if same else None


def write(views, out_dir: Path = ORGAN_ROOT, updated: str | None = None) -> list[Path]:
    out_dir = Path(out_dir)
    md, page, badge, feed = (
        out_dir / "dashboard.md",
        out_dir / "dashboard.html",
        out_dir / "badge.json",
        out_dir / "state.json",
    )
    md.write_text(render_markdown(views))
    page.write_text(render_html(views))
    badge.write_text(json.dumps(render_badge(views), indent=2) + "\n")
    state = render_state(views, updated)
    if updated is None:
        state["updated"] = _carried_updated(feed, state) or state["updated"]
    feed.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n")
    return [md, page, badge, feed]


def markers(text: str) -> dict[str, str]:
    """``{instance name: manifest digest}`` as recorded in a rendered dashboard.md."""
    return dict(MARKER.findall(text))
