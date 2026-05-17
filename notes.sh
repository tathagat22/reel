#!/usr/bin/env bash
# Summarize each .md file in ./notes with Claude Opus, routed through Reel.
# Print a per-file timing so we can compare record vs replay runs.

set -e

for f in notes/*.md; do
    echo "=== $f ==="
    START=$(python3 -c 'import time; print(time.time())')
    claude -p --model claude-opus-4-7 "Summarize this document in 5 bullet points, capturing the key technical claims:

$(cat "$f")"
    END=$(python3 -c 'import time; print(time.time())')
    echo
    echo "  (took $(python3 -c "print(round($END - $START, 2))")s)"
    echo
done
