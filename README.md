# PyAutoEyes

**The Eyes of the PyAuto organism: where the human checks in on what every
library's figures look like.** Dashboard: **[dashboard.md](dashboard.md)**, or
with thumbnails and one-tap copy on Pages at
<https://pyautolabs.github.io/PyAutoEyes/>.

## Two layers

- **Project repos** `<lib>_visualization` (first: [`autolens_visualization`](https://github.com/PyAutoLabs/autolens_visualization))
  make, store and track the figures: producers, datasets, the tracked PNGs,
  `GALLERY.md`, and a tracked figure manifest. They re-render on every library
  release.
- **This organ** reads each project repo's manifest and builds one dashboard
  across all of them. It links to the PNGs where they live. It **renders
  nothing**, **copies no figures** and **never judges** them (the Brain's Eyes
  conductor does). It **never edits library plot code**, because accepted
  critiques route through intake → start_dev.

It is the same layering as `autolens_profiling` / `autolens_inference` under
the Brain board.

## Use

```bash
bin/pyauto-eyes board            # re-render dashboard.md + dashboard.html
bin/pyauto-eyes check            # registry, manifests, every PNG URL, dashboard current
bin/pyauto-eyes survey lens      # pyauto-brain eyes survey on the lens project repo
bin/pyauto-eyes board --offline --from lens=../../lens/autolens_visualization   # no network
```

To ask for a figure to be improved, use its **Suggest an improvement** link on
the dashboard. It opens a pre-filled issue on the project repo (title
`figure: <domain>/<file>`, the raw PNG link and a `Suggested improvement:`
stub, label `eyes-critique`). Or copy its `/eyes review <instance> <figure>`
line into a Claude Code session. The dashboard files nothing itself, and an
accepted critique becomes a PyAutoMind intake prompt that goes through
start_dev.

For each instance the dashboard also shows the Brain Eyes conductor's survey
of the local checkout (PNGs on disk, never-rendered gaps, orphan image trees,
stale renders), and the open PyAutoMind drafts that mention the instance.

## What is here

| Path | What |
|------|------|
| `registry.yaml` | one row per instance (lens today; galaxy, fit and cti follow) |
| `REFERENCE.md` | the manifest contract (schema 1), the registry fields and the refresh chain |
| `eyes/` | `registry.py`, `manifest.py`, `context.py` (survey + critiques), `board.py`, `cli.py` |
| `bin/pyauto-eyes` | `board`, `check`, `survey` |
| `dashboard.md` / `dashboard.html` / `badge.json` | generated, never hand-edited |
| `tests/` | hermetic tests (no network) |
| `.github/workflows/` | `lint.yml`, `pages_dashboard.yml`, `dashboard_refresh.yml` |

Requires Python 3.11+ and PyYAML. There is nothing to install: `bin/pyauto-eyes`
puts the repo on `sys.path`.

## AI policy

See [AI_POLICY.md](AI_POLICY.md).
