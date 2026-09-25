"""
Simulator: Instrument-Based Interferometer Datasets
===================================================

Simulates an interferometer dataset for one of the
``instruments.interferometer.INSTRUMENTS`` presets (``sma`` / ``alma`` /
``alma_high`` / ``jvla``) and writes ``data.fits``, ``noise_map.fits``,
``uv_wavelengths.fits``, ``lensed_source.fits``, ``positions.json`` and
``tracer.json`` into ``dataset/interferometer/<instrument>/``.

Copied from ``autolens_profiling/scripts/misc/simulators/interferometer.py`` with
the profiling half (phase timers, eager-vs-JIT check, ``results/simulators/`` JSON
+ bar chart) removed. One deliberate physics change: the lens mass, external
shear and source are the SAME as ``scripts/misc/simulators/imaging.py`` (so the
imaging and interferometer galleries show one lens system). The lens has no light
profile — a sub-mm/radio interferometer does not see the lens galaxy's stellar
light — so the lens here is ``Isothermal`` + ``ExternalShear`` only.

The tracked ``dataset/interferometer/sma/`` was produced by::

    python scripts/misc/simulators/interferometer.py --instrument sma

Usage
-----

    python scripts/misc/simulators/interferometer.py                  # sma (default)
    python scripts/misc/simulators/interferometer.py --instrument alma
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

from instruments.interferometer import INSTRUMENTS  # noqa: E402

_REPO_ROOT = _repo_root()


def simulate(instrument: str = "sma", output_root: Path | None = None) -> Path:
    """Simulate the named interferometer instrument. Returns the dataset directory."""
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
    real_space_shape = config["real_space_shape"]
    n_visibilities = config["n_visibilities"]
    uv_scale = config["uv_scale"]
    noise_sigma = config["noise_sigma"]
    seed = config["seed"]
    transformer_choice = config.get("transformer", "dft").lower()
    transformer_chunk_size = config.get("transformer_chunk_size", None)
    if transformer_choice == "nufft":

        def transformer_class(uv_wavelengths, real_space_mask):
            return al.TransformerNUFFT(
                uv_wavelengths=uv_wavelengths,
                real_space_mask=real_space_mask,
                chunk_size=transformer_chunk_size,
            )
    elif transformer_choice == "dft":
        transformer_class = al.TransformerDFT
    else:
        raise ValueError(f"Unknown transformer '{transformer_choice}'")

    root = output_root if output_root is not None else _REPO_ROOT
    dataset_path = root / "dataset" / "interferometer" / instrument
    dataset_path.mkdir(parents=True, exist_ok=True)

    print(f"\n--- Interferometer simulator [{instrument}] ---")
    print(f"  pixel_scale:      {pixel_scale} arcsec/px")
    print(f"  real_space_shape: {real_space_shape[0]} x {real_space_shape[1]}")
    print(f"  n_visibilities:   {n_visibilities:,}")
    print(f"  output:           {dataset_path}")

    # Interferometer does not use over-sampling.
    grid = al.Grid2D.uniform(shape_native=real_space_shape, pixel_scales=pixel_scale)

    # Synthetic baselines drawn from a 2D isotropic Gaussian whose 3-sigma envelope
    # matches ``uv_scale``. Seeded for reproducibility.
    rng = np.random.default_rng(seed)
    uv_wavelengths = rng.normal(loc=0.0, scale=uv_scale / 3.0, size=(n_visibilities, 2)).astype(
        np.float64
    )

    simulator = al.SimulatorInterferometer(
        uv_wavelengths=uv_wavelengths,
        exposure_time=300.0,
        noise_sigma=noise_sigma,
        transformer_class=transformer_class,
        noise_seed=seed,
    )

    # Same mass + shear + source as scripts/misc/simulators/imaging.py (no lens light).
    lens_galaxy = al.Galaxy(
        redshift=0.5,
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

    aplt.fits_interferometer(
        dataset=dataset,
        data_path=dataset_path / "data.fits",
        noise_map_path=dataset_path / "noise_map.fits",
        uv_wavelengths_path=dataset_path / "uv_wavelengths.fits",
        overwrite=True,
    )

    # Lensed source image (real-space) — an optional adapt-image cache (gitignored).
    lensed_source = tracer.image_2d_list_from(grid=grid)[-1]
    al.output_to_fits(
        values=lensed_source.native_for_fits,
        file_path=dataset_path / "lensed_source.fits",
        overwrite=True,
    )

    al.output_to_json(obj=positions, file_path=dataset_path / "positions.json")
    al.output_to_json(obj=tracer, file_path=dataset_path / "tracer.json")

    print(f"  wrote {dataset_path}")
    return dataset_path


if __name__ == "__main__":
    import argparse

    from autonerves import jax_wrapper  # noqa: F401

    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--instrument",
        type=str,
        default="sma",
        choices=list(INSTRUMENTS.keys()),
        help="Instrument preset to simulate (default: sma).",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=None,
        help="Override the repo root that holds dataset/ (default: inferred from this file).",
    )
    args = parser.parse_args()
    simulate(instrument=args.instrument, output_root=args.output_root)
