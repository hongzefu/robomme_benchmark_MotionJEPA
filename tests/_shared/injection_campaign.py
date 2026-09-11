"""新值注入专项的编排入口（NEW_VALUE_INJECTION_TEST_PLAN 第五节）。

子命令：

* ``plan``  —— 生成并冻结 11 组 × 100 条规格，写运行根目录与清单（步骤 0）。
* ``check`` —— 从冻结的规格**独立重算**全部计数与几何，打第 5.7 节的判定行。
* ``plot``  —— 出跑前／跑后三类图（委托 :mod:`tests._shared.injection_plots`）。
* ``run``   —— 校准与实跑的编排（步骤 2～5），复用生产入口 ``generate_dataset_newseed``。

``plan`` 拒绝已存在的运行根目录；``check``／``plot`` 只从该编号的冻结清单读输入。
本模块属于测试侧工具，**生产代码不导入它**。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from robomme.robomme_env.utils import bin_collision as bc  # noqa: E402

from tests._shared.injection_categories import legal_categories, observed_values  # noqa: E402
from tests._shared.injection_sampling import COARSE_BINS, GROUP_SIZE  # noqa: E402
from tests._shared.injection_specs import (  # noqa: E402
    CUBE_HALF_SIZE,
    EXCLUDED_GROUPS,
    GENERATOR_VERSION,
    GROUPS,
    SPEC_SCHEMA_VERSION,
    DEFAULT_SEED,
    build_group,
    canonical_json,
    record_sha256,
    rotate_xy,
    button_obb,
    board_obbs,
    cube_obb,
    obb2d_intersect,
)

DEFAULT_SAMPLING_CONFIG = REPO_ROOT / "scripts" / "configs" / "newtask-v2" / "native_sampling.json"
INJECTION_ROOT = REPO_ROOT / "artifacts" / "injection"


class CampaignError(RuntimeError):
    """编排层的错误：目录冲突、清单缺失、判据不通过等。"""


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def run_root(run_id: str) -> Path:
    if not run_id or "/" in run_id or run_id.startswith("."):
        raise CampaignError(f"运行编号不合法：{run_id!r}")
    return INJECTION_ROOT / run_id


# ── plan ────────────────────────────────────────────────────────────────────
def cmd_plan(run_id: str, seed: int, per_group: int, sampling_config: Path) -> dict[str, Any]:
    """生成 11 组规格并冻结。运行编号不可复用：目录已存在直接拒绝。"""
    if per_group != GROUP_SIZE:
        raise CampaignError(f"本轮固定每组 {GROUP_SIZE} 条，收到 --per-group {per_group}")
    root = run_root(run_id)
    if root.exists():
        raise CampaignError(f"运行根目录已存在，编号不可复用：{root}")

    sampling = json.loads(sampling_config.read_text(encoding="utf-8"))
    config_sha = _sha256_file(sampling_config)

    started = time.monotonic()
    groups_meta: list[dict[str, Any]] = []
    stats_all: dict[str, Any] = {}
    for task, difficulty in GROUPS:
        group = build_group(task, difficulty, sampling, seed)
        relative = Path("specs") / task / f"{difficulty}.json"
        _write_json(root / relative, group.as_document(config_sha))
        groups_meta.append(
            {
                "task": task,
                "difficulty": difficulty,
                "path": str(relative),
                "file_sha256": _sha256_file(root / relative),
                "episodes": len(group.episodes),
                "derived_seed": group.derived_seed,
            }
        )
        stats_all[f"{task}/{difficulty}"] = {k: v for k, v in group.stats.items() if k != "rejections"}
        stats_all[f"{task}/{difficulty}"]["rejection_samples"] = group.stats["rejections"][:8]
        print(f"  冻结 {task}/{difficulty}: {len(group.episodes)} 条", flush=True)

    manifest = {
        "run_id": run_id,
        "spec_schema_version": SPEC_SCHEMA_VERSION,
        "generator_version": GENERATOR_VERSION,
        "generator_seed": seed,
        "per_group": per_group,
        "sampling_config_path": str(sampling_config.relative_to(REPO_ROOT)),
        "sampling_config_sha256": config_sha,
        "groups": groups_meta,
        "excluded_groups": [list(item) for item in EXCLUDED_GROUPS],
        "elapsed_s": round(time.monotonic() - started, 1),
    }
    _write_json(root / "manifest.json", manifest)
    _write_json(root / "plan_stats.json", stats_all)
    total = sum(item["episodes"] for item in groups_meta)
    print(f"PLAN=OK run_id={run_id} groups={len(groups_meta)} specs={total} elapsed_s={manifest['elapsed_s']}")
    return manifest


def load_manifest(run_id: str) -> tuple[Path, dict[str, Any]]:
    root = run_root(run_id)
    path = root / "manifest.json"
    if not path.is_file():
        raise CampaignError(f"找不到清单：{path}；先跑 plan")
    return root, json.loads(path.read_text(encoding="utf-8"))


def load_group_documents(run_id: str) -> tuple[Path, dict[str, Any], dict[tuple[str, str], dict[str, Any]]]:
    root, manifest = load_manifest(run_id)
    documents: dict[tuple[str, str], dict[str, Any]] = {}
    for item in manifest["groups"]:
        path = root / item["path"]
        actual = _sha256_file(path)
        if actual != item["file_sha256"]:
            raise CampaignError(f"{path} 的散列与清单不符：{actual} != {item['file_sha256']}")
        documents[(item["task"], item["difficulty"])] = json.loads(path.read_text(encoding="utf-8"))
    return root, manifest, documents


# ── check ───────────────────────────────────────────────────────────────────
class Verdicts:
    """收集判定行；任一项 FAIL 则整体不通过。"""

    def __init__(self) -> None:
        self.lines: list[str] = []
        self.records: list[dict[str, Any]] = []

    def add(self, name: str, passed: bool | None, **fields: Any) -> None:
        status = "NOT_RUN" if passed is None else ("PASS" if passed else "FAIL")
        rendered = " ".join(f"{key}={value}" for key, value in fields.items())
        self.lines.append(f"{name}={status}" + (f" {rendered}" if rendered else ""))
        self.records.append({"name": name, "status": status, **fields})

    @property
    def passed(self) -> bool:
        return all(item["status"] == "PASS" for item in self.records)


def _check_scope(documents: dict[tuple[str, str], dict[str, Any]], verdicts: Verdicts) -> None:
    problems: list[str] = []
    total = 0
    for (task, difficulty), doc in documents.items():
        episodes = doc["episodes"]
        total += len(episodes)
        numbers = [item["episode"] for item in episodes]
        if sorted(numbers) != list(range(GROUP_SIZE)):
            problems.append(f"{task}/{difficulty} 的 episode 号有缺号／重复／越界")
        for item in episodes:
            if item["task"] != task or item["difficulty"] != difficulty:
                problems.append(f"{task}/{difficulty}/episode {item['episode']} 的任务或难度不符")
            if record_sha256(item) != item["spec_sha256"]:
                problems.append(f"{task}/{difficulty}/episode {item['episode']} 的 spec_sha256 不符")
    excluded_present = [key for key in documents if list(key) in [list(e) for e in EXCLUDED_GROUPS]]
    if excluded_present:
        problems.append(f"排除组仍被生成：{excluded_present}")
    verdicts.add(
        "SPEC_SCOPE",
        not problems,
        groups=len(documents),
        specs=total,
        excluded="VideoRepick-hard",
        problems=len(problems),
    )
    if problems:
        verdicts.records[-1]["detail"] = problems[:10]


def _check_reproducible(
    documents: dict[tuple[str, str], dict[str, Any]], sampling: dict[str, Any], seed: int, verdicts: Verdicts
) -> None:
    """同 seed、**不同组调度顺序**独立再生成一次，逐记录散列必须相同。"""
    compared = 0
    differences = 0
    for task, difficulty in reversed(GROUPS):  # 倒序调度，证明结果与顺序无关
        rebuilt = build_group(task, difficulty, sampling, seed)
        frozen = documents[(task, difficulty)]["episodes"]
        for left, right in zip(frozen, rebuilt.episodes):
            compared += 1
            if left["spec_sha256"] != right["spec_sha256"]:
                differences += 1
    verdicts.add("SPEC_REPRODUCIBLE", differences == 0, compared=compared, differences=differences)


def _check_quota(
    documents: dict[tuple[str, str], dict[str, Any]], sampling: dict[str, Any], verdicts: Verdicts
) -> dict[str, Any]:
    """独立类别按完整合法集合补零后计数差 ≤1；连续量验粗箱与批次覆盖。"""
    gaps: list[str] = []
    report: dict[str, Any] = {}
    for (task, difficulty), doc in documents.items():
        categories = legal_categories(task, difficulty, sampling)
        counts: dict[str, Counter] = {}
        for record in doc["episodes"]:
            for field, values in observed_values(task, record).items():
                bucket = counts.setdefault(field, Counter())
                for value in values:
                    bucket[canonical_json(value)] += 1
        group_report: dict[str, Any] = {"independent": {}, "coupled": {}, "continuous": {}}

        for field, legal in categories["independent"].items():
            observed = counts.get(field, Counter())
            # ⚠ 按完整合法类别补零，否则「100 条全为同一值」也会算出计数差 0
            table = {canonical_json(value): observed.get(canonical_json(value), 0) for value in legal}
            spread = max(table.values()) - min(table.values())
            group_report["independent"][field] = {"counts": table, "spread": spread}
            if spread > 1:
                gaps.append(f"{task}/{difficulty} 的 {field} 计数差 {spread} > 1")

        for field, legal in categories["coupled"].items():
            observed = counts.get(field, Counter())
            table = dict(observed)
            uncovered = [canonical_json(v) for v in legal if canonical_json(v) not in table]
            group_report["coupled"][field] = {"counts": table, "uncovered": uncovered}

        # 连续量：从 sampling_cells 独立重算粗箱与批次覆盖
        cells: dict[str, list[int]] = {}
        for record in doc["episodes"]:
            for name, (coarse, _fine) in record["sampling_cells"].items():
                cells.setdefault(name, []).append(int(coarse))
        for name, series in cells.items():
            per_bin = Counter(series)
            batch_cover = [len(set(series[t * COARSE_BINS : (t + 1) * COARSE_BINS])) for t in range(COARSE_BINS)]
            ok = all(per_bin.get(b, 0) == GROUP_SIZE // COARSE_BINS for b in range(COARSE_BINS)) and all(
                value == COARSE_BINS for value in batch_cover
            )
            group_report["continuous"][name] = {
                "per_bin": {str(b): per_bin.get(b, 0) for b in range(COARSE_BINS)},
                "batch_coverage": batch_cover,
                "ok": ok,
            }
            if not ok:
                gaps.append(f"{task}/{difficulty} 的连续量 {name} 分箱或批次覆盖不达标")
        report[f"{task}/{difficulty}"] = group_report

    verdicts.add(
        "COVERAGE_QUOTA",
        not gaps,
        groups=len(documents),
        batches=COARSE_BINS,
        quota_gaps=len(gaps),
    )
    if gaps:
        verdicts.records[-1]["detail"] = gaps[:10]
    return report


def _check_static_geometry(
    documents: dict[tuple[str, str], dict[str, Any]], sampling: dict[str, Any], verdicts: Verdicts
) -> None:
    """逐条检查难度、索引、取值范围、避让、路线合法性与动作长度。"""
    problems: list[str] = []
    checked = 0
    for (task, difficulty), doc in documents.items():
        parameters = sampling["parameters"][task]
        positions = sampling["positions"][task]
        config = parameters["configs"][difficulty]
        for record in doc["episodes"]:
            checked += 1
            tag = f"{task}/{difficulty}/ep{record['episode']}"
            problems.extend(_static_problems(task, difficulty, tag, record, config, parameters, positions))
    verdicts.add("STATIC_GEOMETRY", not problems, checked=checked, rejected=len(problems))
    if problems:
        verdicts.records[-1]["detail"] = problems[:10]


def _in_range(value: float, lo: float, hi: float, tol: float = 1e-9) -> bool:
    return math.isfinite(value) and lo - tol <= value <= hi + tol


def _static_problems(
    task: str,
    difficulty: str,
    tag: str,
    record: dict[str, Any],
    config: dict[str, Any],
    parameters: dict[str, Any],
    positions: dict[str, Any],
) -> list[str]:
    problems: list[str] = []
    layout = record["layout"]
    objects = record["objects"]
    actions = record["actions"]

    if task == "BinFill":
        button = positions["button"]
        bx, by = (float(v) for v in button["center_xy"])
        rx, ry = (float(v) for v in button["randomize_range"])
        if not (_in_range(layout["button_xy"][0], bx - rx / 2, bx + rx / 2) and _in_range(layout["button_xy"][1], by - ry / 2, by + ry / 2)):
            problems.append(f"{tag}: 按钮越界")
        board = positions["board"]
        base_x = float(board["base_position"][0])
        if not _in_range(layout["board"]["xy"][0], base_x - board["x_offset"]["subtract"], base_x - board["x_offset"]["subtract"] + board["x_offset"]["scale"]):
            problems.append(f"{tag}: 孔板 x 越界")
        if not _in_range(layout["board"]["xy"][1], -board["y_offset"]["subtract"], -board["y_offset"]["subtract"] + board["y_offset"]["scale"]):
            problems.append(f"{tag}: 孔板 y 越界")
        if not _in_range(layout["board"]["yaw_deg"], -board["yaw_deg"]["subtract"], -board["yaw_deg"]["subtract"] + board["yaw_deg"]["scale"]):
            problems.append(f"{tag}: 孔板朝向越界")

        cubes_cfg = positions["cubes"]
        center = [float(v) for v in cubes_cfg["region_center"]]
        half = [float(v) for v in cubes_cfg["region_half_size"]]
        obstacles = [
            button_obb(layout["button_xy"], float(button["scale"])),
            *board_obbs(layout["board"]["xy"], float(board["board_side"]), float(board["hole_side"])),
        ]
        placed: list[Any] = []
        for cube in layout["cubes"]:
            if not (
                _in_range(cube["xy"][0], center[0] - half[0] + CUBE_HALF_SIZE, center[0] + half[0] - CUBE_HALF_SIZE)
                and _in_range(cube["xy"][1], center[1] - half[1] + CUBE_HALF_SIZE, center[1] + half[1] - CUBE_HALF_SIZE)
            ):
                problems.append(f"{tag}: 方块 {cube['object_id']} 越界")
            if not _in_range(cube["yaw_rad"], 0.0, 2 * math.pi):
                problems.append(f"{tag}: 方块 {cube['object_id']} 朝向越界")
            candidate = cube_obb(cube["xy"][0], cube["xy"][1], CUBE_HALF_SIZE, cube["yaw_rad"], pad=CUBE_HALF_SIZE)
            if any(obb2d_intersect(*item, *candidate) for item in obstacles + placed):
                problems.append(f"{tag}: 方块 {cube['object_id']} 未满足 min_gap 或压在按钮／孔板上")
            placed.append(cube_obb(cube["xy"][0], cube["xy"][1], CUBE_HALF_SIZE, cube["yaw_rad"]))

        # 数量与动作
        if len(layout["cubes"]) != sum(objects["spawn_count"].values()):
            problems.append(f"{tag}: 方块数与 spawn_count 不符")
        if len(actions) != sum(objects["target_count"].values()):
            problems.append(f"{tag}: 动作数与 target_count 不符")
        colors = objects["colors_present"]
        if len(colors) != int(config["color"]):
            problems.append(f"{tag}: 场上颜色数与难度不符")
        for color, count in objects["spawn_count"].items():
            if count < objects["target_count"].get(color, 0):
                problems.append(f"{tag}: {color} 的生成数少于目标数")
        # B7：每种目标颜色抓的必须是该色生成列表最前面的几块
        by_color: dict[str, list[str]] = {}
        for cube in layout["cubes"]:
            by_color.setdefault(cube["color"], []).append(cube["object_id"])
        taken: dict[str, int] = {}
        for action in actions:
            object_id = action["pick"]
            color = next((c["color"] for c in layout["cubes"] if c["object_id"] == object_id), None)
            if color is None:
                problems.append(f"{tag}: 动作引用了不存在的方块 {object_id}")
                continue
            index = taken.get(color, 0)
            if by_color[color][index] != object_id:
                problems.append(f"{tag}: {color} 的第 {index} 次抓取不是生成列表最前面的一块")
            taken[color] = index + 1
        return problems

    if task == "RouteStick":
        walk = parameters["walk"]
        nodes = actions["nodes"]
        slots = actions["node_slots"]
        length_lo, length_hi = (int(v) for v in config["length"])
        if not length_lo <= objects["L"] <= length_hi:
            problems.append(f"{tag}: 段数越界")
        if len(nodes) != objects["L"] + 1 or len(actions["directions"]) != objects["L"]:
            problems.append(f"{tag}: 节点数或方向数与段数不符")
        node_indices = [int(v) for v in walk["node_indices"]]
        if any(node not in node_indices for node in nodes):
            problems.append(f"{tag}: 路线经过了非按钮节点")
        for i in range(len(slots) - 1):
            if abs(slots[i + 1] - slots[i]) != 1:
                problems.append(f"{tag}: 第 {i} 段不是相邻按钮")
            if not config["backtrack"] and i > 0 and slots[i + 1] == slots[i - 1]:
                # 不允许回退的难度里只有走到两端才可以被迫掉头
                if 0 < slots[i] < len(node_indices) - 1:
                    problems.append(f"{tag}: 第 {i} 段在非端点主动回退")
        if any(d not in (walk["direction"]["less_than"], walk["direction"]["otherwise"]) for d in actions["directions"]):
            problems.append(f"{tag}: 出现非法绕行方向")
        yaw = positions["yaw_deg"]
        if not _in_range(layout["rotation_deg"], -yaw["subtract"], -yaw["subtract"] + yaw["scale"]):
            problems.append(f"{tag}: 整排旋转角越界")
        if len(layout["obstacle_rgb"]) != int(positions["obstacle_color"]["count"]):
            problems.append(f"{tag}: 障碍柱颜色数不符")
        return problems

    if task in ("VideoUnmaskSwap", "VideoRepick"):
        is_unmask = task == "VideoUnmaskSwap"
        block = positions["containers"] if is_unmask else positions["easy_medium_cubes"]
        theta_lo, theta_hi = (float(v) for v in block["layout_rotation_range_rad"])
        if not _in_range(layout["theta_rad"], theta_lo, theta_hi):
            problems.append(f"{tag}: 整组旋转越界")
        region_half = float(block["region_half_size"])
        limit = region_half - ((CUBE_HALF_SIZE * 2.5 + 0.005) * 0.5 if is_unmask else CUBE_HALF_SIZE)
        anchors = rotate_xy([list(p) for p in block[layout["type"]]], layout["theta_rad"])
        items = layout["bins"] if is_unmask else layout["cubes"]
        if len(items) != len(anchors):
            problems.append(f"{tag}: 对象数与锚点数不符")
        for index, item in enumerate(items):
            dx = item["xy"][0] - anchors[index][0]
            dy = item["xy"][1] - anchors[index][1]
            if not (_in_range(dx, -limit, limit) and _in_range(dy, -limit, limit)):
                problems.append(f"{tag}: {item['object_id']} 的偏移超出上限 {limit}")
            if is_unmask and not _in_range(item["yaw_deg"], 0.0, float(block["yaw_scale_deg"])):
                problems.append(f"{tag}: {item['object_id']} 的朝向越界")
            if not is_unmask and not _in_range(item["yaw_rad"], 0.0, 2 * math.pi):
                problems.append(f"{tag}: {item['object_id']} 的朝向越界")
        swaps = actions["swap_pairs"]
        if len(swaps) != objects["n_swaps"]:
            problems.append(f"{tag}: 交换次数与 n_swaps 不符")
        for item in swaps:
            if item["initiator"] == item["partner"]:
                problems.append(f"{tag}: 交换发起者与搭档相同")
        if is_unmask:
            if len(objects["selected"]) != 3 or len(set(objects["selected"])) != 3:
                problems.append(f"{tag}: 藏物排序不是 3 个互异容器")
            if len(objects["pick_order"]) != objects["n_picks"]:
                problems.append(f"{tag}: 抓取个数与 n_picks 不符")
            if sorted(objects["hidden"]) != sorted(["red", "green", "blue"]):
                problems.append(f"{tag}: 藏物颜色不是红绿蓝三色")
            if len(objects["empty"]) != objects["n_bins"] - 3:
                problems.append(f"{tag}: 空容器数不符")
        else:
            if swaps and swaps[0]["initiator"] != objects["target"]:
                problems.append(f"{tag}: 首次交换不是由目标方块发起")
            if objects["target"] not in {item["object_id"] for item in items}:
                problems.append(f"{tag}: 目标方块不在场上")
            button = positions["button"]
            bx, by = (float(v) for v in button["center_xy"])
            rx, ry = (float(v) for v in button["randomize_range"])
            if not (_in_range(layout["button_xy"][0], bx - rx / 2, bx + rx / 2) and _in_range(layout["button_xy"][1], by - ry / 2, by + ry / 2)):
                problems.append(f"{tag}: 按钮越界")
        return problems

    problems.append(f"{tag}: 未知任务")
    return problems


def _check_collision(documents: dict[tuple[str, str], dict[str, Any]], verdicts: Verdicts) -> None:
    """几何描述对齐第 8.1 节，并对 500 条视频规格重跑初态与全部预定交换的连续检查。"""
    expected = [
        ([0.0, 0.0, 0.0], [0.02, 0.02, 0.02]),
        ([0.0, 0.0, 0.002], [0.0275, 0.0275, 0.002]),
        ([-0.0275, 0.0, 0.027], [0.0025, 0.0275, 0.025]),
        ([0.0275, 0.0, 0.027], [0.0025, 0.0275, 0.025]),
        ([0.0, -0.0275, 0.027], [0.0275, 0.0025, 0.025]),
        ([0.0, 0.0275, 0.027], [0.0275, 0.0025, 0.025]),
    ]
    shapes = bc.bin_shape_specs(CUBE_HALF_SIZE)
    geometry_ok = len(shapes) == len(expected) and len(bc.cube_shape_specs(CUBE_HALF_SIZE)) == 1
    for shape, (p, half) in zip(shapes, expected):
        geometry_ok = geometry_ok and all(abs(a - b) < 1e-12 for a, b in zip(shape.local_p, p))
        geometry_ok = geometry_ok and all(abs(a - b) < 1e-12 for a, b in zip(shape.half, half))
    verdicts.add(
        "COLLISION_GEOMETRY",
        geometry_ok,
        bin_shapes=len(shapes),
        cube_shapes=1,
        four_object_pairs=6,
        note="真实-actor-对照在步骤2冒烟",
    )

    specs = 0
    rejected = 0
    uncertified = 0
    worst = math.inf
    details: list[str] = []
    for (task, difficulty), doc in documents.items():
        if task not in ("VideoUnmaskSwap", "VideoRepick"):
            continue
        for record in doc["episodes"]:
            specs += 1
            states = _states_of(task, record)
            gap, rejection = bc.check_bin_layout(list(states.values()), stage="initial")
            if rejection is not None:
                rejected += 1
                uncertified += rejection.reason == "uncertified"
                details.append(f"{task}/{difficulty}/ep{record['episode']} 初态 {rejection.summary()}")
                continue
            worst = min(worst, gap)
            current = dict(states)
            for index, pair in enumerate(record["actions"]["swap_pairs"]):
                a = int(pair["initiator"].rsplit("_", 1)[1])
                b = int(pair["partner"].rsplit("_", 1)[1])
                bystanders = [state for key, state in sorted(current.items()) if key not in (a, b)]
                gap, rejection = bc.check_swap_sweep(current[a], current[b], bystanders, sweep_index=index)
                if rejection is not None:
                    rejected += 1
                    uncertified += rejection.reason == "uncertified"
                    details.append(f"{task}/{difficulty}/ep{record['episode']} 第 {index} 段 {rejection.summary()}")
                    break
                worst = min(worst, gap)
                sa, sb = current[a], current[b]
                current[a] = bc.ObjectState(sa.name, [sb.p[0], sb.p[1], sa.p[2]], sb.q, sa.shapes)
                current[b] = bc.ObjectState(sb.name, [sa.p[0], sa.p[1], sb.p[2]], sa.q, sb.shapes)
    verdicts.add(
        "COLLISION_SWEEP",
        rejected == 0,
        specs=specs,
        rejected=rejected,
        uncertified=uncertified,
        min_g_m=round(worst, 9) if math.isfinite(worst) else None,
    )
    if details:
        verdicts.records[-1]["detail"] = details[:10]


def _states_of(task: str, record: dict[str, Any]) -> dict[int, bc.ObjectState]:
    states: dict[int, bc.ObjectState] = {}
    if task == "VideoUnmaskSwap":
        for index, item in enumerate(record["layout"]["bins"]):
            p, q = bc.bin_actor_pose(item["xy"], item["yaw_deg"], CUBE_HALF_SIZE)
            states[index] = bc.ObjectState(item["object_id"], p, q, bc.bin_shape_specs(CUBE_HALF_SIZE))
    else:
        for index, item in enumerate(record["layout"]["cubes"]):
            p, q = bc.cube_actor_pose(item["xy"], item["yaw_rad"], CUBE_HALF_SIZE)
            states[index] = bc.ObjectState(item["object_id"], p, q, bc.cube_shape_specs(CUBE_HALF_SIZE))
    return states


def cmd_check(run_id: str, sampling_config: Path) -> dict[str, Any]:
    root, manifest, documents = load_group_documents(run_id)
    sampling = json.loads(sampling_config.read_text(encoding="utf-8"))
    if _sha256_file(sampling_config) != manifest["sampling_config_sha256"]:
        raise CampaignError("原值配置的散列与冻结时不符，拒绝在漂移的依据上验收")

    verdicts = Verdicts()
    started = time.monotonic()
    _check_scope(documents, verdicts)
    quota_report = _check_quota(documents, sampling, verdicts)
    _check_static_geometry(documents, sampling, verdicts)
    _check_collision(documents, verdicts)
    _check_reproducible(documents, sampling, manifest["generator_seed"], verdicts)

    payload = {
        "run_id": run_id,
        "elapsed_s": round(time.monotonic() - started, 1),
        "verdicts": verdicts.records,
        "quota_report": quota_report,
        "passed": verdicts.passed,
    }
    _write_json(root / "check_result.json", payload)
    for line in verdicts.lines:
        print(line)
    print(f"CHECK={'PASS' if verdicts.passed else 'FAIL'} elapsed_s={payload['elapsed_s']}")
    return payload


# ── compare：两个运行目录的 HDF5 逐位对拍 ───────────────────────────────────
def _index_h5(root: Path) -> dict[tuple[str, int], Path]:
    """按 ``(任务, episode)`` 索引一个运行目录下的全部 HDF5。

    清单模式下每组落在 ``<根>/<任务>/<难度>/hdf5_files/`` 里，单组模式落在
    ``<根>/hdf5_files/``，所以这里直接递归找，不假设层级。
    """
    index: dict[tuple[str, int], Path] = {}
    for path in sorted(root.rglob("hdf5_files/*.h5")):
        name = path.stem  # <任务>_ep<k>_seed<s>
        try:
            task, rest = name.split("_ep", 1)
            episode = int(rest.split("_seed", 1)[0])
        except (ValueError, IndexError):
            continue
        index[(task, episode)] = path
    return index


def cmd_compare(left_dir: Path, right_dir: Path, label: str) -> dict[str, Any]:
    """逐位比较两个运行目录里同名 episode 的完整 HDF5。

    复用 ``tests/_shared/native_sampling_parity.py::compare_h5``——它显式遍历全部
    group、dataset 及各层 attribute，检查类型、形状与内容。保持这个全集覆盖，
    不能只挑动作字段比较。

    只在一侧出现的 episode 单列为 ``only_left``／``only_right``，**不算通过**：
    少产物和内容不一致是两种不同的失败，不能互相掩盖。
    """
    from tests._shared.native_sampling_parity import compare_h5

    left = _index_h5(left_dir)
    right = _index_h5(right_dir)
    shared = sorted(set(left) & set(right))
    only_left = sorted(set(left) - set(right))
    only_right = sorted(set(right) - set(left))

    differences: list[dict[str, Any]] = []
    for key in shared:
        detail = compare_h5(left[key], right[key])
        if detail:
            differences.append({"task": key[0], "episode": key[1], "differences": detail[:20], "count": len(detail)})

    passed = not differences and not only_left and not only_right and bool(shared)
    payload = {
        "label": label,
        "left": str(left_dir),
        "right": str(right_dir),
        "compared": len(shared),
        "only_left": [f"{task}/ep{episode}" for task, episode in only_left],
        "only_right": [f"{task}/ep{episode}" for task, episode in only_right],
        "difference_episodes": differences,
        "passed": passed,
    }
    print(
        f"{label}={'PASS' if passed else 'FAIL'} compared={len(shared)} "
        f"differences={len(differences)} only_left={len(only_left)} only_right={len(only_right)}"
    )
    for item in differences[:5]:
        print(f"  {item['task']}/ep{item['episode']}: {item['count']} 处差异，首条 {item['differences'][0]}")
    return payload


# ── CLI ─────────────────────────────────────────────────────────────────────
def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="新值注入专项：规格生成、静态检查、出图与实跑编排")
    sub = parser.add_subparsers(dest="command", required=True)

    plan = sub.add_parser("plan", help="生成并冻结 11 组 × 100 条规格")
    plan.add_argument("--run-id", required=True)
    plan.add_argument("--seed", type=int, default=DEFAULT_SEED)
    plan.add_argument("--per-group", type=int, default=GROUP_SIZE)
    plan.add_argument("--sampling-config", default=str(DEFAULT_SAMPLING_CONFIG))

    check = sub.add_parser("check", help="从冻结规格独立重算全部计数与几何")
    check.add_argument("--run-id", required=True)
    check.add_argument("--sampling-config", default=str(DEFAULT_SAMPLING_CONFIG))

    plot = sub.add_parser("plot", help="出跑前／跑后三类图")
    plot.add_argument("--run-id", required=True)
    plot.add_argument("--phase", default="before", choices=("before", "after"))

    compare = sub.add_parser("compare", help="两个运行目录的完整 HDF5 逐位对拍")
    compare.add_argument("--left", required=True, help="参考侧目录")
    compare.add_argument("--right", required=True, help="候选侧目录")
    compare.add_argument("--label", default="COMPARE", help="判定行名，如 DEFAULT_PARITY")
    compare.add_argument("--out", default=None, help="把完整结果写到该 JSON")

    args = parser.parse_args(argv)
    try:
        if args.command == "plan":
            cmd_plan(args.run_id, args.seed, args.per_group, Path(args.sampling_config).resolve())
            return 0
        if args.command == "check":
            return 0 if cmd_check(args.run_id, Path(args.sampling_config).resolve())["passed"] else 1
        if args.command == "plot":
            from tests._shared.injection_plots import cmd_plot

            cmd_plot(args.run_id, args.phase)
            return 0
        if args.command == "compare":
            payload = cmd_compare(Path(args.left).resolve(), Path(args.right).resolve(), args.label)
            if args.out:
                _write_json(Path(args.out), payload)
            return 0 if payload["passed"] else 1
    except CampaignError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
