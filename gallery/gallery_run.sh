#!/usr/bin/env bash
# Gallery runner: regenerate the visualization figures, then build GALLERY.md +
# the Eyes-contract contact sheet / manifest (gallery/gallery_build.py), then
# verify with --check.
#
# Runs every flat producer scripts/<domain>/visualization*.py from the repo root
# (each wipes and rewrites its own scripts/<domain>/images/<stem>/ tree).
#
# Usage (from anywhere):
#   bash gallery/gallery_run.sh                 # all producers + build + check
#   bash gallery/gallery_run.sh --all           # same (explicit; used by CI)
#   bash gallery/gallery_run.sh imaging         # one domain + build + check
#   bash gallery/gallery_run.sh --build-only    # skip runs, just build + check

set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

ALL_SCRIPTS=(scripts/*/visualization*.py)

run_list=()
build_only=0
for arg in "$@"; do
    case "$arg" in
        --build-only) build_only=1 ;;
        --all) run_list=("${ALL_SCRIPTS[@]}") ;;
        *)  # a domain name: select its producers
            for s in "${ALL_SCRIPTS[@]}"; do
                [[ "$s" == scripts/"$arg"/* ]] && run_list+=("$s")
            done
            ;;
    esac
done
[[ ${#run_list[@]} -eq 0 && $build_only -eq 0 ]] && run_list=("${ALL_SCRIPTS[@]}")

failures=()
for script in "${run_list[@]}"; do
    [[ -f "$script" ]] || { echo "SKIP (missing): $script"; continue; }
    echo "== $script"
    start=$SECONDS
    log="output/gallery_logs/$(echo "$script" | tr '/' '_').log"
    mkdir -p output/gallery_logs
    if python "$script" > "$log" 2>&1; then
        echo "   ok ($((SECONDS - start))s)"
    else
        echo "   FAILED ($((SECONDS - start))s) — traceback in $log"
        tail -n 30 "$log"
        failures+=("$script")
    fi
done

python gallery/gallery_build.py && python gallery/gallery_build.py --check
status=$?

if [[ ${#failures[@]} -gt 0 ]]; then
    echo
    echo "Visualization scripts FAILED (${#failures[@]}):"
    printf '  %s\n' "${failures[@]}"
    exit 1
fi
exit $status
