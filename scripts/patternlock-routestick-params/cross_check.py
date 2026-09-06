"""对拍：离线复算结果 vs h5 真值。

免 GPU、免重新生成，用 val 的原版 h5 校验 derive_episode_params.py 的 RNG 顺序是否复现正确。
逐条比对三项：seed、move 次数（= h5 执行段数）、move 语义串（= h5 段名串）。
只要有一条不一致，就说明随机数消费顺序错位，必须先修复复算再往下走。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def check_source(key: str, derived_rows: list[dict], durations: dict[str, dict]) -> dict:
    mismatches = []
    checked = 0
    for row in derived_rows:
        episode = str(row["episode"])
        truth = durations.get(episode)
        if truth is None:
            continue
        checked += 1
        problems = []
        if int(truth["seed"]) != int(row["seed"]):
            problems.append(f"seed {row['seed']} != h5 {truth['seed']}")
        if truth["difficulty"] != row["difficulty"]:
            problems.append(f"difficulty {row['difficulty']} != h5 {truth['difficulty']}")
        if truth["exec_moves"] != row["moves"]:
            problems.append(f"move 次数 {row['moves']} != h5 执行段 {truth['exec_moves']}")
        if truth["exec_subgoals"] != row["move_directions"]:
            problems.append(
                f"语义串不符：复算 {row['move_directions']} != h5 {truth['exec_subgoals']}"
            )
        # 演示段与执行段应当是同一组 move
        if truth["demo_subgoals"] != truth["exec_subgoals"]:
            problems.append(
                f"h5 内部演示段与执行段不一致：{truth['demo_subgoals']} vs {truth['exec_subgoals']}"
            )
        if problems:
            mismatches.append({"episode": row["episode"], "problems": problems})
    return {"source": key, "checked": checked, "mismatches": mismatches}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="离线复算与 h5 真值对拍")
    parser.add_argument("--derived", default=str(HERE / "outputs" / "derived_params.json"))
    parser.add_argument("--durations", default=str(HERE / "outputs" / "durations_val.json"))
    parser.add_argument("--out", default=str(HERE / "outputs" / "cross_check.json"))
    args = parser.parse_args(argv)

    derived = json.loads(Path(args.derived).read_text(encoding="utf-8"))
    durations = json.loads(Path(args.durations).read_text(encoding="utf-8"))

    reports = []
    failed = False
    for key, truth in durations.items():
        if key not in derived:
            print(f"[跳过] {key} 没有对应的复算结果")
            continue
        report = check_source(key, derived[key], truth)
        reports.append(report)
        bad = len(report["mismatches"])
        status = "全部一致" if bad == 0 else f"{bad} 条不一致"
        print(f"{key}: 对拍 {report['checked']} 条，{status}")
        for item in report["mismatches"][:5]:
            print(f"  ep{item['episode']}: {item['problems']}")
        failed = failed or bad > 0

    Path(args.out).write_text(
        json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"已写出 {args.out}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
