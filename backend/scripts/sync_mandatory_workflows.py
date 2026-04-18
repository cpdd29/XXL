from __future__ import annotations

import json
from pathlib import Path
import sys

CURRENT_DIR = Path(__file__).resolve().parent
BACKEND_ROOT = CURRENT_DIR.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.mandatory_workflow_registry_service import ensure_mandatory_workflows_registered
from app.services.persistence_service import persistence_service


def main() -> int:
    persistence_service.initialize()
    try:
        payload = ensure_mandatory_workflows_registered()
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    finally:
        persistence_service.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
