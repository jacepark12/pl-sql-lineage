#!/usr/bin/env python3
"""Generate a deterministic large lineage JSON fixture for browser-scale checks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def build_sample(node_count: int) -> dict[str, list[dict[str, str]]]:
    if node_count < 2:
        raise ValueError("node_count must be at least 2")

    objects = [
        {
            "id": f"table.scale_{index:04d}",
            "type": "table",
            "name": f"SCALE_{index:04d}",
        }
        for index in range(node_count)
    ]
    relationships = [
        {
            "type": "direct",
            "source": f"table.scale_{index:04d}",
            "target": f"table.scale_{index + 1:04d}",
            "expression": f"scale_step_{index:04d}",
        }
        for index in range(node_count - 1)
    ]
    return {"objects": objects, "relationships": relationships, "diagnostics": []}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a large, deterministic lineage JSON fixture."
    )
    parser.add_argument("--nodes", type=int, default=1000)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("reports/demo/lineage-scale-1000.json"),
    )
    args = parser.parse_args()

    sample = build_sample(args.nodes)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(sample, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"wrote {args.out}: {len(sample['objects'])} objects, "
        f"{len(sample['relationships'])} relationships"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
