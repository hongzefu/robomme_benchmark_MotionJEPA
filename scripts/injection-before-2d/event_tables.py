"""从冻结规格统计「结果分布」，生成 11 组「事件 / 取值域 / 分配 / 结果分布」四列表（每组分「初始化」「事件」两张）。

* 只读 ``artifacts/injection/<run-id>/specs/<任务>/<难度>.json`` 与 ``scripts/configs/newtask-v2/native_sampling.json``，
  只依赖标准库，不 import matplotlib，也不 import ``tests._shared``（与出图脚本同样是独立只读工具；
  视频任务反算偏移量需要的 ``rotate`` 在本文件自写，刻意不从出图脚本 import，免得把 matplotlib 拖进校验路径）。
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
SAMPLING_CONFIG = REPO_ROOT / "scripts" / "configs" / "newtask-v2" / "native_sampling.json"
DOC = HERE / "NEW_VALUE_DISTRIBUTION_BEFORE.md"
DEFAULT_RUN_ID = "20260910-new-values-04"
BEGIN = "<!-- AUTO:EVENT_TABLES BEGIN -->"
END = "<!-- AUTO:EVENT_TABLES END -->"

GROUPS: list[tuple[str, str]] = [
    ("BinFill", "easy"), ("BinFill", "medium"), ("BinFill", "hard"),
    ("RouteStick", "easy"), ("RouteStick", "medium"), ("RouteStick", "hard"),
    ("VideoUnmaskSwap", "easy"), ("VideoUnmaskSwap", "medium"), ("VideoUnmaskSwap", "hard"),
    ("VideoRepick", "easy"), ("VideoRepick", "medium"),
]
COARSE_BINS = 10
MAX_KEYS = 12  # 频数键超过这个数只列前几个，避免把表撑爆

# 几何常量与颜色定义（与 tests/_shared/injection_specs.py 一致，照抄数值不 import）
CUBE_HALF = 0.02
BIN_HALF = (CUBE_HALF * 2.5 + 0.005) * 0.5  # 0.0275
SPAWN_COLOR_ORDER = ("red", "blue", "green")
INITIALIZE_COLOR_DEFS = ("blue", "red", "green")
UNMASK_COLOR_ORDER = ("red", "green", "blue")
REPICK_COLOR_ORDER = ("red", "blue", "green")
ROUTE_EDGES = ["0→2", "2→0", "2→4", "4→2", "4→6", "6→4", "6→8", "8→6"]  # 线性邻接 ±1 的 8 条有向边


# ── 通用 ────────────────────────────────────────────────────────────────────
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


def closed_range(lo_hi: list[int]) -> list[str]:
    return [str(v) for v in range(int(lo_hi[0]), int(lo_hi[1]) + 1)]


def range_text(lo, hi) -> str:
    return str(lo) if lo == hi else f"{lo}～{hi}"


def color_sorted(colors: Iterable[str], order: tuple[str, ...]) -> list[str]:
    return sorted(colors, key=order.index)


# ── BinFill ────────────────────────────────────────────────────────────────
def binfill_rows(records: list[dict[str, Any]], config: dict[str, Any]) -> list[tuple[str, str, str, str]]:
    n_color = int(config["color"])
    spawn_lo, spawn_hi = config["spawn_cubes"]
    put_lo, put_hi = config["put_in_numbers"]
    put_color_legal = sorted({min(max(int(v), 1), max(1, n_color)) for v in range(int(config["put_in_color"][0]), int(config["put_in_color"][1]) + 1)})
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
    color_cn = {1: "1 种", 2: "2 种", 3: "3 种"}[n_color]
    return [
        ("`dynamic`（方块分批出现还是开局全在）", "True / False", "配额 50/50",
         count_cell(Counter(str(r["layout"]["dynamic"]) for r in records), ["True", "False"])),
        ("`colors_present`（场上有哪些颜色）", f"红蓝绿里取 {color_cn}", "配额", count_cell(colors_obs, colors_legal)),
        ("`put_in_color` 目标色种数", "/".join(str(k) for k in put_color_legal), "配额",
         count_cell(Counter(str(len(r["objects"]["target_pool"])) for r in records), [str(k) for k in put_color_legal])),
        ("`target_pool`（要投入的颜色子集）", "场上颜色的子集", "合法候选内平衡", freq_cell(pool_obs, pool_universe)),
        ("`spawn_total`（生成几块）", f"{spawn_lo}～{spawn_hi}", "配额", count_cell(Counter(str(r["objects"]["spawn_total"]) for r in records), closed_range(config["spawn_cubes"]))),
        ("`put_in_total`（投入几块）", f"{put_lo}～{put_hi}", "配额", count_cell(Counter(str(r["objects"]["put_in_total"]) for r in records), closed_range(config["put_in_numbers"]))),
        ("`initialize_color_order`（颜色创建顺序）", "蓝红绿 6 种排列", "配额",
         count_cell(Counter("-".join(r["objects"]["initialize_color_order"]) for r in records), order_legal)),
        ("`target_count[颜色]`（每色投几块）", "投入数逐个随机分给目标色，允许 0", "`rng_ep` 逐条随机（耦合）", freq_cell(target_items, unit="个颜色项")),
        ("`spawn_count[颜色]`（每色生成几块）", "每色至少 max(目标,1)，余量随机摊", "`rng_ep` 逐条随机（耦合）", freq_cell(spawn_items, unit="个颜色项")),
        ("方块生成顺序", "(颜色, 序号) 的随机排列", "`rng_ep.permutation`", "生成序首块的颜色 " + count_cell(first_color, list(SPAWN_COLOR_ORDER))),
        ("`button_xy`（按钮中心）", "x∈[-0.25,-0.15] y∈[-0.2,0.2]", "分层",
         "；".join([cont_seg("x", records, "button_x", [r["layout"]["button_xy"][0] for r in records], 4),
                    cont_seg("y", records, "button_y", [r["layout"]["button_xy"][1] for r in records], 4)])),
        ("`board.xy`、`board.yaw_deg`（孔板）", "x∈[-0.05,0.15] y∈[-0.2,0.2]，yaw∈[-20°,20°]", "分层",
         "；".join([cont_seg("x", records, "board_x", [r["layout"]["board"]["xy"][0] for r in records], 4),
                    cont_seg("y", records, "board_y", [r["layout"]["board"]["xy"][1] for r in records], 4),
                    cont_seg("yaw", records, "board_yaw", [r["layout"]["board"]["yaw_deg"] for r in records], 2)])),
        ("`cubes[i].xy`、`yaw_rad`（每块方块）", "x∈[-0.28,0.08] y∈[-0.23,0.23]，yaw 0～2π",
         "第 0 块首次尝试分层；其余块粗箱轮转；被拒整域重抽",
         "采样输入 cube_x " + bins_text(r["sampling_cells"]["cube_x"][0] for r in records)
         + "、cube_y " + bins_text(r["sampling_cells"]["cube_y"][0] for r in records)
         + "、cube_yaw " + bins_text(r["sampling_cells"]["cube_yaw"][0] for r in records)
         + f"；实际位置 x {actual_bins_text(cx, -0.28, 0.08)}，实测 {rng_text(cx, 4)}"
         + f"；y {actual_bins_text(cy, -0.23, 0.23)}，实测 {rng_text(cy, 4)}"
         + f"；yaw 实测 {rng_text(cyaw, 2)}{unit_suffix(len(cubes), '块')}"),
        ("`actions`（抓哪块）", "按颜色创建顺序遍历，每色取生成列表最前 `target_count` 块", "推出",
         "推出：被抓方块的色内序号 " + count_cell(pick_index, pick_legal, "个动作")),
    ]


# ── RouteStick ─────────────────────────────────────────────────────────────
def routestick_points(rotation_deg: float) -> list[tuple[float, float]]:
    return [rotate((-0.1, (col - 4) * 0.07), math.radians(rotation_deg)) for col in range(9)]


def routestick_rows(records: list[dict[str, Any]], config: dict[str, Any]) -> list[tuple[str, str, str, str]]:
    lo, hi = config["length"]
    edges = Counter(f"{r['actions']['nodes'][i]}→{r['actions']['nodes'][i + 1]}" for r in records for i in range(len(r["actions"]["nodes"]) - 1))
    directions = Counter(d for r in records for d in r["actions"]["directions"])
    rgb = [v for r in records for stick in r["layout"]["obstacle_rgb"] for v in stick]
    points = [p for r in records for p in routestick_points(r["layout"]["rotation_deg"])]
    px, py = [p[0] for p in points], [p[1] for p in points]
    backtrack = "允许回退" if config["backtrack"] else "不许回退：剔除上一步，端点被迫掉头"
    return [
        ("`L`（走几段）", f"{lo}～{hi}", "配额", count_cell(Counter(str(r["objects"]["L"]) for r in records), closed_range(config["length"]))),
        ("起点 `nodes[0]`", "0/2/4/6/8", "配额各 20", count_cell(Counter(str(r["actions"]["nodes"][0]) for r in records), ["0", "2", "4", "6", "8"])),
        ("`rotation_deg`（整排绕世界原点转）", "[-30°, 30°]", "分层",
         cont_seg("", records, "rotation_deg", [r["layout"]["rotation_deg"] for r in records], 2).strip()),
        ("每段去哪（有向边）", f"线性邻接 ±1；{backtrack}", "合法候选内平衡", freq_cell(edges, ROUTE_EDGES, "段")),
        ("每段绕行方向 `directions`", "clockwise / counterclockwise", "合法候选内平衡", count_cell(directions, ["clockwise", "counterclockwise"], "段")),
        ("`obstacle_rgb[4]`（4 根障碍柱颜色）", "每根一个随机 RGB，各通道 [0,1)", "`rng_ep` 随机（只影响观感）",
         f"通道值 {actual_bins_text(rgb, 0.0, 1.0)}，实测 {rng_text(rgb, 3)}{unit_suffix(len(rgb), '个通道值')}"),
        ("9 个格点位置", "由 `rotation_deg` 唯一确定", "推出", f"推出：{len(points)} 个格点 x 实测 {rng_text(px, 4)}，y 实测 {rng_text(py, 4)}"),
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


def swap_rows(records: list[dict[str, Any]], names: list[str]) -> tuple[str, str, str, str]:
    pairs = Counter(f"{p['initiator']}→{p['partner']}" for r in records for p in r["actions"]["swap_pairs"])
    universe = [f"{a}→{b}" for a in names for b in names if a != b]
    return ("`swap_pairs[k].partner`（交换搭档）", "交换开始时的水平最近邻，等距取序号小者", "推出（执行时核验，不符即失败）",
            freq_cell(pairs, universe, "次交换", derived=True))


def candidates_row(records: list[dict[str, Any]]) -> tuple[str, str, str, str]:
    used = Counter(str(r["collision"]["candidates_used"]) for r in records)
    legal = [str(k) for k in sorted(int(k) for k in used)]
    return ("`collision.candidates_used`（冻结用了第几个候选）", "1～256", "几何／碰撞被拒后重抽的落地结果", count_cell(used, legal))


def unmask_rows(records: list[dict[str, Any]], config: dict[str, Any], anchors_cfg: dict[str, Any]) -> list[tuple[str, str, str, str]]:
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
        ("`n_swaps`（交换几次）", range_text(config["swap_min"], config["swap_max"]), "配额",
         count_cell(Counter(str(r["objects"]["n_swaps"]) for r in records), closed_range([config["swap_min"], config["swap_max"]]))),
        ("`n_picks`（视频后抓几个）", range_text(config["pick_min"], config["pick_max"]), "配额",
         count_cell(Counter(str(r["objects"]["n_picks"]) for r in records), closed_range([config["pick_min"], config["pick_max"]]))),
        ("`layout_type`（锚点布局）", "三角／直线" if n_bins == 3 else "四点（固定）", "配额" if n_bins == 3 else "常量",
         count_cell(Counter(r["layout"]["type"] for r in records), layout_legal)),
        ("`selected`（藏物容器排序）", "前三个容器的 6 种排列", "配额",
         count_cell(Counter("-".join(str(v) for v in r["objects"]["selected"]) for r in records), selected_legal)),
        ("`color_order`（藏物颜色顺序）", "红绿蓝 6 种排列", "配额",
         count_cell(Counter("-".join(r["objects"]["color_order"]) for r in records), color_legal)),
        ("前两个发起者 `swap_initiators[:2]`", "3 取 2 的 6 种有序对（原代码把藏物序号当生成序号用，照抄）", "配额",
         count_cell(Counter("-".join(r["objects"]["swap_initiators"][:2]) for r in records), first_two_legal)),
        ("第三个发起者 `swap_initiators[2]`", "其余生成序号", "合法候选内平衡",
         freq_cell(Counter(r["objects"]["swap_initiators"][2] for r in records), names)),
        ("`theta_rad`（整组绕原点转）", "[0, 180] 弧度（原单位就是弧度，不是度）", "分层；被拒同粗箱重抽",
         cont_seg("", records, "theta_rad", [r["layout"]["theta_rad"] for r in records], 2).strip()),
        ("`bins[i].xy`、`yaw_deg`（每个容器）", f"锚点旋转后各偏移 ≤ {0.07 - BIN_HALF:.4f}，yaw 0～90°", "分层；被拒同粗箱重抽",
         offset_segments(records, anchors_cfg, "bins", "bin", "yaw_deg", 2)),
        ("`hidden`（颜色→容器）", "由 `selected` + `color_order` 算出", "推出", freq_cell(hidden, hidden_universe, "项", derived=True)),
        ("`empty`（空容器）", "不在 `selected` 里的容器", "推出", freq_cell(empty, derived=True)),
        ("`pick_order`（视频后抓取顺序）", "`selected` 的前 `n_picks` 个", "推出", freq_cell(picks, derived=True)),
        swap_rows(records, names),
        candidates_row(records),
    ]


def repick_rows(records: list[dict[str, Any]], config: dict[str, Any], anchors_cfg: dict[str, Any]) -> list[tuple[str, str, str, str]]:
    names = ["bin_0", "bin_1", "bin_2"]
    tail_legal = [f"{a}-{b}" for a, b in itertools.permutations(names, 2)]
    return [
        ("`n_swaps`（交换几次）", range_text(config["swap_min"], config["swap_max"]), "配额",
         count_cell(Counter(str(r["objects"]["n_swaps"]) for r in records), closed_range([config["swap_min"], config["swap_max"]]))),
        ("`num_repeats`（重复抓放次数）", "1～3", "配额", count_cell(Counter(str(r["objects"]["num_repeats"]) for r in records), ["1", "2", "3"])),
        ("`layout_type`（锚点布局）", "三角／直线", "配额", count_cell(Counter(r["layout"]["type"] for r in records), ["region3_tri", "region3_line"])),
        ("`color`（三块统一颜色）", "红／蓝／绿", "配额", count_cell(Counter(r["objects"]["color"] for r in records), list(REPICK_COLOR_ORDER))),
        ("`target`（目标方块）", "三块之一", "配额", count_cell(Counter(r["objects"]["target"] for r in records), names)),
        ("后续发起者顺序 `tail`", "另外两块的 2 种排列", "配额", count_cell(Counter("-".join(r["objects"]["swap_initiators"][1:]) for r in records), tail_legal)),
        ("`theta_rad`、`button_xy`", "[0, 180] 弧度；x∈[-0.25,-0.15] y∈[-0.05,0.05]", "分层（θ 被拒同粗箱重抽，按钮不参与重抽）",
         "；".join([cont_seg("θ", records, "theta_rad", [r["layout"]["theta_rad"] for r in records], 2),
                    cont_seg("按钮 x", records, "button_x", [r["layout"]["button_xy"][0] for r in records], 4),
                    cont_seg("按钮 y", records, "button_y", [r["layout"]["button_xy"][1] for r in records], 4)])),
        ("`cubes[i].xy`、`yaw_rad`（每块方块）", f"锚点旋转后各偏移 ≤ {0.07 - CUBE_HALF:.4f}，yaw 0～2π",
         "分层；方块间距 < 0.02、压按钮或碰撞被拒后同粗箱重抽",
         offset_segments(records, anchors_cfg, "cubes", "cube", "yaw_rad", 2)),
        swap_rows(records, names),
        candidates_row(records),
    ]


# ── 每行归「初始化」还是「事件」（用户要求表格分两部分）────────────────────────
INIT, EVT = "初始化", "事件"
SECTION_OF = {
    # BinFill：场景里有什么、摆在哪 = 初始化；要投哪些、投几块、抓哪块 = 事件
    "`dynamic`（方块分批出现还是开局全在）": INIT, "`colors_present`（场上有哪些颜色）": INIT, "`spawn_total`（生成几块）": INIT,
    "`initialize_color_order`（颜色创建顺序）": INIT, "`spawn_count[颜色]`（每色生成几块）": INIT, "方块生成顺序": INIT,
    "`button_xy`（按钮中心）": INIT, "`board.xy`、`board.yaw_deg`（孔板）": INIT, "`cubes[i].xy`、`yaw_rad`（每块方块）": INIT,
    "`put_in_color` 目标色种数": EVT, "`target_pool`（要投入的颜色子集）": EVT, "`put_in_total`（投入几块）": EVT,
    "`target_count[颜色]`（每色投几块）": EVT, "`actions`（抓哪块）": EVT,
    # RouteStick：整排位置与柱子颜色 = 初始化；走几段、从哪起、每段去哪怎么绕 = 事件
    "`rotation_deg`（整排绕世界原点转）": INIT, "`obstacle_rgb[4]`（4 根障碍柱颜色）": INIT, "9 个格点位置": INIT,
    "`L`（走几段）": EVT, "起点 `nodes[0]`": EVT, "每段去哪（有向边）": EVT, "每段绕行方向 `directions`": EVT,
    # VideoUnmaskSwap：布局、藏物、位姿、冻结候选 = 初始化；交换几次、谁发起、抓几个 = 事件
    "`layout_type`（锚点布局）": INIT, "`selected`（藏物容器排序）": INIT, "`color_order`（藏物颜色顺序）": INIT,
    "`theta_rad`（整组绕原点转）": INIT, "`bins[i].xy`、`yaw_deg`（每个容器）": INIT, "`hidden`（颜色→容器）": INIT,
    "`empty`（空容器）": INIT, "`collision.candidates_used`（冻结用了第几个候选）": INIT,
    "`n_swaps`（交换几次）": EVT, "`n_picks`（视频后抓几个）": EVT, "前两个发起者 `swap_initiators[:2]`": EVT,
    "第三个发起者 `swap_initiators[2]`": EVT, "`pick_order`（视频后抓取顺序）": EVT, "`swap_pairs[k].partner`（交换搭档）": EVT,
    # VideoRepick：布局、颜色、位姿 = 初始化；交换、重复、目标、发起顺序 = 事件
    "`color`（三块统一颜色）": INIT, "`theta_rad`、`button_xy`": INIT, "`cubes[i].xy`、`yaw_rad`（每块方块）": INIT,
    "`num_repeats`（重复抓放次数）": EVT, "`target`（目标方块）": EVT, "后续发起者顺序 `tail`": EVT,
}


# ── 渲染 ────────────────────────────────────────────────────────────────────
def group_rows(task: str, difficulty: str, records: list[dict[str, Any]], sampling: dict[str, Any]) -> list[tuple[str, str, str, str]]:
    config = sampling["parameters"][task]["configs"][difficulty]
    if task == "BinFill":
        return binfill_rows(records, config)
    if task == "RouteStick":
        return routestick_rows(records, config)
    if task == "VideoUnmaskSwap":
        return unmask_rows(records, config, sampling["positions"][task]["containers"])
    return repick_rows(records, config, sampling["positions"][task]["easy_medium_cubes"])


def render_group_table(task: str, difficulty: str, records: list[dict[str, Any]], sampling: dict[str, Any]) -> tuple[str, int]:
    rows = group_rows(task, difficulty, records, sampling)
    lines = [f"### {task} / {difficulty}（{len(records)} 条）", ""]
    if task == "VideoRepick":
        lines += ["> 注：VideoRepick 的三块方块在规格里 `object_id` 是 `bin_0/1/2`（沿用源码命名），下表照此写。", ""]
    unknown = [a for a, *_ in rows if a not in SECTION_OF]
    if unknown:
        raise KeyError(f"事件行未归类到初始化/事件：{unknown}")
    for section, note in ((INIT, "场景开局是什么样：物体种类、数量、位姿、藏物关系"), (EVT, "任务要做什么：投入／抓取／路线／交换的选择")):
        lines += [f"#### {section}（{note}）", "", "| 事件 | 取值域 | 分配 | 结果分布 |", "|---|---|---|---|"]
        lines += [f"| {a} | {b} | {c} | {d} |" for a, b, c, d in rows if SECTION_OF[a] == section]
        lines.append("")
    return "\n".join(lines).rstrip("\n"), len(rows)


def render_all(root: Path, sampling: dict[str, Any]) -> tuple[str, int]:
    blocks, total = [], 0
    for task, difficulty in GROUPS:
        text, n = render_group_table(task, difficulty, load_group(root, task, difficulty), sampling)
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


def check(run_id: str = DEFAULT_RUN_ID, artifacts_root: Path | None = None) -> tuple[bool, int, int]:
    """重新生成并与文档比对，返回 (是否一致, 事件行数, 漂移行数)。"""
    root = (artifacts_root or REPO_ROOT / "artifacts" / "injection") / run_id
    sampling = json.loads(SAMPLING_CONFIG.read_text(encoding="utf-8"))
    block, rows = render_all(root, sampling)
    try:
        _, current, _ = split_region(DOC.read_text(encoding="utf-8"))
    except (ValueError, FileNotFoundError):
        return False, rows, -1
    diff = [line for line in difflib.ndiff(current.splitlines(), block.splitlines()) if line[:1] in "+-"]
    return not diff, rows, len(diff)


def main() -> int:
    parser = argparse.ArgumentParser(description="从冻结规格统计结果分布并生成事件表（只读规格 JSON）")
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--artifacts-root", default=str(REPO_ROOT / "artifacts" / "injection"))
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true", help="把表写入文档标记区间")
    mode.add_argument("--check", action="store_true", help="只比对不写（默认）")
    mode.add_argument("--print", action="store_true", help="只打印生成的表")
    args = parser.parse_args()

    root = Path(args.artifacts_root) / args.run_id
    sampling = json.loads(SAMPLING_CONFIG.read_text(encoding="utf-8"))
    block, rows = render_all(root, sampling)
    if args.print:
        print(block)
        return 0
    if args.write:
        head, _, tail = split_region(DOC.read_text(encoding="utf-8"))
        DOC.write_text(head + block + tail, encoding="utf-8")
        print(f"EVENT_TABLES=WRITTEN groups={len(GROUPS)} rows={rows}")
        return 0
    ok, rows, drift = check(args.run_id, Path(args.artifacts_root))
    if not ok:
        _, current, _ = split_region(DOC.read_text(encoding="utf-8"))
        for line in [l for l in difflib.ndiff(current.splitlines(), block.splitlines()) if l[:1] in "+-"][:5]:
            print(f"  漂移：{line[:160]}", file=sys.stderr)
    print(f"EVENT_TABLES={'PASS' if ok else 'FAIL'} groups={len(GROUPS)} rows={rows} drift={drift}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
