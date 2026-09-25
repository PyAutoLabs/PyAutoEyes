#!/usr/bin/env bash
# Activate a PyAuto venv and point PYTHONPATH at the PyAuto* library source
# checkouts, so the producers render against the libraries you are editing.
#
# Adapted from autolens_profiling/activate.sh (which targets the RAL HPC mirror).
# This repo has no HPC leg: it resolves the libraries from the PyAutoLabs
# workspace layout this checkout sits in (lens/autolens_visualization ->
# organs/PyAutoNerves, fit/PyAutoFit, array/PyAutoArray, galaxy/PyAutoGalaxy,
# lens/PyAutoLens). Override with PYAUTO_LIB_BASE=<dir holding all five repos>
# for a flat layout, and PYAUTO_VENV=<venv dir> to activate a venv first.
#
# Usage (from anywhere):
#
#     source lens/autolens_visualization/activate.sh
#     bash gallery/gallery_run.sh --all

_viz_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -n "${PYAUTO_VENV:-}" ] && [ -f "$PYAUTO_VENV/bin/activate" ]; then
    # shellcheck disable=SC1091
    source "$PYAUTO_VENV/bin/activate"
fi

if [ -n "${PYAUTO_LIB_BASE:-}" ]; then
    _libs="$PYAUTO_LIB_BASE/PyAutoNerves:$PYAUTO_LIB_BASE/PyAutoFit:$PYAUTO_LIB_BASE/PyAutoArray:$PYAUTO_LIB_BASE/PyAutoGalaxy:$PYAUTO_LIB_BASE/PyAutoLens"
else
    _ws="$(cd "$_viz_root/../.." && pwd)"
    _libs="$_ws/organs/PyAutoNerves:$_ws/fit/PyAutoFit:$_ws/array/PyAutoArray:$_ws/galaxy/PyAutoGalaxy:$_ws/lens/PyAutoLens"
fi

export PYTHONPATH="$_libs${PYTHONPATH:+:$PYTHONPATH}"
export NUMBA_CACHE_DIR="${NUMBA_CACHE_DIR:-/tmp/numba_cache}"
export MPLCONFIGDIR="${MPLCONFIGDIR:-/tmp/matplotlib}"
mkdir -p "$NUMBA_CACHE_DIR" "$MPLCONFIGDIR"
unset _viz_root _ws _libs
