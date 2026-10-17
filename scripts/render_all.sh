#!/bin/bash
# Render the listed scenes one after another (each run uses all CPU cores).
cd "$(dirname "$0")/.."
for s in "$@"; do
  start=$(date +%s)
  python3 scripts/scenes.py "$s" > "renders/$s.log" 2>&1
  echo "$s finished in $(( $(date +%s) - start ))s: $(tail -1 renders/$s.log)"
done
