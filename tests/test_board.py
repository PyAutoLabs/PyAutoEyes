import pytest

from eyes import board, registry


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
        assert f"`/eyes review demo {fig.file}`" in md
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
        assert f"data-copy='/eyes review demo {fig.file}'" in page
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


def test_write_emits_both_pages(views, tmp_path):
    paths = board.write(views, tmp_path)
    assert [p.name for p in paths] == ["dashboard.md", "dashboard.html"]
    assert all(p.read_text() for p in paths)
