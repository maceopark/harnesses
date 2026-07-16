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
  $0 --one-generation [--max-candidates 1-4] [--max-parallel 1-4]
  $0 --resume RUN_DIRECTORY --one-generation [--max-candidates 1-4] [--max-parallel 1-4]
  $0 --evolve PARENT_RUN_DIRECTORY --one-generation [--max-candidates 1-4] [--max-parallel 1-4]
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
case ${MAX_PARALLEL:-4} in 1|2|3|4) ;; *) printf '%s\n' "--max-parallel must be 1-4" >&2; exit 2 ;; esac

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
