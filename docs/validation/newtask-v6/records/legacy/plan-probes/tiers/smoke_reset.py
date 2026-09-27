#!/usr/bin/env python3
"""本机 reset 级冒烟：每格第 0 个 seed 做 gym.make + reset，确认配置被守卫接受、抽到的旋钮落在新区间。"""
import json
import multiprocessing as mp
import os
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import tiers_worker  # noqa: E402


def one(item):
    import gymnasium as gym
    for p in item["patches"]:
        tiers_worker.apply_patch(p)
    cfg = json.loads((HERE / item["config"]).read_text())["sampling_config"]
    t0 = time.time()
    row = {"task": item["task"], "tier": item["tier"], "seed": item["seed"]}
    try:
        env = gym.make(item["task"], obs_mode="rgb+depth+segmentation", control_mode="pd_joint_pos",
                       render_mode="rgb_array", reward_mode="dense", seed=item["seed"], difficulty="xhard",
                       sampling_config=cfg)
        env.reset()
        u = env.unwrapped
        row["ok"] = True
        row["n_tasks"] = len(u.task_list)
        spec = tiers_worker._plain(u._spec.to_dict())
        row["objects"] = {k: v for k, v in (spec.get("objects") or {}).items() if len(json.dumps(v)) < 200}
        row["actions_keys"] = sorted((spec.get("actions") or {}).keys())
        objs = spec.get("objects") or {}
        row["distractor_info"] = {k: (len(v) if isinstance(v, (list, dict)) else v) for k, v in objs.items() if "distract" in k}
        if isinstance(objs.get("distractors"), dict):
            row["distractor_sub"] = {k: (len(v) if isinstance(v, (list, dict)) else v) for k, v in objs["distractors"].items()}
        acts = spec.get("actions") or {}
        if "path_nodes" in acts:
            row["path_nodes_len"] = len(acts["path_nodes"])
        env.close()
    except Exception as exc:  # noqa: BLE001
        row["ok"] = False
        row["error"] = f"{type(exc).__name__}: {exc}"[:500]
        row["tb"] = traceback.format_exc()[-800:]
    row["wall"] = round(time.time() - t0, 1)
    return row


def main():
    jobs = json.loads((HERE / "jobs.json").read_text())
    seen, items = set(), []
    for j in jobs:
        key = (j["task"], j["tier"])
        if key not in seen:
            seen.add(key)
            items.append(j)
    gpu = sys.argv[1] if len(sys.argv) > 1 else "0"
    with ProcessPoolExecutor(max_workers=10, mp_context=mp.get_context("spawn"),
                             initializer=tiers_worker.init, initargs=(gpu,)) as ex:
        with open(HERE / "smoke_reset.jsonl", "w") as fh:
            for row in ex.map(one, items):
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                print(row["task"], row["tier"], row["ok"], row.get("error", "")[:200], row["wall"], flush=True)


if __name__ == "__main__":
    main()
