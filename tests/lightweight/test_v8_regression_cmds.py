#!/usr/bin/env python3
"""轻量测试：v8 对拍守卫（1001 方案第一部分 §3、第二部分 §2.3；子代理 S2-C）。

纯 CPU 合成夹具，不起仿真：在 tmp_path 里写 /4 规格根（``<root>/<tier>/specs.jsonl``，经 ``hard_specs`` 真签名）、
最小 h5（``timestep_*`` + ``info/is_video_demo``）与 ``delivery.json``（schema ``v8-delivery/1``），走「写 JSON → 读
JSON → 守卫」往返，覆盖：

* ``hard_regression.py delivery-set``：完整 43 格根、冒烟 7 格根、分片子集根三种格表各一次 PASS；判定行计数键（含零值）
  显式出现在判定行与 ``--out`` JSON 里；相等比较（少一局即 FAIL）、seed 跨档相交、``layout_parent`` 非空、跨档照抄
  布局（逐叶子比较：剔除恒定叶子后任一浮点叶子逐位相等，或 PatternLock 路径 ≥9 节点前缀相同）各自判 FAIL；用 v7
  包内派生规格证明 13 个跨档任务都抓得出共享布局、同档独立抽样不误报；坏文件／备用耗尽不崩溃、照常打印判定行；
* ``tier-values``：三种根 PASS（完整根 ``tasks=14 cells=41``）、区间任务逐格直方图、改值即 FAIL；
* ``step-headroom``（v8）：``--pool`` 数 exec_over_cap 递补候选、xhard0 按 1300 单独查、超 1600／计数键缺失／
  过滤数与 delivery.json 不符即 FAIL；v7 清单仍分派到旧判据；
* ``hard_parity.py compare --tier v8``：先核分母「冻结交付集 = delivery.json = H = H2」，缺失／多余／重复／空集即
  FAIL；逐身份五个互斥终态（byte_equal／noise／h2_fail／flipped／structural）计数合计 = compared；
* ``eval-smoke`` 的每任务局数按格表推出（v8 62／62／62／32／32／92，换包前 v7 92／32）、``reset-replay`` 的
  ``delivery_index`` 在 /4 根上按 ``V8_TIERS`` 读。

    uv run --no-sync python -m pytest tests/lightweight/test_v8_regression_cmds.py -q
"""

from __future__ import annotations

import copy
import json
import re
import sys
import types
from pathlib import Path

import h5py
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.parity import hard_parity as H  # noqa: E402
from scripts.parity import hard_regression as R  # noqa: E402
from tests._shared import v7_tier_values as TV  # noqa: E402

HS = H.hard_specs_light()

SMOKE = "smoke"
#: 分片子集：PickXtimes 三档 + MoveCube／InsertPeg 的 xhard4（局数取 V8_CELLS 原值）
SHARD_CELLS = {key: HS.V8_CELLS[key] for key in (
    ("PickXtimes", "xhard1"), ("PickXtimes", "xhard2"), ("PickXtimes", "xhard3"),
    ("MoveCube", "xhard4"), ("InsertPeg", "xhard4"))}
TOL = {"action_max_rad": 0.01, "state_max": 0.01, "image_mad": 2.0, "frames_max": 5}


def _cells(kind) -> dict[tuple[str, str], int]:
    if kind == "full":
        return dict(HS.V8_CELLS)
    if kind == SMOKE:
        return dict(H.V8_SMOKE_CELLS)
    return dict(SHARD_CELLS)


def _cells_arg(kind, tmp_path: Path) -> str:
    if kind in ("full", SMOKE):
        return kind
    path = tmp_path / "shard-cells.json"
    path.write_text(json.dumps({f"{t}/{tier}": n for (t, tier), n in SHARD_CELLS.items()}))
    return str(path)


# ── 合成 h5 ────────────────────────────────────────────────────────────


def write_h5(path: Path, seed: int, demo: int = 2, exec_steps: int = 3, shift: float = 0.0) -> Path:
    """最小 h5：``demo`` 帧演示（``info/is_video_demo`` 为真）+ ``exec_steps`` 步执行；带 compare 所需的 setup 与观测。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "w") as f:
        ep = f.create_group("episode_0")
        setup = ep.create_group("setup")
        setup["seed"] = seed
        setup["difficulty"] = b"xhard1"
        setup["task_goal"] = np.array([b"goal"])
        for i in range(demo + exec_steps):
            t = ep.create_group(f"timestep_{i}")
            t["info/is_video_demo"] = i < demo
            t["action/joint_action"] = np.full(8, float(i) + (shift if i >= 2 else 0.0))
            t["obs/joint_state"] = np.zeros(7, dtype=np.float32)
            t["obs/gripper_state"] = np.zeros(2, dtype=np.float32)
            t["obs/front_rgb"] = np.zeros((2, 2, 3), dtype=np.uint8)
            t["obs/wrist_rgb"] = np.zeros((2, 2, 3), dtype=np.uint8)
    return path


# ── 合成 /4 规格根 ─────────────────────────────────────────────────────


def _value(want, cand: int) -> int:
    """表 1 取值：定值原样；区间按候选号在区间内轮转（直方图非单点）。"""
    if isinstance(want, tuple):
        return want[0] + cand % (want[1] - want[0] + 1)
    return want


def make_spec(task: str, tier: str, cand: int) -> dict:
    """按表 1 合成一局 reset 后规格：取值字段与 v7 规格样例同路径；位置类取值按 (档, 候选) 各不相同。"""
    want = {dim: _value(v, cand) for dim, v in R.V8_TIER_TABLE.get(task, {}).get(tier, {}).items()}
    ti = HS.V8_TIERS.index(tier)
    spec = {"spec_kind": "native-newvalue/2", "task": task, "objects": {}, "actions": {},
            "layout": {"button_xy": [round(0.1 * ti + 0.001 * cand + 0.0003, 6), -0.25], "cube_count": 3,
                       # 跨行恒定的浮点叶子（配置常量）：逐叶子比较须先剔除，不得误报
                       "cube_min_center_dist": 0.05, "goal_xy": [0.12, -0.08]}}
    o, a = spec["objects"], spec["actions"]
    if task in ("PickXtimes", "SwingXtimes"):
        o["num_repeats"] = want["times" if task == "PickXtimes" else "rounds"]
        o["distractor_count"] = {"actual": want["distractors"], "requested": want["distractors"]}
    elif task == "StopCube":
        a.update(stop_time=want["stop_time"], move_interval=want["move_interval"])
    elif task in ("VideoUnmask", "ButtonUnmask"):
        o["n_picks"] = want["pick"]
        o["distractors"] = {"placed": want["distractor_bins"], "requested": want["distractor_bins"],
                            "cube_count": want["distractor_cubes"]}
    elif task in ("VideoUnmaskSwap", "ButtonUnmaskSwap"):
        o.update(n_swaps=want["swap"], n_picks=want["pick"], distractors={"placed": want["outer"], "requested": want["outer"]})
    elif task == "BinFill":
        o["target_numbers"] = [want["put_in"] - 2, 1, 1]
    elif task == "VideoPlaceButton":
        a["target_placement_count"] = want["placements"]
    elif task == "VideoPlaceOrder":
        o["visit_counts_by_object"] = [want["visits"] - 2, 2]
    elif task == "PickHighlight":
        o.update(highlight_count=want["pick"], n_cubes_spawned=want["total"])
    elif task == "VideoRepick":
        o.update(cube_count={"actual": want["cubes"], "requested": want["cubes"]}, n_swaps=want["swap"],
                 num_repeats=want["repick"])
    elif task == "RouteStick":
        o["L"] = want["segments"]
        a["nodes"] = [ti * 1000 + cand * 10 + k for k in range(want["segments"] + 1)]
    elif task == "PatternLock":
        del spec["layout"]  # 真实 PatternLock 规格没有 layout，只有 path_nodes
        a["path_nodes"] = [ti * 1000 + cand * 10 + k for k in range(want["nodes"])]
    return spec


def build_tier(tier: str, quotas: dict[str, int], *, backfill: bool, h5_root: Path | None) -> tuple[dict, list[dict]]:
    """一档 /4：每任务候选 ``quota + 2``；``backfill`` 时候选 0 记 exec_over_cap 失败、候选 quota 递补为 selected。"""
    rule = HS.seed_rule_for(tier, "v8")
    rows = []
    for task, quota in quotas.items():
        for cand in range(quota + 2):
            spec = make_spec(task, tier, cand)
            initial = cand < quota
            selected = (initial and not (backfill and cand == 0)) or (backfill and cand == quota)
            seed = HS.seed_for(task, cand, 0, rule)
            rollout = None
            if backfill and cand == 0:
                rollout = {"status": "failed", "error_type": "exec_over_cap", "exec_steps": 1700, "round": 0}
            elif selected:
                rollout = {"status": "ok", "exec_steps": 3, "round": 0, "frames": 5,
                           "env_module": f"robomme_hard.robomme_env.{task}"}
                if h5_root is not None:
                    path = write_h5(h5_root / "episodes" / tier / f"{task}_episode_{cand}" / "hdf5_files" / "ep.h5", seed)
                    rollout.update(h5_path=str(path), h5_sha256=H.sha256_file(path))
                else:
                    rollout["h5_sha256"] = f"{tier}-{task}-{cand}"
            rows.append({"record": "spec", "task": task, "tier": tier, "candidate": cand, "episode": cand,
                         "seed": seed, "attempt": 0, "spec": spec, "spec_sha256": HS.spec_sha256(spec),
                         "selected": selected, "tried": rollout is not None, "initial_selected": initial,
                         "rollout": rollout, "layout_parent": None})
    sampling = {t: {"decision": {"k": t}, "native": {}} for t in quotas}
    header = {
        "record": "header", "schema": HS.SCHEMA_V8, "difficulty": tier, "tasks": list(quotas),
        "per_env": {t: q + 2 for t, q in quotas.items()}, "runtime": dict(HS.RUNTIME), "seed_rule": rule,
        "select_rule": {t: list(range(q)) for t, q in quotas.items()},
        "sampling_config": sampling, "sampling_config_sha256": HS.digest(sampling),
        "recovery_rule": {"rule": "off"}, "identity_source": "formula", "layout_rule": {"mode": "independent"},
        "exec_cap": HS.V8_EXEC_CAP, "delivery_per_cell": dict(quotas),
        "run_id": f"v8-fixture-{tier}", "draw_stats": {}, "provenance": {},
    }
    return resign(header, rows), rows


def resign(header: dict, rows: list[dict]) -> dict:
    header = dict(header)
    header["identity_sha256"] = HS.identity_sha256(header, rows)
    header["delivery_sha256"] = HS.delivery_sha256(rows)
    return header


def write_tier(root: Path, header: dict, rows: list[dict]) -> None:
    path = root / header["difficulty"] / "specs.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(HS.canonical_json(r) + "\n" for r in (header, *rows)), encoding="utf-8")


def build_root(root: Path, cells: dict, *, backfill: bool = False, h5_root: Path | None = None) -> Path:
    by_tier: dict[str, dict[str, int]] = {}
    for (task, tier), n in cells.items():
        by_tier.setdefault(tier, {})[task] = n
    for tier, quotas in by_tier.items():
        write_tier(root, *build_tier(tier, quotas, backfill=backfill, h5_root=h5_root))
    return root


def edit_root(root: Path, tier: str, fn) -> None:
    """改一档文件里的行（``fn(rows)`` 原地改），规格散列与 header 签名重算（模拟「重签后仍违反守卫」）。"""
    path = root / tier / "specs.jsonl"
    records = [json.loads(t) for t in path.read_text().splitlines()]
    header, rows = records[0], records[1:]
    fn(rows)
    for row in rows:
        row["spec_sha256"] = HS.spec_sha256(row["spec"])
    write_tier(root, resign(header, rows), rows)


def all_rows(root: Path) -> list[dict]:
    out = []
    for path in sorted(root.glob("xhard*/specs.jsonl")):
        out += [json.loads(t) for t in path.read_text().splitlines()[1:]]
    return out


def write_delivery(root: Path, out: Path, *, counts: dict | None = None, rows: list[dict] | None = None) -> Path:
    """按 S2-B 契约写 delivery.json：逐局身份 + h5 相对路径 + exec_steps；全局计数键显式写出（含零）。"""
    delivered = [r for r in all_rows(root) if HS.delivered(r)]
    failed = [r for r in all_rows(root) if (r.get("rollout") or {}).get("status") == "failed"]
    over = sum((r["rollout"] or {}).get("error_type") == "exec_over_cap" for r in failed)
    payload = {
        "schema": H.V8_DELIVERY_SCHEMA,
        "counts": counts if counts is not None else {"exec_over_cap": over, "backfills": over, "infra_retries": 0,
                                                     "failed": len(failed)},
        "cells": {}, "rows": rows if rows is not None else [
            {"task": r["task"], "tier": r["tier"], "episode": r["episode"], "seed": r["seed"],
             "candidate": r["candidate"], "path": str(Path(r["rollout"]["h5_path"]).relative_to(out.parent)),
             "h5_sha256": r["rollout"]["h5_sha256"], "exec_steps": r["rollout"]["exec_steps"],
             "env_module": r["rollout"]["env_module"]} for r in delivered],
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1))
    return out


def run(main, argv, capsys) -> tuple[int, str]:
    rc = main([str(a) for a in argv])
    return rc, capsys.readouterr().out


def line(out: str, name: str) -> str:
    hits = [t for t in out.splitlines() if t.startswith(f"{name}=")]
    assert len(hits) == 1, out
    return hits[0]


def kv(text: str) -> dict[str, str]:
    return dict(re.findall(r"(\w+)=(\S+)", text))


# ── 常量与格表 ─────────────────────────────────────────────────────────


def test_表1与测试侧取值表一致():
    """守卫的表 1 与 tests/_shared/v7_tier_values.py（S1-A 钉死的源码取值）在重合维度上逐档相同。"""
    rename = {"PickXtimes": {"times": "number", "distractors": "distractors"},
              "SwingXtimes": {"rounds": "number", "distractors": "distractors"},
              "StopCube": {"stop_time": "stop_time", "move_interval": "move_interval"},
              "VideoUnmask": {"pick": "pick", "distractor_bins": "distractor_count", "distractor_cubes": "distractor_cubes"},
              "ButtonUnmask": {"pick": "pick", "distractor_bins": "distractor_count", "distractor_cubes": "distractor_cubes"},
              "VideoUnmaskSwap": {"swap": "swap", "pick": "pick", "outer": "outer"},
              "ButtonUnmaskSwap": {"swap": "swap", "pick": "pick", "outer": "outer"},
              "VideoRepick": {"cubes": "cube", "swap": "swap", "repick": "repick"},
              "RouteStick": {"segments": "length"}, "PatternLock": {"nodes": "length"},
              "BinFill": {"put_in": "put_in"}, "PickHighlight": {"pick": "pick", "total": "spawn"},
              "VideoPlaceOrder": {"visits": "visits_total"}}
    assert set(R.V8_TIER_TABLE) == set(TV.V7_TIER_VALUES) and len(R.V8_TIER_TABLE) == 14
    for task, dims in rename.items():
        tiers = TV.tiers_for(task)
        for tier, values in R.V8_TIER_TABLE[task].items():
            for mine, theirs in dims.items():
                assert values[mine] == TV.V7_TIER_VALUES[task][theirs][tiers.index(tier)], (task, tier, mine)
    valued = [key for key in HS.V8_CELLS if key[0] in R.V8_TIER_TABLE]
    assert len(valued) == 41 and {k: set(v) for k, v in R.V8_TIER_TABLE.items()} == {
        t: {tier for task, tier in valued if task == t} for t in R.V8_TIER_TABLE}
    # v9：格集合与 V8 相同（只局数不同），表 1 的取值维度逐格照用
    assert {key for key in HS.V9_CELLS if key[0] in R.V8_TIER_TABLE} == set(valued)


def test_格表解析与形状():
    # full 跟随包内 EXPECTED_CELLS（v9 阶段 3b 切换前 V8 1070、切换后 V9 800）；v8full／v9full 不随切换漂移
    assert H.parse_cells("full") == HS.EXPECTED_CELLS
    assert H.parse_cells_versioned("full")[1] == ("v9" if HS.EXPECTED_CELLS == HS.V9_CELLS else "v8")
    assert H.parse_cells_versioned("v8full") == (HS.V8_CELLS, "v8") and sum(HS.V8_CELLS.values()) == 1070
    for name in ("v9full", "v9"):
        assert H.parse_cells_versioned(name) == (HS.V9_CELLS, "v9") and sum(H.parse_cells(name).values()) == 800
    assert H.parse_cells_versioned("v9smoke") == ({("MoveCube", "xhard4"): 1, ("InsertPeg", "xhard4"): 1}, "v9")
    assert H.parse_cells_versioned("v9shard1") == ({("MoveCube", "xhard4"): 50}, "v9")
    # 只能被 V9_CELLS 覆盖的 JSON 子表判 v9（_rollout 的 Task@tier 写法也认）；能被 V8 覆盖的判 v8
    assert H.parse_cells_versioned('{"InsertPeg@xhard4": 50}') == ({("InsertPeg", "xhard4"): 50}, "v9")
    assert H.parse_cells_versioned('{"cells": [{"task": "MoveCube", "tier": "xhard4", "count": 3}]}')[1] == "v8"
    assert H.parse_cells("smoke") == H.V8_SMOKE_CELLS and len(H.V8_SMOKE_CELLS) == 7
    assert H.parse_cells('{"PickXtimes/xhard1": 17, "MoveCube": {"xhard4": 3}}') == {
        ("PickXtimes", "xhard1"): 17, ("MoveCube", "xhard4"): 3}
    assert H.parse_cells('[["StopCube", "xhard5", 1], {"task": "BinFill", "tier": "xhard2", "n": 2}]') == {
        ("StopCube", "xhard5"): 1, ("BinFill", "xhard2"): 2}
    # 跨表混用（VideoUnmask 20 只在 V8 合法、MoveCube 50 只在 V9 合法）也拒
    for bad in ('{"PickXtimes/xhard4": 1}', '{"PickXtimes/xhard1": 18}', '{"BinFill/xhard1": 0}', "{}",
                '{"MoveCube/xhard4": 51}', '{"VideoUnmask/xhard1": 20, "MoveCube/xhard4": 50}'):
        with pytest.raises(H.ParityError):
            H.parse_cells(bad)
    per_tier = [sum(n for (_, t), n in HS.V8_CELLS.items() if t == tier) for tier in HS.V8_TIERS]
    assert H.SHAPES["v8"] == "cells43:" + "+".join(map(str, per_tier)) and per_tier == [411, 411, 128, 100, 20]
    v9_tier = [sum(n for (_, t), n in HS.V9_CELLS.items() if t == tier) for tier in HS.V8_TIERS]
    assert H.SHAPES["v9"] == "cells43:" + "+".join(map(str, v9_tier)) and v9_tier == [272, 272, 92, 144, 20]
    assert H.TIER_NAMES == HS.V8_TIERS and "v7" not in H.TIERS and {"v8", "v9"} <= set(H.TIERS)
    assert H.default_h5_root("v9").parts[-3:] == ("newtask-v9", "parity", "h5")
    assert H.default_h5_root("v8") == H.LOCAL_H5_ROOT and H.default_compare_root("v8") == H.COMPARE_ROOT
    # hard_parity 自带的 v9 具名格表与 _rollout 同值（hard_parity 只用标准库、不 import _rollout）
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "injection-dev"))
    import _rollout  # noqa: PLC0415

    assert H.V9_SMOKE_CELLS == _rollout.V9_SMOKE_CELLS
    assert {k: tuple(v) for k, v in H.V9_SHARD_TASKS.items()} == {k: tuple(v) for k, v in _rollout.V9_SHARD_TASKS.items()}
    for name in ("v9smoke", "v9shard1"):
        assert H.parse_cells(name) == _rollout.resolve_cells(name)
    assert H.LOCAL_H5_ROOT.parts[-3:] == ("newtask-v8", "parity", "h5")


# ── delivery-set ───────────────────────────────────────────────────────

EXPECT_SET = {
    "full": ("V8_DELIVERY_SET=PASS tasks=16 cells=43 total=1070", "V8_SEED_DISJOINT=PASS tasks=16 tier_pairs=48 shared=0",
             "V8_LAYOUT_INDEPENDENT=PASS files=5 delivered=1070 parent_non_null=0 layout_equal_pairs=0"),
    SMOKE: ("V8_DELIVERY_SET=PASS tasks=6 cells=7 total=7", "V8_SEED_DISJOINT=PASS tasks=6 tier_pairs=1 shared=0",
            "V8_LAYOUT_INDEPENDENT=PASS files=4 delivered=7 parent_non_null=0 layout_equal_pairs=0"),
    "shard": ("V8_DELIVERY_SET=PASS tasks=3 cells=5 total=90", "V8_SEED_DISJOINT=PASS tasks=3 tier_pairs=3 shared=0",
              "V8_LAYOUT_INDEPENDENT=PASS files=4 delivered=90 parent_non_null=0 layout_equal_pairs=0"),
}


@pytest.mark.parametrize("kind", ["full", SMOKE, "shard"])
def test_delivery_set三种格表往返(tmp_path, capsys, kind):
    backfill = kind == SMOKE
    root = build_root(tmp_path / "root", _cells(kind), backfill=backfill)
    report = tmp_path / "report.json"
    rc, out = run(R.main, ["delivery-set", "--specs-root", root, "--cells", _cells_arg(kind, tmp_path), "--out", report],
                  capsys)
    assert rc == 0, out
    for want, name in zip(EXPECT_SET[kind], ("V8_DELIVERY_SET", "V8_SEED_DISJOINT", "V8_LAYOUT_INDEPENDENT")):
        assert line(out, name).startswith(want), out
    got = json.loads(report.read_text())
    n_bf = 7 if backfill else 0
    # 计数键显式出现（含零值），判定行与 JSON 一致
    keys = kv(line(out, "V8_DELIVERY_SET"))
    for key, value in {"cell_mismatch": 0, "extra_cells": 0, "selected_not_ok": 0, "delivered_over_cap": 0,
                       "failed": n_bf, "exec_over_cap": n_bf, "backfills": n_bf, "missing_files": 0, "load_errors": 0}.items():
        assert keys[key] == str(value), (key, out)
        if key in got["delivery_set"]:
            assert got["delivery_set"][key] == value
    assert kv(line(out, "V8_LAYOUT_INDEPENDENT"))["mode_bad"] == "0" and kv(line(out, "V8_LAYOUT_INDEPENDENT"))["no_position"] == "0"
    assert got["seed_disjoint"]["shared"] == 0 and got["layout_independent"]["layout_equal_pairs"] == 0
    assert got["delivery_set"]["verdict"] == got["seed_disjoint"]["verdict"] == got["layout_independent"]["verdict"] == "PASS"


def test_delivery_set相等比较_少一局即FAIL(tmp_path, capsys):
    """某格交付 9／10（rollout 失败且未递补）：不是「≤ 即通过」。"""
    root = build_root(tmp_path / "root", H.V8_SMOKE_CELLS | {("StopCube", "xhard2"): 1})

    def drop(rows):
        rows[0]["rollout"] = {"status": "failed", "error_type": "PlanningFailure"}
    edit_root(root, "xhard2", drop)
    cells = json.dumps({f"{t}/{tier}": n for (t, tier), n in (H.V8_SMOKE_CELLS | {("StopCube", "xhard2"): 1}).items()})
    rc, out = run(R.main, ["delivery-set", "--specs-root", root, "--cells", cells], capsys)
    keys = kv(line(out, "V8_DELIVERY_SET"))
    assert rc == 1 and line(out, "V8_DELIVERY_SET").startswith("V8_DELIVERY_SET=FAIL")
    assert keys["total"] == "7" and keys["expected_total"] == "8" and keys["cell_mismatch"] == "1"
    assert keys["selected_not_ok"] == "1" and keys["failed"] == "1" and keys["exec_over_cap"] == "0"
    # 冒烟格表要的格少于根里的档：格表外档的文件不读；格表与 header 任务集合不符 → load_errors
    rc, out = run(R.main, ["delivery-set", "--specs-root", root, "--cells", SMOKE], capsys)
    assert rc == 1 and kv(line(out, "V8_DELIVERY_SET"))["load_errors"] == "1"


def test_delivery_set_seed相交与parent非空与照抄布局(tmp_path, capsys):
    root = build_root(tmp_path / "root", H.V8_SMOKE_CELLS)
    base = {r["task"] + r["tier"] + str(r["candidate"]): r for r in all_rows(root)}

    # ① 照抄布局：StopCube xhard5 的交付局位置取值改成与 xhard1 交付局逐位相同（只改位置，不碰 seed 与标志）
    def copy_layout(rows):
        rows_by = {(r["task"], r["candidate"]): r for r in rows}
        rows_by[("StopCube", 0)]["spec"]["layout"] = copy.deepcopy(base["StopCubexhard10"]["spec"]["layout"])
        rows_by[("StopCube", 0)]["spec"]["layout"]["cube_count"] = 99  # 计数类叶子不同不掩盖照抄
    edit_root(root, "xhard5", copy_layout)
    rc, out = run(R.main, ["delivery-set", "--specs-root", root, "--cells", SMOKE], capsys)
    assert rc == 1 and line(out, "V8_DELIVERY_SET").startswith("V8_DELIVERY_SET=PASS")
    assert line(out, "V8_LAYOUT_INDEPENDENT").startswith(
        "V8_LAYOUT_INDEPENDENT=FAIL files=4 delivered=7 parent_non_null=0 layout_equal_pairs=1")

    # ② layout_parent 非空（/4 校验也会拒绝 → 交付形态同时 FAIL）
    root2 = build_root(tmp_path / "root2", H.V8_SMOKE_CELLS)
    edit_root(root2, "xhard1", lambda rows: rows[0].update(layout_parent={"tier": "xhard4"}))
    rc, out = run(R.main, ["delivery-set", "--specs-root", root2, "--cells", SMOKE], capsys)
    assert rc == 1 and kv(line(out, "V8_LAYOUT_INDEPENDENT"))["parent_non_null"] == "1"
    assert kv(line(out, "V8_DELIVERY_SET"))["load_errors"] == "1"

    # ③ seed 跨档相交：StopCube xhard5 候选 0 的 seed 改成 xhard1 候选 0 的 seed（公式校验也拒）
    root3 = build_root(tmp_path / "root3", H.V8_SMOKE_CELLS)
    first = next(r for r in all_rows(root3) if r["task"] == "StopCube" and r["tier"] == "xhard1" and r["candidate"] == 0)
    edit_root(root3, "xhard5", lambda rows: next(r for r in rows if r["task"] == "StopCube"
                                                 and r["candidate"] == 0).update(seed=first["seed"]))
    rc, out = run(R.main, ["delivery-set", "--specs-root", root3, "--cells", SMOKE], capsys)
    assert rc == 1 and line(out, "V8_SEED_DISJOINT").startswith("V8_SEED_DISJOINT=FAIL tasks=6 tier_pairs=1 shared=1")


def _items(specs: list[tuple[str, int, dict, bool]]):
    return [(tier, {"task": "T", "candidate": cand, "spec": spec}, delivered) for tier, cand, spec, delivered in specs]


def test_逐叶子比较_前缀照抄判出_恒定浮点不误报():
    """F1：低档位置叶子是高档的子集／前缀（v7 式派生）→ 记对；跨行恒定的浮点叶子剔除后独立布局 → 0。"""
    const = {"cube_min_center_dist": 0.05, "goal_xy": [0.1, -0.1]}
    high = {"layout": {**const, "cubes": {"a": [0.31, 0.12], "b": [0.42, -0.07], "c": [0.15, 0.2]}}}
    low = {"layout": {**const, "cubes": {"a": [0.31, 0.12]}}}  # 子集：只放下母布局的第一个方块
    other = {"layout": {**const, "cubes": {"a": [0.29, 0.11]}}}
    hit = R.layout_overlap(_items([("xhard4", 0, high, True), ("xhard1", 0, low, True), ("xhard1", 1, other, True)]))
    assert hit["pairs"] == 1 and "layout.cube_min_center_dist" in hit["constant"] and "layout.goal_xy" in hit["constant"]
    indep = R.layout_overlap(_items([("xhard4", 0, high, True), ("xhard1", 1, other, True)]))
    assert indep["pairs"] == 0 and indep["no_position"] == 0
    # PatternLock 路径：低档是高档 ≥9 节点的前缀 → 记对；只有短前缀（<9）相同不记；整数 actions.nodes 不参与
    path = list(range(21))
    pl = R.layout_overlap(_items([("xhard3", 0, {"actions": {"path_nodes": path}}, True),
                                  ("xhard1", 0, {"actions": {"path_nodes": path[:9]}}, True),
                                  ("xhard2", 0, {"actions": {"path_nodes": path[:5] + [99, 98, 97, 96, 95]}}, True)]))
    assert pl["pairs"] == 1
    rs = R.layout_overlap(_items([("xhard1", 0, {"actions": {"nodes": [0, 2, 4, 2]}, "layout": {"r": 0.11}}, True),
                                  ("xhard2", 0, {"actions": {"nodes": [0, 2, 4, 2]}, "layout": {"r": 0.27}}, True)]))
    assert rs["pairs"] == 0
    # 跨档任务剔除恒定叶子后无可比叶子 → no_position
    flat = R.layout_overlap(_items([("xhard1", 0, {"layout": dict(const)}, True), ("xhard2", 0, {"layout": dict(const)}, True)]))
    assert flat["no_position"] == 2


#: v7 包内规格小样本（v8 阶段 3b 换包后包内已是 /4）：截自 f9ba91eb 的 xhard{1..4}/specs.jsonl，每任务 2 个
#: 四档都交付的候选，行内容照抄、保持母布局派生关系；header 只留少数键（不能走 load_specs）
V7_SAMPLE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "v7_specs_sample"


def test_逐叶子比较抓得出v7共享布局():
    """F1③：v7 规格是母布局派生（低档照抄 xhard4 或其前缀）：13 个跨档任务各自 layout_equal_pairs>0；
    同档不同候选是独立抽样，把每个候选当成单独一档也不误报。换包后改读 v7 冻结小样本 ``V7_SAMPLE_ROOT``。"""
    by_task: dict[str, list] = {}
    for tier in HS.V7_TIERS:
        records = HS.read_jsonl(V7_SAMPLE_ROOT / tier / "specs.jsonl")
        assert records[0]["schema"] == HS.SCHEMA_V7
        for row in records[1:]:
            by_task.setdefault(row["task"], []).append((tier, row, HS.delivered(row)))
    cross = {task: R.layout_overlap(items)["pairs"] for task, items in by_task.items()
             if len({t for t, *_ in items}) > 1}
    assert len(cross) == 13 and all(n > 0 for n in cross.values()), cross
    for task, items in by_task.items():
        for tier in {t for t, *_ in items}:
            solo = [(f"{t}#{r['candidate']}", r, d) for t, r, d in items if t == tier]
            assert R.layout_overlap(solo)["pairs"] == 0, (task, tier)


def test_坏文件与备用耗尽不崩溃(tmp_path, capsys):
    """F4：某格备用候选耗尽（selected 少于期望，load_specs_v8 会抛）→ 逐格判 FAIL；坏 JSON 文件 → load_errors。"""
    root = build_root(tmp_path / "root", H.V8_SMOKE_CELLS)

    def exhaust(rows):
        row = next(r for r in rows if r["task"] == "StopCube")
        row.update(selected=False, rollout={"status": "failed", "error_type": "exec_over_cap", "exec_steps": 1700})
    edit_root(root, "xhard5", exhaust)
    rc, out = run(R.main, ["delivery-set", "--specs-root", root, "--cells", SMOKE], capsys)
    keys = kv(line(out, "V8_DELIVERY_SET"))
    assert rc == 1 and line(out, "V8_DELIVERY_SET").startswith("V8_DELIVERY_SET=FAIL tasks=6 cells=6 total=6")
    assert keys["cell_mismatch"] == "1" and keys["load_errors"] == "1" and keys["exec_over_cap"] == "1"
    assert line(out, "V8_SEED_DISJOINT").startswith("V8_SEED_DISJOINT=PASS")
    (root / "xhard3" / "specs.jsonl").write_text('{"record": "header", oops\n')
    (root / "xhard2" / "specs.jsonl").write_text("")
    rc, out = run(R.main, ["delivery-set", "--specs-root", root, "--cells", SMOKE], capsys)
    assert rc == 1 and int(kv(line(out, "V8_DELIVERY_SET"))["load_errors"]) >= 3
    assert kv(line(out, "V8_LAYOUT_INDEPENDENT"))["load_errors"] == "2"
    rc, out = run(R.main, ["tier-values", "--specs-root", root, "--cells", SMOKE], capsys)
    assert rc == 1 and kv(line(out, "V8_TIER_VALUES"))["missing_files"] == "2"


def test_pool坏文件计数与档目录补档名(tmp_path):
    pool = tmp_path / "pool"
    (pool / "xhard2").mkdir(parents=True)
    (pool / "xhard2" / "specs.jsonl").write_text(
        json.dumps({"record": "header"}) + "\n"
        + json.dumps({"task": "BinFill", "candidate": 3, "rollout": {"status": "failed", "error_type": "exec_over_cap"}}) + "\n")
    (pool / "bad.jsonl").write_text("{not json\n")
    (pool / "results.json").write_text("")
    found, errors = R.pool_scan([pool, tmp_path / "nope"])
    assert found == {("BinFill", "xhard2", "c3")} and len(errors) == 3


def test_specs_tiers局部根只含xhard5也判v8(tmp_path):
    root = build_root(tmp_path / "root", {("SwingXtimes", "xhard5"): 1})
    assert R.specs_tiers(str(root)) == (HS.V8_TIERS, True)


def test_step_headroom_skip_xhard0只出INFO(tmp_path, capsys):
    gen = tmp_path / "gen1"
    root = build_root(gen / "specs-root", H.V8_SMOKE_CELLS, backfill=True, h5_root=gen)
    delivery = write_delivery(root, gen / "delivery.json")
    rc, out = run(R.main, ["step-headroom", "--delivery", delivery, "--pool", root, "--skip-xhard0"], capsys)
    assert rc == 0 and line(out, "V8_STEP_CAP").startswith(
        "V8_STEP_CAP=INFO max=3 cap=1600 over=0 filtered=7 xhard0_max=skipped xhard0_cap=1300")
    assert "PASS" not in out
    (root / "xhard1" / "broken.jsonl").write_text("{x\n")
    rc, out = run(R.main, ["step-headroom", "--delivery", delivery, "--pool", root, "--xhard0", _xhard0_side(tmp_path)],
                  capsys)
    assert rc == 1 and kv(line(out, "V8_STEP_CAP"))["pool_load_errors"] == "1"


# ── tier-values ────────────────────────────────────────────────────────

EXPECT_VALUES = {"full": "V8_TIER_VALUES=PASS tasks=14 cells=41 mismatches=0",
                 SMOKE: "V8_TIER_VALUES=PASS tasks=6 cells=7 mismatches=0",
                 "shard": "V8_TIER_VALUES=PASS tasks=1 cells=3 mismatches=0"}


@pytest.mark.parametrize("kind", ["full", SMOKE, "shard"])
def test_tier_values三种格表往返(tmp_path, capsys, kind):
    root = build_root(tmp_path / "root", _cells(kind), backfill=kind == SMOKE)
    report = tmp_path / "values.json"
    rc, out = run(R.main, ["tier-values", "--specs-root", root, "--cells", _cells_arg(kind, tmp_path), "--out", report],
                  capsys)
    assert rc == 0 and line(out, "V8_TIER_VALUES").startswith(EXPECT_VALUES[kind]), out
    assert kv(line(out, "V8_TIER_VALUES"))["missing_files"] == "0"
    got = json.loads(report.read_text())
    assert got["mismatches"] == 0 and got["verdict"] == "PASS"
    hists = [t for t in out.splitlines() if t.startswith("V8_TIER_LENGTH_HIST=INFO")]
    assert len(hists) == {"full": 6, SMOKE: 2, "shard": 0}[kind]
    if kind == "full":
        # RouteStick xhard1：27 局在 [8, 10] 轮转 → 9／9／9
        assert got["histograms"]["RouteStick/xhard1"] == {"8": 9, "9": 9, "10": 9}
        assert got["histograms"]["PatternLock/xhard3"] == {"16": 9, "17": 9, "18": 8}
        assert "MoveCube/xhard4" not in got["per_cell"] and len(got["per_cell"]) == 41


def test_tier_values改值即FAIL(tmp_path, capsys):
    root = build_root(tmp_path / "root", H.V8_SMOKE_CELLS)
    edit_root(root, "xhard1", lambda rows: next(r for r in rows if r["task"] == "StopCube")["spec"]["actions"].update(stop_time=7))
    edit_root(root, "xhard2", lambda rows: next(r for r in rows if r["task"] == "RouteStick")["spec"]["objects"].update(L=14))
    rc, out = run(R.main, ["tier-values", "--specs-root", root, "--cells", SMOKE], capsys)
    assert rc == 1 and line(out, "V8_TIER_VALUES").startswith("V8_TIER_VALUES=FAIL tasks=6 cells=7 mismatches=2")
    assert "out_of_range=1" in next(t for t in out.splitlines() if "task=RouteStick" in t)


# ── step-headroom（v8）────────────────────────────────────────────────


def _xhard0_side(tmp_path: Path, exec_steps: int = 7) -> Path:
    side = tmp_path / "H-xhard0"
    lines = []
    for i in range(3):
        rel = f"episodes/BinFill_episode_{i}/hdf5_files/x.h5"
        write_h5(side / rel, 100 + i, demo=1, exec_steps=exec_steps + i)
        lines.append({"tier": "hard", "task": "BinFill", "episode": i, "seed": 100 + i, "success": True, "path": rel})
    lines.append({"tier": "hard", "task": "BinFill", "episode": 9, "seed": 109, "success": False, "path": None})
    (side / "identities.jsonl").write_text("".join(json.dumps(x) + "\n" for x in lines))
    return side


@pytest.mark.parametrize("kind", ["full", SMOKE, "shard"])
def test_step_headroom_v8三种根往返(tmp_path, capsys, kind):
    gen = tmp_path / "gen1"
    backfill = kind != "full"
    root = build_root(gen / "specs-root", _cells(kind), backfill=backfill, h5_root=gen)
    delivery = write_delivery(root, gen / "delivery.json")
    report = tmp_path / "steps.json"
    rc, out = run(R.main, ["step-headroom", "--delivery", delivery, "--pool", root, "--xhard0", _xhard0_side(tmp_path),
                           "--out", report], capsys)
    total = sum(_cells(kind).values())
    filtered = len(_cells(kind)) if backfill else 0
    assert rc == 0, out
    assert line(out, "V8_STEP_CAP").startswith(
        f"V8_STEP_CAP=PASS max=3 cap=1600 over=0 filtered={filtered} xhard0_max=9 xhard0_cap=1300 rows={total}"), out
    keys = kv(line(out, "V8_STEP_CAP"))
    assert keys["missing_h5"] == keys["exec_steps_mismatch"] == keys["filtered_mismatch"] == keys["count_keys_absent"] == "0"
    assert keys["xhard0_rows"] == "4" and keys["xhard0_over"] == "0" and keys["filtered_delivery"] == str(filtered)
    got = json.loads(report.read_text())
    assert got["over"] == [] and got["filtered"] == filtered and got["cells"] == len(_cells(kind))


def test_step_headroom_v8各类FAIL(tmp_path, capsys):
    gen = tmp_path / "gen1"
    root = build_root(gen / "specs-root", H.V8_SMOKE_CELLS, backfill=True, h5_root=gen)
    delivery = write_delivery(root, gen / "delivery.json")
    x0 = _xhard0_side(tmp_path)
    # ① 超 1600：重写一局交付 h5 为 1601 执行步（delivery 里的 exec_steps 也跟着写成 1601）
    payload = json.loads(delivery.read_text())
    victim = payload["rows"][0]
    write_h5(gen / victim["path"], victim["seed"], demo=2, exec_steps=1601)
    victim["exec_steps"] = 1601
    delivery.write_text(json.dumps(payload))
    rc, out = run(R.main, ["step-headroom", "--delivery", delivery, "--pool", root, "--xhard0", x0], capsys)
    assert rc == 1 and line(out, "V8_STEP_CAP").startswith("V8_STEP_CAP=FAIL max=1601 cap=1600 over=1")
    # ② 计数键缺失（没有显式写零）且过滤数与候选池不符
    delivery2 = write_delivery(root, gen / "delivery2.json", counts={"exec_over_cap": 0, "backfills": 0, "failed": 0})
    rc, out = run(R.main, ["step-headroom", "--delivery", delivery2, "--pool", root, "--skip-xhard0"], capsys)
    keys = kv(line(out, "V8_STEP_CAP"))
    assert rc == 1 and keys["count_keys_absent"] == "1" and keys["filtered"] == "7" and keys["filtered_mismatch"] == "1"
    assert keys["xhard0_max"] == "skipped"
    # ③ xhard0 超 1300
    rc, out = run(R.main, ["step-headroom", "--delivery", write_delivery(root, gen / "d3.json"), "--pool", root,
                           "--xhard0", _xhard0_side(tmp_path / "x", exec_steps=1301)], capsys)
    assert rc == 1 and kv(line(out, "V8_STEP_CAP"))["xhard0_over"] == "3"
    # ④ 必填参数
    with pytest.raises(SystemExit, match="--pool"):
        R.main(["step-headroom", "--delivery", str(delivery)])
    with pytest.raises(SystemExit, match="--xhard0"):
        R.main(["step-headroom", "--delivery", str(delivery), "--pool", str(root)])


def test_step_headroom按清单形态分派v7(tmp_path, monkeypatch):
    called = []
    monkeypatch.setattr(R, "_step_headroom_v7", lambda args: called.append(args.delivery) or 0)
    v7 = tmp_path / "v7.json"
    v7.write_text(json.dumps({"schema": "v7-delivery/1", "rows": []}))
    assert R.main(["step-headroom", "--delivery", str(v7)]) == 0 and called == [str(v7)]
    v8 = tmp_path / "v8.json"
    v8.write_text(json.dumps({"schema": H.V8_DELIVERY_SCHEMA, "rows": []}))
    assert R.main(["step-headroom", "--delivery", str(v8), "--v7"]) == 0 and len(called) == 2
    other = tmp_path / "x.json"
    other.write_text(json.dumps({"schema": "v9-delivery/1", "rows": []}))
    with pytest.raises(SystemExit, match="未知交付清单"):
        R.main(["step-headroom", "--delivery", str(other)])


def test_pool_over_cap按身份去重(tmp_path):
    root = build_root(tmp_path / "root", H.V8_SMOKE_CELLS, backfill=True)
    rounds = tmp_path / "out" / "_rounds" / "xhard1-0"
    rounds.mkdir(parents=True)
    over = [r for r in all_rows(root) if (r["rollout"] or {}).get("error_type") == "exec_over_cap"]
    rounds.joinpath("results.partial.jsonl").write_text("".join(
        json.dumps({"task": r["task"], "tier": r["tier"], "seed": r["seed"], "error_type": "exec_over_cap"}) + "\n"
        for r in over[:3]) + json.dumps({"task": "X", "tier": "xhard1", "seed": 1, "error_type": "Other"}) + "\n")
    assert len(R.pool_over_cap([root])) == 7 and len(R.pool_over_cap([root, tmp_path / "out"])) == 7
    assert len(R.pool_over_cap([tmp_path / "out"])) == 3


# ── eval-smoke 局数、reset-replay 档序 ─────────────────────────────────


def test_eval_smoke每任务局数按格表推出():
    v8 = types.SimpleNamespace(TIERS=HS.V8_TIERS, V8_CELLS=HS.V8_CELLS, EXPECTED_CELLS=HS.V8_CELLS,
                               XHARD0_PER_TASK=HS.XHARD0_PER_TASK, V7_TIERS=HS.V7_TIERS, V7_XHARD4_ONLY=HS.V7_XHARD4_ONLY)
    want = {t: 92 for t in HS.ALL_TASKS} | {"PickXtimes": 62, "SwingXtimes": 62, "StopCube": 62, "MoveCube": 32,
                                             "InsertPeg": 32}
    assert {t: R.expected_episodes(t, v8) for t in HS.ALL_TASKS} == want
    assert sum(want.values()) == 1262
    # v9：每任务 12 + 50 = 62，共 992；EXPECTED_CELLS 切到 V9 与显式传格表两种入口同值
    v9ns = types.SimpleNamespace(**{**vars(v8), "EXPECTED_CELLS": HS.V9_CELLS})
    want9 = {t: 62 for t in HS.ALL_TASKS}
    assert {t: R.expected_episodes(t, v9ns) for t in HS.ALL_TASKS} == want9
    assert {t: R.expected_episodes(t, v8, HS.V9_CELLS) for t in HS.ALL_TASKS} == want9 and sum(want9.values()) == 992
    # 换包前（全局 TIERS 不含 xhard5）按冻结的 V7 常量 92／32
    v7ns = types.SimpleNamespace(TIERS=HS.V7_TIERS, V8_CELLS=HS.V8_CELLS, XHARD0_PER_TASK=HS.XHARD0_PER_TASK,
                                 V7_TIERS=HS.V7_TIERS, V7_XHARD4_ONLY=HS.V7_XHARD4_ONLY)
    v7 = {t: R.expected_episodes(t, v7ns) for t in HS.ALL_TASKS}
    assert v7["StopCube"] == v7["MoveCube"] == v7["InsertPeg"] == 32 and v7["PickXtimes"] == v7["BinFill"] == 92
    # 包内 TIERS 含 xhard5：真实 hard_specs 按当前 EXPECTED_CELLS 推出（v9 阶段 3b 切换前 V8、切换后 V9）
    assert "xhard5" in HS.TIERS
    assert {t: R.expected_episodes(t, HS) for t in HS.ALL_TASKS} == (want9 if HS.EXPECTED_CELLS == HS.V9_CELLS else want)


def test_reset_replay在v8根按V8_TIERS读(tmp_path):
    root = build_root(tmp_path / "root", H.V8_SMOKE_CELLS)
    tiers, v8 = R.specs_tiers(str(root))
    assert v8 and tiers == HS.V8_TIERS
    index = R.delivery_index(str(root))
    assert len(index) == 7 and min(h["builder_episode"] for h in index.values()) == HS.XHARD0_PER_TASK
    stop = sorted((k[1], h["builder_episode"]) for k, h in index.items() if k[0] == "StopCube")
    assert stop == [("xhard1", 12), ("xhard5", 13)]
    targets = R._replay_targets(str(root))
    assert [t["tier"] for t in targets] == sorted((t["tier"] for t in targets), key=HS.V8_TIERS.index)
    # v8 阶段 3b 换包后包内规格为 /4：缺省根即按 V8_TIERS 读
    assert R.specs_tiers(None) == (HS.V8_TIERS, True)


# ── hard_parity compare --tier v8：分母核对与五终态 ─────────────────────


@pytest.fixture
def v8_sides(tmp_path, monkeypatch):
    """gen1（规格根 + h5 + delivery.json）→ import-delivery 成 H 侧；H2 侧逐字节复制 H 的 h5。"""
    monkeypatch.setattr(H, "TOLERANCES", tmp_path / "tol.json")
    (tmp_path / "tol.json").write_text(json.dumps(TOL))
    gen = tmp_path / "gen1"
    root = build_root(gen / "specs-root", H.V8_SMOKE_CELLS, backfill=True, h5_root=gen)
    delivery = write_delivery(root, gen / "delivery.json")
    h5_root = tmp_path / "h5"
    assert H.main(["import-delivery", "--delivery", str(delivery), "--h5-root", str(h5_root)]) == 0
    left = h5_root / "H-v8"
    right = h5_root / "H2-v8"
    lines = []
    for item in map(json.loads, (left / "identities.jsonl").read_text().splitlines()):
        target = right / item["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((left / item["path"]).read_bytes())
        lines.append({**item, "side": "H2"})
    (right / "identities.jsonl").write_text("".join(json.dumps(x) + "\n" for x in lines))
    return {"root": root, "delivery": delivery, "h5_root": h5_root, "left": left, "right": right, "tmp": tmp_path}


def _compare(s, capsys, run_name="r", delivery=None):
    rc = H.main(["compare", "--pair", "H:H2", "--tier", "v8", "--manifest", str(delivery or s["delivery"]),
                 "--specs-root", str(s["root"]), "--cells", SMOKE, "--h5-root", str(s["h5_root"]),
                 "--compare-root", str(s["tmp"] / "cmp"), "--run-name", run_name, "--workers", "2"])
    out = capsys.readouterr().out
    keys = kv(line(out, "PARITY_H_H2"))
    assert sum(int(keys[state]) for state in H.TERMINAL_STATES) == int(keys["compared"]), out
    return rc, out, keys


def _rewrite(path: Path, fn) -> None:
    items = [json.loads(t) for t in path.read_text().splitlines() if t.strip()]
    items = fn(items)
    path.write_text("".join(json.dumps(x) + "\n" for x in items))


def test_compare_v8全等即PASS(v8_sides, capsys):
    rc, out, keys = _compare(v8_sides, capsys)
    assert rc == 0, out
    assert line(out, "PARITY_H_H2").startswith(
        "PARITY_H_H2=PASS tier=v8 compared=7 cells=7 missing=0 extra=0 duplicate=0 identity_equal=7 "
        "byte_equal=7 noise=0 h2_fail=0 flipped=0 structural=0")
    summary = json.loads((v8_sides["tmp"] / "cmp" / "HH2-v8" / "r" / "summary.json").read_text())
    assert summary["terminal"] == {"byte_equal": 7, "noise": 0, "h2_fail": 0, "flipped": 0, "structural": 0}
    assert summary["denominator"]["missing"] == summary["denominator"]["duplicate"] == 0


def test_compare_v8噪声与H2失败与成败相反(v8_sides, capsys):
    s = v8_sides
    items = [json.loads(t) for t in (s["right"] / "identities.jsonl").read_text().splitlines()]
    # 噪声：第 0 局 H2 从第 2 步起动作差 0.001（容差内），sha 不同、setup／结构／成败相同
    noisy = items[0]
    write_h5(s["right"] / noisy["path"], noisy["seed"], shift=0.001)
    noisy["sha256"] = H.sha256_file(s["right"] / noisy["path"])
    (s["right"] / "identities.jsonl").write_text("".join(json.dumps(x) + "\n" for x in items))
    rc, out, keys = _compare(s, capsys, "noise")
    assert rc == 0 and keys["byte_equal"] == "6" and keys["noise"] == "1" and keys["noise_first_divergence_min"] == "2"
    # H2 失败（gen1 成功）
    _rewrite(s["right"] / "identities.jsonl", lambda xs: [dict(x, success=False, path=None, sha256=None)
                                                          if i == 1 else x for i, x in enumerate(xs)])
    rc, out, keys = _compare(s, capsys, "h2fail")
    assert rc == 1 and keys["h2_fail"] == "1" and keys["structural"] == "0"
    # 成败相反（gen1 失败而 H2 成功）
    _rewrite(s["left"] / "identities.jsonl", lambda xs: [dict(x, success=False, path=None)
                                                         if i == 2 else x for i, x in enumerate(xs)])
    rc, out, keys = _compare(s, capsys, "flip")
    assert rc == 1 and keys["flipped"] == "1" and keys["h2_fail"] == "1"


@pytest.mark.parametrize("case", ["missing", "extra", "duplicate", "delivery_empty", "source_sha"])
def test_compare_v8四方集合不等即FAIL(v8_sides, capsys, case):
    s = v8_sides
    delivery = None
    if case == "missing":
        _rewrite(s["right"] / "identities.jsonl", lambda xs: xs[1:])
    elif case == "extra":
        _rewrite(s["right"] / "identities.jsonl",
                 lambda xs: xs + [dict(xs[0], seed=xs[0]["seed"] + 1, episode=99)])
    elif case == "duplicate":
        _rewrite(s["right"] / "identities.jsonl", lambda xs: xs + [xs[0]])
    elif case == "delivery_empty":
        delivery = write_delivery(s["root"], s["delivery"].parent / "empty.json", rows=[])
    elif case == "source_sha":
        # 交付清单登记的 h5 sha 与 H 侧实际文件不符 → 来源错误（⑤）
        payload = json.loads(s["delivery"].read_text())
        payload["rows"][0]["h5_sha256"] = "0" * 64
        delivery = s["delivery"].parent / "badsha.json"
        delivery.write_text(json.dumps(payload))
    rc, out, keys = _compare(s, capsys, case, delivery=delivery)
    assert rc == 1 and line(out, "PARITY_H_H2").startswith("PARITY_H_H2=FAIL"), out
    want = {"missing": ("missing", "1"), "extra": ("extra", "1"), "duplicate": ("duplicate", "1"),
            "delivery_empty": ("missing", "7"), "source_sha": ("structural", "1")}[case]
    assert keys[want[0]] == want[1], out
    assert int(keys["structural"]) >= 1


def test_compare_空清单不再判PASS(tmp_path, monkeypatch, capsys):
    """旧口径 compared= 就是调用方清单行数，空清单各项 0 = 0 也能过；现拒绝空集（所有 tier）。"""
    monkeypatch.setattr(H, "TOLERANCES", tmp_path / "tol.json")
    (tmp_path / "tol.json").write_text(json.dumps(TOL))
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"rows_total": 0, "rows": []}))
    for side in ("O", "H"):
        (tmp_path / "h5" / f"{side}-native").mkdir(parents=True)
        (tmp_path / "h5" / f"{side}-native" / "identities.jsonl").write_text("")
    rc = H.main(["compare", "--pair", "O:H", "--tier", "native", "--manifest", str(manifest),
                 "--h5-root", str(tmp_path / "h5"), "--compare-root", str(tmp_path / "cmp"), "--workers", "2"])
    out = capsys.readouterr().out
    assert rc == 1 and "PARITY_O_H=FAIL" in out and "compared=0" in out


def test_compare_v8须给冻结规格根(tmp_path):
    with pytest.raises(H.ParityError, match="--specs-root"):
        H.main(["compare", "--pair", "H:H2", "--tier", "v8", "--manifest", str(tmp_path / "d.json")])


def test_import_delivery只收v8清单(tmp_path):
    bad = tmp_path / "delivery.json"
    bad.write_text(json.dumps({"schema": "v7-delivery/1", "rows": []}))
    with pytest.raises(H.ParityError, match="v8-delivery/1"):
        H.main(["import-delivery", "--delivery", str(bad), "--h5-root", str(tmp_path / "h5")])


# ── v9（1002 方案 §2.3；子代理 S1-C）：判定行按格表版本、reset-replay 新键、compare --identities ──────────


#: V9 才合法的子表（MoveCube xhard4 50 > V8 的 20）：规格根按 header 推出 V9
V9_ONLY_CELLS = {("MoveCube", "xhard4"): 50}


def _v9_delivery(root: Path, out: Path, new: set[tuple[str, str]] | None = None) -> Path:
    """assemble 形态的交付清单：逐局身份 + ``source``（MoveCube 全部、InsertPeg 候选号 ≥ 20 记 v9-new，其余 v8-reuse）。"""
    rows = []
    for r in all_rows(root):
        if not HS.delivered(r):
            continue
        is_new = r["task"] == "MoveCube" or (r["task"] == "InsertPeg" and r["candidate"] >= 20)
        rows.append({"task": r["task"], "tier": r["tier"], "episode": r["episode"], "seed": r["seed"],
                     "candidate": r["candidate"], "source": "v9-new" if is_new else "v8-reuse"})
    out.write_text(json.dumps({"schema": H.V8_DELIVERY_SCHEMA, "rows": rows}))
    return out


def test_delivery_set_v9全表打V9行与new_reused(tmp_path, capsys):
    root = build_root(tmp_path / "root", HS.V9_CELLS)
    delivery = _v9_delivery(root, tmp_path / "delivery.local.json")
    rc, out = run(R.main, ["delivery-set", "--specs-root", root, "--cells", "v9full", "--delivery", delivery], capsys)
    assert rc == 0, out
    assert line(out, "V9_DELIVERY_SET").startswith(
        "V9_DELIVERY_SET=PASS tasks=16 cells=43 total=800 new=80 reused=720 expected_cells=43 expected_total=800"), out
    assert line(out, "V9_SEED_DISJOINT").startswith("V9_SEED_DISJOINT=PASS")
    assert line(out, "V9_LAYOUT_INDEPENDENT").startswith("V9_LAYOUT_INDEPENDENT=PASS files=5 delivered=800")
    assert "V8_" not in out and kv(line(out, "V9_DELIVERY_SET"))["delivery_mismatch"] == "0"
    # 不给 --delivery：不打 new／reused
    rc, out = run(R.main, ["delivery-set", "--specs-root", root, "--cells", "v9"], capsys)
    assert rc == 0 and "new=" not in line(out, "V9_DELIVERY_SET")
    # 清单少一局 → delivery_mismatch=1 FAIL；source 写坏 → delivery_bad_rows
    payload = json.loads(delivery.read_text())
    short = tmp_path / "short.json"
    short.write_text(json.dumps({**payload, "rows": payload["rows"][1:]}))
    rc, out = run(R.main, ["delivery-set", "--specs-root", root, "--cells", "v9full", "--delivery", short], capsys)
    assert rc == 1 and kv(line(out, "V9_DELIVERY_SET"))["delivery_mismatch"] == "1"
    payload["rows"][0]["source"] = "v8"
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(payload))
    rc, out = run(R.main, ["delivery-set", "--specs-root", root, "--cells", "v9full", "--delivery", bad], capsys)
    assert rc == 1 and kv(line(out, "V9_DELIVERY_SET"))["delivery_bad_rows"] == "1"
    # 用 V8 表核 V9 根：判定行仍是 V8_ 前缀且 FAIL（3b 切换前核 V9 根必须显式 v9full）
    rc, out = run(R.main, ["delivery-set", "--specs-root", root, "--cells", "v8full"], capsys)
    assert rc == 1 and line(out, "V8_DELIVERY_SET").startswith("V8_DELIVERY_SET=FAIL")


def test_规格根按header推版本(tmp_path):
    v9 = build_root(tmp_path / "v9", V9_ONLY_CELLS)
    assert H.root_cell_table(v9) == ("v9", HS.V9_CELLS) and R.specs_version(str(v9)) == ("v9", HS.V9_CELLS)
    v8 = build_root(tmp_path / "v8", H.V8_SMOKE_CELLS)
    assert H.root_cell_table(v8) == ("v8", HS.V8_CELLS)
    assert H.root_cell_table(tmp_path / "empty") is None
    # 单文件读取按 header 推格表：V9 文件（MoveCube 50）在 EXPECTED_CELLS 仍为 V8 时也能读
    header, rows = H.load_specs_any(v9 / "xhard4" / "specs.jsonl")
    assert header["delivery_per_cell"] == {"MoveCube": 50} and len(rows) == 52
    index = R.delivery_index(str(v9))
    assert len(index) == 50 and all(hit["row"]["spec_sha256"] for hit in index.values())


def _fake_replay(monkeypatch, root: Path, calls: list) -> None:
    """替身 builder／env／spec_binding（不建环境、不 reset）：绑定规格 sha 取 builder 身份里的 spec_sha256。"""
    from robomme_hard import env_record_wrapper as W

    targets = {t["builder_episode"]: t for t in R._replay_targets(str(root))}

    class Env:
        def __init__(self, sha):
            self.sha = sha

        def reset(self):
            return {"front_rgb_list": [0, 0]}, {}

        def close(self):
            pass

    class Builder:
        def __init__(self, task, dataset):
            self.task = task

        def resolve_identity(self, ep):
            t = targets[ep]
            return {"seed": t["seed"], "tier": t["tier"], "spec_sha256": t["spec_sha256"]}

        def make_env_for_episode(self, ep, max_steps):
            calls.append(ep)
            return Env(targets[ep]["spec_sha256"])

    monkeypatch.setattr(W, "BenchmarkEnvBuilder", Builder)
    monkeypatch.setattr(W, "spec_binding", lambda env: {
        "available": True, "mode": "replay", "spec_sha256": env.sha, "injected_mismatch": 0, "layout_drift": 0,
        "unused": 0, "layered": False})
    monkeypatch.setenv(HS.SPECS_ROOT_ENV, str(root))


def test_reset_replay续跑键含spec_sha256_同seed不同规格负例(tmp_path, monkeypatch, capsys):
    root = build_root(tmp_path / "root", V9_ONLY_CELLS)
    calls: list = []
    _fake_replay(monkeypatch, root, calls)
    (target,) = R._replay_targets(str(root))
    out = tmp_path / "gates" / "reset-replay.jsonl"
    out.parent.mkdir()
    # 同 (task, tier, seed)、不同 spec_sha256 的旧记录（如 v8 MoveCube）：不得当成已完成、也不得进判定
    stale = {**target, "spec_sha256": "0" * 64, "ok": True,
             "binding": {"mode": "replay", "spec_sha256": "0" * 64, "injected_mismatch": 0, "unused": 0}}
    out.write_text(json.dumps(stale) + "\n")
    assert R.replay_key(stale) != R.replay_key(target) and R.replay_key(stale)[:3] == R.replay_key(target)[:3]
    argv = ["reset-replay", "--specs-root", root, "--out", out, "--limit", "1"]
    rc, text = run(R.main, argv, capsys)
    assert rc == 0 and calls == [target["builder_episode"]], text
    assert line(text, "V9_RESET_REPLAY").startswith(
        "V9_RESET_REPLAY=PASS shape=cells1 resets=1 replay=1 injected_mismatch=0 layout_drift=0 spec_bound=1"), text
    # 再跑：新键已完成，不再 reset
    rc, text = run(R.main, argv, capsys)
    assert rc == 0 and len(calls) == 1 and "resets=1" in line(text, "V9_RESET_REPLAY")
    # 只有旧记录（换个文件）→ 旧键记录不计入：判定前先重跑；若绑定 sha 不符则 spec_bound=0 FAIL
    monkeypatch.setattr(sys.modules["robomme_hard.env_record_wrapper"], "spec_binding", lambda env: {
        "available": True, "mode": "replay", "spec_sha256": "f" * 64, "injected_mismatch": 0, "layout_drift": 0,
        "unused": 0, "layered": False})
    other = tmp_path / "gates" / "other.jsonl"
    other.write_text(json.dumps(stale) + "\n")
    rc, text = run(R.main, ["reset-replay", "--specs-root", root, "--out", other, "--limit", "1"], capsys)
    assert rc == 1 and kv(line(text, "V9_RESET_REPLAY"))["spec_bound"] == "0"


def test_reset_replay_out必须是文件(tmp_path):
    with pytest.raises(SystemExit, match="必须是 jsonl 文件路径"):
        R.main(["reset-replay", "--out", str(tmp_path)])
    with pytest.raises(SystemExit, match="必须是 jsonl 文件路径"):
        R.main(["reset-replay", "--out", str(tmp_path / "gates") + "/"])
    with pytest.raises(SystemExit):
        R.main(["reset-replay"])  # --out 必填


def test_reset_replay判定行按版本(tmp_path):
    targets = [{"task": "MoveCube", "tier": "xhard4", "seed": i, "spec_sha256": f"s{i}"} for i in range(43)]
    rows = [{**t, "ok": True, "binding": {"mode": "replay", "spec_sha256": t["spec_sha256"], "injected_mismatch": 0,
                                          "layout_drift": 0, "unused": 0}} for t in targets]
    ok, text = R.replay_verdict(targets, rows, version="v9", table=HS.V9_CELLS, limited=False)
    assert ok and text == ("V9_RESET_REPLAY=PASS shape=cells43 resets=43 replay=43 injected_mismatch=0 layout_drift=0 "
                           "spec_bound=43 unused=0 layout_hit_bad=0 errors=0")
    ok, text = R.replay_verdict(targets, rows, version="v8", table=HS.V8_CELLS, limited=False)
    assert ok and text.startswith("V8_RESET_REPLAY=PASS shape=cells43")
    rows[0]["binding"]["spec_sha256"] = "other"
    ok, text = R.replay_verdict(targets, rows, version="v9", table=HS.V9_CELLS, limited=False)
    assert not ok and "spec_bound=42" in text
    ok, _ = R.replay_verdict(targets[:42], rows[1:], version="v9", table=HS.V9_CELLS, limited=False)
    assert not ok  # 未截断却少一格


def test_step_headroom_v9清单打V9行(tmp_path, capsys):
    gen = tmp_path / "gen1"
    root = build_root(gen / "specs-root", V9_ONLY_CELLS, h5_root=gen)
    delivery = write_delivery(root, gen / "delivery.json")
    rc, out = run(R.main, ["step-headroom", "--delivery", delivery, "--pool", root, "--skip-xhard0"], capsys)
    assert rc == 0 and line(out, "V9_STEP_CAP").startswith("V9_STEP_CAP=INFO max=3 cap=1600 over=0 filtered=0"), out


@pytest.fixture
def v9_sides(tmp_path, monkeypatch):
    """v9 冒烟根（MoveCube／InsertPeg 各 1 局）+ 带 source 的清单：MoveCube 为 v9-new、InsertPeg（候选 0）为 v8-reuse。"""
    monkeypatch.setattr(H, "TOLERANCES", tmp_path / "tol.json")
    (tmp_path / "tol.json").write_text(json.dumps(TOL))
    gen = tmp_path / "gen1"
    root = build_root(gen / "specs-root", H.V9_SMOKE_CELLS, h5_root=gen)
    delivery = write_delivery(root, gen / "delivery.json")
    payload = json.loads(delivery.read_text())
    for row in payload["rows"]:
        row["source"] = "v9-new" if row["task"] == "MoveCube" else "v8-reuse"
    delivery.write_text(json.dumps(payload))
    h5_root = tmp_path / "h5"
    assert H.main(["import-delivery", "--tier", "v9", "--delivery", str(delivery), "--identities", str(delivery),
                   "--h5-root", str(h5_root)]) == 0
    left, right = h5_root / "H-v9", h5_root / "H2-v9"
    lines = []
    for item in map(json.loads, (left / "identities.jsonl").read_text().splitlines()):
        target = right / item["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((left / item["path"]).read_bytes())
        lines.append({**item, "side": "H2"})
    (right / "identities.jsonl").write_text("".join(json.dumps(x) + "\n" for x in lines))
    return {"root": root, "delivery": delivery, "h5_root": h5_root, "left": left, "right": right, "tmp": tmp_path}


def _compare_v9(s, capsys, run_name, extra=()):
    rc = H.main(["compare", "--pair", "H:H2", "--tier", "v9", "--manifest", str(s["delivery"]),
                 "--specs-root", str(s["root"]), "--cells", "v9smoke", "--identities", str(s["delivery"]),
                 "--h5-root", str(s["h5_root"]), "--compare-root", str(s["tmp"] / "cmp"), "--run-name", run_name,
                 "--workers", "2", *extra])
    out = capsys.readouterr().out
    return rc, out, kv(line(out, "PARITY_H_H2"))


def test_compare_v9只比identities子集(v9_sides, capsys):
    s = v9_sides
    # import-delivery --identities：H 侧只登记 v9-new 的 1 局
    assert len((s["left"] / "identities.jsonl").read_text().splitlines()) == 1
    rc, out, keys = _compare_v9(s, capsys, "ok")
    assert rc == 0, out
    assert line(out, "PARITY_H_H2").startswith(
        "PARITY_H_H2=PASS tier=v9 compared=1 cells=1 missing=0 extra=0 duplicate=0 identity_equal=1 "
        "byte_equal=1 noise=0 h2_fail=0 flipped=0 structural=0"), out
    assert keys["identities"] == "1" and keys["manifest_rows_all"] == "2" and keys["hard_line_5pct"] == "ok"
    assert keys["shape"] == "cells43:272+272+92+144+20"
    # 子集身份在 H2 缺席 → missing=1 FAIL
    (s["right"] / "identities.jsonl").write_text("")
    rc, out, keys = _compare_v9(s, capsys, "missing")
    assert rc == 1 and keys["missing"] == "1"


def test_compare_v9格表与档不符即报错(v9_sides):
    s = v9_sides
    with pytest.raises(H.ParityError, match="--cells 与 --tier v9 不符"):
        H.main(["compare", "--pair", "H:H2", "--tier", "v9", "--manifest", str(s["delivery"]),
                "--specs-root", str(s["root"]), "--cells", '{"VideoUnmask/xhard1": 20}', "--h5-root", str(s["h5_root"]),
                "--compare-root", str(s["tmp"] / "cmp"), "--run-name", "bad"])
    with pytest.raises(H.ParityError, match="子集为空"):
        empty = s["tmp"] / "empty.jsonl"
        empty.write_text("")
        H.read_identity_subset(empty)
