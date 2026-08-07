#!/usr/bin/env python3
"""自对拍：验证开启 flow 与遮蔽图采集之后，h5 里其余的一切**逐位不变**。

「只增不改」是这条链路的生命线——新增字段不得改变任何既有 h5 内容。验收口径是
**自对拍**而不是跟官方参考对拍：同一个 commit 的代码，两个开关全关 / 全开各生成一次，
比较除新增字段之外的全部内容。基准侧必须是 ``--no-flow --no-masked-rgb``。

比较是逐位的（``np.array_equal``），不设容差。之所以敢要求逐位：flow 采集全部发生在
``env.step()`` **之后**，只读仿真状态、不消费随机数，理论上对仿真与规划零影响。真要出现
差异，第一嫌疑永远是规划器退避到了 RRTStar（带墙钟预算的采样式规划，链路里唯一的非确定性
来源），生成报告里的 ``planner_fallback.rrtstar_attempts`` 就是用来第一时间排除这个的。

比较范围覆盖 h5 里的每一个 dataset：路径集合、shape、dtype、数值全部要一致。只有下面这些
路径被明确排除（它们正是本轮新增的东西）：

- ``episode_<i>/timestep_<k>/flow/**``
- ``episode_<i>/setup/flow_schema_version``
- ``episode_<i>/setup/flow_objects/**``
- ``episode_<i>/setup/flow_excluded/**``
- ``episode_<i>/timestep_<k>/obs/front_rgb_masked``
- ``episode_<i>/setup/masked_rgb_*``（schema_version / paint_color / painted / kept）

flow 与 masked rgb 的存在性断言是**两个独立计数器**，不是合成一个：合成之后
``--no-masked-rgb`` 开关坏掉时就能躲在正常工作的 ``--flow`` 后面不被发现。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

import h5py
import numpy as np


# 允许出现在候选侧而基准侧没有的路径（即本轮新增的内容），两组分开数。
# flow（v2.0）：
FLOW_PATH_MARKERS = (
    "/flow/",
    "/flow_schema_version",
    "/flow_objects/",
    "/flow_excluded/",
)
# 纯色棕遮蔽图（v2.1）：`/masked_rgb_` 一条覆盖 setup 下的 schema_version /
# paint_color / painted / kept 四处
MASKED_RGB_PATH_MARKERS = (
    "/front_rgb_masked",
    "/masked_rgb_",
)

MAX_REPORTED_DIFFS = 40


def _is_flow_path(path: str) -> bool:
    return any(marker in path for marker in FLOW_PATH_MARKERS)


def _is_masked_rgb_path(path: str) -> bool:
    # front_rgb_masked 用 endswith 判定：子串判定虽然也不会误伤 /front_rgb
    # （方向是单向的），但写成 endswith 才是把意图直接摆出来
    if path.endswith("/front_rgb_masked"):
        return True
    return "/masked_rgb_" in path


def _collect_datasets(
    handle: h5py.File,
) -> tuple[dict[str, tuple[tuple[int, ...], str]], int, int]:
    """递归收集全部 dataset 的路径 -> (shape, dtype)，跳过新增内容。

    同时**分别**返回被跳过的 flow 与 masked rgb dataset 数量。比较本身要排除这两类
    （那正是新增的东西），但「基准侧一个都没有、候选侧确实写了」这件事必须单独核一次——
    否则 ``--no-flow`` / ``--no-masked-rgb`` 开关坏掉、两边都不写时，逐位对拍照样全绿，
    等于什么都没验证。

    两个计数**必须分开**：合成一个计数器的话，``--no-masked-rgb`` 坏掉时就能躲在正常工作的
    ``--flow`` 后面不被发现。
    """
    collected: dict[str, tuple[tuple[int, ...], str]] = {}
    flow_dataset_count = 0
    masked_rgb_dataset_count = 0

    def visit(name: str, obj: Any) -> None:
        nonlocal flow_dataset_count, masked_rgb_dataset_count
        if not isinstance(obj, h5py.Dataset):
            return
        path = "/" + name
        if _is_flow_path(path):
            flow_dataset_count += 1
            return
        if _is_masked_rgb_path(path):
            masked_rgb_dataset_count += 1
            return
        collected[path] = (tuple(obj.shape), obj.dtype.str)

    handle.visititems(visit)
    return collected, flow_dataset_count, masked_rgb_dataset_count


def _values_equal(left: Any, right: Any) -> bool:
    """逐位比较两个 dataset 的值，字符串与数值分别处理。"""
    left_value = left[()]
    right_value = right[()]

    if isinstance(left_value, bytes) or isinstance(right_value, bytes):
        return left_value == right_value
    if isinstance(left_value, str) or isinstance(right_value, str):
        return left_value == right_value

    left_array = np.asarray(left_value)
    right_array = np.asarray(right_value)
    if left_array.dtype.kind in "OSU" or right_array.dtype.kind in "OSU":
        return left_array.shape == right_array.shape and bool(
            np.all(left_array == right_array)
        )
    # NaN 在既有字段里是正常哨兵（waypoint_action），必须按「同位置同为 NaN」算相等
    if left_array.dtype.kind == "f":
        return left_array.shape == right_array.shape and bool(
            np.array_equal(left_array, right_array, equal_nan=True)
        )
    return bool(np.array_equal(left_array, right_array))


def compare_files(
    baseline_path: Path,
    candidate_path: Path,
    expect_flow: bool = True,
    expect_masked_rgb: bool = True,
) -> dict[str, Any]:
    """比较两个 h5 文件除 flow 与 masked rgb 外的全部内容。"""
    differences: list[str] = []
    joint_action_checked = 0
    joint_action_mismatched = 0

    with h5py.File(baseline_path, "r") as baseline, h5py.File(candidate_path, "r") as candidate:
        baseline_sets, baseline_flow_count, baseline_masked_count = _collect_datasets(
            baseline
        )
        candidate_sets, candidate_flow_count, candidate_masked_count = _collect_datasets(
            candidate
        )

        # 存在性：基准侧必须一个都没有，候选侧必须真的写了。两项独立断言，互不遮蔽。
        if baseline_flow_count != 0:
            differences.append(
                f"基准侧（应为 --no-flow）意外含有 {baseline_flow_count} 个 flow dataset"
            )
        if expect_flow and candidate_flow_count == 0:
            differences.append(
                "候选侧（应为 --flow）一个 flow dataset 都没有，flow 采集没生效"
            )
        if baseline_masked_count != 0:
            differences.append(
                f"基准侧（应为 --no-masked-rgb）意外含有 {baseline_masked_count} 个 masked rgb dataset"
            )
        if expect_masked_rgb and candidate_masked_count == 0:
            differences.append(
                "候选侧（应为 --masked-rgb）一个 masked rgb dataset 都没有，遮蔽图采集没生效"
            )

        only_baseline = sorted(set(baseline_sets) - set(candidate_sets))
        only_candidate = sorted(set(candidate_sets) - set(baseline_sets))
        for path in only_baseline[:MAX_REPORTED_DIFFS]:
            differences.append(f"仅基准侧存在：{path}")
        for path in only_candidate[:MAX_REPORTED_DIFFS]:
            differences.append(f"仅候选侧存在：{path}")

        for path in sorted(set(baseline_sets) & set(candidate_sets)):
            baseline_shape, baseline_dtype = baseline_sets[path]
            candidate_shape, candidate_dtype = candidate_sets[path]
            is_joint_action = path.endswith("/action/joint_action")
            if is_joint_action:
                joint_action_checked += 1

            if baseline_shape != candidate_shape:
                differences.append(
                    f"shape 不一致：{path} 基准={baseline_shape} 候选={candidate_shape}"
                )
                if is_joint_action:
                    joint_action_mismatched += 1
                continue
            if baseline_dtype != candidate_dtype:
                differences.append(
                    f"dtype 不一致：{path} 基准={baseline_dtype} 候选={candidate_dtype}"
                )
                if is_joint_action:
                    joint_action_mismatched += 1
                continue
            if not _values_equal(baseline[path], candidate[path]):
                differences.append(f"数值不逐位相等：{path}")
                if is_joint_action:
                    joint_action_mismatched += 1

        # timestep 集合单独核一次，便于差异定位
        baseline_episodes = sorted(
            name for name in baseline.keys() if name.startswith("episode_")
        )
        candidate_episodes = sorted(
            name for name in candidate.keys() if name.startswith("episode_")
        )
        if baseline_episodes != candidate_episodes:
            differences.append(
                f"episode 集合不一致：基准={baseline_episodes} 候选={candidate_episodes}"
            )
        else:
            for name in baseline_episodes:
                baseline_steps = sorted(
                    key for key in baseline[name].keys() if key.startswith("timestep_")
                )
                candidate_steps = sorted(
                    key for key in candidate[name].keys() if key.startswith("timestep_")
                )
                if baseline_steps != candidate_steps:
                    differences.append(
                        f"{name} 的 timestep 集合不一致："
                        f"基准 {len(baseline_steps)} 个 / 候选 {len(candidate_steps)} 个"
                    )

    return {
        "baseline": str(baseline_path),
        "candidate": str(candidate_path),
        "dataset_count": len(baseline_sets),
        "baseline_flow_datasets": baseline_flow_count,
        "candidate_flow_datasets": candidate_flow_count,
        "baseline_masked_rgb_datasets": baseline_masked_count,
        "candidate_masked_rgb_datasets": candidate_masked_count,
        "joint_action_checked": joint_action_checked,
        "joint_action_mismatched": joint_action_mismatched,
        "difference_count": len(differences),
        "differences": differences[:MAX_REPORTED_DIFFS],
        "passed": not differences,
    }


def compare_directories(
    baseline_dir: Path,
    candidate_dir: Path,
    expect_flow: bool = True,
    expect_masked_rgb: bool = True,
) -> list[dict[str, Any]]:
    """按任务逐个比较两个产物目录下的 record_dataset_<任务>.h5。"""
    baseline_files = sorted(baseline_dir.glob("record_dataset_*.h5"))
    if not baseline_files:
        raise FileNotFoundError(f"基准目录里没有 record_dataset_*.h5：{baseline_dir}")

    results: list[dict[str, Any]] = []
    for baseline_path in baseline_files:
        candidate_path = candidate_dir / baseline_path.name
        if not candidate_path.is_file():
            results.append(
                {
                    "baseline": str(baseline_path),
                    "candidate": str(candidate_path),
                    "difference_count": 1,
                    "differences": [f"候选目录里缺少同名文件：{candidate_path.name}"],
                    "passed": False,
                }
            )
            continue
        results.append(
            compare_files(
                baseline_path,
                candidate_path,
                expect_flow=expect_flow,
                expect_masked_rgb=expect_masked_rgb,
            )
        )
    return results


def _format_report(all_results: dict[str, list[dict[str, Any]]]) -> str:
    lines: list[str] = []
    for candidate_dir, results in all_results.items():
        passed = sum(1 for item in results if item["passed"])
        lines.append(f"=== 候选：{candidate_dir} ===")
        for item in results:
            name = Path(item["baseline"]).name
            mark = "✓" if item["passed"] else "✗"
            lines.append(
                f"  {mark} {name}: 比较 {item.get('dataset_count', 0)} 个既有 dataset，"
                f"其中 joint_action {item.get('joint_action_checked', 0)} 个"
                f"（不一致 {item.get('joint_action_mismatched', 0)} 个）；"
                f"flow dataset 基准侧 {item.get('baseline_flow_datasets', '?')} 个 / "
                f"候选侧 {item.get('candidate_flow_datasets', '?')} 个；"
                f"masked rgb dataset 基准侧 {item.get('baseline_masked_rgb_datasets', '?')} 个 / "
                f"候选侧 {item.get('candidate_masked_rgb_datasets', '?')} 个；"
                f"总差异 {item['difference_count']} 处"
            )
            for detail in item["differences"]:
                lines.append(f"      - {detail}")
        lines.append(
            f"  小计：{passed}/{len(results)} 个任务除 flow 与 masked rgb 外逐位一致"
        )
    return "\n".join(lines)


def _args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="自对拍：验证开启 flow 与遮蔽图后 h5 里其余内容逐位不变",
    )
    parser.add_argument(
        "--baseline",
        required=True,
        help="基准产物目录（应为 --no-flow --no-masked-rgb 那次）",
    )
    parser.add_argument(
        "--candidates",
        nargs="+",
        required=True,
        help="待比较的产物目录，可传多个",
    )
    parser.add_argument(
        "--no-expect-flow",
        dest="expect_flow",
        action="store_false",
        default=True,
        help="候选侧本来就不带 flow 时用，跳过「候选侧必须写了 flow」这条断言",
    )
    parser.add_argument(
        "--no-expect-masked-rgb",
        dest="expect_masked_rgb",
        action="store_false",
        default=True,
        help="候选侧本来就不带遮蔽图时用，跳过「候选侧必须写了 masked rgb」这条断言",
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
    baseline_dir = Path(namespace.baseline).expanduser().resolve()

    all_results: dict[str, list[dict[str, Any]]] = {}
    for raw in namespace.candidates:
        candidate_dir = Path(raw).expanduser().resolve()
        all_results[str(candidate_dir)] = compare_directories(
            baseline_dir,
            candidate_dir,
            expect_flow=namespace.expect_flow,
            expect_masked_rgb=namespace.expect_masked_rgb,
        )

    print(_format_report(all_results), flush=True)

    if namespace.json_path:
        Path(namespace.json_path).write_text(
            json.dumps(all_results, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )

    everything_passed = all(
        item["passed"] for results in all_results.values() for item in results
    )
    print(
        "结论：除 flow 与 masked rgb 之外全部逐位一致"
        if everything_passed
        else "结论：存在既有字段的差异，需逐条排查（先看生成报告里的 planner_fallback）",
        flush=True,
    )
    return 0 if everything_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
