#!/usr/bin/env python3
"""轻量测试：v9 子集派生与产物树工具 ``scripts/injection-dev/v9_subset_specs.py``（v9 方案 §2.1、§2.12 S1-D 行）。

纯 CPU 合成夹具，不碰真实 artifacts、不 reset：V8 风格世界 = ``_freeze.freeze``（/4）封冻结根 → ``split_v8`` 切片 →
``run_continue_v8``（假 runner 在显式局目录写假 h5／mp4）→ ``merge_v8`` 合并出带结果段的规格根与 ``delivery.json``。覆盖：

* derive：取的是交付行候选号最小的 N 个，不是 ``select_rule[:N]``（初选失败、递补候选交付）；重签后
  ``load_specs_v8`` 能过；改任一行即失败；清单与规格交付行不符即 FAIL；
* extend：40 行冻结 + 29 条已试（20 ok 9 fail）→ 配额 50、备用 11 未试、追加 35 行候选号 40～74（注入假抽签）、
  账本原样带入；``run_continue_v8 --resume`` 实际只跑未试身份且恰为 29～74；dry-run 不写盘；账本身份不符即失败；
* assemble：五档可加载、清单来源标记正确、任一任务 ``sampling_config`` 不一致即 FAIL；
* link：hardlink 同 inode、幂等、目标存在且内容不同即 FAIL；verify：复用局逐字节同 V8 → PASS，换掉一个文件即 FAIL。

    uv run --no-sync python -m pytest tests/lightweight/test_v9_subset_specs.py -q
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "injection-dev"))

import _freeze  # noqa: E402
import _rollout  # noqa: E402
import v9_subset_specs as V  # noqa: E402
from robomme_hard.env_record_wrapper import hard_specs as H  # noqa: E402


# ── 合成 V8 世界 ───────────────────────────────────────────────────────


def _drafts(task: str, tier: str, candidates: int) -> list[dict]:
    rule = H.seed_rule_for(tier, "v8")
    rows = []
    for episode in range(candidates):
        spec = {"spec_kind": "native-newvalue/2", "task": task, "tier": tier, "layout": {"x": episode}}
        if task == "MoveCube":
            spec["initializations"] = {"0": {"way_idx": 0}, "1": {"way_idx": episode % 3}}
        rows.append({"task": task, "difficulty": tier, "episode": episode, "attempt": 0,
                     "seed": H.seed_for(task, episode, 0, rule), "reset_ok": True, "spec": spec,
                     "spec_sha256": H.spec_sha256(spec)})
    return rows


def build_frozen(root: Path, cells: dict, spare: int = 2, sampling_tag: str = "v8") -> Path:
    for tier in _rollout.cell_tiers(cells):
        tasks = [t for t in H.ALL_TASKS if (t, tier) in cells]
        cands = {t: cells[(t, tier)] + spare for t in tasks}
        drafts = [row for t in tasks for row in _drafts(t, tier, cands[t])]
        parts = {"difficulty": tier, "tasks": tasks, "seed_rule": H.seed_rule_for(tier, "v8"),
                 "sampling_config": {t: {"decision": {"k": t, "tier": tier, "tag": sampling_tag}, "native": {}}
                                     for t in tasks},
                 "recovery_rule": {"rule": "off"}, "identity_source": "formula", "run_id": f"v8-specs-{tier}",
                 "draw_stats": {}, "provenance": {}}
        select = {t: tuple(range(cells[(t, tier)])) for t in tasks}
        header, rows = _freeze.freeze(drafts, parts, select, cands, schema=H.SCHEMA_V8)
        _freeze.write_jsonl_exclusive(root / tier / "specs.jsonl", [header, *rows])
    return root


class FakeRunner:
    """代替 ``run_batch``：在显式局目录写假 h5 与主视频；``fails`` 里的 (tier, task, candidate) 记规划失败。"""

    def __init__(self, out_dir: Path, fails=()):
        self.out_dir = Path(out_dir)
        self.fails = set(fails)
        self.ran: list[tuple] = []

    def __call__(self, batch, header, round_index):
        tier = header["difficulty"]
        work = self.out_dir / "_rounds" / f"{tier}_round_{round_index:02d}"
        work.mkdir(parents=True, exist_ok=True)
        out = []
        for row in batch:
            key = (tier, row["task"], row["candidate"])
            self.ran.append(key)
            ok = key not in self.fails
            record = {"task": row["task"], "tier": tier, "candidate": row["candidate"], "episode": row["episode"],
                      "seed": row["seed"], "attempt": row["attempt"], "spec_sha256": row["spec_sha256"], "ok": ok,
                      "error_type": None if ok else "ScrewPlanFailure", "error": None if ok else "规划失败",
                      "spec_binding": None, "env_package": "robomme_hard",
                      "env_module": f"robomme_hard.robomme_env.{row['task']}", "wrapper_modules": None, "h5": None,
                      "round": round_index, "role": row.get("_role", "selected")}
            if ok:
                wdir = _rollout.episode_dir(self.out_dir, row)
                h5 = wdir / "hdf5_files" / f"{row['task']}_ep{row['episode']}_seed{row['seed']}.h5"
                h5.parent.mkdir(parents=True, exist_ok=True)
                payload = f"h5-{self.out_dir.name}-{tier}-{row['task']}-{row['candidate']}".encode()
                h5.write_bytes(payload)
                (wdir / "videos").mkdir(exist_ok=True)
                (wdir / "videos" / f"{row['task']}_ep{row['episode']}_seed{row['seed']}_demo.mp4").write_bytes(
                    b"mp4-" + payload)
                record.update(h5=str(h5), h5_sha256=hashlib.sha256(payload).hexdigest(), bytes=len(payload),
                              frames=105, exec_steps=100)
            out.append(record)
        return out


def run_shard(specs_root: Path, cells: dict, out: Path, fails=(), resume: bool = False) -> tuple[dict, FakeRunner]:
    runner = FakeRunner(out, fails)
    summary = _rollout.run_continue_v8(specs_root, cells, out, src_root=REPO, workers=1, gpu="0", pkg="robomme_hard",
                                       code_baseline="test", resume=resume, batch_runner=runner)
    return summary, runner


def build_v8_world(base: Path, cells: dict, fails=(), spare: int = 2, sampling_tag: str = "v8") -> dict:
    """冻结根 → 单片 → continue → 合并：返回 V8 风格的 specs-root、gen1 根（含 delivery.local.json）与片根。"""
    frozen = build_frozen(base / "frozen", cells, spare, sampling_tag)
    shard = base / "gen1" / "shard1"
    _rollout.split_v8(frozen, cells, shard, label="shard1")
    summary, _ = run_shard(shard / "specs", cells, shard, fails)
    assert summary["delivery_set"].startswith("V8_DELIVERY_SET=PASS"), summary["delivery_set"]
    report = _rollout.merge_v8(frozen, cells, [shard], base / "specs-root", base / "gen1" / "merged",
                               cells_label="test", code_baseline="test")
    assert report["line"].startswith("V8_DELIVERY_SET=PASS")
    shutil.copyfile(base / "gen1" / "merged" / "delivery.json", base / "gen1" / "delivery.local.json")
    return {"root": base / "specs-root", "gen": base / "gen1", "delivery": base / "gen1" / "delivery.local.json",
            "shard": shard, "frozen": frozen, "cells": cells}


def read_file(path: Path) -> tuple[dict, list[dict]]:
    records = [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
    return records[0], records[1:]


def rewrite(path: Path, header: dict, rows: list[dict], *, resign: bool) -> None:
    if resign:
        header = copy.deepcopy(header)
        header["sampling_config_sha256"] = H.digest(header["sampling_config"])
        header["identity_sha256"] = H.identity_sha256(header, rows)
        header["delivery_sha256"] = H.delivery_sha256(rows)
    Path(path).write_text("".join(H.canonical_json(r) + "\n" for r in [header, *rows]))


# ── derive ─────────────────────────────────────────────────────────────

DERIVE_V8 = {("VideoUnmask", "xhard1"): 6, ("VideoUnmask", "xhard4"): 6, ("StopCube", "xhard1"): 3,
             ("StopCube", "xhard4"): 3, ("InsertPeg", "xhard4"): 4}
DERIVE_V9 = {("VideoUnmask", "xhard1"): 4, ("VideoUnmask", "xhard4"): 4, ("StopCube", "xhard1"): 2,
             ("StopCube", "xhard4"): 2, ("InsertPeg", "xhard4"): 4}


@pytest.fixture()
def derive_world(tmp_path):
    # VideoUnmask/xhard1 初选 0..5，候选 1 规划失败 → 递补 6；交付行 = 0,2,3,4,5,6
    return build_v8_world(tmp_path / "v8", DERIVE_V8, fails={("xhard1", "VideoUnmask", 1)})


def test_derive取交付行最小N个而非select_rule前N个(derive_world, tmp_path):
    out2 = tmp_path / "subset2"
    result = V.derive(derive_world["root"], derive_world["delivery"], out2, source_cells=DERIVE_V8,
                      target_cells=DERIVE_V9)
    assert not result["problems"], result["problems"]
    assert result["line"] == "V9_DERIVE=PASS cells=5 subset=12 insertpeg=4 total=16 tiers=2"
    assert json.loads((out2 / V.DERIVE_META).read_text())["picks"]["VideoUnmask@xhard1"] == [0, 2, 3, 4]
    v8_header, v8_rows = read_file(derive_world["root"] / "xhard1" / "specs.jsonl")
    assert v8_header["select_rule"]["VideoUnmask"][:4] == [0, 1, 2, 3]
    assert result["picks"]["VideoUnmask@xhard1"] == [0, 2, 3, 4]
    assert result["dropped"]["VideoUnmask@xhard1"] == [5, 6]
    header, rows = read_file(out2 / "xhard1" / "specs.jsonl")
    assert header["select_rule"]["VideoUnmask"] == [0, 2, 3, 4] and header["delivery_per_cell"]["VideoUnmask"] == 4
    assert header["per_env"] == v8_header["per_env"]
    selected = sorted(r["candidate"] for r in rows if r["task"] == "VideoUnmask" and r["selected"])
    assert selected == [0, 2, 3, 4]
    old = {(r["task"], r["candidate"]): r for r in v8_rows}
    for row in rows:  # 规格行除 selected 外逐字段不动
        assert {k: v for k, v in row.items() if k != "selected"} == \
            {k: v for k, v in old[(row["task"], row["candidate"])].items() if k != "selected"}
    lines = (out2 / "xhard1" / "specs.jsonl").read_text().splitlines()
    v8_lines = set((derive_world["root"] / "xhard1" / "specs.jsonl").read_text().splitlines()[1:])
    kept = [line for line, row in zip(lines[1:], rows) if row["selected"] == old[(row["task"], row["candidate"])]["selected"]]
    assert all(line in v8_lines for line in kept)  # 未改 selected 的行逐字节相同
    assert header["identity_sha256"] != v8_header["identity_sha256"]
    loaded = H.load_specs_v8(out2, DERIVE_V9, check_fingerprint=False)
    assert set(loaded) == {"xhard1", "xhard4"}
    # InsertPeg（只在 xhard4）取 V8 交付的全部局
    assert result["picks"]["InsertPeg@xhard4"] == [0, 1, 2, 3]


def test_derive产物改任一行即失败(derive_world, tmp_path):
    out = tmp_path / "subset"
    assert not V.derive(derive_world["root"], derive_world["delivery"], out, source_cells=DERIVE_V8,
                        target_cells=DERIVE_V9)["problems"]
    path = out / "xhard1" / "specs.jsonl"
    header, rows = read_file(path)
    pristine = path.read_text()
    for mutate in (lambda r: r["spec"]["layout"].update(x=99), lambda r: r.update(selected=not r["selected"]),
                   lambda r: r.update(seed=r["seed"] + 1)):
        bad = copy.deepcopy(rows)
        mutate(next(r for r in bad if r["task"] == "VideoUnmask" and r["candidate"] == 2))
        rewrite(path, header, bad, resign=False)
        with pytest.raises(H.SpecsError):
            H.load_specs_v8(out, DERIVE_V9, check_fingerprint=False)
        path.write_text(pristine)
    H.load_specs_v8(out, DERIVE_V9, check_fingerprint=False)


def test_derive清单与规格不符即FAIL且不写盘(derive_world, tmp_path, capsys):
    data = json.loads(derive_world["delivery"].read_text())
    data["rows"][0]["h5_sha256"] = "0" * 64
    bad = tmp_path / "bad-delivery.json"
    bad.write_text(json.dumps(data))
    out = tmp_path / "subset"
    result = V.derive(derive_world["root"], bad, out, source_cells=DERIVE_V8, target_cells=DERIVE_V9)
    assert result["line"] is None and any("h5_sha256" in p for p in result["problems"])
    assert not out.exists()
    # CLI 缺省按真实 V8／V9 表读：合成世界只有 5 格 → 响亮 FAIL、非零退出、不写盘
    rc = V.main(["derive", "--v8-root", str(derive_world["root"]), "--v8-gen", str(derive_world["gen"]),
                 "--out", str(out)])
    text = capsys.readouterr().out
    assert rc == 1 and "V9_DERIVE=FAIL" in text
    assert not out.exists()


# ── extend ─────────────────────────────────────────────────────────────

IP = ("InsertPeg", "xhard4")
#: 初选 0..19 里 2,3,9,11,18 失败 → 递补 20..24；其中 20、24 失败 → 25、26；26 失败 → 27；27 失败 → 28
IP_FAILS = {("xhard4", "InsertPeg", c) for c in (2, 3, 9, 11, 18, 20, 24, 26, 27)}


def _fake_draw(task, seed, episode, sampling):
    return True, {"spec_kind": "native-newvalue/2", "task": task, "tier": "xhard4", "layout": {"x": episode}}, None, None


@pytest.fixture()
def insertpeg_world(tmp_path):
    return build_v8_world(tmp_path / "v8", {IP: 20}, fails=IP_FAILS, spare=20)


def test_extend导入终态_配额50_追加35_待跑恰为29到74(insertpeg_world, tmp_path, capsys):
    world = insertpeg_world
    v8_header, v8_rows = read_file(world["shard"] / "specs" / "xhard4" / "specs.jsonl")
    assert sorted(r["candidate"] for r in v8_rows if r["tried"]) == list(range(29))
    out = tmp_path / "insertpeg-root"
    checked = []
    rc = V.main(["extend", "--task", "InsertPeg", "--tier", "xhard4", "--v8-frozen", str(world["root"]),
                 "--v8-shard", str(world["shard"]), "--quota", "50", "--append", "35", "--max-reset-attempts", "60",
                 "--out", str(out)], draw_one=_fake_draw, sampling_check=lambda task, s: checked.append(task))
    text = capsys.readouterr().out
    assert rc == 0, text
    assert text.strip().splitlines()[-1] == \
        "V9_INSERTPEG_EXTEND=PASS imported_ok=20 imported_fail=9 spares=11 appended=35 quota=50"
    assert checked == ["InsertPeg"]
    header, rows = read_file(out / "specs" / "xhard4" / "specs.jsonl")
    assert header["tasks"] == ["InsertPeg"] and header["per_env"] == {"InsertPeg": 75}
    assert header["delivery_per_cell"] == {"InsertPeg": 50} and len(header["select_rule"]["InsertPeg"]) == 50
    assert [r["candidate"] for r in rows] == list(range(75))
    old = {r["candidate"]: r for r in v8_rows}
    for row in rows[:40]:  # V8 40 行：除 selected 外逐字段不动；29～39 保持未试
        assert {k: v for k, v in row.items() if k != "selected"} == \
            {k: v for k, v in old[row["candidate"]].items() if k != "selected"}
    assert [r["candidate"] for r in rows if not r["tried"]] == list(range(29, 75))
    assert [r["candidate"] for r in rows if r["selected"] and r["rollout"] is None] == list(range(29, 59))
    assert all(r["seed"] == H.seed_for("InsertPeg", r["episode"], 0, header["seed_rule"]) for r in rows[40:])
    # 账本原样带入
    v8_ledger = [line for line in (world["shard"] / "results.jsonl").read_text().splitlines()
                 if json.loads(line)["task"] == "InsertPeg"]
    assert (out / "results.jsonl").read_text().splitlines() == v8_ledger and len(v8_ledger) == 29
    assert json.loads((out / "cells.json").read_text()) == {"InsertPeg@xhard4": 50}
    cells = _rollout.resolve_cells(out / "cells.json")
    # 续跑：29..44 失败 → 同格递补 59..74；实际跑的身份恰为 29～74，V8 已试的 0～28 一个不重跑
    fails = {("xhard4", "InsertPeg", c) for c in range(29, 45)}
    summary, runner = run_shard(out / "specs", cells, out, fails, resume=True)
    assert sorted(c for _, _, c in runner.ran) == list(range(29, 75))
    assert summary["delivery_set"].startswith("V8_DELIVERY_SET=PASS tasks=1 cells=1 total=50"), summary["delivery_set"]
    # 不带 --resume 会因账本已存在被拒（片根自带账本）
    with pytest.raises(_rollout.RolloutError, match="--resume"):
        run_shard(out / "specs", cells, out)


def test_extend干跑不写盘_账本身份不符即失败(insertpeg_world, tmp_path, capsys):
    world = insertpeg_world
    out = tmp_path / "dry"
    rc = V.main(["extend", "--v8-frozen", str(world["root"]), "--v8-shard", str(world["shard"]), "--quota", "50",
                 "--append", "35", "--out", str(out), "--dry-run"])
    text = capsys.readouterr().out
    assert rc == 0 and "V9_INSERTPEG_EXTEND_DRY_RUN imported_ok=20 imported_fail=9 spares=11" in text
    assert "first_pending=29..58" in text and "untried_after=29..74" in text
    assert not out.exists()
    # 账本里一条终态的 spec_sha256 与规格行不符 → 响亮失败
    shard = tmp_path / "shard-copy"
    shutil.copytree(world["shard"], shard)
    lines = (shard / "results.jsonl").read_text().splitlines()
    entry = json.loads(lines[3])
    entry["record"]["spec_sha256"] = "f" * 64
    lines[3] = json.dumps(entry, ensure_ascii=False, sort_keys=True)
    (shard / "results.jsonl").write_text("\n".join(lines) + "\n")
    rc = V.main(["extend", "--v8-frozen", str(world["root"]), "--v8-shard", str(shard), "--quota", "50",
                 "--append", "35", "--out", str(tmp_path / "bad"), "--dry-run"])
    text = capsys.readouterr().out
    assert rc == 1 and "V9_INSERTPEG_EXTEND=FAIL" in text and "spec_sha256" in text


# ── assemble／link／verify ──────────────────────────────────────────────

ASM_V8 = {**{("StopCube", t): 3 for t in H.V8_TIERS}, IP: 4, ("MoveCube", "xhard4"): 3}
ASM_SUBSET = {**{("StopCube", t): 2 for t in H.V8_TIERS}, IP: 4}
ASM_V9 = {**{("StopCube", t): 2 for t in H.V8_TIERS}, IP: 6, ("MoveCube", "xhard4"): 4}


@pytest.fixture()
def assembled(tmp_path):
    v8 = build_v8_world(tmp_path / "v8", ASM_V8, fails={("xhard4", "InsertPeg", 1)})  # InsertPeg 递补 4，备用 5
    subset = tmp_path / "subset"
    assert not V.derive(v8["root"], v8["delivery"], subset, source_cells=ASM_V8, target_cells=ASM_SUBSET)["problems"]
    ip = tmp_path / "insertpeg-root"
    res = V.extend("InsertPeg", "xhard4", v8["root"], v8["shard"], 6, 3, ip, max_reset_attempts=10,
                   draw_one=_fake_draw, sampling_check=lambda task, s: None)
    assert res["line"].endswith("imported_ok=4 imported_fail=1 spares=1 appended=3 quota=6")
    summary, _ = run_shard(ip / "specs", _rollout.resolve_cells(ip / "cells.json"), ip, resume=True)
    assert summary["delivery_set"].startswith("V8_DELIVERY_SET=PASS")
    mc_cells = {("MoveCube", "xhard4"): 4}
    mc_frozen = build_frozen(tmp_path / "mc-frozen", mc_cells, spare=2, sampling_tag="v9-region")
    mc = tmp_path / "shard-movecube"
    _rollout.split_v8(mc_frozen, mc_cells, mc, label="v9shard1")
    summary, _ = run_shard(mc / "specs", mc_cells, mc)
    assert summary["delivery_set"].startswith("V8_DELIVERY_SET=PASS")
    out_specs, out_delivery = tmp_path / "v9" / "specs-root", tmp_path / "v9" / "delivery" / "delivery.local.json"
    result = V.assemble(subset, mc, ip, v8["delivery"], out_specs, out_delivery, cells=ASM_V9)
    return {"v8": v8, "subset": subset, "ip": ip, "mc": mc, "out_specs": out_specs, "out_delivery": out_delivery,
            "result": result, "tmp": tmp_path}


def test_assemble五档可加载_来源标记正确(assembled):
    result = assembled["result"]
    assert not result["problems"], result["problems"]
    assert result["line"] == "V9_ASSEMBLE=PASS rows=20 reused=14 new=6 cells=7"
    loaded = H.load_specs_v8(assembled["out_specs"], ASM_V9, cell_table=H.V9_CELLS, check_fingerprint=False)
    assert list(loaded) == list(H.V8_TIERS)
    header, rows = loaded["xhard4"]
    assert header["tasks"] == ["StopCube", "InsertPeg", "MoveCube"]
    assert header["per_env"] == {"StopCube": 5, "InsertPeg": 9, "MoveCube": 6}
    assert header["sampling_config"]["MoveCube"]["decision"]["tag"] == "v9-region"
    assert header["sampling_config_sha256"] == H.digest(header["sampling_config"])
    for tier in ("xhard1", "xhard2", "xhard3", "xhard5"):  # 其余四档与子集根逐字节相同
        assert (assembled["out_specs"] / tier / "specs.jsonl").read_bytes() == \
            (assembled["subset"] / tier / "specs.jsonl").read_bytes()
    data = json.loads(assembled["out_delivery"].read_text())
    assert data["schema"] == "v8-delivery/1" and len(data["rows"]) == 20
    src = {(r["task"], r["tier"], r["candidate"]): r["source"] for r in data["rows"]}
    assert sorted(c for (t, _, c), s in src.items() if t == "InsertPeg" and s == "v8-reuse") == [0, 2, 3, 4]
    assert sorted(c for (t, _, c), s in src.items() if t == "InsertPeg" and s == "v9-new") == [5, 6]
    assert {s for (t, _, _), s in src.items() if t == "MoveCube"} == {"v9-new"}
    assert {s for (t, _, _), s in src.items() if t == "StopCube"} == {"v8-reuse"}
    # 接口契约（S1-E／站点目录、subgoals、step-headroom 消费）：顶层键与计数键、逐格键与 V8 聚合清单同口径
    v8_data = json.loads(assembled["v8"]["delivery"].read_text())
    assert set(v8_data) <= set(data)
    for key in ("line", "counts", "cells_table", "cells", "exec_cap", "cell_count", "tasks"):
        assert key in data
    assert data["cells_table"] == _rollout.cells_json(ASM_V9) and data["cell_count"] == 7 and data["tasks"] == 3
    assert set(_rollout.V8_TOTAL_COUNT_KEYS) <= set(data["counts"])
    assert data["counts"]["delivered"] == data["counts"]["expected"] == 20
    assert (data["counts"]["reused"], data["counts"]["new"]) == (14, 6)
    assert data["line"].startswith("V9_DELIVERY_SET=PASS tasks=3 cells=7 total=20 expected=20")
    assert data["assemble_line"] == result["line"]
    v8_cell_keys = set(next(iter(v8_data["cells"].values())))
    assert all(v8_cell_keys <= set(c) and c["status"] == "PASS" for c in data["cells"].values())
    v8_rows = {(r["task"], r["tier"], r["candidate"]): r for r in v8_data["rows"]}
    for row in data["rows"]:
        for key in ("h5", "path", "exec_steps", "frames", "seed", "episode", "video", *V.DELIVERY_ROW_KEYS):
            assert row.get(key) is not None or key in ("recovery_mode",), (key, row)
        if row["source"] == "v8-reuse":  # 复用行 = V8 原行逐键拷贝 + video／video_sha256／source（path 随清单位置重算）
            orig = v8_rows[(row["task"], row["tier"], row["candidate"])]
            assert set(row) == set(orig) | {"video", "video_sha256", "source"}
            assert all(row[k] == orig[k] for k in orig if k not in ("path",))
    for row in data["rows"]:
        assert Path(row["h5"]).is_file() and Path(row["video"]).is_file()
        assert row["video_sha256"] == hashlib.sha256(Path(row["video"]).read_bytes()).hexdigest()
        assert (assembled["out_delivery"].parent / row["path"]).resolve() == Path(row["h5"]).resolve()
        if row["source"] == "v8-reuse":
            assert str(assembled["v8"]["gen"]) in row["h5"]


def test_assemble任一任务sampling不一致即FAIL(assembled, capsys):
    path = assembled["ip"] / "specs" / "xhard4" / "specs.jsonl"
    header, rows = read_file(path)
    header["sampling_config"]["InsertPeg"]["decision"]["tag"] = "drifted"
    rewrite(path, header, rows, resign=True)
    tmp = assembled["tmp"]
    rc = V.main(["assemble", "--subset", str(assembled["subset"]), "--movecube", str(assembled["mc"]),
                 "--insertpeg", str(assembled["ip"]), "--v8-delivery", str(assembled["v8"]["delivery"]),
                 "--out-specs", str(tmp / "v9b" / "specs-root"), "--out-delivery", str(tmp / "v9b" / "d.json")])
    text = capsys.readouterr().out
    assert rc == 1 and "V9_ASSEMBLE=FAIL" in text and "sampling_config" in text
    assert not (tmp / "v9b").exists()


def test_link幂等_目标内容不同即FAIL_verify逐字节(assembled, capsys):
    assert not assembled["result"]["problems"]
    tree = assembled["out_delivery"].parent
    rc = V.main(["link", "--delivery", str(assembled["out_delivery"]), "--out", str(tree)])
    assert rc == 0 and "V9_LINK=PASS rows=20 files=40 linked=40 skipped=0" in capsys.readouterr().out
    data = json.loads(assembled["out_delivery"].read_text())
    for row in data["rows"]:
        wdir = tree / "episodes" / row["tier"] / f"{row['task']}_episode_{row['candidate']}"
        assert os.path.samefile(wdir / "hdf5_files" / Path(row["h5"]).name, row["h5"])
        assert os.path.samefile(wdir / "videos" / Path(row["video"]).name, row["video"])
    rc = V.main(["link", "--delivery", str(assembled["out_delivery"]), "--out", str(tree)])
    assert rc == 0 and "linked=0 skipped=40" in capsys.readouterr().out
    v8 = assembled["v8"]
    result = V.verify(v8["root"], v8["delivery"], assembled["out_specs"], assembled["out_delivery"], tree,
                      v8_cells=ASM_V8, v9_cells=ASM_V9, rehash_h5=True)
    assert result["ok"], result["problems"]
    assert result["line"] == "V9_SUBSET=PASS reused=14 spec_equal=14 h5_equal=14 video_equal=14"
    # 交付树里一个复用 h5 被换成内容不同的独立文件：link 拒绝覆盖、verify FAIL
    row = next(r for r in data["rows"] if r["source"] == "v8-reuse")
    target = tree / "episodes" / row["tier"] / f"{row['task']}_episode_{row['candidate']}" / "hdf5_files" / \
        Path(row["h5"]).name
    target.unlink()
    target.write_bytes(b"not the v8 h5")
    rc = V.main(["link", "--delivery", str(assembled["out_delivery"]), "--out", str(tree)])
    text = capsys.readouterr().out
    assert rc == 1 and "V9_LINK=FAIL" in text and "不覆盖" in text
    assert target.read_bytes() == b"not the v8 h5"
    result = V.verify(v8["root"], v8["delivery"], assembled["out_specs"], assembled["out_delivery"], tree,
                      v8_cells=ASM_V8, v9_cells=ASM_V9)
    assert not result["ok"] and result["line"].startswith("V9_SUBSET=FAIL") and "h5_equal=13" in result["line"]
