import pytest
import yaml
from conftest import ROW

from eyes import registry


def test_the_committed_registry_is_valid_and_has_the_lens_row():
    instances = registry.load()
    lens = registry.get(instances, "lens")
    assert lens.repo == "autolens_visualization"
    assert lens.github == "PyAutoLabs/autolens_visualization"
    assert lens.import_name == "autolens"
    assert lens.manifest == "gallery/viz_manifest.yaml"
    assert lens.dispatch_event == "pyautolens-release"
    assert lens.manifest_url == (
        "https://raw.githubusercontent.com/PyAutoLabs/autolens_visualization/main/"
        "gallery/viz_manifest.yaml"
    )


def test_the_committed_registry_has_the_galaxy_row():
    instances = registry.load()
    galaxy = registry.get(instances, "galaxy")
    assert galaxy.repo == "autogalaxy_visualization"
    assert galaxy.path == "galaxy/autogalaxy_visualization"
    assert galaxy.github == "PyAutoLabs/autogalaxy_visualization"
    assert galaxy.library == "PyAutoGalaxy"
    assert galaxy.import_name == "autogalaxy"
    assert galaxy.manifest == "gallery/viz_manifest.yaml"
    assert galaxy.dispatch_event == "pyautogalaxy-release"
    assert galaxy.manifest_url == (
        "https://raw.githubusercontent.com/PyAutoLabs/autogalaxy_visualization/main/"
        "gallery/viz_manifest.yaml"
    )
    assert [i.name for i in instances] == ["lens", "galaxy"]


def test_load_fabricated_registry(registry_file):
    (demo,) = registry.load(registry_file)
    assert demo.image_url("a/b.png") == ROW["images_base_url"] + "a/b.png"
    assert demo.gallery_url.endswith("/blob/main/GALLERY.md")


@pytest.mark.parametrize(
    "mutate, needle",
    [
        (lambda r: r.pop("manifest"), "manifest is missing"),
        (lambda r: r.update(images_base_url="http://x/"), "images_base_url"),
        (lambda r: r.update(images_base_url="https://x"), "images_base_url"),
        (lambda r: r.update(github="no-slash"), "owner/repo"),
        (lambda r: r.update(name="Bad Name"), "name must match"),
        (lambda r: r.update(path="../escape"), "relative path"),
        (lambda r: r.update(colour="red"), "unknown field"),
    ],
)
def test_validation_catches_bad_rows(mutate, needle):
    row = dict(ROW)
    mutate(row)
    problems = registry.validate({"schema": 1, "instances": [row]})
    assert any(needle in p for p in problems), problems


def test_duplicate_names_and_wrong_schema_are_rejected():
    problems = registry.validate({"schema": 2, "instances": [dict(ROW), dict(ROW)]})
    assert any("schema must be 1" in p for p in problems)
    assert any("duplicate name" in p for p in problems)


def test_load_raises_with_every_problem(tmp_path):
    path = tmp_path / "registry.yaml"
    path.write_text(yaml.safe_dump({"schema": 1, "instances": []}))
    with pytest.raises(registry.RegistryError, match="non-empty list"):
        registry.load(path)


def test_get_unknown_instance_names_the_known_ones(registry_file):
    with pytest.raises(registry.RegistryError, match="known: demo"):
        registry.get(registry.load(registry_file), "nonesuch")


def test_local_checkout_grouped_then_flat(tmp_path, registry_file):
    (demo,) = registry.load(registry_file)
    assert demo.local_checkout(tmp_path / "ws") is None
    (tmp_path / "ws" / "demo_visualization").mkdir(parents=True)
    assert demo.local_checkout(tmp_path / "ws") == tmp_path / "ws" / "demo_visualization"
    (tmp_path / "ws" / "demo" / "demo_visualization").mkdir(parents=True)
    assert demo.local_checkout(tmp_path / "ws") == tmp_path / "ws" / "demo" / "demo_visualization"
