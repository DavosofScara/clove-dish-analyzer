#!/bin/bash
# Same as run_mumma_pipeline.sh but always sends the client email (for launchd when ready).
export MUMMA_SCHEDULED_MODE=full
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/run_mumma_pipeline.sh"
