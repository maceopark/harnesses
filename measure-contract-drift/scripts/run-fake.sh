#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
PROJECT="$ROOT/benchmark/ultimateinterview-contract-drift"
IMAGE_TAG="driftbench-worker:local"
docker build --quiet --file "$PROJECT/Dockerfile.worker" --tag "$IMAGE_TAG" "$PROJECT" >/dev/null
IMAGE_ID="$(docker image inspect "$IMAGE_TAG" --format '{{.Id}}')"
exec uv run --project "$PROJECT" driftbench run --config "$PROJECT/configs/fake-dev.toml" --worker-image "$IMAGE_ID" --resume
