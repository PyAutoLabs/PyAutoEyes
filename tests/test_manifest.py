import pytest
import yaml

from eyes import manifest, registry


@pytest.fixture
def demo(registry_file):
    return registry.load(registry_file)[0]


def test_load_from_checkout_dir_and_from_file(demo, project):
    by_dir = manifest.load(demo, project)
    by_file = manifest.load(demo, project / "gallery" / "viz_manifest.yaml")
    assert by_dir.local_root == project
    assert by_file.local_root.resolve() == project.resolve()
    assert len(by_dir.figures) == 3
    assert by_dir.rendered_with["autodemo"] == "2026.9.1.1"
    assert by_dir.digest == by_file.digest


def test_digest_ignores_comments_but_not_content(demo, project):
    path = project / "gallery" / "viz_manifest.yaml"
    before = manifest.load(demo, project).digest
    path.write_text("# another comment\n" + path.read_text())
    assert manifest.load(demo, project).digest == before
    doc = yaml.safe_load(path.read_text())
    doc["generated"] = "2026-10-01"
    path.write_text(yaml.safe_dump(doc))
    assert manifest.load(demo, project).digest != before


def test_load_remote_reads_the_raw_url(demo, project, monkeypatch):
    text = (project / "gallery" / "viz_manifest.yaml").read_bytes()
    seen = []

    def fake_get(url):
        seen.append(url)
        return text

    monkeypatch.setattr(manifest, "_http_get", fake_get)
    man = manifest.load(demo)
    assert seen == [demo.manifest_url]
    assert man.local_root is None and man.origin == demo.manifest_url


def test_unreachable_remote_is_a_manifest_error(demo):
    with pytest.raises(manifest.ManifestError, match="unreachable"):
        manifest.load(demo)


def test_offline_without_checkout_says_how_to_point_at_one(demo, monkeypatch, tmp_path):
    monkeypatch.setattr(registry, "workspace_roots", lambda root=None: [tmp_path / "nowhere"])
    with pytest.raises(manifest.ManifestError, match="--from demo="):
        manifest.load(demo, offline=True)


@pytest.mark.parametrize(
    "mutate, needle",
    [
        (lambda d: d.update(schema=2), "unsupported schema"),
        (lambda d: d.update(figure_count=99), "figure_count is 99"),
        (lambda d: d.pop("rendered_with"), "rendered_with"),
        (lambda d: d["figures"][0].pop("sha256"), "sha256 is missing"),
        (lambda d: d["figures"][0].update(sha256="xyz"), "64 lowercase hex"),
        (lambda d: d["figures"][0].update(file="/abs.png"), "relative to the repo root"),
        (lambda d: d["figures"][0].update(file="a.fits"), "must be a .png"),
        (lambda d: d["figures"].append(dict(d["figures"][0])), "duplicate file"),
    ],
)
def test_contract_violations(project, mutate, needle):
    doc = yaml.safe_load((project / "gallery" / "viz_manifest.yaml").read_text())
    mutate(doc)
    problems = manifest.validate(doc)
    assert any(needle in p for p in problems), problems


def test_unknown_keys_are_ignored(demo, project):
    path = project / "gallery" / "viz_manifest.yaml"
    doc = yaml.safe_load(path.read_text())
    doc["future_field"] = {"anything": 1}
    doc["figures"][0]["caption"] = "added later"
    path.write_text(yaml.safe_dump(doc))
    assert len(manifest.load(demo, project).figures) == 3


def test_resolve_figures_local_checks_size_and_hash(demo, project):
    man = manifest.load(demo, project)
    assert manifest.resolve_figures(demo, man) == []
    (project / man.figures[0].file).write_bytes(b"tampered")
    (project / man.figures[1].file).unlink()
    problems = manifest.resolve_figures(demo, man)
    assert len(problems) == 2
    assert "does not match" in problems[0] and "missing" in problems[1]


def test_resolve_figures_remote_heads_every_raw_url(demo, project, monkeypatch):
    text = (project / "gallery" / "viz_manifest.yaml").read_bytes()
    monkeypatch.setattr(manifest, "_http_get", lambda url: text)
    heads = []

    class Ok:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(request, timeout):
        heads.append((request.get_method(), request.full_url))
        return Ok()

    monkeypatch.setattr(manifest.urllib.request, "urlopen", fake_urlopen)
    man = manifest.load(demo)
    assert manifest.resolve_figures(demo, man) == []
    assert heads == [("HEAD", demo.image_url(f.file)) for f in man.figures]
