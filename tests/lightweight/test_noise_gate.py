"""轻量测试：scripts/parity/noise_gate.py（1003 噪声基线计划第一部分第三、六节；纯 CPU、临时目录，不读 artifacts/）。"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from scripts.parity import noise_gate as ng


# ── 夹具 ───────────────────────────────────────────────────────────────────


def _ids(n, tier="xhard1", task="T"):
    return ng._fx_idents(n, tier=tier, task=task)


def _two_sides(tmp_path, new_kwargs: dict[int, dict], n=6, new_entries_extra=None):
    """参照侧 n 局全成功；新侧按 new_kwargs[seed] 改造（值为 None 表示与参照逐字节相同）。"""
    ref, new = {}, {}
    for s in range(n):
        ref[("T", s)] = {"h5": ng._fx_h5(tmp_path / "ref" / f"e{s}.h5", seed=s)}
        kw = new_kwargs.get(s)
        new[("T", s)] = {"h5": ng._fx_h5(tmp_path / "new" / f"e{s}.h5", seed=s, **(kw or {}))}
    if new_entries_extra:
        new.update(new_entries_extra)
    return ng._fx_side(tmp_path / "ref", ref), ng._fx_side(tmp_path / "new", new)


# ── 生成五类 ───────────────────────────────────────────────────────────────


def test_五类各至少一例且互斥完备(tmp_path):
    n = 7
    kwargs = {1: {"diverge_at": 2}, 2: {"setup_seed": 99}, 3: {"drop": (0, "obs/front_depth")},
              4: {"frame0_delta": True}}
    ref_root, _ = _two_sides(tmp_path, kwargs, n=n)
    # 新侧：seed 5 求解失败、seed 6 缺文件
    new_entries = {}
    for s in range(5):
        new_entries[("T", s)] = {"h5": tmp_path / "new" / f"e{s}.h5"}
    new_entries[("T", 5)] = {"ok": False, "error_type": "DatasetGenerationError"}
    new_root = ng._fx_side(tmp_path / "new", new_entries)
    (tmp_path / "new" / "e6.h5").unlink()
    rows, counts = ng.gen_compare(ref_root, new_root, _ids(n))
    by = {r["seed"]: r for r in rows}
    assert by[0]["class"] == "byte_equal" and by[0]["first_divergence"] is None
    assert by[1]["class"] == "diverge" and by[1]["first_divergence"] == 2
    assert by[1]["action_max"] == pytest.approx(0.5) and by[1]["state_max"] == pytest.approx(0.5)
    assert by[2]["class"] == "structural" and "setup" in by[2]["reason"]
    assert by[3]["class"] == "structural" and "frame0" in by[3]["reason"]
    assert by[4]["class"] == "structural" and by[4]["reason"].endswith("frame0_content")
    assert by[5]["class"] == "gen_fail" and by[5]["fail_side"] == "new"
    assert by[6]["class"] == "unknown" and by[6]["reason"] == "missing_new"
    assert sum(counts.values()) == n
    assert all(r["class"] in ng.GEN_CLASSES for r in rows)


def test_中间帧缺字段判结构不同(tmp_path):
    ref_root, new_root = _two_sides(tmp_path, {0: {"drop": (2, "info/is_completed")}}, n=1)
    rows, _ = ng.gen_compare(ref_root, new_root, _ids(1))
    assert rows[0]["class"] == "structural" and "frame2" in rows[0]["reason"]


def _wp_pair(tmp_path, name, ref_kw, new_kw):
    ref = {("T", 0): {"h5": ng._fx_h5(tmp_path / f"{name}-r" / "0.h5", seed=0, **ref_kw)}}
    new = {("T", 0): {"h5": ng._fx_h5(tmp_path / f"{name}-n" / "0.h5", seed=0, **new_kw)}}
    rows, _ = ng.gen_compare(ng._fx_side(tmp_path / f"{name}-r", ref), ng._fx_side(tmp_path / f"{name}-n", new), _ids(1))
    return rows[0]


def test_白名单常量():
    assert ng.POLYMORPHIC_KEYS == {"action/waypoint_action": frozenset({("float32", (7,)), ("float64", (7,))})}


def test_白名单字段占位签名随轨迹变化按分叉计(tmp_path):
    # 实测形态：waypoint_action 每帧都在，无路点时 float32 NaN 占位、有路点时 float64 实值
    row = _wp_pair(tmp_path, "a", dict(waypoint_frames=(1, 2), waypoint_nan_frames=(0, 3)),
                   dict(waypoint_frames=(1, 3), waypoint_nan_frames=(0, 2), diverge_at=2))
    assert row["class"] == "diverge" and row["first_divergence"] == 2
    assert row["variable_signature_frames"] == 2 and row["variable_keys"] == ["action/waypoint_action"]


def test_白名单字段一侧全程实值另一侧有占位不判结构不同(tmp_path):
    # 「某一遍一帧都没走到占位」：参照侧全程 float64，新侧第 2、3 帧是 NaN 占位
    row = _wp_pair(tmp_path, "b", dict(waypoint_frames=range(4)),
                   dict(waypoint_frames=(0, 1), waypoint_nan_frames=(2, 3), diverge_at=2))
    assert row["class"] == "diverge" and row["first_divergence"] == 2


def test_白名单字段集合外签名判结构不同(tmp_path):
    row = _wp_pair(tmp_path, "c", dict(waypoint_frames=range(4)),
                   dict(waypoint_frames=(0, 1, 2), waypoint_int_frames=(3,), diverge_at=2))
    assert row["class"] == "structural" and "polymorphic_signature_new" in row["reason"]
    # 白名单字段在某帧不存在也属集合外
    row = _wp_pair(tmp_path, "d", dict(waypoint_frames=range(4)), dict(waypoint_frames=(0, 1, 3), diverge_at=2))
    assert row["class"] == "structural" and "frame2:polymorphic_signature_new" in row["reason"]


def test_白名单字段第0帧签名不同判结构不同(tmp_path):
    row = _wp_pair(tmp_path, "e", dict(waypoint_frames=range(4)), dict(waypoint_frames=(1, 2, 3), waypoint_nan_frames=(0,)))
    assert row["class"] == "structural" and row["reason"].endswith("frame0:schema")


def test_非白名单字段随帧变化或只在一侧出现判结构不同(tmp_path):
    # 非白名单字段单帧缺失（另一侧恒定）
    row = _wp_pair(tmp_path, "f", {}, dict(drop=(2, "obs/gripper_state"), diverge_at=1))
    assert row["class"] == "structural" and row["reason"].endswith("frame2:schema_new")
    # 字段只在一侧出现
    row = _wp_pair(tmp_path, "g", {}, dict(waypoint_frames=range(4)))
    assert row["class"] == "structural" and row["reason"].endswith("dataset_universe")


def test_内容全同字节不同判原因不明(tmp_path):
    import h5py
    import numpy as np

    ref_root, new_root = _two_sides(tmp_path, {}, n=1)
    path = tmp_path / "new" / "e0.h5"
    # 改一个属性之外的元数据：重新写同内容但用不同 chunk 布局，使字节不同、内容全同
    with h5py.File(path, "w") as f:
        ep = f.create_group("episode_0")
        st = ep.create_group("setup")
        st["seed"] = np.int64(0)
        st["difficulty"] = "xhard1"
        st.create_dataset("front_camera_intrinsic", data=np.eye(3, dtype=np.float32), chunks=(3, 3))
        for i in range(4):
            g = ep.create_group(f"timestep_{i}")
            g["action/joint_action"] = np.full(8, 0.1 * i, dtype=np.float64)
            g["obs/joint_state"] = np.full(7, 0.2 * i, dtype=np.float32)
            g["obs/gripper_state"] = np.zeros(2, dtype=np.float32)
            g["obs/front_rgb"] = np.full((4, 4, 3), i, dtype=np.uint8)
            g["obs/front_depth"] = np.zeros((4, 4, 1), dtype=np.int16)
            g["info/is_completed"] = np.bool_(i == 3)
    ng._fx_side(tmp_path / "new", {("T", 0): {"h5": path}})
    rows, _ = ng.gen_compare(ref_root, new_root, _ids(1))
    assert rows[0]["class"] == "unknown" and rows[0]["reason"] == "content_equal_bytes_differ"


def test_帧数不同判分叉(tmp_path):
    ref_root, new_root = _two_sides(tmp_path, {0: {"frames": 6}}, n=1)
    rows, _ = ng.gen_compare(ref_root, new_root, _ids(1))
    # 末帧 is_completed 在两侧落在不同帧号，第 3 帧起即不同
    assert rows[0]["class"] == "diverge" and rows[0]["first_divergence"] == 3 and rows[0]["frames_diff"] == 2


def test_参照侧失败与基础设施失败(tmp_path):
    ref = {("T", 0): {"ok": False, "error_type": "PlannerExhausted"}, ("T", 1): {"h5": ng._fx_h5(tmp_path / "r" / "1.h5", seed=1)}}
    new = {("T", 0): {"h5": ng._fx_h5(tmp_path / "n" / "0.h5", seed=0)},
           ("T", 1): {"ok": False, "error_type": "RuntimeError"}}
    rows, _ = ng.gen_compare(ng._fx_side(tmp_path / "r", ref), ng._fx_side(tmp_path / "n", new), _ids(2))
    assert rows[0]["class"] == "gen_fail" and rows[0]["fail_side"] == "ref"
    assert rows[1]["class"] == "unknown" and rows[1]["reason"].startswith("infra_new")


def test_记录的sha与文件不符判原因不明(tmp_path):
    ref_root, new_root = _two_sides(tmp_path, {}, n=1)
    lines = ng.read_jsonl(new_root / "identities.jsonl")
    lines[0]["sha256"] = "0" * 64
    ng.write_jsonl(new_root / "identities.jsonl", lines)
    rows, _ = ng.gen_compare(ref_root, new_root, _ids(1))
    assert rows[0]["class"] == "unknown" and rows[0]["reason"].startswith("sha_recorded_mismatch")


def test_交付清单侧与xhard0档位别名(tmp_path):
    h5 = ng._fx_h5(tmp_path / "d" / "e0.h5", seed=0)
    delivery = tmp_path / "delivery.json"
    delivery.write_text(json.dumps({"schema": "v8-delivery/1", "rows": [
        {"task": "T", "tier": "xhard1", "seed": 0, "h5": str(h5), "h5_sha256": ng.sha256_file(h5)}]}))
    side = ng.load_side(delivery)
    assert side[("T", 0)]["status"] == "ok"
    rows, counts = ng.gen_compare(delivery, delivery, _ids(1))
    assert counts["byte_equal"] == 1
    assert ng.tier_compatible("xhard0", "hard") and not ng.tier_compatible("xhard1", "hard")


def test_身份清单三种格式(tmp_path):
    d0 = tmp_path / "d0.json"
    d0.write_text(json.dumps([{"task": "A", "seed": 1, "source_episode": 3, "builder_episode": 0}]))
    got = ng.load_identities(d0)
    assert got[0]["tier"] == "xhard0" and got[0]["source_episode"] == 3 and got[0]["id"] == "A|xhard0|1"
    jl = ng.write_jsonl(tmp_path / "x.jsonl", [{"task": "A", "tier": "xhard2", "seed": 5}])
    assert ng.load_identities(jl)[0]["id"] == "A|xhard2|5"
    dup = ng.write_jsonl(tmp_path / "dup.jsonl", [{"task": "A", "seed": 5}, {"task": "A", "seed": 5}])
    with pytest.raises(ng.GateError):
        ng.load_identities(dup)


# ── 统计量 ─────────────────────────────────────────────────────────────────


def test_clopper_pearson_手算对照():
    assert ng.cp_upper(0, 10) == pytest.approx(1 - 0.05 ** (1 / 10), abs=1e-15)
    assert ng.cp_upper(0, 10) == pytest.approx(0.2588655, abs=1e-6)
    assert ng.cp_upper(10, 10) == 1.0
    # 已知表值：n=10, x=1 单侧 95% 上界 0.3941633（双侧 90% 区间上端）
    assert ng.cp_upper(1, 10) == pytest.approx(0.3941633, abs=1e-6)
    # 定义式：P(X ≤ x | n, p_U) = 0.05
    for x, n in ((3, 20), (7, 192), (18, 800)):
        assert ng.binom_cdf(x, n, ng.cp_upper(x, n)) == pytest.approx(0.05, abs=1e-9)


def test_二项分位数手算对照():
    assert ng.binom_quantile(0.99, 10, 0.0) == 0
    assert ng.binom_quantile(0.99, 10, 1.0) == 10
    # Bin(2, 0.5)：CDF = 0.25, 0.75, 1 → 99% 分位数 2；50% 分位数 1
    assert ng.binom_quantile(0.99, 2, 0.5) == 2
    assert ng.binom_quantile(0.5, 2, 0.5) == 1

    def brute(q, n, p):
        acc = 0.0
        for k in range(n + 1):
            acc += math.comb(n, k) * p ** k * (1 - p) ** (n - k)
            if acc >= q - 1e-12:
                return k
        return n
    for n, p in ((10, 0.2588655), (192, 0.03), (192, 0.1)):
        assert ng.binom_quantile(0.99, n, p) == brute(0.99, n, p)


def test_线公式_全零与不小于观测最大值():
    zero = ng.noise_line([0, 0], 192)
    assert zero["p_upper"] == pytest.approx(1 - 0.05 ** (1 / 384))
    assert zero["line"] == ng.binom_quantile(0.99, 192, zero["p_upper"]) and zero["line"] >= 0
    big = ng.noise_line([0, 30], 192)
    assert big["line"] >= 30 and big["p_hat"] == pytest.approx(30 / 384)


def test_mcnemar_手算():
    assert ng.mcnemar_p(12, 4) == pytest.approx(2 * 2517 / 65536)
    assert ng.mcnemar_p(0, 0) == 1.0


# ── 评估取数：V8 账本 ──────────────────────────────────────────────────────


def _entry(seed, attempts, tier="xhard1", task="T", spec=None):
    return {"key": f"{task}_{tier}_{seed}", "task": task, "tier": tier, "seed": seed, "spec": spec,
            "attempts": attempts}


def test_v8_接受_冲突_迟到_步后重试(tmp_path):
    ents = [
        _entry(0, [{"id": "a0", "status": "success", "exec_steps": 50, "accept": True, "t": 10.0}]),
        # 冲突：两个不同的被接受尝试
        _entry(1, [{"id": "a1", "status": "fail", "exec_steps": 50, "accept": True},
                   {"id": "b1", "status": "success", "exec_steps": 40, "accept": True}]),
        # 迟到成功不覆盖已接受失败（也算步后重试）
        _entry(2, [{"id": "a2", "status": "fail", "exec_steps": 60, "accept": True, "t": 12.0},
                   {"id": "b2", "status": "success", "exec_steps": 30, "late": True}]),
        # 墙钟超时（步数不明）后重试成功 → 步后重试
        _entry(3, [{"id": "a3", "status": "error", "exec_steps": None, "infra": True, "infra_reason": "episode_wall"},
                   {"id": "b3", "status": "success", "exec_steps": 70, "accept": True, "t": 13.0}]),
        # 0 步 env_build 失败后重试：允许
        _entry(4, [{"id": "a4", "status": "error", "exec_steps": 0, "infra": True, "infra_reason": "env_build"},
                   {"id": "b4", "status": "timeout", "exec_steps": 1600, "accept": True, "t": 14.0}]),
        # 步数不明但在 reset 之前（env_build）：允许
        _entry(5, [{"id": "a5", "status": "error", "exec_steps": None, "infra": True, "infra_reason": "env_build"},
                   {"id": "b5", "status": "fail", "exec_steps": 5, "accept": True, "t": 15.0}]),
        # 规格指纹不符
        _entry(6, [{"id": "a6", "status": "fail", "exec_steps": 5, "accept": True}], spec="bad"),
    ]
    stage = ng._fx_v8_stage(tmp_path / "stage", "p", ents)
    ids = _ids(8)
    ids[6]["spec_sha256"] = "good"
    rows, meta = ng.extract_v8(stage, "p", ids)
    by = {r["seed"]: r for r in rows}
    assert by[0]["status"] == "success" and by[0]["attempt_id"] == "a0" and by[0]["started_at"] == 10.0
    assert by[0]["retried_after_steps"] is False
    assert by[1]["conflict"] == "multiple_accept"
    assert by[2]["status"] == "fail" and by[2]["retried_after_steps"] is True
    assert any(f.startswith("late:b2") for f in by[2]["flags"])
    assert by[3]["status"] == "success" and by[3]["retried_after_steps"] is True
    assert by[4]["status"] == "timeout" and by[4]["retried_after_steps"] is False
    assert by[5]["retried_after_steps"] is False
    assert by[6]["conflict"] == "spec_sha256_mismatch"
    assert by[7]["missing"] is True
    s = ng.extract_summary(rows, meta)
    # 冲突身份（seed 1）没有被接受的尝试，它的两次尝试都算步后重试
    assert s["missing"] == 1 and s["conflicts"] == 2 and s["retried_after_steps"] == 3


def test_v8_多运行根按规格指纹选根(tmp_path):
    # 身份 0：旧根接受了旧规格、新根接受了新规格 → 取新根；身份 1：两根都按新规格接受 → multiple_roots
    old = ng._fx_v8_stage(tmp_path / "old", "p", [
        _entry(0, [{"id": "o0", "status": "fail", "exec_steps": 9, "accept": True}], spec="old"),
        _entry(1, [{"id": "o1", "status": "fail", "exec_steps": 9, "accept": True}], spec="new")])
    new = ng._fx_v8_stage(tmp_path / "new", "p", [
        _entry(0, [{"id": "n0", "status": "success", "exec_steps": 7, "accept": True, "t": 5.0}], spec="new"),
        _entry(1, [{"id": "n1", "status": "success", "exec_steps": 7, "accept": True}], spec="new")])
    ids = _ids(2)
    for i in ids:
        i["spec_sha256"] = "new"
    rows, _meta = ng.extract_v8([old, new], "p", ids)
    assert rows[0]["status"] == "success" and rows[0]["attempt_id"] == "n0" and rows[0]["started_at"] == 5.0
    assert "ignored_root:r0:spec_sha256_mismatch" in rows[0]["flags"]
    assert rows[1]["conflict"] == "multiple_roots"
    rows, _meta = ng.extract_v8([old], "p", ids[:1])
    assert rows[0]["conflict"] == "spec_sha256_mismatch"


def test_v8_被接受的是基础设施错误判冲突(tmp_path):
    ents = [_entry(0, [{"id": "a0", "status": "error", "exec_steps": 3, "infra": True, "accept": True}])]
    rows, _ = ng.extract_v8(ng._fx_v8_stage(tmp_path / "s", "p", ents), "p", _ids(1))
    assert rows[0]["conflict"] == "accept_infra_error"


# ── 评估取数：旧路线 ───────────────────────────────────────────────────────


def _legacy(tmp_path, rows, rec=()):
    root = tmp_path / "legacy"
    (root / "p" / "rec").mkdir(parents=True, exist_ok=True)
    for name in rec:
        (root / "p" / "rec" / name).mkdir()
    base = {"policy": "p", "canary": False, "infra": False, "attempt": 1}
    ng.write_jsonl(root / "p" / "results.jsonl", [{**base, **r} for r in rows])
    return root


def _lid(n):
    return [{"id": ng.id_str("T", "xhard0", s), "task": "T", "tier": "xhard0", "seed": s, "source_episode": s}
            for s in range(n)]


def test_legacy_严格规则(tmp_path):
    rows = [
        {"task": "T", "seed": 0, "source_episode": 0, "status": "success", "steps": 100, "rec_dir": "/x/rec/T_0"},
        # 0 步 infra 前置重试：允许
        {"task": "T", "seed": 1, "source_episode": 1, "status": "error", "infra": True, "infra_reason": "env_build",
         "steps": 0, "rec_dir": "/x/rec/T_1"},
        {"task": "T", "seed": 1, "source_episode": 1, "status": "fail", "steps": 1301, "attempt": 2,
         "rec_dir": "/x/rec/T_1.a2"},
        # 连接断（steps>0 的 infra）后重试 → 步后重试
        {"task": "T", "seed": 2, "source_episode": 2, "status": "error", "infra": True, "infra_reason": "conn",
         "steps": 40, "rec_dir": "/x/rec/T_2"},
        {"task": "T", "seed": 2, "source_episode": 2, "status": "success", "steps": 90, "attempt": 2,
         "rec_dir": "/x/rec/T_2.a2"},
        # 两条非 infra 行 → 冲突
        {"task": "T", "seed": 3, "source_episode": 3, "status": "fail", "steps": 10, "rec_dir": "/x/rec/T_3"},
        {"task": "T", "seed": 3, "source_episode": 3, "status": "fail", "steps": 11, "rec_dir": "/x/rec/T_3.a2"},
        # 被 kill -9 的尝试只留录像目录 T_4（无结果行）→ orphan
        {"task": "T", "seed": 4, "source_episode": 4, "status": "success", "steps": 80, "attempt": 2,
         "rec_dir": "/x/rec/T_4.a2"},
        # canary 行不计
        {"task": "T", "seed": 0, "source_episode": 0, "status": "success", "steps": 5, "canary": True},
    ]
    root = _legacy(tmp_path, rows, rec=("T_0", "T_1", "T_1.a2", "T_2", "T_2.a2", "T_3", "T_3.a2", "T_4", "T_4.a2"))
    got, meta = ng.extract_legacy(root, "p", _lid(6))
    by = {r["seed"]: r for r in got}
    assert by[0]["status"] == "success" and not by[0]["retried_after_steps"]
    assert by[1]["status"] == "fail" and by[1]["exec_steps"] == 1301 and not by[1]["retried_after_steps"]
    assert by[2]["retried_after_steps"] is True
    assert by[3]["conflict"] == "multiple_final_rows"
    assert by[4]["retried_after_steps"] is True and any(f.startswith("orphan_attempt:T_4") for f in by[4]["flags"])
    assert by[5]["missing"] is True
    assert meta["rec_checked"] is True and meta["run_blocked"] == 0


def test_清单外身份_allow_extra(tmp_path):
    ents = [_entry(0, [{"id": "a0", "status": "success", "exec_steps": 5, "accept": True}]),
            _entry(9, [{"id": "a9", "status": "fail", "exec_steps": 5, "accept": True}])]
    stage = ng._fx_v8_stage(tmp_path / "s", "p", ents)
    _r, meta, ok, line = ng.eval_extract("v8", stage, "p", _ids(1))
    assert not ok and "extra=1" in line
    _r, meta, ok, _line = ng.eval_extract("v8", stage, "p", _ids(1), allow_extra=True)
    assert ok and meta["allow_extra"] is True


def test_legacy_run_blocked_整遍无效(tmp_path):
    rows = [{"task": "T", "seed": 0, "status": "success", "steps": 5, "rec_dir": "/x/rec/T_0"},
            {"task": "T", "seed": 0, "status": "error", "run_blocked": True, "steps": 0}]
    got, meta, ok, line = ng.eval_extract("legacy", _legacy(tmp_path, rows, rec=("T_0",)), "p", _lid(1))
    assert not ok and "run_blocked=1" in line and line.startswith("EVAL_EXTRACT=FAIL")


def test_legacy_墙钟超时后重试成功判步后重试(tmp_path):
    rows = [{"task": "T", "seed": 0, "status": "error", "infra": True, "infra_reason": "episode_wall", "steps": None,
             "rec_dir": "/x/rec/T_0"},
            {"task": "T", "seed": 0, "status": "success", "steps": 300, "attempt": 2, "rec_dir": "/x/rec/T_0.a2"}]
    got, _meta = ng.extract_legacy(_legacy(tmp_path, rows, rec=("T_0", "T_0.a2")), "p", _lid(1))
    assert got[0]["status"] == "success" and got[0]["retried_after_steps"] is True


# ── 新跑核验 ───────────────────────────────────────────────────────────────


def _ext(tmp_path, name, *, root, started, prefix):
    ext = ng._fx_extract(["success", "fail"], [10, 20], ids=_ids(2), root=root, aid_prefix=prefix, started=started)
    return ng.read_extract(ng._fx_write_extract(tmp_path / name, ext))


def test_run_fresh_v8(tmp_path):
    prov = {"pass": "g9-mme-1", "started_at": 50.0, "out_root": "/r1", "assets_sha": "abc", "fingerprint": "9" * 64,
            "out_root_state": "empty_dir"}
    first = _ext(tmp_path, "a.jsonl", root="/r1", started=100.0, prefix="a")
    ok, line, _ = ng.run_fresh(first, prov, 2, [])
    assert ok and line.startswith("RUN_FRESH=PASS pass=g9-mme-1 fresh=2/2 ledger_new=yes assets=PASS fingerprint=999999999999")
    # 起跑时间晚于被接受尝试（旧结果冒充）
    ok, line, why = ng.run_fresh(first, {**prov, "started_at": 100.5}, 2, [])
    assert not ok and "fresh=1/2" in line
    # 第二遍复用第一遍的 attempt_id 或输出根
    second = _ext(tmp_path, "b.jsonl", root="/r2", started=100.0, prefix="a")
    ok, _line, why = ng.run_fresh(second, {**prov, "out_root": "/r2"}, 2, [first])
    assert not ok and any(w.startswith("attempt_id_reused") for w in why)
    ok, _line, why = ng.run_fresh(first, prov, 2, [first])
    assert not ok and any(w.startswith("root_reused") for w in why)
    # 无资产记录
    ok, line, _ = ng.run_fresh(first, {**prov, "assets_sha": None}, 2, [])
    assert not ok and "assets=FAIL" in line


def test_run_fresh_legacy_输出根须为空(tmp_path):
    rows = [{"task": "T", "seed": 0, "status": "success", "steps": 5, "rec_dir": "/x/rec/T_0"}]
    root = _legacy(tmp_path, rows, rec=("T_0",))
    got, meta, _ok, _line = ng.eval_extract("legacy", root, "p", _lid(1))
    prov = {"pass": "d0", "out_root": str(root), "assets_sha": "a", "fingerprint": "x" * 64}
    for state in ("absent", "empty_dir"):
        ok, line, _ = ng.run_fresh((meta, got), {**prov, "out_root_state": state}, 1, [])
        assert ok and "ledger_new=yes" in line


@pytest.mark.parametrize("state", ["empty", "missing", "nonexistent", "EMPTY_DIR", "nonempty", None,
                                   {"exists": False}, {"exists": True, "entries": 0}])
def test_run_fresh_out_root_state_未知取值判FAIL(tmp_path, state):
    rows = [{"task": "T", "seed": 0, "status": "success", "steps": 5, "rec_dir": "/x/rec/T_0"}]
    root = _legacy(tmp_path, rows, rec=("T_0",))
    got, meta, _ok, _line = ng.eval_extract("legacy", root, "p", _lid(1))
    prov = {"pass": "d0", "out_root": str(root), "assets_sha": "a", "fingerprint": "x" * 64}
    if state is not None:
        prov["out_root_state"] = state
    ok, line, why = ng.run_fresh((meta, got), prov, 1, [])
    assert not ok and line.startswith("RUN_FRESH=FAIL") and "reason=" in line and "out_root_state" in line
    assert "out_root_state" in why
    # v8 格式同样严格
    ext = ng._fx_extract(["success"], [5], ids=_ids(1), root="/r9", started=100.0)
    prov8 = {"pass": "g", "started_at": 1.0, "out_root": "/r9", "assets_sha": "a", "fingerprint": "x" * 64}
    if state is not None:
        prov8["out_root_state"] = state
    ok, line, why = ng.run_fresh(ext, prov8, 1, [])
    assert not ok and "out_root_state" in why


# ── 评估两遍比较、冻结与闸门 ───────────────────────────────────────────────


def test_评估两遍指标():
    ids = _ids(4)
    a = ng._fx_extract(["success", "fail", "fail", "timeout"], [10, 20, 30, 1600], ids=ids)[1]
    b = ng._fx_extract(["fail", "success", "timeout", "timeout"], [10, 25, 1600, 1600], ids=ids)[1]
    m = ng.eval_pair_metrics(a, b)
    assert (m["status_changed"], m["s2f"], m["f2s"], m["net"]) == (3, 1, 1, 0)
    assert m["timeout_delta"] == 1 and m["steps_diff"] == 2
    assert m["steps_absdiff_mean"] == pytest.approx((5 + 1570) / 4)
    assert m["steps_absdiff_median"] == pytest.approx(2.5)


def test_freeze_verify_sha绑定与篡改检出(tmp_path):
    obj, ref = ng._noisy_eval_baseline(tmp_path)
    path = tmp_path / "nb.json"
    path.write_text(json.dumps(obj))
    ok, line, why = ng.verify(json.loads(path.read_text()))
    assert ok, why
    assert line.startswith("NOISE_BASELINE=PASS groups=1 inputs_bound=3 file_sha=")
    g = obj["groups"][0]
    assert g["lines"]["s2f"]["line"] >= max(g["lines"]["s2f"]["x"])
    assert g["bands"]["steps_absdiff_mean"]["band"] == pytest.approx(g["bands"]["steps_absdiff_mean"]["max_abs"] * 1.5)
    # 改一条线并重算顶层 sha：公式核对仍抓到
    t = json.loads(json.dumps(obj))
    t["groups"][0]["lines"]["f2s"]["line"] += 3
    t["sha256"] = ng.payload_sha256(t)
    ok, _line, why = ng.verify(t)
    assert not ok and any("line_formula" in w for w in why)
    # 改一条线不改 sha
    t = json.loads(json.dumps(obj))
    t["groups"][0]["lines"]["f2s"]["line"] += 3
    ok, _line, why = ng.verify(t)
    assert not ok and "top_sha256_mismatch" in why
    # 改输入报告：sha 不符
    lines = ref.read_text().splitlines()
    ref.write_text("\n".join(lines[:-1]) + "\n")
    ok, _line, why = ng.verify(obj)
    assert not ok and any("input_sha_mismatch" in w for w in why)


def test_freeze_拒冻结结构不同或原因不明(tmp_path):
    meta = {"kind": "meta", "schema": ng.GEN_SCHEMA}
    rows = [{"kind": "pair", "id": "T|xhard1|0", "task": "T", "class": "structural"}]
    p = ng.write_jsonl(tmp_path / "g.jsonl", [meta, *rows])
    with pytest.raises(ng.GateError):
        ng.freeze({"groups": [{"kind": "gen", "set": "G9", "workers": 4, "pairs": [str(p)]}]})


def test_零噪声组要求逐局全同(tmp_path):
    ids = _ids(10)
    st = ["success"] * 5 + ["fail"] * 5
    sp = list(range(10, 20))
    a = ng._fx_write_extract(tmp_path / "a.jsonl", ng._fx_extract(st, sp, ids=ids))
    b = ng._fx_write_extract(tmp_path / "b.jsonl", ng._fx_extract(st, sp, ids=ids, aid_prefix="b"))
    obj = ng.freeze({"groups": [{"kind": "eval", "set": "D0", "policy": "smvla", "pairs": [[str(a), str(b)]],
                                 "reference": str(a)}]})
    g = ng.find_group(obj, "eval:D0:smvla")
    assert g["zero_noise"] is True
    _m, ra = ng.read_extract(a)
    ok, line, _w, _ = ng.gate_eval(g, ra, ng._fx_extract(st, sp, ids=ids)[1])
    assert ok and "mode=zero" in line
    sp2 = list(sp)
    sp2[0] += 1
    ok, _line, why, _ = ng.gate_eval(g, ra, ng._fx_extract(st, sp2, ids=ids)[1])
    assert not ok and why == ["steps_diff=1>0"]


def test_净损失常量来自用户裁决():
    assert ng.NET_LOSS_MAX == 4


def test_check_reset(tmp_path):
    def cmp(details):
        layers = ("identity", "pre_demo_state")
        return {"compared": len(details), "missing_in_a": [], "missing_in_b": [],
                "layer_equal": {k: sum(d["layers"][k]["equal"] for d in details) for k in layers},
                "name_only": {k: sum(bool(d["layers"][k].get("name_only")) for d in details) for k in layers},
                "details": details}
    eq = {"identity": {"equal": True}, "pre_demo_state": {"equal": True}}
    nm = {"identity": {"equal": True}, "pre_demo_state": {"equal": False, "name_only": True, "key_set_diff": True}}
    df = {"identity": {"equal": True}, "pre_demo_state": {"equal": False, "diff_keys": ["x"]}}
    base = tmp_path / "base.json"
    base.write_text(json.dumps(cmp([{"id": "A", "layers": eq}, {"id": "B", "layers": nm}])))
    obj = ng.freeze({"groups": [{"kind": "reset", "set": "G9", "compare": [str(base)]}]})
    g = ng.find_group(obj, "reset:G9")
    assert g["name_only_ids"] == ["B"]
    ok, line, _ = ng.gate_reset(g, cmp([{"id": "A", "layers": eq}, {"id": "B", "layers": nm}]))
    assert ok and line.startswith("RESET_GATE=PASS")
    ok, _line, why = ng.gate_reset(g, cmp([{"id": "A", "layers": nm}, {"id": "B", "layers": nm}]))
    assert not ok and "new_name_only=1" in why
    ok, _line, why = ng.gate_reset(g, cmp([{"id": "A", "layers": df}, {"id": "B", "layers": eq}]))
    assert not ok and "layer_diff=1" in why


def test_cli_gen_compare_与_check_gen(tmp_path, capsys):
    ref_root, new_root = _two_sides(tmp_path, {1: {"diverge_at": 1}}, n=3)
    idf = ng.write_jsonl(tmp_path / "ids.jsonl", [{"task": "T", "tier": "xhard1", "seed": s} for s in range(3)])
    out = tmp_path / "pair.jsonl"
    assert ng.main(["gen-compare", "--ref", str(ref_root), "--new", str(new_root), "--identities", str(idf),
                    "--out", str(out)]) == 0
    assert "GEN_PAIR=INFO" in capsys.readouterr().out
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps({"conditions": {"gpu": "A40"},
                                "groups": [{"kind": "gen", "set": "G9", "workers": 4, "pairs": [str(out)]}]}))
    nb = tmp_path / "nb.json"
    assert ng.main(["freeze", "--spec", str(spec), "--out", str(nb)]) == 0
    assert ng.main(["verify", "--path", str(nb)]) == 0
    assert ng.main(["check-gen", "--baseline", str(nb), "--set", "G9", "--workers", "4", "--pair", str(out)]) == 0
    assert "GEN_NOISE_GATE=PASS" in capsys.readouterr().out
    # 篡改输入报告 → 拒跑
    out.write_text(out.read_text() + "\n")
    assert ng.main(["check-gen", "--baseline", str(nb), "--set", "G9", "--workers", "4", "--pair", str(out)]) == 2


# ── selftest 本身 ──────────────────────────────────────────────────────────


def test_selftest():
    ok, line, cases = ng.selftest(verbose=False)
    assert ok, (line, cases)
    assert line.startswith("GATE_SELFTEST=PASS same_code=PASS cases_fail=")
    k = line.split("cases_fail=")[1]
    good, total = map(int, k.split("/"))
    assert good == total >= 9
