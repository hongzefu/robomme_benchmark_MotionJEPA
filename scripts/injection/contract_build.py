"""生成注入取值域契约：``build-v1``（从 native_sampling.json 派生现状口径）、``build-v2``（v1 + BinFill 对齐 heldout 的
三条 override）、``check``（离线回算核对）。

    uv run --no-sync python -m scripts.injection.contract_build build-v1 --out scripts/configs/newtask-v2/injection_contract_v1.json
    uv run --no-sync python -m scripts.injection.contract_build build-v2 --base .../injection_contract_v1.json --out .../injection_contract_v2.json
    uv run --no-sync python -m scripts.injection.contract_build check --contract .../injection_contract_v2.json

v1 的数值域全部由 ``contract.RECIPES`` 从 ``native_sampling.json`` 现算（所以天然满足 ``CONTRACT_DERIVED``），
离散域的 ``values`` 顺序与生成器 ``specs.py`` 消费的 ``itertools`` 调用同式；``domain_text`` / ``allocation_text``
是事件表（``scripts/injection-before-2d/event_tables.py``）「取值域」「分配」两列的原文——契约建成后事件表改为
直接取这两列，本文件成为这些文案的唯一来源。
"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

from .contract import (
    CONSTS,
    CONTRACT_SCHEMA_VERSION,
    Contract,
    ContractError,
    audit_overrides,
    derive_all,
    load_contract,
    run_recipe,
)

REPO_ROOT = Path(__file__).resolve().parents[2]  # scripts/injection/ 向上两级是仓库根
DEFAULT_SAMPLING = REPO_ROOT / "scripts" / "configs" / "newtask-v2" / "native_sampling.json"
DEFAULT_SEED = 20260909
GROUP_SIZE = 100
GROUPS = (
    ("BinFill", "easy"), ("BinFill", "medium"), ("BinFill", "hard"),
    ("RouteStick", "easy"), ("RouteStick", "medium"), ("RouteStick", "hard"),
    ("VideoUnmaskSwap", "easy"), ("VideoUnmaskSwap", "medium"), ("VideoUnmaskSwap", "hard"),
    ("VideoRepick", "easy"), ("VideoRepick", "medium"),
)
EXCLUDED_GROUPS = (("VideoRepick", "hard"),)
#: 2026-09-11 用户决定新增的 xhard 三组；``GROUPS`` 保持 11 组（v1／v2 的输入清单）不动。
XHARD_GROUPS = (("RouteStick", "xhard"), ("VideoUnmaskSwap", "xhard"), ("VideoRepick", "xhard"))
GROUPS_V3 = GROUPS + XHARD_GROUPS

#: BinFill 对齐 heldout 分支 ``cvpr2026Challenge-heldOutSeed-4-5/4``（commit 2fa5660）的三条 override（v2）。
HELDOUT_COMMIT = "2fa5660d8b78f31a6735538660d18a8e830bff63"
USER_DECISION = "用户 2026-09-11 原话「能否改为对齐heldout」「按照这个方案改 把现有的…写作为json约定 v1 修改后的binfill计为v2」"
BINFILL_HELDOUT_OVERRIDES: list[dict[str, Any]] = [
    {"group": "BinFill/medium", "field": "spawn_total", "native": {"lo": 8, "hi": 10}, "contract": {"lo": 6, "hi": 8},
     "source": f"heldout 分支 {HELDOUT_COMMIT[:7]} 的 BinFill.config_medium['spawn_cubes'] = [6, 8]", "reason": USER_DECISION},
    {"group": "BinFill/hard", "field": "spawn_total", "native": {"lo": 10, "hi": 12}, "contract": {"lo": 8, "hi": 10},
     "source": f"heldout 分支 {HELDOUT_COMMIT[:7]} 的 BinFill.config_hard['spawn_cubes'] = [8, 10]", "reason": USER_DECISION},
]
#: target_count 的规则切换不进 derive_all（coupled 域没有 derivation），单独按组登记，供文档与 check 的判定行报数。
TARGET_RULE_OVERRIDE_SOURCE = (
    f"heldout 分支 {HELDOUT_COMMIT[:7]} 的 BinFill::_load_scene 多色分支：先 for color_idx in active_color_indices: "
    "target_numbers[color_idx] += 1，再把 total_target - min_required_targets 逐个随机分；单色分支不变"
)
TARGET_TEXT_V1 = "投入数逐个随机分给目标色，允许 0"
TARGET_TEXT_V2 = "单色直接给总数；多目标色每色先各 1，余量逐个随机分（heldout 规则，不允许 0）"


# ── 小工具 ──────────────────────────────────────────────────────────────────
def g(v: float) -> str:
    """区间端点的短写：-0.25 → "-0.25"，20.0 → "20"（与事件表原文一致）。"""
    return f"{float(v):g}"


def range_text(lo: int, hi: int) -> str:
    return str(lo) if lo == hi else f"{lo}～{hi}"


def field(key: str, label: str, domain: dict[str, Any], domain_text: str, allocation: dict[str, Any], allocation_text: str) -> dict[str, Any]:
    return {"key": key, "label": label, "domain": domain, "domain_text": domain_text, "allocation": allocation, "allocation_text": allocation_text}


def derived_domain(sampling: dict[str, Any], kind: str, recipe: str, inputs: dict[str, Any], expr: str, **extra: Any) -> dict[str, Any]:
    """按 recipe 现算数值域并把派生说明一并写入。"""
    result = run_recipe(sampling, recipe, inputs)
    domain: dict[str, Any] = {"kind": kind}
    if kind == "int_range":
        domain["closed"] = True
    domain.update(result)
    domain.update(extra)
    domain["derivation"] = {"recipe": recipe, "inputs": inputs, "expr": expr}
    return domain


def component(sampling: dict[str, Any], recipe: str, inputs: dict[str, Any], expr: str, unit: str) -> dict[str, Any]:
    result = run_recipe(sampling, recipe, inputs)
    return {"lo": result["lo"], "hi": result["hi"], "unit": unit, "derivation": {"recipe": recipe, "inputs": inputs, "expr": expr}}


def continuous(components: dict[str, dict[str, Any]], closed: str = "[]") -> dict[str, Any]:
    return {"kind": "continuous", "closed": closed, "components": components}


Q = {"kind": "quota"}
DERIVED = {"kind": "derived"}
BALANCED = {"kind": "balanced", "usage_scope": "group"}


# ── BinFill ─────────────────────────────────────────────────────────────────
def binfill_group(sampling: dict[str, Any], difficulty: str) -> dict[str, Any]:
    cfg = f"parameters.BinFill.configs.{difficulty}"
    config = sampling["parameters"]["BinFill"]["configs"][difficulty]
    n_color = int(config["color"])
    button = {
        "button_x": component(sampling, "center_pm_half_range", {"center": "positions.BinFill.button.center_xy[0]", "span": "positions.BinFill.button.randomize_range[0]"}, "[center - span/2, center + span/2]", "m"),
        "button_y": component(sampling, "center_pm_half_range", {"center": "positions.BinFill.button.center_xy[1]", "span": "positions.BinFill.button.randomize_range[1]"}, "[center - span/2, center + span/2]", "m"),
    }
    board = {
        "board_x": component(sampling, "base_minus_subtract_span", {"base": "positions.BinFill.board.base_position[0]", "subtract": "positions.BinFill.board.x_offset.subtract", "scale": "positions.BinFill.board.x_offset.scale"}, "[base - subtract, base - subtract + scale]（x_expression 叠 base）", "m"),
        "board_y": component(sampling, "subtract_span", {"subtract": "positions.BinFill.board.y_offset.subtract", "scale": "positions.BinFill.board.y_offset.scale"}, "[-subtract, -subtract + scale]；⚠ 不叠 base_position[1]，与 y_expression 一致", "m"),
        "board_yaw": component(sampling, "subtract_span", {"subtract": "positions.BinFill.board.yaw_deg.subtract", "scale": "positions.BinFill.board.yaw_deg.scale"}, "[-subtract, -subtract + scale]", "deg"),
    }
    cubes = {
        "cube_x": component(sampling, "region_inset", {"center": "positions.BinFill.cubes.region_center[0]", "half": "positions.BinFill.cubes.region_half_size[0]", "inset": "const:cube_half_size"}, "[center - half + inset, center + half - inset]（object_generation.cube_center_bounds）", "m"),
        "cube_y": component(sampling, "region_inset", {"center": "positions.BinFill.cubes.region_center[1]", "half": "positions.BinFill.cubes.region_half_size[1]", "inset": "const:cube_half_size"}, "同 cube_x 取 [1]", "m"),
        "cube_yaw": component(sampling, "pair", {"pair": "positions.BinFill.cubes.yaw_range_rad"}, "[pair[0], pair[1]]", "rad"),
    }
    put_color_domain = derived_domain(sampling, "enum", "clamped_color_counts", {"pair": f"{cfg}.put_in_color", "num_colors": f"{cfg}.color"},
                                      "sorted({min(max(1, min(3, k)), max(1, num_colors)) for k in pair[0]..pair[1]})；源码先夹 [1,3] 再夹 [1, max(1, color)]")
    spawn_domain = derived_domain(sampling, "int_range", "closed_int_range", {"pair": f"{cfg}.spawn_cubes"}, "[pair[0] … pair[1]] 闭区间（torch.randint(lo, hi+1) 消费）")
    put_domain = derived_domain(sampling, "int_range", "closed_int_range", {"pair": f"{cfg}.put_in_numbers"}, "[pair[0] … pair[1]] 闭区间",
                                note="heldout 多色分支抽 randint(max(pair[0], 目标色数), pair[1]+1)；三档配置下 max(...) 恒等于 pair[0]，域不变")
    return {
        "task": "BinFill", "difficulty": difficulty,
        "初始化": [
            field("dynamic", "`dynamic`（方块分批出现还是开局全在）",
                  derived_domain(sampling, "enum", "bool_pair", {"spec": "parameters.BinFill.dynamic"}, "torch.randint(0, 2) 转 bool → [true, false]"),
                  "True / False", Q, "配额 50/50"),
            field("colors_present", "`colors_present`（场上有哪些颜色）",
                  derived_domain(sampling, "combinations", "combinations_of_color_pool", {"num_colors": f"{cfg}.color", "pool": "const:SPAWN_COLOR_ORDER"},
                                 "itertools.combinations(range(3), num_colors)，颜色名按 SPAWN_COLOR_ORDER", pool=CONSTS["SPAWN_COLOR_ORDER"], choose=n_color),
                  f"红蓝绿里取 {n_color} 种", Q, "配额"),
            field("spawn_total", "`spawn_total`（生成几块）", spawn_domain, range_text(spawn_domain["lo"], spawn_domain["hi"]), Q, "配额"),
            field("initialize_color_order", "`initialize_color_order`（颜色创建顺序）",
                  derived_domain(sampling, "permutations_of", "permutations_of_constant", {"pool": "const:INITIALIZE_COLOR_DEFS"}, "itertools.permutations(('blue','red','green'))", pool=CONSTS["INITIALIZE_COLOR_DEFS"]),
                  "蓝红绿 6 种排列", Q, "配额"),
            field("spawn_count", "`spawn_count[颜色]`（每色生成几块）",
                  {"kind": "coupled", "depends_on": ["spawn_total", "target_count", "colors_present"], "rule_note": "每色底数 max(target_count, 1)，余量逐个随机摊到场上颜色；单色直接取 max(spawn_total, target_count)"},
                  "每色至少 max(目标,1)，余量随机摊", {"kind": "rng_ep", "draws": "max(0, spawn_total - sum(max(target,1)))"}, "`rng_ep` 逐条随机（耦合）"),
            field("spawn_order", "方块生成顺序",
                  {"kind": "derived", "from": ["spawn_count"], "expr": "把 (颜色, 该色序号) 展开后整体打乱，等价于 torch.randperm(len(cube_tasks))"},
                  "(颜色, 序号) 的随机排列", {"kind": "rng_ep", "call": "permutation"}, "`rng_ep.permutation`"),
            field("button_xy", "`button_xy`（按钮中心）", continuous(button),
                  f"x∈[{g(button['button_x']['lo'])},{g(button['button_x']['hi'])}] y∈[{g(button['button_y']['lo'])},{g(button['button_y']['hi'])}]",
                  {"kind": "stratify", "resample": "none"}, "分层"),
            field("board_pose", "`board.xy`、`board.yaw_deg`（孔板）", continuous(board),
                  f"x∈[{g(board['board_x']['lo'])},{g(board['board_x']['hi'])}] y∈[{g(board['board_y']['lo'])},{g(board['board_y']['hi'])}]，yaw∈[{g(board['board_yaw']['lo'])}°,{g(board['board_yaw']['hi'])}°]",
                  {"kind": "stratify", "resample": "none"}, "分层"),
            field("cube_pose", "`cubes[i].xy`、`yaw_rad`（每块方块）", continuous(cubes),
                  f"x∈[{g(cubes['cube_x']['lo'])},{g(cubes['cube_x']['hi'])}] y∈[{g(cubes['cube_y']['lo'])},{g(cubes['cube_y']['hi'])}]，yaw 0～2π",
                  {"kind": "stratify", "resample": "whole_region", "note": "第 0 块首次尝试用分层点并计入配额；其余块粗箱轮转；被拒后照 spawn_random_cube 在整个区域重抽，最多 256 次"},
                  "第 0 块首次尝试分层；其余块粗箱轮转；被拒整域重抽"),
        ],
        "事件": [
            field("put_in_color", "`put_in_color` 目标色种数", put_color_domain, "/".join(str(k) for k in put_color_domain["values"]), Q, "配额"),
            field("target_pool", "`target_pool`（要投入的颜色子集）",
                  {"kind": "coupled", "depends_on": ["colors_present", "put_in_color"], "universe_recipe": "场上颜色里取 put_in_color 种的全部子集"},
                  "场上颜色的子集", BALANCED, "合法候选内平衡"),
            field("put_in_total", "`put_in_total`（投入几块）", put_domain, range_text(put_domain["lo"], put_domain["hi"]), Q, "配额"),
            field("target_count", "`target_count[颜色]`（每色投几块）",
                  {"kind": "coupled", "depends_on": ["put_in_total", "target_pool"], "rule": "allow_zero",
                   "note": "单色直接给总数；多目标色把总数逐个随机分给目标色，某色可为 0（原值 94449db）"},
                  TARGET_TEXT_V1, {"kind": "rng_ep", "draws": "put_in_total"}, "`rng_ep` 逐条随机（耦合）"),
            field("actions", "`actions`（抓哪块）",
                  {"kind": "derived", "from": ["initialize_color_order", "target_count", "spawn_order"], "expr": "按 initialize_color_order 遍历定义表，每色取生成列表最前 target_count 块"},
                  "按颜色创建顺序遍历，每色取生成列表最前 `target_count` 块", DERIVED, "推出"),
        ],
    }


# ── RouteStick ──────────────────────────────────────────────────────────────
def routestick_group(sampling: dict[str, Any], difficulty: str) -> dict[str, Any]:
    cfg = f"parameters.RouteStick.configs.{difficulty}"
    config = sampling["parameters"]["RouteStick"]["configs"][difficulty]
    walk = "parameters.RouteStick.walk"
    count = int(sampling["positions"]["RouteStick"]["obstacle_color"]["count"])
    length_domain = derived_domain(sampling, "int_range", "closed_int_range", {"pair": f"{cfg}.length"}, "[pair[0] … pair[1]] 闭区间")
    start_domain = derived_domain(sampling, "enum", "node_values", {"node_indices": f"{walk}.node_indices"}, "可踩节点值表本身；生成器用 node_indices.index(v) 映回局部槽位")
    edge_domain = derived_domain(sampling, "coupled", "linear_adjacency_edges",
                                 {"node_indices": f"{walk}.node_indices", "neighbor_order": f"{walk}.neighbor_order", "backtrack": f"{cfg}.backtrack"},
                                 "局部索引 ±1 且不越界的全部有向边；backtrack=false 时剔除上一步，端点无路可走被迫掉头", depends_on=["start_node", "L"])
    direction_domain = derived_domain(sampling, "enum", "direction_pair", {"direction": f"{walk}.direction"}, "[less_than, otherwise]")
    rotation = {"rotation_deg": component(sampling, "subtract_span", {"subtract": "positions.RouteStick.yaw_deg.subtract", "scale": "positions.RouteStick.yaw_deg.scale"}, "[-subtract, -subtract + scale]", "deg")}
    rgb = {"rgb_channel": component(sampling, "unit_interval_half_open", {}, "torch.rand → [0, 1)", "1")}
    backtrack = "允许回退" if bool(config["backtrack"]) else "不许回退：剔除上一步，端点被迫掉头"
    return {
        "task": "RouteStick", "difficulty": difficulty,
        "初始化": [
            field("rotation_deg", "`rotation_deg`（整排绕世界原点转）", continuous(rotation),
                  f"[{g(rotation['rotation_deg']['lo'])}°, {g(rotation['rotation_deg']['hi'])}°]", {"kind": "stratify", "resample": "none"}, "分层"),
            field("obstacle_rgb", f"`obstacle_rgb[{count}]`（{count} 根障碍柱颜色）", {**continuous(rgb, closed="[)"), "per_object": count},
                  "每根一个随机 RGB，各通道 [0,1)", {"kind": "rng_ep", "draws": f"{count} × 3"}, "`rng_ep` 随机（只影响观感）"),
            field("grid_points", "9 个格点位置", {"kind": "derived", "from": ["rotation_deg"], "expr": "1×9 整排绕世界原点旋转 rotation_deg"},
                  "由 `rotation_deg` 唯一确定", DERIVED, "推出"),
        ],
        "事件": [
            field("L", "`L`（走几段）", length_domain, range_text(length_domain["lo"], length_domain["hi"]), Q, "配额"),
            field("start_node", "起点 `nodes[0]`", start_domain, "/".join(str(v) for v in start_domain["values"]), Q, f"配额各 {GROUP_SIZE // len(start_domain['values'])}"),
            field("edge", "每段去哪（有向边）", edge_domain, f"线性邻接 ±1；{backtrack}", BALANCED, "合法候选内平衡"),
            field("direction", "每段绕行方向 `directions`", direction_domain, " / ".join(direction_domain["values"]), BALANCED, "合法候选内平衡"),
        ],
    }


# ── 视频任务共用 ────────────────────────────────────────────────────────────
def swap_pairs_field() -> dict[str, Any]:
    return field("swap_pairs", "`swap_pairs[k].partner`（交换搭档）",
                 {"kind": "derived", "from": ["initiators", "layout"], "expr": "每段交换开始时与发起者水平距离最近的对象，等距取序号小者；执行时按实际位姿重算，不符判失败"},
                 "交换开始时的水平最近邻，等距取序号小者", DERIVED, "推出（执行时核验，不符即失败）")


def candidates_field(sampling: dict[str, Any]) -> dict[str, Any]:
    domain = derived_domain(sampling, "int_range", "one_to_max_trials", {"max_trials": "native_semantics.object_generation.max_trials"}, "[1, max_trials]")
    domain["values"] = None  # 只用于文案与范围，不铺配额
    return field("candidates_used", "`collision.candidates_used`（冻结用了第几个候选）", domain, f"{domain['lo']}～{domain['hi']}", DERIVED, "几何／碰撞被拒后重抽的落地结果")


def unmask_group(sampling: dict[str, Any], difficulty: str) -> dict[str, Any]:
    cfg = f"parameters.VideoUnmaskSwap.configs.{difficulty}"
    config = sampling["parameters"]["VideoUnmaskSwap"]["configs"][difficulty]
    n_bins = int(config["bin"])
    sel = "parameters.VideoUnmaskSwap.object_selection"
    containers = "positions.VideoUnmaskSwap.containers"
    swaps = derived_domain(sampling, "int_range", "closed_int_range_from_bounds", {"lo": f"{cfg}.swap_min", "hi": f"{cfg}.swap_max"}, "[swap_min … swap_max] 闭区间")
    picks = derived_domain(sampling, "int_range", "closed_int_range_from_bounds", {"lo": f"{cfg}.pick_min", "hi": f"{cfg}.pick_max"}, "[pick_min … pick_max] 闭区间")
    layout_inputs = {"bins": f"{cfg}.bin", "order": f"{containers}.region3_choice.order"}
    if n_bins == 3:
        layout = field("layout_type", "`layout_type`（锚点布局）",
                       derived_domain(sampling, "enum", "layout_choice_by_bins", layout_inputs, "bins==3 → region3_choice.order；否则恒为 region4"),
                       "三角／直线", Q, "配额")
    else:
        layout = field("layout_type", "`layout_type`（锚点布局）",
                       derived_domain(sampling, "constant", "layout_choice_by_bins", layout_inputs, "bins==3 → region3_choice.order；否则恒为 region4"),
                       "四点（固定）", {"kind": "constant"}, "常量")
    bin_half = {"recipe": "bin_half_from_cube_half", "inputs": {"cube_half": "const:cube_half_size"}}
    comps: dict[str, dict[str, Any]] = {"theta_rad": component(sampling, "pair", {"pair": f"{containers}.layout_rotation_range_rad"}, "[pair[0], pair[1]]（原单位就是弧度）", "rad")}
    pose: dict[str, dict[str, Any]] = {}
    for i in range(n_bins):
        for axis in ("dx", "dy"):
            pose[f"bin{i}_{axis}"] = component(sampling, "offset_limit", {"region_half": f"{containers}.region_half_size", "object_half": bin_half},
                                               "±(region_half − (cube_half*2.5+0.005)*0.5)，公式取自 native_semantics.object_generation.bin_half_size", "m")
        pose[f"bin{i}_yaw"] = component(sampling, "zero_to", {"scale": f"{containers}.yaw_scale_deg"}, "[0, scale]", "deg")
    limit = pose["bin0_dx"]["hi"]
    names = [f"bin_{i}" for i in range(n_bins)]
    return {
        "task": "VideoUnmaskSwap", "difficulty": difficulty,
        "初始化": [
            layout,
            field("selected", "`selected`（藏物容器排序）",
                  derived_domain(sampling, "permutations_of", "permutations_of_range", {"n": f"{sel}.hidden_bin_permutation_size"}, "itertools.permutations(range(3))", pool=[0, 1, 2]),
                  "前三个容器的 6 种排列", Q, "配额"),
            field("color_order", "`color_order`（藏物颜色顺序）",
                  derived_domain(sampling, "permutations_of", "permutations_of_constant", {"pool": "const:UNMASK_COLOR_ORDER"}, "itertools.permutations(('red','green','blue'))", pool=CONSTS["UNMASK_COLOR_ORDER"]),
                  "红绿蓝 6 种排列", Q, "配额"),
            field("theta_rad", "`theta_rad`（整组绕原点转）", continuous(comps),
                  f"[{g(comps['theta_rad']['lo'])}, {g(comps['theta_rad']['hi'])}] 弧度（原单位就是弧度，不是度）", {"kind": "stratify", "resample": "coarse_bin"}, "分层；被拒同粗箱重抽"),
            field("bin_pose", "`bins[i].xy`、`yaw_deg`（每个容器）", {**continuous(pose), "per_object": n_bins},
                  f"锚点旋转后各偏移 ≤ {limit:.4f}，yaw 0～{g(pose['bin0_yaw']['hi'])}°", {"kind": "stratify", "resample": "coarse_bin"}, "分层；被拒同粗箱重抽"),
            field("hidden", "`hidden`（颜色→容器）", {"kind": "derived", "from": ["selected", "color_order"], "expr": "color_order[i] → bin_{selected[i]}"},
                  "由 `selected` + `color_order` 算出", DERIVED, "推出"),
            field("empty", "`empty`（空容器）", {"kind": "derived", "from": ["selected"], "expr": "range(n_bins) 里不在 selected 的容器"},
                  "不在 `selected` 里的容器", DERIVED, "推出"),
            candidates_field(sampling),
        ],
        "事件": [
            field("n_swaps", "`n_swaps`（交换几次）", swaps, range_text(swaps["lo"], swaps["hi"]), Q, "配额"),
            field("n_picks", "`n_picks`（视频后抓几个）", picks, range_text(picks["lo"], picks["hi"]), Q, "配额"),
            field("swap_initiators_first_two", "前两个发起者 `swap_initiators[:2]`",
                  derived_domain(sampling, "permutations_of", "permutations_of_range_k", {"n": f"{sel}.hidden_bin_permutation_size", "k": f"{sel}.swap_seed_target_count"}, "itertools.permutations(range(3), 2)", pool=[0, 1, 2]),
                  "3 取 2 的 6 种有序对（原代码把藏物序号当生成序号用，照抄）", Q, "配额"),
            field("swap_initiators_third", "第三个发起者 `swap_initiators[2]`",
                  {"kind": "coupled", "depends_on": ["swap_initiators_first_two"], "universe": names, "note": "range(n_bins) 去掉前两个发起者"},
                  "其余生成序号", BALANCED, "合法候选内平衡"),
            field("pick_order", "`pick_order`（视频后抓取顺序）",
                  {"kind": "derived", "from": ["selected", "n_picks"], "expr": "object_selection.pickup_selected_indices[:n_picks] 索引进 selected"},
                  "`selected` 的前 `n_picks` 个", DERIVED, "推出"),
            swap_pairs_field(),
        ],
    }


def repick_group(sampling: dict[str, Any], difficulty: str) -> dict[str, Any]:
    cfg = f"parameters.VideoRepick.configs.{difficulty}"
    config = sampling["parameters"]["VideoRepick"]["configs"][difficulty]
    n_cubes = int(config["cube"])
    plain = "positions.VideoRepick.easy_medium_cubes"
    swaps = derived_domain(sampling, "int_range", "closed_int_range_from_bounds", {"lo": f"{cfg}.swap_min", "hi": f"{cfg}.swap_max"}, "[swap_min … swap_max] 闭区间")
    repeats = derived_domain(sampling, "int_range_half_open", "half_open_int_range", {"low": "parameters.VideoRepick.num_repeats.low", "high_exclusive": "parameters.VideoRepick.num_repeats.high_exclusive"},
                             "[low, high_exclusive)，源码 torch.randint(1, 4) 半开，不含 4")
    theta_button = {
        "theta_rad": component(sampling, "pair", {"pair": f"{plain}.layout_rotation_range_rad"}, "[pair[0], pair[1]]（原单位就是弧度）", "rad"),
        "button_x": component(sampling, "center_pm_half_range", {"center": "positions.VideoRepick.button.center_xy[0]", "span": "positions.VideoRepick.button.randomize_range[0]"}, "[center - span/2, center + span/2]", "m"),
        "button_y": component(sampling, "center_pm_half_range", {"center": "positions.VideoRepick.button.center_xy[1]", "span": "positions.VideoRepick.button.randomize_range[1]"}, "[center - span/2, center + span/2]", "m"),
    }
    pose: dict[str, dict[str, Any]] = {}
    for i in range(n_cubes):
        for axis in ("dx", "dy"):
            pose[f"cube{i}_{axis}"] = component(sampling, "offset_limit", {"region_half": f"{plain}.region_half_size", "object_half": "const:cube_half_size"}, "±(region_half − cube_half)", "m")
        pose[f"cube{i}_yaw"] = component(sampling, "pair", {"pair": f"{plain}.yaw_range_rad"}, "[pair[0], pair[1]]", "rad")
    limit = pose["cube0_dx"]["hi"]
    tb = theta_button
    return {
        "task": "VideoRepick", "difficulty": difficulty,
        "初始化": [
            field("layout_type", "`layout_type`（锚点布局）",
                  derived_domain(sampling, "enum", "layout_choice_by_bins", {"bins": f"{cfg}.cube", "order": f"{plain}.region3_choice.order"}, "cube==3 → region3_choice.order"),
                  "三角／直线", Q, "配额"),
            field("color", "`color`（三块统一颜色）",
                  derived_domain(sampling, "enum", "enum_from_constant", {"pool": "const:REPICK_COLOR_ORDER"}, "REPICK_COLOR_ORDER"),
                  "红／蓝／绿", Q, "配额"),
            field("theta_button", "`theta_rad`、`button_xy`", continuous(theta_button),
                  f"[{g(tb['theta_rad']['lo'])}, {g(tb['theta_rad']['hi'])}] 弧度；x∈[{g(tb['button_x']['lo'])},{g(tb['button_x']['hi'])}] y∈[{g(tb['button_y']['lo'])},{g(tb['button_y']['hi'])}]",
                  {"kind": "stratify", "resample": "coarse_bin", "note": "θ 被拒同粗箱重抽；按钮在候选循环外算一次，不参与重抽"}, "分层（θ 被拒同粗箱重抽，按钮不参与重抽）"),
            field("cube_pose", "`cubes[i].xy`、`yaw_rad`（每块方块）", {**continuous(pose), "per_object": n_cubes},
                  f"锚点旋转后各偏移 ≤ {limit:.4f}，yaw 0～2π", {"kind": "stratify", "resample": "coarse_bin"}, "分层；方块间距 < 0.02、压按钮或碰撞被拒后同粗箱重抽"),
            candidates_field(sampling),
        ],
        "事件": [
            field("n_swaps", "`n_swaps`（交换几次）", swaps, range_text(swaps["lo"], swaps["hi"]), Q, "配额"),
            field("num_repeats", "`num_repeats`（重复抓放次数）", repeats, range_text(repeats["lo"], repeats["high_exclusive"] - 1), Q, "配额"),
            field("target", "`target`（目标方块）", derived_domain(sampling, "enum", "range_of_n", {"n": f"{cfg}.cube"}, "range(cube)，值是方块生成序号"), "三块之一", Q, "配额"),
            field("tail", "后续发起者顺序 `tail`",
                  derived_domain(sampling, "permutations_of", "permutations_of_range_minus_one", {"n": f"{cfg}.cube"}, "itertools.permutations(range(cube - 1))，索引进 others = 除 target 外的两块", pool=[0, 1]),
                  "另外两块的 2 种排列", Q, "配额"),
            swap_pairs_field(),
        ],
    }


BUILDERS = {"BinFill": binfill_group, "RouteStick": routestick_group, "VideoUnmaskSwap": unmask_group, "VideoRepick": repick_group}


def build_v1(sampling: dict[str, Any], sampling_path: Path) -> dict[str, Any]:
    from .specs import operand_sha256  # 惰性：避免 contract ↔ specs 循环

    groups = {f"{task}/{difficulty}": BUILDERS[task](sampling, difficulty) for task, difficulty in GROUPS}
    return {
        "contract_schema_version": CONTRACT_SCHEMA_VERSION,
        "contract_version": "v1",
        "contract_note": "注入规格的取值域与分配约定（事件表三列的机器可读版）；几何常量仍在 native_sampling.json，contract 里的派生数值由 check 每次回算核对",
        "generator_seed": DEFAULT_SEED,
        "group_size": GROUP_SIZE,
        "derives_from": str(sampling_path.relative_to(REPO_ROOT)) if sampling_path.is_relative_to(REPO_ROOT) else str(sampling_path),
        # 只算 v1 消费到的三档（作用域散列，见 specs.operand_sha256）：源码日后加档不改变 v1 的依据身份
        "derives_from_operands_sha256": operand_sha256(sampling, {d for _, d in GROUPS}),
        "excluded_groups": [list(item) for item in EXCLUDED_GROUPS],
        "overrides": [],
        "groups": groups,
    }


def build_v2(base: dict[str, Any]) -> dict[str, Any]:
    """v1 + BinFill 对齐 heldout：两档 spawn_total 区间、三档 target_count 规则；其余 120 行逐字不动。"""
    doc = copy.deepcopy(base)
    doc["contract_version"] = "v2"
    doc["contract_note"] = base["contract_note"] + "；v2 = v1 + BinFill 对齐 heldout 分支 2fa5660（medium/hard 方块数区间、多目标色每色至少 1 块）"
    doc["overrides"] = copy.deepcopy(BINFILL_HELDOUT_OVERRIDES)
    doc["target_count_rule_override"] = {
        "groups": ["BinFill/easy", "BinFill/medium", "BinFill/hard"], "field": "target_count",
        "native": {"rule": "allow_zero"}, "contract": {"rule": "each_target_at_least_one"},
        "source": TARGET_RULE_OVERRIDE_SOURCE, "reason": USER_DECISION,
        "note": "coupled 域没有 derivation，不进 CONTRACT_DERIVED 的回算；BinFill/easy 恒为单色，规则不起作用、规格逐位不变",
    }
    for item in BINFILL_HELDOUT_OVERRIDES:
        group = doc["groups"][item["group"]]
        target = next(f for section in ("初始化", "事件") for f in group[section] if f["key"] == item["field"])
        lo, hi = item["contract"]["lo"], item["contract"]["hi"]
        target["domain"].update({"lo": lo, "hi": hi, "values": list(range(lo, hi + 1))})
        target["domain_text"] = range_text(lo, hi)
    for difficulty in ("easy", "medium", "hard"):
        group = doc["groups"][f"BinFill/{difficulty}"]
        target = next(f for f in group["事件"] if f["key"] == "target_count")
        target["domain"]["rule"] = "each_target_at_least_one"
        target["domain"]["note"] = "单色直接给总数；多目标色先每色各 1，余量再逐个随机分（heldout 2fa5660 的 min_required_targets）"
        target["domain_text"] = TARGET_TEXT_V2
    return doc


def write_contract(doc: dict[str, Any], out: Path) -> Contract:
    contract = Contract(doc)  # 先做结构校验
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return contract


def report_check(contract: Contract, sampling: dict[str, Any]) -> tuple[bool, str]:
    mismatches, checked = derive_all(contract, sampling)
    _, problems = audit_overrides(contract, sampling)
    line = f"CONTRACT_DERIVED={'PASS' if not problems else 'FAIL'} fields={checked} mismatches={len(mismatches)} overrides={len(contract.overrides)} problems={len(problems)}"
    return not problems, line


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="注入取值域契约：生成 v1／v2 与离线回算核对")
    sub = parser.add_subparsers(dest="command", required=True)
    b1 = sub.add_parser("build-v1"); b1.add_argument("--sampling", default=str(DEFAULT_SAMPLING)); b1.add_argument("--out", required=True)
    b2 = sub.add_parser("build-v2"); b2.add_argument("--base", required=True); b2.add_argument("--out", required=True)
    ck = sub.add_parser("check"); ck.add_argument("--contract", required=True); ck.add_argument("--sampling", default=str(DEFAULT_SAMPLING))
    args = parser.parse_args(argv)
    try:
        if args.command == "build-v1":
            sampling_path = Path(args.sampling).resolve()
            sampling = json.loads(sampling_path.read_text(encoding="utf-8"))
            contract = write_contract(build_v1(sampling, sampling_path), Path(args.out))
            ok, line = report_check(contract, sampling)
            print(f"CONTRACT_BUILT=v1 out={args.out} sha256={contract.sha256[:12]}…"); print(line)
            return 0 if ok else 1
        if args.command == "build-v2":
            base = json.loads(Path(args.base).read_text(encoding="utf-8"))
            if base.get("contract_version") != "v1":
                raise ContractError("build-v2 的 --base 必须是 v1 契约")
            contract = write_contract(build_v2(base), Path(args.out))
            sampling = json.loads(DEFAULT_SAMPLING.read_text(encoding="utf-8"))
            ok, line = report_check(contract, sampling)
            print(f"CONTRACT_BUILT=v2 out={args.out} sha256={contract.sha256[:12]}…"); print(line)
            return 0 if ok else 1
        contract = load_contract(args.contract)
        sampling = json.loads(Path(args.sampling).read_text(encoding="utf-8"))
        ok, line = report_check(contract, sampling)
        _, problems = audit_overrides(contract, sampling)
        for item in problems[:10]:
            print(f"  问题：{item}")
        print(line)
        return 0 if ok else 1
    except ContractError as exc:
        print(f"CONTRACT_ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
