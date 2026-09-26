#!/usr/bin/env python3
"""V6 档位单调性检查器（计划 NEWTASK_RELEASE_V6_PLAN.md 的 S2「单调性检查器」与验收判据 TIER_MONOTONE）。

难度序 ``easy < medium < hard < xhard1 < xhard2 < xhard3 < xhard4``。每个环境按计划第三节总表里
用户指定（或实施方定）的难度维度取「每局取值的均值」，逐档比较：

* **闸门链**（计入判定）：``hard → xhard1 → xhard2 → xhard3 → xhard4``。每个维度均值
  单调不减，且每一步至少一个维度严格上升；任一维度下降 = 违例（``kind=decrease``），
  某一步所有维度都持平 = 违例（``kind=flat_step``）。
* **原三档链**（只报告、不计入）：``easy → medium → hard`` 是冻结的原版定义（V1 逐位冻结），
  原版本身不保证单调（如 SwingXtimes medium 轮数 [1,2] 低于 easy [1,3]），只作参照输出。

输入是「档名 → {维度: 取值}」，取值可以是标量、闭区间 ``[lo, hi]``（整数均匀，均值 (lo+hi)/2），
或逐局样本列表 ``{"samples": [...]}``（离线抽 200 局时传这个，均值取样本均值）。
缺某档或某维度取 ``None`` 时该维度在相邻两档间跳过比较（例如 VideoRepick hard 的块数是聚簇布局、
与新档的「块数」不同口径）。

``PLAN_TIERS`` 是按计划 2.3～2.12 表格逐格抄录的数值；新档 config 在管道那一路落地后，
用 :func:`tiers_from_decisions` 从各档 decision 抽出同一组维度再调 :func:`check_all`。

uv run --no-sync python -m scripts.parity.v6_tier_monotone       # 检查最终计划表
uv run --no-sync python -m scripts.parity.v6_tier_monotone --json
# 按 S1 运行规程，用 v4_specs draw 为每个新值档各自生成一份13环境 drafts.jsonl：
uv run --no-sync python -m scripts.parity.v4_specs draw --run-id v6-mono-xhard1 --tasks BinFill,PickXtimes,SwingXtimes,PickHighlight,VideoUnmask,ButtonUnmask,VideoUnmaskSwap,ButtonUnmaskSwap,VideoRepick,PatternLock,RouteStick,VideoPlaceButton,VideoPlaceOrder --difficulty xhard1 --seed-profile v6 --candidates-per-env 200 --max-reset-attempts 12000 --sampling-config scripts/configs/newtask-v6/sampling_config.json --out artifacts/newtask-v6/plan-probes/xhard1/drafts.jsonl
uv run --no-sync python -m scripts.parity.v6_tier_monotone --reset-all --drafts <xhard1.jsonl> --drafts <xhard2.jsonl> --drafts <xhard3.jsonl> --drafts <xhard4.jsonl> --samples 200 --out artifacts/newtask-v6/vp-tier-monotone.json

``--reset-all`` 消费四份 ``v4_specs draw`` 的真实 reset 规格，不启动仿真；每份须含13个梯度环境、
每环境200条连续成功 episode。无 ``--reset-all`` 时只验静态计划表，结果标签为 ``TIER_PLAN_TABLE``，
不得当作 ``TIER_MONOTONE`` 实测闸门。
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Mapping

NATIVE_CHAIN = ("easy", "medium", "hard")
GATE_CHAIN = ("hard", "xhard1", "xhard2", "xhard3", "xhard4")
NEWVALUE_TIERS = GATE_CHAIN[1:]
TIER_ORDER = ("easy", "medium", "hard", "xhard1", "xhard2", "xhard3", "xhard4")
EPS = 1e-9
REPO_ROOT = Path(__file__).resolve().parents[2]


def value_mean(value: Any) -> float | None:
    """单个维度取值的均值：标量原样、闭区间取中点、样本取算术平均、None 表示不可比。"""
    if value is None:
        return None
    if isinstance(value, Mapping):
        samples = value.get("samples")
        if not samples:
            raise ValueError(f"样本输入为空：{value!r}")
        return float(sum(samples)) / len(samples)
    if isinstance(value, (list, tuple)):
        if len(value) != 2 or value[0] > value[1]:
            raise ValueError(f"区间必须是 [lo, hi] 且 lo ≤ hi：{value!r}")
        return (float(value[0]) + float(value[1])) / 2.0
    return float(value)


def tier_means(tier_cfg: Mapping[str, Any]) -> dict[str, float | None]:
    return {dim: value_mean(v) for dim, v in tier_cfg.items()}


def value_interval(value: Any) -> tuple[float, float] | None:
    """返回配置值或实测样本的覆盖区间，用于检查相邻档是否有交集。"""
    if value is None:
        return None
    if isinstance(value, Mapping):
        samples = value.get("samples")
        if not samples:
            raise ValueError(f"样本输入为空：{value!r}")
        return float(min(samples)), float(max(samples))
    if isinstance(value, (list, tuple)):
        if len(value) != 2 or value[0] > value[1]:
            raise ValueError(f"区间必须是 [lo, hi] 且 lo ≤ hi：{value!r}")
        return float(value[0]), float(value[1])
    scalar = float(value)
    return scalar, scalar


def check_chain(env: str, tiers: Mapping[str, Mapping[str, Any]], chain=GATE_CHAIN) -> dict:
    """沿 ``chain`` 逐步比较均值与区间；缺档必须由 :func:`check_all` 报错。"""
    present = [t for t in chain if t in tiers]
    means = {t: tier_means(tiers[t]) for t in present}
    dims = sorted({d for t in present for d in means[t]})
    intervals = {t: {d: value_interval(v) for d, v in tiers[t].items()} for t in present}
    steps, violations = [], []
    for lo, hi in zip(present, present[1:]):
        rising, flat, falling = [], [], []
        overlaps = []
        for dim in dims:
            if dim not in means[lo] or dim not in means[hi]:
                if dim not in means[lo] or dim not in means[hi]:
                    violations.append({"env": env, "step": f"{lo}->{hi}", "dim": dim,
                                       "kind": "missing_dimension"})
                continue
            a, b = means[lo].get(dim), means[hi].get(dim)
            if a is None or b is None:
                continue
            if b > a + EPS:
                rising.append(dim)
            elif b < a - EPS:
                falling.append(dim)
                violations.append({"env": env, "step": f"{lo}->{hi}", "dim": dim, "kind": "decrease",
                                   "from": a, "to": b})
            else:
                flat.append(dim)
            interval_a, interval_b = intervals[lo].get(dim), intervals[hi].get(dim)
            if (b > a + EPS and lo in GATE_CHAIN[1:] and hi in GATE_CHAIN[1:]
                    and interval_a is not None and interval_b is not None
                    and interval_b[0] <= interval_a[1] + EPS):
                overlaps.append(dim)
                violations.append({"env": env, "step": f"{lo}->{hi}", "dim": dim,
                                   "kind": "overlap", "from": interval_a, "to": interval_b})
        if not rising and not falling:
            violations.append({"env": env, "step": f"{lo}->{hi}", "dim": None, "kind": "flat_step"})
        steps.append({"step": f"{lo}->{hi}", "rising": rising, "flat": flat,
                      "falling": falling, "overlaps": overlaps})
    return {"means": means, "intervals": intervals, "steps": steps, "violations": violations}


def check_all(table: Mapping[str, Mapping[str, Mapping[str, Any]]]) -> dict:
    """对每个环境跑闸门链（计入）与原三档链（参照）；返回汇总与判定。"""
    envs, violations, native_notes = {}, [], []
    expected_envs = set(PLAN_TIERS)
    missing_envs = sorted(expected_envs - set(table))
    extra_envs = sorted(set(table) - expected_envs)
    violations.extend({"env": env, "step": "table", "dim": None, "kind": "missing_environment"}
                      for env in missing_envs)
    violations.extend({"env": env, "step": "table", "dim": None, "kind": "unexpected_environment"}
                      for env in extra_envs)
    for env, tiers in table.items():
        for tier in GATE_CHAIN:
            if tier not in tiers:
                violations.append({"env": env, "step": "table", "dim": None,
                                   "kind": "missing_tier", "tier": tier})
        for tier in NATIVE_CHAIN:
            if tier not in tiers:
                violations.append({"env": env, "step": "table", "dim": None,
                                   "kind": "missing_tier", "tier": tier})
        required_dims = set(PLAN_TIERS.get(env, {}).get("hard", {}))
        for tier in GATE_CHAIN:
            if tier in tiers:
                for dim in sorted(required_dims - set(tiers[tier])):
                    violations.append({"env": env, "step": "table", "dim": dim,
                                       "kind": "missing_dimension", "tier": tier})
        gate = check_chain(env, tiers, GATE_CHAIN)
        native = check_chain(env, tiers, NATIVE_CHAIN)
        envs[env] = {"gate": gate, "native": native}
        violations.extend(gate["violations"])
        native_notes.extend(native["violations"])
    return {"envs": envs, "violations": violations, "native_notes": native_notes,
            "verdict": "PASS" if not violations else "FAIL"}


def format_report(result: Mapping, label: str = "TIER_MONOTONE") -> list[str]:
    lines = []
    for env, block in result["envs"].items():
        means = block["gate"]["means"]
        dims = sorted({d for t in means for d in means[t]})
        for dim in dims:
            seq = " → ".join(
                f"{t}:{'—' if means[t].get(dim) is None else f'{means[t][dim]:g}'}" for t in means
            )
            lines.append(f"  {env:18s} {dim:22s} {seq}")
    for v in result["violations"]:
        kind = v["kind"]
        if kind == "decrease":
            detail = f" {v['from']:g}→{v['to']:g}"
        elif kind == "overlap":
            detail = f" {v['from']}∩{v['to']}"
        else:
            detail = f" {v.get('tier', '')}".rstrip()
        lines.append(f"VIOLATION env={v['env']} step={v['step']} dim={v.get('dim')} kind={kind}{detail}")
    for v in result["native_notes"]:
        lines.append(f"NATIVE_NOTE（原三档冻结，不计入）env={v['env']} step={v['step']} dim={v['dim']} kind={v['kind']}")
    lines.append(f"{label}={result['verdict']} envs={len(result['envs'])} violations={len(result['violations'])}")
    return lines


# ── 定稿计划表（NEWTASK_RELEASE_V6_PLAN 第三节；hard 及原三档只作冻结基线）───────────────
# VP 梯度只数放到 target 的次数；所有新值档统一回家，回家段不计入梯度。
def _vpo_place(visit_counts):
    return sum(int(value) for value in visit_counts)


PLAN_TIERS: dict[str, dict[str, dict[str, Any]]] = {
    "BinFill": {
        "easy": {"put_in": [1, 3]}, "medium": {"put_in": [2, 4]}, "hard": {"put_in": [3, 5]},
        "xhard1": {"put_in": 6}, "xhard2": {"put_in": 7}, "xhard3": {"put_in": 8},
        "xhard4": {"put_in": 9},
    },
    "PickXtimes": {
        "easy": {"times": [1, 3], "distractors": 0}, "medium": {"times": [1, 3], "distractors": 0},
        "hard": {"times": [4, 5], "distractors": 0}, "xhard1": {"times": [6, 7], "distractors": 1},
        "xhard2": {"times": [8, 9], "distractors": 2}, "xhard3": {"times": [10, 12], "distractors": 3},
        "xhard4": {"times": [13, 15], "distractors": 3},
    },
    "SwingXtimes": {
        "easy": {"rounds": [1, 3], "distractors": 0}, "medium": {"rounds": [1, 2], "distractors": 0},
        "hard": {"rounds": 3, "distractors": 0}, "xhard1": {"rounds": [4, 5], "distractors": 1},
        "xhard2": {"rounds": [6, 7], "distractors": 2}, "xhard3": {"rounds": [8, 9], "distractors": 3},
        "xhard4": {"rounds": [10, 11], "distractors": 3},
    },
    "PickHighlight": {
        "easy": {"pick": 1, "total": 3}, "medium": {"pick": 2, "total": 4},
        "hard": {"pick": 3, "total": 6}, "xhard1": {"pick": 4, "total": 7},
        "xhard2": {"pick": 5, "total": 8}, "xhard3": {"pick": 6, "total": 9},
        "xhard4": {"pick": 7, "total": 10},
    },
    "VideoUnmask": {
        "easy": {"distractors": 0, "pick": 1}, "medium": {"distractors": 0, "pick": 1},
        "hard": {"distractors": 0, "pick": 2}, "xhard1": {"distractors": 8, "pick": 2},
        "xhard2": {"distractors": 10, "pick": 3}, "xhard3": {"distractors": 13, "pick": 3},
        "xhard4": {"distractors": 15, "pick": 3},
    },
    "ButtonUnmask": {
        "easy": {"distractors": 0, "pick": 1}, "medium": {"distractors": 0, "pick": 1},
        "hard": {"distractors": 0, "pick": 2}, "xhard1": {"distractors": 7, "pick": 2},
        "xhard2": {"distractors": 9, "pick": 3}, "xhard3": {"distractors": 12, "pick": 3},
        "xhard4": {"distractors": 14, "pick": 3},
    },
    "VideoUnmaskSwap": {
        "easy": {"swap": [1, 2], "pick": [1, 2], "outer_distractors": 0},
        "medium": {"swap": [1, 2], "pick": 1, "outer_distractors": 0},
        "hard": {"swap": [2, 3], "pick": 2, "outer_distractors": 0},
        "xhard1": {"swap": [4, 5], "pick": 2, "outer_distractors": 4},
        "xhard2": {"swap": [6, 7], "pick": 3, "outer_distractors": 6},
        "xhard3": {"swap": [8, 9], "pick": 3, "outer_distractors": 8},
        "xhard4": {"swap": [10, 12], "pick": 3, "outer_distractors": 10},
    },
    "ButtonUnmaskSwap": {
        "easy": {"swap": [1, 2], "pick": [1, 2], "outer_distractors": 0},
        "medium": {"swap": [1, 2], "pick": 1, "outer_distractors": 0},
        "hard": {"swap": [2, 3], "pick": 2, "outer_distractors": 0},
        "xhard1": {"swap": 4, "pick": 2, "outer_distractors": 4},
        "xhard2": {"swap": 5, "pick": 3, "outer_distractors": 6},
        "xhard3": {"swap": [6, 7], "pick": 3, "outer_distractors": 8},
        "xhard4": {"swap": [8, 9], "pick": 3, "outer_distractors": 10},
    },
    # hard 的块数是原版聚簇布局（5 轮生成），与新档「块数」不同口径 ⇒ None 跳过
    "VideoRepick": {
        "easy": {"cubes": None, "swap": [1, 2], "repick": [1, 3]},
        "medium": {"cubes": None, "swap": [2, 3], "repick": [1, 3]},
        "hard": {"cubes": None, "swap": 0, "repick": [1, 3]},
        "xhard1": {"cubes": 4, "swap": [3, 4], "repick": 2},
        "xhard2": {"cubes": 5, "swap": [5, 6], "repick": 3},
        "xhard3": {"cubes": 6, "swap": [7, 8], "repick": 4},
        "xhard4": {"cubes": 7, "swap": [9, 12], "repick": [5, 6]},
    },
    "PatternLock": {
        "easy": {"nodes": [2, 4]}, "medium": {"nodes": [3, 5]}, "hard": {"nodes": [4, 8]},
        "xhard1": {"nodes": [9, 12]}, "xhard2": {"nodes": [13, 16]}, "xhard3": {"nodes": [17, 20]},
        "xhard4": {"nodes": [21, 25]},
    },
    "RouteStick": {
        "easy": {"segments": [2, 3]}, "medium": {"segments": [4, 5]}, "hard": {"segments": [4, 7]},
        "xhard1": {"segments": [8, 10]}, "xhard2": {"segments": [11, 13]}, "xhard3": {"segments": [14, 16]},
        "xhard4": {"segments": [17, 21]},
    },
    "VideoPlaceButton": {
        "easy": {"placements": 2}, "medium": {"placements": 2}, "hard": {"placements": 2},
        "xhard1": {"placements": 3}, "xhard2": {"placements": 4}, "xhard3": {"placements": 5},
        "xhard4": {"placements": 6},
    },
    "VideoPlaceOrder": {
        "easy": {"placements": _vpo_place([3])}, "medium": {"placements": _vpo_place([3])},
        "hard": {"placements": _vpo_place([3])},
        "xhard1": {"placements": _vpo_place([2, 3])},
        "xhard2": {"placements": _vpo_place([3, 3])},
        "xhard3": {"placements": _vpo_place([3, 4])},
        "xhard4": {"placements": _vpo_place([4, 4])},
    },
}

GRADIENT_ENVS = tuple(PLAN_TIERS)
XHARD4_EXTRA_TASKS = frozenset({"MoveCube", "InsertPeg", "StopCube"})
V6_SEED_OFFSETS = {"xhard4": 6_000_000, "xhard1": 8_000_000,
                   "xhard2": 10_000_000, "xhard3": 12_000_000}
SEED_RULE_SHAPE = {
    "env_block": 100_000,
    "episode_stride": 100,
    "formula": "offset + env_code*env_block + episode*100 + attempt",
}
DRAFT_HEADER_REQUIRED = {
    "record", "schema", "run_id", "difficulty", "sampling_config", "sampling_config_sha256",
    "source_fingerprint", "runtime", "seed_rule", "recovery_rule", "identity_source", "tasks",
}
DRAFT_ROW_REQUIRED = {
    "record", "task", "difficulty", "episode", "attempt", "seed", "spec", "spec_sha256",
}
SPECS_ROW_REQUIRED = DRAFT_ROW_REQUIRED | {"selected"}
V6_RUNTIME = {
    "obs_mode": "rgb+depth+segmentation",
    "control_mode": "pd_joint_pos",
    "render_mode": "rgb_array",
    "reward_mode": "dense",
}


# ── 从各档 decision（xhard 形态：新档沿用 xhard 机制、只改 xhard 位置的数值）抽维度 ───────────────
def _rng(value):
    if isinstance(value, Mapping) and "low" in value:  # VideoRepick num_repeats_range：{low, high_exclusive}
        return [value["low"], value["high_exclusive"] - 1]
    if isinstance(value, Mapping) and "swap_min" in value:
        return [value["swap_min"], value["swap_max"]]
    return value


def _tier_value(value: Any, tier: str):
    return value.get(tier) if isinstance(value, Mapping) and tier in value else value


def dims_from_xhard_decision(env: str, d: Mapping[str, Any], tier: str = "xhard4") -> dict[str, Any]:
    """从某一档的 decision 抽本环境难度维度；支持完整快照与单档子树。"""
    if "decision" in d and isinstance(d["decision"], Mapping):
        d = d["decision"]
    legacy_key = "xhard" if tier == "xhard4" and "xhard4" not in d else tier
    candidate = d.get(legacy_key, d)
    x = candidate if isinstance(candidate, Mapping) else {}
    if env == "BinFill":
        config = d.get("configs", {}).get(legacy_key, x)
        return {"put_in": config["put_in_numbers"]}
    if env == "PickXtimes":
        return {"times": _tier_value(d["number_range"], tier),
                "distractors": len(x["distractor"]["colors"])}
    if env == "SwingXtimes":
        return {"rounds": _tier_value(d["number_range"], tier),
                "distractors": len(x["distractor"]["colors"])}
    if env == "PickHighlight":
        pick = _tier_value(d["highlight_count"], tier)
        total = _tier_value(d["spawn_count"], tier)
        return {"pick": pick, "total": total}
    if env in ("VideoUnmask", "ButtonUnmask"):
        return {"distractors": x["distractor"]["count"], "pick": _tier_value(d["pick_count"], tier)}
    if env in ("VideoUnmaskSwap", "ButtonUnmaskSwap"):
        return {"swap": _tier_value(d["swap_count_range"], tier),
                "pick": _tier_value(d["pick_count_range"], tier),
                "outer_distractors": x["distractor"]["count"]}
    if env == "VideoRepick":
        return {"cubes": x["layout"]["cube_count"], "swap": _rng(_tier_value(d["swap"], tier)),
                "repick": _rng(_tier_value(d["num_repeats_range"], tier))}
    if env == "PatternLock":
        return {"nodes": _tier_value(d["path_length_range"], tier)}
    if env == "RouteStick":
        return {"segments": x["segment_count_range"]}
    if env in ("VideoPlaceButton", "VideoPlaceOrder"):
        if env == "VideoPlaceButton":
            k = int(x["demo_object_count"])
            return {"placements": 2 * k + int(x.get("extra_place_before", 0))
                    + int(x.get("extra_place_after", 0))}
        if "visit_counts" in x:
            return {"placements": _vpo_place(x["visit_counts"])}
        k = int(x["demo_object_count"])
        visit_range = x.get("visit_count_range", [2, 4])
        if isinstance(visit_range, Mapping):
            visit_range = [visit_range["low"], visit_range["high"]]
        return {"placements": k * value_mean(visit_range)}
    raise KeyError(f"未登记难度维度的环境：{env}")


def tiers_from_decisions(env: str, decisions: Mapping[str, Mapping[str, Any]],
                         base: Mapping[str, Mapping[str, Any]] | None = None) -> dict[str, dict[str, Any]]:
    """``decisions``：四个新值档名 → 完整 decision 或单档子树；原三档沿用计划表。"""
    base = PLAN_TIERS[env] if base is None else base
    out = {t: dict(base[t]) for t in NATIVE_CHAIN if t in base}
    for tier in NEWVALUE_TIERS:
        if tier not in decisions:
            raise ValueError(f"{env} decision 缺少新值档 {tier}")
        out[tier] = dims_from_xhard_decision(env, decisions[tier], tier=tier)
    return out


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _has_tier_key(value: Any, tier: str) -> bool:
    if isinstance(value, Mapping):
        return tier in value or any(_has_tier_key(child, tier) for child in value.values())
    if isinstance(value, list):
        return any(_has_tier_key(child, tier) for child in value)
    return False


def _required(mapping: Mapping[str, Any], key: str, where: str) -> Any:
    if key not in mapping:
        raise ValueError(f"{where} 缺字段 {key}")
    return mapping[key]


def _integer(value: Any, where: str) -> int:
    if isinstance(value, Mapping):
        if type(value.get("actual")) is int:
            value = value["actual"]
        elif type(value.get("placed")) is int:
            value = value["placed"]
        else:
            raise ValueError(f"{where} 没有实际整数值")
    if type(value) is not int or value < 0:
        raise ValueError(f"{where} 必须是非负整数")
    return value


def _distractor_placed(objects: Mapping[str, Any], where: str) -> int:
    distractors = _required(objects, "distractors", where)
    if not isinstance(distractors, Mapping):
        raise ValueError(f"{where}.distractors 必须是对象")
    if type(distractors.get("placed")) is int:
        return _integer(distractors["placed"], f"{where}.distractors.placed")
    if type(distractors.get("requested")) is int:
        return _integer(distractors["requested"], f"{where}.distractors.requested")
    raise ValueError(f"{where}.distractors 缺少 placed/requested 计数")


def dimensions_from_reset_spec(task: str, spec: Mapping[str, Any]) -> dict[str, int]:
    """从 v4_specs reset 后封存的 EpisodeSpec 取实际梯度值，不读计划表或配置默认值。"""
    objects = spec.get("objects") or {}
    actions = spec.get("actions") or {}
    if not isinstance(objects, Mapping) or not isinstance(actions, Mapping):
        raise ValueError(f"{task} spec.objects/actions 必须是对象")
    where = f"{task}.spec"
    if task == "BinFill":
        numbers = _required(objects, "target_numbers", where)
        if not isinstance(numbers, list) or not numbers:
            raise ValueError(f"{where}.objects.target_numbers 必须是非空数组")
        return {"put_in": sum(_integer(value, f"{where}.objects.target_numbers") for value in numbers)}
    if task in ("PickXtimes", "SwingXtimes"):
        count = "times" if task == "PickXtimes" else "rounds"
        return {count: _integer(_required(objects, "num_repeats", where), f"{where}.objects.num_repeats"),
                "distractors": _integer(_required(objects, "distractor_count", where),
                                        f"{where}.objects.distractor_count")}
    if task == "PickHighlight":
        return {"pick": _integer(_required(objects, "highlight_count", where), f"{where}.objects.highlight_count"),
                "total": _integer(_required(objects, "n_cubes_spawned", where),
                                  f"{where}.objects.n_cubes_spawned")}
    if task in ("VideoUnmask", "ButtonUnmask"):
        return {"distractors": _distractor_placed(objects, where),
                "pick": _integer(_required(objects, "n_picks", where), f"{where}.objects.n_picks")}
    if task in ("VideoUnmaskSwap", "ButtonUnmaskSwap"):
        return {"swap": _integer(_required(objects, "n_swaps", where), f"{where}.objects.n_swaps"),
                "pick": _integer(_required(objects, "n_picks", where), f"{where}.objects.n_picks"),
                "outer_distractors": _distractor_placed(objects, where)}
    if task == "VideoRepick":
        cube_count = _integer(_required(objects, "cube_count", where), f"{where}.objects.cube_count")
        return {"cubes": cube_count,
                "swap": _integer(_required(objects, "n_swaps", where), f"{where}.objects.n_swaps"),
                "repick": _integer(_required(objects, "num_repeats", where), f"{where}.objects.num_repeats")}
    if task == "PatternLock":
        nodes = _required(actions, "path_nodes", where)
        if not isinstance(nodes, list):
            raise ValueError(f"{where}.actions.path_nodes 必须是数组")
        return {"nodes": len(nodes)}
    if task == "RouteStick":
        return {"segments": _integer(_required(objects, "L", where), f"{where}.objects.L")}
    if task == "VideoPlaceButton":
        return {"placements": _integer(_required(actions, "target_placement_count", where),
                                       f"{where}.actions.target_placement_count")}
    if task == "VideoPlaceOrder":
        count = actions.get("target_placement_count")
        if count is None:
            visits = objects.get("visit_counts_by_object", objects.get("num_targets_by_object"))
            if isinstance(visits, Mapping):
                visits = [visits[key] for key in sorted(visits, key=lambda item: int(item))]
            if isinstance(visits, list):
                count = sum(_integer(value, f"{where}.objects.visit_counts_by_object") for value in visits)
        if count is None:
            raise ValueError(f"{where} 缺少实际 visit_counts/target_placement_count")
        return {"placements": _integer(count, f"{where}.actions.target_placement_count")}
    raise KeyError(f"未登记的梯度环境：{task}")


def _validate_v4_header(header: Mapping[str, Any], path: Path) -> tuple[str, str, str, set[str]]:
    missing = DRAFT_HEADER_REQUIRED - header.keys()
    if missing:
        raise ValueError(f"{path} header 缺字段 {sorted(missing)}")
    if header["record"] != "header" or header["schema"] not in {"v4-drafts/1", "v4-specs/1"}:
        raise ValueError(f"{path} 不是 v4_specs draw/freeze 文件")
    tier = header["difficulty"]
    if tier not in NEWVALUE_TIERS:
        raise ValueError(f"{path} header difficulty={tier!r} 不属于 V6 新值四档")
    tasks = header["tasks"]
    expected_tasks = (set(GRADIENT_ENVS) | XHARD4_EXTRA_TASKS) if tier == "xhard4" else set(GRADIENT_ENVS)
    if (not isinstance(tasks, list) or len(tasks) != len(expected_tasks)
            or set(tasks) != expected_tasks):
        expected_count = len(expected_tasks)
        raise ValueError(f"{path} {tier} header.tasks 必须恰含 {expected_count} 个环境")
    if not isinstance(header["sampling_config"], Mapping):
        raise ValueError(f"{path} header.sampling_config 必须是对象")
    if set(header["sampling_config"]) != expected_tasks:
        raise ValueError(f"{path} header.sampling_config 与 {tier} 的任务集合不符")
    for task in expected_tasks:
        task_block = header["sampling_config"][task]
        decision = task_block.get("decision") if isinstance(task_block, Mapping) else None
        if not isinstance(decision, Mapping) or not _has_tier_key(decision, tier):
            raise ValueError(f"{path} sampling_config[{task}].decision 树中缺少 {tier}")
    if header["sampling_config_sha256"] != _canonical_sha256(header["sampling_config"]):
        raise ValueError(f"{path} header.sampling_config_sha256 不匹配")
    expected_seed_rule = {
        **SEED_RULE_SHAPE,
        "offset": V6_SEED_OFFSETS[tier],
    }
    if header["seed_rule"] != expected_seed_rule:
        raise ValueError(f"{path} header.seed_rule 与 {tier} 的 V6 规则不符")
    if header["runtime"] != V6_RUNTIME or header["identity_source"] != "formula":
        raise ValueError(f"{path} header runtime/identity_source 与 v4_specs 口径不符")
    release_fingerprint = _canonical_sha256({
        "source_fingerprint": header["source_fingerprint"],
        "runtime": header["runtime"],
        "recovery_rule": header["recovery_rule"],
    })
    gradient_config_fingerprint = _canonical_sha256(
        {task: header["sampling_config"][task] for task in GRADIENT_ENVS}
    )
    return tier, release_fingerprint, gradient_config_fingerprint, expected_tasks


def _seed_env_code(task: str) -> int:
    scripts_dir = str(REPO_ROOT / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    from seed_layout import env_code
    return int(env_code(task))


def _read_v4_reset_file(path: Path) -> tuple[str, str, str, set[str], list[dict[str, Any]], dict[str, int], set[str]]:
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines:
        raise ValueError(f"{path} 为空")
    records = [json.loads(line) for line in lines]
    if not isinstance(records[0], Mapping):
        raise ValueError(f"{path} header 不是对象")
    tier, release_fingerprint, gradient_config_fingerprint, header_tasks = _validate_v4_header(records[0], path)
    failures = {task: 0 for task in header_tasks}
    valid_rows = []
    seen_tasks = set()
    for index, row in enumerate(records[1:], start=2):
        if not isinstance(row, Mapping):
            raise ValueError(f"{path} 第{index}行不是对象")
        required = DRAFT_ROW_REQUIRED if row.get("record") == "draft" else SPECS_ROW_REQUIRED
        missing = required - row.keys()
        if missing:
            raise ValueError(f"{path} 第{index}行缺字段 {sorted(missing)}")
        if row["record"] not in {"draft", "spec"}:
            raise ValueError(f"{path} 第{index}行 record 非 draft/spec")
        if row["difficulty"] != tier or row["task"] not in header_tasks:
            raise ValueError(f"{path} 第{index}行档位/任务与 header 不符")
        seen_tasks.add(row["task"])
        episode, attempt, seed = row["episode"], row["attempt"], row["seed"]
        if any(type(value) is not int or value < 0 for value in (episode, attempt, seed)):
            raise ValueError(f"{path} 第{index}行 episode/attempt/seed 非法")
        expected_seed = (V6_SEED_OFFSETS[tier] + _seed_env_code(row["task"]) * 100_000
                         + episode * 100 + attempt)
        if seed != expected_seed:
            raise ValueError(f"{path} 第{index}行 seed 与 V6 公式不符")
        if row["record"] == "draft":
            if type(row.get("reset_ok")) is not bool:
                raise ValueError(f"{path} 第{index}行 reset_ok 必须是 bool")
            if not row["reset_ok"]:
                failures[row["task"]] += 1
                continue
        spec = row["spec"]
        if not isinstance(spec, Mapping) or row["spec_sha256"] != _canonical_sha256(spec):
            raise ValueError(f"{path} 第{index}行 reset spec 缺失或散列不符")
        identity = spec.get("identity")
        if (not isinstance(identity, Mapping) or identity.get("task") != row["task"]
                or identity.get("difficulty") != tier or identity.get("episode") != episode
                or identity.get("seed") != seed or spec.get("spec_kind") != "native-newvalue/2"):
            raise ValueError(f"{path} 第{index}行 spec identity/spec_kind 不符")
        valid_rows.append({"task": row["task"], "episode": episode, "spec": spec})
    return tier, release_fingerprint, gradient_config_fingerprint, header_tasks, valid_rows, failures, seen_tasks


def check_reset_drafts(paths: list[str | Path], samples: int = 200,
                       out_path: str | Path | None = None) -> dict:
    """汇总四份 v4_specs draw/freeze 真实 reset 样本并执行完整 TIER_MONOTONE 闸门。"""
    if samples <= 0:
        raise ValueError("samples 必须为正数")
    cell_rows = {(env, tier): {} for env in GRADIENT_ENVS for tier in NEWVALUE_TIERS}
    cell_failures = {(env, tier): 0 for env in GRADIENT_ENVS for tier in NEWVALUE_TIERS}
    file_hashes, input_errors, tiers_seen = [], [], set()
    source_fingerprints, gradient_config_fingerprints = set(), set()
    xhard4_extra_validation = {task: {"valid_success_specs": 0, "reset_failures": 0}
                               for task in sorted(XHARD4_EXTRA_TASKS)}
    for raw_path in paths:
        path = Path(raw_path).resolve()
        try:
            tier, fingerprint, config_fingerprint, header_tasks, rows, failures, seen_tasks = _read_v4_reset_file(path)
        except Exception as exc:
            input_errors.append({"path": str(path), "error": f"{type(exc).__name__}: {exc}"})
            continue
        if tier in tiers_seen:
            input_errors.append({"path": str(path), "error": f"重复档位文件：{tier}"})
            continue
        tiers_seen.add(tier)
        source_fingerprints.add(fingerprint)
        gradient_config_fingerprints.add(config_fingerprint)
        file_hashes.append({"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                            "tier": tier})
        for env in GRADIENT_ENVS:
            cell_failures[(env, tier)] = failures.get(env, 0)
        if tier == "xhard4":
            for task in XHARD4_EXTRA_TASKS:
                xhard4_extra_validation[task]["reset_failures"] = failures.get(task, 0)
                if task not in seen_tasks:
                    input_errors.append({"path": str(path), "error":
                                         f"xhard4 非梯度任务 {task} 缺少 reset 尝试行"})
        for row in rows:
            if row["task"] not in GRADIENT_ENVS:
                if tier == "xhard4" and row["task"] in XHARD4_EXTRA_TASKS:
                    xhard4_extra_validation[row["task"]]["valid_success_specs"] += 1
                continue
            key = (row["task"], tier)
            episode = row["episode"]
            target = cell_rows[key]
            if episode in target:
                input_errors.append({"path": str(path), "error": f"{key} 重复成功 episode={episode}"})
                continue
            try:
                target[episode] = dimensions_from_reset_spec(row["task"], row["spec"])
            except Exception as exc:
                input_errors.append({"path": str(path), "error":
                                     f"{row['task']}/{tier}/episode_{episode}: {type(exc).__name__}: {exc}"})
    missing_tiers = sorted(set(NEWVALUE_TIERS) - tiers_seen)
    if len(paths) != len(NEWVALUE_TIERS):
        input_errors.append({"path": "", "error": f"需要四份档位文件，收到 {len(paths)} 份"})
    if len(source_fingerprints) > 1:
        input_errors.append({"path": "", "error": "四个档位文件的配置／源码／运行指纹不一致"})
    if len(gradient_config_fingerprints) > 1:
        input_errors.append({"path": "", "error": "四个档位文件的13个梯度环境 sampling_config 不一致"})

    table = copy.deepcopy(PLAN_TIERS)
    coverage = {}
    shortfalls = []
    observed_samples = {}
    for env in GRADIENT_ENVS:
        for tier in NEWVALUE_TIERS:
            key = (env, tier)
            rows = cell_rows[key]
            required_episodes = list(range(samples))
            available_episodes = sorted(episode for episode in rows if episode < samples)
            missing_episodes = sorted(set(required_episodes) - set(available_episodes))
            dims = set(PLAN_TIERS[env][tier])
            used_values: dict[str, list[int]] = {}
            if len(available_episodes) >= samples:
                chosen = available_episodes[:samples]
                for dim in dims:
                    used_values[dim] = [rows[episode][dim] for episode in chosen]
                    table[env][tier][dim] = {"samples": used_values[dim]}
            else:
                for dim in dims:
                    used_values[dim] = [rows[episode][dim] for episode in available_episodes]
                    table[env][tier][dim] = {"samples": used_values[dim]} if used_values[dim] else None
            observed_samples[f"{env}/{tier}"] = used_values
            coverage[f"{env}/{tier}"] = {
                "required": samples,
                "valid_successes": len(rows),
                "episodes_used": available_episodes[:samples],
                "missing_episodes": missing_episodes,
                "reset_failures": cell_failures[key],
            }
            if missing_episodes:
                shortfalls.append({"env": env, "tier": tier, "required": samples,
                                   "available": len(available_episodes),
                                   "missing_episodes": missing_episodes[:20]})
    result = check_all(table)
    for missing in shortfalls:
        result["violations"].append({"env": missing["env"], "step": "reset-coverage",
                                     "dim": None, "kind": "sample_shortfall",
                                     "tier": missing["tier"], "available": missing["available"],
                                     "required": missing["required"]})
    for error in input_errors:
        result["violations"].append({"env": "input", "step": "v4_specs", "dim": None,
                                     "kind": "invalid_reset_input", **error})
    if result["violations"]:
        result["verdict"] = "FAIL"
    report = {
        "schema": "v6-tier-reset-monotone/1",
        "sample_source": "v4_specs draw/freeze EpisodeSpec",
        "samples_per_cell": samples,
        "expected_cells": len(GRADIENT_ENVS) * len(NEWVALUE_TIERS),
        "covered_cells": sum(not value["missing_episodes"] for value in coverage.values()),
        "missing_tiers": missing_tiers,
        "source_files": file_hashes,
        "xhard4_non_gradient_validation": xhard4_extra_validation,
        "coverage": coverage,
        "samples": observed_samples,
        "input_errors": input_errors,
        "check": result,
    }
    if out_path is not None:
        output = Path(out_path).resolve()
        if not output.is_relative_to(REPO_ROOT):
            raise ValueError(f"reset验收报告必须保存在仓库内：{output}")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                          encoding="utf-8")
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--json", action="store_true", help="额外打印逐档均值 JSON")
    parser.add_argument("--reset-all", action="store_true",
                        help="用四份 v4_specs draw/freeze 文件验证13环境×4档的真实reset样本")
    parser.add_argument("--drafts", action="append", default=[],
                        help="一个 V6 档位的 v4_specs drafts.jsonl/specs.jsonl；须重复提供四次")
    parser.add_argument("--samples", type=int, default=200, help="每个环境/档位所需成功reset数，默认200")
    parser.add_argument("--out", help="reset闸门 JSON 报告路径，必须位于仓库内")
    args = parser.parse_args(argv)
    if args.reset_all:
        if len(args.drafts) != len(NEWVALUE_TIERS):
            parser.error("--reset-all 必须提供四份 --drafts 文件，每档一份")
        if not args.out:
            parser.error("--reset-all 必须提供 --out")
        for draft in args.drafts:
            if not Path(draft).resolve().is_relative_to(REPO_ROOT):
                parser.error(f"drafts 输入必须位于仓库内：{draft}")
        report = check_reset_drafts(args.drafts, args.samples, args.out)
        result = report["check"]
        print(f"RESET_COVERAGE cells={report['covered_cells']}/{report['expected_cells']} "
              f"samples_per_cell={args.samples} missing_tiers={report['missing_tiers']} out={args.out}")
    elif args.drafts:
        parser.error("--drafts 只能与 --reset-all 一起使用")
    else:
        result = check_all(PLAN_TIERS)
    for line in format_report(result, label="TIER_MONOTONE" if args.reset_all else "TIER_PLAN_TABLE"):
        print(line)
    if args.json:
        print(json.dumps({e: b["gate"]["means"] for e, b in result["envs"].items()}, ensure_ascii=False))
    return 0 if result["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
