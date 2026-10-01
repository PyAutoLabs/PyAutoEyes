import html
import importlib.util
import json
import os
import re
import shutil
import subprocess
import urllib.parse
from pathlib import Path

import pytest

from eyes import board, context, registry


@pytest.mark.parametrize("length", [50_000, 50_001])
def test_review_copy_budget_retains_complete_unicode_request(length):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is needed for the browser clipboard contract")
    script = (
        r"""
const assert=require('assert');
let click,status,downloaded,writes=0;
const text='🌌'.repeat(LENGTH);
const b={getAttribute:()=>text,addEventListener:(event,fn)=>click=fn,
 parentNode:{querySelector:()=>status},insertAdjacentElement:(where,s)=>status=s,
 classList:{add(){},remove(){}}};
global.document={querySelectorAll:()=>[b],
 createElement:()=>({dataset:{},setAttribute(){},appendChild(){}})};
Object.defineProperty(global,'navigator',{value:{clipboard:{writeText:async()=>{writes++}}}});
global.URL={createObjectURL:blob=>{downloaded=blob;return 'blob:test'},revokeObjectURL(){}};
global.setTimeout=()=>{};
"""
        + board.JS
        + r"""
click();assert.equal(writes,LENGTH<=50000?1:0);
if(LENGTH>50000){
 assert.match(status.textContent,/Not copied/);
 downloaded.text().then(value=>assert.equal(value,text));
}
"""
    )
    subprocess.run(
        [node, "-e", script.replace("LENGTH", str(length))],
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def views(registry_file, project):
    instances = registry.load(registry_file)
    return board.collect(instances, {"demo": project}, offline=True)


def test_markdown_lists_every_figure_with_raw_links_and_review_lines(views, project):
    md = board.render_markdown(views)
    demo = views[0].instance
    assert "| [demo](#demo) | PyAutoDemo | 3 | `autodemo 2026.9.1.1` | 2026-09-28 |" in md
    for fig in views[0].manifest.figures:
        assert f"({demo.image_url(fig.file)})" in md
        assert f"`Use the eyes skill. review demo {fig.file}`" in md
    assert "### demo / imaging" in md and "### demo / interferometer" in md
    assert board.markers(md) == {"demo": views[0].manifest.digest}
    # Never a local path, even when the manifest was read from a checkout.
    assert str(project) not in md and str(project.parent) not in md


def test_html_thumbnails_link_to_the_full_size_raw_png(views, project):
    page = board.render_html(views)
    demo = views[0].instance
    assert page.startswith("<!doctype html>")
    assert page.count("class='fig'") == 3
    for fig in views[0].manifest.figures:
        url = demo.image_url(fig.file)
        assert f"<a href='{url}' target='_blank'" in page
        assert f"<img loading='lazy' src='{url}'" in page
        assert f"data-copy='Use the eyes skill. review demo {fig.file}'" in page
    assert str(project) not in page
    assert "prefers-color-scheme:dark" in page


def test_render_is_deterministic(views):
    assert board.render_markdown(views) == board.render_markdown(views)
    assert board.render_html(views) == board.render_html(views)


@pytest.mark.parametrize(
    "latest, expected",
    [
        (None, "unknown (release lookup offline)"),
        ("2026.9.1.1", "current (2026.9.1.1)"),
        ("2026.9.27.2", "behind (rendered 2026.9.1.1, released 2026.9.27.2)"),
        ("2026.8.1.1", "ahead of release"),
    ],
)
def test_freshness_against_the_latest_release(registry_file, project, latest, expected):
    instances = registry.load(registry_file)
    (view,) = board.collect(instances, {"demo": project}, release_lookup=lambda name: latest)
    assert view.freshness.startswith(expected)


def test_offline_never_looks_up_releases(registry_file, project):
    def boom(name):
        raise AssertionError("release lookup while offline")

    instances = registry.load(registry_file)
    board.collect(instances, {"demo": project}, offline=True, release_lookup=boom)


def test_release_lookup_degrades_to_none_without_network():
    assert board.latest_release("autodemo") is None


def test_an_unavailable_manifest_still_renders(registry_file):
    instances = registry.load(registry_file)
    (view,) = board.collect(instances)  # network refused by the conftest fixture
    md = board.render_markdown([view])
    assert "**Manifest unavailable:**" in md
    assert board.markers(md) == {"demo": "unavailable"}
    assert "Manifest unavailable" in board.render_html([view])


def test_write_emits_both_pages_the_badge_and_the_state_feed(views, tmp_path):
    paths = board.write(views, tmp_path)
    assert [p.name for p in paths] == [
        "dashboard.md",
        "dashboard.html",
        "badge.json",
        "state.json",
    ]
    assert all(p.read_text() for p in paths)
    assert json.loads(paths[2].read_text())["label"] == "eyes"
    assert json.loads(paths[3].read_text())["organ"] == "eyes"


def test_a_rewrite_on_unchanged_inputs_keeps_the_state_stamp(views, tmp_path):
    feed = board.write(views, tmp_path, updated="2026-09-01T00:00:00Z")[3]
    before = feed.read_text()
    board.write(views, tmp_path)  # clock default, nothing else changed
    assert feed.read_text() == before


# ------------------------------------------------ phase 2: content + route ---


@pytest.fixture
def rich_views(registry_file, project, fake_brain, mind):
    """Views with a live survey (fabricated conductor) and live critiques."""
    brain, _ = fake_brain

    def lookup(inst, checkout, previous):
        return context.gather(inst, checkout, previous, mind=mind, brain=brain)

    instances = registry.load(registry_file)
    return board.collect(
        instances,
        {"demo": project},
        release_lookup=lambda name: "2026.9.27.2",
        context_lookup=lookup,
    )


def test_the_head_of_the_page_is_the_counts_table_the_brain_reads(rich_views):
    md = board.render_markdown(rich_views)
    head = md.split("\n## ", 1)[0]
    assert "| [Instances](#instances) | 1 |" in head
    assert "| [Figures](#instances) | 3 |" in head
    assert "| [Behind](#instances) | 1 |" in head
    assert "| [Critiques](#instances) | 2 |" in head
    # The Brain board's regex over the head finds exactly these four rows.
    rows = re.findall(r"^\|\s*\[([^\]]+)\]\([^)]*\)[^|]*\|\s*(\d+)\s*\|", head, re.M)
    assert [r[0] for r in rows] == ["Instances", "Figures", "Behind", "Critiques"]


def test_the_instance_row_and_section_carry_survey_and_critiques(rich_views, project):
    md = board.render_markdown(rich_views)
    assert "| 3 png · 1 gaps · 0 orphans · 1 stale | 2 |" in md
    assert "3 PNGs on disk (imaging 2, interferometer 1)" in md
    assert "gaps `interferometer/visualization_jax`" in md
    assert "stale renders `imaging/visualization`" in md
    assert "- Restyle the -- fit panel (`draft/feature/demo/restyle_fit.md`)" in md
    # Never a machine path: not the checkout, not the survey's workspace.
    assert str(project.parent) not in md and "/somewhere/on/a/laptop" not in md
    page = board.render_html(rich_views)
    assert "Restyle the -- fit panel" in page and "3 png · 1 gaps" in page
    assert str(project.parent) not in page


def test_each_figure_has_a_prefilled_issue_on_the_project_repo(rich_views):
    view = rich_views[0]
    demo, man = view.instance, view.manifest
    md = board.render_markdown(rich_views)
    page = board.render_html(rich_views)
    for fig in man.figures:
        url = board.issue_url(demo, man, fig)
        assert url.startswith("https://github.com/PyAutoLabs/demo_visualization/issues/new?")
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        assert q["title"] == [f"figure: {fig.domain}/{board._figure_label(fig)}"]
        assert q["labels"] == ["eyes-critique"]
        body = q["body"][0]
        assert f"Raw PNG: {demo.image_url(fig.file)}" in body
        assert "generated 2026-09-28, rendered with autodemo 2026.9.1.1" in body
        assert "Suggested improvement:" in body
        assert f"Use the eyes skill. review demo {fig.file}" in body
        # The markdown link survives the table (no raw pipe or paren in it).
        assert f"| [suggest]({url}) |" in md and "|" not in url and ")" not in url
        assert html.escape(url, quote=True) in page
    assert page.count("Suggest an improvement</a>") == len(man.figures)


def test_a_manifest_survey_mismatch_is_called_out(registry_file, project, mind):
    extra = context.Survey(domains={"imaging": 5})
    instances = registry.load(registry_file)
    (view,) = board.collect(
        instances,
        {"demo": project},
        offline=True,
        context_lookup=lambda i, c, p: context.Context(survey=extra, critiques=[]),
    )
    md = board.render_markdown([view])
    assert "The checkout holds 5 PNGs but the manifest lists 3" in md
    assert "(PyAutoMind drafts mentioning this instance): none." in md


def test_a_ci_render_carries_the_last_local_reading_forward(rich_views, registry_file, project):
    local = board.render_markdown(rich_views)
    instances = registry.load(registry_file)
    # The runner: no checkout, no Brain, no Mind — only the committed page.
    ci = board.collect(
        instances,
        {"demo": project},
        release_lookup=lambda name: "2026.9.27.2",
        context_lookup=lambda inst, checkout, prev: context.gather(inst, None, prev, mind=False),
        previous=local,
    )
    assert board.render_markdown(ci) == local
    assert board.render_html(ci) == board.render_html(rich_views)


def test_badge_tracks_behind_and_unavailable(rich_views, registry_file):
    assert board.render_badge(rich_views) == {
        "schemaVersion": 1,
        "label": "eyes",
        "message": "3 figures · 1 behind",
        "color": "yellow",
    }
    instances = registry.load(registry_file)
    (missing,) = board.collect(instances)  # network refused
    assert board.render_badge([missing])["color"] == "red"


# ------------------------------------------------- phase 5: cockpit feed ---


def _brain_state_validator():
    """The Brain's board/_state.py (the contract), imported by path, or skip."""
    roots = []
    if os.environ.get("PYAUTO_BRAIN"):
        roots.append(Path(os.environ["PYAUTO_BRAIN"]))
    roots.append(Path(__file__).resolve().parents[1].parent / "PyAutoBrain")
    for root in roots:
        path = root / "board" / "_state.py"
        if path.is_file():
            spec = importlib.util.spec_from_file_location("_brain_state", path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
    pytest.skip("no PyAutoBrain checkout here (set PYAUTO_BRAIN) to validate against")


def test_state_feed_matches_brain_contract(rich_views, registry_file):
    validator = _brain_state_validator()
    state = board.render_state(rich_views, updated="2026-09-30T00:00:00Z")
    assert validator.validate_state(state) == []
    instances = registry.load(registry_file)
    (missing,) = board.collect(instances)  # network refused
    assert validator.validate_state(board.render_state([missing])) == []


def test_state_feed_status_and_items(rich_views, registry_file):
    state = board.render_state(rich_views, updated="2026-09-30T00:00:00Z")
    assert state["schema_version"] == 1
    assert (state["organ"], state["repo"]) == ("eyes", "PyAutoEyes")
    assert state["pages_url"] == board.PAGES_URL
    assert state["updated"] == "2026-09-30T00:00:00Z"
    assert state["status"] == "yellow"
    assert state["headline"] == board.render_badge(rich_views)["message"]
    items = state["items"]
    assert [i["severity"] for i in items] == ["yellow", "yellow", "info"]
    behind, critiques, survey = items
    assert behind["text"] == "demo: behind (rendered 2026.9.1.1, released 2026.9.27.2)"
    assert behind["url"] == "https://github.com/PyAutoLabs/demo_visualization"
    assert behind["prompt"] == "Use the eyes skill. survey --instance demo"
    assert critiques["text"] == "demo: 2 open critiques"
    assert critiques["prompt"] == "Use the eyes skill. review --instance demo"
    assert critiques["url"] is None or critiques["url"].startswith("https://")
    assert survey["text"] == "demo: 1 gaps · 1 stale · 0 orphans"
    assert survey["url"] is None
    assert all("\n" not in i["text"] and i["text"].strip() for i in items)

    instances = registry.load(registry_file)
    (missing,) = board.collect(instances)  # network refused
    red = board.render_state([missing], updated="2026-09-30T00:00:00Z")
    assert red["status"] == "red"
    assert red["items"][0] == {
        "severity": "red",
        "text": "demo: manifest unavailable",
        "url": "https://github.com/PyAutoLabs/demo_visualization",
        "prompt": "Use the eyes skill. survey --instance demo",
    }


def test_state_feed_is_green_when_nothing_asks_for_a_human(views):
    state = board.render_state(views, updated="2026-09-30T00:00:00Z")
    assert state["status"] == "green" and state["items"] == []
    assert state["headline"] == "3 figures, all current"


def test_state_updated_defaults_to_a_utc_z_stamp(views):
    stamp = board.render_state(views)["updated"]
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", stamp)
