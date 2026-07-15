#!/bin/sh
set -eu

PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
POLICY="$PROJECT_ROOT/configs/interview-eval.json"
MAX_CELLS=
MAX_PARALLEL=1
RESUME=

usage() {
    cat <<EOF
Usage:
  $0 --max-cells 1-6 [--max-parallel 1-6]
  $0 --max-parallel 1-6 [--max-cells 1-6]
  $0 --resume RUN_DIRECTORY [--max-cells 1-6] [--max-parallel 1-6]
  $0 --help

Options:
  --max-cells N       Process at most N pending case cells in this invocation.
  --max-parallel N    Run up to N case cells concurrently (default: 1).
  --resume DIR        Resume an existing frozen-only interview-eval run.
  -h, --help          Show this help and exit.

With no options, this help is displayed. To start all six cells serially, use
--max-parallel 1. If not already inside tmux, the wrapper creates a session first.
EOF
}

if [ "$#" -eq 0 ]; then
    usage
    exit 0
fi

while [ "$#" -gt 0 ]; do
    case "$1" in
        -h|--help)
            usage
            exit 0
            ;;
        --max-cells)
            if [ "$#" -lt 2 ]; then
                printf '%s\n\n' "Missing value for --max-cells" >&2
                usage >&2
                exit 2
            fi
            MAX_CELLS=$2
            shift 2
            ;;
        --max-parallel)
            if [ "$#" -lt 2 ]; then
                printf '%s\n\n' "Missing value for --max-parallel" >&2
                usage >&2
                exit 2
            fi
            MAX_PARALLEL=$2
            shift 2
            ;;
        --resume)
            if [ "$#" -lt 2 ]; then
                printf '%s\n\n' "Missing value for --resume" >&2
                usage >&2
                exit 2
            fi
            RESUME=$2
            shift 2
            ;;
        *)
            printf '%s\n\n' "Unknown option: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

case "$MAX_PARALLEL" in 1|2|3|4|5|6) ;; *)
    printf '%s\n' "--max-parallel must be between 1 and 6" >&2
    exit 2
esac
if [ -n "$MAX_CELLS" ]; then
    case "$MAX_CELLS" in 1|2|3|4|5|6) ;; *)
        printf '%s\n' "--max-cells must be between 1 and 6" >&2
        exit 2
    esac
fi

if [ -z "${TMUX-}" ]; then
    if ! command -v tmux >/dev/null 2>&1; then
        printf '%s\n' "run-live requires tmux, but tmux was not found in PATH" >&2
        exit 1
    fi
    set -- --max-parallel "$MAX_PARALLEL"
    if [ -n "$MAX_CELLS" ]; then
        set -- "$@" --max-cells "$MAX_CELLS"
    fi
    if [ -n "$RESUME" ]; then
        set -- "$@" --resume "$RESUME"
    fi
    exec tmux new-session "$0" "$@"
fi

CELL_ARGS=
if [ -n "$MAX_CELLS" ]; then
    CELL_ARGS="--max-cells $MAX_CELLS"
fi

configure_tmux_pane_titles() {
    case "$MAX_PARALLEL" in
        2|3|4|5|6) ;;
        *) return 0 ;;
    esac
    case "$MAX_CELLS" in
        2|3|4|5|6) ;;
        *) return 0 ;;
    esac
    if [ -z "${TMUX-}" ] || [ -z "${TMUX_PANE-}" ]; then
        return 0
    fi
    if ! command -v tmux >/dev/null 2>&1; then
        return 0
    fi
    tmux set-option -w -t "$TMUX_PANE" pane-border-status top \
        >/dev/null 2>&1 || return 0
    tmux set-option -w -t "$TMUX_PANE" pane-border-format ' #{pane_title} ' \
        >/dev/null 2>&1 || return 0
}

configure_tmux_pane_titles

if [ -n "$RESUME" ]; then
    exec uv run --project "$PROJECT_ROOT" driftbench interview-eval resume \
        --run-dir "$RESUME" --max-parallel "$MAX_PARALLEL" $CELL_ARGS
fi

exec uv run --project "$PROJECT_ROOT" driftbench interview-eval run \
    --policy "$POLICY" --max-parallel "$MAX_PARALLEL" $CELL_ARGS
