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

CELL_ARGS=
if [ -n "$MAX_CELLS" ]; then
    CELL_ARGS="--max-cells $MAX_CELLS"
fi

if [ -n "$RESUME" ]; then
    exec uv run --project "$PROJECT_ROOT" driftbench interview-eval resume \
        --run-dir "$RESUME" --max-parallel "$MAX_PARALLEL" $CELL_ARGS
fi

exec uv run --project "$PROJECT_ROOT" driftbench interview-eval run \
    --policy "$POLICY" --max-parallel "$MAX_PARALLEL" $CELL_ARGS
