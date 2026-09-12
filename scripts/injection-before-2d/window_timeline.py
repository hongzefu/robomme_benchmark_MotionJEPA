"""采样窗口数轴的数据层（只读实跑 HDF5 与 ``episode_results.jsonl``，不 import matplotlib，不 import ``tests._shared``）。

两个子命令：

* ``extract``：从 ``artifacts/injection/<run-id>/feasibility/<档>/`` 逐条读成功 episode 的
  总帧数 T、demo 段长度（``info/is_video_demo`` 为 True 的前缀）与 subgoal 分段
  （``info/is_subgoal_boundary`` 为 True 的帧切开，标签取 ``info/simple_subgoal``），
  写成本目录 ``windows_timeline.json``（小文件，入库；clone 后不必重开 h5 就能核对）。
  **BinFill 的 demo 是「同一条重复两遍」**：前一遍记 demo、后一遍记 exec
  （2026-09-11 用户要求「binfill任务改为加入模拟的demo 即为把一个任务重复两遍」）。
  07 起生成器直出就是重复两遍的 h5（``demo == total/2``），本脚本只校验不再翻倍（``demo_source="recorded"``）；
  05/06 的旧数据没有 demo 前缀，仍在这一步用 ``simulate_binfill_demo`` 补出来（``demo_source="simulated"``）。
  另外 extract 末尾会做**慢条剔除**（见 ``apply_slow_exclusion``）：单段过长或 T 远超组中位的 episode 移出统计。
* ``tables``：按窗口公式算每条的窗口数与帧路步长，生成 ``SAMPLING_WINDOWS.md`` 的自动表
  （``--write`` 写入标记区间，``--check`` 只比对，供 ``check_doc_links.py`` 调用）。

窗口公式与上一会话的 artifact「采样窗口与 eval 成功率」逐字一致：窗口 ``[f, f+32]``（33 帧）、stride 16、
**不跨 demo／exec 段**（各自从段起点铺），每段窗口数 ``len(range(0, max(0, L-32), 16))``；
帧路 ``round(linspace(0, T-1, N))``，N=32 与 N=8 是帧预算，Δ = ``(T-1)/(N-1)``。
"""

from __future__ import annotations

import argparse
import difflib
import json
import math
import re
import statistics
import sys
from pathlib import Path
from typing import Any, Callable

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
DEFAULT_ROLLOUT_RUN_ID = "20260911-contract-v3-07"  # 07 一次实跑 14 组；逗号分隔可传多个运行，后者覆盖前者的同 key 行
TIMELINE_JSON = HERE / "windows_timeline.json"
DOC = HERE / "SAMPLING_WINDOWS.md"
BEGIN = "<!-- AUTO:WINDOW_TABLES BEGIN -->"
END = "<!-- AUTO:WINDOW_TABLES END -->"

# 14 组：本目录三个脚本的唯一组列表（event_tables／plot_injection_before_2d 从这里 import），
# 与 scripts/injection/specs.py::GROUPS_V3 逐项相同（tests/lightweight/test_window_timeline.py 断言）。
# 2026-09-11 加 xhard 三组；旧 11 组的轨迹来自 05 实跑，xhard 来自 06（--rollout-run-id 可给多个运行，后者覆盖前者）。
GROUPS: list[tuple[str, str]] = [
    ("BinFill", "easy"), ("BinFill", "medium"), ("BinFill", "hard"),
    ("RouteStick", "easy"), ("RouteStick", "medium"), ("RouteStick", "hard"), ("RouteStick", "xhard"),
    ("VideoUnmaskSwap", "easy"), ("VideoUnmaskSwap", "medium"), ("VideoUnmaskSwap", "hard"), ("VideoUnmaskSwap", "xhard"),
    ("VideoRepick", "easy"), ("VideoRepick", "medium"), ("VideoRepick", "xhard"),
]  # 按任务分组、每任务 easy→medium→hard→xhard（2026-09-11 用户要求总览按 task 排列）
WIN, STRIDE, BUDGETS = 33, 16, (32, 8)
BANDS = ("最短", "中位", "最长")
SIMULATED_DEMO_TASKS = ("BinFill",)
# swap 事件（2026-09-11 用户要求「videounmaskswap和videorepick的swap事件能标出来吗」）
SWAP_TASKS = ("VideoUnmaskSwap", "VideoRepick")
SWAP_START, SWAP_LEN = 64, 50           # VideoUnmaskSwap._refresh_swap_schedule：第 k 次 swap = [64+50(k-1), 64+50k]
STATIC_HOLD, STATIC_THRESHOLD = 20, 0.01  # VideoRepick 热身段 static_check(20)；is_static 阈值 0.2 rad/s × 控制周期 0.05 s
B1_MINUS_S_RANGE = (5, 30)               # 关节法 S 与第一个 swap-static 段起始的合理差（实测 12～17）
FREEZE_THRESHOLD = 100.0                 # VideoRepick 最后一次 swap 结束后画面冻结、帧差严格为 0；100 以下视为渲染噪声
# 慢条剔除（2026-09-12）：卡在单个 subgoal 上磨的 episode 不进统计与代表条
MAX_SEGMENT_FRAMES = 400                 # 单个 subgoal 段超过这么多帧即判「磨」
SLOW_T_MEDIAN_FACTOR = 2.0               # 有效 T 超过「组中位 × 该倍数」即判慢


# ── 窗口公式（纯函数）─────────────────────────────────────────────────────────
def window_starts(length: int) -> list[int]:
    """一段 length 帧里能铺的窗口起点：``range(0, max(0, L-32), 16)``，与 artifact 的 ``winStarts`` 同。"""
    return list(range(0, max(0, length - (WIN - 1)), STRIDE))


def frame_path(total: int, n: int) -> list[int]:
    """帧路 ``round(linspace(0, T-1, N))``；用 floor(x+0.5) 而不是 Python 的银行家舍入，与 JS ``Math.round`` 一致。"""
    t = total - 1
    return [math.floor(i * t / (n - 1) + 0.5) for i in range(n)]


def deltas(total: int) -> tuple[float, ...]:
    """两条帧路的步长 Δ = (T-1)/(N-1)。"""
    return tuple((total - 1) / (n - 1) for n in BUDGETS)


def phase_segments(row: dict[str, Any]) -> list[tuple[int, int, str]]:
    """不跨段：demo 与 exec 各自从段起点铺；没有 demo 时整条是一个 exec 段。"""
    if row["demo"]:
        return [(0, row["demo"], "demo"), (row["demo"], row["total"] - row["demo"], "exec")]
    return [(0, row["total"], "exec")]


def window_counts(row: dict[str, Any]) -> tuple[int, int]:
    """(demo 段窗口数, exec 段窗口数)。"""
    counts = {"demo": 0, "exec": 0}
    for _start, length, kind in phase_segments(row):
        counts[kind] = len(window_starts(length))
    return counts["demo"], counts["exec"]


def simulate_binfill_demo(row: dict[str, Any]) -> dict[str, Any]:
    """同一条重复两遍：前一遍当 demo、后一遍当 exec；分段序列复制一份整体右移 T。"""
    total = int(row["total"])
    return {
        **row,
        "total": 2 * total,
        "demo": total,
        "original_total": total,
        "simulated_demo": True,
        "segs": [list(s) for s in row["segs"]] + [[int(s) + total, int(l), text] for s, l, text in row["segs"]],
    }


# ── 慢条剔除（单段过长 / T 远超组中位）──────────────────────────────────────
def effective_total(row: dict[str, Any]) -> int:
    """判定慢条用的「有效总帧数」：BinFill 的 T 是同一条重复两遍后的两倍，取 ``original_total``
    （即后一遍的真实长度）；其它任务直接用 ``total``。"""
    original = row.get("original_total")
    return int(original) if original is not None else int(row["total"])


def max_segment(row: dict[str, Any]) -> tuple[int, str]:
    """该行 segs 里最长的一段，返回 (帧数, 中文短标)；并列时取靠前的一段。没有 segs 时返回 (0, "—")。"""
    segs = row.get("segs") or []
    if not segs:
        return 0, "—"
    _start, length, text = max(segs, key=lambda s: int(s[1]))
    return int(length), short_label(str(text))[0]


def exclusion_reasons(row: dict[str, Any], group_median: float) -> list[str]:
    """该行命中的剔除原因文案列表（空列表 = 不剔除）。两条规则各自独立、可同时命中：
    ① 任一 subgoal 段超过 ``MAX_SEGMENT_FRAMES`` 帧；② 有效 T 超过 ``组中位 × SLOW_T_MEDIAN_FACTOR``。"""
    reasons: list[str] = []
    frames, _label = max_segment(row)
    if frames > MAX_SEGMENT_FRAMES:
        reasons.append(f"单段 {frames} 帧 > {MAX_SEGMENT_FRAMES}")
    total = effective_total(row)
    if total > group_median * SLOW_T_MEDIAN_FACTOR:
        reasons.append(f"T={total} > {SLOW_T_MEDIAN_FACTOR:g}×组中位 {_fmt(group_median)}")
    return reasons


def apply_slow_exclusion(groups: dict[str, list[dict[str, Any]]]) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    """把每组里的慢条移出来，返回 (剔除后的 groups, 剔除清单)。

    组中位按 ``effective_total`` 在**剔除前**算一次（``statistics.median``），一次性判定、不迭代——
    否则剔掉最慢的几条后中位会继续下移、把本来正常的条也带走。清单每项除了判定用的数字外还带整行
    （``row`` 键），出图脚本据此把被剔除的行灰化画出来。
    """
    kept: dict[str, list[dict[str, Any]]] = {}
    excluded: list[dict[str, Any]] = []
    for key, rows in groups.items():
        if not rows:
            kept[key] = list(rows)
            continue
        task, difficulty = key.split("/", 1)
        group_median = statistics.median([effective_total(r) for r in rows])
        keep_rows: list[dict[str, Any]] = []
        for row in rows:
            reasons = exclusion_reasons(row, group_median)
            if not reasons:
                keep_rows.append(row)
                continue
            frames, label = max_segment(row)
            excluded.append({
                "task": task, "difficulty": difficulty, "episode": row.get("episode"), "seed": row.get("seed"),
                "run_id": row.get("run_id"), "total": row.get("total"), "effective_total": effective_total(row),
                "group_median": group_median, "longest_segment_frames": frames, "longest_segment_label": label,
                "reasons": reasons, "h5_path": row.get("h5_path"), "row": row,
            })
        kept[key] = keep_rows
    return kept, excluded


def representatives(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """按 T 排序取最短／中位（下标 n//2）／最长三条，与 artifact 的三档同规则。"""
    ordered = sorted(rows, key=lambda r: (r["total"], r["episode"]))
    return {"最短": ordered[0], "中位": ordered[len(ordered) // 2], "最长": ordered[-1]}


# ── swap 事件 ─────────────────────────────────────────────────────────────────
def _pair_label(pair: dict[str, Any]) -> str:
    return f"{pair['initiator']}↔{pair['partner']}"


def unmask_swaps(n_swaps: int, pairs: list[dict[str, Any]]) -> list[list[Any]]:
    """VideoUnmaskSwap：调度常量，第 k 次 swap = [64 + 50(k-1), 64 + 50k]，之间无间隔。"""
    return [[SWAP_START + SWAP_LEN * k, SWAP_START + SWAP_LEN * (k + 1), _pair_label(pairs[k])] for k in range(n_swaps)]


def repick_swaps(start: int, n_swaps: int, pairs: list[dict[str, Any]]) -> list[list[Any]]:
    """VideoRepick：从闩锁的 start 起每 50 帧一次，首尾相接。"""
    return [[start + SWAP_LEN * k, start + SWAP_LEN * (k + 1), _pair_label(pairs[k])] for k in range(n_swaps)]


def load_specs(run_id: str, task: str, difficulty: str) -> dict[int, dict[str, Any]]:
    """从该运行的冻结规格读每条的 n_swaps 与 swap_pairs（只取 initiator/partner）。"""
    path = REPO_ROOT / "artifacts" / "injection" / run_id / "specs" / task / f"{difficulty}.json"
    out = {}
    for item in json.loads(path.read_text(encoding="utf-8"))["episodes"]:
        pairs = [{"initiator": p["initiator"], "partner": p["partner"]} for p in item["actions"]["swap_pairs"]]
        n_swaps = int(item["objects"]["n_swaps"])
        if n_swaps != len(pairs):
            raise ValueError(f"{path} ep{item['episode']}: n_swaps={n_swaps} 与 swap_pairs 数 {len(pairs)} 不一致")
        out[int(item["episode"])] = {"n_swaps": n_swaps, "pairs": pairs}
    return out


def first_swap_static(segs: list[list[Any]], demo: int) -> tuple[int | None, int | None]:
    """返回 (热身 static 段起始帧, 第一个 swap-static 段起始帧 B1)：demo 内第 1 个 static 是热身；B1 取其后第一个长度 48～60 的 static，
    没有则退到第 2 个 static。"""
    statics = [(int(s), int(l)) for s, l, text in segs if int(s) < demo and str(text).strip().lower() == "static"]
    if not statics:
        return None, None
    warm = statics[0][0]
    b1 = next((s for s, l in statics[1:] if 48 <= l <= 60), None)
    if b1 is None and len(statics) > 1:
        b1 = statics[1][0]
    return warm, b1


def static_start_from_deltas(deltas: list[float], first_index: int, hold: int = STATIC_HOLD, threshold: float = STATIC_THRESHOLD) -> int | None:
    """复现 static_check：deltas[i] 是帧 first_index+i 相对前一帧的最大关节位移；不静止即重新计数，
    连续 hold 帧静止（帧 t0..t0+hold-1）后返回 S = t0 + hold；找不到返回 None。"""
    run = 0
    for i, d in enumerate(deltas):
        run = run + 1 if d <= threshold else 0
        if run >= hold:
            return first_index + i + 1
    return None


def joint_static_start(h5_path: Path, warm_start: int, demo_end: int) -> int | None:
    """VideoRepick：从热身段起读 obs/joint_state[:7]，相邻帧差分近似 qvel，按 static_check(20) 反解 swap 起点 S。"""
    import h5py
    import numpy as np

    base = max(int(warm_start) - 1, 0)
    with h5py.File(h5_path, "r") as handle:
        group = handle[[name for name in handle if name.startswith("episode_")][0]]
        q = np.stack([np.asarray(group[f"timestep_{t}/obs/joint_state"][()])[:7] for t in range(base, demo_end)])
    deltas = np.abs(np.diff(q, axis=0)).max(axis=1).tolist()  # deltas[i] ↔ 帧 base+1+i
    return static_start_from_deltas(deltas, base + 1)


def frame_diffs(h5_path: Path, lo: int, hi: int) -> dict[int, float]:
    """diff[t] = Σ|front_rgb[t] − front_rgb[t−1]|，t ∈ [lo, hi]（lo ≥ 1）。只在机械臂已静止的区间内使用。"""
    import h5py
    import numpy as np

    lo = max(int(lo), 1)
    out: dict[int, float] = {}
    with h5py.File(h5_path, "r") as handle:
        group = handle[[name for name in handle if name.startswith("episode_")][0]]
        prev = np.asarray(group[f"timestep_{lo - 1}/obs/front_rgb"][()], dtype=np.int32)
        for t in range(lo, int(hi) + 1):
            cur = np.asarray(group[f"timestep_{t}/obs/front_rgb"][()], dtype=np.int32)
            out[t] = float(np.abs(cur - prev).sum())
            prev = cur
    return out


def solve_swap_end(diffs: dict[int, float], absolute: float | None = None) -> int | None:
    """区间内最后一个超阈值的帧。默认阈值 max(0.1×最大值, 500)（VideoUnmaskSwap：最后一次 swap 在 end_step 直接 set_pose
    并放回方块，是个 2.5 万级尖峰）；``absolute`` 给定时用绝对阈值（VideoRepick：末尾没有尖峰，smoothstep 收尾帧差只有
    两千级，但之后画面冻结、帧差严格为 0，所以取最后一个 > 100 的帧）。"""
    if not diffs:
        return None
    threshold = absolute if absolute is not None else max(0.1 * max(diffs.values()), 500.0)
    hits = [t for t, v in diffs.items() if v > threshold]
    return max(hits) if hits else None


def solve_swap_first_change(diffs: dict[int, float]) -> int | None:
    """区间内第一个超阈值的帧（VideoUnmaskSwap 用：帧 64 方块被藏起、交换开始）。"""
    if not diffs:
        return None
    threshold = max(0.1 * max(diffs.values()), 500.0)
    hits = [t for t, v in diffs.items() if v > threshold]
    return min(hits) if hits else None


def annotate_swaps(task: str, entry: dict[str, Any], spec: dict[str, Any], h5_path: Path) -> None:
    """给一条视频任务的 entry 加 swaps / swap_source / swap_check 等字段（就地修改）。"""
    n, pairs = spec["n_swaps"], spec["pairs"]
    demo, total = int(entry["demo"]), int(entry["total"])
    warm, b1 = first_swap_static(entry["segs"], demo)
    if task == "VideoUnmaskSwap":
        # 公式给区间；像素差只做校验：帧 40～63 静置、64 首次变化；n≥2 时最后一次结束帧 64+50n < demo，也校验
        swaps = unmask_swaps(n, pairs)
        expected_end = SWAP_START + SWAP_LEN * n
        diffs = frame_diffs(h5_path, 40, demo - 1)
        first_change = solve_swap_first_change(diffs)
        pixel_end = solve_swap_end(diffs) if expected_end < demo else None
        check = "PASS" if first_change == SWAP_START and (pixel_end is None or pixel_end == expected_end) else "FAIL"
        entry.update({"swaps": swaps, "swap_source": "schedule", "swap_pixel_first": first_change,
                      "swap_pixel_end": pixel_end, "swap_check": check})
        return
    # VideoRepick：关节静止法反解 S_joint，像素差在 [S_joint-5, demo-1] 内取画面冻结前的最后一帧 E，S_pix = E - 50n。
    # 关节差分在 0.01 rad 阈值边缘（0.0097～0.0102）会与仿真器内部 qvel 差一帧，而画面冻结没有歧义（之后帧差严格为 0），
    # 所以两者差 ≤ 1 帧时以像素为准并把两个值都记下来；差 > 1 帧才判 FAIL。05 实测：57 条里 49 条两法相等、8 条差 1 帧。
    s_joint = joint_static_start(h5_path, warm, demo) if warm is not None else None
    if s_joint is None:
        entry.update({"swaps": [], "swap_source": "joint_static", "swap_start": None, "swap_start_joint": None,
                      "swap_start_pixel": None, "swap_pixel_end": None, "b1_minus_s": None, "swap_check": "FAIL"})
        return
    diffs = frame_diffs(h5_path, s_joint - 5, demo - 1)
    pixel_end = solve_swap_end(diffs, absolute=FREEZE_THRESHOLD)
    s_pix = (pixel_end - SWAP_LEN * n) if pixel_end is not None else None
    if s_pix is not None and abs(s_pix - s_joint) <= 1:
        start, check = s_pix, "PASS"
    else:
        start, check = s_joint, "FAIL"
    b1_minus_s = (b1 - start) if b1 is not None else None
    if check == "PASS" and (b1_minus_s is None or not B1_MINUS_S_RANGE[0] <= b1_minus_s <= B1_MINUS_S_RANGE[1]):
        check = "WARN"
    entry.update({"swaps": repick_swaps(start, n, pairs), "swap_source": "joint_static", "swap_start": start,
                  "swap_start_joint": s_joint, "swap_start_pixel": s_pix, "swap_pixel_end": pixel_end,
                  "b1_minus_s": b1_minus_s, "swap_check": check})


# ── subgoal 短标（04 实跑 322 条只出现 31 种文本，规则表覆盖全部）─────────────────
_DIRS = {"left": "左", "right": "右"}
_ORDS = {"first": "1", "second": "2", "third": "3", "fourth": "4", "fifth": "5", "sixth": "6", "seventh": "7", "eighth": "8"}
_COLS = {"red": "红", "blue": "蓝", "green": "绿"}
_RULES: list[tuple[re.Pattern[str], Callable[[re.Match[str]], str]]] = [
    (re.compile(r"^move to the nearest (left|right) target by circling around the stick counterclockwise$", re.I), lambda m: "绕" + _DIRS[m[1].lower()] + "逆"),
    (re.compile(r"^move to the nearest (left|right) target by circling around the stick clockwise$", re.I), lambda m: "绕" + _DIRS[m[1].lower()] + "顺"),
    (re.compile(r"^pick up the (\w+) (red|blue|green) cube$", re.I), lambda m: "抓" + _COLS[m[2].lower()] + _ORDS.get(m[1].lower(), m[1])),
    (re.compile(r"^pick up the container that hides the (red|blue|green) cube$", re.I), lambda m: "抓" + _COLS[m[1].lower()] + "容"),
    (re.compile(r"^put down the container$", re.I), lambda m: "放容"),
    (re.compile(r"^put it into the bin$", re.I), lambda m: "投箱"),
    (re.compile(r"^pick up the correct cube for the (\w+) time$", re.I), lambda m: "抓对" + _ORDS.get(m[1].lower(), m[1])),
    (re.compile(r"^pick up the cube$", re.I), lambda m: "抓块"),
    (re.compile(r"^drop the cube on the table$", re.I), lambda m: "放桌"),
    (re.compile(r"^put it down$", re.I), lambda m: "放下"),
    (re.compile(r"^press the button to finish$", re.I), lambda m: "按钮停"),
    (re.compile(r"^press the button$", re.I), lambda m: "按钮"),
    (re.compile(r"^static$", re.I), lambda m: "静止"),
    (re.compile(r"^All tasks completed$", re.I), lambda m: "完成"),
]


def short_label(text: str) -> tuple[str, bool]:
    """返回 (短标, 是否命中规则)；没命中时兜底取前 6 个字符，调用方应把这类文本报出来。"""
    for pattern, render in _RULES:
        match = pattern.match(text.strip())
        if match:
            return render(match), True
    return text.strip()[:6], False


# ── 读 HDF5 ────────────────────────────────────────────────────────────────────
def _read_str(dataset) -> str:
    value = dataset.asstr()[()] if dataset.shape == () else dataset[()]
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    return str(value)


def read_episode(h5_path: Path) -> dict[str, Any]:
    """一条轨迹 → ``{"total", "demo", "segs": [[start, len, text], …]}``；demo 必须是从 0 起的连续前缀。"""
    import h5py  # 延迟 import：tables/check 路径不需要它

    with h5py.File(h5_path, "r") as handle:
        episodes = [name for name in handle if name.startswith("episode_")]
        if len(episodes) != 1:
            raise ValueError(f"{h5_path}: 期望恰好一个 episode 组，实际 {episodes}")
        group = handle[episodes[0]]
        steps = sorted((int(name.split("_", 1)[1]), name) for name in group if name.startswith("timestep_"))
        if [index for index, _ in steps] != list(range(len(steps))):
            raise ValueError(f"{h5_path}: timestep 不从 0 连续")
        demo_flags: list[bool] = []
        boundaries: list[tuple[int, str]] = []
        for index, name in steps:
            info = group[name]["info"]
            demo_flags.append(bool(info["is_video_demo"][()]))
            if bool(info["is_subgoal_boundary"][()]):
                boundaries.append((index, _read_str(info["simple_subgoal"])))
    total = len(steps)
    demo = sum(demo_flags)
    if not (all(demo_flags[:demo]) and not any(demo_flags[demo:])):
        raise ValueError(f"{h5_path}: is_video_demo 不是从 0 起的连续前缀")
    if not boundaries or boundaries[0][0] != 0:
        raise ValueError(f"{h5_path}: 第 0 帧不是 subgoal 边界")
    segs = []
    for k, (start, text) in enumerate(boundaries):
        end = boundaries[k + 1][0] if k + 1 < len(boundaries) else total
        segs.append([start, end - start, text])
    return {"total": total, "demo": demo, "segs": segs}


def rollout_dir(run_id: str, mode: str | None = None) -> Path:
    """``artifacts/injection/<run-id>/feasibility/`` 下唯一的档目录（04 是 P0x12、05 是 P01x20）；多于一个时必须 ``--mode``。"""
    root = REPO_ROOT / "artifacts" / "injection" / run_id / "feasibility"
    if not root.is_dir():
        raise FileNotFoundError(f"找不到实跑产物目录：{root}")
    modes = sorted(item.name for item in root.iterdir() if item.is_dir())
    if mode is None:
        if len(modes) != 1:
            raise ValueError(f"{root} 下有 {modes} 多个档，请用 --mode 指定")
        mode = modes[0]
    if mode not in modes:
        raise FileNotFoundError(f"{root} 下没有档 {mode}（有 {modes}）")
    return root / mode


def extract(run_ids: Sequence[str] | str, sources: Sequence[Path] | Path) -> dict[str, Any]:
    """读 jsonl（每个 (任务, 难度, episode) 只取最后一次 attempt）→ 成功条逐个开 h5 → BinFill 模拟 demo。

    可传多个运行（与 ``sources`` 一一对应，按序合并、后者覆盖前者的同 key 行）：05 出旧 11 组、06 只实跑 3 个 xhard 组，
    合并后 14 组落在同一份 JSON；每条行记 ``run_id``，规格按该行所属运行读。
    """
    if isinstance(run_ids, str):
        run_ids = [run_ids]
    if isinstance(sources, Path):
        sources = [sources]
    if len(run_ids) != len(sources):
        raise ValueError("run_ids 与 sources 数量不一致")
    latest: dict[tuple[str, str, int], dict[str, Any]] = {}
    for run_id, source in zip(run_ids, sources):
        for line in (source / "episode_results.jsonl").read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                row["run_id"] = run_id
                latest[(row["task"], row["difficulty"], int(row["episode"]))] = row
    groups: dict[str, list[dict[str, Any]]] = {f"{task}/{difficulty}": [] for task, difficulty in GROUPS}
    skipped: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    unknown_labels: dict[str, int] = {}
    specs: dict[tuple[str, str, str], dict[int, dict[str, Any]]] = {}
    group_sources: dict[str, str] = {}
    swap_summary = {"episodes": 0, "fail": 0, "warn": 0}
    for (task, difficulty, episode), row in sorted(latest.items()):
        key = f"{task}/{difficulty}"
        if key not in groups:
            continue
        if not row.get("ok"):
            failed.append({"task": task, "difficulty": difficulty, "episode": episode, "seed": row.get("seed"),
                           "error_type": row.get("error_type"), "failure_class": row.get("failure_class")})
            continue
        h5_path = Path(row["h5_path"])
        try:
            record = read_episode(h5_path)
        except (OSError, ValueError) as exc:
            skipped.append({"task": task, "difficulty": difficulty, "episode": episode, "seed": row.get("seed"),
                            "h5_path": str(h5_path), "reason": f"{type(exc).__name__}: {exc}"[:200]})
            continue
        if record["total"] != int(row["timestep_count"]):
            raise ValueError(f"{h5_path}: h5 帧数 {record['total']} 与 jsonl 的 timestep_count {row['timestep_count']} 不一致")
        for _s, _l, text in record["segs"]:
            _label, known = short_label(text)
            if not known:
                unknown_labels[text] = unknown_labels.get(text, 0) + 1
        run_id = row["run_id"]
        group_sources[key] = run_id
        entry = {"episode": episode, "seed": int(row["seed"]), "recovery_mode": row.get("recovery_mode"), "run_id": run_id,
                 "h5_path": str(h5_path), **record}
        if task in SWAP_TASKS:
            if (run_id, task, difficulty) not in specs:
                specs[(run_id, task, difficulty)] = load_specs(run_id, task, difficulty)
            annotate_swaps(task, entry, specs[(run_id, task, difficulty)][episode], h5_path)
        if task in SIMULATED_DEMO_TASKS:
            # 07 起生成器直出「同一条重复两遍」的 h5：已有 demo 前缀就只校验、不再翻倍；
            # 05/06 的旧数据没有 demo 前缀，仍在这里模拟出来。
            if entry["demo"] > 0:
                if entry["total"] != 2 * entry["demo"]:
                    skipped.append({"task": task, "difficulty": difficulty, "episode": episode, "seed": row.get("seed"),
                                    "h5_path": str(h5_path), "reason": "BinFill demo 前缀不是全长一半"})
                    continue
                entry = {**entry, "original_total": entry["demo"], "simulated_demo": True, "demo_source": "recorded"}
            else:
                entry = {**simulate_binfill_demo(entry), "demo_source": "simulated"}
        groups[key].append(entry)
    groups, excluded_slow = apply_slow_exclusion(groups)
    # swap 统计与 BinFill demo 来源都按剔除后的 groups 重算
    for rows in groups.values():
        for r in rows:
            if "swap_check" not in r:
                continue
            swap_summary["episodes"] += 1
            if r["swap_check"] == "FAIL":
                swap_summary["fail"] += 1
            elif r["swap_check"] == "WARN":
                swap_summary["warn"] += 1
    binfill_demo_source: dict[str, str] = {}
    for task, difficulty in GROUPS:
        if task not in SIMULATED_DEMO_TASKS:
            continue
        kinds = {r.get("demo_source") for r in groups.get(f"{task}/{difficulty}", [])}
        if kinds:
            binfill_demo_source[f"{task}/{difficulty}"] = kinds.pop() if len(kinds) == 1 else "mixed"
    return {
        "rollout_run_id": ",".join(run_ids),
        "rollout_run_ids": list(run_ids),
        "source": ",".join(str(s.relative_to(REPO_ROOT)) for s in sources),
        "group_sources": group_sources,
        "window": WIN, "stride": STRIDE, "budgets": list(BUDGETS),
        "binfill_simulated_demo": True,
        "binfill_demo_source": binfill_demo_source,
        "episodes": sum(len(rows) for rows in groups.values()),
        "episodes_before_exclusion": sum(len(rows) for rows in groups.values()) + len(excluded_slow),
        "groups": groups,
        "skipped": skipped,
        "failed_rows": failed,
        "unknown_labels": unknown_labels,
        "swap_summary": swap_summary,
        "excluded_slow": excluded_slow,
        "exclusion_rule": {"max_segment_frames": MAX_SEGMENT_FRAMES, "t_median_factor": SLOW_T_MEDIAN_FACTOR,
                           "median_basis": "剔除前按组"},
    }


# ── 自动表 ──────────────────────────────────────────────────────────────────
def _fmt(v: float) -> str:
    return f"{v:g}" if float(v).is_integer() else f"{v:.1f}"


def _seq_text(row: dict[str, Any]) -> str:
    parts = []
    for start, length, text in row["segs"]:
        if row["demo"] and start == row["demo"]:
            parts.append("‖")
        parts.append(f"{short_label(text)[0]} {length}")
    return " · ".join(parts).replace(" · ‖ · ", " ‖ ")


def _swap_text(row: dict[str, Any]) -> str:
    parts = [f"{k + 1}: {s}–{e} {label}" for k, (s, e, label) in enumerate(row.get("swaps", []))]
    text = " · ".join(parts) or "—"
    if row.get("swap_source") == "joint_static":
        sj, sp = row.get("swap_start_joint"), row.get("swap_start_pixel")
        text += (f"（关节法 S={sj} = 像素法，B1−S={row.get('b1_minus_s')}）" if sj == sp
                 else f"（关节法 S={sj}、像素法 S={sp}，取像素法，B1−S={row.get('b1_minus_s')}）")
    if row.get("swap_check") != "PASS":
        text = f"⚠{row.get('swap_check')} " + text
    return text


def demo_note(rows: list[dict[str, Any]], *, in_title: bool) -> str:
    """BinFill 的 demo 来源文案：07 起由生成器直出、05/06 是脚本模拟；非 BinFill 返回空串。

    ``in_title`` 为真时给组表标题用（带「T = 2×原 T」），否则给汇总表的组名后缀用。
    """
    if not rows or not rows[0].get("simulated_demo"):
        return ""
    if rows[0].get("demo_source") == "recorded":
        return "；demo 由生成器直出（重复两遍），T = 2×原 T" if in_title else "（demo 由生成器直出（重复两遍））"
    return "；模拟 demo：同一条重复两遍，T = 2×原 T" if in_title else "（模拟 demo）"


def render_tables(data: dict[str, Any]) -> tuple[str, int]:
    lines = ["### 汇总（每组：条数、T、demo 长度、motion token 数）", "",
             "| 组 | 条数 | T 最短 / 中位 / 最长 | demo 最短 / 中位 / 最长 | 窗口 最少 / 中位 / 最多 | 铺不出窗口 | 跳过／失败 | 慢条剔除 |",
             "|---|---|---|---|---|---|---|---|"]
    skipped = {}
    for item in data.get("skipped", []) + data.get("failed_rows", []):
        skipped[f"{item['task']}/{item['difficulty']}"] = skipped.get(f"{item['task']}/{item['difficulty']}", 0) + 1
    excluded_slow = data.get("excluded_slow", [])
    excluded_count: dict[str, int] = {}
    for item in excluded_slow:
        key = f"{item['task']}/{item['difficulty']}"
        excluded_count[key] = excluded_count.get(key, 0) + 1
    total_rows = 0
    for task, difficulty in GROUPS:
        key = f"{task}/{difficulty}"
        rows = data["groups"].get(key, [])
        if not rows:
            lines.append(f"| {key} | 0 | — | — | — | — | {skipped.get(key, 0)} | {excluded_count.get(key, 0)} |")
            continue
        totals = [r["total"] for r in rows]
        demos = [r["demo"] for r in rows]
        tokens = [sum(window_counts(r)) for r in rows]
        zero = sum(1 for t in tokens if t == 0)
        label = key + demo_note(rows, in_title=False)
        lines.append(f"| {label} | {len(rows)} | {min(totals)} / {_fmt(statistics.median(totals))} / {max(totals)} "
                     f"| {min(demos)} / {_fmt(statistics.median(demos))} / {max(demos)} "
                     f"| {min(tokens)} / {_fmt(statistics.median(tokens))} / {max(tokens)} | {zero} | {skipped.get(key, 0)} "
                     f"| {excluded_count.get(key, 0)} |")
    lines.append("")
    for task, difficulty in GROUPS:
        key = f"{task}/{difficulty}"
        rows = sorted(data["groups"].get(key, []), key=lambda r: r["episode"])
        has_swaps = task in SWAP_TASKS
        dropped = excluded_count.get(key, 0)
        lines += [f"### {task} / {difficulty}（{len(rows)} 条" + demo_note(rows, in_title=True)
                  + (f"；剔除 {dropped} 条" if dropped else "") + "）", "",
                  "| ep | seed | T | demo | 段数 | 窗口 demo+exec=合计 | Δ32 | Δ8 | 段序列（短标 帧数，‖ = demo→exec） |"
                  + (" swap 起止帧（发起者↔搭档） |" if has_swaps else ""),
                  "|---|---|---|---|---|---|---|---|---|" + ("---|" if has_swaps else "")]
        for r in rows:
            d, e = window_counts(r)
            d32, d8 = deltas(r["total"])
            t_cell = f"{r['total']} = 2×{r['original_total']}" if r.get("simulated_demo") else str(r["total"])
            lines.append(f"| {r['episode']} | {r['seed']} | {t_cell} | {r['demo']} | {len(r['segs'])} | {d}+{e}={d + e}"
                         f"{'（无 motion token）' if d + e == 0 else ''} | {d32:.1f} | {d8:.1f} | {_seq_text(r)} |"
                         + (f" {_swap_text(r)} |" if has_swaps else ""))
            total_rows += 1
        lines.append("")
    # 剔除清单：不计入逐条行数（total_rows），只供人工复核
    lines += [f"### 剔除的慢条（供复核；规则：单段 > {MAX_SEGMENT_FRAMES} 帧 或 T > 组中位 × {SLOW_T_MEDIAN_FACTOR:g}，"
              "中位按剔除前算；BinFill 按后一遍原 T）", "",
              "| 组 | ep | seed | T | 组中位 T | 最长段（标签 帧数） | 命中原因 | h5 |",
              "|---|---|---|---|---|---|---|---|"]
    if not excluded_slow:
        lines.append("| （本轮无剔除） | | | | | | | |")
    for item in excluded_slow:
        lines.append(f"| {item['task']}/{item['difficulty']} | {item.get('episode')} | {item.get('seed')} "
                     f"| {item.get('effective_total')} | {_fmt(item.get('group_median', 0))} "
                     f"| {item.get('longest_segment_label')} {item.get('longest_segment_frames')} "
                     f"| {'；'.join(item.get('reasons', []))} | {item.get('h5_path') or '—'} |")
    lines.append("")
    return "\n" + "\n".join(lines).rstrip("\n") + "\n", total_rows


def split_region(text: str) -> tuple[str, str, str]:
    start, end = text.find(BEGIN), text.find(END)
    if start < 0 or end < 0 or end < start:
        raise ValueError(f"文档缺少 {BEGIN} / {END} 标记")
    return text[: start + len(BEGIN)], text[start + len(BEGIN): end], text[end:]


def load_timeline(json_path: Path | None = None) -> dict[str, Any]:
    return json.loads((json_path or TIMELINE_JSON).read_text(encoding="utf-8"))


def check(json_path: Path | None = None, doc_path: Path | None = None) -> tuple[bool, int, int]:
    """重新生成并与文档比对，返回 (是否一致, 逐条行数, 漂移行数)；缺文件时漂移记 -1。"""
    try:
        block, rows = render_tables(load_timeline(json_path))
        _, current, _ = split_region((doc_path or DOC).read_text(encoding="utf-8"))
    except (ValueError, FileNotFoundError):
        return False, 0, -1
    diff = [line for line in difflib.ndiff(current.splitlines(), block.splitlines()) if line[:1] in "+-"]
    return not diff, rows, len(diff)


# ── 入口 ────────────────────────────────────────────────────────────────────
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="采样窗口数轴数据层：extract 抽轨迹成 JSON；tables 生成/校验文档自动表")
    sub = parser.add_subparsers(dest="command", required=True)
    ext = sub.add_parser("extract", help="从实跑 HDF5 抽 T / demo / 分段，写 windows_timeline.json")
    ext.add_argument("--rollout-run-id", default=DEFAULT_ROLLOUT_RUN_ID, help="逗号分隔的一个或多个运行编号，后者覆盖前者的同 key 行")
    ext.add_argument("--mode", default=None, help="feasibility 下的档目录名（各运行只有一个档时可省；给了则对每个运行都用它）")
    ext.add_argument("--out", default=str(TIMELINE_JSON))
    tab = sub.add_parser("tables", help="生成或校验 SAMPLING_WINDOWS.md 的自动表")
    tab.add_argument("--json", default=str(TIMELINE_JSON))
    tab.add_argument("--doc", default=str(DOC))
    mode = tab.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true", help="默认")
    mode.add_argument("--print", action="store_true")
    args = parser.parse_args(argv)

    if args.command == "extract":
        run_ids = [item.strip() for item in args.rollout_run_id.split(",") if item.strip()]
        sources = [rollout_dir(run_id, args.mode) for run_id in run_ids]
        payload = extract(run_ids, sources)
        out = Path(args.out)
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        for text, count in payload["unknown_labels"].items():
            print(f"  ⚠ 规则表未覆盖的 subgoal 文本（兜底截断）：{text!r} × {count}", file=sys.stderr)
        for item in payload["skipped"]:
            print(f"  跳过 {item['task']}/{item['difficulty']} ep{item['episode']}：{item['reason']}", file=sys.stderr)
        for item in payload["excluded_slow"]:
            print(f"  剔除 {item['task']}/{item['difficulty']} ep{item['episode']} seed{item['seed']}："
                  f"{'；'.join(item['reasons'])}", file=sys.stderr)
        for key, rows in payload["groups"].items():
            for r in rows:
                if r.get("swap_check") not in (None, "PASS"):
                    print(f"  swap {r['swap_check']}：{key} ep{r['episode']} start={r.get('swap_start')} joint={r.get('swap_start_joint')} "
                          f"pixel={r.get('swap_start_pixel')} b1_minus_s={r.get('b1_minus_s')} first={r.get('swap_pixel_first')}", file=sys.stderr)
        adjusted = sum(1 for rows in payload["groups"].values() for r in rows
                       if r.get("swap_start_joint") is not None and r.get("swap_start_joint") != r.get("swap_start"))
        payload["swap_summary"]["pixel_adjusted"] = adjusted
        groups_ok = sum(1 for rows in payload["groups"].values() if rows)
        sw = payload["swap_summary"]
        ok = groups_ok == len(GROUPS) and payload["episodes"] > 0 and sw["fail"] == 0
        print(f"WINDOWS_EXTRACT={'PASS' if ok else 'FAIL'} groups={groups_ok} episodes={payload['episodes']} "
              f"skipped={len(payload['skipped'])} failed_rows={len(payload['failed_rows'])} "
              f"unknown_labels={len(payload['unknown_labels'])} swap_episodes={sw['episodes']} swap_fail={sw['fail']} swap_warn={sw['warn']} "
              f"swap_pixel_adjusted={sw.get('pixel_adjusted', 0)} excluded_slow={len(payload['excluded_slow'])} "
              f"out={out.relative_to(REPO_ROOT) if out.is_relative_to(REPO_ROOT) else out}")
        return 0 if ok else 1

    json_path, doc_path = Path(args.json), Path(args.doc)
    block, rows = render_tables(load_timeline(json_path))
    if args.print:
        print(block)
        return 0
    if args.write:
        head, _, tail = split_region(doc_path.read_text(encoding="utf-8"))
        doc_path.write_text(head + block + tail, encoding="utf-8")
        print(f"WINDOW_TABLES=WRITTEN groups={len(GROUPS)} rows={rows}")
        return 0
    ok, rows, drift = check(json_path, doc_path)
    if not ok and drift > 0:
        _, current, _ = split_region(doc_path.read_text(encoding="utf-8"))
        for line in [l for l in difflib.ndiff(current.splitlines(), block.splitlines()) if l[:1] in "+-"][:5]:
            print(f"  漂移：{line[:160]}", file=sys.stderr)
    print(f"WINDOW_TABLES={'PASS' if ok else 'FAIL'} groups={len(GROUPS)} rows={rows} drift={drift}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
