#!/usr/bin/env python3
"""导出 ``front_rgb`` 与 ``front_rgb_masked`` 的并排对照图，供人肉目视检查。

白名单涂对没有，最终只能靠眼睛判定——没有任何自动判据能替代「看一眼画面里该留的留住了、
该涂的涂掉了」。这个脚本就是那个落点：每个任务出一张网格图，行是抽样的若干帧，
每行左边原图、右边遮蔽图。

目视时要逐条核对的东西：

1. **桌面**变成完全均匀的一块棕色，木纹与阴影全没了；
2. **机械臂臂杆**（含腕部相机支架 ``camera_base_link`` / ``camera_link``）整根消失在棕色里；
3. **夹爪两根手指**还在，颜色正常——这是判断白名单没写反的最直接信号；
4. **任务物体**（方块、按钮、目标标记等）全部保留原样；
5. **地面**顶部那条棋盘格横带保留原样（这是已确认接受的口径，不是 bug）；
6. **stick 任务**（RouteStick / PatternLock）里那根棍还在——它挂在 ``panda_hand`` 上，
   连着手掌一起保留。

图上不写中文：OpenCV 的 Hershey 字体渲染不了中文，会画成一堆问号。标注一律用 ASCII。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Sequence

import h5py
import numpy as np

try:
    import cv2
except ImportError as exc:  # pragma: no cover - 环境问题应当直接暴露
    raise SystemExit(f"需要 opencv：{exc}")


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "masked-preview"

# 单块图放大倍数。原图 256×256 太小，看不清手指有没有留住。
SCALE = 2
# 标注条高度（像素）
LABEL_HEIGHT = 22
# 两列之间、两行之间的留白
GAP = 6


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
        text[:48],
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


def build_preview(h5_path: Path, episode: int, frames: int) -> tuple[np.ndarray, dict[str, Any]]:
    """读一个 episode，拼出并排对照网格图，同时返回涂色口径摘要。"""
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
        for index in picked:
            obs_group = episode_group[f"timestep_{index}"]["obs"]
            if "front_rgb_masked" not in obs_group:
                raise KeyError(
                    f"{h5_path.name} 的 timestep_{index} 没有 front_rgb_masked，"
                    "这份产物不是带 --masked-rgb 生成的"
                )
            original = _to_bgr(np.asarray(obs_group["front_rgb"][()]))
            masked = _to_bgr(np.asarray(obs_group["front_rgb_masked"][()]))
            left = _label(original, f"t={index} front_rgb")
            right = _label(masked, f"t={index} front_rgb_masked")
            spacer = np.full((left.shape[0], GAP, 3), 24, dtype=np.uint8)
            rows.append(np.hstack([left, spacer, right]))

        width = max(row.shape[1] for row in rows)
        padded = []
        for row in rows:
            if row.shape[1] < width:
                pad = np.full((row.shape[0], width - row.shape[1], 3), 24, dtype=np.uint8)
                row = np.hstack([row, pad])
            padded.append(row)
            padded.append(np.full((GAP, width, 3), 24, dtype=np.uint8))
        grid = np.vstack(padded[:-1])

        summary = _read_summary(episode_group)

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
    kept_group = setup_group["masked_rgb_kept"]
    kept = {
        key: (
            _decode(kept_group[key]["reason"][()]),
            _decode(kept_group[key]["resolved_by"][()]),
        )
        for key in kept_group
    }
    preserved = {
        key: value for key, value in kept.items() if value[0] != "not_whitelisted"
    }
    return {
        "paint_color": np.asarray(setup_group["masked_rgb_paint_color"][()]).tolist(),
        "painted_count": len(painted),
        "painted": sorted(painted),
        "preserved": preserved,
        "kept_other_count": len(kept) - len(preserved),
    }


def _args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="导出 front_rgb 与 front_rgb_masked 的并排对照图供目视检查",
    )
    parser.add_argument("--h5", nargs="+", required=True, help="待检查的 h5 文件，可传多个")
    parser.add_argument("--episode", type=int, default=0, help="检查哪个 episode，默认 0")
    parser.add_argument("--frames", type=int, default=4, help="每个任务抽几帧，默认 4")
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
        cv2.imwrite(str(target), grid)
        preserved = summary.get("preserved", {})
        preserved_text = "、".join(
            f"{key}（{reason}/{how}）" for key, (reason, how) in sorted(preserved.items())
        )
        print(
            f"✓ {h5_path.name}: 涂色 {summary.get('painted_count', '?')} 个对象，"
            f"保留部位 {preserved_text or '无'}，"
            f"其余原样保留 {summary.get('kept_other_count', '?')} 个；"
            f"棕色 {summary.get('paint_color', '?')} → {target.name}",
            flush=True,
        )

    print(f"\n图片已写到 {output_dir}", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
