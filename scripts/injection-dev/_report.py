"""生成报告：读 jsonl 的 ``rollout`` 块与本轮 ``results.jsonl``，输出 ``HARD_GENERATION=REPORT``（计数字段显式输出零值，P4）。

由 ``scripts/parity/v5_generation.py`` 的报告部分下沉，去掉 drafts 依赖；演示帧带外口径同原报告
（只统计 PatternLock／RouteStick 的 ``info/is_video_demo`` 帧数，合格带 750～1050）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import _common  # noqa: F401  路径设置

from robomme_hard.env_record_wrapper import hard_specs  # noqa: E402

DEMO_BAND = (750, 1050)
DEMO_TASKS = ("PatternLock", "RouteStick")
COUNT_KEYS = ("cells", "rows", "selected", "delivered", "rollout_ok", "rollout_failed", "backfilled",
              "selected_shortfall", "demo_frames_checked", "demo_frames_out_of_band")


def count_demo_frames(h5_path: str | Path) -> int:
    import h5py

    with h5py.File(h5_path, "r") as handle:
        episode = handle[list(handle.keys())[0]]
        return sum(bool(episode[k]["info"]["is_video_demo"][()]) for k in episode if k.startswith("timestep_"))


def per_cell_quota(header: dict[str, Any], task: str) -> int:
    """逐格配额：/2、/3 的 ``delivery_per_cell`` 是全局整数；/4（v8）是 ``{task: n}`` 逐任务字典。"""
    quota = header["delivery_per_cell"]
    return int(quota[task]) if isinstance(quota, dict) else int(quota)


def build_report(specs: Path, check_demo: bool = True) -> dict[str, Any]:
    # /4 单文件的配额上限格表按 header 自带的逐任务配额推出：V9 文件（MoveCube／InsertPeg 50）在 3b 换包前
    # EXPECTED_CELLS 仍是 V8 时也能读（V9 计划 S1-B 遗留配合项）
    with Path(specs).open(encoding="utf-8") as stream:
        try:
            table = hard_specs.header_cell_table(json.loads(stream.readline()))
        except ValueError:
            table = None  # 首行坏了：交给 load_specs 报具体错
    header, rows = hard_specs.load_specs(specs, expected_cells=table, check_fingerprint=False)
    totals = {key: 0 for key in COUNT_KEYS}
    cells = sorted({r["task"] for r in rows})
    totals["cells"] = len(cells)
    totals["rows"] = len(rows)
    demo_out = []
    for task in cells:
        mine = [r for r in rows if r["task"] == task]
        delivered = [r for r in mine if hard_specs.delivered(r)]
        totals["selected"] += sum(r["selected"] for r in mine)
        totals["delivered"] += len(delivered)
        totals["rollout_ok"] += sum((r["rollout"] or {}).get("status") == "ok" for r in mine)
        totals["rollout_failed"] += sum((r["rollout"] or {}).get("status") == "failed" for r in mine)
        totals["backfilled"] += sum(r["selected"] and not r["initial_selected"] for r in delivered)
        totals["selected_shortfall"] += max(0, per_cell_quota(header, task) - len(delivered))
        if check_demo and task in DEMO_TASKS:
            for row in delivered:
                path = row["rollout"].get("h5_path")
                if path and Path(path).is_file():
                    frames = count_demo_frames(path)
                    totals["demo_frames_checked"] += 1
                    if not DEMO_BAND[0] <= frames <= DEMO_BAND[1]:
                        demo_out.append(f"{task}/{row['candidate']}:{frames}")
    totals["demo_frames_out_of_band"] = len(demo_out)
    line = "HARD_GENERATION=REPORT tier={} ".format(header["difficulty"]) + " ".join(f"{k}={totals[k]}" for k in COUNT_KEYS)
    return {"tier": header["difficulty"], "totals": totals, "demo_out_of_band": demo_out, "line": line}


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("specs", nargs="+")
    parser.add_argument("--no-demo", action="store_true")
    parser.add_argument("--out", default=None, help="报告 JSON 输出路径（可选）")
    args = parser.parse_args()
    reports = [build_report(Path(p), not args.no_demo) for p in args.specs]
    for report in reports:
        print(report["line"])
    if args.out:
        Path(args.out).write_text(json.dumps(reports, ensure_ascii=False, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
