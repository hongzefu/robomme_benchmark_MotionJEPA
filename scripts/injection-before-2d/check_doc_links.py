"""核对 NEW_VALUE_DISTRIBUTION_BEFORE.md 里的相对链接全部存在，并核对 plots-2d 产物数量与尺寸。"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DOC = HERE / "NEW_VALUE_DISTRIBUTION_BEFORE.md"
EXPECTED_FILES = 11 * 6 + 1


def main() -> int:
    text = DOC.read_text(encoding="utf-8")
    links = re.findall(r"\]\(([^)]+)\)", text)
    missing = [link for link in links if not link.startswith("http") and not (HERE / link).resolve().exists()]
    manifest_path = HERE.parents[1] / "artifacts" / "injection" / "20260910-new-values-04" / "plots-2d" / "before" / "manifest.json"
    files = sizes = 0
    min_edge = None
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        files = sum(len(g["files"]) for g in manifest["groups"]) + 1
        sizes = manifest.get("sizes", {})
        min_edge = min((max(s) for s in sizes.values()), default=None)
    ok = not missing and files == EXPECTED_FILES and (min_edge or 0) >= 3000
    for link in missing:
        print(f"  缺失：{link}")
    print(f"DOC_LINKS={'PASS' if ok else 'FAIL'} links={len(links)} missing={len(missing)} files={files}/{EXPECTED_FILES} min_long_edge_px={min_edge}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
