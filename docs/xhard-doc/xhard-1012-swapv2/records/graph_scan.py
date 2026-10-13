"""阶段零：仅 reset，比较不含按钮、按钮底座、按钮包络的可行槽对图。"""

import argparse
import hashlib
import itertools
import json
import subprocess
from pathlib import Path

import gymnasium as gym
import numpy as np
import robomme.robomme_env  # noqa: F401
import robomme_xhard
from robomme_xhard.collision import bin_collision as bc
import robomme_xhard.envs.video_unmask_swap as vus
import robomme_xhard.envs.button_unmask_swap as bus
import robomme_xhard.envs.video_repick as vr

TASKS = ("VideoUnmaskSwap", "ButtonUnmaskSwap", "VideoRepick")
CAPTURE = {}


def capture(env, actors, bystanders, prefix):
    """只替换 xhard 的规划器，读取父类刚建完的真实布局。"""
    CAPTURE["states"] = [bc.object_state_from_actor(a, f"{prefix}{i}") for i, a in enumerate(actors)]


vus.certify_swap_plan = capture
bus.certify_swap_plan = capture
vr.certify_swap_plan = capture


def shape_pose(component, shape):
    """SAPIEN 碰撞形状的世界中心和旋转。"""
    pose = component.entity.pose * shape.local_pose
    return np.asarray(pose.p, dtype=np.float64), bc.quat_to_matrix(pose.q)


def button_states(articulation, name):
    """从真实盒体、圆柱及其世界位姿构造底座和静止包络。"""
    links = {link.get_name(): link for link in articulation.get_links()}
    assert set(links) == {"button_base", "button_cap"}, links.keys()
    base_component = links["button_base"]._objs[0]
    cap_component = links["button_cap"]._objs[0]
    bases = base_component.get_collision_shapes()
    caps = cap_component.get_collision_shapes()
    assert len(bases) == len(caps) == 1
    base, cap = bases[0], caps[0]
    assert type(base).__name__ == "PhysxCollisionShapeBox"
    assert type(cap).__name__ == "PhysxCollisionShapeCylinder"
    bp, br = shape_pose(base_component, base)
    cp, cr = shape_pose(cap_component, cap)
    half = np.asarray(base.half_size, dtype=np.float64)
    be = np.abs(br) @ half
    # SAPIEN 圆柱的轴为局部 x；本任务的轴必须竖直。
    axis = cr[:, 0]
    assert np.allclose(np.abs(axis), [0, 0, 1], atol=1e-6), axis
    radius, length = float(cap.radius), float(cap.half_length)
    ce = np.abs(axis) * length + radius * np.sqrt(np.maximum(0, 1 - axis * axis))
    blo, bhi, clo, chi = bp - be, bp + be, cp - ce, cp + ce
    assert np.all(clo[:2] >= blo[:2] - 1e-8) and np.all(chi[:2] <= bhi[:2] + 1e-8)
    assert abs(float(blo[2])) < 1e-7, blo
    assert np.allclose(articulation.get_qpos().cpu().numpy(), 0, atol=1e-7)
    low, high = np.minimum(blo, clo), np.maximum(bhi, chi)
    low[2] = blo[2]
    identity = np.array([1.0, 0, 0, 0])
    base_state = bc.ObjectState(name, bp, np.asarray((base_component.entity.pose * base.local_pose).q),
                                [bc.ShapeSpec(np.zeros(3), identity, half)])
    envelope = bc.ObjectState(name, (low + high) / 2, identity,
                              [bc.ShapeSpec(np.zeros(3), identity, (high - low) / 2)])
    return base_state, envelope, {"name": name, "base_low": blo.tolist(), "base_high": bhi.tolist(),
                                  "cap_low": clo.tolist(), "cap_high": chi.tolist(),
                                  "envelope_low": low.tolist(), "envelope_high": high.tolist(),
                                  "radius": radius, "half_length": length, "cap_inside_base": True}


def graph(states, bystanders):
    n = len(states)
    adj, gaps, rejections = [[False] * n for _ in range(n)], {}, {}
    for a, b in itertools.combinations(range(n), 2):
        others = [s for i, s in enumerate(states) if i not in (a, b)] + bystanders
        gap, rejection = bc.check_swap_sweep(states[a], states[b], others, sweep_index=-1, stage="graph")
        adj[a][b] = adj[b][a] = rejection is None
        key = f"{a}-{b}"
        gaps[key] = float(gap) if rejection is None else rejection.gap_m
        if rejection is not None:
            rejections[key] = rejection.as_dict()
    isolated = [i for i, row in enumerate(adj) if not any(row)]
    return {"adj": adj, "gaps": gaps, "rejections": rejections, "isolated": isolated,
            "b_pass": not isolated}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    assert not args.out.exists(), f"禁止覆盖：{args.out}"
    manifest = json.loads(args.manifest.read_text())
    rows = []
    def save():
        args.out.write_text(json.dumps({"git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
                                       "manifest_sha256": hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
                                       "rows": rows}, ensure_ascii=False, indent=2) + "\n")
    first_buttons = 0
    for task in TASKS:
        for index, item in enumerate(manifest["tasks"][task]):
            if args.limit is not None and len(rows) >= args.limit:
                break
            env = gym.make(robomme_xhard.env_name(task), seed=item["seed"], difficulty="xhard20",
                           obs_mode="rgb+depth+segmentation", control_mode="pd_joint_pos",
                           render_mode="rgb_array", reward_mode="dense")
            try:
                env.reset(seed=item["seed"])
                states = CAPTURE.pop("states")
                names = ["button_left", "button_right"] if task == "ButtonUnmaskSwap" else (
                    ["button_left"] if task == "VideoRepick" else [])
                bases, envelopes, geometry = [], [], []
                for name in names:
                    base, envelope, detail = button_states(getattr(env.unwrapped, name), name)
                    bases.append(base); envelopes.append(envelope); geometry.append(detail)
                if index == 0:
                    first_buttons += len(names)
                result = {"task": task, **item, "slots": [s.p.tolist() for s in states],
                          "buttons": geometry, "no_button": graph(states, []),
                          "base_only": graph(states, bases), "envelope": graph(states, envelopes)}
                rows.append(result)
                save()
                print("SCAN", task, item["seed"], "b_pass", result["envelope"]["b_pass"],
                      "isolated", result["envelope"]["isolated"], flush=True)
            finally:
                env.close()
    rejected = sum(not row["envelope"]["b_pass"] for row in rows)
    differences = sum(row["base_only"]["adj"] != row["envelope"]["adj"] for row in rows)
    print(f"BUTTON_ENVELOPE=PASS buttons={first_buttons} base_box=1 cap_cylinder=1 cap_inside_base=1", flush=True)
    print(f"SWAP_V2_GRAPH_SCAN=INFO seeds={len(rows)} b_pass={len(rows)-rejected} b_reject={rejected} base_envelope_diff={differences}", flush=True)
    if rejected > 6:
        print("GRAPH_SCAN_GATE=FAIL 剔除超过六个，停止等待用户裁决", flush=True)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
