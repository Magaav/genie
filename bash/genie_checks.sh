#!/bin/bash

set -euo pipefail

GATEWAY_PORT="${GENIE_GATEWAY_PORT:-18790}"
STATE_PORT="${GENIE_STATE_PORT:-18792}"
BRAIN_PORT="${GENIE_BRAIN_PORT:-18793}"
INSTINCT_PORT="${GENIE_INSTINCT_PORT:-18794}"

python3 - <<'PY'
from pathlib import Path

FILES = [
    "/local/services/gateway/app.py",
    "/local/services/ethics/app.py",
    "/local/services/ethics/control_plane.py",
    "/local/services/ethics/workcell_support.py",
    "/local/services/state/app.py",
    "/local/services/state/common.py",
    "/local/services/state/gateway_domain.py",
    "/local/services/state/memory_domain.py",
    "/local/services/state/policy_domain.py",
    "/local/services/state/runtime_domain.py",
    "/local/services/state/telemetry_domain.py",
    "/local/services/brain/app.py",
    "/local/services/instinct/app.py",
    "/local/services/instinct/engine.py",
    "/local/bash/genie_state.py",
    "/local/bash/local_agent.py",
    "/local/bash/local_memory.py",
    "/local/bash/provider_router.py",
]

for path in FILES:
    source = Path(path).read_text(encoding="utf-8")
    compile(source, path, "exec")
PY

export PYTHONDONTWRITEBYTECODE=1
python3 -m unittest discover -s /local/tests -p 'test_*.py'

curl -fsS "http://127.0.0.1:${GATEWAY_PORT}/health" >/dev/null
curl -fsS "http://127.0.0.1:${STATE_PORT}/health" >/dev/null
curl -fsS "http://127.0.0.1:${BRAIN_PORT}/health" >/dev/null
curl -fsS "http://127.0.0.1:${INSTINCT_PORT}/health" >/dev/null

echo "Genie hardness checks passed."
