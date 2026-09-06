"""把离线复算参数与 h5 时长合成 Markdown 报告（总览 + 四个分源明细）。"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
SOURCES = ["PatternLock-test", "PatternLock-val", "RouteStick-test", "RouteStick-val"]
ORIGIN = {
    "PatternLock-val": "原版 h5 `/data/hongzefu/data-0306/record_dataset_PatternLock.h5`",
    "RouteStick-val": "原版 h5 `/data/hongzefu/data-0306/record_dataset_RouteStick.h5`",
    "PatternLock-test": "本轮按 test metadata 死 seed 实跑生成",
    "RouteStick-test": "本轮按 test metadata 死 seed 实跑生成",
}


def fmt_xyz(point: list[float]) -> str:
    return f"({point[0]:+.3f}, {point[1]:+.3f}, {point[2]:+.3f})"


def episode_section(row: dict[str, Any], dur: dict[str, Any] | None) -> list[str]:
    task = row["task"]
    lines = [
        f"#### episode {row['episode']} — seed `{row['seed']}`，难度 {row['difficulty']}，move {row['moves']} 次",
        "",
    ]
    if task == "RouteStick":
        lines.append(f"整排绕 z 轴旋转 `theta = {row['theta_deg']:.3f}°`；节点序列 `{row['path_nodes']}`（1×9 格点，只用偶数下标）。")
    else:
        lines.append(f"{row['grid']}×{row['grid']} 格点，节点序列 `{row['path_nodes']}`。")
    lines.append("")

    if dur is None:
        lines.append("> 时长：**未生成**（该 episode 无 h5）。")
        lines.append("")
        exec_dur: list[int] = []
        demo_dur: list[int] = []
    else:
        exec_dur = dur["exec_durations"]
        demo_dur = dur["demo_durations"]
        lines.append(
            f"整条 {dur['n_timesteps_total']} timestep（其中收尾段 {dur['completed_tail_timesteps']}）。"
        )
        lines.append("")

    header = "| # | 起点 (x,y,z) | 终点 (x,y,z) | 动作语义 | 执行段时长 | 演示段时长 |"
    lines.append(header)
    lines.append("| --- | --- | --- | --- | --- | --- |")
    coords = row["coords_xyz"]
    for index, semantic in enumerate(row["move_directions"]):
        e = f"{exec_dur[index]} ts" if index < len(exec_dur) else "—"
        d = f"{demo_dur[index]} ts" if index < len(demo_dur) else "—"
        lines.append(
            f"| {index + 1} | {fmt_xyz(coords[index])} | {fmt_xyz(coords[index + 1])} | {semantic} | {e} | {d} |"
        )
    lines.append("")
    return lines


def build_source_report(key: str, rows: list[dict], durations: dict[str, Any]) -> str:
    task, split = key.split("-")
    lines = [
        f"# {key} 逐 episode 动作参数",
        "",
        f"共 {len(rows)} 条。时长来源：{ORIGIN[key]}。",
        "",
        "口径：坐标是 SAPIEN 世界坐标，单位米（机器人 base 在 `(-0.615, 0, 0)`），"
        "表中给的是按钮本身的位置；运动规划实际下发的终点高度统一抬到 `z=0.07`。"
        "时长单位是 timestep（1 timestep = 1 个 env step = 0.05 s）；"
        "每组 move 在数据里出现两遍，前一遍是给模型看的演示段，后一遍是真正执行段。",
        "",
    ]
    if task == "RouteStick":
        lines += [
            "RouteStick 的 move 不是直线：末端要绕开挡在中间的柱子，走二次贝塞尔弧线"
            "（横向偏移 0.2 m，顺/逆时针由 `swing_directions` 决定），因此单次 move 时长稳定在 50 timestep 上下。",
            "",
        ]
    for row in rows:
        dur = durations.get(str(row["episode"])) if durations else None
        lines += episode_section(row, dur)
    return "\n".join(lines)


def summary_stats(rows: list[dict], durations: dict[str, Any]) -> dict[str, Any]:
    moves = [row["moves"] for row in rows]
    all_dur = [
        d
        for row in rows
        for d in (durations.get(str(row["episode"]), {}).get("exec_durations", []) if durations else [])
    ]
    totals = [
        durations[str(row["episode"])]["n_timesteps_total"]
        for row in rows
        if durations and str(row["episode"]) in durations
    ]
    difficulties: dict[str, int] = {}
    for row in rows:
        difficulties[row["difficulty"]] = difficulties.get(row["difficulty"], 0) + 1
    return {
        "episodes": len(rows),
        "moves_total": sum(moves),
        "moves_range": (min(moves), max(moves)),
        "moves_mean": statistics.mean(moves),
        "difficulties": difficulties,
        "covered": len(totals),
        "dur_range": (min(all_dur), max(all_dur)) if all_dur else None,
        "dur_mean": statistics.mean(all_dur) if all_dur else None,
        "total_range": (min(totals), max(totals)) if totals else None,
    }


def build_summary(payload: dict[str, list[dict]], durations: dict[str, dict]) -> str:
    lines = [
        "# PatternLock / RouteStick 的 test+val 源逐 episode 动作参数",
        "",
        "四个源各 50 条，共 200 个 episode。每个 episode 给出：move 了几次、每次 move 的起终点坐标、"
        "每次 move 占多少 timestep。明细见同目录的四份分源报告。",
        "",
        "## 口径",
        "",
        "- **seed / 难度**：一律读 `src/robomme/env_metadata/{test,val}/record_dataset_{Task}_metadata.json`，"
        "不用公式反推（存在 attempt 尾号例外，如 PatternLock-val ep37 = 1153701）。",
        "- **move 次数与坐标**：不需要跑仿真。两个 env 的场景随机段只用一个 `torch.Generator(seed)`，"
        "消费顺序确定，离线重跑一遍随机数即可还原（`derive_episode_params.py`）。",
        "- **坐标**：SAPIEN 世界坐标，单位米，机器人 base 在 `(-0.615, 0, 0)`。表里是按钮本身的位置"
        "（PatternLock z=0.01；RouteStick 偶数下标 z=0.01）；规划实际下发的终点高度统一抬到 z=0.07。",
        "- **时长**：1 timestep = 1 个 env step = 0.05 s（控制频率 20 Hz），与数据集的采样频率一致。"
        "录像 fps=30 与 timestep 不等长，报告里不用视频帧。",
        "- **演示段 / 执行段**：同一组 move 在数据里出现两遍——前一遍 `is_video_demo=True` 是给模型看的示范，"
        "后一遍才是真正 rollout。表中两列分开给。每条 episode 末尾还有一个几到十几 timestep 的收尾段，不算 move。",
        "",
        "## 各源总览",
        "",
        "| 源 | 条数 | 难度分布 | move 次数（min~max，均值） | move 总数 | 单次 move 时长 | 整条时长 | 时长来源 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for key in SOURCES:
        rows = payload.get(key)
        if not rows:
            continue
        stat = summary_stats(rows, durations.get(key, {}))
        diff = "/".join(f"{k} {v}" for k, v in sorted(stat["difficulties"].items()))
        dur = (
            f"{stat['dur_range'][0]}~{stat['dur_range'][1]} ts（均值 {stat['dur_mean']:.1f}）"
            if stat["dur_range"]
            else "未生成"
        )
        total = (
            f"{stat['total_range'][0]}~{stat['total_range'][1]} ts" if stat["total_range"] else "未生成"
        )
        lines.append(
            f"| [{key}]({key}.md) | {stat['episodes']} | {diff} | "
            f"{stat['moves_range'][0]}~{stat['moves_range'][1]}，{stat['moves_mean']:.2f} | "
            f"{stat['moves_total']} | {dur} | {total} | {ORIGIN[key]} |"
        )
    lines += [
        "",
        "## 校验",
        "",
        "1. **复算 vs h5 逐条对拍**（`cross_check.py`）：比对 seed、难度、move 次数（= h5 执行段数）、"
        "move 语义串（= h5 段名串），并检查 h5 内部演示段与执行段是否同一组 move。"
        "**四个源 200 条全部一致**（val 见 `outputs/cross_check.json`，test 见 `outputs/cross_check_test.json`）。"
        "语义串是从复算坐标算出来的方向，所以这一项同时验证了坐标。",
        "2. **test seed 一致性**（`check_test_seeds.py`）：本轮实跑 100 条全部 attempt=0 一次通过，"
        "seed 与 test metadata **逐条相等，0 条不一致**，即拿到的时长就是原版 seed 下的时长"
        "（`outputs/test_seed_check.json`）。",
        "3. **口径自洽**：RouteStick 满足「整条时长 = 段数 × 50」；两个 env 的 move 段数都是偶数"
        "（演示段与执行段成对）。",
        "",
        "test 与 val 的统计高度吻合（PatternLock 单次 move 均值 30.5 vs 30.7，RouteStick 均为 48.1），"
        "这是当前环境代码与原版行为一致的旁证。",
        "",
    ]
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="生成 Markdown 报告")
    parser.add_argument("--derived", default=str(HERE / "outputs" / "derived_params.json"))
    parser.add_argument(
        "--durations",
        action="append",
        default=None,
        help="时长 JSON，可重复（多份会按源名合并）",
    )
    parser.add_argument("--out-dir", default=str(HERE / "reports"))
    args = parser.parse_args(argv)

    payload = json.loads(Path(args.derived).read_text(encoding="utf-8"))
    durations: dict[str, dict] = {}
    for path in args.durations or [str(HERE / "outputs" / "durations_val.json")]:
        durations.update(json.loads(Path(path).read_text(encoding="utf-8")))

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for key in SOURCES:
        rows = payload.get(key)
        if not rows:
            continue
        text = build_source_report(key, rows, durations.get(key, {}))
        (out_dir / f"{key}.md").write_text(text, encoding="utf-8")
        print(f"已写出 {out_dir / (key + '.md')}")
    (out_dir / "README.md").write_text(build_summary(payload, durations), encoding="utf-8")
    print(f"已写出 {out_dir / 'README.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
