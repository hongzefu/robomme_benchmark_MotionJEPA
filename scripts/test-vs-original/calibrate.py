#!/usr/bin/env python
"""用实测结果标定容差表（`scripts/test-vs-original/tolerance.json`）。

输入是一份或多份 ``compare_vs_original.py`` 产出的 ``episodes.jsonl``（**全部是"产物 vs 原版发布集"**，
不接受产物互比的结果），按档位汇总：

* DRIFT／REPLAN 局的手臂通道 ``p99``、``max`` 分位数；
* REPLAN 率；帧数差、子目标边界帧号偏移、边界坐标像素差、夹爪翻转帧号偏移；
* ts0 图像像素差比例与深度差。

余量规则（可用参数覆盖）：手臂阈值 = 观测 DRIFT 局该统计量的最大值 × ``--margin``（默认 2）再向上取 1 位有效数字；
``replan_max`` = 观测 REPLAN 率 × ``--margin`` + 1/compared；帧号/像素类上限 = 观测 max × ``--margin``（观测为 0 保持 0）。
``ada`` 档的 ``ts0_image`` 与帧号/像素类上限固定为 0（同架构应精确复现布局）。

判定行::

    CALIBRATION_DONE tier=a40 samples=3 episodes=336 replan_rate=0.19 arm_p99_obs=… -> tolerance.json 已更新
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
DEFAULT_TOLERANCE = HERE / "tolerance.json"
ARM_FIELDS = ("joint_action", "eef_action", "joint_state", "eef_state")


def _ceil_sig(value: float, digits: int = 1) -> float:
    """向上取到 ``digits`` 位有效数字（0 保持 0）。"""
    if value <= 0:
        return 0.0
    exp = math.floor(math.log10(value))
    factor = 10 ** (exp - digits + 1)
    return math.ceil(value / factor) * factor


def _load(paths: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for p in paths:
        path = Path(p)
        if path.is_dir():
            path = path / "episodes.jsonl"
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                rec["_source"] = str(path)
                rows.append(rec)
    if not rows:
        raise SystemExit("没有读到任何逐局记录")
    return rows


def observe(rows: list[dict[str, Any]]) -> dict[str, Any]:
    obs: dict[str, Any] = {"episodes": len(rows), "counts": {}, "arm": {}}
    for cat in ("IDENTICAL", "DRIFT", "REPLAN", "FAIL"):
        obs["counts"][cat] = sum(1 for r in rows if r.get("category") == cat)
    n = len(rows)
    obs["replan_rate"] = obs["counts"]["REPLAN"] / n if n else 0.0
    drift = [r for r in rows if r.get("category") == "DRIFT"]
    for k in ARM_FIELDS:
        p99s = [r["arm"][k]["p99"] for r in drift if "arm" in r]
        maxs = [r["arm"][k]["max"] for r in drift if "arm" in r]
        obs["arm"][k] = {"p99_max": max(p99s) if p99s else 0.0, "max_max": max(maxs) if maxs else 0.0, "n": len(p99s)}
    withsub = [r for r in rows if "subgoal" in r]
    obs["frame_delta_max_drift"] = max((abs(r["frames"]["generated"] - r["frames"]["reference"]) for r in drift), default=0)
    obs["boundary_shift_max_drift"] = max((r["subgoal"]["boundary_shift_max"] for r in drift), default=0)
    obs["px_max_drift"] = max((r["subgoal"]["px_max"] for r in drift), default=0)
    obs["flip_shift_max_drift"] = max((r["gripper"]["flip_shift_max"] for r in drift), default=0)
    imgs = [r["ts0_image"] for r in rows if "ts0_image" in r and "px_diff_ratio" in r["ts0_image"].get("front_depth", {})]
    obs["ts0_px_diff_ratio_max"] = max((max(i["front_depth"]["px_diff_ratio"], i["front_rgb"]["px_diff_ratio"]) for i in imgs), default=0.0)
    obs["ts0_depth_max"] = max((i["front_depth"]["max"] for i in imgs), default=0)
    obs["text_raw_mismatch_episodes"] = sum(1 for r in rows if r.get("text_raw_mismatch"))
    obs["replan_reasons"] = {}
    for r in rows:
        if r.get("category") == "REPLAN":
            for reason in r.get("reasons", []):
                for item in reason.split(":", 1)[-1].split(","):
                    key = item.split("=")[0].split(":")[0]
                    obs["replan_reasons"][key] = obs["replan_reasons"].get(key, 0) + 1
    obs["fail_reasons"] = {}
    for r in rows:
        if r.get("category") == "FAIL":
            for reason in r.get("reasons", []):
                obs["fail_reasons"][reason] = obs["fail_reasons"].get(reason, 0) + 1
    return obs


def propose(tier: str, obs: dict[str, Any], margin: float, tier_cfg: dict[str, Any]) -> dict[str, Any]:
    new = json.loads(json.dumps(tier_cfg))
    n = obs["episodes"]
    for k in ARM_FIELDS:
        p99 = _ceil_sig(obs["arm"][k]["p99_max"] * margin)
        mx = _ceil_sig(obs["arm"][k]["max_max"] * margin)
        floor = 1e-6 if tier == "ada" else 0.0  # 同架构也有 1e-17 级舍入噪声，给个下限
        new["arm"][k] = {"p99": max(p99, floor), "max": max(mx, floor)}
    new["replan_max"] = round(obs["replan_rate"] * margin + (1.0 / n if n else 0.0), 4)
    if tier == "ada":
        new.update({"frame_delta_max": 0, "px_tol": 0, "boundary_shift_max": 0, "flip_shift_max": 0})
        new["ts0_image"] = {"px_diff_ratio": 0.0, "depth_max": 0}
    else:
        new["frame_delta_max"] = int(math.ceil(obs["frame_delta_max_drift"] * margin)) or tier_cfg.get("frame_delta_max", 0)
        new["px_tol"] = int(math.ceil(obs["px_max_drift"] * margin)) or tier_cfg.get("px_tol", 0)
        new["boundary_shift_max"] = int(math.ceil(obs["boundary_shift_max_drift"] * margin)) or tier_cfg.get("boundary_shift_max", 0)
        new["flip_shift_max"] = int(math.ceil(obs["flip_shift_max_drift"] * margin)) or tier_cfg.get("flip_shift_max", 0)
        new["ts0_image"] = {
            "px_diff_ratio": round(obs["ts0_px_diff_ratio_max"] * margin, 4),
            "depth_max": int(math.ceil(obs["ts0_depth_max"] * margin)),
        }
    return new


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--tier", required=True, help="要标定的档位（ada｜a40）")
    p.add_argument("--results", nargs="+", required=True, help="episodes.jsonl 文件或其所在目录，可多份")
    p.add_argument("--tolerance", default=str(DEFAULT_TOLERANCE))
    p.add_argument("--margin", type=float, default=2.0, help="余量倍数（默认 2）")
    p.add_argument("--write", action="store_true", help="写回 tolerance.json（默认只打印建议值）")
    p.add_argument("--note", default="", help="写进 calibrated_from 的说明（机器/规模/worker 数）")
    args = p.parse_args(argv)

    tolerance = json.loads(Path(args.tolerance).read_text(encoding="utf-8"))
    if args.tier not in tolerance["tiers"]:
        raise SystemExit(f"未知档位 {args.tier}")
    rows = _load(args.results)
    obs = observe(rows)
    new_cfg = propose(args.tier, obs, args.margin, tolerance["tiers"][args.tier])
    print(json.dumps({"tier": args.tier, "observed": obs, "proposed": new_cfg}, ensure_ascii=False, indent=2))
    arm_obs = " ".join(f"{k}={obs['arm'][k]['p99_max']:.3g}" for k in ARM_FIELDS)
    print(
        f"CALIBRATION_DONE tier={args.tier} samples={len(args.results)} episodes={obs['episodes']} "
        f"replan_rate={obs['replan_rate']:.4f} arm_p99_obs=[{arm_obs}] write={int(args.write)}"
    )
    if args.write:
        tolerance["tiers"][args.tier] = new_cfg
        tolerance.setdefault("calibrated_from", []).append({
            "tier": args.tier, "date": datetime.now(timezone.utc).isoformat(), "note": args.note,
            "results": [str(Path(r).resolve()) for r in args.results], "margin": args.margin, "observed": obs,
        })
        Path(args.tolerance).write_text(json.dumps(tolerance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"# 已写回 {args.tolerance}")
    print("EXIT_CODE=0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
