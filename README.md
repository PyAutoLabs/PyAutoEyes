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

To ask for a figure to be improved, copy its `/eyes review <instance> <figure>`
line from the dashboard into a Claude Code session.

## What is here

| Path | What |
|------|------|
| `registry.yaml` | one row per instance (lens today; galaxy, fit and cti follow) |
| `REFERENCE.md` | the manifest contract (schema 1), the registry fields and the refresh chain |
| `eyes/` | `registry.py`, `manifest.py`, `board.py`, `cli.py` |
| `bin/pyauto-eyes` | `board`, `check`, `survey` |
| `dashboard.md` / `dashboard.html` | generated, never hand-edited |
| `tests/` | hermetic tests (no network) |
| `.github/workflows/` | `lint.yml`, `pages_dashboard.yml`, `dashboard_refresh.yml` |

Requires Python 3.11+ and PyYAML. There is nothing to install: `bin/pyauto-eyes`
puts the repo on `sys.path`.

## AI policy

See [AI_POLICY.md](AI_POLICY.md).
