#!/usr/bin/env python3
"""轻量测试：v8 站点目录与逐段数据（v8 方案第一部分 §2.2 站点行、§3「站点与 v7 布局一致」；§2.12 S4-A）。

纯 CPU 合成夹具（不启动仿真）：本文件自带最小 v8 合成目录 builder——``hard-specs/4`` 规格根（43 格或子表，
配置值按表 1 写进 ``spec.objects``／``spec.actions``）、h5py 合成 h5、``delivery.json``（``v8-delivery/1``）、
xhard0 生成清单 ``manifest-{H,O}.jsonl``、身份清单 ``eval-identities-1262.jsonl``、极小 mp4（有 ffmpeg 时为可播放
H.264，否则占位字节）。覆盖：

* 评估来源全部缺省时每局 ``eval`` 为空、``eval_status == "unevaluated"``，按页面同一口径的成败筛选零命中；
* 1262 校验：完整 43 格 + 16×12 xhard0 = 1262 才 PASS，少一个或多一个身份即 FAIL；
* xhard5 列存在（SwingXtimes、StopCube 各 10 局）；配置逐局取自规格并与表 1 一致，篡改即 ``config_mismatch``；
* ``v8_subgoal_lengths.py`` 在 59 格上 PASS、上限取规格 ``exec_cap``／xhard0 1300、执行步与 delivery 不符即 FAIL
  且不写 ``subgoals.json``。

合成目录也供浏览器检查使用：

    python tests/lightweight/test_v8_site_catalog.py --build /tmp/v8-site-synth

    uv run --no-sync python -m pytest tests/lightweight/test_v8_site_catalog.py -q
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / "scripts/injection-dev/site"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # 子进程按模块名反序列化函数
    spec.loader.exec_module(module)
    return module


C = _load("v8_site_catalog_t", SITE / "v8_site_catalog.py")
H = C.load_hard_specs()
SEG_TEXT = {"demo": "watch the video", "a": "pick up the first red cube", "b": "put it down", "end": "All tasks completed"}
DEMO_TASKS = {"VideoUnmask", "VideoUnmaskSwap", "VideoRepick", "VideoPlaceButton", "VideoPlaceOrder"}


# ── 合成数据 ─────────────────────────────────────────────────────────


def table_value(task: str, dim: str, tier: str, cand: int) -> int:
    want = C.TABLE1[task][dim][tier]
    return want[0] + cand % (want[1] - want[0] + 1) if isinstance(want, list) else want


def synth_spec(task: str, tier: str, cand: int, tamper: bool = False) -> dict:
    """按表 1 合成 spec.objects／actions，使 ``C.DIMS`` 抽出的值等于表 1（tamper 时第一维 +1）。"""
    v = {dim: table_value(task, dim, tier, cand) for dim, _ in C.DIMS[task]}
    if tamper and v:
        first = next(iter(v))
        v[first] += 1
    obj, act = {}, {}
    if task in ("PickXtimes", "SwingXtimes"):
        obj = {"num_repeats": v[C.DIMS[task][0][0]], "distractor_count": {"actual": v["干扰块"], "requested": v["干扰块"]}}
    elif task == "StopCube":
        act = {"stop_time": v["停止序号 stop_time"], "move_interval": v["方块速度 move_interval"]}
    elif task == "BinFill":
        n = v["投入块数"]
        obj = {"target_numbers": [n // 3, n // 3, n - 2 * (n // 3)]}
    elif task in ("VideoUnmask", "ButtonUnmask"):
        obj = {"n_picks": v["抓取数"], "distractors": {"placed": v["干扰容器"], "cube_count": v["干扰方块"]}}
    elif task in ("VideoUnmaskSwap", "ButtonUnmaskSwap"):
        obj = {"n_swaps": v["换位次数"], "n_picks": v["抓取数"], "distractors": {"placed": v["外圈干扰"]}}
    elif task == "VideoPlaceButton":
        act = {"target_placement_count": v["放置次数"]}
    elif task == "VideoPlaceOrder":
        act = {"target_placement_count": v["访问总次数"]}
    elif task == "PickHighlight":
        obj = {"highlight_count": v["抓取数"], "n_cubes": v["总方块数"]}
    elif task == "VideoRepick":
        obj = {"cube_count": {"actual": v["方块数"]}, "n_swaps": v["换位"], "num_repeats": v["重抓"]}
    elif task == "RouteStick":
        obj = {"L": v["路线段数"]}
    elif task == "PatternLock":
        act = {"path_nodes": list(range(v["图案节点数"]))}
    return {"spec_kind": "native-newvalue/2", "task": task, "tier": tier, "objects": obj, "actions": act}


def build_tier(tier: str, quotas: dict[str, int], tamper: set = frozenset(), spare: int = 1) -> tuple[dict, list[dict]]:
    """与 ``test_v8_specs_schema.build_tier`` 同形态的 /4，另把表 1 配置写进 spec。"""
    rule = H.seed_rule_for(tier, "v8")
    tasks = list(quotas)
    rows = []
    for task in tasks:
        for cand in range(quotas[task] + spare):
            spec = synth_spec(task, tier, cand, tamper=(task, tier) in tamper)
            flag = cand < quotas[task]
            rows.append({"record": "spec", "task": task, "tier": tier, "candidate": cand, "episode": cand,
                         "seed": H.seed_for(task, cand, 0, rule), "attempt": 0,
                         "spec": spec, "spec_sha256": H.spec_sha256(spec),
                         "selected": flag, "tried": flag, "initial_selected": flag, "rollout": None,
                         "layout_parent": None})
    sampling = {t: {"decision": {"k": t}, "native": {}} for t in tasks}
    header = {
        "record": "header", "schema": H.SCHEMA_V8, "difficulty": tier, "tasks": tasks,
        "per_env": {t: quotas[t] + spare for t in tasks}, "runtime": dict(H.RUNTIME), "seed_rule": rule,
        "select_rule": {t: list(range(quotas[t])) for t in tasks},
        "sampling_config": sampling, "sampling_config_sha256": H.digest(sampling),
        "recovery_rule": {"rule": "off"}, "identity_source": "formula",
        "layout_rule": {"mode": "independent"}, "exec_cap": H.V8_EXEC_CAP, "delivery_per_cell": dict(quotas),
        "run_id": f"v8-site-fixture-{tier}", "draw_stats": {}, "provenance": {},
    }
    header["identity_sha256"] = H.identity_sha256(header, rows)
    header["delivery_sha256"] = H.delivery_sha256(rows)
    return header, rows


def make_mp4(path: Path) -> bool:
    """2 秒 160×96 的 H.264 测试片；无 ffmpeg 时写占位字节（目录测试不播放）。返回是否为真视频。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        cmd = [ffmpeg, "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=160x96:rate=10", "-t", "2",
               "-pix_fmt", "yuv420p", "-c:v", "libx264", "-movflags", "+faststart", str(path)]
        if subprocess.run(cmd, check=False).returncode == 0 and path.stat().st_size > 0:
            return True
    path.write_bytes(b"\x00\x00\x00\x18ftypmp42")
    return False


def link(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(src, dst)
    except OSError:
        shutil.copyfile(src, dst)


def write_h5(path: Path, task: str, tier: str, seed: int, *, empty: bool = False) -> tuple[int, int]:
    """合成 h5：返回 (总帧数, 演示帧数)。段落长度随档位与 seed 变化，便于逐格统计不全相同。"""
    import h5py  # noqa: PLC0415

    path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "w") as f:
        if empty:
            return 0, 0
        g = f.create_group(f"episode_{seed % 1000}")
        k = int(tier[-1]) if tier != "xhard0" else 0
        plan = ([("demo", 2)] if task in DEMO_TASKS else []) + [("a", 2 + k), ("b", 2 + seed % 3), ("a", 2), ("end", 1)]
        step = demo = 0
        for name, n in plan:
            for _ in range(n):
                info = g.create_group(f"timestep_{step}/info")
                info["simple_subgoal"] = SEG_TEXT[name].encode()
                info["is_video_demo"] = name == "demo"
                demo += name == "demo"
                step += 1
        setup = g.create_group("setup")
        setup["task_goal"] = [f"{task} goal A".encode(), f"{task} goal B".encode()]
        setup["difficulty"] = tier.encode()
    return step, demo


def build_synthetic(root: Path, cells: dict[tuple[str, str], int] | None = None, *, tamper: set = frozenset()) -> dict:
    """在 ``root`` 下写出完整合成 v8 目录，返回 catalog 源字典（``cells`` 缺省为 ``V8_CELLS``）。"""
    root = Path(root)
    cells = dict(H.V8_CELLS) if cells is None else dict(cells)
    mp4 = root / "_proto.mp4"
    make_mp4(mp4)
    by_tier: dict[str, dict[str, int]] = {}
    for (task, tier), n in cells.items():
        by_tier.setdefault(tier, {})[task] = n
    delivery_rows, idents = [], []
    gen1 = root / "gen1"
    for tier in H.V8_TIERS:
        if tier not in by_tier:
            continue
        header, rows = build_tier(tier, by_tier[tier], tamper=tamper)
        path = root / "specs-root" / tier / "specs.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(H.canonical_json(r) + "\n" for r in (header, *rows)), encoding="utf-8")
        for row in rows:
            if not row["selected"]:
                continue
            task, ep, seed = row["task"], row["episode"], row["seed"]
            epdir = gen1 / "episodes" / tier / f"{task}_episode_{ep}"
            h5 = epdir / "hdf5_files" / f"{task}_ep{ep}_seed{seed}.h5"
            frames, demo = write_h5(h5, task, tier, seed)
            video = epdir / "videos" / f"{task}_ep{ep}_seed{seed}_{tier}_synthetic.mp4"
            link(mp4, video)
            # S2-B 口径：h5 绝对路径、path 相对 delivery.json 目录、video 绝对路径（可选）
            delivery_rows.append({"task": task, "tier": tier, "episode": ep, "candidate": row["candidate"], "seed": seed,
                                  "exec_steps": frames - demo, "frames": frames, "h5": str(h5.resolve()),
                                  "path": str(h5.relative_to(gen1)), "h5_sha256": hashlib.sha256(h5.read_bytes()).hexdigest(),
                                  "env_module": f"robomme_hard.robomme_env.{task}", "video": str(video.resolve())})
            idents.append({"candidate": row["candidate"], "episode": None, "round": None, "seed": seed, "shard": None,
                           "source_episode": None, "task": task, "tier": tier})
    gen1.mkdir(parents=True, exist_ok=True)
    (gen1 / "delivery.json").write_text(json.dumps({
        "schema": C.DELIVERY_SCHEMA, "rows": delivery_rows,
        "counts": {"exec_over_cap": 0, "backfills": 0, "infra_retries": 0, "failed": 0},
        "cells": {f"{t}/{tier}": n for (t, tier), n in cells.items()}}, ensure_ascii=False))
    xdir = root / "xhard0-gen"
    manifests = {"H": [], "O": []}
    for code, task in enumerate(H.ALL_TASKS, 1):
        for i in range(C.XHARD0_PER_TASK):
            seed = 500_000 + code * 1000 + i
            failed = task == "VideoPlaceOrder" and i == 0  # 对应真实的「官方原版生成失败」局
            for side in ("H", "O"):
                h5 = root / "xhard0-h5" / side / task / f"{task}_ep{i}_seed{seed}.h5"
                frames, demo = write_h5(h5, task, "xhard0", seed, empty=failed)
                row = {"side": side, "task": task, "seed": seed, "episode": i, "h5": str(h5),
                       "h5_sha256": hashlib.sha256(h5.read_bytes()).hexdigest(), "frames": frames, "demo_frames": demo}
                if failed:
                    row["generation_failed"] = True
                else:
                    video = xdir / side / task / f"{task}_xhard0_{seed}.mp4"
                    link(mp4, video)
                    row.update(mp4=str(video), mp4_frames=frames)
                manifests[side].append(row)
            idents.append({"candidate": None, "episode": i, "round": None, "seed": seed, "shard": None,
                           "source_episode": i, "task": task, "tier": "xhard0"})
    for side, rows in manifests.items():
        (xdir / f"manifest-{side}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    for i, row in enumerate(sorted(idents, key=lambda r: (r["tier"], r["task"], r["seed"]))):
        row["episode"] = i
    ident_path = root / f"eval-identities-{sum(cells.values()) + 16 * C.XHARD0_PER_TASK}.jsonl"
    ident_path.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in idents))
    cells_json = None
    if cells != dict(H.V8_CELLS):
        cells_json = root / "cells.json"
        cells_json.write_text(json.dumps({f"{t}/{tier}": n for (t, tier), n in cells.items()}))
    return {"specs_root": root / "specs-root", "delivery": gen1 / "delivery.json", "identities": ident_path,
            "xhard0_gen": xdir, "gen_videos": None, "path_base": root, "cells_json": cells_json}


def src_args(src: dict, out: Path) -> list[str]:
    args = ["--out", str(out)]
    for name, value in src.items():
        if value is not None:
            args += [f"--{name.replace('_', '-')}", str(value)]
    return args


# 与 v8_site.html 的 epMatches 同一口径：成败筛选只看两策略都已评估的终态
FINAL = ("success", "fail", "timeout", "error")


def ep_matches(ep: dict, filt: str) -> bool:
    sts = [((ep.get("eval") or {}).get("new") or {}).get(p, {}).get("status", "unevaluated") for p, _ in C.POLICIES]
    done = all(s in FINAL for s in sts)
    a, b = (s == "success" for s in sts)
    return {"both": done and a and b, "split": done and a != b, "none": done and not a and not b,
            "flip": bool(ep.get("flip")) and any(ep["flip"].values()), "rerun": bool(ep.get("rerun")),
            "uneval": any(s not in FINAL for s in sts)}.get(filt, True)


# ── 夹具 ────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def full(tmp_path_factory):
    root = tmp_path_factory.mktemp("v8site-full")
    src = build_synthetic(root)
    catalog, media, stats = C.build_catalog(src)
    return root, src, catalog, media, stats


# ── 测试 ────────────────────────────────────────────────────────────


def test_完整合成目录_1262且评估全部未评估(full):
    _, _, catalog, media, stats = full
    assert stats["problems"] == []
    assert stats["identities"] == stats["expected"] == 1262
    c = stats["counts"]
    assert c["gen_v8"] == 1070 and c["eval_unevaluated"] == 1262 and c.get("config_mismatch", 0) == 0
    assert c["gen_new_xhard0"] == 191 and c["gen_old_xhard0"] == 191 and c["gen_failed"] == 2
    assert catalog["schema"] == "v8-site-catalog/1" and catalog["eval"]["status"] == "unevaluated"
    assert "rerun11" not in catalog
    eps = [ep for t in catalog["tasks"] for cell in t["tiers"].values() for ep in cell["episodes"]]
    assert len(eps) == 1262
    assert all(ep["eval"] == {} and ep["eval_status"] == "unevaluated" for ep in eps)
    assert all("flip" not in ep and "rerun" not in ep for ep in eps)
    # 媒体白名单只有生成视频（无任何评估媒体）
    assert len(media) == 1070 + 191 * 2


def test_成败筛选零命中_未评估独立计数(full):
    catalog = full[2]
    eps = [ep for t in catalog["tasks"] for cell in t["tiers"].values() for ep in cell["episodes"]]
    for filt in ("both", "split", "none", "flip", "rerun"):
        assert sum(ep_matches(ep, filt) for ep in eps) == 0, filt
    assert sum(ep_matches(ep, "uneval") for ep in eps) == 1262
    html = (SITE / "v8_site.html").read_text(encoding="utf-8")
    assert "case 'none': return done && !a && !b;" in html and "PL_ACTUAL" not in html


def test_xhard5列与格表(full):
    catalog = full[2]
    assert catalog["tiers"] == ["xhard0", "xhard1", "xhard2", "xhard3", "xhard4", "xhard5"]
    have = {(t["id"], tier): len(cell["episodes"]) for t in catalog["tasks"] for tier, cell in t["tiers"].items()}
    assert len(have) == 59
    assert {k: n for k, n in have.items() if k[1] != "xhard0"} == dict(H.V8_CELLS)
    assert {k[0] for k in have if k[1] == "xhard5"} == {"SwingXtimes", "StopCube"}
    assert all(n == 12 for k, n in have.items() if k[1] == "xhard0")


def test_配置逐局取自规格且与表1一致(full):
    catalog = full[2]
    for t in catalog["tasks"]:
        for tier, cell in t["tiers"].items():
            if tier == "xhard0":
                assert cell["config"][0]["dim"] is None
                continue
            dims = [d for d, _ in C.DIMS[t["id"]]]
            assert [it["dim"] for it in cell["config"]] == (dims or [None])
            for ep in cell["episodes"]:
                assert list(ep["config"]) == dims
                assert all(C.table1_ok(t["id"], d, tier, v) for d, v in ep["config"].items())
    swing5 = next(t for t in catalog["tasks"] if t["id"] == "SwingXtimes")["tiers"]["xhard5"]["config"]
    assert {it["dim"]: it["values"] for it in swing5} == {"摆动轮数": [8], "干扰块": [4]}
    rs = next(t for t in catalog["tasks"] if t["id"] == "RouteStick")["tiers"]["xhard2"]["config"][0]
    assert rs["values"] == [11, 12, 13]


def test_xhard0复用渲染视频(full):
    root, _, _, media, _ = full
    x0 = [p for p in media.values() if "/xhard0-gen/" in p]
    assert len(x0) == 382 and all(Path(p).is_relative_to(root.resolve()) for p in x0)


def test_main_写出目录_且1262校验(tmp_path, full, capsys):
    root, src, *_ = full
    out = tmp_path / "site"
    assert C.main(src_args(src, out)) == 0
    line = capsys.readouterr().out.strip().splitlines()[-1]
    assert line.startswith("V8_SITE_CATALOG=PASS identities=1262 expected=1262 gen_v8=1070 ")
    assert "eval_filled=0 config_mismatch=0" in line
    assert (out / "catalog.json").is_file() and (out / "media-private.json").is_file()
    # 少一个身份 → FAIL；多一个身份 → FAIL；均不写产物
    idents = Path(src["identities"]).read_text().splitlines()
    for name, lines in (("short", idents[:-1]),
                        ("extra", idents + [json.dumps({"tier": "xhard0", "task": "BinFill", "seed": 1, "episode": 9999})])):
        bad = tmp_path / f"ident-{name}.jsonl"
        bad.write_text("\n".join(lines) + "\n")
        out2 = tmp_path / f"site-{name}"
        assert C.main(src_args(dict(src, identities=bad), out2)) == 1
        assert capsys.readouterr().out.strip().splitlines()[-1].startswith("V8_SITE_CATALOG=FAIL")
        assert not out2.exists()


def test_delivery口径_缺执行步即FAIL_相对视频路径可解析(tmp_path, capsys):
    src = build_synthetic(tmp_path, {("StopCube", "xhard1"): 1, ("SwingXtimes", "xhard5"): 1})
    data = json.loads(Path(src["delivery"]).read_text())
    gen1 = Path(src["delivery"]).parent
    for row in data["rows"]:  # h5 只留相对 path、video 改相对 delivery.json 目录
        del row["h5"]
        row["video"] = str(Path(row["video"]).relative_to(gen1.resolve()))
    Path(src["delivery"]).write_text(json.dumps(data))
    assert C.main(src_args(src, tmp_path / "site-ok")) == 0
    capsys.readouterr()
    del data["rows"][0]["exec_steps"]
    Path(src["delivery"]).write_text(json.dumps(data))
    assert C.main(src_args(src, tmp_path / "site-bad")) == 1
    out = capsys.readouterr().out
    assert "缺 ['exec_steps']" in out and out.strip().splitlines()[-1].startswith("V8_SITE_CATALOG=FAIL")


def test_目标文件已存在_FAIL且不覆盖(tmp_path, capsys):
    src = build_synthetic(tmp_path, {("StopCube", "xhard1"): 1})
    out = tmp_path / "site"
    out.mkdir()
    (out / "media-private.json").write_text("{}")
    assert C.main(src_args(src, out)) == 1
    assert capsys.readouterr().out.strip().splitlines()[-1].startswith("V8_SITE_CATALOG=FAIL")
    assert not (out / "catalog.json").exists() and (out / "media-private.json").read_text() == "{}"


SMALL = {("SwingXtimes", "xhard5"): 2, ("StopCube", "xhard1"): 1, ("RouteStick", "xhard3"): 2}


def test_配置篡改_config_mismatch(tmp_path, capsys):
    src = build_synthetic(tmp_path, SMALL, tamper={("SwingXtimes", "xhard5")})
    assert C.main(src_args(src, tmp_path / "site")) == 1
    line = capsys.readouterr().out.strip().splitlines()[-1]
    assert line.startswith("V8_SITE_CATALOG=FAIL") and "config_mismatch=2" in line


def test_子表目录_expected由格表推出(tmp_path, capsys):
    src = build_synthetic(tmp_path, SMALL)
    assert C.main(src_args(src, tmp_path / "site")) == 0
    line = capsys.readouterr().out.strip().splitlines()[-1]
    assert "identities=197 expected=197 gen_v8=5" in line


def _subgoals():
    return _load("v8_subgoal_lengths_t", SITE / "v8_subgoal_lengths.py")


def test_逐段数据_59格_上限取规格(full, tmp_path, capsys):
    root, src, *_ = full
    site = tmp_path / "site"
    assert C.main(src_args(src, site)) == 0
    capsys.readouterr()
    S = _subgoals()
    rc = S.main(["--site-dir", str(site), "--specs-root", str(src["specs_root"]), "--delivery", str(src["delivery"]),
                 "--xhard0-gen", str(src["xhard0_gen"]), "--path-base", str(root), "--workers", "0"])
    line = capsys.readouterr().out.strip().splitlines()[-1]
    assert rc == 0, line
    assert line.startswith("V8_SUBGOALS=PASS h5=1454 cells=59 missing=0 exec_mismatch=0 over_cap=0 xhard0_same=192/192")
    sg = json.loads((site / "subgoals.json").read_text())
    assert sg["schema"] == "v8-subgoals/1"
    assert sg["oracle"]["SwingXtimes"]["xhard5"]["max_steps"] == 1600
    assert sg["oracle"]["BinFill"]["xhard0"]["max_steps"] == 1300
    assert sg["oracle"]["VideoPlaceOrder"]["xhard0"]["n"] == 11  # 生成失败的空 h5 不计入长度
    assert sum(len(v) for v in sg["oracle"].values()) == 59


def test_逐段数据_执行步不符即FAIL且不写文件(tmp_path, capsys):
    src = build_synthetic(tmp_path, SMALL)
    site = tmp_path / "site"
    assert C.main(src_args(src, site)) == 0
    data = json.loads(Path(src["delivery"]).read_text())
    data["rows"][0]["exec_steps"] += 1
    Path(src["delivery"]).write_text(json.dumps(data))
    capsys.readouterr()
    rc = _subgoals().main(["--site-dir", str(site), "--specs-root", str(src["specs_root"]),
                           "--delivery", str(src["delivery"]), "--xhard0-gen", str(src["xhard0_gen"]),
                           "--path-base", str(tmp_path), "--workers", "0"])
    line = capsys.readouterr().out.strip().splitlines()[-1]
    assert rc == 1 and line.startswith("V8_SUBGOALS=FAIL") and "exec_mismatch=1" in line
    assert not (site / "subgoals.json").exists()


def main() -> int:
    ap = argparse.ArgumentParser(description="写出 v8 合成站点目录（供浏览器检查与接续测试）")
    ap.add_argument("--build", type=Path, required=True)
    ap.add_argument("--cells-json", type=Path, help="{\"Task/tier\": n} 子表；缺省完整 43 格")
    args = ap.parse_args()
    if args.build.exists() and any(args.build.iterdir()):
        raise SystemExit(f"{args.build} 非空，拒绝覆盖")
    cells = None
    if args.cells_json:
        cells = {tuple(k.split("/")): int(n) for k, n in json.loads(args.cells_json.read_text()).items()}
    src = build_synthetic(args.build, cells)
    print(json.dumps({k: (str(v) if v is not None else None) for k, v in src.items()}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
