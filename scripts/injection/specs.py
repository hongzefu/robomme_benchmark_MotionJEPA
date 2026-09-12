"""外部 CPU 规格生成器：为 11 组各生成 100 条固定规格。

字段口径逐条对应 NEW_VALUE_INJECTION_TEST_PLAN 第二节的「约定」与「固定值」两张表，
分配办法见第四节。本模块**不导入仿真**、不建 actor、不需要 GPU，可在独立 CPU 进程运行。

⚠ 与计划正文的一处偏差：第 2.1 节 B6 写「方块……与按钮、孔板不做避让（沿用原逻辑）」，
但 ``BinFill::_load_scene`` 实际把 ``button_obb`` 与 ``board_with_hole`` 都放进了
``spawn_random_cube`` 的 ``avoid``。这里按**源码**走（做避让），否则会生成压在按钮上、
必然失败的规格；该偏差在交付说明里单列。
"""

from __future__ import annotations

import copy
import hashlib
import itertools
import json
import math
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Sequence

import numpy as np

from robomme.robomme_env.utils import bin_collision as bc

from .contract import Contract, ContractError, GroupContract
from .sampling import (
    COARSE_BINS,
    FINE_LAYERS,
    GROUP_SIZE,
    Stratified,
    balanced_choice,
    derive_rng,
    quota_series,
    stratify,
)

#: 规格文件格式版本；与 schema 3 的 ``native_sampling.json`` 无关，独立演进。
SPEC_SCHEMA_VERSION = 1
#: 生成器实现版本，改变任何采样语义时必须递增。
GENERATOR_VERSION = "injection-specs-1"
#: 本轮固定的生成 seed。
DEFAULT_SEED = 20260909
#: 单个规格位置最多尝试的候选数（含首个候选），与 ``object_generation.max_trials`` 同值。
MAX_CANDIDATES = 256
#: ``PICK_CUBE_CONFIGS["panda"]`` 的 ``cube_half_size``；四任务的 ``robot_uids`` 都走 panda 分支。
CUBE_HALF_SIZE = 0.02

#: 本轮的 11 个组；``VideoRepick hard`` 已被用户排除，不生成、不画图、不实跑。
GROUPS: tuple[tuple[str, str], ...] = (
    ("BinFill", "easy"),
    ("BinFill", "medium"),
    ("BinFill", "hard"),
    ("RouteStick", "easy"),
    ("RouteStick", "medium"),
    ("RouteStick", "hard"),
    ("VideoUnmaskSwap", "easy"),
    ("VideoUnmaskSwap", "medium"),
    ("VideoUnmaskSwap", "hard"),
    ("VideoRepick", "easy"),
    ("VideoRepick", "medium"),
)
EXCLUDED_GROUPS: tuple[tuple[str, str], ...] = (("VideoRepick", "hard"),)
#: 2026-09-11 用户决定新增的 xhard 三组（RouteStick 段数 8～10；两个视频任务 swap 4～5 次）。
#: ``GROUPS`` 保持 11 组不动：它是 v1／v2 契约 builder 的输入清单，也是 05 及更早冻结运行的复验口径。
XHARD_GROUPS: tuple[tuple[str, str], ...] = (
    ("RouteStick", "xhard"),
    ("VideoUnmaskSwap", "xhard"),
    ("VideoRepick", "xhard"),
)
#: 契约 v3 的完整组列表（14 组），**按任务分组、每任务 easy→medium→hard→xhard**——这是出图与文档的展示顺序
#: （2026-09-11 用户要求总览「按照task来排列」）。运行期（plan／check／run）不读这两个常量，一律由契约或清单驱动；
#: v3 契约 JSON 里的组键序仍是 11 + 3（冻结时的顺序），与此无关。
GROUPS_V3: tuple[tuple[str, str], ...] = (
    ("BinFill", "easy"), ("BinFill", "medium"), ("BinFill", "hard"),
    ("RouteStick", "easy"), ("RouteStick", "medium"), ("RouteStick", "hard"), ("RouteStick", "xhard"),
    ("VideoUnmaskSwap", "easy"), ("VideoUnmaskSwap", "medium"), ("VideoUnmaskSwap", "hard"), ("VideoUnmaskSwap", "xhard"),
    ("VideoRepick", "easy"), ("VideoRepick", "medium"), ("VideoRepick", "xhard"),
)

#: ``BinFill`` 的颜色池顺序（``native_semantics.BinFill.spawn_color_order``），只是索引口径。
SPAWN_COLOR_ORDER = ("red", "blue", "green")
#: ``BinFill::_initialize_episode`` 里 ``color_task_definitions`` 的定义表顺序。
INITIALIZE_COLOR_DEFS = ("blue", "red", "green")
#: 两个视频任务的藏物颜色定义顺序（``native_semantics.<任务>.color_order``）。
UNMASK_COLOR_ORDER = ("red", "green", "blue")
#: ``VideoRepick`` 的方块颜色定义顺序。
REPICK_COLOR_ORDER = ("red", "blue", "green")


class SpecGenerationError(RuntimeError):
    """配额格耗尽 256 个候选仍无法冻结；报缺口并停止，不降难度、不放宽阈值。"""


# ── 规格散列 ────────────────────────────────────────────────────────────────
def canonical_json(payload: Any) -> str:
    """固定 UTF-8、键排序、固定分隔符、禁止 NaN 的规范序列化。"""
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


#: 不进规格身份散列的字段。
#: * ``spec_sha256``：散列自身。
#: * ``collision``：碰撞**诊断结果**（判定值、用掉几个候选），不是规格原文。
#:   计划第二部分第二节明确要求「碰撞结果与规格原文分离，不为记录诊断而改写冻结记录或
#:   其散列」。⚠ 实测踩过这一下：给碰撞检查加了一层不改判据的包围球粗筛之后，
#:   ``min_g_m`` 的数值变了（粗筛跳过的对不再贡献精算值），同 seed 两次冻结的
#:   ``VideoUnmaskSwap/hard`` 有 50/100 条散列不同——规格内容一模一样，只是诊断数字变了。
#:   规格的**身份**只能由布局、对象、动作决定。
SHA_EXCLUDED_FIELDS = frozenset({"spec_sha256", "collision"})


def record_sha256(record: dict[str, Any]) -> str:
    """规格身份散列：排除散列自身与碰撞诊断结果，只覆盖布局、对象、动作。"""
    payload = {key: value for key, value in record.items() if key not in SHA_EXCLUDED_FIELDS}
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def operand_sha256(sampling: dict[str, Any], difficulties: Iterable[str] | None = None) -> str:
    """规格生成**实际消费的那部分**原值依据的散列：只取 ``parameters`` 与 ``positions``。

    ⚠ 不能用 ``native_sampling.json`` 的整个文件字节散列。该文件里还有
    ``sources.sha256``——四个任务模块的源码指纹，接入新值后每改一次源码就得刷新一次。
    拿文件散列当验收依据，会在一次纯源码改动之后把已经冻结的规格全部判成「依据漂移」，
    而真正的取值域（parameters / positions）根本没动。实测就踩过这一下。

    ``difficulties``（2026-09-11 加 xhard 时引入）：非空时 ``parameters.<任务>.configs`` 只保留
    这些难度键，其余原样。同一原则的延伸——某个契约／某次冻结只消费了 easy/medium/hard 三档，
    源码后来加了 ``config_xhard`` 也不该把它们判成「依据漂移」。实测：新源码按三档过滤后的散列
    与 05 冻结时的 ``124e49f8…`` 逐位相同，四档全量则是新值。``None`` 为全量（向后兼容）。
    """
    parameters = sampling["parameters"]
    if difficulties is not None:
        keep = set(difficulties)
        parameters = copy.deepcopy(parameters)
        for task_block in parameters.values():
            configs = task_block.get("configs") if isinstance(task_block, dict) else None
            if isinstance(configs, dict):
                task_block["configs"] = {key: value for key, value in configs.items() if key in keep}
    payload = {"parameters": parameters, "positions": sampling["positions"]}
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def difficulties_of(groups: Iterable[tuple[str, str]]) -> set[str]:
    """一组 ``(任务, 难度)`` 消费到的难度集合，供 :func:`operand_sha256` 的作用域参数。"""
    return {difficulty for _task, difficulty in groups}


def seal(record: dict[str, Any]) -> dict[str, Any]:
    record["spec_sha256"] = record_sha256(record)
    return record


# ── 与原实现同源的几何常量 ───────────────────────────────────────────────────
def button_obb(center_xy: Sequence[float], scale: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """复刻 ``build_button`` 结尾的 ``create_button_obb``：轴对齐、半边 = 缩放后底座 ×1.5。"""
    base_half = 0.025 * float(scale)
    half = base_half * 1.5
    return (
        np.asarray(center_xy, dtype=np.float64),
        np.eye(2, dtype=np.float64),
        np.array([half, half], dtype=np.float64),
    )


def board_obbs(center_xy: Sequence[float], board_side: float, hole_side: float) -> list[tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """复刻 ``spawn_random_cube`` 里 ``board_with_hole`` 的四条边 OBB。

    ⚠ 原实现用 ``A_top = np.eye(2)``，**忽略孔板自身的 yaw**；这里照抄该近似，不"顺手修"。
    """
    center = np.asarray(center_xy[:2], dtype=np.float64)
    board_half = board_side / 2.0
    hole_half = hole_side / 2.0
    if board_half <= hole_half:
        return []
    strip = board_half - hole_half
    axes = np.eye(2, dtype=np.float64)
    h_tb = np.array([board_half, strip / 2.0], dtype=np.float64)
    h_lr = np.array([strip / 2.0, hole_half], dtype=np.float64)
    return [
        (center + np.array([0.0, hole_half + strip / 2.0]), axes, h_tb),
        (center + np.array([0.0, -(hole_half + strip / 2.0)]), axes, h_tb),
        (center + np.array([-(hole_half + strip / 2.0), 0.0]), axes, h_lr),
        (center + np.array([hole_half + strip / 2.0, 0.0]), axes, h_lr),
    ]


def cube_obb(x: float, y: float, half_xy: float, yaw: float, pad: float = 0.0):
    """复刻 ``_build_new_cube_obb2d``。"""
    cos_y, sin_y = math.cos(yaw), math.sin(yaw)
    return (
        np.array([x, y], dtype=np.float64),
        np.array([[cos_y, -sin_y], [sin_y, cos_y]], dtype=np.float64),
        np.array([half_xy + pad, half_xy + pad], dtype=np.float64),
    )


def obb2d_intersect(c1, a1, h1, c2, a2, h2) -> bool:
    """复刻 ``_obb2d_intersect``：四根轴，接触也算相交。"""
    d = c2 - c1
    for axis in (a1[:, 0], a1[:, 1], a2[:, 0], a2[:, 1]):
        norm = float(np.linalg.norm(axis))
        unit = axis / norm if norm > 1e-12 else axis
        r1 = abs(float(np.dot(a1[:, 0], unit))) * h1[0] + abs(float(np.dot(a1[:, 1], unit))) * h1[1]
        r2 = abs(float(np.dot(a2[:, 0], unit))) * h2[0] + abs(float(np.dot(a2[:, 1], unit))) * h2[1]
        if abs(float(np.dot(d, unit))) > (r1 + r2):
            return False
    return True


def rotate_xy(points: Sequence[Sequence[float]], theta: float) -> list[list[float]]:
    """复刻 ``rotate_points_random`` 的旋转部分：绕世界原点 (0,0)，右乘旋转矩阵的转置。"""
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    return [[p[0] * cos_t - p[1] * sin_t, p[0] * sin_t + p[1] * cos_t] for p in points]


# ── 分组结果 ────────────────────────────────────────────────────────────────
@dataclass
class GroupResult:
    task: str
    difficulty: str
    seed: int
    derived_seed: int
    episodes: list[dict[str, Any]]
    strata: dict[str, Stratified] = field(default_factory=dict)
    stats: dict[str, Any] = field(default_factory=dict)

    def as_document(self, sampling_config_sha256: str) -> dict[str, Any]:
        """``sampling_config_sha256`` 存的是 :func:`operand_sha256`（取值域散列），
        不是配置文件的字节散列——理由见该函数的说明。"""
        return {
            "spec_schema_version": SPEC_SCHEMA_VERSION,
            "task": self.task,
            "difficulty": self.difficulty,
            "generator_seed": self.seed,
            "derived_seed": self.derived_seed,
            "generator_version": GENERATOR_VERSION,
            "sampling_config_sha256": sampling_config_sha256,
            "episodes": self.episodes,
        }


def _new_stats() -> dict[str, Any]:
    return {
        "candidates_tried": 0,
        "rejected_geometry": 0,
        "rejected_contact": 0,
        "rejected_numerical_boundary": 0,
        "rejected_uncertified": 0,
        "max_candidates_used": 0,
        "rejections": [],
    }


def _count_rejection(stats: dict[str, Any], rejection: bc.CollisionRejection | None, *, geometry: bool = False) -> None:
    if geometry:
        stats["rejected_geometry"] += 1
        return
    if rejection is None:
        return
    stats[f"rejected_{rejection.reason}"] += 1
    if len(stats["rejections"]) < 64:
        stats["rejections"].append(rejection.as_dict())


# ── BinFill ─────────────────────────────────────────────────────────────────
def _binfill_group(difficulty: str, gc: GroupContract, positions: dict[str, Any], seed: int) -> GroupResult:
    """取值域与分配办法来自契约 ``gc``；按钮／孔板的盒体尺寸等几何常量仍来自 ``positions``。"""
    rng_root = derive_rng(seed, "BinFill", difficulty)
    derived = int(rng_root.integers(0, 2**62))

    # 离散域按契约的 values 顺序铺配额（顺序与此前的 itertools 调用同式，rng 消费逐位不变）
    combos = gc.values("colors_present")
    color_counts = gc.values("put_in_color")

    rng = derive_rng(seed, "BinFill", difficulty, "discrete")
    dynamic_series = quota_series(gc.values("dynamic"), rng)
    combo_series = quota_series(combos, rng)
    put_color_series = quota_series(color_counts, rng)
    spawn_total_series = quota_series(gc.values("spawn_total"), rng)
    put_total_series = quota_series(gc.values("put_in_total"), rng)
    init_order_series = quota_series(gc.values("initialize_color_order"), rng)
    target_rule = gc.rule("target_count")
    if target_rule not in ("allow_zero", "each_target_at_least_one"):
        raise ContractError(f"BinFill/{difficulty}: 未知的 target_count 规则 {target_rule!r}")

    button_cfg = positions["button"]
    board_cfg = positions["board"]
    # 连续域端点来自契约（契约里的数值由 check 按 positions 回算钉住）
    strata = {
        name: stratify(*gc.bounds(name), derive_rng(seed, "BinFill", difficulty, name))
        for name in ("button_x", "button_y", "board_x", "board_y", "board_yaw", "cube_x", "cube_y", "cube_yaw")
    }
    cube_x_lo, cube_x_hi = gc.bounds("cube_x")
    cube_y_lo, cube_y_hi = gc.bounds("cube_y")

    target_pool_usage: dict[tuple[int, ...], int] = {}
    stats = _new_stats()
    episodes: list[dict[str, Any]] = []

    for episode in range(GROUP_SIZE):
        rng_ep = derive_rng(seed, "BinFill", difficulty, f"episode-{episode}")
        colors_idx = list(combo_series[episode])
        put_color = min(put_color_series[episode], len(colors_idx))
        put_total = int(put_total_series[episode])
        spawn_total = int(spawn_total_series[episode])

        # 目标色池：从场上颜色里选 put_color 种，在合法候选内平衡
        pool_candidates = list(itertools.combinations(colors_idx, put_color))
        target_idx = list(balanced_choice(rng_ep, pool_candidates, target_pool_usage))

        # 目标数分配：单色直接给总数；多色按契约的 rule——
        #   allow_zero（原值 94449db）：把总数逐个随机分给目标色，某色可为 0；
        #   each_target_at_least_one（heldout 2fa5660）：先每目标色各 1，余量再逐个随机分。
        # allow_zero 路径的语句与加入契约之前逐字相同，rng 消费逐位不变。
        target_count = {SPAWN_COLOR_ORDER[i]: 0 for i in colors_idx}
        if put_color == 1:
            target_count[SPAWN_COLOR_ORDER[target_idx[0]]] = put_total
        elif target_rule == "allow_zero":
            for _ in range(put_total):
                pick = target_idx[int(rng_ep.integers(len(target_idx)))]
                target_count[SPAWN_COLOR_ORDER[pick]] += 1
        else:
            if put_total < len(target_idx):
                # 源码里对应 total_target 的下界 max(put_in_numbers[0], 目标色数)；三档配置下永远不触发，留作硬闸
                raise SpecGenerationError(
                    f"BinFill/{difficulty}/episode {episode}: 投入总数 {put_total} 少于目标色数 {len(target_idx)}，"
                    "无法保证每色至少 1 块"
                )
            for pick in target_idx:
                target_count[SPAWN_COLOR_ORDER[pick]] += 1
            for _ in range(put_total - len(target_idx)):
                pick = target_idx[int(rng_ep.integers(len(target_idx)))]
                target_count[SPAWN_COLOR_ORDER[pick]] += 1

        # 生成数：每色至少 max(目标数, 1)，剩余随机摊到场上颜色
        spawn_count = {SPAWN_COLOR_ORDER[i]: max(target_count[SPAWN_COLOR_ORDER[i]], 1) for i in colors_idx}
        if len(colors_idx) == 1:
            only = SPAWN_COLOR_ORDER[colors_idx[0]]
            spawn_count[only] = max(spawn_total, target_count[only])
        else:
            remaining = spawn_total - sum(spawn_count.values())
            for _ in range(max(0, remaining)):
                pick = colors_idx[int(rng_ep.integers(len(colors_idx)))]
                spawn_count[SPAWN_COLOR_ORDER[pick]] += 1

        button_xy = [strata["button_x"].values[episode], strata["button_y"].values[episode]]
        board_xy = [strata["board_x"].values[episode], strata["board_y"].values[episode]]
        board_yaw = strata["board_yaw"].values[episode]

        # 生成顺序：把 (颜色, 该色序号) 展开后打乱，等价于源码的 randperm(len(cube_tasks))
        tasks: list[tuple[str, int]] = []
        for color_index in colors_idx:
            name = SPAWN_COLOR_ORDER[color_index]
            tasks.extend((name, idx) for idx in range(spawn_count[name]))
        order = rng_ep.permutation(len(tasks))
        tasks = [tasks[i] for i in order]

        placed = _place_binfill_cubes(
            tasks,
            episode=episode,
            strata=strata,
            button=button_obb(button_xy, float(button_cfg["scale"])),
            boards=board_obbs(board_xy, float(board_cfg["board_side"]), float(board_cfg["hole_side"])),
            bounds=(cube_x_lo, cube_x_hi, cube_y_lo, cube_y_hi),
            rng=rng_ep,
            stats=stats,
        )
        if placed is None:
            raise SpecGenerationError(
                f"BinFill/{difficulty}/episode {episode}: {MAX_CANDIDATES} 个候选内放不下 {len(tasks)} 块方块，"
                "报缺口并停止冻结"
            )

        # 动作：按 initialize_color_order 遍历定义表，取该色生成列表最前面的 target_count 块
        init_order = list(init_order_series[episode])
        by_color: dict[str, list[str]] = {}
        for item in placed:
            by_color.setdefault(item["color"], []).append(item["object_id"])
        actions = []
        for color_name in init_order:
            need = target_count.get(color_name, 0)
            if need <= 0:
                continue
            for object_id in by_color.get(color_name, [])[:need]:
                actions.append({"pick": object_id, "put_in": True})

        episodes.append(
            seal(
                {
                    "episode": episode,
                    "task": "BinFill",
                    "difficulty": difficulty,
                    "layout": {
                        "dynamic": bool(dynamic_series[episode]),
                        "button_xy": button_xy,
                        "board": {"xy": board_xy, "yaw_deg": board_yaw},
                        "cubes": placed,
                    },
                    "objects": {
                        "colors_present": [SPAWN_COLOR_ORDER[i] for i in colors_idx],
                        "initialize_color_order": init_order,
                        "target_pool": [SPAWN_COLOR_ORDER[i] for i in target_idx],
                        "spawn_total": spawn_total,
                        "put_in_total": put_total,
                        "spawn_count": spawn_count,
                        "target_count": target_count,
                    },
                    "actions": actions,
                    "sampling_cells": {
                        name: [strata[name].bin_of[episode], strata[name].layer_of[episode]]
                        for name in ("button_x", "button_y", "board_x", "board_y", "board_yaw", "cube_x", "cube_y", "cube_yaw")
                    },
                }
            )
        )
    return GroupResult("BinFill", difficulty, seed, derived, episodes, strata, stats)


def _place_binfill_cubes(
    tasks: Sequence[tuple[str, int]],
    *,
    episode: int,
    strata: dict[str, Stratified],
    button,
    boards,
    bounds: tuple[float, float, float, float],
    rng: np.random.Generator,
    stats: dict[str, Any],
) -> list[dict[str, Any]] | None:
    """按原 ``spawn_random_cube`` 的判据逐块落位：新方块半长扩 ``min_gap``，与已有 OBB 相交即重抽。

    第 0 块的**首次尝试**用本 episode 的分层采样点，这一次就是计入连续量配额的
    「采样输入」；其余方块的首次尝试按粗箱轮转散开，避免一局的方块挤在同一区间。

    ⚠ 首次尝试被几何拒绝后，一律照 ``spawn_random_cube`` 的原逻辑在整个区域重抽，
    **不锁在原细分层格里**。格宽只有 0.0036 米，被按钮或孔板压住时同格重抽 256 次
    必然全灭（实测 ``BinFill/hard/episode 13`` 就是这样耗尽的）。计划第 4.2 节的
    ⚠ 也把这类每局物体数可变的位置口径定为「每 episode 的采样输入配额」与
    「全部对象的实际位置频数」分开报，正对应这里的处理。
    """
    x_lo, x_hi, y_lo, y_hi = bounds
    obstacles = [button, *boards]
    placed: list[dict[str, Any]] = []
    for order_index, (color_name, color_idx) in enumerate(tasks):
        found = None
        for trial in range(MAX_CANDIDATES):
            stats["candidates_tried"] += 1
            if order_index == 0 and trial == 0:
                x = strata["cube_x"].values[episode]
                y = strata["cube_y"].values[episode]
                yaw = strata["cube_yaw"].values[episode]
            elif trial == 0:
                x = _shifted_cell(strata["cube_x"], episode, order_index, rng)
                y = _shifted_cell(strata["cube_y"], episode, order_index, rng)
                yaw = _shifted_cell(strata["cube_yaw"], episode, order_index, rng)
            else:
                x = float(rng.uniform(x_lo, x_hi))
                y = float(rng.uniform(y_lo, y_hi))
                yaw = float(rng.uniform(0.0, 2 * math.pi))
            candidate = cube_obb(x, y, CUBE_HALF_SIZE, yaw, pad=CUBE_HALF_SIZE)
            if any(obb2d_intersect(*obstacle, *candidate) for obstacle in obstacles):
                stats["rejected_geometry"] += 1
                continue
            found = (x, y, yaw)
            break
        if found is None:
            return None
        x, y, yaw = found
        obstacles.append(cube_obb(x, y, CUBE_HALF_SIZE, yaw))
        placed.append(
            {
                "object_id": f"cube_{color_name}_{color_idx}",
                "color": color_name,
                "color_index": color_idx,
                "xy": [x, y],
                "yaw_rad": yaw,
            }
        )
    return placed


def _shifted_cell(stratum: Stratified, episode: int, shift: int, rng: np.random.Generator) -> float:
    """同一 episode 的第 ``shift`` 个对象：粗箱按 shift 轮转，细层随机，散开而不占配额。"""
    coarse = (stratum.bin_of[episode] + shift) % COARSE_BINS
    fine = int(rng.integers(FINE_LAYERS))
    span = (stratum.high - stratum.low) / (COARSE_BINS * FINE_LAYERS)
    cell = coarse * FINE_LAYERS + fine
    return float(stratum.low + (cell + rng.random()) * span)


# ── RouteStick ──────────────────────────────────────────────────────────────
def _routestick_group(difficulty: str, gc: GroupContract, config: dict[str, Any], parameters: dict[str, Any], positions: dict[str, Any], seed: int) -> GroupResult:
    """1×9 整排，偶数索引可踩、奇数索引是障碍柱；只固定整排旋转角、路线与逐段绕行方向。"""
    rng_root = derive_rng(seed, "RouteStick", difficulty)
    derived = int(rng_root.integers(0, 2**62))

    allow_backtracking = bool(config["backtrack"])
    walk_cfg = parameters["walk"]
    node_indices = [int(v) for v in walk_cfg["node_indices"]]
    directions_pool = tuple(gc.values("direction"))

    rng = derive_rng(seed, "RouteStick", difficulty, "discrete")
    length_series = quota_series(gc.values("L"), rng)
    # 契约存的是节点值（0/2/4/6/8），生成器内部用局部槽位
    start_series = quota_series([node_indices.index(int(v)) for v in gc.values("start_node")], rng)

    strata = {
        "rotation_deg": stratify(*gc.bounds("rotation_deg"), derive_rng(seed, "RouteStick", difficulty, "rotation"))
    }

    edge_usage: dict[tuple[int, int], int] = {}
    direction_usage: dict[str, int] = {}
    episodes: list[dict[str, Any]] = []
    stats = _new_stats()

    for episode in range(GROUP_SIZE):
        rng_ep = derive_rng(seed, "RouteStick", difficulty, f"episode-{episode}")
        steps = int(length_series[episode])
        rotation_deg = strata["rotation_deg"].values[episode]

        # 路线：复用 generate_dynamic_walk 的线性邻接语义（局部索引 ±1，越界剔除；
        # 不允许回退时剔除上一步，无路可走则被迫回退）。在合法候选内按边使用频数平衡。
        history = [int(start_series[episode])]
        for _ in range(steps):
            current = history[-1]
            previous = history[-2] if len(history) > 1 else None
            neighbours = [current + offset for offset in walk_cfg["neighbor_order"] if 0 <= current + offset < len(node_indices)]
            if allow_backtracking or previous is None:
                candidates = neighbours
            else:
                filtered = [n for n in neighbours if n != previous]
                candidates = filtered if filtered else neighbours
            edges = [(current, n) for n in candidates]
            history.append(balanced_choice(rng_ep, edges, edge_usage)[1])

        directions = [balanced_choice(rng_ep, list(directions_pool), direction_usage) for _ in range(steps)]
        obstacle_count = int(positions["obstacle_color"]["count"])
        obstacle_rgb = [[float(v) for v in rng_ep.random(3)] for _ in range(obstacle_count)]

        episodes.append(
            seal(
                {
                    "episode": episode,
                    "task": "RouteStick",
                    "difficulty": difficulty,
                    "layout": {"rotation_deg": rotation_deg, "obstacle_rgb": obstacle_rgb},
                    "objects": {"L": steps, "allow_backtracking": allow_backtracking},
                    "actions": {
                        # nodes 存的是节点**值**（0/2/4/6/8），与 generate_dynamic_walk 的返回一致；
                        # node_slots 存对应的局部索引，供 check 直接验邻接。
                        "nodes": [node_indices[i] for i in history],
                        "node_slots": history,
                        "directions": directions,
                    },
                    "sampling_cells": {
                        "rotation_deg": [strata["rotation_deg"].bin_of[episode], strata["rotation_deg"].layer_of[episode]]
                    },
                }
            )
        )
    return GroupResult("RouteStick", difficulty, seed, derived, episodes, strata, stats)


# ── 两个视频任务共用的布局与交换模拟 ──────────────────────────────────────────
def _layout_anchor_points(positions: dict[str, Any], layout_type: str) -> list[list[float]]:
    return [list(point) for point in positions[layout_type]]


def _nearest_partner(index: int, xy: dict[int, list[float]]) -> int:
    """复刻 ``step`` 的最近邻扫描：``dist < closest_dist`` 严格小于，等距取生成序号小者。"""
    best_index, best_dist = -1, float("inf")
    for other in sorted(xy):
        if other == index:
            continue
        dist = math.dist(xy[index][:2], xy[other][:2])
        if dist < best_dist:
            best_index, best_dist = other, dist
    if best_index < 0:
        raise SpecGenerationError("最近邻扫描找不到候选对象")
    return best_index


def _simulate_swaps(
    initiators: Sequence[int],
    states: dict[int, bc.ObjectState],
    *,
    check_sweeps: bool,
    stats: dict[str, Any],
) -> tuple[list[dict[str, Any]], bc.CollisionRejection | None, float]:
    """按名义位姿逐段模拟交换：解析最近邻搭档 → 连续几何检查 → 双方位姿互换。

    ⚠ 这是**设计口径**：运行时的搭档由 ``step`` 在交换开始那一刻按实际位姿重算，
    上一段的收尾帧与物理漂移都可能让实际最近邻与这里预写的不同。计划因此要求执行时
    核验，不一致的样本直接记「实际对象／动作不符」失败，而不是现场换搭档。
    """
    current = {index: state for index, state in states.items()}
    pairs: list[dict[str, Any]] = []
    worst = float("inf")
    for sweep_index, initiator in enumerate(initiators):
        xy = {index: list(state.p[:2]) for index, state in current.items()}
        partner = _nearest_partner(initiator, xy)
        if check_sweeps:
            bystanders = [state for index, state in sorted(current.items()) if index not in (initiator, partner)]
            gap, rejection = bc.check_swap_sweep(
                current[initiator], current[partner], bystanders, sweep_index=sweep_index
            )
            if rejection is not None:
                _count_rejection(stats, rejection)
                return pairs, rejection, worst
            worst = min(worst, gap)
        pairs.append(
            {
                "initiator": initiator,
                "partner": partner,
                "distance_m": math.dist(xy[initiator], xy[partner]),
            }
        )
        # 交换完成后 A 落到 B 的位置并接手 B 的朝向，反之亦然（``swap_flat_two_lane`` 的收尾）
        a, b = current[initiator], current[partner]
        current[initiator] = bc.ObjectState(name=a.name, p=np.array([b.p[0], b.p[1], a.p[2]]), q=b.q, shapes=a.shapes)
        current[partner] = bc.ObjectState(name=b.name, p=np.array([a.p[0], a.p[1], b.p[2]]), q=a.q, shapes=b.shapes)
    return pairs, None, worst


# ── VideoUnmaskSwap ─────────────────────────────────────────────────────────
def _unmask_group(difficulty: str, gc: GroupContract, config: dict[str, Any], parameters: dict[str, Any], positions: dict[str, Any], seed: int) -> GroupResult:
    rng_root = derive_rng(seed, "VideoUnmaskSwap", difficulty)
    derived = int(rng_root.integers(0, 2**62))

    n_bins = int(config["bin"])
    containers = positions["containers"]  # 锚点坐标等几何仍从 positions 取

    rng = derive_rng(seed, "VideoUnmaskSwap", difficulty, "discrete")
    swap_series = quota_series(gc.values("n_swaps"), rng)
    pick_series = quota_series(gc.values("n_picks"), rng)
    # bin=3 时布局按配额；bin=4 时契约给常量，不消费 rng
    layout_series = (
        quota_series(gc.values("layout_type"), rng)
        if gc.allocation("layout_type") == "quota"
        else [gc.constant("layout_type")] * GROUP_SIZE
    )
    selected_series = quota_series(gc.values("selected"), rng)
    color_series = quota_series(gc.values("color_order"), rng)
    initiator_series = quota_series(gc.values("swap_initiators_first_two"), rng)

    strata: dict[str, Stratified] = {
        "theta_rad": stratify(*gc.bounds("theta_rad"), derive_rng(seed, "VideoUnmaskSwap", difficulty, "theta"))
    }
    for i in range(n_bins):
        for axis in ("dx", "dy"):
            strata[f"bin{i}_{axis}"] = stratify(
                *gc.bounds(f"bin{i}_{axis}"), derive_rng(seed, "VideoUnmaskSwap", difficulty, f"bin{i}-{axis}")
            )
        strata[f"bin{i}_yaw"] = stratify(*gc.bounds(f"bin{i}_yaw"), derive_rng(seed, "VideoUnmaskSwap", difficulty, f"bin{i}-yaw"))

    third_usage: dict[int, int] = {}
    stats = _new_stats()
    episodes: list[dict[str, Any]] = []

    for episode in range(GROUP_SIZE):
        rng_ep = derive_rng(seed, "VideoUnmaskSwap", difficulty, f"episode-{episode}")
        n_swaps = int(swap_series[episode])
        n_picks = int(pick_series[episode])
        layout_type = layout_series[episode]
        selected = list(selected_series[episode])
        colors = list(color_series[episode])

        # 交换发起者：前两次是「藏物排序里抽出的两个位置」直接当生成序号用（原代码就这样混用索引），
        # 第三次从其余生成序号里取；n_bins=3 时 remaining 恰好剩一个，不会越界。
        target_indices = list(initiator_series[episode])
        remaining = [i for i in range(n_bins) if i not in target_indices]
        third = balanced_choice(rng_ep, remaining, third_usage)
        # ⚠ 源码**无条件**赋值 swap_pair{1,2,3}_idx1（以及只赋值不读的 target_bin_1/2），
        # 即使 n_swaps=1 也要有 3 个发起者，否则会 IndexError。所以规格存完整的 3 个，
        # actions.swap_pairs 只存实际执行的前 n_swaps 段——未执行的那部分也不靠随机。
        initiators_full = [*target_indices, third]
        # xhard（n_swaps 4～5）第 k 次发起者循环沿用循环基 initiators_full[k mod 3]（a,b,c,a,b）；n ≤ 3 时与 [:n_swaps] 逐元素相同
        initiators = [initiators_full[k % len(initiators_full)] for k in range(n_swaps)]

        frozen = None
        for trial in range(MAX_CANDIDATES):
            stats["candidates_tried"] += 1
            theta = strata["theta_rad"].values[episode] if trial == 0 else strata["theta_rad"].resample(episode, rng_ep)
            anchors = rotate_xy(_layout_anchor_points(containers, layout_type), theta)
            bins = []
            for i in range(n_bins):
                if trial == 0:
                    dx = strata[f"bin{i}_dx"].values[episode]
                    dy = strata[f"bin{i}_dy"].values[episode]
                    yaw = strata[f"bin{i}_yaw"].values[episode]
                else:
                    dx = strata[f"bin{i}_dx"].resample(episode, rng_ep)
                    dy = strata[f"bin{i}_dy"].resample(episode, rng_ep)
                    yaw = strata[f"bin{i}_yaw"].resample(episode, rng_ep)
                bins.append({"object_id": f"bin_{i}", "xy": [anchors[i][0] + dx, anchors[i][1] + dy], "yaw_deg": yaw})

            states = {}
            for i, item in enumerate(bins):
                p, q = bc.bin_actor_pose(item["xy"], item["yaw_deg"], CUBE_HALF_SIZE)
                states[i] = bc.ObjectState(name=item["object_id"], p=p, q=q, shapes=bc.bin_shape_specs(CUBE_HALF_SIZE))

            initial_gap, rejection = bc.check_bin_layout(list(states.values()), stage="initial")
            if rejection is not None:
                _count_rejection(stats, rejection)
                continue
            pairs, rejection, sweep_gap = _simulate_swaps(initiators, states, check_sweeps=True, stats=stats)
            if rejection is not None:
                continue
            frozen = (theta, bins, pairs, initial_gap, sweep_gap, trial + 1)
            break

        if frozen is None:
            raise SpecGenerationError(
                f"VideoUnmaskSwap/{difficulty}/episode {episode}: {MAX_CANDIDATES} 个候选内没有通过碰撞检查的布局，"
                "报缺口并停止冻结"
            )
        theta, bins, pairs, initial_gap, sweep_gap, used = frozen
        stats["max_candidates_used"] = max(stats["max_candidates_used"], used)

        hidden = {colors[i]: f"bin_{selected[i]}" for i in range(3)}
        pick_order = [f"bin_{selected[i]}" for i in parameters["object_selection"]["pickup_selected_indices"][:n_picks]]
        empty = [f"bin_{i}" for i in range(n_bins) if i not in selected]

        episodes.append(
            seal(
                {
                    "episode": episode,
                    "task": "VideoUnmaskSwap",
                    "difficulty": difficulty,
                    "layout": {"type": layout_type, "theta_rad": theta, "bins": bins},
                    "objects": {
                        "n_bins": n_bins,
                        "n_swaps": n_swaps,
                        "n_picks": n_picks,
                        "selected": selected,
                        "color_order": colors,
                        "hidden": hidden,
                        "empty": empty,
                        "pick_order": pick_order,
                        "swap_initiators": [f"bin_{i}" for i in initiators_full],
                    },
                    "actions": {
                        "swap_pairs": [
                            {"initiator": f"bin_{item['initiator']}", "partner": f"bin_{item['partner']}", "distance_m": item["distance_m"]}
                            for item in pairs
                        ]
                    },
                    "collision": {
                        "initial": "PASS",
                        "sweeps": ["PASS"] * len(pairs),
                        "min_g_m": min(initial_gap, sweep_gap) if pairs else initial_gap,
                        "candidates_used": used,
                    },
                    "sampling_cells": {
                        name: [strata[name].bin_of[episode], strata[name].layer_of[episode]] for name in strata
                    },
                }
            )
        )
    return GroupResult("VideoUnmaskSwap", difficulty, seed, derived, episodes, strata, stats)


# ── VideoRepick ─────────────────────────────────────────────────────────────
def _repick_group(difficulty: str, gc: GroupContract, config: dict[str, Any], parameters: dict[str, Any], positions: dict[str, Any], seed: int) -> GroupResult:
    if difficulty == "hard":
        raise SpecGenerationError("VideoRepick hard 已由用户排除，不生成规格")

    rng_root = derive_rng(seed, "VideoRepick", difficulty)
    derived = int(rng_root.integers(0, 2**62))

    n_cubes = int(config["cube"])
    plain = positions["easy_medium_cubes"]  # 锚点坐标等几何仍从 positions 取
    button_cfg = positions["button"]

    rng = derive_rng(seed, "VideoRepick", difficulty, "discrete")
    swap_series = quota_series(gc.values("n_swaps"), rng)
    repeat_series = quota_series(gc.values("num_repeats"), rng)
    layout_series = quota_series(gc.values("layout_type"), rng)
    color_series = quota_series(gc.values("color"), rng)
    target_series = quota_series(gc.values("target"), rng)
    tail_series = quota_series(gc.values("tail"), rng)

    strata: dict[str, Stratified] = {
        name: stratify(*gc.bounds(name), derive_rng(seed, "VideoRepick", difficulty, label))
        for name, label in (("theta_rad", "theta"), ("button_x", "button_x"), ("button_y", "button_y"))
    }
    for i in range(n_cubes):
        for axis in ("dx", "dy"):
            strata[f"cube{i}_{axis}"] = stratify(
                *gc.bounds(f"cube{i}_{axis}"), derive_rng(seed, "VideoRepick", difficulty, f"cube{i}-{axis}")
            )
        strata[f"cube{i}_yaw"] = stratify(*gc.bounds(f"cube{i}_yaw"), derive_rng(seed, "VideoRepick", difficulty, f"cube{i}-yaw"))

    stats = _new_stats()
    episodes: list[dict[str, Any]] = []

    for episode in range(GROUP_SIZE):
        rng_ep = derive_rng(seed, "VideoRepick", difficulty, f"episode-{episode}")
        n_swaps = int(swap_series[episode])
        num_repeats = int(repeat_series[episode])
        layout_type = layout_series[episode]
        color = color_series[episode]
        target = int(target_series[episode])
        others = [i for i in range(n_cubes) if i != target]
        tail = [others[i] for i in tail_series[episode]]
        # 同 VideoUnmaskSwap：源码无条件赋值 swap_pair{1,2,3}_idx1，需要完整的 3 个发起者
        initiators_full = [target, *tail]
        # 同 VideoUnmaskSwap：第 k 次发起者 = initiators_full[k mod 3]；n ≤ 3 时与 [:n_swaps] 逐元素相同
        initiators = [initiators_full[k % len(initiators_full)] for k in range(n_swaps)]

        button_xy = [strata["button_x"].values[episode], strata["button_y"].values[episode]]
        button = button_obb(button_xy, float(button_cfg["scale"]))

        frozen = None
        for trial in range(MAX_CANDIDATES):
            stats["candidates_tried"] += 1
            theta = strata["theta_rad"].values[episode] if trial == 0 else strata["theta_rad"].resample(episode, rng_ep)
            anchors = rotate_xy(_layout_anchor_points(plain, layout_type), theta)
            cubes = []
            for i in range(n_cubes):
                if trial == 0:
                    dx = strata[f"cube{i}_dx"].values[episode]
                    dy = strata[f"cube{i}_dy"].values[episode]
                    yaw = strata[f"cube{i}_yaw"].values[episode]
                else:
                    dx = strata[f"cube{i}_dx"].resample(episode, rng_ep)
                    dy = strata[f"cube{i}_dy"].resample(episode, rng_ep)
                    yaw = strata[f"cube{i}_yaw"].resample(episode, rng_ep)
                cubes.append({"object_id": f"bin_{i}", "xy": [anchors[i][0] + dx, anchors[i][1] + dy], "yaw_rad": yaw})

            # 原逻辑：方块两两之间至少留 min_gap=0.02，并避让按钮
            geometry_ok = True
            placed_obbs = [button]
            for item in cubes:
                candidate = cube_obb(item["xy"][0], item["xy"][1], CUBE_HALF_SIZE, item["yaw_rad"], pad=CUBE_HALF_SIZE)
                if any(obb2d_intersect(*obstacle, *candidate) for obstacle in placed_obbs):
                    geometry_ok = False
                    break
                placed_obbs.append(cube_obb(item["xy"][0], item["xy"][1], CUBE_HALF_SIZE, item["yaw_rad"]))
            if not geometry_ok:
                _count_rejection(stats, None, geometry=True)
                continue

            states = {}
            for i, item in enumerate(cubes):
                p, q = bc.cube_actor_pose(item["xy"], item["yaw_rad"], CUBE_HALF_SIZE)
                states[i] = bc.ObjectState(name=item["object_id"], p=p, q=q, shapes=bc.cube_shape_specs(CUBE_HALF_SIZE))

            initial_gap, rejection = bc.check_bin_layout(list(states.values()), stage="initial")
            if rejection is not None:
                _count_rejection(stats, rejection)
                continue
            pairs, rejection, sweep_gap = _simulate_swaps(initiators, states, check_sweeps=True, stats=stats)
            if rejection is not None:
                continue
            frozen = (theta, cubes, pairs, initial_gap, sweep_gap, trial + 1)
            break

        if frozen is None:
            raise SpecGenerationError(
                f"VideoRepick/{difficulty}/episode {episode}: {MAX_CANDIDATES} 个候选内没有通过碰撞检查的布局，"
                "报缺口并停止冻结"
            )
        theta, cubes, pairs, initial_gap, sweep_gap, used = frozen
        stats["max_candidates_used"] = max(stats["max_candidates_used"], used)

        episodes.append(
            seal(
                {
                    "episode": episode,
                    "task": "VideoRepick",
                    "difficulty": difficulty,
                    "layout": {"type": layout_type, "theta_rad": theta, "button_xy": button_xy, "cubes": cubes},
                    "objects": {
                        "n_cubes": n_cubes,
                        "n_swaps": n_swaps,
                        "color": color,
                        "target": f"bin_{target}",
                        "num_repeats": num_repeats,
                        "swap_initiators": [f"bin_{i}" for i in initiators_full],
                    },
                    "actions": {
                        "swap_pairs": [
                            {"initiator": f"bin_{item['initiator']}", "partner": f"bin_{item['partner']}", "distance_m": item["distance_m"]}
                            for item in pairs
                        ]
                    },
                    "collision": {
                        "initial": "PASS",
                        "sweeps": ["PASS"] * len(pairs),
                        "min_g_m": min(initial_gap, sweep_gap) if pairs else initial_gap,
                        "candidates_used": used,
                    },
                    "sampling_cells": {
                        name: [strata[name].bin_of[episode], strata[name].layer_of[episode]] for name in strata
                    },
                }
            )
        )
    return GroupResult("VideoRepick", difficulty, seed, derived, episodes, strata, stats)


# ── 对外入口 ────────────────────────────────────────────────────────────────
_BUILDERS: dict[str, Callable[..., GroupResult]] = {}


def build_group(task: str, difficulty: str, sampling: dict[str, Any], contract: Contract, seed: int = DEFAULT_SEED) -> GroupResult:
    """按任务与难度生成一组 100 条规格。

    * ``contract``：取值域与分配办法的约定（``injection_contract_v*.json``），离散域的候选列表与
      连续域的端点都从它读——这是「候选分布怎么产生」的派生依据；
    * ``sampling``：``native_sampling.json`` 的内容，只再提供几何常量（按钮盒尺寸、孔板边长、
      锚点坐标、避让间距）与结构性输入（节点表、邻接顺序）。
    """
    parameters = sampling["parameters"][task]
    positions = sampling["positions"][task]
    config = parameters["configs"][difficulty]
    gc = contract.group(task, difficulty)
    if task == "BinFill":
        return _binfill_group(difficulty, gc, positions, seed)
    if task == "RouteStick":
        return _routestick_group(difficulty, gc, config, parameters, positions, seed)
    if task == "VideoUnmaskSwap":
        return _unmask_group(difficulty, gc, config, parameters, positions, seed)
    if task == "VideoRepick":
        return _repick_group(difficulty, gc, config, parameters, positions, seed)
    raise SpecGenerationError(f"未知任务 {task}")
