"""Per-instrument dataset presets — single source of truth across the repo.

This package decouples instrument configuration (pixel_scale, mask_radius,
PSF shape, visibility count, transformer config, ...) from the simulator
and likelihood-fit code that consume it. Multiple consumers — simulators,
``likelihood_runtime/``, ``likelihood_breakdown/``, ``vram/`` — read the
same dicts, so they live in their own module.

Public API::

    from instruments.imaging import INSTRUMENTS, mask_radius_pixels
    from instruments.interferometer import INSTRUMENTS, transformer_chunk_size_for

The legacy ``from simulators.{imaging,interferometer} import INSTRUMENTS``
imports continue to work via re-exports in those modules.
"""

from instruments import imaging, interferometer  # noqa: F401

__all__ = ["imaging", "interferometer"]
