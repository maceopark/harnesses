#!/bin/sh
set -eu

PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
STUDY="$PROJECT_ROOT/configs/evolution-study.json"
MAX_GENERATIONS=
MAX_CANDIDATES=
RESUME=
SMOKE=

usage() {
    cat <<EOF
Usage:
  $0 --max-generations 1-10 [--max-candidates 1-8]
  $0 --max-candidates 1-8 [--max-generations 1-10]
  $0 --resume RUN_DIRECTORY [--max-generations 1-10] [--max-candidates 1-8]
  $0 --smoke
  $0 --help

Options:
  --max-generations N  Bound this study to N generations (1-10).
  --max-candidates N   Bound each generation to N candidates (1-8).
  --resume DIR         Resume a digest-bound evolution run.
  --smoke              Run only one train case and the frozen candidate (2 repetitions).
  -h, --help           Show this help and exit.

With no options, this help is displayed. The checked-in study uses 8 candidates,
up to 10 generations, adaptive 2-5 repetitions, and a public 6/3/3 split.
EOF
}

if [ "$#" -eq 0 ]; then
    usage
    exit 0
fi

while [ "$#" -gt 0 ]; do
    case "$1" in
        -h|--help) usage; exit 0 ;;
        --max-generations)
            [ "$#" -ge 2 ] || { printf '%s\n\n' "Missing value for --max-generations" >&2; usage >&2; exit 2; }
            MAX_GENERATIONS=$2; shift 2 ;;
        --max-candidates)
            [ "$#" -ge 2 ] || { printf '%s\n\n' "Missing value for --max-candidates" >&2; usage >&2; exit 2; }
            MAX_CANDIDATES=$2; shift 2 ;;
        --resume)
            [ "$#" -ge 2 ] || { printf '%s\n\n' "Missing value for --resume" >&2; usage >&2; exit 2; }
            RESUME=$2; shift 2 ;;
        --smoke) SMOKE=1; shift ;;
        *) printf '%s\n\n' "Unknown option: $1" >&2; usage >&2; exit 2 ;;
    esac
done

if [ -n "$MAX_GENERATIONS" ]; then
    case "$MAX_GENERATIONS" in 1|2|3|4|5|6|7|8|9|10) ;; *)
        printf '%s\n' "--max-generations must be between 1 and 10" >&2; exit 2;;
    esac
fi
if [ -n "$MAX_CANDIDATES" ]; then
    case "$MAX_CANDIDATES" in 1|2|3|4|5|6|7|8) ;; *)
        printf '%s\n' "--max-candidates must be between 1 and 8" >&2; exit 2;;
    esac
fi

set --
[ -z "$MAX_GENERATIONS" ] || set -- "$@" --max-generations "$MAX_GENERATIONS"
[ -z "$MAX_CANDIDATES" ] || set -- "$@" --max-candidates "$MAX_CANDIDATES"
[ -z "$SMOKE" ] || set -- "$@" --smoke

if [ -n "$RESUME" ]; then
    exec uv run --project "$PROJECT_ROOT" driftbench interview-eval resume \
        --run-dir "$RESUME" "$@"
fi

exec uv run --project "$PROJECT_ROOT" driftbench interview-eval run \
    --study "$STUDY" "$@"
