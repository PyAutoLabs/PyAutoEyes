# PyAutoEyes — Agent Guidance

This file is for AI coding agents (Claude Code, Codex, Cursor, etc.) and humans
discovering this repository. PyAutoEyes is the **Eyes** organ of the PyAuto
organism. It is where the human checks in on what the figures look like across
every library.

<!-- repos_sync:map:begin -->
**You are one peer organ of the PyAuto organism** (human-led, natural-language software development), not a part of another. Boundaries: `PyAutoBrain/ORGANISM.md`; every repo: `PyAutoMind/repos.yaml`.

| Organ | Repo | Role |
|-------|------|------|
| **Brain** | PyAutoBrain | Reasoning and orchestration: decomposes and routes work through its conductors and faculties. |
| **Broca** | PyAutoBroca | Assistant evaluation history, upkeep evidence and its dashboard. |
| **Mind** | PyAutoMind | Intent, priorities and workflow state; every task starts as a prompt here. |
| **Cortex** | PyAutoCortex | What is true in the science: the project body map and one ledger per project. |
| **Memory** | PyAutoMemory | Long-term scientific, software and project knowledge. |
| **Eyes** | PyAutoEyes | Cross-project figure dashboard over the `<lib>_visualization` repos. |
| **Ears** | PyAutoEars | Read-only community listening: conversation snapshots and coverage. |
| **Heart** | PyAutoHeart | Health/readiness — the authoritative release verdict. |
| **Hands** | PyAutoHands | Packaging, tagging, notebooks and PyPI release execution. |
| **Pulse** | PyAutoPulse | Cross-project profiling dashboard over the `<lib>_profiling` repos. |
| **Insight** | PyAutoInsight | Inference campaign intent, instance registry and evidence dashboard. |
| **DNA** | PyAutoDNA | Software-stack specifications, environment inventories and upgrade campaigns. |
| **Nerves** | PyAutoNerves | Configuration/serialization layer (`autonerves`): layered config, version handshake, test_mode. |
| **Gut** | PyAutoGut | Condemned branches, stashes and dead code, held as recoverable refs until swept. |

Call chain: **Brain → Heart (gate) → Build (execute)**. Conductors decide *and* act; faculties judge read-only and stop. New capability grows as a faculty, not an organ, unless it owns state or effects no organ can.

Generated from `PyAutoMind/repos.yaml` + `PyAutoBrain/ORGANISM.md`; edit there, then run `python3 PyAutoMind/scripts/repos_sync.py --write`.
<!-- repos_sync:map:end -->
## What this repo is

The design has **two layers** (human decision 2026-09-28):

- **Project repos** `<lib>_visualization` make, store and track the figures.
  Four are registered: `lens/autolens_visualization`,
  `galaxy/autogalaxy_visualization`, `fit/autofit_visualization` and
  `cti/autocti_visualization`. Each
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
- **Copies no figures.** The selected image loads directly from the project’s raw PNG URL, and the Pages
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
eyes/board.py        build dashboard.md + dashboard.html + badge.json + state.json (deterministic)
eyes/cli.py          the pyauto-eyes commands
bin/pyauto-eyes      board | check | survey
dashboard.md/.html   GENERATED; never edit by hand (badge.json and state.json too)
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

- a copyable `Use the eyes skill. review <instance> <figure>` line for an AI assistant session;
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

<!-- repos_sync:standards:begin -->
## Shared standards

Before changing a shared interface, consult the applicable
[organism standard](https://github.com/PyAutoLabs/PyAutoBrain/blob/main/docs/standards.md)
on demand, identify affected consumers, and validate their adoption. Change
generated guidance at its canonical source and regenerate.

For board changes, follow the applicable sizing, navigation and orchestration
standards and reuse Brain’s shared components. Keep domain data, prompt meaning
and approval boundaries with the board’s owner.
<!-- repos_sync:standards:end -->
