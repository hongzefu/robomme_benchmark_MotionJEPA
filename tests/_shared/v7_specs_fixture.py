"""V7 规格根（``hard-specs/3``）的纯 CPU 合成夹具：xhard4 母布局经 ``_freeze.freeze``（带 ``layout_rule``）封签，
xhard1～3 按 ``scripts/injection-dev/derive_specs.py::derive`` 的写法派生（行带 ``layout_parent``、规格为
``native-layered/3``），不 reset、不起仿真。供 ``test_v7_freeze_schema.py`` 与 ``test_v7_candidate_pool.py`` 共用。
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
_INJECTION_DEV = str(REPO / "scripts" / "injection-dev")
if _INJECTION_DEV not in sys.path:
    sys.path.insert(0, _INJECTION_DEV)

import _freeze  # noqa: E402
from robomme_hard.env_record_wrapper import hard_specs  # noqa: E402

LAYOUT_RULE = {"mode": "shared", "parent_tier": "xhard4", "whitelist_sha256": "0" * 64}
#: v7 派生档＝冻结 v7 四档去掉母布局 xhard4（v8 阶段 1 起读 V7_TIERS，不随全局 TIERS 变化）
DERIVED_TIERS = tuple(t for t in hard_specs.V7_TIERS if t != "xhard4")


def header_parts(tasks, *, difficulty: str = "xhard4", layout_rule: dict | None = LAYOUT_RULE,
                 profile: str = "v7") -> dict[str, Any]:
    parts = {"difficulty": difficulty, "tasks": list(tasks), "seed_rule": hard_specs.seed_rule_for(difficulty, profile),
             "sampling_config": {t: {"decision": {"k": t}, "native": {}} for t in tasks},
             "recovery_rule": {"rule": "off"}, "identity_source": "formula", "run_id": "v7-fixture",
             "draw_stats": {}, "provenance": {}}
    if layout_rule is not None:
        parts["layout_rule"] = copy.deepcopy(layout_rule)
    return parts


def parent_drafts(tasks, candidates: int, *, difficulty: str = "xhard4", profile: str = "v7") -> list[dict[str, Any]]:
    rule = hard_specs.seed_rule_for(difficulty, profile)
    drafts = []
    for task in tasks:
        for episode in range(candidates):
            spec = {"spec_kind": "native-newvalue/2", "task": task, "layout": {"x": episode}}
            drafts.append({"task": task, "difficulty": difficulty, "episode": episode, "attempt": 0,
                           "seed": hard_specs.seed_for(task, episode, 0, rule), "reset_ok": True,
                           "spec": spec, "spec_sha256": hard_specs.spec_sha256(spec)})
    return drafts


def freeze_parent(tasks, candidates: int, per_cell: int):
    """xhard4 母布局：``select=0..per_cell-1``，封成 ``hard-specs/3``。"""
    return _freeze.freeze(parent_drafts(tasks, candidates), header_parts(tasks), tuple(range(per_cell)), candidates,
                          schema=hard_specs.SCHEMA_V7)


def derive_tier(parent_header: dict, parent_rows: list[dict], tier: str, *, missing=frozenset()) -> tuple[dict, list]:
    """与 derive_specs.derive 同一写法：派生行 ``layout_parent`` 指向 xhard4 同候选；``missing`` 为派生失败的 (task, candidate)。"""
    tasks = [t for t in parent_header["tasks"] if t not in hard_specs.V7_XHARD4_ONLY]
    rows = []
    for mother in parent_rows:
        key = (mother["task"], int(mother["candidate"]))
        if mother["task"] not in tasks or key in missing:
            continue
        spec = {"spec_kind": "native-layered/3", "task": mother["task"], "layout": {"x": key[1]},
                "layout_drawn": {}, "layout_paths_hit": []}
        rows.append({"record": "spec", "task": mother["task"], "tier": tier, "candidate": key[1],
                     "episode": int(mother["episode"]), "seed": int(mother["seed"]), "attempt": int(mother["attempt"]),
                     "spec": spec, "spec_sha256": hard_specs.spec_sha256(spec),
                     "selected": bool(mother["initial_selected"]), "tried": False,
                     "initial_selected": bool(mother["initial_selected"]), "rollout": None,
                     "layout_parent": {"tier": "xhard4", "candidate": key[1], "spec_sha256": mother["spec_sha256"]}})
    rows.sort(key=lambda r: (r["task"], r["candidate"]))
    header = {key: copy.deepcopy(parent_header[key]) for key in (
        "record", "schema", "tasks", "runtime", "seed_rule", "select_rule", "sampling_config",
        "sampling_config_sha256", "recovery_rule", "identity_source", "layout_rule", "delivery_per_cell")}
    header.update(difficulty=tier, tasks=tasks, run_id=f"{parent_header['run_id']}-derive-{tier}",
                  per_env={t: {"candidates": sum(r["task"] == t for r in rows)} for t in tasks},
                  draw_stats={}, provenance={})
    header["identity_sha256"] = hard_specs.identity_sha256(header, rows)
    header["delivery_sha256"] = hard_specs.delivery_sha256(rows)
    hard_specs.validate_specs(header, rows)
    return header, rows


def build_root(root: Path, tasks=("BinFill", "StopCube"), candidates: int = 6, per_cell: int = 3,
               missing: dict[str, set] | None = None) -> Path:
    """写出 ``<root>/<V7_TIERS 各档>/specs.jsonl``；``missing={tier: {(task, candidate)}}`` 模拟派生失败。"""
    missing = missing or {}
    header4, rows4 = freeze_parent(tasks, candidates, per_cell)
    _freeze.write_jsonl_exclusive(root / "xhard4" / "specs.jsonl", [header4, *rows4])
    for tier in DERIVED_TIERS:
        header, rows = derive_tier(header4, rows4, tier, missing=missing.get(tier, set()))
        _freeze.write_jsonl_exclusive(root / tier / "specs.jsonl", [header, *rows])
    return root
