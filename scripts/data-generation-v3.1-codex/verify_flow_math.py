#!/usr/bin/env python3
"""验证落盘的 2D flow ground truth 在数学上确实与 3D 真值一一对应。

### 正反变换

记内参 ``K``（``fx, fy, cx, cy``），外参 ``[R | t]``（OpenCV 的 world->camera）：

- 正向：``X_c = R·X_w + t``；``z = X_c[2]``；``u = fx·X_c[0]/z + cx``，``v = fy·X_c[1]/z + cy``
- 反向：``X_c' = z·K⁻¹·[u, v, 1]ᵀ``；``X_w' = R⁻¹·(X_c' − t)``

在 ``z > 0`` 的半空间上，``X_w ↦ (u, v, z)`` 是双射（``fx, fy ≠ 0``、``R`` 可逆），上面的反向式
就是它逆映射的显式构造。注意**只有 (u, v) 是反解不出 3D 的**——一个像素对应一整条射线。落盘的
``z_cam`` 正是把这个一对多映射补成双射的那一维。

### 六条判据

| # | 判据 | 阈值 | 证明了什么 |
|---|---|---|---|
| 1 | 闭环还原 ‖X_w' − pos_3d‖∞ | ≤ 1e-9 m | 反向变换精确还原 3D 真值 |
| 2 | 重投影 ‖(u',v') − (u,v)‖∞ | ≤ 1e-9 px 且 ≤ 100 ulp | 正向∘反向 = 恒等，双射闭合 |
| 3 | pos_2d_yx == [rint(v), rint(u)] | 逐元素相等 | float 口径与 choice_action 整数口径不漂移 |
| 4 | 雅可比二阶收敛 r(Δ/2)/r(Δ) | → 0.25 ± 0.05 | 2D 位移确实是 3D 位移的正确微分像 |
| 5 | 静止物体零位移 ‖flow_2d‖ | < 1e-12 px | 相机静止 ⇒ 静止物零流 |
| 6 | **充分可见**帧上投影点落在自身掩码内的比例 | ≥ 95% | 投影结果与真实渲染图像一致 |

判据 1、2 只能证明「存下来的 (u,v,z) 与存下来的 X_w 自洽」；判据 6 才把它锚到真实渲染图像上；
判据 4 才把「位移」这一层锁死。六条缺一不可。

⚠ 刻意**不做**「投影深度 vs front_depth 逐点等值」这条判据：``pos_3d`` 是物体原点（几何中心
附近），而深度图给的是可见**表面**的深度，两者系统性相差半个物体厚度。该量只作诊断打印，
不设阈值。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

import h5py
import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from robomme.robomme_env.utils.choice_action_mapping import (  # noqa: E402
    project_world_to_pixel_subpixel,
    projection_jacobian,
    unproject_pixel_to_world,
)


# 各判据阈值
TOL_ROUNDTRIP_WORLD = 1e-9  # 米
# 判据 2 用「绝对 + 相对」双阈值。绝对阈值本来定的是 1e-12 px，实测发现它对本链路不成立，
# 但原因不是实现有问题，而是阈值本身与坐标量级挂钩：pos_2d_uv 刻意不裁剪，出界物体的
# 子像素坐标可以到几百甚至上千，而 float64 在 1000 附近的 ulp 已经是 1.1e-13——「反投影
# (一次 LU 解) + 正投影(两次矩阵乘 + 一次除法)」这套复合运算累积十几个 ulp 是必然的，
# 实测最坏样本 1.59e-12 恰好就是 14 ulp。
#
# 因此改成量级无关的判据：绝对误差仍压在 1e-9 px（亚纳米像素，比任何实际用途严格 6 个
# 数量级），同时叠加一条真正检验「双射闭合到浮点精度」的相对判据——误差不得超过该像素
# 坐标量级的 100 ulp。后者才是这条判据的实质，前者只是防止量级失控的兜底。
TOL_REPROJECTION_PIXEL = 1e-9  # 像素
TOL_REPROJECTION_ULP = 100.0  # 相对于像素坐标量级的 ulp 倍数
TOL_STATIC_FLOW_PIXEL = 1e-12  # 像素
JACOBIAN_RATIO_TARGET = 0.25
JACOBIAN_RATIO_TOLERANCE = 0.05

# 判据 6 的口径经过一次修正。最初是「全部 in_frame 帧上，投影点落在自身掩码内的比例 ≥ 90%」，
# 实测有三个任务过不了（PickXtimes 63.5%、VideoPlaceButton 87.0%、VideoPlaceOrder 87.6%）。
# 逐物体拆开一看，低比例全都出在名字带 target 的物体上——那是「目标位置标记」，任务过程中方块
# 最终会盖到它上面，**被遮挡正是任务语义本身**。PickXtimes 的 target 全帧只有 29.9% 未被遮挡。
#
# 也就是说，原口径度量的其实是「场景里发生了多少遮挡」，而不是「投影对不对」——遮挡越多分越低，
# 可 point_unoccluded=False 恰恰是该字段忠实完成了自己的工作。
#
# 修正后只在物体**充分可见**的帧上统计：把该物体本 episode 的 seg_pixel_count 取 75 分位数，
# 只看可见像素数达到这个水平的帧（此时它基本没被挡）。在这些帧上投影点理应落在自身掩码内，
# 落不上才是投影错了。实测这么算之后，全部 16 个任务的每一个 actor 都是 100%（唯一例外是
# VideoPlaceOrder 的 cube_blue_0，299/300 = 99.7%），阈值因此定在 95%。
# 全帧比例保留为诊断量一并打印，不再作为判据。
MIN_UNOCCLUDED_RATIO = 0.95
VISIBLE_PERCENTILE = 75.0

JACOBIAN_SAMPLE_LIMIT = 300  # 判据 4 抽样上限，避免逐帧逐物体全跑拖慢验证
JACOBIAN_STEP = 1e-3  # 米


class FlowVerificationError(RuntimeError):
    """h5 结构不满足验证前提（缺 flow 组、字段对不上等）。"""


def _text(dataset: Any) -> str:
    value = dataset[()]
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def _timestep_names(episode_group: h5py.Group) -> list[str]:
    named: list[tuple[int, str]] = []
    for name in episode_group.keys():
        if not name.startswith("timestep_"):
            continue
        suffix = name[len("timestep_") :]
        if suffix.isdigit():
            named.append((int(suffix), name))
    named.sort()
    return [name for _, name in named]


def _read_flow_objects(setup_group: h5py.Group) -> dict[str, dict[str, Any]]:
    """读 setup/flow_objects 字典：key -> {original_name, seg_id, kind, articulation_name}。"""
    objects_group = setup_group.get("flow_objects")
    if not isinstance(objects_group, h5py.Group):
        raise FlowVerificationError("setup 下缺少 flow_objects，该 h5 未写入 flow")
    result: dict[str, dict[str, Any]] = {}
    for key in objects_group.keys():
        entry = objects_group[key]
        result[key] = {
            "original_name": _text(entry["original_name"]),
            "seg_id": int(entry["seg_id"][()]),
            "kind": _text(entry["kind"]),
            "articulation_name": _text(entry["articulation_name"]),
        }
    return result


def verify_episode(
    episode_group: h5py.Group,
    label: str,
    rng: np.random.Generator,
) -> dict[str, Any]:
    """对单个 episode 跑完六条判据，返回结构化结果。"""
    setup_group = episode_group.get("setup")
    if not isinstance(setup_group, h5py.Group):
        raise FlowVerificationError(f"{label}：缺少 setup group")

    schema_version = (
        _text(setup_group["flow_schema_version"])
        if "flow_schema_version" in setup_group
        else ""
    )
    flow_objects = _read_flow_objects(setup_group)
    intrinsic = np.asarray(setup_group["front_camera_intrinsic"][()], dtype=np.float64)

    timestep_names = _timestep_names(episode_group)
    if not timestep_names:
        raise FlowVerificationError(f"{label}：没有 timestep")

    # ---- 逐帧读入 ----
    extrinsics: list[np.ndarray] = []
    frames: list[dict[str, np.ndarray]] = []
    for name in timestep_names:
        step_group = episode_group[name]
        flow_group = step_group.get("flow")
        if not isinstance(flow_group, h5py.Group):
            raise FlowVerificationError(f"{label}/{name}：缺少 flow group")
        extrinsics.append(
            np.asarray(step_group["obs"]["front_camera_extrinsic"][()], dtype=np.float64)
        )
        frames.append({key: flow_group[key][()] for key in flow_group.keys()})

    missing_keys = set(flow_objects) - set(frames[0])
    if missing_keys:
        raise FlowVerificationError(
            f"{label}：setup 声明的物体在 timestep_0 的 flow 里缺失：{sorted(missing_keys)[:5]}"
        )

    # ---- 判据 5 的前置：相机外参必须逐帧逐位相同（base_camera 是固定相机）----
    base_extrinsic = extrinsics[0]
    extrinsic_is_constant = all(
        np.array_equal(item, base_extrinsic) for item in extrinsics
    )

    # ---- 判据 1 / 2 / 3 / 6：逐帧逐物体全量 ----
    max_world_error = 0.0
    max_reprojection_error = 0.0
    max_reprojection_ulp = 0.0
    pixel_convention_mismatches = 0
    checked_samples = 0

    # 判据 6 需要按物体分组统计，才能逐物体判断「什么时候算充分可见」
    per_object_samples: dict[str, list[tuple[int, bool]]] = {}
    unoccluded_hits = {"actor": 0, "link": 0, "tcp": 0}
    unoccluded_total = {"actor": 0, "link": 0, "tcp": 0}

    jacobian_candidates: list[tuple[int, str]] = []

    for frame_index, (frame, extrinsic) in enumerate(zip(frames, extrinsics)):
        for key, record in frame.items():
            kind = flow_objects.get(key, {}).get("kind", "actor")
            z_cam = float(record["z_cam"])
            if not np.isfinite(z_cam) or z_cam <= 0.0:
                continue
            checked_samples += 1

            u, v = (float(record["pos_2d_uv"][0]), float(record["pos_2d_uv"][1]))
            world = np.asarray(record["pos_3d"], dtype=np.float64)

            # 判据 1：反投影闭环还原 3D
            restored = unproject_pixel_to_world(
                u, v, z_cam, intrinsic_cv=intrinsic, extrinsic_cv=extrinsic
            )
            if restored is None:
                raise FlowVerificationError(
                    f"{label}/timestep_{frame_index}/{key}：反投影失败（深度 {z_cam}）"
                )
            max_world_error = max(
                max_world_error, float(np.max(np.abs(restored - world)))
            )

            # 判据 2：再投影回像素
            reprojected = project_world_to_pixel_subpixel(
                world_xyz=restored, intrinsic_cv=intrinsic, extrinsic_cv=extrinsic
            )
            if reprojected is None:
                raise FlowVerificationError(
                    f"{label}/timestep_{frame_index}/{key}：重投影失败"
                )
            reprojection_error = float(
                max(abs(reprojected[0] - u), abs(reprojected[1] - v))
            )
            max_reprojection_error = max(max_reprojection_error, reprojection_error)
            # 换算成该像素坐标量级的 ulp 倍数，这才是量级无关的浮点闭合判据
            pixel_scale = max(abs(u), abs(v), 1.0)
            max_reprojection_ulp = max(
                max_reprojection_ulp, reprojection_error / float(np.spacing(pixel_scale))
            )

            # 判据 3：两套像素口径必须严格对应
            if bool(record["in_frame"]):
                expected_yx = np.asarray(
                    [int(np.rint(v)), int(np.rint(u))], dtype=np.int64
                )
                actual_yx = np.asarray(record["pos_2d_yx"], dtype=np.int64)
                if not np.array_equal(expected_yx, actual_yx):
                    pixel_convention_mismatches += 1

                # 判据 6：投影点是否落在自身分割掩码内
                if int(record["seg_pixel_count"]) > 0 and kind in unoccluded_total:
                    unoccluded_total[kind] += 1
                    if bool(record["point_unoccluded"]):
                        unoccluded_hits[kind] += 1
                    if kind == "actor":
                        per_object_samples.setdefault(key, []).append(
                            (int(record["seg_pixel_count"]), bool(record["point_unoccluded"]))
                        )

                jacobian_candidates.append((frame_index, key))

    # ---- 判据 4：雅可比二阶收敛 ----
    jacobian_ratios: list[float] = []
    if jacobian_candidates:
        picks = rng.choice(
            len(jacobian_candidates),
            size=min(JACOBIAN_SAMPLE_LIMIT, len(jacobian_candidates)),
            replace=False,
        )
        for pick in picks:
            frame_index, key = jacobian_candidates[int(pick)]
            record = frames[frame_index][key]
            extrinsic = extrinsics[frame_index]
            world = np.asarray(record["pos_3d"], dtype=np.float64)

            jacobian = projection_jacobian(
                world_xyz=world, intrinsic_cv=intrinsic, extrinsic_cv=extrinsic
            )
            base = project_world_to_pixel_subpixel(
                world_xyz=world, intrinsic_cv=intrinsic, extrinsic_cv=extrinsic
            )
            if jacobian is None or base is None:
                continue
            base_uv = np.asarray(base[:2], dtype=np.float64)

            direction = rng.normal(size=3)
            direction /= np.linalg.norm(direction)

            def residual(step: float) -> float | None:
                moved = project_world_to_pixel_subpixel(
                    world_xyz=world + step * direction,
                    intrinsic_cv=intrinsic,
                    extrinsic_cv=extrinsic,
                )
                if moved is None:
                    return None
                delta_2d = np.asarray(moved[:2], dtype=np.float64) - base_uv
                return float(np.linalg.norm(delta_2d - jacobian @ (step * direction)))

            coarse = residual(JACOBIAN_STEP)
            fine = residual(JACOBIAN_STEP / 2.0)
            if coarse is None or fine is None or coarse < 1e-11:
                continue
            jacobian_ratios.append(fine / coarse)

    # ---- 判据 5：静止物体零位移 ----
    # 「静止」定义为整个 episode 里 pos_3d 逐帧逐位不变的物体
    static_keys: list[str] = []
    max_static_flow = 0.0
    for key in flow_objects:
        positions = np.stack(
            [np.asarray(frame[key]["pos_3d"], dtype=np.float64) for frame in frames]
        )
        if not np.array_equal(positions, np.repeat(positions[:1], len(frames), axis=0)):
            continue
        static_keys.append(key)
        for frame in frames:
            flow = np.asarray(frame[key]["flow_2d_uv"], dtype=np.float64)
            if np.all(np.isfinite(flow)):
                max_static_flow = max(max_static_flow, float(np.max(np.abs(flow))))

    # ---- 判据 6：只在物体充分可见的帧上统计 ----
    visible_hits = 0
    visible_total = 0
    per_object_visible: dict[str, list[int]] = {}
    for key, samples in per_object_samples.items():
        pixel_counts = np.asarray([count for count, _ in samples], dtype=np.float64)
        threshold = float(np.percentile(pixel_counts, VISIBLE_PERCENTILE))
        selected = [flag for count, flag in samples if count >= threshold]
        if not selected:
            continue
        hits = sum(1 for flag in selected if flag)
        visible_hits += hits
        visible_total += len(selected)
        per_object_visible[key] = [hits, len(selected)]

    visible_ratio = (
        visible_hits / visible_total if visible_total > 0 else float("nan")
    )

    # ---- 汇总 ----
    actor_ratio = (
        unoccluded_hits["actor"] / unoccluded_total["actor"]
        if unoccluded_total["actor"] > 0
        else float("nan")
    )
    mean_jacobian_ratio = float(np.mean(jacobian_ratios)) if jacobian_ratios else float("nan")

    checks = {
        "1_roundtrip_world": {
            "value": max_world_error,
            "threshold": TOL_ROUNDTRIP_WORLD,
            "passed": max_world_error <= TOL_ROUNDTRIP_WORLD,
            "描述": "反投影闭环还原 3D 真值的最大绝对误差（米）",
        },
        "2_reprojection_pixel": {
            "value": max_reprojection_error,
            "threshold": TOL_REPROJECTION_PIXEL,
            "max_ulp": max_reprojection_ulp,
            "max_ulp_threshold": TOL_REPROJECTION_ULP,
            "passed": (
                max_reprojection_error <= TOL_REPROJECTION_PIXEL
                and max_reprojection_ulp <= TOL_REPROJECTION_ULP
            ),
            "描述": "正向∘反向恒等的最大像素误差（同时按坐标量级的 ulp 倍数判定）",
        },
        "3_pixel_convention": {
            "value": pixel_convention_mismatches,
            "threshold": 0,
            "passed": pixel_convention_mismatches == 0,
            "描述": "pos_2d_yx 与 [rint(v), rint(u)] 不一致的样本数",
        },
        "4_jacobian_second_order": {
            "value": mean_jacobian_ratio,
            "threshold": [
                JACOBIAN_RATIO_TARGET - JACOBIAN_RATIO_TOLERANCE,
                JACOBIAN_RATIO_TARGET + JACOBIAN_RATIO_TOLERANCE,
            ],
            "passed": bool(
                jacobian_ratios
                and abs(mean_jacobian_ratio - JACOBIAN_RATIO_TARGET)
                <= JACOBIAN_RATIO_TOLERANCE
            ),
            "sample_count": len(jacobian_ratios),
            "描述": "步长减半后残差比的均值，应趋近 0.25",
        },
        "5_static_zero_flow": {
            "value": max_static_flow,
            "threshold": TOL_STATIC_FLOW_PIXEL,
            "passed": extrinsic_is_constant and max_static_flow <= TOL_STATIC_FLOW_PIXEL,
            "extrinsic_is_constant": extrinsic_is_constant,
            "static_object_count": len(static_keys),
            "描述": "3D 位置全程不变的物体，其 2D 位移的最大绝对值",
        },
        "6_point_unoccluded_ratio": {
            "value": visible_ratio,
            "threshold": MIN_UNOCCLUDED_RATIO,
            "passed": bool(
                visible_total > 0 and visible_ratio >= MIN_UNOCCLUDED_RATIO
            ),
            "visible_frames": [visible_hits, visible_total],
            "per_object_visible": per_object_visible,
            # 下面这些是诊断量，不参与判定：全帧比例低说明场景里遮挡多，不代表投影错
            "all_frames_actor_ratio": actor_ratio,
            "all_frames_actor": [unoccluded_hits["actor"], unoccluded_total["actor"]],
            "all_frames_link": [unoccluded_hits["link"], unoccluded_total["link"]],
            "all_frames_tcp": [unoccluded_hits["tcp"], unoccluded_total["tcp"]],
            "描述": (
                "actor 在充分可见帧（分割像素数达本物体 p75）上投影点落在自身掩码内的比例；"
                "全帧比例与 link/tcp 仅作诊断，不设阈值"
            ),
        },
    }

    return {
        "label": label,
        "flow_schema_version": schema_version,
        "timestep_count": len(timestep_names),
        "object_count": len(flow_objects),
        "checked_samples": checked_samples,
        "static_object_count": len(static_keys),
        "checks": checks,
        "passed": all(item["passed"] for item in checks.values()),
    }


def verify_file(path: Path, episodes: Sequence[int] | None, seed: int) -> list[dict[str, Any]]:
    """对单个 h5 文件的若干 episode 跑验证。"""
    results: list[dict[str, Any]] = []
    with h5py.File(path, "r") as handle:
        if episodes is None:
            names = sorted(
                (name for name in handle.keys() if name.startswith("episode_")),
                key=lambda item: int(item.split("_")[1]),
            )
        else:
            names = [f"episode_{index}" for index in episodes]
        for name in names:
            if name not in handle:
                raise FlowVerificationError(f"{path}：缺少 {name}")
            rng = np.random.default_rng(seed)
            results.append(
                verify_episode(handle[name], f"{path.name}/{name}", rng)
            )
    return results


def _format_report(results: Sequence[dict[str, Any]]) -> str:
    lines: list[str] = []
    for item in results:
        status = "通过" if item["passed"] else "未通过"
        lines.append(
            f"[{status}] {item['label']}  "
            f"schema={item['flow_schema_version']}  "
            f"帧数={item['timestep_count']}  物体数={item['object_count']}  "
            f"有效样本={item['checked_samples']}"
        )
        for name, check in item["checks"].items():
            mark = "✓" if check["passed"] else "✗"
            lines.append(
                f"    {mark} 判据{name}: 实测={check['value']!r} 阈值={check['threshold']!r}"
                f"  —— {check['描述']}"
            )
    passed = sum(1 for item in results if item["passed"])
    lines.append(f"汇总：{passed}/{len(results)} 个 episode 六条判据全绿")
    return "\n".join(lines)


def _args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="验证 h5 里的 2D flow ground truth 与 3D 真值严格一一对应",
    )
    parser.add_argument(
        "--h5",
        nargs="+",
        required=True,
        help="待验证的 record_dataset_<任务>.h5，可传多个",
    )
    parser.add_argument(
        "--episode",
        type=int,
        default=0,
        help="要验证的 episode 序号（默认 %(default)s）",
    )
    parser.add_argument(
        "--all-episodes",
        action="store_true",
        help="验证文件里的全部 episode，忽略 --episode",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=20260806,
        help="判据 4 抽样与随机方向所用的种子（默认 %(default)s）",
    )
    parser.add_argument(
        "--json",
        dest="json_path",
        default=None,
        help="把结构化结果额外写到指定 JSON 文件",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    namespace = _args(argv)
    episodes = None if namespace.all_episodes else [namespace.episode]

    results: list[dict[str, Any]] = []
    try:
        for raw_path in namespace.h5:
            results.extend(verify_file(Path(raw_path), episodes, namespace.seed))
    except FlowVerificationError as exc:
        print(f"验证失败：{exc}", file=sys.stderr, flush=True)
        return 1

    print(_format_report(results), flush=True)

    if namespace.json_path:
        Path(namespace.json_path).write_text(
            json.dumps(results, ensure_ascii=False, indent=2, default=float) + "\n",
            encoding="utf-8",
        )

    return 0 if all(item["passed"] for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
