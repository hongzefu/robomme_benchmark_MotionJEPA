"""第一阶段 ③封存：按完整选签函数选正式局，算 ``spec_sha256``／``identity_sha256``／``delivery_sha256``，排他落盘。

选签逻辑由 ``scripts/parity/v4_specs.py`` 的 ``stratified_select`` / ``_movecube_way`` / ``freeze`` 搬来，语义不变：
默认按 index（0/3/6）选正式局；MoveCube 在新值档按运动方式分层（每种 way 取编号最小的候选，不足按 index 补齐）。
与原实现的差别：输入是内存里的抽签行、输出是 ``hard-specs/2`` 的 ``(header, rows)``；首次落盘用
``os.link`` 排他发布（目标已存在就原子失败，不用会静默覆盖的 ``os.replace``）。
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

import _common  # noqa: F401  路径设置

from robomme_hard.env_record_wrapper import hard_specs  # noqa: E402
from robomme_hard.env_record_wrapper.hard_specs import SpecsError  # noqa: E402

DEFAULT_SELECT = (0, 3, 6)
MOVECUBE_WAYS = (0, 1, 2)  # MoveCube.py::self.ways：peg_push / gripper_push / grasp_putdown


def _movecube_way(spec: dict[str, Any]) -> int | None:
    """录像局用的是最后一次 _initialize_episode 的 way_idx（构造期 reset 是 initializations.0，正式 reset 是最大序号）。"""
    inits = spec.get("initializations") if isinstance(spec, dict) else None
    if not isinstance(inits, dict) or not inits:
        return None
    last = max(inits, key=lambda k: int(k))
    way = inits[last].get("way_idx") if isinstance(inits[last], dict) else None
    return int(way) if way is not None else None


def stratified_select(task: str, difficulty: str, ok_rows: list[dict[str, Any]], select) -> list[int]:
    episodes = [r["episode"] for r in ok_rows]
    default = [e for e in episodes if e in select]
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
        if candidates:
            chosen.append(candidates[0])
    for episode in list(select) + episodes:
        if len(chosen) >= len(select):
            break
        if episode in episodes and episode not in chosen:
            chosen.append(episode)
    return sorted(chosen[: len(select)])


def parse_select(text: str) -> tuple[int, ...]:
    """``default``（0,3,6）、逗号分隔的候选 index，或 ``a..b`` 闭区间（v7：``0..19``）。"""
    if text == "default":
        return DEFAULT_SELECT
    if ".." in text:
        lo, _, hi = text.partition("..")
        return tuple(range(int(lo), int(hi) + 1))
    return tuple(int(x) for x in text.split(","))


def freeze(drafts: list[dict[str, Any]], header_parts: dict[str, Any], select=DEFAULT_SELECT,
           candidates_per_env: int = 10) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """纯函数：抽签行 → ``(header, rows)``。``header_parts`` 必含
    ``difficulty tasks seed_rule sampling_config recovery_rule identity_source run_id draw_stats provenance``；
    另带 ``layout_rule`` 时封成 v7 的 ``hard-specs/3``（母布局行 ``layout_parent`` 为 null）。"""
    difficulty, seed_rule = header_parts["difficulty"], header_parts["seed_rule"]
    v7 = "layout_rule" in header_parts
    if difficulty not in hard_specs.TIERS:
        raise SpecsError(f"未知档位 {difficulty}")
    rows, per_env = [], {}
    for task in header_parts["tasks"]:
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
        chosen = stratified_select(task, difficulty, ok_rows, select)
        per_env[task] = {"attempted": sum(1 for r in drafts if r["task"] == task), "candidates": len(ok_rows),
                         "initial_selected": chosen}
        for row in ok_rows:
            flag = row["episode"] in chosen
            rows.append({
                "record": "spec", "task": task, "tier": difficulty, "candidate": row["episode"],
                "episode": row["episode"], "seed": row["seed"], "attempt": row["attempt"],
                "spec": row["spec"], "spec_sha256": row["spec_sha256"],
                "selected": flag, "tried": False, "initial_selected": flag, "rollout": None,
                **({"layout_parent": None} if v7 else {}),
            })
    header = {
        "record": "header",
        "schema": hard_specs.SCHEMA_V7 if v7 else hard_specs.SCHEMA,
        **({"layout_rule": copy.deepcopy(header_parts["layout_rule"])} if v7 else {}),
        "difficulty": difficulty,
        "tasks": list(header_parts["tasks"]),
        "per_env": per_env,
        "runtime": dict(hard_specs.RUNTIME),
        "seed_rule": dict(seed_rule),
        "select_rule": {"indices": list(select), "movecube": "新值档按运动方式分层（MOVECUBE_WAYS）",
                        "candidates_per_env": candidates_per_env},
        "sampling_config": copy.deepcopy(header_parts["sampling_config"]),
        "sampling_config_sha256": hard_specs.digest(header_parts["sampling_config"]),
        "recovery_rule": copy.deepcopy(header_parts["recovery_rule"]),
        "identity_source": header_parts.get("identity_source", "formula"),
        "run_id": header_parts["run_id"],
        "draw_stats": header_parts["draw_stats"],
        "provenance": header_parts["provenance"],
        "delivery_per_cell": len(select),
    }
    header["identity_sha256"] = hard_specs.identity_sha256(header, rows)
    header["delivery_sha256"] = hard_specs.delivery_sha256(rows)
    hard_specs.validate_specs(header, rows)
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
