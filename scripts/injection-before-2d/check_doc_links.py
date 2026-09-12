"""核对本目录两份文档：相对链接全部存在、figures/ 产物数量与尺寸达标、两份自动表与数据未漂移。

* ``NEW_VALUE_DISTRIBUTION_BEFORE.md``：98 张跑前 2D 图（``figures/manifest.json``）+ 事件表（``event_tables.check``）；
* ``SAMPLING_WINDOWS.md``：15 张采样窗口数轴（``figures/windows_manifest.json``）+ 逐条窗口表（``window_timeline.check``）。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import event_tables
import window_timeline

HERE = Path(__file__).resolve().parent
DOCS = [HERE / "NEW_VALUE_DISTRIBUTION_BEFORE.md", HERE / "SAMPLING_WINDOWS.md"]
RUN_ID = event_tables.DEFAULT_RUN_ID
EXPECTED_FILES = len(window_timeline.GROUPS) * 7        # 14 组 × （1_positions + 2_events + 3_episodes_p1～p5）
EXPECTED_WINDOW_FILES = len(window_timeline.GROUPS) + 1  # 14 组 × 4_windows + 总览
MIN_LONG_EDGE = 2000


def _manifest_stats(path: Path, file_key: str) -> tuple[int, int | None]:
    """返回 (产物张数, 最小长边像素)；清单不存在时 (0, None)。"""
    if not path.is_file():
        return 0, None
    manifest = json.loads(path.read_text(encoding="utf-8"))
    files = sum(len(g["files"]) for g in manifest["groups"]) if file_key == "groups" else len(manifest["files"])
    sizes = manifest.get("sizes", {})
    return files, min((max(s) for s in sizes.values()), default=None)


def main() -> int:
    links: list[str] = []
    missing: list[str] = []
    for doc in DOCS:
        found = re.findall(r"\]\(([^)]+)\)", doc.read_text(encoding="utf-8"))
        links += found
        missing += [f"{doc.name} → {link}" for link in found if not link.startswith("http") and not (HERE / link).resolve().exists()]
    files, min_edge = _manifest_stats(HERE / "figures" / "manifest.json", "groups")
    window_files, window_min_edge = _manifest_stats(HERE / "figures" / "windows_manifest.json", "files")
    tables_ok, rows, drift = event_tables.check(RUN_ID)
    window_ok, window_rows, window_drift = window_timeline.check()
    ok = (not missing and files == EXPECTED_FILES and (min_edge or 0) >= MIN_LONG_EDGE and tables_ok
          and window_files == EXPECTED_WINDOW_FILES and (window_min_edge or 0) >= MIN_LONG_EDGE and window_ok)
    for link in missing:
        print(f"  缺失：{link}")
    print(f"DOC_LINKS={'PASS' if ok else 'FAIL'} links={len(links)} missing={len(missing)} files={files}/{EXPECTED_FILES} "
          f"windows_files={window_files}/{EXPECTED_WINDOW_FILES} min_long_edge_px={min_edge} windows_min_long_edge_px={window_min_edge} "
          f"tables={'PASS' if tables_ok else 'FAIL'} rows={rows} drift={drift} "
          f"window_tables={'PASS' if window_ok else 'FAIL'} window_rows={window_rows} window_drift={window_drift}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
