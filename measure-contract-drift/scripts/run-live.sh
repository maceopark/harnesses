#!/bin/sh
set -eu

PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
POLICY="$PROJECT_ROOT/configs/interview-eval.json"
MAX_CELLS=
MAX_PARALLEL=1
RESUME=

while [ "$#" -gt 0 ]; do
    case "$1" in
        --max-cells)
            MAX_CELLS=$2
            shift 2
            ;;
        --max-parallel)
            MAX_PARALLEL=$2
            shift 2
            ;;
        --resume)
            RESUME=$2
            shift 2
            ;;
        *)
            printf '%s\n' "Unknown option: $1" >&2
            exit 2
            ;;
    esac
done

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
        2|3|4|5|6|7|8|9|10|11|12) ;;
        *) return 0 ;;
    esac
    case "$MAX_CELLS" in
        2|3|4|5|6|7|8|9|10|11|12) ;;
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
