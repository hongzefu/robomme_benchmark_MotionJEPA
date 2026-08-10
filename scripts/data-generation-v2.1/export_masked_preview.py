#!/usr/bin/env python3
"""导出「原图 / 涂色区掩码 / 遮蔽结果」三列拼接网格，供人肉目视检查。

白名单涂对没有，最终只能靠眼睛判定——没有任何自动判据能替代「看一眼画面里该留的留住了、
该涂的涂掉了」。这个脚本就是那个落点：每个任务出一张网格图，行是整段 episode 上均匀抽的
若干帧，每行三列：

| 列 | 内容 | 看什么 |
|---|---|---|
| `front_rgb` | 原始渲染图 | 这一帧机械臂在哪、夹爪什么姿态 |
| `paint_mask` | 涂色区红色半透明叠在原图上 | 掩码边界准不准、有没有多涂/漏涂 |
| `front_rgb_masked` | h5 里的遮蔽图 | 最终结果，黑指尖是不是留住了 |

中列的掩码取 ``front_rgb != front_rgb_masked``。这是**近似而非精确**的口径：理论上某个机器人
像素本来就恰好等于涂色棕 ``(179, 107, 67)`` 时会被漏判，但机器人是灰白黑三色、逐位撞上这个
棕色的概率可以忽略；桌面木纹里确实有接近该棕的像素，但桌面根本不在涂色集里，不会造成误判。
真要精确掩码只能另开 h5 字段，不要试图从颜色反解（见 doc/h5_data_format.md 的「已知代价」）。

目视时要逐条核对的东西（**v2.1 口径，与 v2 逐条不同，别拿旧图对照**）：

1. **桌面**木纹原样保留——v2.1 取消了桌面涂色，桌面看起来应当与 ``front_rgb`` 一模一样；
2. **机械臂**从底座到手掌整根消失在棕色里，含腕部相机支架 ``camera_base_link`` /
   ``camera_link``，以及手掌上那几块黑色方块；
3. **夹爪指尖那一小块黑色**还在，白色指身必须已经被涂掉——这是判断像素级黑色豁免生效的
   最直接信号：画面里与机器人有关的东西**只剩这一处**。中列的红色掩码在指尖处应当有一个
   小缺口，那个缺口就是豁免出来的黑指尖；
4. **任务物体**（方块、按钮、目标标记等）全部保留原样；
5. **地面**顶部那条棋盘格横带保留原样；
6. **stick 任务**（RouteStick / PatternLock）里那根棍**也没了**——v2.1 对 panda_stick
   不做任何保留，棍与手掌同属 ``panda_hand`` 一个 link，连着一起涂掉。

图上不写中文：OpenCV 的 Hershey 字体渲染不了中文，会画成一堆问号。标注一律用 ASCII。
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Sequence

import h5py
import numpy as np

try:
    import cv2
except ImportError as exc:  # pragma: no cover - 环境问题应当直接暴露
    raise SystemExit(f"需要 opencv：{exc}")


REPO_ROOT = Path(__file__).resolve().parents[2]
# 与 v2 的 artifacts/masked-preview/ 分开落盘：v2 的旧预览图是 masked-rgb-v1 口径，
# 两套图长得完全不一样，混在一个目录里迟早会被拿错。
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "flow-viz" / "v21mask-preview"

# 单块图放大倍数。原图 256×256 太小，看不清指尖那几十个像素有没有留住。
SCALE = 2
# 标注条高度（像素）
LABEL_HEIGHT = 22
# 列间、行间的留白
GAP = 6
# 掩码叠加色（RGB）与叠加权重：红色够扎眼，0.7 的权重既盖得住又能透出下面的轮廓
MASK_OVERLAY_COLOR = (255, 40, 40)
MASK_OVERLAY_ALPHA = 0.70


def _timestep_indices(episode_group: h5py.Group) -> list[int]:
    indices: list[int] = []
    for name in episode_group.keys():
        if not name.startswith("timestep_"):
            continue
        suffix = name[len("timestep_") :]
        if suffix.isdigit():
            indices.append(int(suffix))
    return sorted(indices)


def _pick_frames(indices: Sequence[int], count: int) -> list[int]:
    """在整个 episode 上均匀抽 count 帧，保证首尾都在里面。"""
    if not indices:
        return []
    if len(indices) <= count:
        return list(indices)
    positions = np.linspace(0, len(indices) - 1, count).round().astype(int)
    picked: list[int] = []
    for position in positions:
        value = indices[int(position)]
        if value not in picked:
            picked.append(value)
    return picked


def _label(image: np.ndarray, text: str) -> np.ndarray:
    """在图片上方加一条 ASCII 标注。"""
    height, width = image.shape[:2]
    canvas = np.full((height + LABEL_HEIGHT, width, 3), 24, dtype=np.uint8)
    canvas[LABEL_HEIGHT:] = image
    cv2.putText(
        canvas,
        text[:56],
        (4, LABEL_HEIGHT - 7),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.42,
        (235, 235, 235),
        1,
        cv2.LINE_AA,
    )
    return canvas


def _to_bgr(rgb: np.ndarray) -> np.ndarray:
    scaled = cv2.resize(
        rgb, None, fx=SCALE, fy=SCALE, interpolation=cv2.INTER_NEAREST
    )
    return cv2.cvtColor(scaled, cv2.COLOR_RGB2BGR)


def _mask_overlay(rgb: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """把掩码区域按固定权重压成红色，掩码外一个像素都不动。"""
    overlay = rgb.copy()
    overlay[mask] = np.asarray(MASK_OVERLAY_COLOR, dtype=np.uint8)
    blended = (
        (1.0 - MASK_OVERLAY_ALPHA) * rgb.astype(np.float32)
        + MASK_OVERLAY_ALPHA * overlay.astype(np.float32)
    ).astype(np.uint8)
    return np.where(mask[..., None], blended, rgb)


def build_preview(
    h5_path: Path, episode: int, frames: int
) -> tuple[np.ndarray, dict[str, Any]]:
    """读一个 episode，拼出三列网格图，同时返回涂色口径摘要。"""
    with h5py.File(h5_path, "r") as handle:
        episode_name = f"episode_{episode}"
        if episode_name not in handle:
            raise KeyError(f"{h5_path.name} 里没有 {episode_name}")
        episode_group = handle[episode_name]

        indices = _timestep_indices(episode_group)
        picked = _pick_frames(indices, frames)
        if not picked:
            raise ValueError(f"{h5_path.name} 的 {episode_name} 一个 timestep 都没有")

        rows: list[np.ndarray] = []
        mask_pixels = 0
        mask_total = 0
        for index in picked:
            obs_group = episode_group[f"timestep_{index}"]["obs"]
            if "front_rgb_masked" not in obs_group:
                raise KeyError(
                    f"{h5_path.name} 的 timestep_{index} 没有 front_rgb_masked，"
                    "这份产物不是带 --masked-rgb 生成的"
                )
            original = np.asarray(obs_group["front_rgb"][()], dtype=np.uint8)
            masked = np.asarray(obs_group["front_rgb_masked"][()], dtype=np.uint8)
            paint_mask = np.any(original != masked, axis=-1)
            mask_pixels += int(paint_mask.sum())
            mask_total += int(paint_mask.size)

            panels = (
                _label(_to_bgr(original), f"t={index} front_rgb"),
                _label(
                    _to_bgr(_mask_overlay(original, paint_mask)),
                    f"t={index} paint_mask",
                ),
                _label(_to_bgr(masked), f"t={index} front_rgb_masked"),
            )
            spacer = np.full((panels[0].shape[0], GAP, 3), 24, dtype=np.uint8)
            rows.append(np.hstack([panels[0], spacer, panels[1], spacer, panels[2]]))

        width = max(row.shape[1] for row in rows)
        padded: list[np.ndarray] = []
        for row in rows:
            if row.shape[1] < width:
                pad = np.full((row.shape[0], width - row.shape[1], 3), 24, dtype=np.uint8)
                row = np.hstack([row, pad])
            padded.append(row)
            padded.append(np.full((GAP, width, 3), 24, dtype=np.uint8))
        grid = np.vstack(padded[:-1])

        summary = _read_summary(episode_group)
        summary.update(
            {
                "frame_count": len(indices),
                "shown_frames": len(picked),
                "mask_fraction": (mask_pixels / mask_total) if mask_total else 0.0,
            }
        )

    return grid, summary


def _read_summary(episode_group: h5py.Group) -> dict[str, Any]:
    """读出这个 episode 的涂色口径，供命令行打印核对。"""
    setup_group = episode_group.get("setup")
    if setup_group is None or "masked_rgb_painted" not in setup_group:
        return {}

    def _decode(value: Any) -> Any:
        return value.decode() if isinstance(value, bytes) else value

    painted = {
        key: _decode(setup_group["masked_rgb_painted"][key]["reason"][()])
        for key in setup_group["masked_rgb_painted"]
    }
    black_group = setup_group.get("masked_rgb_black_exempt")
    black_exempt = (
        {
            key: (
                _decode(black_group[key]["reason"][()]),
                _decode(black_group[key]["resolved_by"][()]),
            )
            for key in black_group
        }
        if black_group is not None
        else {}
    )
    threshold = setup_group.get("masked_rgb_black_luminance_max")
    return {
        "schema_version": _decode(setup_group["masked_rgb_schema_version"][()]),
        "paint_color": np.asarray(setup_group["masked_rgb_paint_color"][()]).tolist(),
        "black_luminance_max": int(threshold[()]) if threshold is not None else None,
        "painted_count": len(painted),
        "painted": sorted(painted),
        "black_exempt": black_exempt,
        "kept_count": len(setup_group["masked_rgb_kept"]),
    }


def _args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="导出 front_rgb / paint_mask / front_rgb_masked 三列拼接图供目视检查",
    )
    parser.add_argument("--h5", nargs="+", required=True, help="待检查的 h5 文件，可传多个")
    parser.add_argument("--episode", type=int, default=0, help="检查哪个 episode，默认 0")
    parser.add_argument("--frames", type=int, default=8, help="每个任务抽几帧，默认 8")
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help=f"图片输出目录，默认 {DEFAULT_OUTPUT_DIR}",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    namespace = _args(argv)
    output_dir = Path(namespace.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    failures = 0
    for raw in namespace.h5:
        h5_path = Path(raw).expanduser().resolve()
        try:
            grid, summary = build_preview(h5_path, namespace.episode, namespace.frames)
        except Exception as exc:
            print(f"✗ {h5_path.name}: {exc}", flush=True)
            failures += 1
            continue

        target = output_dir / f"{h5_path.stem}_ep{namespace.episode}_masked.png"
        if not cv2.imwrite(str(target), grid):
            print(f"✗ {h5_path.name}: 写图失败 {target}", flush=True)
            failures += 1
            continue
        black_exempt = summary.get("black_exempt", {})
        black_text = "、".join(
            f"{key}（{reason}/{how}）"
            for key, (reason, how) in sorted(black_exempt.items())
        )
        print(
            f"✓ {h5_path.name}[{summary.get('schema_version', '?')}]: "
            f"{summary.get('frame_count', '?')} 帧取 {summary.get('shown_frames', '?')} 帧，"
            f"涂色 {summary.get('painted_count', '?')} 个机器人 link、"
            f"掩码占比 {summary.get('mask_fraction', 0.0):.2%}，"
            f"黑色豁免 {black_text or '无（panda_stick 全涂）'}，"
            f"其余原样保留 {summary.get('kept_count', '?')} 个对象；"
            f"棕色 {summary.get('paint_color', '?')}、"
            f"黑判定阈值 {summary.get('black_luminance_max', '?')} → {target.name}",
            flush=True,
        )

    print(f"\n图片已写到 {output_dir}", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
