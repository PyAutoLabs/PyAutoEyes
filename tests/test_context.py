import dataclasses

from conftest import EYES_SURVEY, REAL_MIND_ROOT

from eyes import context, registry


def _demo(registry_file):
    return registry.load(registry_file)[0]


def test_survey_reduces_the_conductor_output_without_paths():
    s = context.Survey.from_eyes_survey(EYES_SURVEY)
    assert s.domains == {"imaging": 2, "interferometer": 1}
    assert s.png == 3
    assert s.gaps == ["interferometer/visualization_jax"]
    assert s.stale == ["imaging/visualization"]
    assert "laptop" not in str(s.to_json())


def test_run_survey_asks_the_brain_eyes_conductor(fake_brain, project):
    brain, log = fake_brain
    s, note = context.run_survey(project, brain)
    assert note == "" and s.png == 3
    assert log.read_text().split() == ["eyes", "--json", "survey", str(project)]


def test_run_survey_without_a_brain_says_so(project):
    s, note = context.run_survey(project)  # brain_cli() is None in tests
    assert s is None and "no pyauto-brain" in note


def test_run_survey_reports_a_failing_conductor(tmp_path, project):
    failing = tmp_path / "failing-brain"
    failing.write_text(
        "#!/usr/bin/env bash\necho 'eyes: not a visualization workspace' >&2\nexit 4\n"
    )
    failing.chmod(0o755)
    s, note = context.run_survey(project, [str(failing)])
    assert s is None
    assert note == "pyauto-brain eyes survey exited 4: eyes: not a visualization workspace"


def test_critiques_are_open_mind_drafts_that_mention_the_instance(registry_file, mind):
    found = context.find_critiques(mind, _demo(registry_file))
    assert found == [
        ("Restyle the -- fit panel", "draft/feature/demo/restyle_fit.md"),
        ("From a review", "draft/feature/x/review_line.md"),
    ]


def _two_instances(registry_file):
    demo = _demo(registry_file)
    other = dataclasses.replace(demo, name="other", repo="other_visualization")
    return demo, other


def _write_drafts(root, drafts):
    for rel, text in drafts.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return root


def test_a_draft_whose_header_names_an_instance_is_attributed_to_it_only(registry_file, tmp_path):
    demo, other = _two_instances(registry_file)
    mind = _write_drafts(
        tmp_path / "PyAutoMind",
        {
            "draft/bug/demo/targeted.md": (
                "# Targeted at demo\n\nTarget: demo_visualization\n\n"
                "Works in other_visualization already; copy its render.yml.\n"
            ),
            "draft/bug/demo/repos_only.md": (
                "# Repos header\n\nRepos:\n- Demo_Visualization\n- PyAutoFit\n\n"
                "See other_visualization for the precedent.\n"
            ),
        },
    )
    both = [demo, other]
    assert context.find_critiques(mind, demo, both) == [
        ("Repos header", "draft/bug/demo/repos_only.md"),
        ("Targeted at demo", "draft/bug/demo/targeted.md"),
    ]
    assert context.find_critiques(mind, other, both) == []


def test_a_draft_whose_header_names_no_instance_falls_back_to_text_mention(registry_file, tmp_path):
    demo, other = _two_instances(registry_file)
    mind = _write_drafts(
        tmp_path / "PyAutoMind",
        {
            "draft/feature/x/no_header.md": "# No header\n\ndemo_visualization and other_visualization\n",
            "draft/feature/x/unknown.md": (
                "# Unknown target\n\nTarget: PyAutoLens\nRepos:\n- PyAutoLens\n\n"
                "Touches other_visualization.\n"
            ),
        },
    )
    both = [demo, other]
    assert context.find_critiques(mind, demo, both) == [
        ("No header", "draft/feature/x/no_header.md")
    ]
    assert context.find_critiques(mind, other, both) == [
        ("No header", "draft/feature/x/no_header.md"),
        ("Unknown target", "draft/feature/x/unknown.md"),
    ]


def test_marker_round_trips_and_survives_an_html_comment(registry_file, mind):
    ctx = context.Context(
        survey=context.Survey.from_eyes_survey(EYES_SURVEY),
        critiques=context.find_critiques(mind, _demo(registry_file)),
        mind_url="https://github.com/ExampleOrg/PyAutoMind",
    )
    line = context.marker("demo", ctx)
    # A "--" in a draft title would end the comment early; it is escaped.
    assert line.count("--") == 2 and line.endswith(" -->")
    back = context.recorded("text before\n" + line + "\ntext after")["demo"]
    assert back.to_json() == ctx.to_json()


def test_gather_carries_forward_what_it_cannot_read_here(registry_file, project):
    demo = _demo(registry_file)
    prior = context.Context(
        survey=context.Survey.from_eyes_survey(EYES_SURVEY),
        critiques=[("Old", "draft/feature/demo/old.md")],
        mind_url="https://github.com/ExampleOrg/PyAutoMind",
    )
    # No checkout, no Brain, no Mind: the CI runner. Nothing is erased.
    ctx = context.gather(demo, None, prior)
    assert ctx.to_json() == prior.to_json()
    # Nothing recorded before either: say why, never guess.
    empty = context.gather(demo, None, None)
    assert empty.survey is None and "no local checkout of demo/demo_visualization" in (
        empty.survey_note
    )
    assert empty.critiques is None and "no PyAutoMind checkout" in empty.critiques_note


def test_gather_reads_live_inputs_when_they_are_here(registry_file, project, fake_brain, mind):
    brain, _ = fake_brain
    ctx = context.gather(_demo(registry_file), project, None, mind=mind, brain=brain)
    assert ctx.survey.png == 3 and len(ctx.critiques) == 2
    assert ctx.mind_url is None  # the fabricated Mind has no git remote
    skipped = context.gather(_demo(registry_file), project, None, survey=False, mind=False)
    assert skipped.survey is None and skipped.survey_note == "not run (--no-survey)"


def test_mind_root_prefers_pyauto_mind(monkeypatch, mind, tmp_path):
    monkeypatch.setenv("PYAUTO_MIND", str(mind))
    assert REAL_MIND_ROOT() == mind
    monkeypatch.setenv("PYAUTO_MIND", str(tmp_path / "nowhere"))
    assert REAL_MIND_ROOT() is None
