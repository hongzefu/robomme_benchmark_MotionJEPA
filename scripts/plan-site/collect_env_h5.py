"""只读已完成 H5 的标量 info；不读取图像、不导入仿真环境。

请求为 JSON 列表，每项含 task/seed/level/episode/h5 及 summary 的
timesteps/demo_timesteps/exec_timesteps/demo_windows/exec_windows/windows。
--requests - 从标准输入读取；--root 解析相对 H5 路径；--out 必须新建。
"""
from __future__ import annotations

import argparse
import json
import math
import pathlib
import re
import sys

MERGE = {
    "BinFill": (r"^pick up the", r"^put it into the bin"),
    "PickXtimes": (r"^pick up the", r"^place the"),
    "SwingXtimes": (r"right-side target", r"left-side target"),
    "StopCube": (r"^move to the top of the button", r"^press the button"),
    **{t: (r"^pick up the container", r"^put down the container") for t in
       ("VideoUnmask", "ButtonUnmask", "VideoUnmaskSwap", "ButtonUnmaskSwap")},
    "PickHighlight": (r"^pick up the", r"^place the cube onto the table"),
    "VideoRepick": (r"^pick up the correct cube", r"^put it down"),
    **{t: (r"^pick up the cube", r"^place the cube onto the correct target") for t in
       ("VideoPlaceButton", "VideoPlaceOrder")},
    "MoveCube": None, "InsertPeg": None, "PatternLock": None, "RouteStick": None,
}
SWAP_TASKS = {"VideoUnmaskSwap", "ButtonUnmaskSwap", "VideoRepick", "VideoPlaceButton", "VideoPlaceOrder"}
SWAP_REASON = "控制步到录像帧的映射尚未验证；交换遗漏与总遗漏未测，不以零代替。"


def windows(length):
    return max(0, (length - 33) // 16 + 1)


def action_stats(task, records):
    """按边界切段，保留同名连续子目标；区间为左闭右开。"""
    if not records or not records[0][0]:
        raise ValueError("H5 第 0 帧不是子目标起点")
    segments = []
    for i, (boundary, text, demo) in enumerate(records):
        if boundary:
            if segments:
                segments[-1]["end"] = i
            segments.append({"start": i, "end": len(records), "text": text, "demo": demo})
        elif text != segments[-1]["text"] or demo != segments[-1]["demo"]:
            raise ValueError(f"第 {i} 帧标签或演示标记改变却没有边界")
    active = [s for s in segments if not s["demo"] and s["text"] != "All tasks completed"]
    units, i, rule = [], 0, MERGE[task]
    while i < len(active):
        a = active[i]
        b = active[i + 1] if i + 1 < len(active) else None
        if rule and b and re.search(rule[0], a["text"]) and re.search(rule[1], b["text"]):
            units.append([a["start"], b["end"], a["text"] + " → " + b["text"]])
            i += 2
        else:
            units.append([a["start"], a["end"], a["text"]])
            i += 1
    frames = [math.floor(i * (len(records) - 1) / 7 + .5) for i in range(8)]
    missed = [u for u in units if not any(u[0] <= f < u[1] for f in frames)]
    unknown = task in SWAP_TASKS
    return {"frames": frames, "units": len(units), "miss_units": len(missed),
            "miss_swaps": None if unknown else 0, "miss": None if unknown else len(missed),
            "swap_reason": SWAP_REASON if unknown else "该任务无交换事件。",
            "missed_units": missed, "segments": segments}


def collect(request, root):
    import h5py
    path = pathlib.Path(request["h5"])
    if not path.is_absolute():
        path = root / path
    with h5py.File(path, "r") as handle:
        group = handle[f'episode_{request["episode"]}']
        if int(group["setup/seed"][()]) != request["seed"]:
            raise ValueError(f"seed 不符：{path}")
        names = [n for n in group if n.startswith("timestep_")]
        if set(names) != {f"timestep_{i}" for i in range(len(names))}:
            raise ValueError(f"录像索引不是从 0 连续递增：{path}")
        records = []
        for i in range(len(names)):
            info = group[f"timestep_{i}/info"]
            value = info["simple_subgoal"][()]
            text = value.decode("utf-8") if isinstance(value, bytes) else str(value)
            records.append((bool(info["is_subgoal_boundary"][()]), text,
                            bool(info["is_video_demo"][()])))
    total, demo = len(records), sum(r[2] for r in records)
    if [r[2] for r in records] != [True] * demo + [False] * (total - demo):
        raise ValueError(f"演示段不连续或不在录像开头：{path}")
    measured = {"timesteps": total, "demo_timesteps": demo, "exec_timesteps": total - demo,
                "demo_windows": windows(demo), "exec_windows": windows(total - demo),
                "windows": windows(demo) + windows(total - demo)}
    for key, value in measured.items():
        if request[key] != value:
            raise ValueError(f"{path} {key}: H5={value} summary={request[key]}")
    return {**{k: request[k] for k in ("task", "seed", "level", "episode", "h5")},
            **measured, **action_stats(request["task"], records)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requests", required=True)
    parser.add_argument("--root", type=pathlib.Path, required=True)
    parser.add_argument("--out", type=pathlib.Path, required=True)
    args = parser.parse_args()
    requests = json.load(sys.stdin) if args.requests == "-" else json.loads(pathlib.Path(args.requests).read_text())
    identities = [(r["task"], r["seed"], r["level"]) for r in requests]
    if len(identities) != len(set(identities)):
        raise ValueError("请求身份重复")
    if args.out.exists():
        raise FileExistsError(args.out)
    rows = []
    for request in requests:
        rows.append(collect(request, args.root))
        print(f'H5_INFO_ROW=PASS task={request["task"]} seed={request["seed"]} level={request["level"]}', flush=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf-8") as stream:
        json.dump({"schema": 1, "rows": rows}, stream, ensure_ascii=False, indent=2)
    print(f"H5_INFO=PASS rows={len(rows)} out={args.out}")


if __name__ == "__main__":
    main()
