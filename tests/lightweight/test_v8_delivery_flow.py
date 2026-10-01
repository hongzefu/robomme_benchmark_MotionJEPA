#!/usr/bin/env python3
"""轻量测试：v8 抽签封存、生成驱动、分片合并与聚合（v8 方案第二部分 §2.2 第 5～7 条、§2.12 S2-B 行）。

纯 CPU 合成夹具，不起仿真、不 reset：抽签行用合成规格经 ``_freeze.freeze(schema="hard-specs/4")`` 封签；
生成用 monkeypatch 把 ``_rollout.run_batch`` 换成假 runner（在显式局目录里写假 h5／mp4、直接给出执行步）。覆盖：

* 候选表合计 1425、四片恰好覆盖 43 格 1070 局、冒烟 7 格；``freeze_specs.plan_v8`` 的逐任务 CLI；
* freeze v8 写出的 /4 能通过 ``load_specs_v8``（冒烟根、分片子集根）；MoveCube 分层 + 逐格配额；选不满即拒；
* ``h5_facts.exec_steps`` = timestep 数 − 演示帧；
* ``generate_h5 --mode continue`` 在合成冒烟根上退出码 0，``delivery.json`` 计数键显式零值（写 JSON → 读 JSON → 守卫）；
* 执行步超限 → ``exec_over_cap``、同格递补、旧 h5／mp4 被删；备用耗尽 → 该格 FAIL、其余格照常交付、退出码 1；
* 基础设施重试账本跨重启保留（每身份 ≤ 1 次）；
* 分片：split → 各片 continue（``expected_cells`` 按片）→ 片未齐拒绝合并 → 全部片齐后合并核 43 格
  ``V8_DELIVERY_SET=PASS tasks=16 cells=43 total=1070``，合并结果逐字节确定、签与冻结根逐档相同；
* replay 读 v8 根含 xhard5；``_report`` 读逐任务配额；``export_eval_identities`` 的 1262 口径。

    uv run --no-sync python -m pytest tests/lightweight/test_v8_delivery_flow.py -q
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "injection-dev"))

import _freeze  # noqa: E402
import _report  # noqa: E402
import _rollout  # noqa: E402
import export_eval_identities  # noqa: E402
import freeze_specs  # noqa: E402
import generate_h5  # noqa: E402
from robomme_hard.env_record_wrapper import hard_specs as H  # noqa: E402

SMOKE = _rollout.V8_SMOKE_CELLS


# ── 合成抽签 + 封存 ─────────────────────────────────────────────────────


def _drafts(task: str, tier: str, candidates: int, fail_attempts: dict[int, int] | None = None) -> list[dict]:
    """合成抽签行：``fail_attempts={episode: 失败次数}`` 模拟 reset 失败（attempt 递增，seed 随公式变）。"""
    rule = H.seed_rule_for(tier, "v8")
    rows = []
    for episode in range(candidates):
        for attempt in range((fail_attempts or {}).get(episode, 0) + 1):
            ok = attempt == (fail_attempts or {}).get(episode, 0)
            spec = {"spec_kind": "native-newvalue/2", "task": task, "tier": tier, "layout": {"x": episode}}
            if task == "MoveCube":
                spec["initializations"] = {"0": {"way_idx": 0}, "1": {"way_idx": episode % 3}}
            rows.append({"task": task, "difficulty": tier, "episode": episode, "attempt": attempt,
                         "seed": H.seed_for(task, episode, attempt, rule), "reset_ok": ok,
                         "spec": spec if ok else None, "spec_sha256": H.spec_sha256(spec) if ok else None})
    return rows


def _parts(tier: str, tasks: list[str]) -> dict:
    return {"difficulty": tier, "tasks": list(tasks), "seed_rule": H.seed_rule_for(tier, "v8"),
            "sampling_config": {t: {"decision": {"k": t, "tier": tier}, "native": {}} for t in tasks},
            "recovery_rule": {"rule": "off"}, "identity_source": "formula", "run_id": f"v8-flow-{tier}",
            "draw_stats": {}, "provenance": {}}


def freeze_tier(tier: str, cells: dict, spare: int = 2, spares: dict | None = None):
    tasks = [t for t in H.ALL_TASKS if (t, tier) in cells]
    cands = {t: cells[(t, tier)] + (spares or {}).get((t, tier), spare) for t in tasks}
    drafts = [row for t in tasks for row in _drafts(t, tier, cands[t])]
    select = {t: tuple(range(cells[(t, tier)])) for t in tasks}
    return _freeze.freeze(drafts, _parts(tier, tasks), select, cands, schema=H.SCHEMA_V8)


def build_root(root: Path, cells: dict, spare: int = 2, spares: dict | None = None) -> Path:
    for tier in _rollout.cell_tiers(cells):
        header, rows = freeze_tier(tier, cells, spare, spares)
        _freeze.write_jsonl_exclusive(root / tier / "specs.jsonl", [header, *rows])
    return root


# ── 假 runner ──────────────────────────────────────────────────────────


class FakeRunner:
    """代替 ``_rollout.run_batch``：在显式局目录写假 h5／mp4 与 runner partial，按 ``plan`` 给结果。

    ``plan[(tier, task, candidate)]``：``"ok"``（默认，执行步 100）、``"fail"``（规划失败）、``"over"``（执行步
    1601）、``"infra"``（基础设施失败）、``"crash"``（抛 KeyboardInterrupt 模拟中断）；值为列表时按调用次序逐次取。"""

    def __init__(self, plan: dict | None = None):
        self.plan = {k: (list(v) if isinstance(v, list) else v) for k, v in (plan or {}).items()}
        self.calls: list[list[tuple]] = []

    def _action(self, key):
        value = self.plan.get(key, "ok")
        if isinstance(value, list):
            return value.pop(0) if len(value) > 1 else value[0]
        return value

    def __call__(self, batch, header, out_dir, round_index, **kw):
        out_dir = Path(out_dir)
        tier = header["difficulty"]
        self.calls.append([(r["tier"], r["task"], r["candidate"]) for r in batch])
        work = out_dir / "_rounds" / f"{tier}_round_{round_index:02d}"
        work.mkdir(parents=True, exist_ok=True)
        out = []
        for row in batch:
            action = self._action((tier, row["task"], row["candidate"]))
            if action == "crash":
                raise KeyboardInterrupt("模拟中断")
            wdir = _rollout.episode_dir(out_dir, row)
            record = {"task": row["task"], "tier": tier, "candidate": row["candidate"], "episode": row["episode"],
                      "seed": row["seed"], "attempt": row["attempt"], "spec_sha256": row["spec_sha256"],
                      "ok": action in ("ok", "over"), "error_type": None, "error": None, "spec_binding": None,
                      "env_package": "robomme_hard", "env_module": f"robomme_hard.robomme_env.{row['task']}",
                      "wrapper_modules": None, "h5": None, "round": round_index, "role": row.get("_role", "selected")}
            if record["ok"]:
                h5 = wdir / "hdf5_files" / f"{row['task']}_ep{row['episode']}_seed{row['seed']}.h5"
                h5.parent.mkdir(parents=True, exist_ok=True)
                payload = f"h5-{tier}-{row['task']}-{row['candidate']}".encode()
                h5.write_bytes(payload)
                (wdir / "videos").mkdir(exist_ok=True)
                (wdir / "videos" / f"{row['task']}_ep{row['episode']}_seed{row['seed']}_demo.mp4").write_bytes(b"mp4")
                steps = H.V8_EXEC_CAP + 1 if action == "over" else 100
                record.update(h5=str(h5), h5_sha256=hashlib.sha256(payload).hexdigest(), bytes=len(payload),
                              frames=steps + 5, exec_steps=steps)
            elif action == "infra":
                record.update(error_type="RunnerCrash", error="svulkan2 设备丢失")
            else:
                record.update(error_type="ScrewPlanFailure", error="规划失败")
            with (work / "results.partial.jsonl").open("a") as stream:
                stream.write(json.dumps({"task": row["task"], "episode": row["episode"], "difficulty": tier}) + "\n")
            out.append(record)
        return out


@pytest.fixture
def fake(monkeypatch):
    def install(plan=None):
        runner = FakeRunner(plan)
        monkeypatch.setattr(_rollout, "run_batch", runner)
        return runner

    monkeypatch.setattr(generate_h5, "_launch_facts", lambda src_root: {
        "gpu_model": "NVIDIA A40", "driver": "fixture", "src_commit": "fixture", "host": "fixture", "slurm_job": None})
    monkeypatch.setattr(generate_h5, "_git_head", lambda src_root: "fixture")
    return install


def _gen(monkeypatch, *argv) -> int:
    monkeypatch.setattr(sys, "argv", ["generate_h5.py", *map(str, argv)])
    return generate_h5.main()


def _guard_delivery(path: Path) -> dict:
    """写 JSON → 读 JSON → 守卫：计数键全部显式存在（零值也写）、逐格同样齐全。"""
    data = json.loads(path.read_text())
    assert data["schema"] == "v8-delivery/1"
    assert set(_rollout.V8_TOTAL_COUNT_KEYS) <= set(data["counts"]), data["counts"]
    for key in ("exec_over_cap", "backfills", "infra_retries", "failed"):
        assert isinstance(data["counts"][key], int)
    assert isinstance(data["cells"], dict)
    for name, cell in data["cells"].items():
        assert name == f"{cell['task']}/{cell['tier']}"
        assert set(_rollout.V8_CELL_COUNT_KEYS) <= set(cell)
    # 两方统一的行口径：h5 绝对路径、path 为同一文件相对 delivery.json 所在目录、candidate == episode
    for r in data["rows"]:
        assert {"task", "tier", "episode", "candidate", "seed", "exec_steps", "frames", "h5", "path", "h5_sha256",
                "env_module"} <= set(r)
        assert r["candidate"] == r["episode"] and Path(r["h5"]).is_absolute()
        assert (path.parent / r["path"]).resolve() == Path(r["h5"]).resolve()
        assert r["env_module"] == f"robomme_hard.robomme_env.{r['task']}"
    return data


# ── 常量与 CLI 计划 ─────────────────────────────────────────────────────


def test_候选表与四片与冒烟格表():
    assert sum(_freeze.V8_DEFAULT_CANDIDATES.values()) == 1425
    assert set(_freeze.V8_DEFAULT_CANDIDATES) == set(H.V8_CELLS)
    shards = {name: _rollout.resolve_cells(name) for name in ("shard1", "shard2", "shard3", "shard4")}
    keys = [k for cells in shards.values() for k in cells]
    assert len(keys) == len(set(keys)) == 43 and set(keys) == set(H.V8_CELLS)
    assert sum(sum(c.values()) for c in shards.values()) == 1070
    smoke = _rollout.resolve_cells("smoke")
    assert len(smoke) == 7 and len({t for t, _ in smoke}) == 6 and sum(smoke.values()) == 7
    assert _rollout.resolve_cells("full") == _rollout.order_cells(H.V8_CELLS)
    with pytest.raises(_rollout.RolloutError, match="V8_CELLS 之外"):
        _rollout.check_cells({("MoveCube", "xhard1"): 1})


def test_plan_v8逐任务CLI与dry_run(capsys, monkeypatch, tmp_path):
    full = _rollout.resolve_cells("full")
    total_cands = total_quota = 0
    for tier in H.V8_TIERS:
        plan = freeze_specs.plan_v8(tier, full, "all", None, "default", None, None)
        assert set(plan["tasks"]) == {t for t, ti in H.V8_CELLS if ti == tier}  # 只抽交付格
        total_cands += sum(plan["candidates"].values())
        total_quota += sum(plan["quota"].values())
        for task in plan["tasks"]:
            assert plan["select"][task] == tuple(range(H.V8_CELLS[(task, tier)]))
            assert plan["reset_caps"][task] == _freeze.v8_reset_cap(task, plan["candidates"][task])
    assert (total_cands, total_quota) == (1425, 1070)
    plan = freeze_specs.plan_v8("xhard1", full, "BinFill,VideoPlaceButton", "BinFill=60,VideoPlaceButton=55",
                                "BinFill=5..44", None, "BinFill@xhard1=200,VideoPlaceButton@xhard2=1")
    assert plan["candidates"] == {"BinFill": 60, "VideoPlaceButton": 55}
    assert plan["select"]["BinFill"] == tuple(range(5, 45)) and plan["select"]["VideoPlaceButton"] == tuple(range(40))
    assert plan["reset_caps"]["BinFill"] == 200  # @xhard2 的条目对 xhard1 不生效
    assert plan["reset_caps"]["VideoPlaceButton"] == _freeze.v8_reset_cap("VideoPlaceButton", 55)
    assert _freeze.v8_reset_cap("VideoPlaceButton", 52) == 170  # ⌈52 ÷ 0.46 × 1.5⌉
    with pytest.raises(H.SpecsError, match="不在 xhard3 交付格"):
        freeze_specs.plan_v8("xhard3", full, "BinFill", None, "default", None, None)
    with pytest.raises(H.SpecsError, match="配额"):
        freeze_specs.plan_v8("xhard1", full, "BinFill", None, "BinFill=0..9", None, None)
    # 全局旧写法兼容
    plan = freeze_specs.plan_v8("xhard5", full, "all", "15", "0..9", 40, None)
    assert plan["candidates"] == {"StopCube": 15, "SwingXtimes": 15} and plan["reset_caps"]["StopCube"] == 40
    # --dry-run：逐格打印，不写盘
    out = tmp_path / "x" / "specs.jsonl"
    monkeypatch.setattr(sys, "argv", ["freeze_specs.py", "--tier", "xhard5", "--seed-profile", "v8", "--cells", "full",
                                      "--out", str(out), "--dry-run"])
    assert freeze_specs.main() == 0
    text = capsys.readouterr().out
    assert text.count("FREEZE_CELL tier=xhard5") == 2 and "FREEZE_PLAN profile=v8 tier=xhard5" in text
    assert "candidates=26" in text and not out.exists()


def test_draw_rows_by_task逐任务候选数():
    calls = []

    def draw_one(task, seed, episode, sampling):
        calls.append((task, episode))
        ok = not (task == "BinFill" and episode == 1 and sum(c == ("BinFill", 1) for c in calls) == 1)
        spec = {"spec_kind": "native-newvalue/2", "task": task, "layout": {"x": episode}}
        return ok, (spec if ok else None), (None if ok else "SceneGenerationError"), None

    rule = H.seed_rule_for("xhard1", "v8")
    rows, stats = freeze_specs.draw_rows_by_task(["BinFill", "PickXtimes"], {"BinFill": {}, "PickXtimes": {}},
                                                 {"BinFill": 3, "PickXtimes": 2}, {"BinFill": 10, "PickXtimes": 10},
                                                 difficulty="xhard1", seed_rule=rule, draw_one=draw_one)
    ok = [(r["task"], r["episode"]) for r in rows if r["reset_ok"]]
    assert ok == [("BinFill", 0), ("BinFill", 1), ("BinFill", 2), ("PickXtimes", 0), ("PickXtimes", 1)]
    assert stats["per_task"]["BinFill"] == {"attempted": 4, "ok": 3, "fail_class": {"SceneGenerationError": 1}}
    retry = next(r for r in rows if r["task"] == "BinFill" and r["episode"] == 1 and r["reset_ok"])
    assert retry["attempt"] == 1 and retry["seed"] == H.seed_for("BinFill", 1, 1, rule)


# ── freeze v8 → /4 → load_specs_v8 ──────────────────────────────────────


def test_freeze_v8写出的规格过load_specs_v8(tmp_path):
    root = build_root(tmp_path / "smoke", SMOKE)
    loaded = H.load_specs_v8(root, SMOKE, check_fingerprint=False)
    assert list(loaded) == ["xhard1", "xhard2", "xhard3", "xhard5"]
    header, rows = loaded["xhard1"]
    assert header["schema"] == H.SCHEMA_V8 and header["layout_rule"] == {"mode": "independent"}
    assert header["exec_cap"] == 1600 and header["delivery_per_cell"] == {"StopCube": 1, "VideoUnmask": 1}
    assert header["per_env"] == {"StopCube": 3, "VideoUnmask": 3} and header["select_rule"]["StopCube"] == [0]
    assert header["seed_rule"] == H.seed_rule_for("xhard1", "v8")
    assert header["draw_stats"]["freeze_per_env"]["StopCube"]["candidates_requested"] == 3
    assert all(r["layout_parent"] is None and r["candidate"] == r["episode"] for r in rows)
    # 抽签里有 reset 失败（attempt>0）也能封
    drafts = _drafts("BinFill", "xhard2", 4, fail_attempts={1: 2})
    header, rows = _freeze.freeze(drafts, _parts("xhard2", ["BinFill"]), {"BinFill": (0, 1)}, {"BinFill": 4},
                                  schema=H.SCHEMA_V8)
    assert [r["attempt"] for r in rows] == [0, 2, 0, 0] and header["draw_stats"]["freeze_per_env"]["BinFill"]["attempted"] == 6
    # MoveCube：逐格配额 + 运动方式分层
    drafts = _drafts("MoveCube", "xhard4", 8)
    header, rows = _freeze.freeze(drafts, _parts("xhard4", ["MoveCube"]), {"MoveCube": (0, 1, 2, 3, 4)},
                                  {"MoveCube": 8}, schema=H.SCHEMA_V8)
    chosen = header["select_rule"]["MoveCube"]
    assert len(chosen) == 5 and {c % 3 for c in chosen} == {0, 1, 2}
    # 选不满配额、调用方给 layout_rule、全局 TIERS 外的 xhard5 走 /3 都拒
    with pytest.raises(H.SpecsError, match="选不满配额"):
        _freeze.freeze(_drafts("BinFill", "xhard1", 2), _parts("xhard1", ["BinFill"]), {"BinFill": (0, 1, 2)}, 2,
                       schema=H.SCHEMA_V8)
    with pytest.raises(H.SpecsError, match="layout_rule"):
        _freeze.freeze(_drafts("BinFill", "xhard1", 2), {**_parts("xhard1", ["BinFill"]), "layout_rule": {}},
                       {"BinFill": (0,)}, 2, schema=H.SCHEMA_V8)
    with pytest.raises(H.SpecsError, match="未知档位"):
        _freeze.freeze(_drafts("StopCube", "xhard5", 2), _parts("xhard5", ["StopCube"]), (0,), 2, schema=H.SCHEMA)


def test_h5_facts执行步口径(tmp_path):
    h5py = pytest.importorskip("h5py")
    path = tmp_path / "ep.h5"
    with h5py.File(path, "w") as handle:
        ep = handle.create_group("episode_0")
        for i in range(7):
            ep.create_dataset(f"timestep_{i}/info/is_video_demo", data=i < 3)
        ep.create_dataset("setup/x", data=1)
    facts = _rollout.h5_facts(path)
    assert facts["frames"] == 7 and facts["exec_steps"] == 4 and len(facts["h5_sha256"]) == 64


# ── continue（冒烟根）、超限、备用耗尽、账本 ─────────────────────────────────


def test_generate_h5冒烟根continue退出码0(tmp_path, fake, monkeypatch, capsys):
    root = build_root(tmp_path / "specs", SMOKE)
    runner = fake()
    assert _gen(monkeypatch, "--mode", "continue", "--specs", root, "--cells", "smoke", "--output", tmp_path / "out") == 0
    text = capsys.readouterr().out
    assert "V8_DELIVERY_SET=PASS tasks=6 cells=7 total=7 expected=7 failed=0 exec_over_cap=0 backfills=0 " \
           "infra_retries=0 exhausted_cells=0 pending_cells=0" in text
    data = _guard_delivery(tmp_path / "out" / "delivery.json")
    assert data["counts"]["exec_over_cap"] == 0 and data["counts"]["backfills"] == 0
    assert data["counts"]["infra_retries"] == 0 and data["counts"]["failed"] == 0
    assert len(data["rows"]) == 7 and all(Path(r["h5"]).is_file() for r in data["rows"])
    assert all(r["exec_steps"] == 100 and r["frames"] == 105 for r in data["rows"])
    # 可选 video：局目录 videos/ 下含 _seed<seed>_ 的唯一 mp4（绝对路径）
    assert all(Path(r["video"]).is_absolute() and f"_seed{r['seed']}_" in r["video"] for r in data["rows"])
    assert {r["tier"] for r in data["rows"]} == {"xhard1", "xhard2", "xhard3", "xhard5"}
    assert len(runner.calls) == 4  # 每档一批
    # 回写后的规格仍可按冒烟格表加载；身份签不变
    loaded = H.load_specs_v8(root, SMOKE, check_fingerprint=False)
    assert sum(H.delivered(r) for _, rows in loaded.values() for r in rows) == 7
    # 同一输出再跑（不带 --resume）拒绝
    with pytest.raises(_rollout.RolloutError, match="运行痕迹"):
        _gen(monkeypatch, "--mode", "continue", "--specs", root, "--cells", "smoke", "--output", tmp_path / "out")


def test_执行步超限同格递补并删旧h5(tmp_path, fake, monkeypatch, capsys):
    cells = {("SwingXtimes", "xhard5"): 2, ("StopCube", "xhard5"): 1}
    root = build_root(tmp_path / "specs", cells, spare=2)
    fake({("xhard5", "SwingXtimes", 0): "over"})
    out = tmp_path / "out"
    victim = _rollout.episode_dir(out, {"tier": "xhard5", "task": "SwingXtimes", "episode": 0})
    _write_cells(tmp_path / "cells.json", cells)
    assert _gen(monkeypatch, "--mode", "continue", "--specs", root, "--cells", tmp_path / "cells.json",
                "--output", out) == 0
    assert "V8_DELIVERY_SET=PASS tasks=2 cells=2 total=3" in capsys.readouterr().out
    _, rows = H.load_specs(root / "xhard5" / "specs.jsonl", check_fingerprint=False)
    over = next(r for r in rows if r["task"] == "SwingXtimes" and r["candidate"] == 0)
    assert (over["selected"], over["tried"], over["rollout"]["status"]) == (False, True, "failed")
    assert over["rollout"]["error_type"] == "exec_over_cap" and over["rollout"]["exec_steps"] == 1601
    assert over["rollout"]["purged_files"] == 2
    assert not list(victim.rglob("*.h5")) and not list(victim.rglob("*.mp4"))  # 显式局目录里的 h5／mp4 已删
    backfill = next(r for r in rows if r["task"] == "SwingXtimes" and r["candidate"] == 2)
    assert H.delivered(backfill) and not backfill["initial_selected"]
    data = _guard_delivery(out / "delivery.json")
    assert data["counts"]["exec_over_cap"] == 1 and data["counts"]["backfills"] == 1 and data["counts"]["failed"] == 1
    assert data["exec_over_cap_rows"] == [{"task": "SwingXtimes", "tier": "xhard5", "candidate": 0,
                                           "seed": over["seed"], "exec_steps": 1601}]
    # 其他局的文件没被波及
    keep = _rollout.episode_dir(out, {"tier": "xhard5", "task": "SwingXtimes", "episode": 1})
    assert list(keep.rglob("*.h5"))


def _write_cells(path: Path, cells: dict) -> None:
    path.write_text(json.dumps(_rollout.cells_json(cells)))


def test_备用耗尽该格FAIL其余格继续(tmp_path, fake, monkeypatch, capsys):
    cells = {("InsertPeg", "xhard4"): 2, ("MoveCube", "xhard4"): 2}
    root = build_root(tmp_path / "specs", cells, spares={("InsertPeg", "xhard4"): 1, ("MoveCube", "xhard4"): 1})
    fake({("xhard4", "InsertPeg", 0): "fail", ("xhard4", "InsertPeg", 2): "fail"})
    _write_cells(tmp_path / "cells.json", cells)
    rc = _gen(monkeypatch, "--mode", "continue", "--specs", root, "--cells", tmp_path / "cells.json",
              "--output", tmp_path / "out")
    text = capsys.readouterr().out
    assert rc == 1 and "V8_DELIVERY_SET=FAIL tasks=2 cells=2 total=3 expected=4" in text
    assert "exhausted_cells=1" in text and " problems=InsertPeg/xhard4:exhausted" in text  # 无空格 k=v 形式
    data = _guard_delivery(tmp_path / "out" / "delivery.json")
    ip, mc = data["cells"]["InsertPeg/xhard4"], data["cells"]["MoveCube/xhard4"]
    assert ip["status"] == "FAIL" and ip["reason"] == "exhausted" and ip["spares_left"] == 0 and ip["failed"] == 2
    assert ip["exec_over_cap"] == 0 and ip["backfills"] == 1 and ip["infra_retries"] == 0
    assert mc["status"] == "PASS" and mc["delivered"] == 2 and mc["failed"] == 0


def test_基础设施重试账本跨重启保留(tmp_path, fake, monkeypatch):
    cells = {("PickXtimes", "xhard3"): 2}
    root = build_root(tmp_path / "specs", cells, spare=1)
    out = tmp_path / "out"
    # 第一次：PickXtimes/0 基础设施失败（记账本、下一轮重试），重试轮中断
    runner = fake({("xhard3", "PickXtimes", 0): ["infra", "crash"]})
    with pytest.raises(KeyboardInterrupt):
        _rollout.run_continue_v8(root, cells, out, src_root=REPO, workers=1, gpu="0", pkg="robomme_hard",
                                 code_baseline="fixture")
    ledger = _rollout.read_ledger(out / _rollout.LEDGER_NAME)
    assert [e["kind"] for e in ledger] == ["infra_retry", "result"]
    assert not Path(str(root / "xhard3" / "specs.jsonl") + ".lock").exists()
    # 重启（--resume）：账本里的 1 次重试已用完 → 这次的基础设施失败按最终失败处理并递补，不再重试
    runner = fake({("xhard3", "PickXtimes", 0): "infra"})
    summary = _rollout.run_continue_v8(root, cells, out, src_root=REPO, workers=1, gpu="0", pkg="robomme_hard",
                                       code_baseline="fixture", resume=True)
    assert runner.calls == [[("xhard3", "PickXtimes", 0)], [("xhard3", "PickXtimes", 2)]]
    assert summary["delivery_set"].startswith("V8_DELIVERY_SET=PASS") and summary["infra_retries"] == 1
    kinds = [e["kind"] for e in _rollout.read_ledger(out / _rollout.LEDGER_NAME)]
    assert kinds.count("infra_retry") == 1 and kinds.count("result") == 3
    # 中断前的轮次号保留，重启后接着编（账本最大轮次 0 → 新轮次从 1 起）
    rounds = [e["round"] for e in _rollout.read_ledger(out / _rollout.LEDGER_NAME)]
    assert rounds == sorted(rounds) and rounds[0] == 0 and min(rounds[2:]) >= 1
    data = _guard_delivery(out / "delivery.json")
    assert data["counts"]["infra_retries"] == 1 and data["counts"]["backfills"] == 1


# ── 分片 → 合并 → 聚合 ────────────────────────────────────────────────────


def test_分片子集根往返(tmp_path):
    full = _rollout.resolve_cells("full")
    frozen = build_root(tmp_path / "frozen", full, spare=1)
    shard_cells = _rollout.resolve_cells("shard3")
    _rollout.split_v8(frozen, shard_cells, tmp_path / "s3", label="shard3")
    loaded = H.load_specs_v8(tmp_path / "s3" / "specs", shard_cells, check_fingerprint=False)
    assert set(loaded) == {t for _, t in shard_cells}
    assert {t for header, _ in loaded.values() for t in header["tasks"]} == set(_rollout.V8_SHARD_TASKS["shard3"])
    with pytest.raises(H.SpecsError):
        H.load_specs_v8(tmp_path / "s3" / "specs", full, check_fingerprint=False)  # 子集根不冒充完整根
    with pytest.raises(_rollout.RolloutError, match="禁止覆盖"):
        _rollout.split_v8(frozen, shard_cells, tmp_path / "s3", label="shard3")


def test_四片生成合并聚合43格(tmp_path, fake, monkeypatch, capsys):
    full = _rollout.resolve_cells("full")
    frozen = build_root(tmp_path / "frozen", full, spare=1)
    identities = {t: H.load_specs(frozen / t / "specs.jsonl", check_fingerprint=False)[0]["identity_sha256"]
                  for t in H.V8_TIERS}
    gen1 = tmp_path / "gen1"
    fake({("xhard1", "BinFill", 3): "over", ("xhard2", "VideoRepick", 0): "fail"})
    for k in range(1, 5):
        shard = gen1 / f"shard{k}"
        assert _gen(monkeypatch, "--mode", "split", "--specs", frozen, "--cells", f"shard{k}", "--output", shard) == 0
        if k == 4:
            # 片未齐：只有 3 片跑完时合并必须拒绝
            with pytest.raises(_rollout.RolloutError, match="分片未齐"):
                _gen(monkeypatch, "--mode", "merge", "--specs", frozen, "--cells", "full",
                     "--shards", ",".join(str(gen1 / f"shard{i}") for i in range(1, 4)), "--output", gen1 / "partial")
            # 已切片但未跑：合并拒绝
            with pytest.raises(_rollout.RolloutError, match="尚未跑完"):
                _gen(monkeypatch, "--mode", "merge", "--specs", frozen, "--cells", "full",
                     "--shards", ",".join(str(gen1 / f"shard{i}") for i in range(1, 5)), "--output", gen1 / "early")
        assert _gen(monkeypatch, "--mode", "continue", "--specs", shard / "specs", "--cells", f"shard{k}",
                    "--output", shard) == 0
        assert (shard / "delivery.json").is_file()
    capsys.readouterr()
    shards = ",".join(str(gen1 / f"shard{k}") for k in range(1, 5))
    assert _gen(monkeypatch, "--mode", "merge", "--specs", frozen, "--cells", "full", "--shards", shards,
                "--specs-out", tmp_path / "specs-root", "--output", gen1 / "merged") == 0
    text = capsys.readouterr().out
    assert "V8_MERGE=PASS shards=4 tiers=5 cells=43" in text
    assert "V8_DELIVERY_SET=PASS tasks=16 cells=43 total=1070 expected=1070 failed=2 exec_over_cap=1 backfills=2 " \
           "infra_retries=0 exhausted_cells=0 pending_cells=0" in text
    data = _guard_delivery(gen1 / "merged" / "delivery.json")
    assert data["cell_count"] == 43 and len(data["rows"]) == 1070 and data["tasks"] == 16
    assert all((gen1 / "merged" / r["path"]).is_file() for r in data["rows"])
    # 合并后的五份规格：签与冻结根逐档相同，完整格表契约通过
    merged = H.load_specs_v8(tmp_path / "specs-root", H.V8_CELLS, check_fingerprint=False)
    assert {t: merged[t][0]["identity_sha256"] for t in merged} == identities
    # delivery.json 的 rows 与合并规格里的 selected 行逐一相等
    selected = {(r["task"], r["tier"], r["candidate"]) for _, rows in merged.values() for r in rows if r["selected"]}
    assert {(r["task"], r["tier"], r["candidate"]) for r in data["rows"]} == selected
    # N3：目标已存在时重跑合并 → V8_MERGE=FAIL、退出码非零、一个文件都不改
    before = {p: p.read_bytes() for p in [*(tmp_path / "specs-root").rglob("specs.jsonl"), gen1 / "merged" / "delivery.json"]}
    capsys.readouterr()
    assert _gen(monkeypatch, "--mode", "merge", "--specs", frozen, "--cells", "full", "--shards", shards,
                "--specs-out", tmp_path / "specs-root", "--output", gen1 / "merged") == 1
    assert "V8_MERGE=FAIL reason=targets_exist existing=6" in capsys.readouterr().out
    assert all(p.read_bytes() == data for p, data in before.items())
    # 确定性：同输入再合并一次，五份文件逐字节相同
    assert _gen(monkeypatch, "--mode", "merge", "--specs", frozen, "--cells", "full", "--shards", shards,
                "--specs-out", tmp_path / "specs-root-2", "--output", gen1 / "merged-2") == 0
    for tier in H.V8_TIERS:
        assert (tmp_path / "specs-root" / tier / "specs.jsonl").read_bytes() == \
               (tmp_path / "specs-root-2" / tier / "specs.jsonl").read_bytes()
    # 单独重算聚合（整树搬迁后可重跑）：同样核全部 43 格；缺任一片账本即拒绝（重试数不能静默少算）
    assert _gen(monkeypatch, "--mode", "aggregate", "--specs", tmp_path / "specs-root", "--cells", "full",
                "--shards", shards, "--output", gen1 / "agg") == 0
    with pytest.raises(_rollout.RolloutError, match="缺少尝试账本"):
        _gen(monkeypatch, "--mode", "aggregate", "--specs", tmp_path / "specs-root", "--cells", "full",
             "--shards", f"{shards},{tmp_path / 'nowhere'}", "--output", gen1 / "agg2")
    # 聚合只认齐全的规格：完整格表配一个只有 shard3 的规格根直接拒绝
    with pytest.raises(_rollout.RolloutError, match="任务集合与格表不符|缺少"):
        _rollout.aggregate_v8(gen1 / "shard3" / "specs", full, [gen1 / "shard3"], gen1 / "agg3" / "delivery.json")


def test_整树搬迁后aggregate_rebase(tmp_path, fake, monkeypatch, capsys):
    """N1：GL NFS 上生成 → rsync 回本机：漏 --rebase 即 FAIL；--rebase 后 h5／video／path 指向新位置、sha 逐个核对。"""
    old, new = tmp_path / "nfs" / "gen1", tmp_path / "data" / "gen1"
    root = build_root(old / "specs", SMOKE)
    fake()
    assert _gen(monkeypatch, "--mode", "continue", "--specs", root, "--cells", "smoke", "--output", old / "out") == 0
    new.parent.mkdir(parents=True)
    shutil.move(str(old), str(new))  # 整树搬迁，旧位置不复存在
    capsys.readouterr()
    args = ["--mode", "aggregate", "--specs", new / "specs", "--cells", "smoke", "--shards", new / "out"]
    # 漏 --rebase：规格里记录的仍是旧路径，文件不在 → FAIL（不静默写旧路径当交付）
    assert _gen(monkeypatch, *args, "--output", new / "agg-norebase") == 1
    text = capsys.readouterr().out
    assert "V8_DELIVERY_SET=FAIL" in text and "bad_h5=7" in text and "StopCube/xhard1:h5_missing" in text
    # 前缀写错：无匹配 → h5_unmapped
    assert _gen(monkeypatch, *args, "--rebase", f"{tmp_path / 'elsewhere'}={new}", "--output", new / "agg-wrong") == 1
    assert "h5_unmapped" in capsys.readouterr().out
    # 正确 --rebase → PASS；h5／video 绝对路径在新树下，path 相对新 delivery.json 可解析
    assert _gen(monkeypatch, *args, "--rebase", f"{old}={new}", "--output", new / "agg") == 0
    assert "V8_DELIVERY_SET=PASS tasks=6 cells=7 total=7" in capsys.readouterr().out
    data = _guard_delivery(new / "agg" / "delivery.json")
    assert all(r["h5"].startswith(str(new) + "/") and r["video"].startswith(str(new) + "/") for r in data["rows"])
    assert data["rebase"] == [[str(old), str(new)]]
    # 已存在的 delivery.json 不静默覆盖
    with pytest.raises(_rollout.RolloutError, match="已存在"):
        _gen(monkeypatch, *args, "--rebase", f"{old}={new}", "--output", new / "agg")
    # 搬迁后某个 h5 内容被改 → sha 不符 → 该格 FAIL
    victim = Path(data["rows"][0]["h5"])
    victim.write_bytes(b"corrupted")
    assert _gen(monkeypatch, *args, "--rebase", f"{old}={new}", "--out", new / "agg-bad" / "delivery.json",
                "--output", new / "unused") == 1
    out = capsys.readouterr().out
    assert "h5_sha_mismatch" in out and "bad_h5=1" in out


def test_超限先落账本再删媒体崩溃后恢复不重跑(tmp_path, fake, monkeypatch):
    """N7：超限局的结果先写账本、再删媒体；删之前崩溃 → --resume 按账本补删，不重跑该局。"""
    cells = {("SwingXtimes", "xhard5"): 1}
    root = build_root(tmp_path / "specs", cells, spare=1)
    out = tmp_path / "out"
    fake({("xhard5", "SwingXtimes", 0): "over"})
    real_purge = _rollout.purge_episode_media

    def crash(*a, **k):
        raise KeyboardInterrupt("删媒体前崩溃")

    monkeypatch.setattr(_rollout, "purge_episode_media", crash)
    with pytest.raises(KeyboardInterrupt):
        _rollout.run_continue_v8(root, cells, out, src_root=REPO, workers=1, gpu="0", pkg="robomme_hard",
                                 code_baseline="fixture")
    ledger = _rollout.read_ledger(out / _rollout.LEDGER_NAME)
    assert [(e["kind"], e["record"]["error_type"], e["record"]["purge_pending"]) for e in ledger] == \
           [("result", "exec_over_cap", True)]
    victim = _rollout.episode_dir(out, {"tier": "xhard5", "task": "SwingXtimes", "episode": 0})
    assert list(victim.rglob("*.h5"))  # 媒体尚未删
    monkeypatch.setattr(_rollout, "purge_episode_media", real_purge)
    runner = fake()
    summary = _rollout.run_continue_v8(root, cells, out, src_root=REPO, workers=1, gpu="0", pkg="robomme_hard",
                                       code_baseline="fixture", resume=True)
    assert runner.calls == [[("xhard5", "SwingXtimes", 1)]]  # 只跑递补，超限局不重跑
    assert not list(victim.rglob("*.h5")) and not list(victim.rglob("*.mp4"))
    assert summary["delivery_set"].startswith("V8_DELIVERY_SET=PASS") and summary["exec_over_cap"] == 1


# ── replay、报告、identities ────────────────────────────────────────────────


def test_replay读v8根含xhard5(tmp_path, fake, monkeypatch, capsys):
    root = build_root(tmp_path / "specs", SMOKE)
    _, rows = H.load_specs(root / "xhard5" / "specs.jsonl", check_fingerprint=False)
    ident = tmp_path / "ids.jsonl"
    ident.write_text("".join(json.dumps({"task": r["task"], "tier": "xhard5", "seed": r["seed"]}) + "\n"
                             for r in rows if r["selected"]))
    runner = fake()
    assert _gen(monkeypatch, "--mode", "replay", "--specs", root, "--identities", ident, "--output", tmp_path / "rp") == 0
    assert "REPLAY_SET=PASS scheduled=2" in capsys.readouterr().out
    assert {c[0] for call in runner.calls for c in call} == {"xhard5"}


def test_report读逐任务配额(tmp_path):
    root = build_root(tmp_path / "specs", SMOKE)
    report = _report.build_report(root / "xhard1" / "specs.jsonl", check_demo=False)
    assert report["totals"]["selected_shortfall"] == 2 and report["totals"]["cells"] == 2
    assert _report.per_cell_quota({"delivery_per_cell": 20}, "BinFill") == 20


def test_export_eval_identities的1262口径():
    assert export_eval_identities.EXPECTED_TOTAL == 1262
    assert export_eval_identities.IDENTITIES_NAME == "eval-identities-1262.jsonl"
    assert not hasattr(export_eval_identities, "V6_SECONDS") and export_eval_identities.TASK_SECONDS["BinFill"] == 224.0
    rows = [{"task": t, "tier": "xhard0", "episode": i, "round": None, "shard": None}
            for t in H.ALL_TASKS for i in range(12)]
    rows += [{"task": t, "tier": tier, "episode": 12 + i, "round": None, "shard": None}
             for (t, tier), n in H.V8_CELLS.items() for i in range(n)]
    official = [r for r in rows if r["tier"] == "xhard0"]
    ok, facts = export_eval_identities.check_rows(rows, official)
    assert ok and facts["episodes"] == 1262 and facts["cells"] == 43
    rows[0]["round"] = 1
    assert not export_eval_identities.check_rows(rows, official)[0]
