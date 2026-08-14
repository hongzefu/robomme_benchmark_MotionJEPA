#!/usr/bin/env python3
"""模式②专用实测入口：读 sidecar + GT，输出 pixel 与 grid 双口径指标。

## 为什么单独一步

mask 生产（`make_mask.py`）全程不看 GT，两种数据源零分叉；GT 量化在这里独立完成。
本入口**不重跑推理链**——直接读 sidecar 里已落盘的 `arm_mask_px`（像素 mask）与
`arm_cell_counts`（阈值无关的格计数），因此不存在「两处各复刻一遍像素链路」的口径
漂移风险，也使得**换 K 重评估不必重跑 mask**。

## 两个口径，判读规则完全不同

### 像素口径 —— 刚性红线在此

**不得把物体判错成 robot arm，「判错」以 GT 为准**：整段每一帧被标成臂的像素，逐个
查它在 `obs/front_camera_segmentation` 里的真身，真身是「物体」的像素数累加必须恒为
0（`false_object_pixels`）。`enforce_no_false_object` 逐 episode 校验，非 0 即以非零
退出码结束，**刻意不提供豁免开关**。

口径偏保守的两处保障：GT 侧 setup 两张表认不出的 seg id 一律兜底归物体（运行中动态
创建的目标/路径标记物），单独由 `uncovered` 计数、不许静默；判臂的定义使标定集上误标
物体恒为 0 是恒等式（见 `color_model` 模块说明）。

### 网格口径 —— ⚠ 刚性红线在此**不适用**

整格涂红必然覆盖臂边界格里的物体/背景像素，「不得误标物体」在网格口径下必然击穿、
也不该成立。因此本入口**只对像素口径调用闸门**，网格口径下 GT 全程只当尺子做量化
记录。不要拿像素口径的结论去推网格 mask 的性质。

## 低估补偿换算表

名义占比 v/64 是链路看到的（像素 mask 计数），GT 臂平均占比是真相；两者之差是像素
mask 漏标造成的系统性低估。想选「格内真实臂占比 ≥ X」直接查表，**不要拿整体召回做
反推**——反推假设漏标在格间均匀，实际薄边缘格漏得多、臂身中央格几乎不漏。

## 用法（在仓库根）

    uv run --no-sync python scripts/data-generation/arm-mask/evaluate.py \\
      --sidecar-dir <make_mask 的 out-dir> \\
      --source artifacts/generated/<自生带 GT 数据集> \\
      --episodes 0-9 --workers 16 \\
      --json scripts/data-generation/arm-mask/outputs/json/generated_eval.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Sequence

import h5py
import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
GT_DATA_DIR = SCRIPT_DIR.parent / "gt-data"
for _path in (SCRIPT_DIR, GT_DATA_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from color_model import (  # noqa: E402
    CLASS_ARM,
    CLASS_BACKGROUND,
    CLASS_OBJECT,
    class_ids_from_setup,
    labels_from_segmentation,
    uncovered_mask,
)
from fit_color_model import parse_episodes  # noqa: E402
from grid_mask import WAN_VAE_SPATIAL_DOWNSAMPLE, cell_counts  # noqa: E402
from make_mask import GRID_MIN_PIXELS  # noqa: E402

FRAME_PIXELS = 256 * 256

# 格空间累计表的列布局（行索引 = 格内像素 mask 计数 v ∈ [0, 64]）
COL_CELLS = 0  # 计数恰为 v 的格子数
COL_PRED_PX = 1  # 这些格子里像素 mask 的像素数（= v·cells，兼自校验）
COL_GT_ARM = 2  # 这些格子里 GT 臂像素数
COL_GT_OBJ = 3  # GT 物体像素数（含兜底，与 labels_from_segmentation 口径一致）
COL_GT_BG = 4  # GT 背景像素数
COL_GT_UNCOV = 5  # 其中 GT 兜底（setup 未覆盖 seg id）像素数
COL_NO_ARM = 6  # 其中 GT 臂像素 == 0 的格子数（涂了就是纯误涂）
COL_TOUCH_ARM = 7  # 其中 GT 臂像素 ≥ 1 的格子数
COL_ARM_MAJOR = 8  # 其中 GT 臂像素 ≥ 半格的格子数
TABLE_COLUMNS = 9


def _ratio(numerator: float, denominator: float) -> float | None:
    if denominator <= 0:
        return None
    return round(float(numerator) / float(denominator), 6)


def _bincount(pred_counts: np.ndarray, weights: np.ndarray | None, rows: int) -> np.ndarray:
    if weights is None:
        return np.bincount(pred_counts, minlength=rows).astype(np.int64)
    # float64 对 ≤2^53 的整数精确，这里的量级（单帧 ≤ 65536）远在其内
    return np.bincount(
        pred_counts, weights=weights.astype(np.float64), minlength=rows
    ).astype(np.int64)


def _iter_gt_segmentation(episode_group: h5py.Group) -> list[np.ndarray]:
    """按 timestep 数字序读 GT segmentation。缺字段 fail-loud（本入口只对带 GT 的源跑）。"""
    named: list[tuple[int, str]] = []
    for name in episode_group:
        if not name.startswith("timestep_"):
            continue
        suffix = name[len("timestep_") :]
        if not suffix.isdigit():
            raise ValueError(f"无法解析的 timestep 名：{name}")
        named.append((int(suffix), name))
    named.sort()

    out: list[np.ndarray] = []
    for _, name in named:
        obs = episode_group[name].get("obs")
        if not isinstance(obs, h5py.Group) or "front_camera_segmentation" not in obs:
            raise KeyError(
                f"{name} 缺 obs/front_camera_segmentation——本入口只能评估带 GT 的数据源"
            )
        out.append(np.squeeze(obs["front_camera_segmentation"][()]))
    return out


def process_episode(
    sidecar_path: str,
    h5_path: str,
    episode_index: int,
    cell_size: int,
    min_pixels: int,
) -> dict[str, Any]:
    """一个 episode 的双口径统计。像素 mask 与格计数都直接读 sidecar，不重跑推理链。"""
    import cv2

    cv2.setNumThreads(1)

    task = Path(h5_path).stem.replace("record_dataset_", "")
    name = f"episode_{episode_index}"
    cell_area = cell_size * cell_size
    rows = cell_area + 1

    with h5py.File(sidecar_path, "r") as handle:
        group = handle[name]
        if "arm_mask_px" not in group:
            raise KeyError(
                f"{sidecar_path}/{name} 没有 arm_mask_px——"
                "sidecar 写入时用了 --no-store-pixel-mask，无法做像素口径实测"
            )
        masks = group["arm_mask_px"][()]
        counts = group["arm_cell_counts"][()]
        unseen_pixels = int(np.asarray(group["unseen_pixels"][()]).sum())

    with h5py.File(h5_path, "r") as handle:
        episode = handle[name]
        class_ids = class_ids_from_setup(episode["setup"])
        segmentations = _iter_gt_segmentation(episode)

    if len(segmentations) != len(masks):
        raise AssertionError(
            f"{task}/{name}: sidecar 帧数 {len(masks)} 与源 h5 帧数 {len(segmentations)} 不一致"
        )

    stats = {
        "task": task,
        "episode": episode_index,
        "frames": len(masks),
        "unseen_color_pixels": unseen_pixels,
        "pred_pixels": 0,
        "gt_arm_pixels": 0,
        "gt_object_pixels": 0,
        "gt_background_pixels": 0,
        "true_arm_pixels": 0,
        "false_object_pixels": 0,
        "false_background_pixels": 0,
        "frames_touching_object": 0,
        "uncovered_gt_pixels": 0,
        "false_uncovered_pixels": 0,
    }
    table = np.zeros((rows, TABLE_COLUMNS), np.int64)

    for mask, segmentation, count_map in zip(masks, segmentations, counts):
        gt = labels_from_segmentation(segmentation, class_ids)
        uncovered = uncovered_mask(segmentation, class_ids)
        mask = np.asarray(mask, bool)

        false_object = int((mask & (gt == CLASS_OBJECT)).sum())
        stats["pred_pixels"] += int(mask.sum())
        stats["gt_arm_pixels"] += int((gt == CLASS_ARM).sum())
        stats["gt_object_pixels"] += int((gt == CLASS_OBJECT).sum())
        stats["gt_background_pixels"] += int((gt == CLASS_BACKGROUND).sum())
        stats["true_arm_pixels"] += int((mask & (gt == CLASS_ARM)).sum())
        stats["false_object_pixels"] += false_object
        stats["false_background_pixels"] += int((mask & (gt == CLASS_BACKGROUND)).sum())
        stats["frames_touching_object"] += 1 if false_object else 0
        stats["uncovered_gt_pixels"] += int(uncovered.sum())
        stats["false_uncovered_pixels"] += int((mask & uncovered).sum())

        # ⚠ 格空间统计只用 GT 尺子，不许误用预测标签——CLASS_MIX == CLASS_OBJECT == 1
        # 数值相同、语义不同
        pred_cell = np.asarray(count_map, np.int64).ravel()
        gt_arm_cell = cell_counts(gt == CLASS_ARM, cell_size).ravel()
        gt_obj_cell = cell_counts(gt == CLASS_OBJECT, cell_size).ravel()
        gt_bg_cell = cell_counts(gt == CLASS_BACKGROUND, cell_size).ravel()
        gt_uncov_cell = cell_counts(uncovered, cell_size).ravel()
        # GT 三类穷尽：一旦破了说明 labels_from_segmentation 口径变了
        if not np.array_equal(
            gt_arm_cell + gt_obj_cell + gt_bg_cell,
            np.full_like(gt_arm_cell, cell_area),
        ):
            raise AssertionError("GT 三类在格内不穷尽，labels 口径疑似变更")
        # sidecar 的格计数必须与像素 mask 现算一致（防 sidecar 与源数据错配）
        if not np.array_equal(pred_cell, cell_counts(mask, cell_size).ravel()):
            raise AssertionError(f"{task}/{name}: sidecar 格计数与像素 mask 不自洽")

        table[:, COL_CELLS] += _bincount(pred_cell, None, rows)
        table[:, COL_PRED_PX] += _bincount(pred_cell, pred_cell, rows)
        table[:, COL_GT_ARM] += _bincount(pred_cell, gt_arm_cell, rows)
        table[:, COL_GT_OBJ] += _bincount(pred_cell, gt_obj_cell, rows)
        table[:, COL_GT_BG] += _bincount(pred_cell, gt_bg_cell, rows)
        table[:, COL_GT_UNCOV] += _bincount(pred_cell, gt_uncov_cell, rows)
        table[:, COL_NO_ARM] += _bincount(
            pred_cell, (gt_arm_cell == 0).astype(np.int64), rows
        )
        table[:, COL_TOUCH_ARM] += _bincount(
            pred_cell, (gt_arm_cell >= 1).astype(np.int64), rows
        )
        table[:, COL_ARM_MAJOR] += _bincount(
            pred_cell, (gt_arm_cell >= cell_area // 2).astype(np.int64), rows
        )

    # 自校验：COL_PRED_PX 逐行必须等于 v·cells
    index = np.arange(rows, dtype=np.int64)
    if not np.array_equal(table[:, COL_PRED_PX], index * table[:, COL_CELLS]):
        raise AssertionError("累计表自校验失败：pred_px ≠ v·cells")

    stats["table"] = table.tolist()
    return stats


def pixel_metrics(records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """像素口径汇总。刚性红线看 false_object_pixels。"""
    keys = [
        "frames",
        "pred_pixels",
        "gt_arm_pixels",
        "gt_object_pixels",
        "gt_background_pixels",
        "true_arm_pixels",
        "false_object_pixels",
        "false_background_pixels",
        "unseen_color_pixels",
        "frames_touching_object",
        "uncovered_gt_pixels",
        "false_uncovered_pixels",
    ]
    total = {key: int(sum(item[key] for item in records)) for key in keys}
    total["物体误标率"] = _ratio(total["false_object_pixels"], total["gt_object_pixels"])
    total["背景误标率"] = _ratio(
        total["false_background_pixels"], total["gt_background_pixels"]
    )
    total["机械臂召回"] = _ratio(total["true_arm_pixels"], total["gt_arm_pixels"])
    total["标定精确率"] = _ratio(total["true_arm_pixels"], total["pred_pixels"])
    total["未见颜色率"] = _ratio(total["unseen_color_pixels"], total["frames"] * FRAME_PIXELS)
    total["碰到物体的帧占比"] = _ratio(total["frames_touching_object"], total["frames"])
    return total


def grid_metrics(table: np.ndarray, min_pixels: int, cell_area: int) -> dict[str, Any]:
    """单个全局阈值 K 的网格口径指标 = 累计表的后缀和 Σ_{v≥K}。"""
    whole = table.sum(axis=0)
    suffix = table[min_pixels:].sum(axis=0)
    grid_cells = int(suffix[COL_CELLS])
    painted = grid_cells * cell_area
    painted_arm = int(suffix[COL_GT_ARM])
    painted_object = int(suffix[COL_GT_OBJ])
    painted_background = int(suffix[COL_GT_BG])
    # 三分解恒等式：GT 三类穷尽 ⇒ 涂红像素恰好分完
    if painted_arm + painted_object + painted_background != painted:
        raise AssertionError(f"K={min_pixels} 三分解恒等式被破坏")
    return {
        "min_pixels": min_pixels,
        "占比": f"{min_pixels}/{cell_area} = {min_pixels / cell_area:.1%}",
        "grid_cells": grid_cells,
        "cells_total": int(whole[COL_CELLS]),
        "painted_pixels": painted,
        "painted_gt_arm": painted_arm,
        "painted_gt_object": painted_object,
        "painted_gt_background": painted_background,
        "painted_gt_uncovered": int(suffix[COL_GT_UNCOV]),
        "cells_no_arm": int(suffix[COL_NO_ARM]),
        "网格臂格占比（/ 全部格）": _ratio(grid_cells, int(whole[COL_CELLS])),
        "GT 臂像素覆盖率（/ GT 臂像素）": _ratio(painted_arm, int(whole[COL_GT_ARM])),
        "GT 物体像素被涂比例（/ GT 物体像素）": _ratio(
            painted_object, int(whole[COL_GT_OBJ])
        ),
        "GT 背景像素被涂比例（/ GT 背景像素）": _ratio(
            painted_background, int(whole[COL_GT_BG])
        ),
        "网格精确率（/ 涂红像素）": _ratio(painted_arm, painted),
        "像素 mask 保留率（/ 像素 mask 像素）": _ratio(
            int(suffix[COL_PRED_PX]), int(whole[COL_PRED_PX])
        ),
        "GT 触臂格召回（/ GT 触臂格）": _ratio(
            int(suffix[COL_TOUCH_ARM]), int(whole[COL_TOUCH_ARM])
        ),
        "GT 臂主导格召回（/ GT 臂主导格）": _ratio(
            int(suffix[COL_ARM_MAJOR]), int(whole[COL_ARM_MAJOR])
        ),
        "纯误涂格占比（/ 网格臂格）": _ratio(int(suffix[COL_NO_ARM]), grid_cells),
        "GT臂主导格定义": f"格内 GT 臂像素 ≥ {cell_area // 2}",
    }


def compensation_table(table: np.ndarray, cell_area: int) -> list[dict[str, Any]]:
    """低估补偿换算表：逐计数档位 v 的「名义占比 vs GT 臂平均占比」。"""
    out = []
    for v in range(table.shape[0]):
        cells = int(table[v, COL_CELLS])
        out.append(
            {
                "v": v,
                "名义占比": round(v / cell_area, 6),
                "cells": cells,
                "GT臂平均占比": _ratio(int(table[v, COL_GT_ARM]), cells * cell_area),
                "GT物体平均占比": _ratio(int(table[v, COL_GT_OBJ]), cells * cell_area),
                "GT背景平均占比": _ratio(int(table[v, COL_GT_BG]), cells * cell_area),
            }
        )
    return out


def enforce_no_false_object(scope: str, entries: Sequence[tuple[str, int]]) -> int:
    """刚性红线闸门：GT 判定的误标物体像素必须恒为 0，否则 fail-loud。

    返回值直接当退出码用：0 = 通过，1 = 红线被击穿。把「误标物体 = 0」写进 JSON 只是
    记录，人不看就等于没有；红线被击穿时产物整体不可信，必须让调用方立刻知道。
    **刻意不提供豁免开关**——有开关就等于又养出第二个口径。

    ⚠ 只适用于像素口径。网格口径下整格涂红必然覆盖物体像素，该闸门不适用也不该成立。
    """
    offenders = [(name, int(count)) for name, count in entries if int(count) > 0]
    if not offenders:
        print(f"刚性红线通过：{scope} 共 {len(entries)} 项，GT 判定的误标物体像素全部为 0")
        return 0
    total = sum(count for _, count in offenders)
    print(
        f"⚠ 刚性红线被击穿：{scope} 有 {len(offenders)} 项把物体标进了机械臂，"
        f"合计 {total} px（GT 逐像素判定）"
    )
    for name, count in sorted(offenders, key=lambda item: item[1], reverse=True):
        print(f"  {name}: {count} px")
    return 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sidecar-dir", required=True, help="make_mask.py 的 --out-dir")
    parser.add_argument("--source", required=True, help="带 GT segmentation 的 h5 数据源目录")
    parser.add_argument("--episodes", default="0-9")
    parser.add_argument("--tasks", default="all", help="all 或逗号分隔任务名")
    parser.add_argument(
        "--min-pixels",
        type=int,
        default=GRID_MIN_PIXELS,
        help=f"网格阈值 K（默认 {GRID_MIN_PIXELS}，与 make_mask 的拍板值一致）",
    )
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument(
        "--json",
        default=str(SCRIPT_DIR / "outputs" / "json" / "generated_eval.json"),
    )
    args = parser.parse_args(argv)

    sidecar_dir = Path(args.sidecar_dir)
    source_root = Path(args.source)
    cell_size = WAN_VAE_SPATIAL_DOWNSAMPLE
    cell_area = cell_size * cell_size

    sidecars = sorted(sidecar_dir.glob("arm_grid_mask_*.h5"))
    if not sidecars:
        raise SystemExit(f"sidecar 目录没有 arm_grid_mask_*.h5：{sidecar_dir}")
    if args.tasks != "all":
        wanted = {item.strip() for item in args.tasks.split(",") if item.strip()}
        sidecars = [
            path for path in sidecars if path.stem.replace("arm_grid_mask_", "") in wanted
        ]

    jobs: list[tuple[str, str, int]] = []
    for sidecar in sidecars:
        task = sidecar.stem.replace("arm_grid_mask_", "")
        h5_path = source_root / f"record_dataset_{task}.h5"
        if not h5_path.is_file():
            raise SystemExit(f"源 h5 不存在：{h5_path}")
        # sidecar 里实际有哪些 episode 为准：模式②可能有 planner 失败被跳过的 episode
        with h5py.File(sidecar, "r") as handle:
            available = {
                int(name.split("_")[1]) for name in handle if name.startswith("episode_")
            }
        wanted_episodes = sorted(available & set(parse_episodes(args.episodes)))
        for index in wanted_episodes:
            jobs.append((str(sidecar), str(h5_path), index))

    if not jobs:
        raise SystemExit("没有可评估的 episode")

    print(
        f"实测：{len(sidecars)} 个任务 / {len(jobs)} 个 episode，"
        f"K={args.min_pixels}（{args.min_pixels}/{cell_area} = "
        f"{args.min_pixels / cell_area:.1%}），并行 {args.workers}"
    )
    started = time.perf_counter()
    records: list[dict[str, Any]] = []
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = [
            executor.submit(
                process_episode, sidecar, h5_path, index, cell_size, args.min_pixels
            )
            for sidecar, h5_path, index in jobs
        ]
        for future in as_completed(futures):
            records.append(future.result())
    elapsed = time.perf_counter() - started
    records.sort(key=lambda item: (item["task"], item["episode"]))

    total_table = np.zeros((cell_area + 1, TABLE_COLUMNS), np.int64)
    for record in records:
        total_table += np.asarray(record["table"], np.int64)

    tasks = sorted({record["task"] for record in records})
    per_task: dict[str, Any] = {}
    for task in tasks:
        subset = [record for record in records if record["task"] == task]
        task_table = np.zeros((cell_area + 1, TABLE_COLUMNS), np.int64)
        for record in subset:
            task_table += np.asarray(record["table"], np.int64)
        per_task[task] = {
            "num_episodes": len(subset),
            **pixel_metrics(subset),
            "网格": grid_metrics(task_table, args.min_pixels, cell_area),
        }
        print(
            f"  {task}: {len(subset)} ep / {per_task[task]['frames']} 帧，"
            f"误标物体 {per_task[task]['false_object_pixels']} px，"
            f"像素召回 {per_task[task]['机械臂召回']}，"
            f"网格臂覆盖 {per_task[task]['网格']['GT 臂像素覆盖率（/ GT 臂像素）']}"
        )

    payload = {
        "参数": {
            "sidecar_dir": str(sidecar_dir),
            "source": str(source_root),
            "episodes": sorted({record["episode"] for record in records}),
            "min_pixels": args.min_pixels,
            "cell_size": cell_size,
            "口径": "像素表拟合在 val split，本实测在 train split 官方同 seed 重放数据上做，"
            "零 seed 重叠；⚠ 不回放 joint angle，轨迹由 planner 重新规划，"
            "故与官方 h5 同场景但不同轨迹",
            "刚性红线": "像素口径误标物体像素必须恒为 0；网格口径不适用该红线",
        },
        "耗时秒": round(elapsed, 1),
        "像素口径": pixel_metrics(records),
        "网格口径": grid_metrics(total_table, args.min_pixels, cell_area),
        "低估补偿换算表": compensation_table(total_table, cell_area),
        "逐任务": per_task,
        "逐 episode": [
            {key: value for key, value in record.items() if key != "table"}
            for record in records
        ],
    }
    json_path = Path(args.json)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"实测 JSON 已写入 {json_path}")

    pixel = payload["像素口径"]
    grid = payload["网格口径"]
    print(
        f"\n像素口径：误标物体 {pixel['false_object_pixels']} px / "
        f"误标背景 {pixel['false_background_pixels']} px / "
        f"精确率 {pixel['标定精确率']} / 召回 {pixel['机械臂召回']} / "
        f"未见色 {pixel['未见颜色率']}"
    )
    print(
        f"网格口径 K={args.min_pixels}：臂覆盖 {grid['GT 臂像素覆盖率（/ GT 臂像素）']} / "
        f"物体被涂 {grid['GT 物体像素被涂比例（/ GT 物体像素）']} / "
        f"网格精确率 {grid['网格精确率（/ 涂红像素）']} / "
        f"纯误涂格 {grid['cells_no_arm']}"
    )

    # 刚性红线只对像素口径生效，逐 episode 校验
    return enforce_no_false_object(
        f"实测 {len(records)} 个 episode",
        [
            (f"{record['task']}/episode_{record['episode']}", record["false_object_pixels"])
            for record in records
        ],
    )


if __name__ == "__main__":
    raise SystemExit(main())
