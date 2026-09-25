# autolens_visualization — Agent Instructions

This repo is the single home for **what PyAutoLens figures look like**: it stores, in git, the
most up-to-date rendering of every figure the PyAutoLens visualizers write during a model-fit,
on realistic HST-scale imaging and SMA-scale interferometer data, so visualization can be judged
and improved (by humans or AI chats against the source) without re-running a workspace fit. It is
a collection of standalone producer scripts, **not** an installable package — there is no
`pyproject.toml`. These are the canonical, agent-agnostic instructions for this repo; the
`README.md` is the human-facing overview and `GALLERY.md` is the browsable gallery.

## Repository Structure

Producers are laid out **flat, one per domain** (`scripts/<domain>/visualization*.py`), because
the Brain Eyes agent scans `scripts/<domain>/*.py` non-recursively for stems containing
`visualization`:

```
scripts/
  imaging/visualization.py          VisualizerImaging on dataset/imaging/hst
  imaging/images/visualization/     its output: before-fit PNGs + parametric/ + delaunay/
  interferometer/visualization.py   VisualizerInterferometer on dataset/interferometer/sma
  interferometer/images/visualization/
  misc/simulators/                  imaging.py + interferometer.py (regenerate datasets)
  misc/test/                        hermetic pytest for the gallery builder
gallery/gallery_build.py            GALLERY.md + output/gallery/{gallery.html,viz_manifest.yaml}
gallery/gallery_run.sh              run producers -> build -> --check
config/general.yaml                 layered over the library config (version check off)
config/visualize/plots.yaml         the library default with EVERY toggle on
instruments/                        imaging + interferometer presets (copied from profiling)
dataset/imaging/hst/                TRACKED, byte-for-byte copy of autolens_profiling's hst
dataset/interferometer/sma/         TRACKED, simulated here (190 visibilities)
_viz_cli.py                         repo-root finder, dataset paths, auto-simulate hook
GALLERY.md                          TRACKED, generated — never edit by hand
```

**What is tracked.** PNG figures under `scripts/<domain>/images/**` and `GALLERY.md`. The FITS /
CSV / JSON data products the visualizers also write are gitignored (bulky, not viewable on
GitHub), as are `output/` and `dataset/**/lensed_source.fits`.

**Import model.** Producers find the repo root by walking up to the directory containing
`ruff.toml` (a depth-proof sentinel) and put it on `sys.path`, so `_viz_cli` and `instruments`
import by their top-level names.

## Rendering

From the repo root, with the library checkouts on `PYTHONPATH` (`source activate.sh`):

```bash
bash gallery/gallery_run.sh --all        # both producers, then build + --check (~3 min)
python scripts/imaging/visualization.py  # one producer (~75 s)
python gallery/gallery_build.py          # rebuild GALLERY.md + output/gallery/ only
python gallery/gallery_build.py --check  # fail if GALLERY.md is stale vs the PNGs on disk
```

Each producer wipes its own `scripts/<domain>/images/visualization/` tree first, so the committed
PNG set is exactly what the last run produced. Commit the PNGs and `GALLERY.md` together.

Each producer pushes `config/` via `conf.instance.push` (the all-true `plots.yaml`), loads its
tracked dataset, builds the simulator's **true model** (every parameter fixed), and calls
`Visualizer*.visualize_before_fit` once and `Visualizer*.visualize` once per source type
(`parametric/` = SersicCore, `delaunay/` = Overlay image-mesh + `Delaunay` + `ConstantSplit`),
with a `SimpleNamespace(image_path=..., output_path=...)` paths stub. Adapt images are the
per-galaxy images of the parametric fit.

**Datasets.** `dataset/imaging/hst` is a byte-for-byte copy of
`autolens_profiling/dataset/imaging/hst` (do not re-simulate it; profiling documents that it does
not regenerate byte-identically). `dataset/interferometer/sma` was produced by

```bash
python scripts/misc/simulators/interferometer.py --instrument sma
```

with the imaging simulator's lens mass, shear and source (no lens light). The auto-simulate hook
in `_viz_cli.py` only fires when `data.fits` is absent — it never deletes a tracked dataset.

## Adding a domain

1. Add a simulator under `scripts/misc/simulators/` (or an instrument preset) and track its
   dataset under `dataset/<domain>/<instrument>/`.
2. Add a flat producer `scripts/<domain>/visualization.py` modelled on the imaging one, writing
   to `scripts/<domain>/images/visualization/`.
3. Run `bash gallery/gallery_run.sh --all` and commit the PNGs + `GALLERY.md`.

## Improving a figure (edit surfaces)

- **config** — `config/visualize/plots.yaml` here: which figures are written at all.
- **plot API** — the plotting code in the libraries: `PyAutoLens/autolens/**/plot/`,
  `PyAutoGalaxy/autogalaxy/**/plot/`, `PyAutoArray/autoarray/plot/` (library changes go through
  the normal library workflow, then this repo is re-rendered).
- **script** — the producer in `scripts/<domain>/visualization.py` (dataset, model, source types).

## Eyes agent contract

The Brain Eyes agent (`organs/PyAutoBrain/agents/conductors/eyes/`) reviews this repo:
`bin/pyauto-brain eyes survey lens/autolens_visualization`. It expects flat
`scripts/<domain>/visualization*.py` producers writing `scripts/<domain>/images/<stem>/**`, a
`gallery/gallery_run.sh` harness, and `output/gallery/{gallery.html,viz_manifest.yaml}`
(`{domain: {script: [{file, kind, group}]}}`). Keep that layout when adding domains; accepted
critiques route through intake / start_dev like any other change.

## Testing

The PR gate is `lint.yml` on Python 3.12 against the library mains:

```bash
ruff check .
ruff format --check .
python gallery/gallery_build.py --check
pytest scripts/misc/test -q
```

plus `lychee` on every `*.md`, then both producers run for real followed by
`gallery_build.py --check` (a PR that changes the figure set without regenerating `GALLERY.md`
fails). `render.yml` (manual + `repository_dispatch: pyautolens-release`) re-renders with the
released PyPI stack and commits PNGs + `GALLERY.md` back as `github-actions[bot]` `[skip ci]`.

## Sandboxed / restricted runs

```bash
NUMBA_CACHE_DIR=/tmp/numba_cache MPLCONFIGDIR=/tmp/matplotlib python scripts/imaging/visualization.py
```

## Bulk-edit safety

When editing the same region across many scripts in one pass, only rewrite the targeted region.
**Never produce a whole-file write unless you have read the entire current file.**

## Related Repos

- `../PyAutoLens` — the visualizers being rendered (plus `../PyAutoGalaxy`, `../PyAutoArray`,
  `../PyAutoFit`, `../PyAutoNerves` on `PYTHONPATH`).
- `../autolens_workspace` — user-facing science scripts and tutorials.
- `../autolens_workspace_test` — visualization *tests* (file/HDU assertions) and the gallery
  harness this repo's was adapted from.
- `../autolens_profiling` — source of the instrument presets, simulators and HST dataset.

## Task Workflows

When changing a producer, the config or a dataset, re-render (`gallery/gallery_run.sh --all`),
keep `ruff check .` / `ruff format --check .` clean, and commit the PNGs + `GALLERY.md` in the same
PR. Do not commit machine-specific absolute paths.

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
