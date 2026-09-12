"""从冻结规格统计「结果分布」，生成 11 组「事件 / 取值域 / 分配 / 结果分布」四列表（每组分「初始化」「事件」两张）。

* 只读 ``artifacts/injection/<run-id>/specs/<任务>/<难度>.json``、``scripts/configs/newtask-v2/native_sampling.json``
  与该运行 ``manifest.json`` 记录的契约 ``scripts/configs/newtask-v2/injection_contract_v*.json``；
  「取值域」「分配」两列**直接取契约的 ``domain_text`` / ``allocation_text``**，本文件只算「结果分布」列。
  只依赖标准库与 ``scripts.injection.contract``（纯标准库），不 import matplotlib，不依赖 ``tests/``
  （视频任务反算偏移量需要的 ``rotate`` 在本文件自写，刻意不从出图脚本 import，免得把 matplotlib 拖进校验路径）。
* ``--write``：把 11 张表写进 ``NEW_VALUE_DISTRIBUTION_BEFORE.md`` 的
  ``<!-- AUTO:EVENT_TABLES BEGIN -->`` / ``<!-- AUTO:EVENT_TABLES END -->`` 标记区间（标记行本身保留）。
* ``--check``（默认）：重新生成后与文档现存区间逐行比对，打 ``EVENT_TABLES=PASS groups=11 rows=… drift=0``。

「结果分布」单元格只有四种写法，格式定死以保证 ``--check`` 逐字节稳定：
  离散量  ``4:34 5:33 6:33``（按合法取值域顺序，含 0）
  连续量  ``10 箱各 10，实测 [-0.2492, -0.1510]``（粗箱计数来自 ``sampling_cells``，不全 10 时逐箱列出）
  耦合量  ``a→b:45 …（共 150 次交换）；未覆盖 …``（频数降序、平局按键名）
  推出量  ``推出：…``（同耦合量格式，前缀标明它不是随机源）
分母不是 100 条 episode 时一律在末尾注明 ``（共 N 段/次交换/块/个动作）``。
"""

from __future__ import annotations

import argparse
import difflib
import itertools
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
from scripts.injection.contract import Contract, ContractError, GroupContract, load_contract  # noqa: E402

NATIVE_SAMPLING_CONFIG = REPO_ROOT / "scripts" / "configs" / "newtask-v2" / "native_sampling.json"
DOC = HERE / "NEW_VALUE_DISTRIBUTION_BEFORE.md"
DEFAULT_RUN_ID = "20260911-contract-v3-07"  # 14 组的冻结规格（与 06 逐条相同，OLD_GROUPS_EQUIVALENCE compared=1400 differences=0）
BEGIN = "<!-- AUTO:EVENT_TABLES BEGIN -->"
END = "<!-- AUTO:EVENT_TABLES END -->"

from window_timeline import GROUPS  # noqa: E402  # 14 组的唯一真源（纯标准库模块）
COARSE_BINS = 10
MAX_KEYS = 12  # 频数键超过这个数只列前几个，避免把表撑爆

# 颜色定义（与 scripts/injection/specs.py 一致，照抄不 import）；几何常量已随取值域文案移入契约，本文件不再需要
SPAWN_COLOR_ORDER = ("red", "blue", "green")
INITIALIZE_COLOR_DEFS = ("blue", "red", "green")
UNMASK_COLOR_ORDER = ("red", "green", "blue")
REPICK_COLOR_ORDER = ("red", "blue", "green")
ROUTE_EDGES = ["0→2", "2→0", "2→4", "4→2", "4→6", "6→4", "6→8", "8→6"]  # 线性邻接 ±1 的 8 条有向边


# ── 通用 ────────────────────────────────────────────────────────────────────
def load_sampling(root: Path) -> dict[str, Any]:
    """读该运行冻结时用的采样配置（几何常量）：以 manifest.json 的 sampling_config_path 为准，没记时回退原值文件。"""
    manifest_path = root / "manifest.json"
    config_path = NATIVE_SAMPLING_CONFIG
    if manifest_path.is_file():
        recorded = json.loads(manifest_path.read_text(encoding="utf-8")).get("sampling_config_path")
        if recorded:
            config_path = REPO_ROOT / recorded
    return json.loads(config_path.read_text(encoding="utf-8"))


def rotate(point: Iterable[float], theta: float) -> tuple[float, float]:
    """绕世界原点旋转，与 injection_specs.rotate_xy 同式。"""
    x, y = point
    c, s = math.cos(theta), math.sin(theta)
    return (x * c - y * s, x * s + y * c)


def load_group(root: Path, task: str, difficulty: str) -> list[dict[str, Any]]:
    doc = json.loads((root / "specs" / task / f"{difficulty}.json").read_text(encoding="utf-8"))
    return sorted(doc["episodes"], key=lambda item: item["episode"])


def fm(v: float, nd: int) -> str:
    return f"{v:.{nd}f}"


def unit_suffix(total: int, unit: str | None) -> str:
    return f"（共 {total} {unit}）" if unit else ""


def _pairs_text(pairs: list[tuple[str, int]], total_keys: int) -> str:
    text = " ".join(f"{k}:{v}" for k, v in pairs[:MAX_KEYS])
    if total_keys > MAX_KEYS:
        text += f" …另 {total_keys - MAX_KEYS} 类略"
    return text


def count_cell(counter: Counter, legal: list[str] | None = None, unit: str | None = None) -> str:
    """离散量：合法取值域顺序在前（含 0），域外出现过的键按名追加。"""
    keys = list(legal) if legal else []
    keys += [k for k in sorted(counter) if k not in keys]
    pairs = [(k, counter.get(k, 0)) for k in keys]
    return _pairs_text(pairs, len(keys)) + unit_suffix(sum(counter.values()), unit)


def freq_cell(counter: Counter, universe: list[str] | None = None, unit: str | None = None, derived: bool = False) -> str:
    """耦合量／推出量：频数降序（平局按键名），带「未覆盖」清单。"""
    pairs = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
    text = _pairs_text(pairs, len(pairs)) + unit_suffix(sum(counter.values()), unit)
    if universe is not None:
        missing = [k for k in universe if counter.get(k, 0) == 0]
        text += "；未覆盖 " + ("、".join(missing) if missing else "无")
    return ("推出：" if derived else "") + text


def bins_text(bin_ids: Iterable[int]) -> str:
    counts = Counter(bin_ids)
    per_bin = [counts.get(b, 0) for b in range(COARSE_BINS)]
    if all(c == per_bin[0] for c in per_bin):
        return f"{COARSE_BINS} 箱各 {per_bin[0]}"
    return "箱计数 " + ",".join(str(c) for c in per_bin)


def cont_seg(label: str, records: list[dict[str, Any]], cell_key: str, values: list[float], nd: int) -> str:
    """连续量一段：采样输入落在哪些粗箱（sampling_cells 第一维）+ 实际值极值。"""
    bins = bins_text(r["sampling_cells"][cell_key][0] for r in records)
    return f"{label} {bins}，实测 [{fm(min(values), nd)}, {fm(max(values), nd)}]"


def actual_bins_text(values: list[float], lo: float, hi: float) -> str:
    """实际值（非采样输入）落进 [lo, hi] 等分 10 箱的计数。"""
    width = (hi - lo) / COARSE_BINS
    ids = [min(max(int((v - lo) / width), 0), COARSE_BINS - 1) for v in values]
    return bins_text(ids)


def rng_text(values: list[float], nd: int) -> str:
    return f"[{fm(min(values), nd)}, {fm(max(values), nd)}]"


def range_text(lo, hi) -> str:
    return str(lo) if lo == hi else f"{lo}～{hi}"


def color_sorted(colors: Iterable[str], order: tuple[str, ...]) -> list[str]:
    return sorted(colors, key=order.index)


# ── BinFill ────────────────────────────────────────────────────────────────
# 各 *_rows 只算「结果分布」列，返回 (key, label, 结果分布)；「取值域」「分配」两列来自契约（render_group_table 合并）。
def binfill_rows(records: list[dict[str, Any]], config: dict[str, Any], gc: GroupContract) -> list[tuple[str, str, str]]:
    n_color = int(config["color"])
    put_color_legal = [int(v) for v in gc.values("put_in_color")]
    spawn_legal = [str(v) for v in gc.values("spawn_total")]
    put_legal = [str(v) for v in gc.values("put_in_total")]
    colors_legal = ["+".join(c) for c in itertools.combinations(SPAWN_COLOR_ORDER, n_color)]
    colors_obs = Counter("+".join(color_sorted(r["objects"]["colors_present"], SPAWN_COLOR_ORDER)) for r in records)
    pool_obs = Counter("+".join(color_sorted(r["objects"]["target_pool"], SPAWN_COLOR_ORDER)) for r in records)
    pool_universe: list[str] = []
    for present in colors_legal:
        for k in put_color_legal:
            for combo in itertools.combinations(present.split("+"), k):
                key = "+".join(combo)
                if key not in pool_universe:
                    pool_universe.append(key)
    order_legal = ["-".join(p) for p in itertools.permutations(INITIALIZE_COLOR_DEFS)]
    target_items = Counter(f"{c}={k}" for r in records for c, k in r["objects"]["target_count"].items())
    spawn_items = Counter(f"{c}={k}" for r in records for c, k in r["objects"]["spawn_count"].items())
    first_color = Counter(r["layout"]["cubes"][0]["color"] for r in records)
    cubes = [c for r in records for c in r["layout"]["cubes"]]
    cx, cy, cyaw = [c["xy"][0] for c in cubes], [c["xy"][1] for c in cubes], [c["yaw_rad"] for c in cubes]
    pick_index = Counter(a["pick"].rsplit("_", 1)[1] for r in records for a in r["actions"])
    pick_legal = [str(i) for i in sorted(int(k) for k in pick_index)]
    return [
        ("dynamic", "`dynamic`（方块分批出现还是开局全在）", count_cell(Counter(str(r["layout"]["dynamic"]) for r in records), ["True", "False"])),
        ("colors_present", "`colors_present`（场上有哪些颜色）", count_cell(colors_obs, colors_legal)),
        ("put_in_color", "`put_in_color` 目标色种数",
         count_cell(Counter(str(len(r["objects"]["target_pool"])) for r in records), [str(k) for k in put_color_legal])),
        ("target_pool", "`target_pool`（要投入的颜色子集）", freq_cell(pool_obs, pool_universe)),
        ("spawn_total", "`spawn_total`（生成几块）", count_cell(Counter(str(r["objects"]["spawn_total"]) for r in records), spawn_legal)),
        ("put_in_total", "`put_in_total`（投入几块）", count_cell(Counter(str(r["objects"]["put_in_total"]) for r in records), put_legal)),
        ("initialize_color_order", "`initialize_color_order`（颜色创建顺序）",
         count_cell(Counter("-".join(r["objects"]["initialize_color_order"]) for r in records), order_legal)),
        ("target_count", "`target_count[颜色]`（每色投几块）", freq_cell(target_items, unit="个颜色项")),
        ("spawn_count", "`spawn_count[颜色]`（每色生成几块）", freq_cell(spawn_items, unit="个颜色项")),
        ("spawn_order", "方块生成顺序", "生成序首块的颜色 " + count_cell(first_color, list(SPAWN_COLOR_ORDER))),
        ("button_xy", "`button_xy`（按钮中心）",
         "；".join([cont_seg("x", records, "button_x", [r["layout"]["button_xy"][0] for r in records], 4),
                    cont_seg("y", records, "button_y", [r["layout"]["button_xy"][1] for r in records], 4)])),
        ("board_pose", "`board.xy`、`board.yaw_deg`（孔板）",
         "；".join([cont_seg("x", records, "board_x", [r["layout"]["board"]["xy"][0] for r in records], 4),
                    cont_seg("y", records, "board_y", [r["layout"]["board"]["xy"][1] for r in records], 4),
                    cont_seg("yaw", records, "board_yaw", [r["layout"]["board"]["yaw_deg"] for r in records], 2)])),
        ("cube_pose", "`cubes[i].xy`、`yaw_rad`（每块方块）",
         "采样输入 cube_x " + bins_text(r["sampling_cells"]["cube_x"][0] for r in records)
         + "、cube_y " + bins_text(r["sampling_cells"]["cube_y"][0] for r in records)
         + "、cube_yaw " + bins_text(r["sampling_cells"]["cube_yaw"][0] for r in records)
         + f"；实际位置 x {actual_bins_text(cx, -0.28, 0.08)}，实测 {rng_text(cx, 4)}"
         + f"；y {actual_bins_text(cy, -0.23, 0.23)}，实测 {rng_text(cy, 4)}"
         + f"；yaw 实测 {rng_text(cyaw, 2)}{unit_suffix(len(cubes), '块')}"),
        ("actions", "`actions`（抓哪块）", "推出：被抓方块的色内序号 " + count_cell(pick_index, pick_legal, "个动作")),
    ]


# ── RouteStick ─────────────────────────────────────────────────────────────
def routestick_points(rotation_deg: float) -> list[tuple[float, float]]:
    return [rotate((-0.1, (col - 4) * 0.07), math.radians(rotation_deg)) for col in range(9)]


def routestick_rows(records: list[dict[str, Any]], config: dict[str, Any], gc: GroupContract) -> list[tuple[str, str, str]]:
    edges = Counter(f"{r['actions']['nodes'][i]}→{r['actions']['nodes'][i + 1]}" for r in records for i in range(len(r["actions"]["nodes"]) - 1))
    directions = Counter(d for r in records for d in r["actions"]["directions"])
    rgb = [v for r in records for stick in r["layout"]["obstacle_rgb"] for v in stick]
    points = [p for r in records for p in routestick_points(r["layout"]["rotation_deg"])]
    px, py = [p[0] for p in points], [p[1] for p in points]
    count = len(records[0]["layout"]["obstacle_rgb"])
    return [
        ("L", "`L`（走几段）", count_cell(Counter(str(r["objects"]["L"]) for r in records), [str(v) for v in gc.values("L")])),
        ("start_node", "起点 `nodes[0]`", count_cell(Counter(str(r["actions"]["nodes"][0]) for r in records), [str(v) for v in gc.values("start_node")])),
        ("rotation_deg", "`rotation_deg`（整排绕世界原点转）",
         cont_seg("", records, "rotation_deg", [r["layout"]["rotation_deg"] for r in records], 2).strip()),
        ("edge", "每段去哪（有向边）", freq_cell(edges, ROUTE_EDGES, "段")),
        ("direction", "每段绕行方向 `directions`", count_cell(directions, list(gc.values("direction")), "段")),
        ("obstacle_rgb", f"`obstacle_rgb[{count}]`（{count} 根障碍柱颜色）",
         f"通道值 {actual_bins_text(rgb, 0.0, 1.0)}，实测 {rng_text(rgb, 3)}{unit_suffix(len(rgb), '个通道值')}"),
        ("grid_points", "9 个格点位置", f"推出：{len(points)} 个格点 x 实测 {rng_text(px, 4)}，y 实测 {rng_text(py, 4)}"),
    ]


# ── 视频任务共用 ────────────────────────────────────────────────────────────
def offset_segments(records: list[dict[str, Any]], anchors_cfg: dict[str, Any], items_key: str, prefix: str,
                    yaw_key: str, yaw_nd: int) -> str:
    """每个对象一段：dx/dy/yaw 的粗箱计数 + 反算偏移量极值 + yaw 极值。"""
    n_obj = len(records[0]["layout"][items_key])
    segments = []
    for i in range(n_obj):
        dxs, dys, yaws = [], [], []
        for r in records:
            anchor = rotate(anchors_cfg[r["layout"]["type"]][i], r["layout"]["theta_rad"])
            item = r["layout"][items_key][i]
            dxs.append(item["xy"][0] - anchor[0])
            dys.append(item["xy"][1] - anchor[1])
            yaws.append(item[yaw_key])
        parts = {axis: bins_text(r["sampling_cells"][f"{prefix}{i}_{axis}"][0] for r in records) for axis in ("dx", "dy", "yaw")}
        if len(set(parts.values())) == 1:
            bins = f"dx/dy/yaw 各 {parts['dx']}"
        else:
            bins = "，".join(f"{axis} {text}" for axis, text in parts.items())
        segments.append(f"bin_{i}：{bins}，偏移实测 {rng_text(dxs + dys, 4)}，yaw 实测 {rng_text(yaws, yaw_nd)}")
    return "；".join(segments)


def swap_row(records: list[dict[str, Any]], names: list[str]) -> tuple[str, str, str]:
    pairs = Counter(f"{p['initiator']}→{p['partner']}" for r in records for p in r["actions"]["swap_pairs"])
    universe = [f"{a}→{b}" for a in names for b in names if a != b]
    return ("swap_pairs", "`swap_pairs[k].partner`（交换搭档）", freq_cell(pairs, universe, "次交换", derived=True))


def candidates_row(records: list[dict[str, Any]]) -> tuple[str, str, str]:
    used = Counter(str(r["collision"]["candidates_used"]) for r in records)
    legal = [str(k) for k in sorted(int(k) for k in used)]
    return ("candidates_used", "`collision.candidates_used`（冻结用了第几个候选）", count_cell(used, legal))


def unmask_rows(records: list[dict[str, Any]], config: dict[str, Any], anchors_cfg: dict[str, Any], gc: GroupContract) -> list[tuple[str, str, str]]:
    n_bins = int(config["bin"])
    names = [f"bin_{i}" for i in range(n_bins)]
    layout_legal = ["region3_tri", "region3_line"] if n_bins == 3 else ["region4"]
    selected_legal = ["-".join(str(v) for v in p) for p in itertools.permutations(range(3))]
    color_legal = ["-".join(p) for p in itertools.permutations(UNMASK_COLOR_ORDER)]
    first_two_legal = [f"bin_{a}-bin_{b}" for a, b in itertools.permutations(range(3), 2)]
    hidden = Counter(f"{c}→{b}" for r in records for c, b in r["objects"]["hidden"].items())
    hidden_universe = [f"{c}→bin_{i}" for c in UNMASK_COLOR_ORDER for i in range(3)]
    empty = Counter("、".join(r["objects"]["empty"]) or "无" for r in records)
    picks = Counter("→".join(r["objects"]["pick_order"]) for r in records)
    return [
        ("n_swaps", "`n_swaps`（交换几次）",
         count_cell(Counter(str(r["objects"]["n_swaps"]) for r in records), [str(v) for v in gc.values("n_swaps")])),
        ("n_picks", "`n_picks`（视频后抓几个）",
         count_cell(Counter(str(r["objects"]["n_picks"]) for r in records), [str(v) for v in gc.values("n_picks")])),
        ("layout_type", "`layout_type`（锚点布局）", count_cell(Counter(r["layout"]["type"] for r in records), layout_legal)),
        ("selected", "`selected`（藏物容器排序）",
         count_cell(Counter("-".join(str(v) for v in r["objects"]["selected"]) for r in records), selected_legal)),
        ("color_order", "`color_order`（藏物颜色顺序）",
         count_cell(Counter("-".join(r["objects"]["color_order"]) for r in records), color_legal)),
        ("swap_initiators_first_two", "前两个发起者 `swap_initiators[:2]`",
         count_cell(Counter("-".join(r["objects"]["swap_initiators"][:2]) for r in records), first_two_legal)),
        ("swap_initiators_third", "第三个发起者 `swap_initiators[2]`",
         freq_cell(Counter(r["objects"]["swap_initiators"][2] for r in records), names)),
        ("theta_rad", "`theta_rad`（整组绕原点转）",
         cont_seg("", records, "theta_rad", [r["layout"]["theta_rad"] for r in records], 2).strip()),
        ("bin_pose", "`bins[i].xy`、`yaw_deg`（每个容器）", offset_segments(records, anchors_cfg, "bins", "bin", "yaw_deg", 2)),
        ("hidden", "`hidden`（颜色→容器）", freq_cell(hidden, hidden_universe, "项", derived=True)),
        ("empty", "`empty`（空容器）", freq_cell(empty, derived=True)),
        ("pick_order", "`pick_order`（视频后抓取顺序）", freq_cell(picks, derived=True)),
        swap_row(records, names),
        candidates_row(records),
    ]


def repick_rows(records: list[dict[str, Any]], config: dict[str, Any], anchors_cfg: dict[str, Any], gc: GroupContract) -> list[tuple[str, str, str]]:
    names = ["bin_0", "bin_1", "bin_2"]
    tail_legal = [f"{a}-{b}" for a, b in itertools.permutations(names, 2)]
    return [
        ("n_swaps", "`n_swaps`（交换几次）",
         count_cell(Counter(str(r["objects"]["n_swaps"]) for r in records), [str(v) for v in gc.values("n_swaps")])),
        ("num_repeats", "`num_repeats`（重复抓放次数）", count_cell(Counter(str(r["objects"]["num_repeats"]) for r in records), [str(v) for v in gc.values("num_repeats")])),
        ("layout_type", "`layout_type`（锚点布局）", count_cell(Counter(r["layout"]["type"] for r in records), ["region3_tri", "region3_line"])),
        ("color", "`color`（三块统一颜色）", count_cell(Counter(r["objects"]["color"] for r in records), list(REPICK_COLOR_ORDER))),
        ("target", "`target`（目标方块）", count_cell(Counter(r["objects"]["target"] for r in records), names)),
        ("tail", "后续发起者顺序 `tail`", count_cell(Counter("-".join(r["objects"]["swap_initiators"][1:]) for r in records), tail_legal)),
        ("theta_button", "`theta_rad`、`button_xy`",
         "；".join([cont_seg("θ", records, "theta_rad", [r["layout"]["theta_rad"] for r in records], 2),
                    cont_seg("按钮 x", records, "button_x", [r["layout"]["button_xy"][0] for r in records], 4),
                    cont_seg("按钮 y", records, "button_y", [r["layout"]["button_xy"][1] for r in records], 4)])),
        ("cube_pose", "`cubes[i].xy`、`yaw_rad`（每块方块）", offset_segments(records, anchors_cfg, "cubes", "cube", "yaw_rad", 2)),
        swap_row(records, names),
        candidates_row(records),
    ]


# ── 渲染 ────────────────────────────────────────────────────────────────────
def group_rows(task: str, difficulty: str, records: list[dict[str, Any]], sampling: dict[str, Any], contract: Contract) -> list[tuple[str, str, str]]:
    """代码侧只产出 ``(key, label, 结果分布)``；离散量「合法取值域顺序」从契约取，几何（锚点）从 sampling 取。"""
    config = sampling["parameters"][task]["configs"][difficulty]
    gc = contract.group(task, difficulty)
    if task == "BinFill":
        return binfill_rows(records, config, gc)
    if task == "RouteStick":
        return routestick_rows(records, config, gc)
    if task == "VideoUnmaskSwap":
        return unmask_rows(records, config, sampling["positions"][task]["containers"], gc)
    return repick_rows(records, config, sampling["positions"][task]["easy_medium_cubes"], gc)


def render_group_table(task: str, difficulty: str, records: list[dict[str, Any]], sampling: dict[str, Any], contract: Contract) -> tuple[str, int]:
    """行序、节归属、「取值域」「分配」两列取自契约；「结果分布」列由本文件从规格算出。契约与代码的 key 集合必须一致。"""
    gc = contract.group(task, difficulty)
    computed = {key: (label, result) for key, label, result in group_rows(task, difficulty, records, sampling, contract)}
    contract_rows = gc.rows()
    if set(computed) != {key for _s, key, *_ in contract_rows}:
        raise ContractError(f"{task}/{difficulty}: 契约字段 {sorted(k for _s, k, *_ in contract_rows)} 与代码产出 {sorted(computed)} 不一致")
    for _section, key, label, _d, _a in contract_rows:
        if computed[key][0] != label:
            raise ContractError(f"{task}/{difficulty}/{key}: 契约 label {label!r} 与代码 {computed[key][0]!r} 不一致")
    lines = [f"### {task} / {difficulty}（{len(records)} 条）", ""]
    if task == "VideoRepick":
        lines += ["> 注：VideoRepick 的三块方块在规格里 `object_id` 是 `bin_0/1/2`（沿用源码命名），下表照此写。", ""]
    for section, note in (("初始化", "场景开局是什么样：物体种类、数量、位姿、藏物关系"), ("事件", "任务要做什么：投入／抓取／路线／交换的选择")):
        lines += [f"#### {section}（{note}）", "", "| 事件 | 取值域 | 分配 | 结果分布 |", "|---|---|---|---|"]
        lines += [f"| {label} | {domain_text} | {allocation_text} | {computed[key][1]} |"
                  for sec, key, label, domain_text, allocation_text in contract_rows if sec == section]
        lines.append("")
    return "\n".join(lines).rstrip("\n"), len(contract_rows)


def render_all(root: Path, sampling: dict[str, Any], contract: Contract) -> tuple[str, int]:
    blocks, total = [], 0
    for task, difficulty in GROUPS:
        text, n = render_group_table(task, difficulty, load_group(root, task, difficulty), sampling, contract)
        blocks.append(text)
        total += n
    return "\n" + "\n\n".join(blocks) + "\n", total


def split_region(text: str) -> tuple[str, str, str]:
    """返回 (标记前, 区间内, 标记后)；找不到标记则抛 ValueError。"""
    start = text.find(BEGIN)
    end = text.find(END)
    if start < 0 or end < 0 or end < start:
        raise ValueError(f"文档缺少 {BEGIN} / {END} 标记")
    head = text[: start + len(BEGIN)]
    tail = text[end:]
    return head, text[start + len(BEGIN): end], tail


def load_contract_for(root: Path, override: str | None = None) -> Contract:
    """契约以该运行 manifest.json 的 contract_path / contract_sha256 为准；清单没记（历史运行）时必须显式 --contract。"""
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
    recorded = manifest.get("contract_path")
    if override is None and recorded is None:
        raise ContractError(f"{root.name} 的清单没有记录契约，请用 --contract 显式指定")
    contract = load_contract(Path(override) if override else REPO_ROOT / recorded)
    expected = manifest.get("contract_sha256")
    if expected is not None and contract.sha256 != expected:
        raise ContractError(f"契约散列 {contract.sha256[:12]}… 与清单冻结时的 {expected[:12]}… 不符")
    return contract


def check(run_id: str = DEFAULT_RUN_ID, artifacts_root: Path | None = None, contract_path: str | None = None) -> tuple[bool, int, int]:
    """重新生成并与文档比对，返回 (是否一致, 事件行数, 漂移行数)。"""
    root = (artifacts_root or REPO_ROOT / "artifacts" / "injection") / run_id
    sampling = load_sampling(root)
    contract = load_contract_for(root, contract_path)
    block, rows = render_all(root, sampling, contract)
    try:
        _, current, _ = split_region(DOC.read_text(encoding="utf-8"))
    except (ValueError, FileNotFoundError):
        return False, rows, -1
    diff = [line for line in difflib.ndiff(current.splitlines(), block.splitlines()) if line[:1] in "+-"]
    return not diff, rows, len(diff)


def main() -> int:
    parser = argparse.ArgumentParser(description="从冻结规格统计结果分布并生成事件表（只读规格 JSON 与契约）")
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--artifacts-root", default=str(REPO_ROOT / "artifacts" / "injection"))
    parser.add_argument("--contract", default=None, help="默认按该运行 manifest.json 的 contract_path；清单没记时必须给")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true", help="把表写入文档标记区间")
    mode.add_argument("--check", action="store_true", help="只比对不写（默认）")
    mode.add_argument("--print", action="store_true", help="只打印生成的表")
    args = parser.parse_args()

    root = Path(args.artifacts_root) / args.run_id
    sampling = load_sampling(root)
    contract = load_contract_for(root, args.contract)
    block, rows = render_all(root, sampling, contract)
    if args.print:
        print(block)
        return 0
    if args.write:
        head, _, tail = split_region(DOC.read_text(encoding="utf-8"))
        DOC.write_text(head + block + tail, encoding="utf-8")
        print(f"EVENT_TABLES=WRITTEN groups={len(GROUPS)} rows={rows}")
        return 0
    ok, rows, drift = check(args.run_id, Path(args.artifacts_root), args.contract)
    if not ok:
        _, current, _ = split_region(DOC.read_text(encoding="utf-8"))
        for line in [l for l in difflib.ndiff(current.splitlines(), block.splitlines()) if l[:1] in "+-"][:5]:
            print(f"  漂移：{line[:160]}", file=sys.stderr)
    print(f"EVENT_TABLES={'PASS' if ok else 'FAIL'} groups={len(GROUPS)} rows={rows} drift={drift}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
