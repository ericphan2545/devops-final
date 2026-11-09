#!/usr/bin/env bash
# Compatibility entry point required by the Week 4 handout.
# Python is already used by this project; no third-party packages are needed.
set -euo pipefail
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
for candidate in python3 python py; do
  if command -v "$candidate" >/dev/null 2>&1 &&
     "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 9))' >/dev/null 2>&1; then
    exec "$candidate" "$script_dir/measure_downtime.py" "$@"
  fi
done
echo "Python 3.9+ is required. On Windows use: py scripts/measure_downtime.py URL --run run-01" >&2
exit 1
