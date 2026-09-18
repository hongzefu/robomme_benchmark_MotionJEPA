"""候选筛查：沿用旧检查算法，逐条观测另行归并。"""
from __future__ import annotations
import math
from collections import Counter
from typing import Any, Sequence
from robomme.robomme_env.utils import bin_collision as bc
from .categories import legal_categories, observed_values
from .contract import Contract, audit_overrides, derive_all
from .sampling import COARSE_BINS, GROUP_SIZE
from .specs import (CUBE_HALF_SIZE, SPEC_SCHEMA_VERSION, EXCLUDED_GROUPS, build_group,
                   record_sha256, rotate_xy, button_obb, board_obbs, cube_obb, obb2d_intersect, canonical_json)

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

    def add_record(self, name: str, passed: bool | None, fields: dict[str, Any]) -> None:
        """按字典汇入：字段名可与 ``add`` 的形参（如 ``passed``）同名，env-check 的判定行就有 passed 计数。"""
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


def _blocks_of(doc: dict[str, Any]) -> int:
    """规格文档由几个 100 条 block 组成；07/09 的文档没有 ``blocks`` 键，即 1。"""
    return int(doc.get("blocks", 1))


def _check_scope(documents: dict[tuple[str, str], dict[str, Any]], verdicts: Verdicts) -> None:
    problems: list[str] = []
    total = 0
    blocks_seen: set[int] = set()
    for (task, difficulty), doc in documents.items():
        episodes = doc["episodes"]
        total += len(episodes)
        blocks = _blocks_of(doc)
        blocks_seen.add(blocks)
        numbers = [item["episode"] for item in episodes]
        # 多 block 时 episode 号恰为 range(blocks × 100)；文档写的 blocks 与条数不符也算问题
        if blocks < 1 or sorted(numbers) != list(range(GROUP_SIZE * blocks)):
            problems.append(f"{task}/{difficulty} 的 episode 号有缺号／重复／越界（blocks={blocks}）")
        for item in episodes:
            if item["task"] != task or item["difficulty"] != difficulty:
                problems.append(f"{task}/{difficulty}/episode {item['episode']} 的任务或难度不符")
            if record_sha256(item) != item["spec_sha256"]:
                problems.append(f"{task}/{difficulty}/episode {item['episode']} 的 spec_sha256 不符")
    excluded_present = [key for key in documents if list(key) in [list(e) for e in EXCLUDED_GROUPS]]
    if excluded_present:
        problems.append(f"排除组仍被生成：{excluded_present}")
    fields: dict[str, Any] = {"groups": len(documents), "specs": total}
    if blocks_seen != {1}:
        # 只在有多 block 组时打 blocks 字段，07/09 的判定行逐字不变
        fields["blocks"] = "/".join(str(b) for b in sorted(blocks_seen))
    verdicts.add(
        "SPEC_SCOPE",
        not problems,
        **fields,
        excluded="+".join(f"{task}-{difficulty}" for task, difficulty in EXCLUDED_GROUPS),
        problems=len(problems),
    )
    if problems:
        verdicts.records[-1]["detail"] = problems[:10]


def _check_reproducible(
    documents: dict[tuple[str, str], dict[str, Any]], sampling: dict[str, Any], contract: Contract, seed: int, verdicts: Verdicts
) -> None:
    """同 seed、**不同组调度顺序**独立再生成一次，逐记录散列必须相同。"""
    compared = 0
    differences = 0
    for task, difficulty in reversed(list(documents)):  # 按清单倒序调度全部组，证明结果与顺序无关
        doc = documents[(task, difficulty)]
        rebuilt = build_group(task, difficulty, sampling, contract, seed, blocks=_blocks_of(doc))
        frozen = doc["episodes"]
        # ⚠ 两边条数不一致也是差异：zip 会静默截断，blocks 记错时会被判成 PASS
        if len(frozen) != len(rebuilt.episodes):
            differences += abs(len(frozen) - len(rebuilt.episodes))
        for left, right in zip(frozen, rebuilt.episodes):
            compared += 1
            if left != right or record_sha256(left) != left["spec_sha256"] or record_sha256(right) != right["spec_sha256"]:
                differences += 1
    verdicts.add("SPEC_REPRODUCIBLE", differences == 0, compared=compared, differences=differences)


def _check_contract_derived(contract: Contract, sampling: dict[str, Any], verdicts: Verdicts) -> None:
    """契约里每个带派生表达式的域用 native_sampling.json 回算；不一致项必须全部落在 overrides 白名单里。"""
    mismatches, checked = derive_all(contract, sampling)
    _, problems = audit_overrides(contract, sampling)
    verdicts.add(
        "CONTRACT_DERIVED", not problems, fields=checked, mismatches=len(mismatches),
        overrides=len(contract.overrides), version=contract.version, problems=len(problems),
    )
    if problems:
        verdicts.records[-1]["detail"] = problems[:10]


def _check_quota(
    documents: dict[tuple[str, str], dict[str, Any]], contract: Contract, verdicts: Verdicts
) -> dict[str, Any]:
    """独立类别按完整合法集合补零后计数差 ≤1；连续量验粗箱与批次覆盖。"""
    gaps: list[str] = []
    report: dict[str, Any] = {}
    blocks_seen: set[int] = set()
    for (task, difficulty), doc in documents.items():
        categories = legal_categories(task, difficulty, contract)
        blocks = _blocks_of(doc)
        blocks_seen.add(blocks)
        # 多 block 时按 block 切片各自判（每个 block 自成一份 100 条均衡样本；两个各自 spread≤1 的 block
        # 合并后可能 spread=2，整组判会假阳）。blocks=1 时 report 形状与此前逐字相同。
        ordered = sorted(doc["episodes"], key=lambda item: int(item["episode"]))
        block_reports: list[dict[str, Any]] = []
        for block in range(blocks):
            block_reports.append(
                _quota_block_report(task, difficulty, categories, ordered[block * GROUP_SIZE : (block + 1) * GROUP_SIZE], gaps, block if blocks > 1 else None)
            )
        report[f"{task}/{difficulty}"] = block_reports[0] if blocks == 1 else {"blocks": block_reports}

    fields: dict[str, Any] = {"groups": len(documents), "batches": COARSE_BINS}
    if blocks_seen != {1}:
        fields["blocks"] = "/".join(str(b) for b in sorted(blocks_seen))
    verdicts.add("COVERAGE_QUOTA", not gaps, **fields, quota_gaps=len(gaps))
    if gaps:
        verdicts.records[-1]["detail"] = gaps[:10]
    return report


def _quota_block_report(
    task: str,
    difficulty: str,
    categories: dict[str, Any],
    records: Sequence[dict[str, Any]],
    gaps: list[str],
    block: int | None,
) -> dict[str, Any]:
    """一个 100 条 block 的配额报告；``block`` 为 None 表示单 block 组（报错文案不带 block 号）。"""
    where = f"{task}/{difficulty}" + (f"/block{block}" if block is not None else "")
    counts: dict[str, Counter] = {}
    for record in records:
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
            gaps.append(f"{where} 的 {field} 计数差 {spread} > 1")

    for field, legal in categories["coupled"].items():
        observed = counts.get(field, Counter())
        table = dict(observed)
        uncovered = [canonical_json(v) for v in legal if canonical_json(v) not in table]
        group_report["coupled"][field] = {"counts": table, "uncovered": uncovered}

    # 连续量：从 sampling_cells 独立重算粗箱与批次覆盖
    cells: dict[str, list[int]] = {}
    for record in records:
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
            gaps.append(f"{where} 的连续量 {name} 分箱或批次覆盖不达标")
    return group_report


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
        # 第 k 段发起者 = 循环基 swap_initiators[k mod 3]（xhard 4～5 次时循环沿用；≤3 次时与逐个取用等价）
        initiators = objects["swap_initiators"]
        for index, item in enumerate(swaps):
            if not initiators or item["initiator"] != initiators[index % len(initiators)]:
                problems.append(f"{tag}: 第 {index} 段发起者不是 swap_initiators[{index} mod {len(initiators)}]")
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


class ObservationCollector:
    """逐次接收真实尝试；完整拒绝落流，内存只保存每条候选计数。"""

    def __init__(self, rejection_stream):
        self.stream = rejection_stream
        self.episodes = {}

    def __call__(self, event):
        import json
        key = (event["task"], event["difficulty"], event["episode"])
        counters = self.episodes.setdefault(key, {"candidates_tried": 0, "accepted": 0,
            "rejected_before_accept": {name: 0 for name in ("geometry", "contact", "numerical_boundary", "uncertified")}})
        counters["candidates_tried"] += 1
        if event["reason"] is None:
            counters["accepted"] += 1
        else:
            counters["rejected_before_accept"][event["reason"]] += 1
            self.stream.write(json.dumps(event, ensure_ascii=False, allow_nan=False) + "\n")

    def screening(self, record, origin):
        key = (record["task"], record["difficulty"], record["episode"])
        collision = record.get("collision", {})
        result = {"geometry": "PASS", "collision_initial": collision.get("initial"),
                  "collision_sweeps": collision.get("sweeps"), "min_g_m": collision.get("min_g_m"),
                  "evidence_origin": origin}
        if record["task"] == "RouteStick":
            if key in self.episodes:
                raise ValueError("RouteStick 不应存在拒绝采样观测")
            return {**result, "count_unit": "not_applicable", "candidates_tried": None,
                    "accepted": None, "rejected_before_accept": None}
        counters = self.episodes[key]
        accepted = len(record["layout"]["cubes"]) if record["task"] == "BinFill" else 1
        if counters["accepted"] != accepted or counters["candidates_tried"] != accepted + sum(counters["rejected_before_accept"].values()):
            raise ValueError(f"尝试计数不守恒：{key}")
        if collision and collision["candidates_used"] != counters["candidates_tried"]:
            raise ValueError(f"碰撞诊断与观测计数不符：{key}")
        return {**result, "count_unit": "object_proposal" if record["task"] == "BinFill" else "episode_proposal", **counters}

    def check_stats(self, group):
        """同时核对全组和逐 block，不能拿总数回填逐条证据。"""
        def compare(stats, start, stop):
            counters = [v for (t, d, e), v in self.episodes.items()
                        if (t, d) == (group.task, group.difficulty) and start <= e < stop]
            actual = {"candidates_tried": sum(v["candidates_tried"] for v in counters)}
            actual.update({f"rejected_{reason}": sum(v["rejected_before_accept"][reason] for v in counters)
                           for reason in ("geometry", "contact", "numerical_boundary", "uncertified")})
            if any(stats[k] != value for k, value in actual.items()):
                raise ValueError(f"观测与旧统计不符：{group.task}/{group.difficulty}/{start}")
        compare(group.stats, 0, len(group.episodes))
        for index, stats in enumerate(group.stats.get("per_block", [])):
            compare(stats, index * 100, (index + 1) * 100)


def screen_documents(documents, sampling, contract, seed):
    """六项旧检查全部通过后调用方才能发布候选。"""
    verdicts = Verdicts(echo=True)
    _check_scope(documents, verdicts)
    _check_contract_derived(contract, sampling, verdicts)
    quota = _check_quota(documents, contract, verdicts)
    _check_static_geometry(documents, sampling, verdicts)
    _check_collision(documents, verdicts)
    _check_reproducible(documents, sampling, contract, seed, verdicts)
    return verdicts, quota
