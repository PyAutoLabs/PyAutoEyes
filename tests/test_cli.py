import pytest

from eyes import cli


def run(*args):
    return cli.main(list(args))


@pytest.fixture
def out(tmp_path):
    d = tmp_path / "organ"
    d.mkdir()
    return d


def base(registry_file, out):
    return ["--registry", str(registry_file)], ["--out", str(out)]


def test_board_then_check_is_green(registry_file, project, out, capsys):
    reg, o = base(registry_file, out)
    assert run(*reg, "board", "--offline", "--from", f"demo={project}", *o) == 0
    assert (out / "dashboard.md").is_file() and (out / "dashboard.html").is_file()
    assert run(*reg, "check", "--offline", "--from", str(project), *o) == 0
    text = capsys.readouterr().out
    assert "all 3 figures resolve" in text and "check: OK" in text


def test_check_fails_when_the_dashboard_is_stale(registry_file, project, out, capsys):
    reg, o = base(registry_file, out)
    run(*reg, "board", "--offline", "--from", str(project), *o)
    manifest_file = project / "gallery" / "viz_manifest.yaml"
    manifest_file.write_text(manifest_file.read_text().replace("2026-09-28", "2026-10-01"))
    assert run(*reg, "check", "--offline", "--from", str(project), *o) == 1
    assert "dashboard: stale for demo" in capsys.readouterr().out


def test_check_fails_on_a_missing_figure_or_dashboard(registry_file, project, out, capsys):
    reg, o = base(registry_file, out)
    assert run(*reg, "check", "--offline", "--from", str(project), *o) == 1
    assert "dashboard.md / dashboard.html missing" in capsys.readouterr().out
    run(*reg, "board", "--offline", "--from", str(project), *o)
    next(project.rglob("*.png")).unlink()
    assert run(*reg, "check", "--offline", "--from", str(project), *o) == 1
    assert "1 of 3 figures do not resolve" in capsys.readouterr().out


def test_check_fails_on_a_bad_registry(tmp_path, out, capsys):
    bad = tmp_path / "registry.yaml"
    bad.write_text("schema: 1\ninstances: []\n")
    assert run("--registry", str(bad), "check", "--out", str(out)) == 1
    assert "FAIL registry" in capsys.readouterr().out


def test_check_fails_on_an_unreachable_manifest(registry_file, out, capsys):
    reg, o = base(registry_file, out)
    assert run(*reg, "check", *o) == 1
    assert "unreachable" in capsys.readouterr().out


def test_from_cannot_guess_an_ambiguous_instance(registry_file, tmp_path):
    from eyes import registry

    instances = registry.load(registry_file) * 2
    with pytest.raises(SystemExit, match="cannot tell"):
        cli._sources([str(tmp_path)], instances)


def test_survey_delegates_to_the_brain_eyes_conductor(registry_file, project, monkeypatch):
    from eyes import registry

    monkeypatch.setattr(registry.Instance, "local_checkout", lambda self, root=None: project)
    monkeypatch.setattr(cli, "_brain_cli", lambda: ["/brain/bin/pyauto-brain"])
    calls = []
    monkeypatch.setattr(cli.subprocess, "call", lambda argv: calls.append(argv) or 0)
    assert run("--registry", str(registry_file), "survey", "demo") == 0
    assert run("--registry", str(registry_file), "survey", "--all") == 0
    assert calls == [["/brain/bin/pyauto-brain", "eyes", "survey", str(project)]] * 2


def test_survey_unknown_instance(registry_file, capsys):
    assert run("--registry", str(registry_file), "survey", "galaxy") == 1
    assert "no instance 'galaxy'" in capsys.readouterr().err


def test_board_reads_critiques_from_mind_and_carries_them_forward(
    registry_file, project, mind, out, capsys
):
    reg, o = base(registry_file, out)
    args = [*reg, "board", "--offline", "--from", f"demo={project}", *o]
    assert run(*args, "--mind", str(mind), "--no-survey") == 0
    text = capsys.readouterr().out
    assert "wrote" in text and str(out / "badge.json") in text
    assert "demo: survey not run (--no-survey); critiques 2" in text
    first = (out / "dashboard.md").read_text()
    assert "Restyle the -- fit panel" in first
    # A re-render with no Mind reachable keeps the recorded critiques.
    assert run(*args, "--no-survey") == 0
    assert (out / "dashboard.md").read_text() == first
    assert run(*reg, "check", "--offline", "--from", str(project), *o) == 0


def test_board_runs_the_conductor_survey_on_the_checkout(
    registry_file, project, fake_brain, out, monkeypatch
):
    from eyes import context

    brain, log = fake_brain
    monkeypatch.setattr(context, "brain_cli", lambda: brain)
    reg, o = base(registry_file, out)
    assert run(*reg, "board", "--offline", "--from", f"demo={project}", *o) == 0
    assert log.read_text().split() == ["eyes", "--json", "survey", str(project)]
    assert "3 png · 1 gaps · 0 orphans · 1 stale" in (out / "dashboard.md").read_text()
