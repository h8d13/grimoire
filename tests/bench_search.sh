#!/bin/sh
# Cold-vs-warm search benchmark using plain `time`.
# Usage: tests/bench_search.sh [pattern]
set -eu
pattern="${1:-python}"
cache_dir="${XDG_CACHE_HOME:-$HOME/.cache}/grimaur"
grimaur="$(cd "$(dirname "$0")/.." && pwd)/grimaur"

echo "== cold (cache cleared) =="
rm -rf "$cache_dir"
time python "$grimaur" search "$pattern" --no-interactive >/dev/null

echo "== warm =="
time python "$grimaur" search "$pattern" --no-interactive >/dev/null
