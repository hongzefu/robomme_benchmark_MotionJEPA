#!/usr/bin/env python3
"""用 v2 仿真遮蔽结果作只读代理真值，验证 v3 纯 CV arm mask。

v2 的 ``front_rgb_masked`` 同时涂掉桌面与机器人，但机器人渲染几乎无彩色、木桌高饱和，因此
``v2_changed & HSV_saturation<=阈值`` 可作为 robot-body 代理 mask。它不包含 v2 特意保留的夹爪，
所以 v3 比该代理多删夹爪是预期行为。这个脚本只用于验收，生产算法完全不读取 v2 遮蔽图。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

import cv2
import h5py
import numpy as np

from cv_arm_removal import ArmRemovalConfig, remove_robot_arm_sequence


def _timestep_names(group: h5py.Group) -> list[str]:
    names = [
        name
        for name in group
        if name.startswith("timestep_") and name[len("timestep_") :].isdigit()
    ]
    return sorted(names, key=lambda name: int(name[len("timestep_") :]))


def verify_h5(path: Path, episode: int) -> dict[str, Any]:
    with h5py.File(path, "r") as handle:
        episode_name = f"episode_{episode}"
        if episode_name not in handle:
            raise KeyError(f"{path}: 缺少 {episode_name}")
        group = handle[episode_name]
        names = _timestep_names(group)
        if not names:
            raise ValueError(f"{path}/{episode_name}: 没有 timestep")
        rgb = np.stack(
            [np.asarray(group[name]["obs/front_rgb"][()], dtype=np.uint8) for name in names]
        )
        depth = np.stack(
            [np.asarray(group[name]["obs/front_depth"][()]) for name in names]
        )
        old_masked = np.stack(
            [
                np.asarray(group[name]["obs/front_rgb_masked"][()], dtype=np.uint8)
                for name in names
            ]
        )

    result = remove_robot_arm_sequence(rgb, depth)
    masks = np.asarray(result.masks, dtype=bool)
    removed = np.asarray(result.frames, dtype=np.uint8)
    unchanged_ok = bool(np.array_equal(removed[~masks], rgb[~masks]))

    saturation = np.stack(
        [cv2.cvtColor(frame, cv2.COLOR_RGB2HSV)[..., 1] for frame in rgb]
    )
    old_changed = np.any(old_masked != rgb, axis=-1)
    proxy = old_changed & (saturation <= ArmRemovalConfig().arm_saturation_max)
    proxy_pixels = int(proxy.sum())
    recalled = int((masks & proxy).sum())
    recall = float(recalled / proxy_pixels) if proxy_pixels else 1.0
    extra = masks & ~old_changed
    return {
        "h5": str(path),
        "episode": int(episode),
        "frame_count": len(names),
        "proxy_pixels": proxy_pixels,
        "proxy_recalled_pixels": recalled,
        "proxy_recall": recall,
        "extra_over_v2_painted_pixels": int(extra.sum()),
        "overall_mask_fraction": float(masks.mean()),
        "mask_outside_bitwise_unchanged": unchanged_ok,
        "depth_table_fit_frames": int(
            result.stats["summary"]["depth_table_fit_frames"]
        ),
    }


def _args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="验证 v3 纯 CV 去臂 mask")
    parser.add_argument("--h5", nargs="+", required=True)
    parser.add_argument("--episode", type=int, default=0)
    parser.add_argument("--min-proxy-recall", type=float, default=0.99)
    parser.add_argument("--json", dest="json_path")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    namespace = _args(argv)
    records: list[dict[str, Any]] = []
    failures: list[str] = []
    for raw in namespace.h5:
        path = Path(raw).expanduser().resolve()
        try:
            record = verify_h5(path, namespace.episode)
        except Exception as exc:
            failures.append(f"{path.name}: {exc}")
            print(f"✗ {path.name}: {exc}", flush=True)
            continue
        records.append(record)
        ok = (
            record["proxy_recall"] >= namespace.min_proxy_recall
            and record["mask_outside_bitwise_unchanged"]
            and record["depth_table_fit_frames"] == record["frame_count"]
        )
        if not ok:
            failures.append(f"{path.name}: 未达到阈值")
        print(
            f"{'✓' if ok else '✗'} {path.name}: proxy recall "
            f"{record['proxy_recall']:.4%}，mask {record['overall_mask_fraction']:.2%}，"
            f"RGB-D {record['depth_table_fit_frames']}/{record['frame_count']}",
            flush=True,
        )

    payload = {
        "passed": not failures,
        "minimum_proxy_recall": float(namespace.min_proxy_recall),
        "records": records,
        "failures": failures,
    }
    if namespace.json_path:
        target = Path(namespace.json_path).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    if records:
        print(
            f"汇总：{len(records)} 个任务，最低 proxy recall "
            f"{min(item['proxy_recall'] for item in records):.4%}",
            flush=True,
        )
    return 1 if failures or not records else 0


if __name__ == "__main__":
    raise SystemExit(main())
