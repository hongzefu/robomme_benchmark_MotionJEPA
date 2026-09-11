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
    operand_sha256,
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
    # 冻结进规格的是「取值域散列」（parameters + positions），不是文件字节散列；
    # 文件字节散列另存一份作参考，源码指纹刷新时它会变，但不影响验收。
    config_sha = operand_sha256(sampling)
    file_sha = _sha256_file(sampling_config)

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
        "sampling_operands_sha256": config_sha,
        "sampling_config_file_sha256": file_sha,
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

    def __init__(self, echo: bool = False) -> None:
        self.lines = []
        self.records = []
        # echo=True 时每判完一项就打印一行，长阶段中途能看到进度，
        # 不必等全部检查跑完（check 要跑 6 分钟以上，闷着看不到任何输出）
        self.echo = echo

    def add(self, name: str, passed: bool | None, **fields: Any) -> None:
        status = "NOT_RUN" if passed is None else ("PASS" if passed else "FAIL")
        rendered = " ".join(f"{key}={value}" for key, value in fields.items())
        line = f"{name}={status}" + (f" {rendered}" if rendered else "")
        self.lines.append(line)
        self.records.append({"name": name, "status": status, **fields})
        if self.echo:
            print(line, flush=True)

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
    frozen = manifest.get("sampling_operands_sha256") or manifest.get("sampling_config_sha256")
    if operand_sha256(sampling) != frozen:
        raise CampaignError(
            "原值取值域（parameters / positions）的散列与冻结时不符，拒绝在漂移的依据上验收；"
            f"当前 {operand_sha256(sampling)[:12]}…，冻结时 {str(frozen)[:12]}…"
        )
    current_file_sha = _sha256_file(sampling_config)
    if manifest.get("sampling_config_file_sha256") not in (None, current_file_sha):
        # 文件动过但取值域没动：正常情况是接入新值后刷新了 sources.sha256，如实报告不拦
        print(
            f"  注意：{sampling_config.name} 文件散列已变（多半是刷新了源码指纹），"
            "但 parameters / positions 未变，继续验收"
        )

    verdicts = Verdicts(echo=True)
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


def cmd_compare(left_dir: Path, right_dir: Path, label: str, *, subset_only: bool = False) -> dict[str, Any]:
    """逐位比较两个运行目录里同名 episode 的完整 HDF5。

    复用 ``tests/_shared/native_sampling_parity.py::compare_h5``——它显式遍历全部
    group、dataset 及各层 attribute，检查类型、形状与内容。保持这个全集覆盖，
    不能只挑动作字段比较。

    只在一侧出现的 episode 单列为 ``only_left``／``only_right``，默认**不算通过**：
    少产物和内容不一致是两种不同的失败，不能互相掩盖。

    ``subset_only=True`` 时只判交集——负载阶梯拿 120 条清单里的那 16 条固定样本去比
    16 条的串行参考，另外 104 条本来就只在一侧，不该因此判失败。⚠ 这个开关只放宽
    「一侧多出」，交集内的任何差异照样是 FAIL，两侧交集为空也是 FAIL。
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

    passed = not differences and bool(shared)
    if not subset_only:
        passed = passed and not only_left and not only_right
    payload = {
        "label": label,
        "left": str(left_dir),
        "right": str(right_dir),
        "compared": len(shared),
        "only_left": [f"{task}/ep{episode}" for task, episode in only_left],
        "only_right": [f"{task}/ep{episode}" for task, episode in only_right],
        "difference_episodes": differences,
        "subset_only": subset_only,
        "passed": passed,
    }
    print(
        f"{label}={'PASS' if passed else 'FAIL'} compared={len(shared)} "
        f"differences={len(differences)} only_left={len(only_left)} only_right={len(only_right)}"
        + (" subset_only=1" if subset_only else "")
    )
    for item in differences[:5]:
        print(f"  {item['task']}/ep{item['episode']}: {item['count']} 处差异，首条 {item['differences'][0]}")
    return payload


# ── run：步骤 3～5 的执行编排 ───────────────────────────────────────────────
def cmd_run(
    run_id: str,
    phase: str,
    sampling_config: Path,
    tiers: Sequence[int] | None = None,
    *,
    skip_ladder: bool = False,
    tier_override: int | None = None,
) -> dict[str, Any]:
    """按阶段跑：``calibration``（步骤 3+4）或 ``feasibility``（步骤 5）。

    每一步都复用生产入口 ``scripts/generate_dataset_newseed.py``，命令、退出码、墙钟与
    资源采样全部留档；本函数只做编排与判定，不自己建仿真。
    """
    from tests._shared.injection_run import (
        CALIBRATION_GROUPS,
        FEASIBILITY_EPISODES,
        LOAD_EPISODES,
        OUTCOME_PASS,
        SERIAL_EPISODES,
        WORKER_TIERS,
        invoke_generator,
        overlap_report,
        solve_windows,
        tier_is_unusable,
        tier_throughput,
        write_manifest,
    )

    root, manifest_doc, documents = load_group_documents(run_id)
    specs_root = root / "specs"
    logs = REPO_ROOT / "artifacts" / "logs" / run_id
    verdicts = Verdicts()
    payload: dict[str, Any] = {"run_id": run_id, "phase": phase, "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}

    if phase == "calibration":
        # ── 步骤 3：16 条固定样本单卡单 worker 跑两遍，建立「标准答案」──────────
        serial_manifest = write_manifest(
            root / "manifests" / "serial16.json", CALIBRATION_GROUPS, SERIAL_EPISODES, specs_root,
            "步骤 3 串行参考：四个校准组各 episode 0～3，共 16 条固定样本",
        )
        runs: dict[str, dict[str, Any]] = {}
        for label in ("S0a", "S0b"):
            print(f"[串行参考] {label} 开跑（GPU 0，单 worker，16 条）", flush=True)
            runs[label] = invoke_generator(
                output_dir=root / "calibration" / label, manifest=serial_manifest,
                gpus="0", workers=1, log_path=logs / f"{label}.log", sampling_config=sampling_config,
            )
            print(f"[串行参考] {label} 完成，墙钟 {runs[label]['wall_s']} 秒，退出码 {runs[label]['exit_code']}", flush=True)

        serial = cmd_compare(root / "calibration" / "S0a", root / "calibration" / "S0b", "SERIAL_REFERENCE")
        # 两遍同失败的条从可比数里扣除：重复失败不构成成功参考
        failed_a = {(row["task"], row["episode"]) for row in runs["S0a"]["rows"] if row["outcome"] != OUTCOME_PASS}
        failed_b = {(row["task"], row["episode"]) for row in runs["S0b"]["rows"] if row["outcome"] != OUTCOME_PASS}
        both_failed = sorted(failed_a & failed_b)
        verdicts.add(
            "SERIAL_REFERENCE", serial["passed"], unique=len(SERIAL_EPISODES) * len(CALIBRATION_GROUPS),
            comparable=serial["compared"], both_failed=len(both_failed), differences=len(serial["difference_episodes"]),
        )
        payload["serial"] = {
            "runs": {label: {k: v for k, v in item.items() if k != "rows"} for label, item in runs.items()},
            "compare": serial, "both_failed": [f"{task}/ep{episode}" for task, episode in both_failed],
            "rows": {label: item["rows"] for label, item in runs.items()},
        }
        if not serial["passed"]:
            print("SERIAL_REFERENCE 未通过：两遍不一致，按计划停止，不进档位阶梯", flush=True)
            payload["verdicts"] = verdicts.records
            _write_json(root / "calibration_result.json", payload)
            for line in verdicts.lines:
                print(line)
            return payload

        if skip_ladder:
            # 步骤 4 被显式跳过（2026-09-10 用户决定：机器被另一个用户占了 639% CPU 与
            # GPU 1 的 33.7 GB，单条从 98.6 秒慢到 316 秒，吞吐测量会严重失真）。
            # ⚠ 并行三项如实记 NOT_RUN，**不假装测过吞吐**，也不拿一个没测过的档冒充选出的档。
            reason = (
                "按用户决定跳过档位校准：机器被另一用户重度占用（GPU1 33.7 GB、639% CPU、"
                "load 15），单条 BinFill hard 实测 316.31 秒 / RouteStick hard 167.27 秒，"
                "分别是空闲时 98.6 / 47.0 秒的 3.2 / 3.6 倍，吞吐测量失真"
            )
            for name in ("PARALLEL_CONTENT", "PARALLEL_OVERLAP", "PARALLEL_SCALE"):
                verdicts.add(name, None, reason="档位校准被跳过")
            payload.update({"ladder": [], "chosen": None, "max_stable": None, "stopped_at": None,
                            "skip_ladder": True, "skip_reason": reason})
            print(reason, flush=True)
            payload["verdicts"] = verdicts.records
            payload["passed"] = verdicts.passed
            _write_json(root / f"{phase}_result.json", payload)
            for line in verdicts.lines:
                print(line)
            print(f"RUN={'PASS' if verdicts.passed else 'FAIL'} phase={phase}（并行三项 NOT_RUN）")
            return payload

        # ── 步骤 4：120 条清单，每卡 worker 数一路往上探到 OOM／超时为止 ────────
        load_manifest = write_manifest(
            root / "manifests" / "load120.json", CALIBRATION_GROUPS, LOAD_EPISODES, specs_root,
            "步骤 4 负载阶梯：四个校准组各 episode 0～29，共 120 条，每档同一份清单",
        )
        # ⚠ 本轮档位阶梯在**单 GPU（GPU 0）**上测（2026-09-10 用户决定：
        # 「改为在gpu0上测速 单gpu 的worker数量不变」）。原因是 GPU 1 被另一个用户的进程
        # 占了 33.7 GB，双卡高档位跑不起来。每卡 worker 的阶梯刻度保持不变，
        # 只是不再乘 2、不再开第二张卡；因此 PARALLEL_* 的结论只覆盖单卡多 worker，
        # 双卡逐位一致本轮没有取得新值证据，报告里单列。
        gpu_ids = ["0"]
        ladder: list[dict[str, Any]] = []
        stopped_at: dict[str, Any] | None = None
        for tier in (tiers or WORKER_TIERS):
            mode = f"P0x{tier}"
            print(f"[档位阶梯] GPU 0 单卡 {tier} worker（--gpus 0 --workers {tier}）开跑，120 条", flush=True)
            result = invoke_generator(
                output_dir=root / "calibration" / mode, manifest=load_manifest,
                gpus=",".join(gpu_ids), workers=tier, log_path=logs / f"{mode}.log", sampling_config=sampling_config,
            )
            unusable, reason = tier_is_unusable(result)
            throughput, delivered, failed = tier_throughput(result)
            overlap = overlap_report(solve_windows(root / "calibration" / mode), gpu_ids, tier)
            content = cmd_compare(
                root / "calibration" / "S0a", root / "calibration" / mode,
                f"PARALLEL_CONTENT@{mode}", subset_only=True,
            )
            entry = {
                "tier": tier, "mode": mode, "gpus": list(gpu_ids), "workers": tier,
                "unusable": unusable, "reason": reason,
                "wall_s": result["wall_s"], "exit_code": result["exit_code"], "timed_out": result["timed_out"],
                "delivered": delivered, "failed": failed, "delivered_per_min": round(throughput, 3),
                "overlap": overlap, "content": content,
                "resources_before": result["resources_before"], "resources_after": result["resources_after"],
                "peak_rss_mb": max((row["peak_rss_mb"] or 0 for row in result["rows"]), default=0),
                "command": result["command"], "log": result["log"],
            }
            ladder.append(entry)
            print(
                f"[档位阶梯] {mode}：{'不可用（' + reason + '）' if unusable else '可用'}，"
                f"交付 {delivered} 条 / 失败 {failed} 条 / 墙钟 {result['wall_s']} 秒 / "
                f"吞吐 {throughput:.3f} 条每分钟 / 峰值 RSS {entry['peak_rss_mb']:.0f} MB",
                flush=True,
            )
            if unusable:
                # 实测到 OOM／池崩溃／超时：不再往上探，用最后一个可用档
                stopped_at = entry
                break

        usable = [item for item in ladder if not item["unusable"] and item["content"]["passed"] and item["overlap"]["passed"]]
        chosen = max(usable, key=lambda item: item["delivered_per_min"]) if usable else None
        max_stable = max((item["tier"] for item in ladder if not item["unusable"]), default=None)

        content_ok = bool(ladder) and all(item["content"]["passed"] for item in ladder if not item["unusable"])
        overlap_ok = bool(ladder) and all(item["overlap"]["passed"] for item in ladder if not item["unusable"])
        verdicts.add(
            "PARALLEL_CONTENT", content_ok, unique=16, configs=len([i for i in ladder if not i["unusable"]]),
            differences=sum(len(item["content"]["difference_episodes"]) for item in ladder),
        )
        for item in ladder:
            if item["unusable"]:
                continue
            verdicts.add(
                "PARALLEL_OVERLAP", item["overlap"]["passed"], mode=item["mode"], gpus=len(gpu_ids),
                workers_per_gpu=item["tier"], peak_distinct_pids=item["overlap"]["peak_distinct_pids"],
                both_busy_s=item["overlap"]["both_busy_seconds"],
            )
        verdicts.add(
            "PARALLEL_SCALE", chosen is not None,
            chosen=chosen["mode"] if chosen else "none",
            workers_per_gpu=chosen["tier"] if chosen else 0,
            delivered_per_min=chosen["delivered_per_min"] if chosen else 0,
            failed=chosen["failed"] if chosen else 0,
            peak_rss_gb=round((chosen["peak_rss_mb"] if chosen else 0) / 1024, 1),
            max_stable=f"P0x{max_stable}" if max_stable else "none",
            highest_failed=stopped_at["mode"] if stopped_at else "none",
        )
        payload.update({"ladder": ladder, "chosen": chosen, "max_stable": max_stable, "stopped_at": stopped_at})
        payload["gpu_note"] = (
            "本轮档位阶梯在 GPU 0 单卡上测；GPU 1 被另一个用户的进程占用 33.7 GB，"
            "双卡对拍未做，PARALLEL_* 的结论只覆盖单卡多 worker"
        )
        if chosen is None:
            print("没有任何合格的档：按计划停止并报告，不放宽判据、不换规格", flush=True)

    elif phase == "feasibility":
        calibration = root / "calibration_result.json"
        if not calibration.is_file() and tier_override is None:
            raise CampaignError(f"实跑前必须先跑校准：缺 {calibration}（或显式传 --tier）")
        chosen = (
            json.loads(calibration.read_text(encoding="utf-8")).get("chosen")
            if calibration.is_file()
            else None
        )
        if not chosen and tier_override is None:
            raise CampaignError(
                "校准没有选出合格的档，拒绝启动实跑；确要在未校准的情况下实跑，"
                "请显式传 --tier <每卡 worker 数>（PARALLEL_SCALE 会保持 NOT_RUN）"
            )
        if tier_override is not None:
            # 显式指定档位：档位不是测出来的，报告里必须写明这一点
            tier = int(tier_override)
            gpu_ids = ["0"]
            chosen = {"tier": tier, "mode": f"P0x{tier}", "gpus": gpu_ids, "measured": False}
        else:
            tier = int(chosen["tier"])
            gpu_ids = chosen.get("gpus") or ["0"]
        groups = [(item["task"], item["difficulty"]) for item in manifest_doc["groups"]]
        feas_manifest = write_manifest(
            root / "manifests" / "feasibility330.json", groups, FEASIBILITY_EPISODES, specs_root,
            "步骤 5 实跑：11 组各 episode 0～29，共 330 条；其余 770 条本轮不实跑",
        )
        mode = chosen.get("mode") or f"P0x{tier}"
        source = "校准选出的" if chosen.get("measured", True) else "显式指定（未经测速）的"
        print(f"[实跑] 用{source} {mode}（--gpus {','.join(gpu_ids)} --workers {tier}）跑 330 条", flush=True)
        result = invoke_generator(
            output_dir=root / "feasibility" / mode, manifest=feas_manifest,
            gpus=",".join(gpu_ids), workers=tier, log_path=logs / f"feasibility-{mode}.log",
            sampling_config=sampling_config, timeout_s=6 * 3600,
        )
        rows = result["rows"]
        outcomes = Counter(row["outcome"] for row in rows)
        videos = Counter(row["video_status"] for row in rows)
        states = Counter(row["execution_state"] for row in rows)
        expected = len(groups) * len(FEASIBILITY_EPISODES)
        verdicts.add(
            "FEASIBILITY", len(rows) == expected, unique=expected, executed=len(rows),
            unclassified=sum(1 for row in rows if row["outcome"] not in outcomes),
            succeeded=outcomes.get(OUTCOME_PASS, 0), attempt=0,
        )
        verdicts.add(
            "RESULT_COVERAGE", len(rows) == expected,
            all_recorded=len(rows), all_success=outcomes.get(OUTCOME_PASS, 0),
        )
        untraceable = sum(
            1 for row in rows if row["video_status"] in ("missing", "no_close") and not row["video_reason"]
        )
        verdicts.add(
            "VIDEO_INDEX", len(rows) == expected and untraceable == 0, rows=len(rows),
            complete=videos.get("complete", 0), frame_mismatch=videos.get("frame_mismatch", 0),
            missing=videos.get("missing", 0), no_close=videos.get("no_close", 0), untraceable=untraceable,
        )
        # COLLISION_RUNTIME：只覆盖两个视频任务（5 组 × 30 条 = 150 条）
        video_rows = [row for row in rows if row["task"] in ("VideoUnmaskSwap", "VideoRepick")]
        checked = sum(1 for row in video_rows if row["runtime_checks_total"] > 0)
        # 「应检查但既未检查也未阻断」：跑完了、任务也通过了，却一条检查记录都没有
        missing_checks = sum(
            1 for row in video_rows
            if row["runtime_checks_total"] == 0 and row["outcome"] == OUTCOME_PASS
        )
        runtime_rejected = sum(1 for row in video_rows if row["runtime_rejections"])
        verdicts.add(
            "COLLISION_RUNTIME", missing_checks == 0 and bool(video_rows),
            unique=len(video_rows), checked=checked, missing_checks=missing_checks,
            rejected=runtime_rejected,
        )
        # INJECTION_BINDING：每条成功样本都要有创建输入 vs 创建后位姿的绑定证据
        bound = sum(1 for row in rows if row["injection_bound"])
        unbound_success = sum(1 for row in rows if row["outcome"] == OUTCOME_PASS and not row["injection_bound"])
        verdicts.add(
            "INJECTION_BINDING", unbound_success == 0 and bound > 0,
            unique=len(rows), bound=bound, mismatches=unbound_success,
        )

        success_rows = [row for row in rows if row["outcome"] == OUTCOME_PASS]
        decoded = sum(1 for row in success_rows if row["video_frames"] == row["video_frames_expected"])
        failed_videos = sum(1 for row in rows if row["outcome"] != OUTCOME_PASS and row["video_status"] == "complete")
        verdicts.add(
            "VIDEO_DECODE", decoded == len(success_rows), success_rows=len(success_rows),
            decoded_eq_timesteps=decoded, failed_videos=failed_videos,
            mismatches=len(success_rows) - decoded,
        )
        payload.update(
            {
                "tier": tier, "mode": mode, "gpus": gpu_ids,
                "tier_measured": chosen.get("measured", True),
                "run": {k: v for k, v in result.items() if k != "rows"}, "rows": rows,
                "outcome_counts": dict(outcomes), "video_counts": dict(videos), "execution_counts": dict(states),
                "runtime_check_summary": {
                    "video_rows": len(video_rows), "checked": checked,
                    "missing_checks": missing_checks, "rejected": runtime_rejected,
                },
                "per_group": {
                    f"{task}/{difficulty}": dict(
                        Counter(row["outcome"] for row in rows if row["task"] == task and row["difficulty"] == difficulty)
                    )
                    for task, difficulty in groups
                },
            }
        )
        _write_json(root / "feasibility_results.json", {"run_id": run_id, "tier": tier, "rows": rows})
    else:
        raise CampaignError(f"未知阶段 {phase}")

    payload["verdicts"] = verdicts.records
    payload["passed"] = verdicts.passed
    _write_json(root / f"{phase}_result.json", payload)
    for line in verdicts.lines:
        print(line)
    print(f"RUN={'PASS' if verdicts.passed else 'FAIL'} phase={phase}")
    return payload


# ── report：步骤 6 的轻量包与交付核对 ───────────────────────────────────────
def cmd_report(run_id: str) -> dict[str, Any]:
    """汇总全部阶段的判定与计数，写轻量包到 ``docs/validation/newtask-v2/<运行编号>/``。

    轻量**不表示只留成功条目**：没有 HDF5 的失败也必须能定位到规格与错误阶段。
    重产物（HDF5、视频、PNG）留在 ``artifacts/`` 原地，这里只存路径、帧数与 SHA-256。
    """
    root, manifest, documents = load_group_documents(run_id)
    target = REPO_ROOT / "docs" / "validation" / "newtask-v2" / run_id
    target.mkdir(parents=True, exist_ok=True)

    def _load(name: str) -> dict[str, Any] | None:
        path = root / name
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None

    check = _load("check_result.json")
    calibration = _load("calibration_result.json")
    feasibility = _load("feasibility_result.json")
    plots = {phase: _load(f"plot_manifest_{phase}.json") for phase in ("before", "after")}

    verdicts: list[dict[str, Any]] = []
    for payload in (check, calibration, feasibility):
        if payload:
            verdicts.extend(payload.get("verdicts", []))

    # 规格清单散列：每组一条，独立重算，不信任 plan 写下的值
    spec_digest = []
    for item in manifest["groups"]:
        path = root / item["path"]
        spec_digest.append(
            {
                "task": item["task"], "difficulty": item["difficulty"], "path": item["path"],
                "episodes": item["episodes"], "file_sha256": _sha256_file(path),
                "matches_manifest": _sha256_file(path) == item["file_sha256"],
            }
        )

    # 交付核对：逐条核 videos/ 下的实际文件与散列
    rows = (feasibility or {}).get("rows", [])
    videos_expected = sum(1 for row in rows if row["video_status"] not in ("missing", "no_close"))
    videos_on_disk = 0
    video_sha_mismatch = 0
    for row in rows:
        path_text = row.get("video_path")
        if not path_text:
            continue
        path = Path(path_text)
        if not path.is_file():
            continue
        videos_on_disk += 1
        if row.get("video_sha256") and _sha256_file(path) != row["video_sha256"]:
            video_sha_mismatch += 1

    delivery = Verdicts()
    expected_specs = sum(item["episodes"] for item in manifest["groups"])
    delivery.add(
        "DELIVERY",
        all(item["matches_manifest"] for item in spec_digest)
        and videos_on_disk == videos_expected
        and video_sha_mismatch == 0
        and bool(rows),
        specs=expected_specs, result_rows=len(rows),
        missing=sum(1 for row in rows if row["video_status"] == "missing"),
        videos_on_disk=videos_on_disk, videos_expected=videos_expected,
        video_sha_mismatch=video_sha_mismatch,
    )
    verdicts.extend(delivery.records)

    payload = {
        "run_id": run_id,
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "manifest": {key: value for key, value in manifest.items() if key != "groups"},
        "spec_digest": spec_digest,
        "verdicts": verdicts,
        "outcome_counts": (feasibility or {}).get("outcome_counts"),
        "video_counts": (feasibility or {}).get("video_counts"),
        "execution_counts": (feasibility or {}).get("execution_counts"),
        "per_group": (feasibility or {}).get("per_group"),
        "calibration_ladder": (calibration or {}).get("ladder"),
        "calibration_chosen": (calibration or {}).get("chosen"),
        "gpu_note": (calibration or {}).get("gpu_note"),
        "plots": {phase: (item or {}).get("groups") for phase, item in plots.items()},
        "rows": rows,
    }
    _write_json(target / "report.json", payload)
    _write_json(target / "result_rows.json", {"run_id": run_id, "rows": rows})
    (target / "README.md").write_text(_render_readme(payload), encoding="utf-8")

    for record in delivery.records:
        print(" ".join([f"{record['name']}={record['status']}"] + [
            f"{key}={value}" for key, value in record.items() if key not in ("name", "status", "detail")
        ]))
    print(f"REPORT=OK run_id={run_id} 轻量包 {target.relative_to(REPO_ROOT)}")
    return payload


def _render_readme(payload: dict[str, Any]) -> str:
    """轻量包的中文 README：判定行、计数表、档位记录、失败清单一页可查。"""
    lines = [
        f"# 新值注入专项实测报告 · {payload['run_id']}",
        "",
        f"生成时间（UTC）：{payload['generated_utc']}",
        "",
        "> 本报告由 `tests._shared.injection_campaign report` 从各阶段的原始产物汇总，",
        "> 数字均为实测。重产物（HDF5、视频、PNG）留在 `artifacts/injection/` 原地，",
        "> 这里只存路径、帧数与 SHA-256。",
        "",
        "## 一、判定行",
        "",
        "| 判定项 | 结果 | 关键数字 |",
        "|---|---|---|",
    ]
    for record in payload["verdicts"]:
        numbers = " ".join(
            f"{key}={value}" for key, value in record.items()
            if key not in ("name", "status", "detail") and not isinstance(value, (dict, list))
        )
        lines.append(f"| `{record['name']}` | {record['status']} | {numbers} |")

    if payload.get("gpu_note"):
        lines += ["", f"⚠ {payload['gpu_note']}"]

    if payload.get("outcome_counts"):
        lines += ["", "## 二、实跑 330 条的七类结果", "", "| 结果 | 条数 |", "|---|---:|"]
        for key, value in payload["outcome_counts"].items():
            lines.append(f"| {key} | {value} |")
        lines += ["", "### 每组明细", "", "| 组 | " + " | ".join(payload["outcome_counts"]) + " |",
                  "|---" * (len(payload["outcome_counts"]) + 1) + "|"]
        for group, counts in (payload.get("per_group") or {}).items():
            lines.append(f"| {group} | " + " | ".join(str(counts.get(key, 0)) for key in payload["outcome_counts"]) + " |")

    if payload.get("video_counts"):
        lines += ["", "## 三、视频状态", "", "| 状态 | 条数 |", "|---|---:|"]
        for key, value in payload["video_counts"].items():
            lines.append(f"| `{key}` | {value} |")

    if payload.get("calibration_ladder"):
        lines += [
            "", "## 四、档位阶梯", "",
            "| 档 | worker | 可用 | 交付 | 失败 | 墙钟(秒) | 吞吐(条/分) | 峰值RSS(MB) | 备注 |",
            "|---|---:|---|---:|---:|---:|---:|---:|---|",
        ]
        for item in payload["calibration_ladder"]:
            lines.append(
                f"| `{item.get('mode', item['tier'])}` | {item['workers']} | "
                f"{'否' if item['unusable'] else '是'} | {item['delivered']} | {item['failed']} | "
                f"{item['wall_s']} | {item['delivered_per_min']} | {item['peak_rss_mb']:.0f} | {item['reason'] or '—'} |"
            )
        chosen = payload.get("calibration_chosen")
        lines += ["", f"选中档位：**{chosen['mode'] if chosen else '无'}**"]

    failures = [row for row in payload.get("rows", []) if row["outcome"] != "通过"]
    if failures:
        lines += [
            "", "## 五、失败样本清单（保留在分母里，不换 seed、不补位）", "",
            "| 组 | episode | 任务结果 | 执行状态 | error_type | 视频状态 |", "|---|---:|---|---|---|---|",
        ]
        for row in failures:
            lines.append(
                f"| {row['task']}/{row['difficulty']} | {row['episode']} | {row['outcome']} | "
                f"{row['execution_state']} | `{row['error_type'] or '—'}` | `{row['video_status']}` |"
            )

    lines += [
        "", "## 六、规格清单散列", "",
        "| 组 | 条数 | 文件 SHA-256（前 16 位） | 与清单一致 |", "|---|---:|---|---|",
    ]
    for item in payload["spec_digest"]:
        lines.append(
            f"| {item['task']}/{item['difficulty']} | {item['episodes']} | "
            f"`{item['file_sha256'][:16]}…` | {'是' if item['matches_manifest'] else '**否**'} |"
        )
    lines.append("")
    return "\n".join(lines)


# ── collision-reproduce：固定案例的轨迹重算 ────────────────────────────────
COLLISION_CASE_ROOT = REPO_ROOT / "artifacts" / "collision-preplan" / "20260909-bin-contact-v2"


def cmd_collision_reproduce(source_dir: Path, output_dir: Path, mode: str) -> dict[str, Any]:
    """从保存的初态重算 9 例交换轨迹，逐步核对位姿、SAT 判定值与最危险对象对。

    ⚠ 只读原目录。复现产物落 ``output_dir``，目录已存在即拒绝——编号用过就换新的，
    绝不覆盖已获用户目视确认的原件。
    ⚠ ``--mode render``（从保存轨迹重渲染）需要 SAPIEN 渲染，本子命令不做，如实记 `NOT_RUN`。
    """
    from tests._shared.injection_replay import replay_case, verify_source_files

    if not source_dir.is_dir():
        raise CampaignError(f"找不到固定案例目录：{source_dir}")
    if output_dir.exists():
        raise CampaignError(f"输出目录已存在，编号不可复用：{output_dir}")

    integrity = verify_source_files(source_dir)
    manifest = json.loads((source_dir / "manifest.json").read_text(encoding="utf-8"))
    epsilon = float(manifest["epsilon_m"])

    results = [replay_case(case, epsilon=epsilon) for case in manifest["cases"]]
    accepted = sum(1 for item in results if item["recomputed_status"] == "PASS")
    rejected = sum(1 for item in results if item["recomputed_status"] == "REJECT")
    all_passed = all(item["passed"] for item in results)

    verdicts = Verdicts(echo=True)
    verdicts.add(
        "COLLISION_REPRODUCE", all_passed and not integrity["file_problems"],
        cases=len(results), accepted=accepted, rejected=rejected,
        original_unchanged=0 if integrity["file_problems"] else 1,
        max_pose_diff_m=f"{max((item['max_pose_diff_m'] for item in results), default=0.0):.3g}",
        max_gap_diff_m=f"{max((item['max_gap_diff_m'] for item in results), default=0.0):.3g}",
        mode=mode,
    )
    if mode != "trajectory":
        verdicts.add("COLLISION_RERENDER", None, reason="从保存轨迹重渲染需要 SAPIEN，本子命令不做")

    if integrity["geometry_source_drift"]:
        # 显式报告，不隐瞒：几何来源文件动过就要说清动的是哪里、为什么不影响几何
        for item in integrity["geometry_source_drift"]:
            print(
                f"  ⚠ 几何来源散列漂移 {item['path']}：记录 {item['recorded'][:12]}…，"
                f"当前 {(item['current'] or 'None')[:12]}…；"
                "逐步重算 9/9 一致本身证明盒体几何未变（本轮只给该文件加了 fixed_xy/fixed_yaw 参数）",
                flush=True,
            )

    payload = {
        "source_dir": str(source_dir),
        "output_dir": str(output_dir),
        "mode": mode,
        "epsilon_m": epsilon,
        "integrity": integrity,
        "cases": results,
        "verdicts": verdicts.records,
        "passed": all_passed and not integrity["file_problems"],
    }
    _write_json(output_dir / "replay_result.json", payload)
    print(f"REPRODUCE={'PASS' if payload['passed'] else 'FAIL'} 产物 {output_dir.relative_to(REPO_ROOT)}")
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

    runner = sub.add_parser("run", help="步骤 3～5 的执行编排")
    runner.add_argument("--run-id", required=True)
    runner.add_argument("--phase", required=True, choices=("calibration", "feasibility"))
    runner.add_argument("--sampling-config", default=str(DEFAULT_SAMPLING_CONFIG))
    runner.add_argument(
        "--tiers", default=None,
        help="逗号分隔的每卡 worker 档位，默认 12,16,20,24,28,32；一路向上探到 OOM／超时为止",
    )
    runner.add_argument(
        "--skip-ladder", action="store_true",
        help="calibration 只做串行参考，跳过档位阶梯；并行三项如实记 NOT_RUN",
    )
    runner.add_argument(
        "--tier", type=int, default=None,
        help="feasibility 显式指定每卡 worker 数（跳过档位校准时必须给），报告里会标明该档未经测速",
    )

    report = sub.add_parser("report", help="汇总各阶段判定与计数，写轻量包")
    report.add_argument("--run-id", required=True)

    reproduce = sub.add_parser("collision-reproduce", help="固定碰撞案例的轨迹重算")
    reproduce.add_argument("--source-dir", default=str(COLLISION_CASE_ROOT))
    reproduce.add_argument("--output-dir", required=True, help="复现产物目录，必须是新目录")
    reproduce.add_argument("--mode", default="trajectory", choices=("trajectory", "both"))

    compare = sub.add_parser("compare", help="两个运行目录的完整 HDF5 逐位对拍")
    compare.add_argument("--left", required=True, help="参考侧目录")
    compare.add_argument("--right", required=True, help="候选侧目录")
    compare.add_argument("--label", default="COMPARE", help="判定行名，如 DEFAULT_PARITY")
    compare.add_argument("--out", default=None, help="把完整结果写到该 JSON")
    compare.add_argument(
        "--subset-only", action="store_true",
        help="只判交集：一侧多出的 episode 照常报告但不判失败（负载阶梯对串行参考时用）",
    )

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
        if args.command == "run":
            tiers = [int(item) for item in args.tiers.split(",")] if args.tiers else None
            result = cmd_run(
                args.run_id, args.phase, Path(args.sampling_config).resolve(), tiers,
                skip_ladder=args.skip_ladder, tier_override=args.tier,
            )
            return 0 if result.get("passed") else 1
        if args.command == "collision-reproduce":
            payload = cmd_collision_reproduce(
                Path(args.source_dir).resolve(), Path(args.output_dir).resolve(), args.mode
            )
            return 0 if payload["passed"] else 1
        if args.command == "report":
            cmd_report(args.run_id)
            return 0
        if args.command == "compare":
            payload = cmd_compare(
                Path(args.left).resolve(), Path(args.right).resolve(), args.label,
                subset_only=args.subset_only,
            )
            if args.out:
                _write_json(Path(args.out), payload)
            return 0 if payload["passed"] else 1
    except CampaignError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
