#!/usr/bin/env python3
"""V4 原三档的 reset 级回归探针（NEWTASK_RELEASE_V4_PLAN 步 3b「每组先过 V0+V1」的本机前置）。

V1（``NATIVE_REGRESSION``）的正式判据要在 A40 上重跑 144 条并与 V3 留档逐位比；那一步重、要排集群。
本探针是它的**本机快速前置**：对同一批原三档身份只做 ``make → reset → 抓取 → close``，把
「规格导出文档 + 取值点轨迹 + generator 终态 + 任务表 + 全部 actor 初始位姿」落成一份 JSON；
改代码前后各跑一次、逐字节比。任何随机流平移、取值变化、任务文本变化、物体位姿变化都会在这里暴露。

⚠ 它**不能替代 V1**：不跑演示、不录 h5，看不到 step 之后的差异；本机（sm_89）结果也不进判据（口径 10）。

    # 采一次（默认 v3 的 144 条子集；--tasks 可只采某几个环境）
    uv run --no-sync python -m scripts.parity.v4_reset_probe probe --out <a.json> [--tasks BinFill,PickXtimes]
    # 比两次
    uv run --no-sync python -m scripts.parity.v4_reset_probe diff <a.json> <b.json>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = REPO_ROOT / "scripts" / "configs" / "newtask-v3" / "subset_manifest.json"


def _floats(value):
    """张量／数组转成 float 列表；用 float.hex 保留全部位，保证逐位可比。"""
    if hasattr(value, "detach"):
        value = value.detach().cpu().numpy()
    if hasattr(value, "tolist"):
        value = value.tolist()
    if isinstance(value, (list, tuple)):
        return [_floats(item) for item in value]
    if isinstance(value, float):
        return float.hex(value)
    return value


def _capture(env) -> dict:
    base = env.unwrapped
    out: dict = {}
    recorder = getattr(base, "_spec", None)
    if recorder is not None:
        out["spec"] = recorder.to_dict()
        out["trace"] = [
            {"path": item["path"], "source": item["source"],
             "value": item.get("drawn", item.get("value"))}
            for item in recorder.trace
        ]
    states = {}
    for attribute in ("generator", "_hb_generator"):
        generator = getattr(base, attribute, None)
        if generator is not None and hasattr(generator, "get_state"):
            states[attribute] = hashlib.sha256(
                bytes(generator.get_state().numpy().tobytes())
            ).hexdigest()
    out["generator_states"] = states
    tasks = getattr(base, "task_list", None)
    if tasks is not None:
        out["task_list"] = [
            {key: item.get(key) for key in ("name", "subgoal_segment", "demonstration")
             if isinstance(item, dict)}
            for item in tasks
        ]
    actors = {}
    for name, actor in sorted(getattr(base.scene, "actors", {}).items()):
        try:
            pose = actor.pose
            actors[name] = {"p": _floats(pose.p), "q": _floats(pose.q)}
        except Exception as exc:  # noqa: BLE001 个别 actor 无位姿时如实记下
            actors[name] = {"error": type(exc).__name__}
    out["actors"] = actors
    return out


def cmd_probe(args: argparse.Namespace) -> int:
    sys.path.insert(0, str(REPO_ROOT / "src"))
    import gymnasium as gym
    import robomme.robomme_env  # noqa: F401 注册环境

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    wanted = set(args.tasks.split(",")) if args.tasks else None
    rows = [row for row in manifest["rows"] if wanted is None or row["task"] in wanted]
    if args.limit_per_task:
        kept, count = [], {}
        for row in rows:
            count[row["task"]] = count.get(row["task"], 0) + 1
            if count[row["task"]] <= args.limit_per_task:
                kept.append(row)
        rows = kept
    results = []
    started = time.time()
    for index, row in enumerate(rows):
        kwargs = {
            "obs_mode": "rgb+depth+segmentation",
            "control_mode": "pd_joint_pos",
            "render_mode": "rgb_array",
            "reward_mode": "dense",
            "seed": row["seed"],
            "difficulty": row["difficulty"],
        }
        if row.get("recovery_mode") is not None:
            kwargs["robomme_failure_recovery"] = True
            kwargs["robomme_failure_recovery_mode"] = row["recovery_mode"]
        entry = {key: row[key] for key in ("task", "episode", "seed", "difficulty", "recovery_mode")}
        env = None
        try:
            env = gym.make(row["task"], **kwargs)
            env.reset()
            entry["capture"] = _capture(env)
            entry["ok"] = True
        except Exception as exc:  # noqa: BLE001 失败本身也是要比的结果
            entry["ok"] = False
            entry["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            if env is not None:
                env.close()
        results.append(entry)
        print(f"[{index + 1}/{len(rows)}] {row['task']}/{row['episode']} "
              f"{row['difficulty']} ok={entry['ok']} {time.time() - started:.0f}s", flush=True)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(
        json.dumps({"schema": "v4-reset-probe/1", "manifest": str(args.manifest), "rows": results},
                   ensure_ascii=False, sort_keys=True, indent=1) + "\n",
        encoding="utf-8",
    )
    print(f"PROBE_DONE rows={len(results)} ok={sum(r['ok'] for r in results)} out={args.out}")
    return 0


def _first_diff(left, right, path=""):
    if type(left) is not type(right):
        return path or "<root>"
    if isinstance(left, dict):
        for key in sorted(set(left) | set(right)):
            if key not in left or key not in right:
                return f"{path}.{key}"
            found = _first_diff(left[key], right[key], f"{path}.{key}")
            if found:
                return found
        return None
    if isinstance(left, list):
        if len(left) != len(right):
            return f"{path}[len {len(left)}!={len(right)}]"
        for index, (a, b) in enumerate(zip(left, right)):
            found = _first_diff(a, b, f"{path}[{index}]")
            if found:
                return found
        return None
    return None if left == right else path


def cmd_diff(args: argparse.Namespace) -> int:
    left = json.loads(Path(args.left).read_text(encoding="utf-8"))["rows"]
    right = json.loads(Path(args.right).read_text(encoding="utf-8"))["rows"]
    key = lambda row: (row["task"], row["episode"])  # noqa: E731
    lmap, rmap = {key(r): r for r in left}, {key(r): r for r in right}
    common = sorted(set(lmap) & set(rmap))
    diffs = []
    for ident in common:
        found = _first_diff(lmap[ident], rmap[ident])
        if found:
            diffs.append((ident, found))
    missing = sorted(set(lmap) ^ set(rmap))
    status = "PASS" if not diffs and not missing else "FAIL"
    print(f"RESET_REGRESSION={status} compared={len(common)} diff={len(diffs)} missing={len(missing)}")
    for ident, found in diffs[: args.show]:
        print(f"# 不同：{ident[0]}/{ident[1]} 首个差异 {found}")
    for ident in missing[: args.show]:
        print(f"# 只在一侧：{ident}")
    return 0 if status == "PASS" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    probe = sub.add_parser("probe", help="对原三档身份只 reset 并抓取可比状态")
    probe.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    probe.add_argument("--tasks", default=None, help="逗号分隔的环境名，默认全部")
    probe.add_argument("--limit-per-task", type=int, default=0, help="每环境最多取几条，0 为不限")
    probe.add_argument("--out", required=True)
    probe.set_defaults(func=cmd_probe)
    diff = sub.add_parser("diff", help="逐字节比较两次探针结果")
    diff.add_argument("left")
    diff.add_argument("right")
    diff.add_argument("--show", type=int, default=20)
    diff.set_defaults(func=cmd_diff)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
