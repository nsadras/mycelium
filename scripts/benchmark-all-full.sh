#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

"${SCRIPT_DIR}/benchmark-locomo-full.sh"
"${SCRIPT_DIR}/benchmark-memoryagentbench-full.sh"
