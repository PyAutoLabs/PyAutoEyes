"""PyAutoEyes: the cross-project visualization dashboard organ.

The ``<lib>_visualization`` project repos make, store and track their figures,
and each one commits a tracked figure manifest. This package reads the
instance registry (``registry.yaml``), fetches each instance's manifest, and
builds the dashboard (``dashboard.md`` + ``dashboard.html``), which links to
the PNGs where they live. It renders nothing, copies no figures and judges
nothing: judgment belongs to the Brain Eyes conductor, and plot-code changes
go through intake.
"""

from pathlib import Path

ORGAN_ROOT = Path(__file__).resolve().parents[1]
