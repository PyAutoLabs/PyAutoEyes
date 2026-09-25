"""
Visualization: Interferometer
=============================

Renders every figure ``VisualizerInterferometer`` writes during a real PyAutoLens
model-fit, on the SMA-preset interferometer dataset, so the most up-to-date version of
each figure lives in git and can be browsed on GitHub (``GALLERY.md``) without
re-running a fit.

This script RENDERS, it does not test: there are no assertions on file names or FITS
HDUs (that is ``autolens_workspace_test``'s job). Which figures appear is governed by
``config/visualize/plots.yaml`` (every toggle on).

Output tree (wiped at the start of every run so stale PNGs never linger)::

    scripts/interferometer/images/visualization/
        dataset.png, image_with_positions.png, adapt_images.png   <- visualize_before_fit
        parametric/   <- visualize(), SersicCore light-profile source
        delaunay/     <- visualize(), Delaunay pixelized source (Overlay image-mesh)

The FITS / CSV products the visualizer also writes are gitignored; only PNGs are tracked.

Dataset: ``dataset/interferometer/sma`` (190 visibilities, 256x256 real-space grid at
0.1"/pix, circular real-space mask 3.5", exact DFT transformer), simulated by
``scripts/misc/simulators/interferometer.py --instrument sma`` with the same lens mass,
shear and source as the imaging dataset (no lens light). The model is that TRUE model.

Run from the repo root::

    python scripts/interferometer/visualization.py
"""

import shutil
import sys
import time
from pathlib import Path
from types import SimpleNamespace


def _repo_root() -> Path:
    for _p in Path(__file__).resolve().parents:
        if (_p / "ruff.toml").exists():
            return _p
    raise RuntimeError("autolens_visualization root (ruff.toml) not found")


REPO_ROOT = _repo_root()
sys.path.insert(0, str(REPO_ROOT))

# Push the all-true plots.yaml before any visualization code path reads config.
from autolens import conf

conf.instance.push(
    new_path=str(REPO_ROOT / "config"),
    output_path=str(REPO_ROOT / "scripts" / "interferometer" / "images"),
)

import autofit as af
import autolens as al
from autolens.interferometer.model.visualizer import VisualizerInterferometer

from _viz_cli import auto_simulate_if_missing
from instruments.interferometer import INSTRUMENTS

INSTRUMENT = "sma"

"""
__Dataset__

The SMA preset: a circular real-space mask on the preset's real-space grid, and the
exact DFT transformer (190 visibilities make the DFT cheap).
"""
config = INSTRUMENTS[INSTRUMENT]
dataset_path = REPO_ROOT / "dataset" / "interferometer" / INSTRUMENT

auto_simulate_if_missing(
    dataset_path, dataset_type="interferometer", instrument=INSTRUMENT, workspace_root=REPO_ROOT
)

real_space_mask = al.Mask2D.circular(
    shape_native=config["real_space_shape"],
    pixel_scales=config["pixel_scale"],
    radius=config["mask_radius"],
)

dataset = al.Interferometer.from_fits(
    data_path=dataset_path / "data.fits",
    noise_map_path=dataset_path / "noise_map.fits",
    uv_wavelengths_path=dataset_path / "uv_wavelengths.fits",
    real_space_mask=real_space_mask,
    transformer_class=al.TransformerDFT,
)

"""
__Positions__

The multiple-image positions the simulator solved for, drawn by ``image_with_positions``.
"""
positions = al.Grid2DIrregular(al.from_json(file_path=dataset_path / "positions.json"))
positions_likelihood = al.PositionsLH(positions=positions, threshold=0.5)

"""
__True Model__

Restated verbatim from ``scripts/misc/simulators/interferometer.py``: an Isothermal
mass lens at z=0.5 (no light) with an ExternalShear ``MassField``, and a SersicCore
source at z=1.0. Every parameter is fixed, so the prior-median instance IS the true
model.
"""
lens = af.Model(
    al.Galaxy,
    redshift=0.5,
    mass=al.mp.Isothermal(
        centre=(0.0, 0.0),
        einstein_radius=1.6,
        ell_comps=al.convert.ell_comps_from(axis_ratio=0.9, angle=45.0),
    ),
)

fields = af.Collection(
    field=al.MassField(redshift=0.5, shear=al.mp.ExternalShear(gamma_1=0.05, gamma_2=0.05))
)

source_parametric = af.Model(
    al.Galaxy,
    redshift=1.0,
    bulge=al.lp.SersicCore(
        centre=(0.0, 0.0),
        ell_comps=al.convert.ell_comps_from(axis_ratio=0.8, angle=60.0),
        intensity=4.0,
        effective_radius=0.1,
        sersic_index=1.0,
    ),
)

model_parametric = af.Collection(
    galaxies=af.Collection(lens=lens, source=source_parametric), fields=fields
)

"""
__Delaunay Source__

The same lens with the source replaced by a Delaunay pixelization whose vertices come
from an ``Overlay`` image-mesh over the real-space mask, regularized by ``ConstantSplit``.
"""
image_mesh = al.image_mesh.Overlay(shape=(26, 26))
image_plane_mesh_grid = image_mesh.image_plane_mesh_grid_from(mask=real_space_mask)

pixelization = al.Pixelization(
    mesh=al.mesh.Delaunay(pixels=image_plane_mesh_grid.shape[0], zeroed_pixels=0),
    regularization=al.reg.ConstantSplit(coefficient=1.0),
)
source_delaunay = af.Model(al.Galaxy, redshift=1.0, pixelization=pixelization)

model_delaunay = af.Collection(
    galaxies=af.Collection(lens=lens, source=source_delaunay), fields=fields
)

"""
__Adapt Images__

Built from the real-space per-galaxy images of the parametric (true-model) fit. The
lens has no light, so only the source carries an adapt image; the Overlay mesh grid
is attached to the source.
"""
instance_parametric = model_parametric.instance_from_prior_medians()

fit_parametric = al.FitInterferometer(
    dataset=dataset,
    tracer=al.Tracer(
        galaxies=list(instance_parametric.galaxies),
        fields=list(instance_parametric.fields),
    ),
)

adapt_images = al.AdaptImages(
    galaxy_name_image_dict={
        "('galaxies', 'source')": fit_parametric.galaxy_image_dict[
            instance_parametric.galaxies.source
        ],
    },
    galaxy_name_image_plane_mesh_grid_dict={"('galaxies', 'source')": image_plane_mesh_grid},
)

analysis = al.AnalysisInterferometer(
    dataset=dataset,
    positions_likelihood_list=[positions_likelihood],
    adapt_images=adapt_images,
    use_jax=False,
)

"""
__Paths__

``VisualizerInterferometer`` only needs ``image_path`` and ``output_path``. The image
tree is wiped first so the committed PNG set is exactly what this run produced.
"""
image_path = REPO_ROOT / "scripts" / "interferometer" / "images" / "visualization"
if image_path.exists():
    shutil.rmtree(image_path)
image_path.mkdir(parents=True)

scratch_root = REPO_ROOT / "output" / "visualization" / "interferometer"
if scratch_root.exists():
    shutil.rmtree(scratch_root)


def _paths(sub: str | None) -> SimpleNamespace:
    img = image_path / sub if sub else image_path
    img.mkdir(parents=True, exist_ok=True)
    out = scratch_root / (sub or "before_fit")  # positions info etc. -> gitignored output/
    out.mkdir(parents=True, exist_ok=True)
    return SimpleNamespace(image_path=img, output_path=out)


"""
__Visualize Before Fit__

dataset.png, image_with_positions.png, adapt_images.png (+ gitignored FITS).
"""
t0 = time.perf_counter()
VisualizerInterferometer.visualize_before_fit(
    analysis=analysis, paths=_paths(None), model=model_parametric
)
print(f"visualize_before_fit: {time.perf_counter() - t0:.1f}s")

"""
__Visualize (per source)__

fit, dirty images, real space, tracer, galaxies (+ inversion for Delaunay).
"""
for name, model in (("parametric", model_parametric), ("delaunay", model_delaunay)):
    t0 = time.perf_counter()
    VisualizerInterferometer.visualize(
        analysis=analysis,
        paths=_paths(name),
        instance=model.instance_from_prior_medians(),
        during_analysis=False,
    )
    print(f"visualize [{name}]: {time.perf_counter() - t0:.1f}s")

n_png = len(list(image_path.rglob("*.png")))
print(f"Wrote {n_png} PNGs under {image_path.relative_to(REPO_ROOT)}")
