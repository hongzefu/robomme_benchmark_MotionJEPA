#!/usr/bin/env python3
"""把 h5 里的 2D flow ground truth 画成对照视频，供人眼确认箭头确实贴在物体上。

每一帧的构成：

- **主画面**：底图用最近邻放大 3 倍到 768×768（保住像素栅格，不糊掉），叠加每个物体的位置点与
  位移箭头。底图默认用 ``front_rgb_cv_arm_removed``：从完整 episode 的原始 RGB-D 以通用 CV
  规则保护任务物体并删除机械臂与夹爪非黑色部分，普通双指夹爪只保留黑色指尖、stick 不豁免，
  再用时序背景补回被挡住的桌面；无需 h5 预先带 v3.1 字段。
- **右侧图例**：物体原名 + 色块 + 当前帧的 (Δu, Δv) 数值；
- **底部状态条**：帧号、是否处于 demo 相位、有效位移计数，以及醒目的
  ``delta = 1 frame (next recorded step)`` 标注——位移的时间基准只有一帧，这一点必须一眼看见。

点的画法区分遮挡：``point_unoccluded=True``（投影点所在像素的分割 id 恰为该物体自身）画实心点，
被遮挡则画空心圈。``in_frame=False`` 的物体画在最近的画幅边缘并标 ``off``。位移是 NaN 的（末帧、
深度非正、或两帧之间是断点）不画箭头。

⚠ 视频内的文字一律用 ASCII：OpenCV 的 ``putText`` 只带 Hershey 字体，渲染中文会变成方框。
代码注释、脚本输出与汇报仍然全部是中文。
"""

from __future__ import annotations

import argparse
import colorsys
import sys
import zlib
from pathlib import Path
from typing import Any, Sequence

import cv2
import h5py
import numpy as np

from cv_arm_removal import remove_robot_arm_sequence


DEFAULT_OUTPUT_DIR = Path("artifacts/flow-viz")
CV_ARM_REMOVED = "front_rgb_cv_arm_removed"
UPSCALE = 3  # 256 -> 768
LEGEND_WIDTH = 330
STATUS_HEIGHT = 64
FONT = cv2.FONT_HERSHEY_SIMPLEX
GOLDEN_RATIO = 0.6180339887498948


class ReplayError(RuntimeError):
    """h5 缺少 flow 内容或结构不符合预期。"""


def _text(dataset: Any) -> str:
    value = dataset[()]
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def _timestep_names(episode_group: h5py.Group) -> list[str]:
    named: list[tuple[int, str]] = []
    for name in episode_group.keys():
        if name.startswith("timestep_"):
            suffix = name[len("timestep_") :]
            if suffix.isdigit():
                named.append((int(suffix), name))
    named.sort()
    return [name for _, name in named]


def color_for(name: str) -> tuple[int, int, int]:
    """按物体原名分配固定颜色，返回 BGR。

    沿用 RecordWrapper 里的黄金比例配色思路：把名字的 CRC32 映射进 [0, 1) 再乘黄金比例步长，
    让相近的名字也能落到分得开的色相上。用 CRC32 而不是内置 hash，是因为后者带进程级随机化，
    跨次运行会变色。种子取 original_name 而不是带 seg_id 的 key，这样同一个物体在不同任务、
    不同 episode 里颜色一致。
    """
    seed = zlib.crc32(name.encode("utf-8")) & 0xFFFFFFFF
    hue = (seed * GOLDEN_RATIO) % 1.0
    saturation = 0.70 + 0.25 * ((seed % 7) / 6.0)
    value = 0.78 + 0.17 * (((seed // 7) % 5) / 4.0)
    red, green, blue = colorsys.hsv_to_rgb(hue, saturation, value)
    return (int(blue * 255), int(green * 255), int(red * 255))


def _read_flow_objects(setup_group: h5py.Group) -> dict[str, dict[str, Any]]:
    objects_group = setup_group.get("flow_objects")
    if not isinstance(objects_group, h5py.Group):
        raise ReplayError("setup 下缺少 flow_objects，该 h5 没有写入 flow")
    result: dict[str, dict[str, Any]] = {}
    for key in sorted(objects_group.keys()):
        entry = objects_group[key]
        result[key] = {
            "original_name": _text(entry["original_name"]),
            "seg_id": int(entry["seg_id"][()]),
            "kind": _text(entry["kind"]),
        }
    return result


def _draw_marker(
    canvas: np.ndarray,
    center: tuple[int, int],
    color: tuple[int, int, int],
    unoccluded: bool,
) -> None:
    """未被遮挡画实心点，被遮挡画空心圈。"""
    if unoccluded:
        cv2.circle(canvas, center, 5, color, -1, lineType=cv2.LINE_AA)
        cv2.circle(canvas, center, 5, (20, 20, 20), 1, lineType=cv2.LINE_AA)
    else:
        cv2.circle(canvas, center, 6, color, 2, lineType=cv2.LINE_AA)


def _render_frame(
    rgb: np.ndarray,
    flow_records: dict[str, np.ndarray],
    flow_objects: dict[str, dict[str, Any]],
    frame_index: int,
    total_frames: int,
    is_video_demo: bool,
    arrow_scale: float,
) -> np.ndarray:
    height, width = rgb.shape[:2]
    canvas = cv2.resize(
        cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR),
        (width * UPSCALE, height * UPSCALE),
        interpolation=cv2.INTER_NEAREST,
    )
    canvas_height, canvas_width = canvas.shape[:2]

    legend = np.full((canvas_height, LEGEND_WIDTH, 3), 28, dtype=np.uint8)
    cv2.putText(
        legend, "objects (name / d_uv)", (12, 26), FONT, 0.5, (235, 235, 235), 1, cv2.LINE_AA
    )

    valid_flow_count = 0
    row_y = 52
    for key in flow_objects:
        record = flow_records[key]
        info = flow_objects[key]
        color = color_for(info["original_name"])

        uv = np.asarray(record["pos_2d_uv"], dtype=np.float64)
        flow_uv = np.asarray(record["flow_2d_uv"], dtype=np.float64)
        in_frame = bool(record["in_frame"])
        unoccluded = bool(record["point_unoccluded"])
        has_flow = bool(np.all(np.isfinite(flow_uv)))

        if np.all(np.isfinite(uv)):
            # 出画的物体钉在最近的边缘上，让它仍然可见
            display_u = float(np.clip(uv[0], 0.0, width - 1.0))
            display_v = float(np.clip(uv[1], 0.0, height - 1.0))
            center = (int(round(display_u * UPSCALE)), int(round(display_v * UPSCALE)))
            _draw_marker(canvas, center, color, unoccluded and in_frame)

            if not in_frame:
                cv2.putText(
                    canvas, "off", (center[0] + 8, center[1] - 8), FONT, 0.42,
                    color, 1, cv2.LINE_AA,
                )

            if has_flow:
                valid_flow_count += 1
                tip = (
                    int(round((uv[0] + flow_uv[0] * arrow_scale) * UPSCALE)),
                    int(round((uv[1] + flow_uv[1] * arrow_scale) * UPSCALE)),
                )
                if tip != center:
                    cv2.arrowedLine(
                        canvas, center, tip, color, 2, cv2.LINE_AA, tipLength=0.35
                    )

        # 图例一行：色块 + 名字 + 位移数值
        cv2.rectangle(legend, (12, row_y - 10), (28, row_y + 4), color, -1)
        label = info["original_name"]
        if len(label) > 20:
            label = label[:19] + "~"
        cv2.putText(legend, label, (36, row_y), FONT, 0.44, (225, 225, 225), 1, cv2.LINE_AA)
        flow_text = (
            f"({flow_uv[0]:+.2f},{flow_uv[1]:+.2f})" if has_flow else "(nan)"
        )
        cv2.putText(
            legend, flow_text, (36, row_y + 16), FONT, 0.40,
            (170, 200, 170) if has_flow else (120, 120, 120), 1, cv2.LINE_AA,
        )
        row_y += 40
        if row_y > canvas_height - 30:
            break

    body = np.hstack([canvas, legend])
    status = np.full((STATUS_HEIGHT, body.shape[1], 3), 18, dtype=np.uint8)
    cv2.putText(
        status,
        f"frame {frame_index + 1}/{total_frames}   "
        f"demo={'yes' if is_video_demo else 'no'}   "
        f"valid flow {valid_flow_count}/{len(flow_objects)}   "
        f"arrow x{arrow_scale:g}",
        (14, 24),
        FONT,
        0.5,
        (225, 225, 225),
        1,
        cv2.LINE_AA,
    )
    cv2.putText(
        status,
        "delta = 1 frame (next recorded step)",
        (14, 48),
        FONT,
        0.56,
        (90, 220, 255),
        1,
        cv2.LINE_AA,
    )
    return np.vstack([body, status])


def render_episode(
    h5_path: Path,
    episode: int,
    output_path: Path,
    arrow_scale: float,
    fps: int,
    base_image: str = CV_ARM_REMOVED,
) -> dict[str, Any]:
    """渲染单个 episode 的 flow 对照视频，返回统计信息。

    ``front_rgb_cv_arm_removed`` 会在内存中对整段 RGB-D 运行一次纯 CV 去臂；它只改 arm mask
    命中的像素，桌面其余像素保持原图。``front_rgb`` 与已落盘的 ``front_rgb_masked`` 仍保留为
    对照选项。
    """
    import imageio

    with h5py.File(h5_path, "r") as handle:
        episode_name = f"episode_{episode}"
        if episode_name not in handle:
            raise ReplayError(f"{h5_path}：缺少 {episode_name}")
        episode_group = handle[episode_name]

        setup_group = episode_group.get("setup")
        if not isinstance(setup_group, h5py.Group):
            raise ReplayError(f"{h5_path}/{episode_name}：缺少 setup")
        flow_objects = _read_flow_objects(setup_group)

        timestep_names = _timestep_names(episode_group)
        if not timestep_names:
            raise ReplayError(f"{h5_path}/{episode_name}：没有 timestep")

        cv_frames: np.ndarray | None = None
        cv_stats: dict[str, Any] | None = None
        if base_image == CV_ARM_REMOVED:
            rgb_frames: list[np.ndarray] = []
            depth_frames: list[np.ndarray] = []
            for name in timestep_names:
                obs_group = episode_group[name]["obs"]
                for required in ("front_rgb", "front_depth"):
                    if required not in obs_group:
                        raise ReplayError(
                            f"{h5_path}/{episode_name}/{name}：obs 下没有 {required}，"
                            "无法离线做纯 CV 去臂"
                        )
                rgb_frames.append(np.asarray(obs_group["front_rgb"][()], dtype=np.uint8))
                depth_frames.append(np.asarray(obs_group["front_depth"][()]))
            removal = remove_robot_arm_sequence(
                np.stack(rgb_frames, axis=0), np.stack(depth_frames, axis=0)
            )
            cv_frames = np.asarray(removal.frames, dtype=np.uint8)
            cv_stats = dict(removal.stats)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        writer = imageio.get_writer(str(output_path), fps=fps, macro_block_size=1)
        try:
            for index, name in enumerate(timestep_names):
                step_group = episode_group[name]
                flow_group = step_group.get("flow")
                if not isinstance(flow_group, h5py.Group):
                    raise ReplayError(f"{h5_path}/{episode_name}/{name}：缺少 flow")
                obs_group = step_group["obs"]
                if base_image != CV_ARM_REMOVED and base_image not in obs_group:
                    raise ReplayError(
                        f"{h5_path}/{episode_name}/{name}：obs 下没有 {base_image}"
                        + (
                            "，这份产物不是带 --masked-rgb 生成的"
                            if base_image == "front_rgb_masked"
                            else ""
                        )
                    )
                rgb = (
                    cv_frames[index]
                    if cv_frames is not None
                    else np.asarray(obs_group[base_image][()], dtype=np.uint8)
                )
                records = {key: flow_group[key][()] for key in flow_objects}
                is_video_demo = bool(step_group["info"]["is_video_demo"][()])

                frame = _render_frame(
                    rgb,
                    records,
                    flow_objects,
                    index,
                    len(timestep_names),
                    is_video_demo,
                    arrow_scale,
                )
                writer.append_data(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        finally:
            writer.close()

    return {
        "h5": str(h5_path),
        "episode": episode,
        "output": str(output_path),
        "frame_count": len(timestep_names),
        "object_count": len(flow_objects),
        "cv_stats": cv_stats,
    }


def _args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="把 h5 里的 2D flow ground truth 画成带箭头的对照视频",
    )
    parser.add_argument(
        "--h5",
        nargs="+",
        required=True,
        help="record_dataset_<任务>.h5，可传多个",
    )
    parser.add_argument("--episode", type=int, default=0, help="episode 序号（默认 %(default)s）")
    parser.add_argument(
        "--arrow-scale",
        type=float,
        default=5.0,
        help="位移箭头的放大倍数；帧间位移常只有 1~3 像素，不放大看不见（默认 %(default)s）",
    )
    parser.add_argument("--fps", type=int, default=30, help="输出帧率（默认 %(default)s）")
    parser.add_argument(
        "--base-image",
        choices=("front_rgb", "front_rgb_masked", CV_ARM_REMOVED),
        default=CV_ARM_REMOVED,
        help="底图；默认从原始 RGB-D 在线生成保留桌面的纯 CV 去臂图（%(default)s）",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="视频输出目录（默认 %(default)s）",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    namespace = _args(argv)
    output_dir = Path(namespace.output_dir).expanduser()

    results: list[dict[str, Any]] = []
    for raw_path in namespace.h5:
        h5_path = Path(raw_path)
        task = h5_path.stem.replace("record_dataset_", "")
        output_path = output_dir / f"{task}_ep{namespace.episode}.mp4"
        try:
            result = render_episode(
                h5_path,
                namespace.episode,
                output_path,
                namespace.arrow_scale,
                namespace.fps,
                namespace.base_image,
            )
        except ReplayError as exc:
            print(f"跳过 {h5_path.name}：{exc}", file=sys.stderr, flush=True)
            continue
        results.append(result)
        print(
            f"已生成 {output_path}（{result['frame_count']} 帧，"
            f"{result['object_count']} 个物体）",
            flush=True,
        )

    print(f"全部完成：共产出 {len(results)} 个视频", flush=True)
    return 0 if results else 1


if __name__ == "__main__":
    raise SystemExit(main())
