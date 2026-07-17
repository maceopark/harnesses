#!/bin/sh
set -eu

PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
MANIFEST="$PROJECT_ROOT/discovery-study.json"
RESUME=
EVOLVE=
MAX_CANDIDATES=
MAX_PARALLEL=
ONE_GENERATION=

usage() {
    cat <<EOF
Usage:
  $0 --one-generation [--max-candidates 1-4] [--max-parallel 1-12]
  $0 --resume RUN_DIRECTORY --one-generation [--max-candidates 1-4] [--max-parallel 1-12]
  $0 --evolve PARENT_RUN_DIRECTORY --one-generation [--max-candidates 1-4] [--max-parallel 1-12]

--max-candidates is the number of open mutations. An immutable control is always
included. The default run uses twelve case-bound panes and twelve concurrent workers.
EOF
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --one-generation) ONE_GENERATION=1; shift ;;
        --resume) [ "$#" -ge 2 ] || { usage >&2; exit 2; }; RESUME=$2; shift 2 ;;
        --evolve) [ "$#" -ge 2 ] || { usage >&2; exit 2; }; EVOLVE=$2; shift 2 ;;
        --max-candidates) [ "$#" -ge 2 ] || { usage >&2; exit 2; }; MAX_CANDIDATES=$2; shift 2 ;;
        --max-parallel) [ "$#" -ge 2 ] || { usage >&2; exit 2; }; MAX_PARALLEL=$2; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) printf '%s\n' "Unknown option: $1" >&2; usage >&2; exit 2 ;;
    esac
done

[ -n "$ONE_GENERATION" ] || { printf '%s\n' "--one-generation is required" >&2; exit 2; }
[ -z "$RESUME" ] || [ -z "$EVOLVE" ] || { printf '%s\n' "--resume and --evolve are mutually exclusive" >&2; exit 2; }
case ${MAX_CANDIDATES:-4} in 1|2|3|4) ;; *) printf '%s\n' "--max-candidates must be 1-4" >&2; exit 2 ;; esac
case ${MAX_PARALLEL:-12} in 1|2|3|4|5|6|7|8|9|10|11|12) ;; *) printf '%s\n' "--max-parallel must be 1-12" >&2; exit 2 ;; esac

shell_quote() {
    printf "'%s'" "$(printf '%s' "$1" | sed "s/'/'\\\\''/g")"
}

if [ -z "${TMUX:-}" ] && [ -z "${DRIFTBENCH_TMUX_LAUNCHED:-}" ] && command -v tmux >/dev/null 2>&1; then
    COMMAND="DRIFTBENCH_TMUX_LAUNCHED=1 $(shell_quote "$0") --one-generation"
    [ -z "$RESUME" ] || COMMAND="$COMMAND --resume $(shell_quote "$RESUME")"
    [ -z "$EVOLVE" ] || COMMAND="$COMMAND --evolve $(shell_quote "$EVOLVE")"
    [ -z "$MAX_CANDIDATES" ] || COMMAND="$COMMAND --max-candidates $(shell_quote "$MAX_CANDIDATES")"
    [ -z "$MAX_PARALLEL" ] || COMMAND="$COMMAND --max-parallel $(shell_quote "$MAX_PARALLEL")"
    exec tmux new-session -s "driftbench-live-$$" "$COMMAND"
fi

set -- --manifest "$MANIFEST" --one-generation
[ -z "$MAX_CANDIDATES" ] || set -- "$@" --max-candidates "$MAX_CANDIDATES"
[ -z "$MAX_PARALLEL" ] || set -- "$@" --max-parallel "$MAX_PARALLEL"

if [ -n "$RESUME" ]; then
    exec uv run --project "$PROJECT_ROOT" driftbench discovery resume --run-dir "$RESUME" "$@"
fi
if [ -n "$EVOLVE" ]; then
    exec uv run --project "$PROJECT_ROOT" driftbench discovery evolve --parent-run "$EVOLVE" "$@"
fi
exec uv run --project "$PROJECT_ROOT" driftbench discovery run "$@"
