#!/usr/bin/env python3
"""由 V5 xhard 快照（scripts/configs/newtask-v5/sampling_config.json）按 V6 计划 2.3～2.12 的三档表
逐格覆盖出 13 环境 × xhard1/2/3 的单任务 {decision, native} 配置，并生成 jobs.json。
新档一律用 difficulty="xhard" 跑（沿用 xhard 机制），只改 decision 里的数值。"""
import copy
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
SNAP = json.loads((REPO / "scripts/configs/newtask-v5/sampling_config.json").read_text())["tasks"]
TASKS = sorted(["BinFill", "PickXtimes", "SwingXtimes", "PickHighlight", "VideoUnmask", "ButtonUnmask",
                "VideoUnmaskSwap", "ButtonUnmaskSwap", "VideoRepick", "PatternLock", "RouteStick",
                "VideoPlaceButton", "VideoPlaceOrder"])
ENV_CODE = {t: i for i, t in enumerate(TASKS)}
DCOL = ["yellow", "cyan", "magenta"]

# 每格：(覆盖描述 dict: 键路径 -> 值, 备注, driver 内补丁名列表)
T = {}
for tier, (nr, k) in enumerate([([5, 7], 1), ([6, 9], 2), ([7, 12], 3)], 1):
    T[("PickXtimes", tier)] = {"number_range.xhard": nr, "xhard.distractor.colors": DCOL[:k]}
for tier, (nr, k) in enumerate([([3, 4], 1), ([4, 6], 2), ([5, 8], 3)], 1):
    T[("SwingXtimes", tier)] = {"number_range.xhard": nr, "xhard.distractor.colors": DCOL[:k]}
for tier, pin in enumerate([[4, 5], [4, 6], [5, 6]], 1):
    T[("BinFill", tier)] = {"configs.xhard.put_in_numbers": pin}
for tier, (p, s) in enumerate([([4, 4], [7, 7]), ([4, 5], [8, 8]), ([5, 6], [8, 9])], 1):
    T[("PickHighlight", tier)] = {"highlight_count.xhard": p, "spawn_count.xhard": s}
for tier, (n, p, cc) in enumerate([(8, 2, [4, 4]), (10, 3, [5, 5]), (13, 3, [6, 7])], 1):
    T[("VideoUnmask", tier)] = {"pick_count.xhard": p, "xhard.distractor.count": n, "xhard.distractor.cube_count_range": cc}
for tier, (n, p, cc) in enumerate([(7, 2, [3, 4]), (9, 3, [4, 5]), (12, 3, [6, 6])], 1):
    T[("ButtonUnmask", tier)] = {"pick_count.xhard": p, "xhard.distractor.count": n, "xhard.distractor.cube_count_range": cc}
for task, swaps in (("VideoUnmaskSwap", [[4, 5], [5, 7], [7, 9]]), ("ButtonUnmaskSwap", [[3, 4], [4, 5], [5, 6]])):
    for tier, (sw, p, n, mult) in enumerate(zip(swaps, [2, 3, 3], [4, 6, 8], [1, 1.5, 1.5]), 1):
        # 外环含 cube 数计划未写，按 xhard 的「干扰数的一半」（10→5）内插
        T[(task, tier)] = {"swap_count_range.xhard": sw, "pick_count_range.xhard": [p, p],
                           "xhard.swap_speed_multiplier": mult, "xhard.distractor.count": n,
                           "xhard.distractor.cube_count_range": [n // 2, n // 2]}
for tier, (c, sw, rp) in enumerate([(4, [3, 5], [2, 3]), (5, [5, 7], [3, 4]), (6, [6, 9], [4, 5])], 1):
    T[("VideoRepick", tier)] = {"xhard.layout.cube_count": c, "swap.xhard": {"swap_min": sw[0], "swap_max": sw[1]},
                                "num_repeats_range.xhard": {"low": rp[0], "high_exclusive": rp[1] + 1}}
for tier, rng in enumerate([[9, 12], [13, 17], [18, 22]], 1):
    T[("PatternLock", tier)] = {"path_length_range.xhard": rng}
for tier, rng in enumerate([[8, 10], [11, 12], [13, 14]], 1):
    T[("RouteStick", tier)] = {"xhard.segment_count_range": rng}
# VideoPlace：xhard 代码只支持 return_to_origin；「不放回」与「只放回末块」在 xhard 路径上未实现，用全放回作上界代测
T[("VideoPlaceButton", 1)] = {"xhard.demo_object_count": 1}
T[("VideoPlaceButton", 2)] = {"xhard.demo_object_count": 2}
T[("VideoPlaceButton", 3)] = {"xhard.demo_object_count": 2}
T[("VideoPlaceOrder", 1)] = {"xhard.demo_object_count": 1}
T[("VideoPlaceOrder", 2)] = {"xhard.demo_object_count": 2}
T[("VideoPlaceOrder", 3)] = {"xhard.demo_object_count": 2}
NOTES = {
    ("VideoPlaceButton", 1): "计划 (k1,放回)，原样实现",
    ("VideoPlaceButton", 2): "计划 (k2,不放回)：xhard 路径未实现不放回，代测 (k2,全放回)=xhard 作上界",
    ("VideoPlaceButton", 3): "计划 (k2,只放回末块 return_last_only)：新语义需实现、未测；代测 (k2,全放回)=xhard 作上界",
    ("VideoPlaceOrder", 1): "计划 (k1,v[2,4],放回)，原样实现",
    ("VideoPlaceOrder", 2): "计划 (k2,v[2,3],不放回)：不放回未实现；代测 (k2,v[2,3],全放回) 作上界，v 上限 3 靠 driver 内补丁",
    ("VideoPlaceOrder", 3): "计划 (k2,v[2,4],不放回)：不放回未实现；代测 (k2,v[2,4],全放回)=xhard 作上界",
    ("VideoUnmaskSwap", 1): "外环含 cube 数计划未写，按干扰数一半 2；xhard1 交换速度 ×1（50 步）",
    ("ButtonUnmaskSwap", 1): "外环含 cube 数按干扰数一半 2；xhard1 交换速度 ×1（50 步）",
}
sys.path.insert(0, str(REPO / "src"))
from robomme.robomme_env.VideoUnmaskSwap import VideoUnmaskSwap as _VUS  # noqa: E402
VUS_CONFIGS = copy.deepcopy(_VUS.configs)
PATCHES = {("VideoPlaceOrder", 2): ["vpo_visit_max3"]}


def set_path(tree, path, value):
    keys = path.split(".")
    node = tree
    for k in keys[:-1]:
        node = node[k]
    if keys[-1] not in node:
        raise KeyError(path)
    node[keys[-1]] = value


def main(n_per_cell=6, n_ctrl=3):
    cdir = HERE / "configs"
    cdir.mkdir(exist_ok=True)
    jobs = []
    tiers = {1: "xhard1", 2: "xhard2", 3: "xhard3", 4: "xhard"}
    for task in TASKS:
        for tier in (1, 2, 3, 4):
            cfg = copy.deepcopy({"decision": SNAP[task]["decision"], "native": SNAP[task]["native"]})
            over = T.get((task, tier), {})
            for path, value in over.items():
                set_path(cfg["decision"], path, value)
            if task == "VideoUnmaskSwap" and tier < 4:
                # VUS 的 n_swaps/n_picks 实际取自 native.parameters.configs[难度]（快照里缺省、由类属性 setdefault 补），
                # decision.swap_count_range/pick_count_range 在 VUS 上是不被消费的键；故显式给出 native.configs（不受全等守卫）
                cfgs = copy.deepcopy(VUS_CONFIGS)
                sw, pk = over["swap_count_range.xhard"], over["pick_count_range.xhard"]
                cfgs["xhard"].update(swap_min=sw[0], swap_max=sw[1], pick_min=pk[0], pick_max=pk[1])
                cfg["native"]["parameters"]["configs"] = cfgs
                over = dict(over, **{"native.parameters.configs.xhard": cfgs["xhard"]})
            name = f"{task}_{tiers[tier]}"
            doc = {"task": task, "tier": tiers[tier], "overrides": over, "note": NOTES.get((task, tier), ""),
                   "patches": PATCHES.get((task, tier), []), "sampling_config": cfg}
            (cdir / f"{name}.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1))
            n = n_per_cell if tier < 4 else n_ctrl
            for i in range(n):
                seed = 9_000_000 + ENV_CODE[task] * 10_000 + tier * 1000 + i * 101
                jobs.append({"task": task, "tier": tiers[tier], "tier_idx": tier, "i": i, "seed": seed,
                             "config": f"configs/{name}.json", "patches": PATCHES.get((task, tier), [])})
    (HERE / "jobs.json").write_text(json.dumps(jobs, indent=0))
    print(f"jobs={len(jobs)} configs={len(TASKS) * 4}")


if __name__ == "__main__":
    main(*(int(a) for a in sys.argv[1:]))
