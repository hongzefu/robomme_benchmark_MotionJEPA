"""探针：用真实 reset 布局算可行槽对图 G，比较 v1 最近邻配对与 V9 负载均衡配对，输出 JSON。

只读仓库；进程内把 certify_swap_plan 换成记录器（不落盘），避免 v1 在 reset 时抛错。
"""
import json
import sys
from pathlib import Path

import numpy as np
import torch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "lib"))
import swap_uniform as su  # V9 5f4f2f9c 原样

import gymnasium as gym
import robomme.robomme_env  # noqa: F401
import robomme_xhard
from robomme_xhard import swap_plan as sp
from robomme_xhard.collision import bin_collision as bc
from robomme_xhard.collision import SceneGenerationError
import robomme_xhard.envs.video_unmask_swap as vus
import robomme_xhard.envs.button_unmask_swap as bus

CAPTURE = {}


def fake_certify(env, actors, bystanders, prefix):
    CAPTURE["states"] = [bc.object_state_from_actor(a, f"{prefix}{i}") for i, a in enumerate(actors)]


vus.certify_swap_plan = fake_certify
bus.certify_swap_plan = fake_certify

CASES = [("VideoUnmaskSwap", 5700, 11), ("VideoUnmaskSwap", 9300, 11), ("ButtonUnmaskSwap", 10500, 12)]
out = []
for task, seed, s_max in CASES:
    env = gym.make(robomme_xhard.env_name(task), seed=seed, difficulty="xhard20",
                   obs_mode="rgb+depth+segmentation", control_mode="pd_joint_pos",
                   render_mode="rgb_array", reward_mode="dense")
    env.reset(seed=seed)
    states = CAPTURE.pop("states")
    env.close()
    n = len(states)
    same_shape = all(len(s.shapes) == len(states[0].shapes) and all(
        np.allclose(x.half, y.half) for x, y in zip(s.shapes, states[0].shapes))
        for s in states)
    gaps = {}

    def feasible(a, b):
        others = [s for j, s in enumerate(states) if j not in (a, b)]
        gap, rej = bc.check_swap_sweep(states[a], states[b], others, sweep_index=-1, stage="graph")
        gaps[f"{a}-{b}"] = None if rej is None else rej.gap_m
        if rej is None:
            gaps[f"{a}-{b}"] = float(gap)
        return rej is None

    adj = su.slot_pair_graph(n, feasible)
    # v1：最近邻配对（同一独立流）
    g1 = torch.Generator().manual_seed(seed + sp.SWAP_PLAN_SEED_OFFSET)
    try:
        p1 = sp.plan_swaps({i: s for i, s in enumerate(states)}, [], s_max, g1)
        v1 = {"pairs": [[int(a), int(b)] for a, b, _, _ in p1.pairs], "usage": p1.usage, "error": None}
    except SceneGenerationError as exc:
        v1 = {"pairs": None, "usage": None, "error": f"{type(exc).__name__}: {exc}"}
    # V9 S5：可行图 + 负载均衡
    g2 = torch.Generator().manual_seed(seed + sp.SWAP_PLAN_SEED_OFFSET)
    plan = su.plan_balanced_swaps(adj, s_max, g2) if su.graph_connected(adj) else None
    nearest = {}
    for i, s in enumerate(states):
        d = [(np.linalg.norm(s.p[:2] - t.p[:2]), j) for j, t in enumerate(states) if j != i]
        nearest[i] = min(d)[1]
    out.append(dict(task=task, seed=seed, s_max=s_max, same_shape=bool(same_shape),
                    slots=[s.p[:2].tolist() for s in states], yaw_q=[s.q.tolist() for s in states],
                    half=[[sh.half.tolist() for sh in s.shapes] for s in states][0],
                    adj=adj, gaps=gaps, connected=su.graph_connected(adj), nearest=nearest, v1=v1,
                    v2=None if plan is None else dict(pairs=[list(p) for p in plan.pairs],
                                                     slot_pairs=[list(p) for p in plan.slot_pairs],
                                                     counts=plan.counts, spread=plan.spread, tries=plan.tries)))
    print("PROBE", task, seed, "edges", len(su.graph_edges(adj)), "connected", su.graph_connected(adj),
          "v1_err", v1["error"], "v2_counts", None if plan is None else plan.counts, flush=True)
(HERE / "probe_g.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
print("EXIT_OK")
