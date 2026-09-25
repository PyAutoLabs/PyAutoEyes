"""
Simulator: Instrument-Based Imaging Datasets
============================================

Simulates an imaging dataset for one of the ``instruments.imaging.INSTRUMENTS``
presets (``euclid`` / ``hst`` / ``jwst`` / ``jwst_lw`` / ``ao``) and writes
``data.fits``, ``psf.fits``, ``noise_map.fits``, ``lensed_source.fits``,
``positions.json`` and ``tracer.json`` into ``dataset/imaging/<instrument>/``.

Copied from ``autolens_profiling/scripts/misc/simulators/imaging.py`` with the
profiling half (phase timers, eager-vs-JIT check, ``results/simulators/`` JSON +
bar chart) removed — this repo renders figures and has no ``results/`` tree. The
physics (grid, over-sampling, PSF, simulator settings, lens + source) is unchanged.

The tracked ``dataset/imaging/hst/`` was copied byte-for-byte from
``autolens_profiling`` rather than regenerated here (profiling documents that its
hst copy does not re-simulate byte-identically); run this only to add a new
instrument or to rebuild a deleted dataset.

The true model (restated verbatim by ``scripts/imaging/visualization.py``):

- lens  (z=0.5): ``Sersic`` bulge + ``Isothermal`` mass, plus an ``ExternalShear``
  ``MassField`` at the lens redshift.
- source (z=1.0): ``SersicCore`` bulge.

Usage
-----

    python scripts/misc/simulators/imaging.py                       # hst (default)
    python scripts/misc/simulators/imaging.py --instrument euclid
"""

import sys as _sys
from pathlib import Path as _Path


def _repo_root() -> _Path:
    for _p in _Path(__file__).resolve().parents:
        if (_p / "ruff.toml").exists():
            return _p
    raise RuntimeError("autolens_visualization root (ruff.toml) not found")


for _extra in (_repo_root(), _repo_root() / "scripts" / "misc"):
    if str(_extra) not in _sys.path:
        _sys.path.insert(0, str(_extra))

from pathlib import Path

from instruments.imaging import INSTRUMENTS  # noqa: E402

_REPO_ROOT = _repo_root()


def simulate(instrument: str = "hst", output_root: Path | None = None) -> Path:
    """Simulate the named imaging instrument. Returns the dataset dir."""
    import matplotlib
    import numpy as np

    matplotlib.use("Agg")
    import autolens as al
    import autolens.plot as aplt

    if instrument not in INSTRUMENTS:
        raise ValueError(
            f"Unknown instrument '{instrument}'. Choose from: {list(INSTRUMENTS.keys())}"
        )

    config = INSTRUMENTS[instrument]
    pixel_scale = config["pixel_scale"]
    mask_radius = config["mask_radius"]
    psf_shape = config["psf_shape"]
    psf_sigma = config["psf_sigma"]
    seed = config["seed"]

    root = output_root if output_root is not None else _REPO_ROOT
    dataset_path = root / "dataset" / "imaging" / instrument
    dataset_path.mkdir(parents=True, exist_ok=True)

    # Grid size derived so the mask_radius circular mask fits in the image.
    shape_pixels = int(np.ceil(2 * mask_radius / pixel_scale))
    if shape_pixels % 2 == 0:
        shape_pixels += 1  # odd for symmetric centering

    print(f"\n--- Imaging simulator [{instrument}] ---")
    print(f"  pixel_scale: {pixel_scale} arcsec/px")
    print(f"  grid_shape:  {shape_pixels} x {shape_pixels}")
    print(f"  output:      {dataset_path}")

    grid = al.Grid2D.uniform(shape_native=(shape_pixels, shape_pixels), pixel_scales=pixel_scale)
    over_sample_size = al.util.over_sample.over_sample_size_via_radial_bins_from(
        grid=grid,
        sub_size_list=[32, 8, 2],
        radial_list=[0.3, 0.6],
        centre_list=[(0.0, 0.0)],
    )
    grid = grid.apply_over_sampling(over_sample_size=over_sample_size)

    psf = al.Convolver.from_gaussian(
        shape_native=psf_shape,
        sigma=psf_sigma,
        pixel_scales=grid.pixel_scales,
    )
    simulator = al.SimulatorImaging(
        exposure_time=300.0,
        psf=psf,
        background_sky_level=0.1,
        add_poisson_noise_to_data=True,
        noise_seed=seed,
    )

    lens_galaxy = al.Galaxy(
        redshift=0.5,
        bulge=al.lp.Sersic(
            centre=(0.0, 0.0),
            ell_comps=al.convert.ell_comps_from(axis_ratio=0.9, angle=45.0),
            intensity=2.0,
            effective_radius=0.6,
            sersic_index=3.0,
        ),
        mass=al.mp.Isothermal(
            centre=(0.0, 0.0),
            einstein_radius=1.6,
            ell_comps=al.convert.ell_comps_from(axis_ratio=0.9, angle=45.0),
        ),
    )
    field = al.MassField(redshift=0.5, shear=al.mp.ExternalShear(gamma_1=0.05, gamma_2=0.05))

    source_galaxy = al.Galaxy(
        redshift=1.0,
        bulge=al.lp.SersicCore(
            centre=(0.0, 0.0),
            ell_comps=al.convert.ell_comps_from(axis_ratio=0.8, angle=60.0),
            intensity=4.0,
            effective_radius=0.1,
            sersic_index=1.0,
        ),
    )

    tracer = al.Tracer(galaxies=[lens_galaxy, source_galaxy], fields=[field])

    dataset = simulator.via_tracer_from(tracer=tracer, grid=grid)

    solver = al.PointSolver.for_grid(
        grid=grid, pixel_scale_precision=0.001, magnification_threshold=0.1
    )
    positions = solver.solve(tracer=tracer, source_plane_coordinate=source_galaxy.bulge.centre)

    aplt.fits_imaging(
        dataset=dataset,
        data_path=dataset_path / "data.fits",
        psf_path=dataset_path / "psf.fits",
        noise_map_path=dataset_path / "noise_map.fits",
        overwrite=True,
    )

    # Lensed source image (PSF-convolved) — an optional adapt-image cache (gitignored).
    lensed_source_unblurred = tracer.image_2d_list_from(grid=grid)[-1]
    lensed_source = psf.convolved_image_from(image=lensed_source_unblurred, blurring_image=None)
    al.output_to_fits(
        values=lensed_source.native_for_fits,
        file_path=dataset_path / "lensed_source.fits",
        overwrite=True,
    )

    al.output_to_json(obj=tracer, file_path=dataset_path / "tracer.json")
    al.output_to_json(obj=positions, file_path=dataset_path / "positions.json")

    print(f"  wrote {dataset_path}")
    return dataset_path


if __name__ == "__main__":
    import argparse

    from autonerves import jax_wrapper  # noqa: F401

    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--instrument",
        type=str,
        default="hst",
        choices=list(INSTRUMENTS.keys()),
        help="Instrument preset to simulate (default: hst).",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=None,
        help="Override the repo root that holds dataset/ (default: inferred from this file).",
    )
    args = parser.parse_args()
    simulate(instrument=args.instrument, output_root=args.output_root)
