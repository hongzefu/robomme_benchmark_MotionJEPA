#!/usr/bin/env python3
"""重要对拍①：关键帧集合、原分辨率无损 PNG 与目视图版（测试侧，产品代码不导入）。

方案 4.1 的口径：

* ①.0 只对 ③ 已通过的格执行；③ 未通过的格记「未验证」，不做目视。
* ①.1 关键帧取首末帧、`is_subgoal_boundary`、演示切换（`is_video_demo`）、
  完成／失败标志变化（`is_completed`）、以及 ② 捕获的物体事件所在步；三路取并集，
  每个边界保留前一帧、本帧、后一帧；越界明确标记。不假设原版存在 `is_keyframe` 字段。
  初态用观察器捕获的 `reset` 返回观测，**不额外渲染**，并标注它不对应任何 HDF5 帧。
* ①.3 从原始 RGB 数组（正面与腕部均为 256×256×3）导出**原分辨率无损 PNG**；
  图版把正面与腕部分别排成 A／B／C 原图与差分图，标注任务、难度、seed、事件、
  步数与记录编号。**生成图版不代表已经目视**——目视记录另存，且绑定图片散列。
* ①.4 任何像素差异仍交 ③ 处理，不能以「看不出来」认定 HDF5 内容一致。

图版与原图留 `artifacts/`（不入 Git）；每帧内容 SHA-256 与像素差异统计入 Git。
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
import zlib
from pathlib import Path
from typing import Any, Sequence

import h5py
import numpy as np
from PIL import Image, ImageDraw

CAMERAS = ("front_rgb", "wrist_rgb")
LABEL_HEIGHT = 18
PADDING = 4
# 图版标注含中文（关键帧入选原因），PIL 默认位图字体渲染不出中文，找一个 CJK 字体
_CJK_FONT_CANDIDATES = (
    "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
)


def _font() -> Any:
    from PIL import ImageFont

    for path in _CJK_FONT_CANDIDATES:
        if Path(path).is_file():
            try:
                return ImageFont.truetype(path, 12)
            except OSError:
                continue
    return ImageFont.load_default()


_FONT = None


def _episode_group(handle: h5py.File) -> tuple[str, h5py.Group]:
    names = [name for name in handle.keys() if name.startswith("episode_")]
    if len(names) != 1:
        raise RuntimeError(f"期望恰好一个 episode，实际 {names}")
    return names[0], handle[names[0]]


def _timesteps(group: h5py.Group) -> list[int]:
    indices = [int(name.split("_")[1]) for name in group.keys() if name.startswith("timestep_")]
    return sorted(indices)


def keyframe_indices(h5_path: Path, extra: Sequence[int] = ()) -> dict[str, Any]:
    """按 ①.1 的规则求一条轨迹的关键帧集合（含每个边界的前后帧）。"""
    reasons: dict[int, list[str]] = {}

    def mark(index: int, reason: str) -> None:
        reasons.setdefault(index, []).append(reason)

    with h5py.File(h5_path, "r") as handle:
        _name, group = _episode_group(handle)
        indices = _timesteps(group)
        if not indices:
            raise RuntimeError(f"{h5_path}: 没有 timestep")
        mark(indices[0], "首帧")
        mark(indices[-1], "末帧")
        previous: dict[str, Any] = {}
        for index in indices:
            info = group[f"timestep_{index}"]["info"]
            if bool(info["is_subgoal_boundary"][()]):
                mark(index, "is_subgoal_boundary")
            for field in ("is_video_demo", "is_completed"):
                value = bool(info[field][()])
                if field in previous and previous[field] != value:
                    mark(index, f"{field} 变化 {previous[field]}→{value}")
                previous[field] = value
            for field in ("simple_subgoal", "grounded_subgoal"):
                value = info[field].asstr()[()] if info[field].shape == () else None
                if field in previous and previous[field] != value:
                    mark(index, f"{field} 变化")
                previous[field] = value
    for index in extra:
        if index in set(indices):
            mark(int(index), "② 事件所在步")

    selected: dict[int, list[str]] = {}
    out_of_range: list[int] = []
    for index, why in reasons.items():
        selected.setdefault(index, []).extend(why)
        for neighbour in (index - 1, index + 1):
            if neighbour in set(indices):
                selected.setdefault(neighbour, []).append(f"边界 {index} 的相邻帧")
            else:
                out_of_range.append(neighbour)
    return {
        "timestep_count": len(indices),
        "keyframes": {index: sorted(set(why)) for index, why in sorted(selected.items())},
        "out_of_range_neighbours": sorted(set(out_of_range)),
    }


def _frame(h5_path: Path, index: int, camera: str) -> np.ndarray:
    with h5py.File(h5_path, "r") as handle:
        _name, group = _episode_group(handle)
        return np.array(group[f"timestep_{index}"]["obs"][camera][()])


def _label(width: int, text: str) -> Image.Image:
    global _FONT
    if _FONT is None:
        _FONT = _font()
    strip = Image.new("RGB", (width, LABEL_HEIGHT), (16, 16, 16))
    draw = ImageDraw.Draw(strip)
    # 按实际渲染宽度截断，中文与 ASCII 的字宽不同，不能按字符数估
    while text and draw.textlength(text, font=_FONT) > width - 4:
        text = text[:-1]
    draw.text((2, 2), text, fill=(230, 230, 230), font=_FONT)
    return strip


def _difference(left: np.ndarray, right: np.ndarray) -> tuple[np.ndarray, dict[str, Any]]:
    """差分图放大到可见范围；统计量按原值记录，不用来代替 ③ 的判定。"""
    delta = np.abs(left.astype(np.int16) - right.astype(np.int16)).astype(np.uint8)
    stats = {
        "max_abs": int(delta.max()),
        "nonzero_pixels": int((delta.sum(axis=2) > 0).sum()),
        "total_pixels": int(delta.shape[0] * delta.shape[1]),
    }
    visible = np.clip(delta.astype(np.int16) * 8, 0, 255).astype(np.uint8)
    return visible, stats


def build_montage(
    frames: dict[str, Path],
    index: int,
    title: str,
    target: Path,
    initial_rgb: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """一帧一张图版：两行（正面／腕部）× 若干列（A／B／C 原图 + 差分图）。

    原图逐像素放进图版，不缩放、不重采样；只有差分图为了肉眼可见做了乘 8 的放大，
    其统计量按原值记录。
    """
    labels = list(frames)
    columns: list[list[tuple[str, np.ndarray]]] = []
    stats: dict[str, Any] = {"frame_sha256": {}, "difference": {}}
    for camera in CAMERAS:
        row: list[tuple[str, np.ndarray]] = []
        if initial_rgb is None:
            arrays = {label: _frame(path, index, camera) for label, path in frames.items()}
        else:
            arrays = {}
            for label in labels:
                stored = initial_rgb[label][camera]
                raw = zlib.decompress(base64.b64decode(stored["zlib_base64"]))
                arrays[label] = np.frombuffer(raw, dtype=np.dtype(stored["dtype"])).reshape(stored["shape"])
        for label in labels:
            array = arrays[label]
            stats["frame_sha256"][f"{camera}.{label}"] = hashlib.sha256(array.tobytes()).hexdigest()
            row.append((f"{label} {camera}", array))
        reference = labels[0]
        for label in labels[1:]:
            visible, detail = _difference(arrays[reference], arrays[label])
            stats["difference"][f"{camera}.{reference}-{label}"] = detail
            row.append((f"diff {reference}-{label} (×8)", visible))
        columns.append(row)

    cell_width = max(array.shape[1] for row in columns for _label_text, array in row)
    cell_height = max(array.shape[0] for row in columns for _label_text, array in row)
    per_row = max(len(row) for row in columns)
    width = per_row * (cell_width + PADDING) + PADDING
    height = len(columns) * (cell_height + LABEL_HEIGHT + PADDING) + LABEL_HEIGHT + PADDING
    canvas = Image.new("RGB", (width, height), (32, 32, 32))
    canvas.paste(_label(width, title), (0, 0))
    for row_index, row in enumerate(columns):
        top = LABEL_HEIGHT + PADDING + row_index * (cell_height + LABEL_HEIGHT + PADDING)
        for column_index, (text, array) in enumerate(row):
            left = PADDING + column_index * (cell_width + PADDING)
            canvas.paste(_label(cell_width, text), (left, top))
            canvas.paste(Image.fromarray(array), (left, top + LABEL_HEIGHT))
    target.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(target, format="PNG", compress_level=6)
    stats["montage"] = str(target)
    stats["montage_sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
    return stats


def event_record_indices(evidence: dict[str, Any]) -> dict[str, Any]:
    """按 wrapper 实际追加记录的位置映射事件，绝不以环境步数猜测 HDF5 编号。"""
    if "recordings" not in evidence:
        raise ValueError("缺少环境步到 HDF5 的记录映射，必须重新采集观察器证据")
    indices = set()
    unmapped = []
    for record in evidence["recordings"]:
        for event in evidence["events"][record["event_begin"]:record["event_end"]]:
            timing = event.get("timing", {})
            if not all(key in timing for key in ("start_step", "end_step", "cur_step")):
                continue
            start, end, current = (timing[key] for key in ("start_step", "end_step", "cur_step"))
            if current not in (start, end, (start + end) // 2):
                continue
            if record["record_begin"] == record["record_end"]:
                unmapped.append({"event": event["name"], "env_step": current, "reason": "原 wrapper 本步未记录"})
            else:
                indices.update(range(record["record_begin"], record["record_end"]))
    return {"indices": sorted(indices), "unrecorded_events": unmapped}


def export_cell(
    cell: str,
    case: dict[str, Any],
    frames: dict[str, Path],
    output_root: Path,
    limit: int | None = None,
    evidence_paths: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """导出一格的关键帧图版；三路取并集，越界邻帧明确标记。"""
    union: dict[int, list[str]] = {}
    per_path: dict[str, Any] = {}
    event_mapping = {}
    for label, path in frames.items():
        events = event_record_indices(evidence_paths[label]) if evidence_paths is not None else {"indices": []}
        event_mapping[label] = events
        detail = keyframe_indices(path, extra=events["indices"])
        per_path[label] = detail
        for index, why in detail["keyframes"].items():
            union.setdefault(int(index), []).extend(f"{label}:{item}" for item in why)

    selected = sorted(union)
    if limit is not None and len(selected) > limit:
        # 只在图版数量上取样时才截断，并如实记录未出图的关键帧
        step = max(1, len(selected) // limit)
        sampled = selected[::step][:limit]
    else:
        sampled = selected

    montages: dict[str, Any] = {}
    if evidence_paths is not None:
        initial = {label: evidence["initial_obs"]["rgb"] for label, evidence in evidence_paths.items()}
        montages["reset"] = build_montage(frames, -1, f"{cell} | 原 reset 返回初态（无 HDF5 帧号）",
            output_root / cell / "reset.png", initial_rgb=initial)
    for index in sampled:
        title = (
            f"{cell} | {case.get('task')} {case.get('difficulty')} seed={case.get('seed')} "
            f"| timestep_{index} | {'; '.join(sorted(set(union[index])))}"
        )
        montages[str(index)] = build_montage(
            frames, index, title, output_root / cell / f"timestep_{index:04d}.png"
        )
    return {
        "cell": cell,
        "case": case,
        "per_path_keyframes": {label: detail for label, detail in per_path.items()},
        "union_keyframe_count": len(selected),
        "union_keyframes": selected,
        "rendered_keyframes": sampled,
        "not_rendered": sorted(set(selected) - set(sampled)),
        "montages": montages,
        "event_record_mapping": event_mapping,
        "initial_observation_note": (
            "初态用观察器捕获的 reset 返回观测，不额外渲染；它在 HDF5 中没有对应帧，"
            "观察器从版本 2 起另存原始 RGB，并在 reset.png 中逐像素展示"
        ),
    }


def _main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="① 关键帧导出与目视图版")
    parser.add_argument("--run-root", required=True)
    parser.add_argument("--cases", required=True)
    parser.add_argument("--result", required=True, help="pack 出来的 result.json，用于只挑 ③ 已通过的格")
    parser.add_argument("--output", required=True, help="图版落点（artifacts/，不入 Git）")
    parser.add_argument("--index", required=True, help="关键帧索引与散列的落点（入 Git）")
    parser.add_argument("--evidence-root", default=None, help="本轮观察器证据：用于事件记录映射与 reset 原图")
    parser.add_argument(
        "--limit", type=int, default=0, help="每格最多出多少张图版；<=0 表示全部关键帧都出图"
    )
    args = parser.parse_args(argv)

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from tests._shared.native_sampling_parity import _episode_dir, _single_h5, load_evidence

    run_root = Path(args.run_root).resolve()
    cases = {case["cell"]: case for case in json.loads(Path(args.cases).read_text(encoding="utf-8"))["cases"]}
    result = json.loads(Path(args.result).read_text(encoding="utf-8"))

    index_payload: dict[str, Any] = {"run": run_root.name, "cells": {}}
    for cell, item in result["cells"].items():
        if item["status"] != "通过":
            index_payload["cells"][cell] = {"status": "未验证", "reason": f"③ 未通过：{item['status']}"}
            continue
        frames: dict[str, Path] = {}
        for label in ("A1", "B", "C"):
            path = _single_h5(_episode_dir(run_root, cell, label))
            if path is not None:
                frames[label] = path
        if len(frames) != 3:
            index_payload["cells"][cell] = {"status": "未验证", "reason": "三路 HDF5 不齐"}
            continue
        evidence_paths = None
        if args.evidence_root:
            case = cases[cell]
            evidence_paths = {label: load_evidence(Path(args.evidence_root) / label / f"{case['task']}_seed{case['seed']}", case["difficulty"])
                              for label in frames}
        index_payload["cells"][cell] = export_cell(
            cell, cases[cell], frames, Path(args.output), args.limit if args.limit > 0 else None, evidence_paths=evidence_paths)
        index_payload["cells"][cell]["status"] = "待目视"
        print(
            f"{cell}: 关键帧 {index_payload['cells'][cell]['union_keyframe_count']} 帧，"
            f"出图 {len(index_payload['cells'][cell]['rendered_keyframes'])} 张",
            flush=True,
        )

    target = Path(args.index)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(index_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"index": str(target), "cells": len(index_payload["cells"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
