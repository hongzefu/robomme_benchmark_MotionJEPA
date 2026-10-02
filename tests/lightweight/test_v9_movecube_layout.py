#!/usr/bin/env python3
"""轻量测试：``hard_regression.py movecube-layout``（1002 方案 §2.3 ``V9_MOVECUBE_LAYOUT``／``V9_MOVECUBE_WAYS``；子代理 S1-C）。

纯 CPU 手写坐标夹具（不建环境、不 reset）：在 tmp_path 写一份 /4 的 ``xhard4/specs.jsonl``（经 ``hard_specs`` 真签名），
MoveCube 50 局交付（另 2 个未选候选），每局 demo／execution 两段的 ``layout.<seg>`` 字段与
``MoveCube._load_scene_xhard4_region`` 写入的形状相同：``cube_pose = [x, y, yaw]``、``goal_xy``、
``peg_offsets = [base_y, 杆根 x, 杆根 y]``、``peg_yaw``、``region``（源码 ``config_xhard4["region"]`` + 记录项
``peg_axis_extent_m`` 等）；运动方式写在 ``initializations`` 的最后一项 ``way_idx``，17／17／16。

覆盖：PASS 一例（300 点全在 V9 U 内、全部落在旧 V8 区域外）；篡改一点出 U → FAIL；方式计数 18／16／16 → FAIL；
规格 region 仍是 V8 值 → ``region_mismatch`` FAIL；``--delivery`` 只取清单内的 selected 行。

    uv run --no-sync python -m pytest tests/lightweight/test_v9_movecube_layout.py -q
"""

from __future__ import annotations

import copy
import json
import re
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.parity import hard_parity as H  # noqa: E402
from scripts.parity import hard_regression as R  # noqa: E402

HS = H.hard_specs_light()
MC, FREEZE = R._movecube_source()
TIER = "xhard4"
#: 杆长与源码 ``self.length = (0.1 + 0 * rand).item()``（float32）同值
LENGTH = float(np.float32(0.1))
#: V9 U 内、旧 V8 圆环（r ≤ 0.20）外的手写点：左右两块各取一组（方块、goal、抓杆点）
SIDES = {
    "demo": {"cube": (0.0, 0.30), "goal": (-0.06, 0.30), "grasp": (-0.10, 0.30)},
    "execution": {"cube": (0.0, -0.30), "goal": (-0.06, -0.30), "grasp": (-0.10, -0.30)},
}


def region_record() -> dict:
    """规格里 ``layout.<seg>.region`` 的形状：源码决策字典 + 只读记录项（与 ``_load_scene_xhard4_region`` 同键）。"""
    return dict(copy.deepcopy(MC.MoveCube.config_xhard4["region"]),
                peg_axis_extent_m=list(MC._peg_axis_extent(LENGTH)), robot_base_xy=list(MC.ROBOT_BASE_XY),
                push_backoff_m=0.1, peg_push_lateral_m=0.1, min_cube_goal_m=0.1)


def make_spec(cand: int, way: int) -> dict:
    layout = {}
    for seg, pts in SIDES.items():
        yaw = 0.0  # u = (1, 0)：杆根 = 抓取点 + length·u
        layout[seg] = {"cube_pose": [pts["cube"][0], pts["cube"][1], 0.5], "goal_xy": list(pts["goal"]),
                       "peg_offsets": [0.0, pts["grasp"][0] + LENGTH, pts["grasp"][1]], "peg_yaw": yaw,
                       "region": region_record(), "region_trials": {"peg_trials": 1 + cand % 3}}
    return {"spec_kind": "native-newvalue/2", "task": "MoveCube", "layout": layout,
            "initializations": {"0": {"way_idx": (way + 1) % 3}, "1": {"way_idx": way}},
            "objects": {"obj_sample": 0, "sampling_trace": {"dir_sample": 1}}}


def ways_for(counts=(17, 17, 16)) -> list[int]:
    return [w for w, n in enumerate(counts) for _ in range(n)]


def write_specs(root: Path, ways: list[int], edit=None) -> Path:
    """MoveCube xhard4：交付 ``len(ways)`` 局 + 2 个未选候选；``edit(rows)`` 原地改后重算规格散列与 header 签名。"""
    quota = len(ways)
    rule = HS.seed_rule_for(TIER, "v8")
    rows = []
    for cand in range(quota + 2):
        selected = cand < quota
        spec = make_spec(cand, ways[cand] if selected else 0)
        rollout = ({"status": "ok", "exec_steps": 300, "round": 0, "frames": 400, "h5_sha256": f"h{cand}",
                    "env_module": "robomme_hard.robomme_env.MoveCube"} if selected else None)
        rows.append({"record": "spec", "task": "MoveCube", "tier": TIER, "candidate": cand, "episode": cand,
                     "seed": HS.seed_for("MoveCube", cand, 0, rule), "attempt": 0, "spec": spec,
                     "spec_sha256": HS.spec_sha256(spec), "selected": selected, "tried": selected,
                     "initial_selected": selected, "rollout": rollout, "layout_parent": None})
    if edit is not None:
        edit(rows)
        for row in rows:
            row["spec_sha256"] = HS.spec_sha256(row["spec"])
    sampling = {"MoveCube": {"decision": {"k": "MoveCube"}, "native": {}}}
    header = {
        "record": "header", "schema": HS.SCHEMA_V8, "difficulty": TIER, "tasks": ["MoveCube"],
        "per_env": {"MoveCube": quota + 2}, "runtime": dict(HS.RUNTIME), "seed_rule": rule,
        "select_rule": {"MoveCube": list(range(quota))}, "sampling_config": sampling,
        "sampling_config_sha256": HS.digest(sampling), "recovery_rule": {"rule": "off"}, "identity_source": "formula",
        "layout_rule": {"mode": "independent"}, "exec_cap": HS.V8_EXEC_CAP, "delivery_per_cell": {"MoveCube": quota},
        "run_id": "v9-movecube-fixture", "draw_stats": {}, "provenance": {},
    }
    header["identity_sha256"] = HS.identity_sha256(header, rows)
    header["delivery_sha256"] = HS.delivery_sha256(rows)
    path = root / TIER / "specs.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(HS.canonical_json(r) + "\n" for r in (header, *rows)), encoding="utf-8")
    return root


def run(argv, capsys) -> tuple[int, str]:
    rc = R.main(["movecube-layout", *map(str, argv)])
    return rc, capsys.readouterr().out


def line(out: str, name: str) -> str:
    hits = [t for t in out.splitlines() if t.startswith(f"{name}=")]
    assert len(hits) == 1, out
    return hits[0]


def kv(text: str) -> dict[str, str]:
    return dict(re.findall(r"(\w+)=(\S+)", text))


def test_源码判定函数与V9配额():
    """命令复用源码函数而不重写：U 判定、抓取点几何、方式取值与期望配额都来自源码模块。"""
    assert R._movecube_source()[0].MoveCube.config_xhard4["region"]["r_in"] == R.V9_MOVECUBE_REGION["r_in"]
    assert {k: MC.MoveCube.config_xhard4["region"][k] for k in R.V9_MOVECUBE_REGION} == R.V9_MOVECUBE_REGION
    assert FREEZE.V9_MOVECUBE_QUOTA_BY_WAY == {0: 17, 1: 17, 2: 16}
    region = MC.MoveCube._xhard4_region(None, {"xhard4": {"region": region_record()}}, "demo_layout")
    assert MC._in_region_u(np.array([-0.06, 0.30]), region) is None
    assert MC._in_region_u(np.array([-0.06, 0.15]), region) is not None  # 旧 V8 圆环内 → V9 内孔
    # 抓杆点 = 杆根 − length·u：夹具按源码几何能恢复手写坐标
    spec = make_spec(0, 0)
    pts = R.movecube_points(spec, "demo", MC)["points"]
    assert np.allclose(pts["grasp"], SIDES["demo"]["grasp"], atol=1e-6)


def test_PASS_300点在新区域且全部在旧区域外(tmp_path, capsys):
    root = write_specs(tmp_path / "root", ways_for())
    report = tmp_path / "layout.json"
    rc, out = run(["--specs-root", root, "--out", report], capsys)
    assert rc == 0, out
    assert line(out, "V9_MOVECUBE_LAYOUT").startswith(
        "V9_MOVECUBE_LAYOUT=PASS episodes=50 in_region=300 outside_old=300 points=300"), out
    assert line(out, "V9_MOVECUBE_WAYS").startswith("V9_MOVECUBE_WAYS=PASS ways=17/17/16 expected=17/17/16"), out
    got = json.loads(report.read_text())
    assert got["region_mismatch"] == 0 and got["ways"] == {"0": 17, "1": 17, "2": 16}
    # 单文件路径同样可读
    rc, out = run(["--specs-root", root / TIER / "specs.jsonl"], capsys)
    assert rc == 0 and "V9_MOVECUBE_LAYOUT=PASS" in out


def test_篡改一点出U即FAIL(tmp_path, capsys):
    def move_goal(rows):
        rows[7]["spec"]["layout"]["execution"]["goal_xy"] = [-0.06, -0.15]  # 落进 V9 内孔（r < 0.24）
    root = write_specs(tmp_path / "root", ways_for(), edit=move_goal)
    rc, out = run(["--specs-root", root], capsys)
    keys = kv(line(out, "V9_MOVECUBE_LAYOUT"))
    assert rc == 1 and line(out, "V9_MOVECUBE_LAYOUT").startswith("V9_MOVECUBE_LAYOUT=FAIL"), out
    assert keys["in_region"] == "299" and keys["points"] == "300" and keys["outside_old"] == "299"
    assert "execution/goal" in out
    # 方式计数不受影响
    assert line(out, "V9_MOVECUBE_WAYS").startswith("V9_MOVECUBE_WAYS=PASS")


def test_方式计数不等于17_17_16即FAIL(tmp_path, capsys):
    root = write_specs(tmp_path / "root", ways_for((18, 16, 16)))
    rc, out = run(["--specs-root", root], capsys)
    assert rc == 1 and line(out, "V9_MOVECUBE_WAYS").startswith("V9_MOVECUBE_WAYS=FAIL ways=18/16/16 expected=17/17/16")
    assert line(out, "V9_MOVECUBE_LAYOUT").startswith("V9_MOVECUBE_LAYOUT=PASS")


def test_规格region仍是V8值即FAIL(tmp_path, capsys):
    def old_region(rows):
        for row in rows:
            row["spec"]["layout"]["demo"]["region"].update(r_in=0.12, r_out=0.20, base_dist=[0.35, 0.76])
    root = write_specs(tmp_path / "root", ways_for(), edit=old_region)
    rc, out = run(["--specs-root", root], capsys)
    keys = kv(line(out, "V9_MOVECUBE_LAYOUT"))
    assert rc == 1 and keys["region_mismatch"] == "50"
    # 按规格自身的旧 region 判：demo 段 150 点都不在（旧）U 内
    assert keys["in_region"] == "150"


def test_delivery清单筛行与局数不足(tmp_path, capsys):
    root = write_specs(tmp_path / "root", ways_for())
    rows = [json.loads(t) for t in (root / TIER / "specs.jsonl").read_text().splitlines()[1:]]
    delivery = tmp_path / "delivery.json"
    keep = [r for r in rows if r["selected"]][:49]
    delivery.write_text(json.dumps({"schema": H.V8_DELIVERY_SCHEMA, "rows": [
        {"task": r["task"], "tier": r["tier"], "seed": r["seed"], "episode": r["episode"], "source": "v9-new"}
        for r in keep]}))
    rc, out = run(["--specs-root", root, "--delivery", delivery], capsys)
    assert rc == 1 and kv(line(out, "V9_MOVECUBE_LAYOUT"))["episodes"] == "49"
    rc, out = run(["--specs-root", root, "--delivery", delivery, "--expected-episodes", 49], capsys)
    assert kv(line(out, "V9_MOVECUBE_LAYOUT"))["in_region"] == "294" and "V9_MOVECUBE_LAYOUT=PASS" in out
