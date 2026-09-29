# PyAutoEyes — Agent Guidance

This file is for AI coding agents (Claude Code, Codex, Cursor, etc.) and humans
discovering this repository. PyAutoEyes is the **Eyes** organ of the PyAuto
organism. It is where the human checks in on what the figures look like across
every library.

<!-- repos_sync:map:begin -->
**You are one organ of the PyAuto organism** — an agentic ecosystem for
human-led, natural-language software development. The organs below are
peer repositories; this repo is one of them, not a part of another.
Canonical boundaries live in `PyAutoBrain/ORGANISM.md`; the full body map
(every repo, not just organs) is `PyAutoMind/repos.yaml`.

| Organ | Repo | Role |
|-------|------|------|
| **Brain** | PyAutoBrain | Reasoning/orchestration layer; how work is decomposed and routed; the specialist agents. |
| **Mind** | PyAutoMind | Intent, goals, priorities, workflow state; every task starts as a markdown prompt here. |
| **Cortex** | PyAutoCortex | The Cortex — where the organism keeps track of what is true: the science body map (`projects.yaml`) and one ledger per science project (what was run, what came back, what was learned, where to pick up); the science mirror of the Mind (runs and a dated log, not prompts and PRs). |
| **Memory** | PyAutoMemory | Long-term scientific/software/project knowledge (see science pointer below). |
| **Eyes** | PyAutoEyes | The Eyes — where the organism sees what its figures look like: the cross-project visualization dashboard over the `<lib>_visualization` project repos (autolens_visualization and autogalaxy_visualization) — the registry of those repos, the tracked-manifest read contract (`gallery/viz_manifest.yaml`) and the Pages board that links to their PNGs as the single point of contact for the visual behaviour of the whole ecosystem. Renders nothing and copies no figures (the project repos render and hold them); never judges them (the Brain's Eyes conductor does) and never edits library plot code (critiques route through intake). |
| **Heart** | PyAutoHeart | Health/readiness — the authoritative "is it safe to release?" verdict. |
| **Hands** | PyAutoHands | Packaging, tagging, notebook generation, PyPI release execution. |
| **Nerves** | PyAutoNerves | The Nerves — the configuration/serialization layer connecting workspace conventions to libraries (layered config, version handshake, test_mode), delivered as the `autonerves` package. |
| **Gut** | PyAutoGut | Owns the lifecycle of condemned self-material (stale branches, stashes, dead code/tests): holds it as durable, recoverable git refs through a transit window and voids it on a sweep. The storage mirror of Memory (retention vs release). |

Call chain (always this order): **Brain → Heart (gate) → Build (execute)**. Brain agents are **conductors** (front-door; a human drives them; they decide *and* act) or **faculties** (read-only opinions the conductors consult; they judge and stop). New capability grows as a faculty, not a new organ, unless it owns state or effects no existing organ can.

Generated from `PyAutoMind/repos.yaml` + `PyAutoBrain/ORGANISM.md`; edit there, then run `python3 PyAutoMind/scripts/repos_sync.py --write`.
<!-- repos_sync:map:end -->
## What this repo is

The design has **two layers** (human decision 2026-09-28):

- **Project repos** `<lib>_visualization` make, store and track the figures.
  Two are registered: `lens/autolens_visualization` and
  `galaxy/autogalaxy_visualization`; fit and cti follow. Each
  one owns its producers, simulators, datasets, `plots.yaml`, instruments,
  tracked PNGs, `GALLERY.md`, render harness and lint/render workflows, and
  it commits a tracked **figure manifest** (`gallery/viz_manifest.yaml`).
- **This organ** is the cross-project dashboard over them. It reads each
  instance's manifest and publishes `dashboard.md` + `dashboard.html`
  (Pages), which link to the PNGs where they live.

This is the same layering as `autolens_profiling` / `autolens_inference`
under the Brain board.

## Boundary (what this organ never does)

- **Renders nothing.** Figures are rendered in the project repos by their own
  harness, on library release.
- **Copies no figures.** Thumbnails are links to the raw PNGs, and the Pages
  site publishes `dashboard.html` alone.
- **Never judges.** Critique is the Brain Eyes conductor's
  (`PyAutoBrain/agents/conductors/eyes/`), per instance via this registry.
- **Never edits library plot code.** Accepted critiques route through intake →
  start_dev like any other change.

## Layout

```
registry.yaml        one row per instance (lens today)
REFERENCE.md         the manifest contract (schema 1), registry fields, refresh chain
eyes/registry.py     read + validate registry.yaml; resolve local checkouts
eyes/manifest.py     read a manifest from a checkout / file / raw GitHub URL; validate
eyes/context.py      per-instance survey (asks the Brain Eyes conductor) + open critiques (Mind drafts)
eyes/board.py        build dashboard.md + dashboard.html + badge.json (deterministic, no stamp)
eyes/cli.py          the pyauto-eyes commands
bin/pyauto-eyes      board | check | survey
dashboard.md/.html   GENERATED; never edit by hand (badge.json too)
tests/               hermetic pytest (no network)
```

## Commands

```bash
bin/pyauto-eyes board [--offline] [--from [INSTANCE=]PATH] [--no-survey] [--mind PATH]   # render the dashboard
bin/pyauto-eyes check [--offline] [--from ...]              # the gate (exit 1 on failure)
bin/pyauto-eyes survey [<instance> | --all]                 # pyauto-brain eyes survey <checkout>
```

`--offline` reads manifests from local checkouts (`<root>/<path>`, or a
flat bundle's `<root>/<repo>`) and skips the PyPI freshness lookup. `--from`
points an instance at a specific checkout, such as a project-repo worktree
whose manifest is not on `main` yet. Image links are always the raw GitHub
URLs, so the committed dashboard carries no machine paths.

`board` also reads two local inputs per instance. It asks the Brain Eyes
conductor to survey the instance's checkout (`pyauto-brain eyes --json survey
<checkout>`), and it lists the open PyAutoMind drafts that mention the
instance (`$PYAUTO_MIND`, or `--mind`). Neither is available on the CI runner.
Whatever cannot be read is carried forward from the `<!-- eyes:context … -->`
marker in the committed dashboard, so a CI render never erases the last local
reading and the page does not flap. `dashboard_refresh.yml` checks out
PyAutoMind, so critiques stay live there; the survey refreshes whenever
someone runs `bin/pyauto-eyes board` where the instance is checked out.

## The critique route

Each figure carries two affordances, and neither files anything:

- a copyable `/eyes review <instance> <figure>` line for a Claude Code session;
- a **Suggest an improvement** link that opens a pre-filled "new issue" form on
  the *project* repo. The title is `figure: <domain>/<file>`, the body holds the
  raw PNG link, the manifest version and a `Suggested improvement:` stub, and
  the label is `eyes-critique`.

The human submits the issue. An accepted critique then becomes a PyAutoMind
intake prompt and goes through start_dev, as any other change does.

## Testing

The PR gate is `lint.yml`: `ruff check .`, `ruff format --check .`,
`python -m pytest tests -q`, `bin/pyauto-eyes check` (against the live raw
URLs), and lychee over the prose markdown. When a change alters the
dashboard, re-run `bin/pyauto-eyes board` and commit `dashboard.*` in the
same PR. On `main`, `dashboard_refresh.yml` self-heals a stale dashboard,
triggered by `repository_dispatch: eyes-refresh` from the project repos'
`render.yml`, by a daily cron, or by hand.

## Changing the contract

Additive manifest fields need no change here. A breaking change bumps
`schema`. The organ adds the new version to `SUPPORTED_SCHEMAS` first, and
the project repos bump after (REFERENCE.md, "Versioning").

## Adding an instance

Birth the `<lib>_visualization` project repo with a tracked schema-1
manifest, and have its `render.yml` fire `eyes-refresh` here. Create its
`eyes-critique` label (`gh label create eyes-critique --repo <owner/repo>`).
Then add its `registry.yaml` row, run `bin/pyauto-eyes board` and
`bin/pyauto-eyes check`, and commit.

<!-- repos_sync:history:begin -->
## Never rewrite history

Never rewrite pushed history on any repo with a remote — no `git init` over a
tracked repo, no force-push to `main`, no fresh-start "Initial commit", no
`filter-repo` / `filter-branch` / `rebase -i` on pushed branches. To get a
clean tree: `git fetch origin && git reset --hard origin/main && git clean -fd`.
<!-- repos_sync:history:end -->

<!-- repos_sync:deliverable:begin -->
## Sessions end at their deliverable

A session ends when it reports its deliverable — never arm anything that
outlives the turn to wait for CI, a review or a merge: no `send_later`, no
`subscribe_pr_activity`, no `CronCreate`, no `ScheduleWakeup`, no `/loop`, no
`RemoteTrigger` create/update/run. Judge once, report, stop; the human re-runs
`/prm` (or the batch review) when it is green. Measured: five batch members
armed hourly check-ins on 2026-08-31, and a mobile `/prm` re-armed a 60-minute
`send_later` hourly all night on 2026-09-03 with no task active, draining usage.
<!-- repos_sync:deliverable:end -->

<!-- repos_sync:filing:begin -->
## Where to file

Questions, help with code or an analysis, ideas, bug reports and results from a
user or collaborator — or an agent acting for one — go to
<https://github.com/orgs/PyAutoLabs/discussions> in the matching category
(Help & Questions, Ideas & Proposals, Bugs & Errors, Show and tell;
Announcements is maintainers-only), never to this repo's Issues. An agent never
runs `gh issue create` for such a report: it drafts the title, category and
body and hands them to the human (sessions cannot create Discussions). Only the
development flow — Mind prompt → `/start_dev` → `/create_issue` → one issue per
task → PR — opens issues here. Why: `PyAutoMind/policy/community_surface.md`.
<!-- repos_sync:filing:end -->
