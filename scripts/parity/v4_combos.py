#!/usr/bin/env python3
"""V6 组合覆盖（口径 14 / N11 / H3 / J8；NEWTASK_RELEASE_V4_PLAN 步 3c）。

对冻结组合清单里的每个组合，把 xhard 声明范围收窄到该组合的取值（离散量逐值、连续量取端点，与其他参数交叉），
用与正式生成逐字相同的 ``generate_dataset_newseed._worker`` 跑 ``--samples`` 条演示，两级都报：
reset 级（``_worker`` 是否走过 reset）与演示级（整局成功）。**以演示级为准**：任一组合演示成功数为 0 即
``zero_success_combinations`` 计 1，须停下回报用户重定参数（不许实施方自行收窄）。

三个子命令：

* ``build``：按本文件 ``COMBO_AXES``（源码申报的 xhard 取值逐值展开）生成组合清单 JSON，冻结进 Git。
* ``run``：跑一个分片（``--shard k/N`` 按「组合×样本」扁平序号取模切分），逐样本写 ``samples-<k>.jsonl``；
  J8：多 worker 并行＝同时起 N 个 ``run`` 进程，各跑一个分片。
* ``summarize``：汇总全部分片，按组合给 reset 级/演示级计数与失败分类，打印 ``COMBO_COVERAGE`` 判定行。

组合清单每项 ``set`` 的键是 ``{decision, native}`` 配置里的点分路径（值整体替换，路径必须已存在）；
``add`` 用于配置里原本没有、由环境运行时 ``setdefault`` 补齐的键（如 RouteStick 的 ``native.parameters.configs``）。

    uv run --no-sync python -m scripts.parity.v4_combos build --out scripts/configs/newtask-v4/combos.json
    uv run --no-sync python -m scripts.parity.v4_combos run --combos ... --samples 5 --shard 0/14 --gpu 0 --out artifacts/newtask-v4/combos/<run>
    uv run --no-sync python -m scripts.parity.v4_combos summarize --out artifacts/newtask-v4/combos/<run> --combos ... --samples 5
"""

from __future__ import annotations

import argparse
import copy
import itertools
import json
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
for extra in (REPO_ROOT, REPO_ROOT / "scripts", REPO_ROOT / "src"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from scripts.parity.v4_specs import DEFAULT_SAMPLING, task_sampling  # noqa: E402

# 与抽签/正式实跑都不重叠的 seed 段：7_000_000 + env_code*100_000 + combo*100 + sample
COMBO_SEED_OFFSET = 7_000_000
SCHEMA = "v4-combos/1"


def _closed(lo, hi):
    return list(range(lo, hi + 1))


def _routestick_configs(length):
    """RouteStick 的 configs 不在快照里（运行时 setdefault 自类属性），组合时整块补上。"""
    from robomme.robomme_env.RouteStick import RouteStick

    configs = copy.deepcopy(RouteStick.configs)
    configs["xhard"] = {**configs["xhard"], "length": [length, length]}
    return configs


def build_combos() -> dict:
    """xhard 申报的每个离散量逐值展开并交叉；连续量（yaw、corner_bias、色域）不单独成组合（取值即端点/固定）。"""
    tasks: dict[str, list] = {}

    def add(task, name, set_=None, add_=None):
        entry = {"name": name, "set": set_ or {}}
        if add_:
            entry["add"] = add_
        tasks.setdefault(task, []).append(entry)

    for n in _closed(6, 15):
        add("PickXtimes", f"num={n}", {"decision.number_range.xhard": [n, n]})
    for n in _closed(6, 15):
        add("StopCube", f"stop_time={n}", {"decision.xhard.stop_time_range": {"low": n, "high_exclusive": n + 1}})
    for n in _closed(4, 10):
        add("SwingXtimes", f"num={n}", {"decision.number_range.xhard": [n, n]})
    for put_in, colors in itertools.product(_closed(5, 7), (2, 3)):
        add("BinFill", f"put_in={put_in},put_in_color={colors}",
            {"decision.configs.xhard.put_in_numbers": [put_in, put_in],
             "native.parameters.put_in_color.xhard": [colors, colors]})
    for swap, cubes in itertools.product(_closed(8, 12), (1, 2)):
        add("VideoUnmaskSwap", f"swap={swap},distractor_cubes={cubes}",
            {"decision.swap_count_range.xhard": [swap, swap],
             "decision.xhard.distractor.with_cube_range": [cubes, cubes]})
    for swap, cubes in itertools.product(_closed(6, 8), (1, 2)):
        add("ButtonUnmaskSwap", f"swap={swap},distractor_cubes={cubes}",
            {"decision.swap_count_range.xhard": [swap, swap],
             "decision.xhard.distractor.with_cube_range": [cubes, cubes]})
    for task in ("VideoUnmask", "ButtonUnmask"):
        for cubes in (1, 2):
            add(task, f"distractor_cubes={cubes}", {"decision.xhard.distractor.cube_count_range": [cubes, cubes]})
    for swap, repeats in itertools.product(_closed(8, 12), _closed(4, 6)):
        add("VideoRepick", f"swap={swap},repeats={repeats}",
            {"decision.swap.xhard": {"swap_min": swap, "swap_max": swap},
             "decision.num_repeats_range.xhard": {"low": repeats, "high_exclusive": repeats + 1}})
    for highlight, spawn in itertools.product(_closed(5, 7), _closed(8, 10)):
        add("PickHighlight", f"highlight={highlight},spawn={spawn}",
            {"decision.highlight_count.xhard": [highlight, highlight],
             "decision.spawn_count.xhard": [spawn, spawn]})
    for length in _closed(20, 24):  # 用户 2026-09-23 把上界从 25 改为 24
        add("PatternLock", f"length={length}", {"decision.path_length_range.xhard": [length, length]})
    for length in _closed(12, 15):
        add("RouteStick", f"L={length}", add_={"native.parameters.configs": _routestick_configs(length)})
    for task in ("VideoPlaceButton", "VideoPlaceOrder", "InsertPeg", "MoveCube"):
        add(task, "default")  # 无离散可调量：xhard 默认即唯一组合
    return {"schema": SCHEMA, "rule": "离散量逐值、连续量取端点、与其他参数交叉（口径 14）", "tasks": tasks}


def apply_combo(config: dict, combo: dict) -> dict:
    out = copy.deepcopy(config)
    for mode in ("set", "add"):
        for dotted, value in combo.get(mode, {}).items():
            node = out
            parts = dotted.split(".")
            for part in parts[:-1]:
                if part not in node:
                    raise KeyError(f"组合路径不存在：{dotted}")
                node = node[part]
            if mode == "set" and parts[-1] not in node:
                raise KeyError(f"组合路径不存在：{dotted}（新键请用 add）")
            if mode == "add" and parts[-1] in node:
                raise KeyError(f"add 的键已存在：{dotted}（改值请用 set）")
            node[parts[-1]] = copy.deepcopy(value)
    return out


def _items(combos: dict, samples: int):
    """扁平化的（task, combo_index, combo, sample）序列，顺序确定。"""
    for task in sorted(combos["tasks"]):
        for index, combo in enumerate(combos["tasks"][task]):
            for sample in range(samples):
                yield task, index, combo, sample


def cmd_build(args) -> int:
    document = build_combos()
    out = Path(args.out)
    if out.exists():
        raise SystemExit(f"{out} 已存在，禁止覆盖")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(document, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    total = sum(len(v) for v in document["tasks"].values())
    print(f"COMBOS_BUILT tasks={len(document['tasks'])} combos={total} out={out}")
    return 0


def cmd_run(args) -> int:
    import generate_dataset_newseed as gen
    from seed_layout import env_code

    combos = json.loads(Path(args.combos).read_text(encoding="utf-8"))
    if combos.get("schema") != SCHEMA:
        raise SystemExit("组合清单版本不符")
    sampling = json.loads(Path(args.sampling_config).read_text(encoding="utf-8"))
    shard, shards = (int(x) for x in args.shard.split("/"))
    gen._pool_init(args.gpu, None, str(REPO_ROOT / "src"))
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    rows_path = out / f"samples-{shard:02d}.jsonl"
    done = set()
    if rows_path.exists():  # 断点续跑：已写的样本跳过
        done = {(r["task"], r["combo"], r["sample"]) for r in
                (json.loads(line) for line in rows_path.read_text().splitlines() if line.strip())}
    for flat, (task, index, combo, sample) in enumerate(_items(combos, args.samples)):
        if flat % shards != shard or (task, combo["name"], sample) in done:
            continue
        config = apply_combo(task_sampling(sampling, task), combo)
        seed = COMBO_SEED_OFFSET + env_code(task) * 100_000 + index * 100 + sample
        job = gen.EpisodeJob(task=task, episode=9, attempt=0, seed=seed, difficulty="xhard",
                             output_root=str(out / "episodes"), repo_root=str(REPO_ROOT), sampling_config=config)
        started = time.time()
        result = gen._worker(job)
        row = {
            "task": task, "combo": combo["name"], "sample": sample, "seed": seed,
            # reset 级：_worker 在 reset 返回后才写 phases["reset_s"]；成功局必然过了 reset
            "reset_ok": bool(result.get("ok")) or "reset_s" in (result.get("phases") or {}),
            "demo_ok": bool(result.get("ok")), "failure_class": result.get("failure_class"),
            "error_type": result.get("error_type"), "error": (result.get("error") or "")[:300] or None,
            "wall_s": round(time.time() - started, 1),
        }
        with rows_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        # 省盘：组合覆盖只要成败，不留 h5/视频
        for sub in ("hdf5_files", "videos"):
            for path in (out / "episodes" / sub).glob(f"{task}_ep9_seed{seed}*"):
                path.unlink(missing_ok=True)
        print(f"COMBO {task} [{combo['name']}] s{sample} seed={seed} reset={row['reset_ok']} "
              f"demo={row['demo_ok']} {row['error_type'] or ''} {row['wall_s']:.0f}s", flush=True)
    print(f"SHARD_DONE shard={shard}/{shards}")
    return 0


def cmd_summarize(args) -> int:
    combos = json.loads(Path(args.combos).read_text(encoding="utf-8"))
    out = Path(args.out)
    rows = [json.loads(line) for path in sorted(out.glob("samples-*.jsonl"))
            for line in path.read_text().splitlines() if line.strip()]
    table = []
    missing = zero = 0
    for task in sorted(combos["tasks"]):
        for combo in combos["tasks"][task]:
            mine = [r for r in rows if r["task"] == task and r["combo"] == combo["name"]]
            failures: dict[str, int] = {}
            for r in mine:
                if not r["demo_ok"]:
                    key = f"{r['failure_class']}:{r['error_type']}"
                    failures[key] = failures.get(key, 0) + 1
            entry = {"task": task, "combo": combo["name"], "samples": len(mine),
                     "reset_ok": sum(r["reset_ok"] for r in mine), "demo_ok": sum(r["demo_ok"] for r in mine),
                     "failures": failures}
            missing += len(mine) < args.samples
            zero += entry["demo_ok"] == 0
            table.append(entry)
    (out / "summary.json").write_text(json.dumps(table, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    status = "PASS" if missing == 0 and zero == 0 else "FAIL"
    print(f"COMBO_COVERAGE={status} combos={len(table)} missing_combinations={missing} zero_success_combinations={zero}")
    for entry in table:
        flag = " ← 演示 0 成功" if entry["demo_ok"] == 0 else ""
        print(f"# {entry['task']} [{entry['combo']}] reset {entry['reset_ok']}/{entry['samples']} "
              f"demo {entry['demo_ok']}/{entry['samples']} {entry['failures'] or ''}{flag}")
    return 0 if status == "PASS" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build")
    b.add_argument("--out", required=True)
    b.set_defaults(func=cmd_build)
    r = sub.add_parser("run")
    r.add_argument("--combos", required=True)
    r.add_argument("--sampling-config", default=str(DEFAULT_SAMPLING))
    r.add_argument("--samples", type=int, required=True)
    r.add_argument("--shard", default="0/1")
    r.add_argument("--gpu", default=os.environ.get("CUDA_VISIBLE_DEVICES", "0"))
    r.add_argument("--out", required=True)
    r.set_defaults(func=cmd_run)
    s = sub.add_parser("summarize")
    s.add_argument("--combos", required=True)
    s.add_argument("--samples", type=int, required=True)
    s.add_argument("--out", required=True)
    s.set_defaults(func=cmd_summarize)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
