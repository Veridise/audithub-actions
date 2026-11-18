#!/usr/bin/env bash
set -euo pipefail

# ACTION_PATH points into the downloaded action repo, not the caller's checkout.
action_root="$(cd -- "${ACTION_PATH}/../../.." && pwd)"
action_environment="$(mktemp -d "${RUNNER_TEMP}/audithub-actions.XXXXXX")"
trap 'rm -rf -- "$action_environment"' EXIT
export UV_PROJECT_ENVIRONMENT="$action_environment/venv"

uv run --directory "$action_root" --project "$action_root" \
  --locked --no-dev --python 3.12 -m audithub_actions.scout "$1"
