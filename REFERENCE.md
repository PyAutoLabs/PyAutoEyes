# PyAutoEyes reference: the manifest contract and the registry

This page is the interface between the organ and the `<lib>_visualization`
project repos. It says what each project repo commits and what the organ
reads. The contract is versioned, so a project repo and the organ can each
change at their own pace.

## The layering

| Layer | Owns | Never does |
|-------|------|------------|
| Project repo (`<lib>_visualization`, e.g. `lens/autolens_visualization`, `galaxy/autogalaxy_visualization`) | producers, simulators, datasets, `plots.yaml`, instruments, the tracked PNGs, `GALLERY.md`, the render harness, its lint/render workflows, and the tracked **figure manifest** | judge its own figures |
| Organ (PyAutoEyes) | `registry.yaml`, this contract, the `eyes/` package, `bin/pyauto-eyes`, `dashboard.md` / `dashboard.html` (Pages) | render, copy or store figures; judge them; edit plot code |
| Brain Eyes conductor (`PyAutoBrain/agents/conductors/eyes/`) | survey, review and critique of an instance, named by `--instance <name>` through this registry (or all of them, given the organ root) | edit plot code directly; accepted critiques route through intake → start_dev |

This is the same layering as `autolens_profiling` / `autolens_inference`
under the Brain board: the project repos hold the runs, and the organ is where
the human checks in across all of them.

## Figure manifest: schema 1

Each project repo commits the manifest at the path its registry row names
(`manifest:`, `gallery/viz_manifest.yaml` for lens). The project repo's own
gallery builder generates it (for lens, `gallery/gallery_build.py`), and it is
never edited by hand.

```yaml
schema: 1                        # contract version (integer)
generated: '2026-09-28'          # date the figure set was last rendered
rendered_with:                   # package -> version the figures were rendered with
  autolens: 2026.8.17.1
  autogalaxy: 2026.8.17.1
  autoarray: 2026.8.17.1
  autofit: 2026.8.17.1
figure_count: 40                 # == len(figures)
figures:
- file: scripts/imaging/images/visualization/dataset.png   # repo-relative .png
  producer: scripts/imaging/visualization.py               # script that wrote it
  domain: imaging                                          # grouping on the dashboard
  source: ''                                               # sub-variant ('' / parametric / delaunay ...)
  bytes: 567479                                            # file size
  sha256: 09baa3cc...                                      # 64 lowercase hex characters
```

**Required:** every key above. `rendered_with` must be a non-empty mapping
and should include the instance's `import_name`, which is the key the
freshness column reads. Each `file` must be a unique, repo-relative `.png`
path.

**What the organ reads:** the manifest at
`<images_base_url><manifest>` (the raw GitHub URL on `main`), or a local
checkout with `--offline` / `--from`. From it the organ takes `figures[*].file`
to build each figure link (`<images_base_url><file>`), `domain` and `source` to
group and label the figures, `rendered_with[<import_name>]` and `generated` for
the freshness columns, and `bytes` + `sha256` for `check`'s local integrity
test. `producer` is carried for the Brain Eyes conductor and is not displayed.

**Versioning:**

- *Additive* changes stay on schema 1. A new top-level key or a new per-figure
  key is ignored by readers that do not know it, so a project repo may add
  one before the organ reads it.
- *Breaking* changes bump `schema`. That covers renaming, removing or
  re-typing a required key, or changing what `file` is relative to. The organ
  lists the versions it reads in `eyes/manifest.py` `SUPPORTED_SCHEMAS`. It
  rejects any other version with a clear `check` failure rather than guessing.
  The order for a bump is: the organ learns the new version first, and the
  project repos bump after.

## Registry: `registry.yaml` schema 1

One row per instance. All fields are required, and `bin/pyauto-eyes check`
validates them.

| Field | Meaning (lens row) |
|-------|--------------------|
| `name` | instance key used by the dashboard, `/eyes review`, `survey` and the conductor's `--instance` (`lens`) |
| `repo` | the project repo's body-map name (`autolens_visualization`) |
| `path` | checkout relative to the workspace root (`lens/autolens_visualization`); a flat task bundle's `<root>/<repo>` is tried too |
| `github` | `owner/repo` (`PyAutoLabs/autolens_visualization`) |
| `library` | the library rendered (`PyAutoLens`) |
| `import_name` | its import / PyPI name, the freshness lookup key (`autolens`) |
| `manifest` | tracked manifest path in the project repo (`gallery/viz_manifest.yaml`) |
| `images_base_url` | raw base, `https://` and ending in `/` (`https://raw.githubusercontent.com/PyAutoLabs/autolens_visualization/main/`) |
| `gallery` | the project repo's browsable gallery (`GALLERY.md`) |
| `dispatch_event` | the library-release `repository_dispatch` the project repo re-renders on (`pyautolens-release`) |

The Brain Eyes conductor reads this file too. `pyauto-brain eyes survey
--instance <name>` (or `review`) resolves the instance's checkout from `path`
(grouped layout) or `repo` (flat bundle) under the workspace root, and it
checks the `manifest` path is present. Handing the conductor this organ's root
covers every registered instance. An instance with no local checkout is skipped
with a note. The conductor reads the registry with a stdlib parser, so rows
must stay one `key: value` string per line, as `check` enforces.

Two instances are registered today: `lens` (`autolens_visualization`,
re-rendered on `pyautolens-release`) and `galaxy` (`autogalaxy_visualization`,
re-rendered on `pyautogalaxy-release`).

Adding an instance: birth the project repo with a tracked schema-1 manifest,
and have its render workflow fire `eyes-refresh` at this repo. Create the
`eyes-critique` label on the project repo, add its row here, and run
`bin/pyauto-eyes board` and `bin/pyauto-eyes check`.

## Refresh chain

1. A library release fires `dispatch_event` at the project repo.
2. Its `render.yml` re-renders, commits the PNGs + `GALLERY.md` + manifest,
   and fires `repository_dispatch` `eyes-refresh` at `PyAutoLabs/PyAutoEyes`
   with `client_payload {repo, sha, manifest}`.
3. This repo's `dashboard_refresh.yml` re-renders the dashboard from every
   manifest's raw URL, commits `dashboard.*` as `github-actions[bot]`
   `[skip ci]` when anything changed, and dispatches `pages_dashboard.yml`.
   A daily cron runs the same step, which catches missed dispatches and new
   library releases.

## The dashboard

`dashboard.md` (on GitHub), `dashboard.html` (on Pages,
<https://pyautolabs.github.io/PyAutoEyes/>) and `badge.json` are generated and
never edited by hand.

The page opens with a counts table: `| [Instances](#instances) | n |` for
Instances, Figures, Behind and Critiques. The Brain board's Eyes strip reads
that table, so keep one `| [Label](#anchor) | n |` row per count above the
first `## ` heading.

For each instance the page shows:

- the figure count, `rendered_with`, the `generated` date, and freshness
  against the library's latest PyPI release (`unknown` when that lookup is
  offline);
- the Brain Eyes conductor's survey of the local checkout: PNGs on disk per
  domain, gaps, orphans and stale renders, plus a note when the checkout and
  the manifest disagree on the count;
- the open critiques, meaning the PyAutoMind drafts that mention the
  instance's repo name or one of its `/eyes review` lines, with links;
- the figures grouped by domain. Each figure links to its full-size raw PNG
  (a lazy thumbnail on the HTML page) and carries the critique route: a
  copyable `/eyes review <instance> <file>` line and a pre-filled "new issue"
  link on the project repo (label `eyes-critique`).

The survey and the critiques are local readings. Each section records them
in an `<!-- eyes:context name=… {json} -->` marker, and a render that cannot
read them (the CI runner has no checkout and no Brain) carries the recorded
reading forward instead of erasing it. Each instance section records the
manifest's content digest in an `<!-- eyes:instance name=… manifest=… -->`
marker. `check` compares that digest to decide whether the committed dashboard
is current. The render has no wall-clock stamp, so re-rendering unchanged
inputs is a no-op.

## `bin/pyauto-eyes`

| Command | Does |
|---------|------|
| `board [--offline] [--from [INSTANCE=]PATH] [--no-survey] [--mind PATH]` | render `dashboard.md` + `dashboard.html` + `badge.json`; `--offline` reads local checkouts and skips the PyPI lookup; `--from` points one instance at a checkout or manifest file; `--no-survey` skips the conductor survey; `--mind` names the PyAutoMind checkout for critiques |
| `check [--offline] [--from …]` | registry valid; each manifest reachable and valid; every PNG resolves (raw URL HEAD, or the local file's size + sha256); dashboard current. Exit 1 on any failure |
| `survey [<instance> \| --all]` | run `pyauto-brain eyes survey <instance checkout>` for each chosen instance (the conductor's own `--instance <name>` resolves through this registry as well) |

Image links always point at the raw GitHub URLs, never at local paths, even
when the manifest was read with `--from`. That keeps the committed dashboard
free of machine paths.
