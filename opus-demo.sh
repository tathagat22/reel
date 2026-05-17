#!/usr/bin/env bash
# opus-demo.sh — self-narrating Reel demo for screen recording.
#
# Walks through: clean setup → record real Opus calls → replay from disk
# → cost comparison. Pauses on key beats so the viewer can read each step.
#
# Run:   ./opus-demo.sh
# Requires: claude (Claude Code CLI), uv, ~/reel checked out.

set -u

# ── visual helpers ─────────────────────────────────────────────────────────
B="\033[1m"; D="\033[2m"; R="\033[0m"
G="\033[32m"; C="\033[36m"; Y="\033[33m"; M="\033[35m"; RED="\033[31m"

CASSETTE=~/.reel/opus-demo.jsonl
PORT=7878
LOG=/tmp/reel-opus-demo.log
REEL_PID=""

pause()    { echo; read -p "  $(printf "${D}⏎  press enter${R}")" _; echo; }
title()    { clear; printf "${B}${C}%s${R}\n${D}%s${R}\n\n" "$1" "$2"; }
section()  { printf "${B}${M}── %s ──${R}\n\n" "$1"; }
note()     { printf "${D}%s${R}\n" "$1"; }
cmd()      { printf "  ${G}\$${R} ${B}%s${R}\n" "$1"; }
ok()       { printf "  ${G}✓${R} %s\n" "$1"; }
warn()     { printf "  ${Y}!${R} %s\n" "$1"; }

cleanup() {
    if [ -n "$REEL_PID" ]; then
        kill "$REEL_PID" 2>/dev/null || true
    fi
    pkill -f "reel auto" 2>/dev/null || true
}
trap cleanup EXIT

# ── prereq checks ──────────────────────────────────────────────────────────
if ! command -v claude >/dev/null 2>&1; then
    printf "${RED}error:${R} \`claude\` is not on PATH. Install Claude Code first.\n"
    exit 1
fi
if [ ! -d ~/reel ]; then
    printf "${RED}error:${R} ~/reel not found. Clone the repo first.\n"
    exit 1
fi
cd ~/reel

# ── ACT 1: setup ───────────────────────────────────────────────────────────
title "Reel — VCR for LLM APIs" \
      "Demo: run the same Claude Opus job three times and pay only once."

note "We're going to:"
echo "    1. Start Reel (a local HTTP proxy)"
echo "    2. Point Claude Code at it via ANTHROPIC_BASE_URL"
echo "    3. Summarize three real markdown docs with Opus — RECORD"
echo "    4. Run the exact same job two more times — REPLAY from disk"
echo "    5. Show the cost comparison"
echo
note "Setup state: fresh start, no cached responses."
pause

section "Step 1 — clean slate"
mkdir -p ~/.reel
rm -f "$CASSETTE" "$LOG"
ok "cleared $CASSETTE"

mkdir -p notes
rm -f notes/*.md
cp README.md notes/reel-readme.md
cp ARCHITECTURE.md notes/architecture.md
cp CHANGELOG.md notes/changelog.md
TOTAL_BYTES=$(wc -c < notes/reel-readme.md)
TOTAL_BYTES=$((TOTAL_BYTES + $(wc -c < notes/architecture.md)))
TOTAL_BYTES=$((TOTAL_BYTES + $(wc -c < notes/changelog.md)))
ok "loaded 3 docs into notes/  ($TOTAL_BYTES bytes total)"
pause

section "Step 2 — start Reel on port $PORT"
cmd "reel auto -c $CASSETTE --port $PORT  &"
uv run reel auto -c "$CASSETTE" --port "$PORT" > "$LOG" 2>&1 &
REEL_PID=$!
sleep 2
if ! ps -p "$REEL_PID" > /dev/null; then
    printf "${RED}error:${R} reel failed to start. Log:\n"
    tail "$LOG"
    exit 1
fi
ok "reel up (pid $REEL_PID), proxying to api.anthropic.com"
echo
cmd "export ANTHROPIC_BASE_URL=http://127.0.0.1:$PORT"
export ANTHROPIC_BASE_URL="http://127.0.0.1:$PORT"
ok "Claude Code will now route through Reel"
pause

# ── ACT 2: record ──────────────────────────────────────────────────────────
section "Step 3 — RECORD: real Opus calls, real money"
note "Running summarizer over 3 markdown files. Each file → one Opus call."
note "This is the only time we'll actually hit api.anthropic.com."
echo
cmd "./notes.sh   # first run"
echo
RECORD_START=$(python3 -c 'import time; print(time.time())')
./notes.sh > /tmp/opus-r1.out 2>&1
RECORD_END=$(python3 -c 'import time; print(time.time())')
RECORD_WALL=$(python3 -c "print(round($RECORD_END - $RECORD_START, 2))")

ENTRIES_AFTER_R1=$(wc -l < "$CASSETTE")
ok "run complete in ${RECORD_WALL}s"
ok "$ENTRIES_AFTER_R1 entries written to cassette"
echo
note "Proxy log for run 1 (real upstream times — note the ms values):"
grep "anthropic POST" "$LOG" | tail -3 | sed 's/^/    /'
pause

# ── ACT 3: replay ──────────────────────────────────────────────────────────
section "Step 4 — REPLAY: same job, served from disk"
note "Running the exact same script two more times. Watch the proxy times."
echo
cmd "./notes.sh   # second run (replay)"
echo
REPLAY2_START=$(python3 -c 'import time; print(time.time())')
./notes.sh > /tmp/opus-r2.out 2>&1
REPLAY2_END=$(python3 -c 'import time; print(time.time())')
REPLAY2_WALL=$(python3 -c "print(round($REPLAY2_END - $REPLAY2_START, 2))")
ENTRIES_AFTER_R2=$(wc -l < "$CASSETTE")
ok "run 2 done in ${REPLAY2_WALL}s — cassette still at $ENTRIES_AFTER_R2 entries (no re-record)"
echo
cmd "./notes.sh   # third run (replay)"
echo
REPLAY3_START=$(python3 -c 'import time; print(time.time())')
./notes.sh > /tmp/opus-r3.out 2>&1
REPLAY3_END=$(python3 -c 'import time; print(time.time())')
REPLAY3_WALL=$(python3 -c "print(round($REPLAY3_END - $REPLAY3_START, 2))")
ENTRIES_AFTER_R3=$(wc -l < "$CASSETTE")
ok "run 3 done in ${REPLAY3_WALL}s — cassette still at $ENTRIES_AFTER_R3 entries"
echo
note "Proxy log: real upstream calls vs replay hits (look at the ms column):"
grep "anthropic POST" "$LOG" | sed 's/^/    /'
pause

# ── ACT 4: verify ──────────────────────────────────────────────────────────
section "Step 5 — verify byte-identical output across runs"
grep -v "(took" /tmp/opus-r1.out > /tmp/opus-r1.clean
grep -v "(took" /tmp/opus-r2.out > /tmp/opus-r2.clean
grep -v "(took" /tmp/opus-r3.out > /tmp/opus-r3.clean

cmd "diff -q run1 run2"
if diff -q /tmp/opus-r1.clean /tmp/opus-r2.clean > /dev/null; then
    ok "run 1 and run 2: byte-identical output"
else
    warn "run 1 and run 2: outputs differ"
fi
cmd "diff -q run1 run3"
if diff -q /tmp/opus-r1.clean /tmp/opus-r3.clean > /dev/null; then
    ok "run 1 and run 3: byte-identical output"
else
    warn "run 1 and run 3: outputs differ"
fi
pause

# ── ACT 5: cost summary ────────────────────────────────────────────────────
section "Step 6 — what would this have cost without Reel?"
cmd "reel cost -c $CASSETTE"
echo
uv run reel cost -c "$CASSETTE"
echo

# Pull the total $ from the cost report
COST_PER_RUN=$(uv run reel cost -c "$CASSETTE" 2>&1 \
    | grep -E "^│ TOTAL" \
    | awk -F'│' '{print $7}' \
    | tr -d ' $')
RUNS=3
WITHOUT_REEL=$(python3 -c "print(f'{$COST_PER_RUN * $RUNS:.4f}')")
SAVED=$(python3 -c "print(f'{$COST_PER_RUN * ($RUNS - 1):.4f}')")

note "Reading that table:"
echo "    • Cost of recording (run 1):       \$$COST_PER_RUN"
echo "    • Cost of replay (runs 2 + 3):     \$0.0000 each"
echo "    • Total spent across $RUNS runs:        \$$COST_PER_RUN"
echo "    • Cost without Reel ($RUNS × run 1):   \$$WITHOUT_REEL"
echo "    • Saved across $RUNS runs:              \$$SAVED"
echo
note "Scale the math: 10 runs saves $(python3 -c "print(f'\${$COST_PER_RUN * 9:.2f}')"). 100 runs saves $(python3 -c "print(f'\${$COST_PER_RUN * 99:.2f}')")."
note "The bigger the prompt and the more iterations, the more this matters."
echo
section "What just happened"
echo "    • Reel is a local HTTP proxy on port $PORT"
echo "    • Run 1 hit api.anthropic.com once per doc → cost real \$"
echo "    • Runs 2 + 3 served identical bytes from $CASSETTE"
echo "    • Same output. Same model. Same prompt. Different bill."
echo
ok "demo complete"
echo
cmd "reel inspect -c $CASSETTE   # browse what got captured"
cmd "reel stats -c $CASSETTE     # see hit rate, token counts, latency"
echo
note "Cassette is plain JSONL — grep it, diff it, commit it in PRs."
echo
