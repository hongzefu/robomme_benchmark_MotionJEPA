"""核对 NEW_VALUE_DISTRIBUTION_BEFORE.md：相对链接全部存在、figures/ 产物数量与尺寸达标、事件表与规格未漂移。"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import event_tables

HERE = Path(__file__).resolve().parent
DOC = HERE / "NEW_VALUE_DISTRIBUTION_BEFORE.md"
RUN_ID = event_tables.DEFAULT_RUN_ID
EXPECTED_FILES = 11 * 7  # 11 组 × （1_positions + 2_events + 3_episodes_p1～p5）
MIN_LONG_EDGE = 2000


def main() -> int:
    text = DOC.read_text(encoding="utf-8")
    links = re.findall(r"\]\(([^)]+)\)", text)
    missing = [link for link in links if not link.startswith("http") and not (HERE / link).resolve().exists()]
    manifest_path = HERE / "figures" / "manifest.json"
    files = sizes = 0
    min_edge = None
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        files = sum(len(g["files"]) for g in manifest["groups"])
        sizes = manifest.get("sizes", {})
        min_edge = min((max(s) for s in sizes.values()), default=None)
    tables_ok, rows, drift = event_tables.check(RUN_ID)
    ok = not missing and files == EXPECTED_FILES and (min_edge or 0) >= MIN_LONG_EDGE and tables_ok
    for link in missing:
        print(f"  缺失：{link}")
    print(f"DOC_LINKS={'PASS' if ok else 'FAIL'} links={len(links)} missing={len(missing)} files={files}/{EXPECTED_FILES} "
          f"min_long_edge_px={min_edge} tables={'PASS' if tables_ok else 'FAIL'} rows={rows} drift={drift}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
