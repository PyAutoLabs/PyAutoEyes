"""Per-instrument imaging dataset presets.

The single source of truth for imaging dataset geometry + simulator
configuration across `autolens_profiling`. Consumed by:

- ``simulators/imaging.py`` (re-exports ``INSTRUMENTS`` and uses every field
  to drive the simulator).
- ``scripts/imaging/likelihood_runtime/{delaunay,mge,pixelization}.py`` (read
  ``pixel_scale`` and ``mask_radius`` to set up the dataset for profiling).
- ``scripts/imaging/likelihood_breakdown/*.py`` (same as above).
- ``vram/config.py`` (uses instrument keys to index the vmap batch_size
  table — only the keys are referenced there, not the field values).

Each preset's fields:

- ``pixel_scale``     — arcsec per pixel.
- ``mask_radius``     — circular mask radius in arcsec.
- ``psf_shape``       — (n_y, n_x) shape of the simulated PSF kernel.
- ``psf_sigma``       — Gaussian PSF width in arcsec.
- ``seed``            — RNG seed for noise generation in the simulator.

To add a new instrument: append a row, then probe the per-(cell, instrument)
vmap batch size via ``vram/`` and add the matching rows in
``vram/config.py:VMAP_BATCH``.
"""

from __future__ import annotations

INSTRUMENTS: dict[str, dict] = {
    "euclid": {
        "pixel_scale": 0.1,
        "mask_radius": 3.5,
        "psf_shape": (21, 21),
        "psf_sigma": 0.1,
        "seed": 1,
    },
    "hst": {
        "pixel_scale": 0.05,
        "mask_radius": 3.5,
        "psf_shape": (21, 21),
        "psf_sigma": 0.05,
        "seed": 1,
    },
    "jwst": {
        "pixel_scale": 0.03,
        "mask_radius": 3.5,
        "psf_shape": (21, 21),
        "psf_sigma": 0.03,
        "seed": 1,
    },
    # JWST long-wavelength channel (F277W/F444W): 0.06 arcsec/px, half the
    # short-wavelength (F115W/F150W) sampling. Paired with ``jwst`` (0.03) it
    # gives the two distinct masked-pixel counts the multi-band datacube A/B
    # needs to test whether heterogeneous per-band shapes block XLA fusion
    # sharing across FactorGraphModel factors (see searches/_setup.py).
    "jwst_lw": {
        "pixel_scale": 0.06,
        "mask_radius": 3.5,
        "psf_shape": (21, 21),
        "psf_sigma": 0.06,
        "seed": 1,
    },
    "ao": {
        "pixel_scale": 0.01,
        "mask_radius": 3.5,
        "psf_shape": (21, 21),
        "psf_sigma": 0.01,
        "seed": 1,
    },
}


def mask_radius_pixels(instrument: str) -> int:
    """Mask radius in pixels = ``mask_radius_arcsec / pixel_scale``."""
    cfg = INSTRUMENTS[instrument]
    return int(round(cfg["mask_radius"] / cfg["pixel_scale"]))


def shape_native(instrument: str) -> tuple[int, int]:
    """Native data grid shape derived from mask radius + pixel scale.

    The simulator uses ``shape_pixels = ceil(2 * mask_radius / pixel_scale)``
    (with a tight bounding box around the unmasked circle). This helper
    replicates that math so consumers can size their grids consistently.
    """
    cfg = INSTRUMENTS[instrument]
    n = int(-(-2 * cfg["mask_radius"] // cfg["pixel_scale"]))  # ceil-div
    return (n, n)
