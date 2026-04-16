from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
import sys
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from scripts.package_t_common import REPORTS_ROOT


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _render_section(title: str, payload: dict[str, Any]) -> list[str]:
    lines = [f"## {title}", "", "```json", json.dumps(payload, ensure_ascii=False, indent=2), "```", ""]
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description="Render aggregated Package T report.")
    parser.add_argument("--load-report", required=True)
    parser.add_argument("--fault-report", required=True)
    parser.add_argument("--output", default=str(REPORTS_ROOT / "PACKAGE_T_REPORT.md"))
    args = parser.parse_args()

    load_payload = _load_json(Path(args.load_report))
    fault_payload = _load_json(Path(args.fault_report))

    lines = [
        "# Package T Report",
        "",
        f"- generated_at: {datetime.now(UTC).isoformat()}",
        f"- load_report: {args.load_report}",
        f"- fault_report: {args.fault_report}",
        "",
    ]
    for index, benchmark in enumerate(load_payload.get("benchmarks", []), start=1):
        lines.extend(_render_section(f"Load Benchmark {index}", benchmark))
    for index, drill in enumerate(fault_payload.get("drills", []), start=1):
        lines.extend(_render_section(f"Fault Drill {index}", drill))

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
