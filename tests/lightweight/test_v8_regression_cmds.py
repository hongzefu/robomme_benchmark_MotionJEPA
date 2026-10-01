#!/usr/bin/env python3
"""轻量测试：v8 对拍守卫（1001 方案第一部分 §3、第二部分 §2.3；子代理 S2-C）。

纯 CPU 合成夹具，不起仿真：在 tmp_path 里写 /4 规格根（``<root>/<tier>/specs.jsonl``，经 ``hard_specs`` 真签名）、
最小 h5（``timestep_*`` + ``info/is_video_demo``）与 ``delivery.json``（schema ``v8-delivery/1``），走「写 JSON → 读
JSON → 守卫」往返，覆盖：

* ``hard_regression.py delivery-set``：完整 43 格根、冒烟 7 格根、分片子集根三种格表各一次 PASS；判定行计数键（含零值）
  显式出现在判定行与 ``--out`` JSON 里；相等比较（少一局即 FAIL）、seed 跨档相交、``layout_parent`` 非空、跨档照抄
  布局（位置指纹相同）各自判 FAIL；
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
            "layout": {"button_xy": [round(0.1 * ti + 0.001 * cand + 0.0003, 6), -0.25], "cube_count": 3}}
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


def test_格表解析与形状():
    assert H.parse_cells("full") == HS.V8_CELLS and sum(H.parse_cells("full").values()) == 1070
    assert H.parse_cells("smoke") == H.V8_SMOKE_CELLS and len(H.V8_SMOKE_CELLS) == 7
    assert H.parse_cells('{"PickXtimes/xhard1": 17, "MoveCube": {"xhard4": 3}}') == {
        ("PickXtimes", "xhard1"): 17, ("MoveCube", "xhard4"): 3}
    assert H.parse_cells('[["StopCube", "xhard5", 1], {"task": "BinFill", "tier": "xhard2", "n": 2}]') == {
        ("StopCube", "xhard5"): 1, ("BinFill", "xhard2"): 2}
    for bad in ('{"PickXtimes/xhard4": 1}', '{"PickXtimes/xhard1": 18}', '{"BinFill/xhard1": 0}', "{}"):
        with pytest.raises(H.ParityError):
            H.parse_cells(bad)
    per_tier = [sum(n for (_, t), n in HS.V8_CELLS.items() if t == tier) for tier in HS.V8_TIERS]
    assert H.SHAPES["v8"] == "cells43:" + "+".join(map(str, per_tier)) and per_tier == [411, 411, 128, 100, 20]
    assert H.TIER_NAMES == HS.V8_TIERS and "v7" not in H.TIERS and "v8" in H.TIERS
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


def test_位置指纹只取位置类叶子():
    a = {"layout": {"cubes": {"r": [0.1, 0.2, 0.3]}, "count": 3, "mode": "x"}, "actions": {"path_nodes": [1, 2, 3]}}
    b = copy.deepcopy(a)
    b["layout"]["count"] = 5
    assert R.layout_fingerprint(a) == R.layout_fingerprint(b)
    b["actions"]["path_nodes"] = [1, 2, 4]
    assert R.layout_fingerprint(a) != R.layout_fingerprint(b)
    assert R.layout_fingerprint({"objects": {"n": 3}}) is None


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
    v8 = types.SimpleNamespace(TIERS=HS.V8_TIERS, V8_CELLS=HS.V8_CELLS, XHARD0_PER_TASK=HS.XHARD0_PER_TASK,
                               V7_TIERS=HS.V7_TIERS, V7_XHARD4_ONLY=HS.V7_XHARD4_ONLY)
    want = {t: 92 for t in HS.ALL_TASKS} | {"PickXtimes": 62, "SwingXtimes": 62, "StopCube": 62, "MoveCube": 32,
                                             "InsertPeg": 32}
    assert {t: R.expected_episodes(t, v8) for t in HS.ALL_TASKS} == want
    assert sum(want.values()) == 1262
    # 换包前包内仍是 v7 规格（R10）：按冻结的 V7 常量 92／32
    assert "xhard5" not in HS.TIERS
    v7 = {t: R.expected_episodes(t, HS) for t in HS.ALL_TASKS}
    assert v7["StopCube"] == v7["MoveCube"] == v7["InsertPeg"] == 32 and v7["PickXtimes"] == v7["BinFill"] == 92


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
    # v7 包内规格仍走 v7 档序
    assert R.specs_tiers(None) == (HS.TIERS, False)


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
