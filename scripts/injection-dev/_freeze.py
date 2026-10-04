"""第一阶段 ③封存：按完整选签函数选正式局，算 ``spec_sha256``／``identity_sha256``／``delivery_sha256``，排他落盘。

选签逻辑由 ``scripts/parity/v4_specs.py`` 的 ``stratified_select`` / ``_movecube_way`` / ``freeze`` 搬来，语义不变：
按 ``select`` 给出的 index 选正式局；MoveCube 在新值档按运动方式分层（每种 way 取编号最小的候选，不足按 index 补齐）。
与原实现的差别：输入是内存里的抽签行、输出是 ``(header, rows)``；首次落盘用
``os.link`` 排他发布（目标已存在就原子失败，不用会静默覆盖的 ``os.replace``）。

schema 由调用方显式传入，且只接受 ``hard-specs/4``（``/2`` 单档与 ``/3`` v7 母布局两支已于维护计划 W2 删除）：

* ``hard-specs/4``（v8／v9）：每档一次冻结、档内逐任务独立抽；``select`` 为 ``{task: 索引元组}``（逐格配额 = 元组长度），
  header 的 ``select_rule``／``per_env``／``delivery_per_cell`` 都是逐任务字典，``layout_rule`` 固定 independent、
  ``exec_cap`` 固定 ``EXEC_CAP``，行 ``layout_parent`` 为 null。
"""

from __future__ import annotations

import copy
import math
import os
import tempfile
from pathlib import Path
from typing import Any

import _common  # noqa: F401  路径设置

from robomme_hard.env_record_wrapper import hard_specs  # noqa: E402
from robomme_hard.env_record_wrapper.hard_specs import SpecsError  # noqa: E402

MOVECUBE_WAYS = (0, 1, 2)  # MoveCube.py::self.ways：peg_push / gripper_push / grasp_putdown

_TWO = ("xhard1", "xhard2")
#: v8 逐格候选数默认表（v8 方案第二部分 §2.2 第 6 条）：每格候选数 = ⌈局数 ÷ (1 − 生成失败率)⌉ + 余量；
#: 抽签拒绝率只放大 reset 次数、不改候选数。合计 1425（首轮 1070 + 递补上限 355）。
V8_DEFAULT_CANDIDATES: dict[tuple[str, str], int] = {
    ("InsertPeg", "xhard4"): 40,
    ("MoveCube", "xhard4"): 32,
    ("BinFill", "xhard1"): 57, ("BinFill", "xhard2"): 57,
    ("PickXtimes", "xhard1"): 22, ("PickXtimes", "xhard2"): 22, ("PickXtimes", "xhard3"): 21,
    **{(task, tier): 13 for task in ("SwingXtimes", "StopCube") for tier in hard_specs.TIERS},
    **{(task, tier): 26 for task in ("VideoUnmask", "ButtonUnmask")
       for tier in ("xhard1", "xhard2", "xhard3", "xhard4")},
    **{(task, tier): 52 for task in ("VideoUnmaskSwap", "ButtonUnmaskSwap", "VideoPlaceButton", "VideoPlaceOrder",
                                     "PickHighlight", "VideoRepick") for tier in _TWO},
    **{(task, tier): n for task in ("RouteStick", "PatternLock")
       for tier, n in zip(("xhard1", "xhard2", "xhard3"), (36, 36, 34))},
}
# V8 1070 局格表已于维护计划阶段 1b（W4）删除；候选表改与 V9_CELLS 的 43 格一一对应
# （两表格集合相同），并核档位都在 TIERS 内、候选数为正整数
assert set(V8_DEFAULT_CANDIDATES) == set(hard_specs.V9_CELLS), "v8 候选表须与 V9_CELLS 的 43 格一一对应"
assert all(tier in hard_specs.TIERS for _, tier in V8_DEFAULT_CANDIDATES), "v8 候选表含未知档位"
assert all(isinstance(n, int) and n > 0 for n in V8_DEFAULT_CANDIDATES.values()), "v8 候选数须为正整数"
assert sum(V8_DEFAULT_CANDIDATES.values()) == 1425, "v8 候选合计须为 1425（§2.2 第 6 条）"

#: v9 候选表（v9 方案第二部分 §2.2 第 3 条）：只列 V9 重新抽签的格；MoveCube xhard4 交付 50、候选 80
#: （按失败率 35% 留量：80 × 0.65 = 52 ≥ 50）。InsertPeg 走 ``v9_subset_specs.py extend``（V8 未试 11 个 + 追加 35 个），
#: 不经本表；其余 14 任务从 V8 交付行取子集，不抽签。``v8_default_candidates`` 不读本表：候选数默认等于局数，
#: V9 抽签必须显式 ``--candidates-per-env MoveCube=80``（``--dry-run`` 的 FREEZE_CELL 行可核对）。
V9_CANDIDATES: dict[tuple[str, str], int] = {("MoveCube", "xhard4"): 80}
assert all(V9_CANDIDATES[k] > hard_specs.V9_CELLS[k] for k in V9_CANDIDATES), "v9 每格候选数须大于局数"
#: v9 MoveCube xhard4 逐运动方式配额（v9 方案第二部分 §2.2 第 4 条，审计 8）：way 0/1/2 = 17/17/16，合计 = 格局数 50
V9_MOVECUBE_QUOTA_BY_WAY: dict[int, int] = {0: 17, 1: 17, 2: 16}
assert sum(V9_MOVECUBE_QUOTA_BY_WAY.values()) == hard_specs.V9_CELLS[("MoveCube", "xhard4")]
assert set(V9_MOVECUBE_QUOTA_BY_WAY) == set(MOVECUBE_WAYS)


def default_quota_by_way(task: str, tier: str, quota: int) -> dict[int, int] | None:
    """逐方式配额的默认取值：只有 MoveCube xhard4 且配额恰为 V9 格局数（50）时返回 ``V9_MOVECUBE_QUOTA_BY_WAY``，
    其余（V7／V8 的 MoveCube 20、冒烟 1 局、别的任务）一律 None，即沿用原分层规则、行为逐字不变。"""
    if task == "MoveCube" and tier == "xhard4" and int(quota) == sum(V9_MOVECUBE_QUOTA_BY_WAY.values()):
        return dict(V9_MOVECUBE_QUOTA_BY_WAY)
    return None


def format_quota_by_way(quota_by_way: dict[int, int] | None) -> str:
    """``{0:17,1:17,2:16}`` 形式（判定行与 ``--dry-run`` 打印用）；None 打印 ``-``。"""
    if not quota_by_way:
        return "-"
    return "{" + ",".join(f"{way}:{int(n)}" for way, n in sorted(quota_by_way.items())) + "}"


#: v8 抽签接受率（reset 成功数 ÷ 尝试数）：取 v7 xhard4 正式抽签实测（包内 xhard4 header
#: ``draw_stats.main.per_task``，每任务 30 候选）；未列出的任务按 §2.4.3「其余 ÷ 0.97～1.0」取保守的 0.97。
#: 只用于 ``--dry-run`` 的预算打印与 v8 默认 reset 上限，不进规格。
V8_DRAW_ACCEPT = {"VideoPlaceButton": 0.46, "VideoPlaceOrder": 0.47, "VideoRepick": 0.54, "ButtonUnmaskSwap": 0.57,
                  "PickHighlight": 0.65, "SwingXtimes": 0.97}
V8_DRAW_ACCEPT_DEFAULT = 0.97
#: 每格 reset 上限 = ⌈候选数 ÷ 接受率 × 1.5⌉（§2.4.3）
V8_RESET_SAFETY = 1.5


def v8_reset_cap(task: str, candidates: int) -> int:
    """§2.4.3 口径的每格 reset 上限（抽签循环里该任务的 ``max_reset_attempts``）。"""
    accept = V8_DRAW_ACCEPT.get(task, V8_DRAW_ACCEPT_DEFAULT)
    return int(math.ceil(candidates / accept * V8_RESET_SAFETY - 1e-9))


def v8_default_candidates(cells: dict[tuple[str, str], int]) -> dict[tuple[str, str], int]:
    """格表 → 默认候选数：候选数默认等于局数（不备用），需要备用候选时显式给 ``--candidates-per-env``。

    原口径「局数恰等于 V8 表 2 值的格取 ``V8_DEFAULT_CANDIDATES``」随 V8 1070 局表于维护计划
    阶段 1b（W4）删除；V9 抽签本就显式给候选数（``V9_CANDIDATES``），不受影响。"""
    return {key: int(n) for key, n in cells.items()}


def _movecube_way(spec: dict[str, Any]) -> int | None:
    """录像局用的是最后一次 _initialize_episode 的 way_idx（构造期 reset 是 initializations.0，正式 reset 是最大序号）。"""
    inits = spec.get("initializations") if isinstance(spec, dict) else None
    if not isinstance(inits, dict) or not inits:
        return None
    last = max(inits, key=lambda k: int(k))
    way = inits[last].get("way_idx") if isinstance(inits[last], dict) else None
    return int(way) if way is not None else None


def candidates_by_way(ok_rows: list[dict[str, Any]]) -> dict[int | None, list[int]]:
    """成功候选按运动方式分组（候选号升序）；读不到 way_idx 的归到 None。"""
    by_way: dict[int | None, list[int]] = {}
    for row in ok_rows:
        by_way.setdefault(_movecube_way(row["spec"]), []).append(row["episode"])
    return {way: sorted(eps) for way, eps in by_way.items()}


def stratified_select(task: str, difficulty: str, ok_rows: list[dict[str, Any]], select,
                      quota: int | None = None, quota_by_way: dict[int, int] | None = None) -> list[int]:
    """选正式局。``quota``（逐格配额，v8）缺省为 ``len(select)``，此时与原实现逐字同义；
    MoveCube 在新值档（``TIERS``）按运动方式分层：每种 way 取编号最小的候选，
    不足先按 ``select`` 再按候选编号补齐到配额。

    ``quota_by_way``（v9 MoveCube，``{0:17, 1:17, 2:16}``）给出时改走逐方式配额：每种方式在自己的候选里按
    候选号升序取前 ``quota_by_way[way]`` 个，不挪用别的方式；某方式候选数 < 配额即抛 ``SpecsError``，报错里写
    三种方式各有多少候选、各差几个。配额合计必须等于 ``quota``（给出时）。V7／V8 调用不传该参数，行为逐字不变。"""
    if quota_by_way is not None:
        return _select_by_way_quota(task, difficulty, ok_rows, quota, quota_by_way)
    quota = len(select) if quota is None else int(quota)
    episodes = [r["episode"] for r in ok_rows]
    default = [e for e in episodes if e in select][:quota]
    if task != "MoveCube" or difficulty not in hard_specs.TIERS:
        return default
    by_way: dict[int, list[int]] = {}
    for row in ok_rows:
        way = _movecube_way(row["spec"])
        if way is not None:
            by_way.setdefault(way, []).append(row["episode"])
    chosen: list[int] = []
    for way in MOVECUBE_WAYS:
        candidates = sorted(by_way.get(way, []))
        if candidates and len(chosen) < quota:
            chosen.append(candidates[0])
    for episode in list(select) + episodes:
        if len(chosen) >= quota:
            break
        if episode in episodes and episode not in chosen:
            chosen.append(episode)
    return sorted(chosen[:quota])


def _select_by_way_quota(task: str, difficulty: str, ok_rows: list[dict[str, Any]], quota: int | None,
                         quota_by_way: dict[int, int]) -> list[int]:
    if task != "MoveCube":
        raise SpecsError(f"quota_by_way 只用于 MoveCube（收到 {task}）")
    if set(quota_by_way) != set(MOVECUBE_WAYS) or any(not isinstance(n, int) or n < 0 for n in quota_by_way.values()):
        raise SpecsError(f"quota_by_way 须为 {{0,1,2: 非负整数}}：{quota_by_way!r}")
    total = sum(quota_by_way.values())
    if quota is not None and int(quota) != total:
        raise SpecsError(f"{task}/{difficulty} quota_by_way 合计 {total} ≠ 格配额 {quota}")
    by_way = candidates_by_way(ok_rows)
    have = {way: len(by_way.get(way, [])) for way in MOVECUBE_WAYS}
    short = {way: quota_by_way[way] - have[way] for way in MOVECUBE_WAYS if have[way] < quota_by_way[way]}
    if short:
        detail = "，".join(f"way{way} 候选 {have[way]} 配额 {quota_by_way[way]} 差 {max(quota_by_way[way] - have[way], 0)}"
                          for way in MOVECUBE_WAYS)
        raise SpecsError(f"{task}/{difficulty} 逐方式配额 {format_quota_by_way(quota_by_way)} 选不满：{detail}"
                         f"（无 way 候选 {len(by_way.get(None, []))} 个）")
    return sorted(ep for way in MOVECUBE_WAYS for ep in by_way.get(way, [])[:quota_by_way[way]])


def parse_select(text: str) -> tuple[int, ...]:
    """逗号分隔的候选 index，或 ``a..b`` 闭区间（``parse_select_by_task`` 的全局写法）。"""
    if ".." in text:
        lo, _, hi = text.partition("..")
        return tuple(range(int(lo), int(hi) + 1))
    return tuple(int(x) for x in text.split(","))


def parse_select_by_task(text: str, tasks, default: dict[str, tuple[int, ...]]) -> dict[str, tuple[int, ...]]:
    """v8 逐任务选取区间。``text``：

    * ``default`` → 用 ``default``（v8：每任务 ``0..配额-1``）；
    * 全局写法（不含 ``=``，同 ``parse_select``）→ 每个任务同一组索引（兼容旧写法）；
    * 逐任务写法 ``TASK=a..b,TASK=n,...``（每条一个闭区间或单个索引）→ 列出的任务覆盖，未列出的沿用 ``default``。"""
    tasks = list(tasks)
    if text == "default":
        return {task: tuple(default[task]) for task in tasks}
    if "=" not in text:
        chosen = parse_select(text)
        return {task: chosen for task in tasks}
    out = {task: tuple(default[task]) for task in tasks}
    for item in filter(None, (x.strip() for x in text.split(","))):
        task, _, value = item.partition("=")
        if task not in out or not value:
            raise SpecsError(f"--select 逐任务条目须为 TASK=a..b 且任务在本档内：{item!r}")
        if ".." in value:
            lo, _, hi = value.partition("..")
            out[task] = tuple(range(int(lo), int(hi) + 1))
        else:
            out[task] = (int(value),)
    return out


def parse_int_by_task(text: str | None, tasks, default: dict[str, int], label: str) -> dict[str, int]:
    """逐任务整数（``--candidates-per-env``）：``None`` 或空 → ``default``；纯整数 → 全部任务同值（兼容旧写法）；
    ``TASK=N,...`` → 列出的任务覆盖，未列出的沿用 ``default``。"""
    tasks = list(tasks)
    if text is None or str(text).strip() == "":
        return {task: int(default[task]) for task in tasks}
    text = str(text).strip()
    if "=" not in text:
        return {task: int(text) for task in tasks}
    out = {task: int(default[task]) for task in tasks}
    for item in filter(None, (x.strip() for x in text.split(","))):
        task, _, value = item.partition("=")
        if task not in out or not value.isdigit():
            raise SpecsError(f"{label} 逐任务条目须为 TASK=N 且任务在本档内：{item!r}")
        out[task] = int(value)
    return out


def freeze(drafts: list[dict[str, Any]], header_parts: dict[str, Any], select,
           candidates_per_env: int | dict[str, int] = 10, *,
           schema: str, quota_by_way: dict[str, dict[int, int] | None] | None = None,
           expected_cells: dict[tuple[str, str], int] | None = None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """纯函数：抽签行 → ``(header, rows)``。``schema`` 必须显式给出且只能是 ``hard-specs/4``。

    ``header_parts`` 必含 ``difficulty tasks seed_rule sampling_config recovery_rule identity_source run_id draw_stats
    provenance``，不得带 ``layout_rule``（``/4`` 的 ``layout_rule`` 固定为 ``LAYOUT_RULE``、``exec_cap`` 固定为
    ``EXEC_CAP``，由本函数写入）。

    ``/4``：``select`` 为 ``{task: 索引元组}``（也接受全局元组，按每任务同一组索引展开），逐格配额 = 元组长度；
    某任务成功候选选不满配额即拒绝；header ``select_rule[task]`` 写实际选中的 episode 列表（MoveCube 分层后
    可能不是 ``0..n-1``）、``per_env[task]`` 写成功候选数、``delivery_per_cell[task]`` 写配额；
    逐任务的尝试数、初选与请求候选数写进 ``draw_stats.freeze_per_env``（不进签）。

    ``quota_by_way``：``{task: {way: 配额}}``；缺省 None 时逐任务取 ``default_quota_by_way``（只有 V9 的
    MoveCube xhard4 配额 50 才启用 17／17／16，V7／V8 不受影响）。启用时打印 ``FREEZE_WAYS`` 一行（逐方式配额与
    逐方式候选数），并把两者写进 ``draw_stats.freeze_per_env[task]``（不进签）；某方式候选不足即抛错。
    ``expected_cells``：封签后校验用的配额上限格表，缺省按本档逐任务配额 ``resolve_cell_table`` 取
    （V9 配额落 V9_CELLS）。"""
    if schema != hard_specs.SCHEMA:
        raise SpecsError(f"未知 schema {schema!r}，只支持 {hard_specs.SCHEMA}")
    difficulty, seed_rule = header_parts["difficulty"], header_parts["seed_rule"]
    if "layout_rule" in header_parts:
        raise SpecsError(f"{schema} 不接受调用方给的 layout_rule（固定 independent）")
    # 按 TIERS（五档，含 xhard5）校验档位
    if difficulty not in hard_specs.TIERS:
        raise SpecsError(f"未知档位 {difficulty}（{schema}）")
    tasks = list(header_parts["tasks"])
    select_by = {task: tuple(select[task] if isinstance(select, dict) else select) for task in tasks}
    rows, per_env = [], {}
    for task in tasks:
        ok_rows = []
        for row in drafts:
            if row["task"] != task or not row["reset_ok"]:
                continue
            if row["spec_sha256"] != hard_specs.spec_sha256(row["spec"]):
                raise SpecsError(f"抽签行规格散列不符：{task}/{row['episode']}")
            if row["difficulty"] != difficulty:
                raise SpecsError(f"抽签行档位与 header 不符：{task}/{row['episode']}")
            if row["seed"] != hard_specs.seed_for(task, row["episode"], row["attempt"], seed_rule):
                raise SpecsError(f"抽签行 seed 与公式不符：{task}/{row['episode']}")
            ok_rows.append(row)
        ok_rows.sort(key=lambda r: r["episode"])
        if [r["episode"] for r in ok_rows] != list(range(len(ok_rows))):
            raise SpecsError(f"{task} 的成功候选编号不连续")
        quota = len(select_by[task])
        ways = default_quota_by_way(task, difficulty, quota) if quota_by_way is None else quota_by_way.get(task)
        if ways is not None:
            have = candidates_by_way(ok_rows)
            print(f"FREEZE_WAYS task={task} tier={difficulty} quota_by_way={format_quota_by_way(ways)} "
                  f"candidates_by_way={format_quota_by_way({w: len(have.get(w, [])) for w in MOVECUBE_WAYS})} "
                  f"no_way={len(have.get(None, []))}", flush=True)
        chosen = stratified_select(task, difficulty, ok_rows, select_by[task], quota, ways)
        if len(chosen) != quota:
            raise SpecsError(f"{task}/{difficulty} 成功候选 {len(ok_rows)} 个，选不满配额 {quota}"
                             f"（select={list(select_by[task])}，选中 {chosen}）")
        per_env[task] = {"attempted": sum(1 for r in drafts if r["task"] == task), "candidates": len(ok_rows),
                         "initial_selected": chosen}
        if ways is not None:
            have = candidates_by_way(ok_rows)
            per_env[task]["quota_by_way"] = {str(w): int(ways[w]) for w in MOVECUBE_WAYS}
            per_env[task]["candidates_by_way"] = {str(w): len(have.get(w, [])) for w in MOVECUBE_WAYS}
        for row in ok_rows:
            flag = row["episode"] in chosen
            rows.append({
                "record": "spec", "task": task, "tier": difficulty, "candidate": row["episode"],
                "episode": row["episode"], "seed": row["seed"], "attempt": row["attempt"],
                "spec": row["spec"], "spec_sha256": row["spec_sha256"],
                "selected": flag, "tried": False, "initial_selected": flag, "rollout": None,
                "layout_parent": None,
            })
    draw_stats = copy.deepcopy(header_parts["draw_stats"])
    requested = candidates_per_env if isinstance(candidates_per_env, dict) else {t: candidates_per_env for t in tasks}
    draw_stats = {**draw_stats, "freeze_per_env": {
        task: {**per_env[task], "candidates_requested": int(requested[task])} for task in tasks}}
    header_per_env: Any = {task: per_env[task]["candidates"] for task in tasks}
    select_rule: Any = {task: list(per_env[task]["initial_selected"]) for task in tasks}
    delivery_per_cell: Any = {task: len(select_by[task]) for task in tasks}
    header = {
        "record": "header",
        "schema": schema,
        "layout_rule": dict(hard_specs.LAYOUT_RULE),
        "exec_cap": hard_specs.EXEC_CAP,
        "difficulty": difficulty,
        "tasks": tasks,
        "per_env": header_per_env,
        "runtime": dict(hard_specs.RUNTIME),
        "seed_rule": dict(seed_rule),
        "select_rule": select_rule,
        "sampling_config": copy.deepcopy(header_parts["sampling_config"]),
        "sampling_config_sha256": hard_specs.digest(header_parts["sampling_config"]),
        "recovery_rule": copy.deepcopy(header_parts["recovery_rule"]),
        "identity_source": header_parts.get("identity_source", "formula"),
        "run_id": header_parts["run_id"],
        "draw_stats": draw_stats,
        "provenance": header_parts["provenance"],
        "delivery_per_cell": delivery_per_cell,
    }
    header["identity_sha256"] = hard_specs.identity_sha256(header, rows)
    header["delivery_sha256"] = hard_specs.delivery_sha256(rows)
    if expected_cells is None:
        expected_cells = hard_specs.resolve_cell_table({(task, difficulty): delivery_per_cell[task] for task in tasks})
    hard_specs.validate_specs(header, rows, expected_cells=expected_cells)
    return header, rows


def write_jsonl_exclusive(path: Path, records: list[dict[str, Any]]) -> None:
    """已存在拒绝覆盖；同目录临时文件 + ``os.link``（目标已存在即原子失败）。"""
    path = Path(path)
    if path.exists():
        raise SpecsError(f"{path} 已存在，禁止覆盖")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".hardspecs-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            for record in records:
                stream.write(hard_specs.canonical_json(record) + "\n")
        os.chmod(name, 0o644)
        os.link(name, path)
    finally:
        os.unlink(name)
