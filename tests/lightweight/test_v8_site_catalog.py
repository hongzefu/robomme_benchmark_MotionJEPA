#!/usr/bin/env python3
"""轻量测试：v8 站点目录与逐段数据（v8 方案第一部分 §2.2 站点行、§3「站点与 v7 布局一致」；§2.12 S4-A）。

纯 CPU 合成夹具（不启动仿真）：本文件自带最小 v8 合成目录 builder——``hard-specs/4`` 规格根（43 格或子表，
配置值按表 1 写进 ``spec.objects``／``spec.actions``）、h5py 合成 h5、``delivery.json``（``v8-delivery/1``）、
xhard0 生成清单 ``manifest-{H,O}.jsonl``、身份清单 ``eval-identities-<n>.jsonl``、极小 mp4（有 ffmpeg 时为可播放
H.264，否则占位字节）。覆盖：

* 评估来源全部缺省时每局 ``eval`` 为空、``eval_status == "unevaluated"``，按页面同一口径的成败筛选零命中；
* 总数校验（V8、V9 两套格表都测，局数一律由格表推出）：完整 43 格 + 16×12 xhard0（V8 1262、V9 992）才 PASS，
  少一个或多一个身份即 FAIL；
* V9 评估复用（v9 方案 §2.1 S1-E）：复用集合只认 ``reused.json``，按 (task, tier, seed, spec_sha256) 四元组从合成 V8
  站点目录复制评估位；同 (task, tier, seed) 但 spec_sha256 不同即不复用、置空计数；新评运行接入；总表检查器的
  ``V9_SITE`` 计数纯函数；接续脚本的 ``--cells v9`` 与透传参数；
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
    """在 ``root`` 下写出完整合成目录，返回 catalog 源字典（``cells`` 缺省为 ``V8_CELLS``；等于 ``V8_CELLS``／``V9_CELLS``
    时走 ``--cells v8|v9``，其他子表走 ``--cells-json``）。"""
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
    cells_json, version = None, None
    if cells == dict(H.V9_CELLS):
        version = "v9"
    elif cells == dict(H.V8_CELLS):
        version = "v8"
    else:
        cells_json = root / "cells.json"
        cells_json.write_text(json.dumps({f"{t}/{tier}": n for (t, tier), n in cells.items()}))
    return {"specs_root": root / "specs-root", "delivery": gen1 / "delivery.json", "identities": ident_path,
            "xhard0_gen": xdir, "gen_videos": None, "path_base": root, "cells_json": cells_json, "cells": version}


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


TABLES = {"v8": H.V8_CELLS, "v9": H.V9_CELLS}
X0_TOTAL = len(H.ALL_TASKS) * C.XHARD0_PER_TASK  # 16 × 12 = 192


@pytest.fixture(scope="module", params=["v8", "v9"])
def full(request, tmp_path_factory):
    """完整合成目录，V8（1070 + 192 = 1262）与 V9（800 + 192 = 992）两套格表各一份；局数由格表推出。"""
    table = dict(TABLES[request.param])
    root = tmp_path_factory.mktemp(f"{request.param}site-full")
    src = build_synthetic(root, table)
    assert src["cells"] == request.param and src["cells_json"] is None
    catalog, media, stats = C.build_catalog(src)
    return root, src, catalog, media, stats, table


# ── 测试 ────────────────────────────────────────────────────────────


def test_格表推出的身份总数():
    assert C.expected_identities(dict(H.V8_CELLS)) == sum(H.V8_CELLS.values()) + X0_TOTAL == 1262
    assert C.expected_identities(dict(H.V9_CELLS)) == sum(H.V9_CELLS.values()) + X0_TOTAL == 992
    assert C.load_cells(None) == dict(H.V8_CELLS) and C.load_cells(None, "v9") == dict(H.V9_CELLS)
    with pytest.raises(ValueError):
        C.load_cells(None, "v7")


def test_完整合成目录_局数由格表推出且评估全部未评估(full):
    _, _, catalog, media, stats, table = full
    total = sum(table.values()) + X0_TOTAL
    assert stats["problems"] == []
    assert stats["identities"] == stats["expected"] == total
    c = stats["counts"]
    assert c["gen_v8"] == sum(table.values()) and c["eval_unevaluated"] == total and c.get("config_mismatch", 0) == 0
    assert c["gen_new_xhard0"] == 191 and c["gen_old_xhard0"] == 191 and c["gen_failed"] == 2
    assert catalog["schema"] == "v8-site-catalog/1" and catalog["eval"]["status"] == "unevaluated"
    assert "rerun11" not in catalog
    eps = [ep for t in catalog["tasks"] for cell in t["tiers"].values() for ep in cell["episodes"]]
    assert len(eps) == total
    assert all(ep["eval"] == {} and ep["eval_status"] == "unevaluated" for ep in eps)
    assert all("flip" not in ep and "rerun" not in ep and "eval_origin" not in ep for ep in eps)
    # 媒体白名单只有生成视频（无任何评估媒体）
    assert len(media) == sum(table.values()) + 191 * 2


def test_成败筛选零命中_未评估独立计数(full):
    catalog, table = full[2], full[5]
    eps = [ep for t in catalog["tasks"] for cell in t["tiers"].values() for ep in cell["episodes"]]
    for filt in ("both", "split", "none", "flip", "rerun"):
        assert sum(ep_matches(ep, filt) for ep in eps) == 0, filt
    assert sum(ep_matches(ep, "uneval") for ep in eps) == sum(table.values()) + X0_TOTAL
    html = (SITE / "v8_site.html").read_text(encoding="utf-8")
    assert "case 'none': return done && !a && !b;" in html and "PL_ACTUAL" not in html


def test_xhard5列与格表(full):
    catalog = full[2]
    assert catalog["tiers"] == ["xhard0", "xhard1", "xhard2", "xhard3", "xhard4", "xhard5"]
    have = {(t["id"], tier): len(cell["episodes"]) for t in catalog["tasks"] for tier, cell in t["tiers"].items()}
    assert len(have) == 59
    assert {k: n for k, n in have.items() if k[1] != "xhard0"} == full[5]
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
    root, _, _, media, *_ = full
    x0 = [p for p in media.values() if "/xhard0-gen/" in p]
    assert len(x0) == 382 and all(Path(p).is_relative_to(root.resolve()) for p in x0)


def test_main_写出目录_且总数由格表推出校验(tmp_path, full, capsys):
    root, src, *_, table = full
    total, n_new = sum(table.values()) + X0_TOTAL, sum(table.values())
    out = tmp_path / "site"
    assert C.main(src_args(src, out)) == 0  # V9 夹具经 --cells v9 进入
    line = capsys.readouterr().out.strip().splitlines()[-1]
    assert line.startswith(f"V8_SITE_CATALOG=PASS identities={total} expected={total} gen_v8={n_new} ")
    assert "eval_filled=0 " in line and f"eval_unevaluated={total} " in line and "config_mismatch=0 " in line  # 不给评估来源时全部未评估
    assert "eval_reused=" not in line  # 非 V9 复用模式不追加 V9 计数
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
    root, src, *_, table = full
    site = tmp_path / "site"
    assert C.main(src_args(src, site)) == 0
    capsys.readouterr()
    S = _subgoals()
    rc = S.main(["--site-dir", str(site), "--specs-root", str(src["specs_root"]), "--delivery", str(src["delivery"]),
                 "--xhard0-gen", str(src["xhard0_gen"]), "--path-base", str(root), "--workers", "0"])
    line = capsys.readouterr().out.strip().splitlines()[-1]
    assert rc == 0, line
    h5 = sum(table.values()) + 2 * X0_TOTAL  # 新值局 + xhard0 两入口（V8 1454、V9 1184）
    assert line.startswith(f"V8_SUBGOALS=PASS h5={h5} cells=59 missing=0 exec_mismatch=0 over_cap=0 xhard0_same=192/192")
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


# ── V9 评估复用（S1-E）────────────────────────────────────────────────

V9_SMALL = {("MoveCube", "xhard4"): 2, ("InsertPeg", "xhard4"): 3, ("StopCube", "xhard1"): 2}
EVAL_POLS = ("smvla", "mme")


def _selected_rows(src: dict) -> list[dict]:
    out = []
    for path in sorted(Path(src["specs_root"]).glob("*/specs.jsonl")):
        out += [r for r in map(json.loads, path.read_text().splitlines()[1:]) if r["selected"]]
    return out


def _key(task: str, tier: str, seed: int) -> str:
    return f"{task}_{tier}_{seed}"


def write_v8_site_eval(root: Path, src: dict, reuse: list[dict], mp4: Path) -> tuple[Path, dict]:
    """合成 V8 站点目录（catalog.json 无 spec_sha256，与真实 V8 site-eval 同形态）：给定新值局 + 全部 xhard0。"""
    site = root / "v8-site-eval"
    media, tasks = {}, {}

    def mid(name: str) -> str:
        path = root / "v8-eval-media" / f"{name}.mp4"
        link(mp4, path)
        ident = hashlib.sha256(name.encode()).hexdigest()[:24]
        media[ident] = str(path.resolve())
        return ident

    for r in reuse:
        ep = {"seed": r["seed"], "eval": {"new": {
            "simplememvla": {"status": "success", "steps": 300, "max_steps": 1600, "media": mid(f"s-{_key(r['task'], r['tier'], r['seed'])}")},
            "mmevla": {"status": "timeout", "steps": 1600, "max_steps": 1600, "media": mid(f"m-{_key(r['task'], r['tier'], r['seed'])}")}}}}
        tasks.setdefault(r["task"], {}).setdefault(r["tier"], []).append(ep)
    for ident in map(json.loads, Path(src["identities"]).read_text().splitlines()):
        if ident["tier"] != "xhard0":
            continue
        name = f"{ident['task']}_{ident['seed']}"
        ev = {e: {"simplememvla": {"status": "fail", "steps": 1300, "max_steps": 1300, "no_video": C.NO_VIDEO_X0_SMVLA},
                  "mmevla": {"status": "success" if e == "new" else "fail", "steps": 500, "max_steps": 1300,
                             "media": mid(f"x0-{e}-{name}")}} for e in ("new", "old")}
        tasks.setdefault(ident["task"], {}).setdefault("xhard0", []).append(
            {"seed": ident["seed"], "eval": ev, "flip": {"simplememvla": False, "mmevla": True},
             "eval_source": "V8 阶段 3′ xhard0 两路线评估（合成）"})
    catalog = {"schema": "v8-site-catalog/1", "eval": {"status": "evaluated", "run": "v8-run-synth"},
               "tasks": [{"id": t, "tiers": {tier: {"episodes": eps} for tier, eps in tiers.items()}}
                         for t, tiers in tasks.items()]}
    site.mkdir(parents=True)
    (site / "catalog.json").write_text(json.dumps(catalog, ensure_ascii=False))
    (site / "media-private.json").write_text(json.dumps(media))
    return site, media


def write_reused(root: Path, rows: list[dict], manifest_rows: list[dict]) -> Path:
    """合成 V8 manifest（含 spec_sha256）与 S1-F 契约的 reused.json（v9-eval-reused/1）。"""
    manifest = root / "v8-manifest.json"
    manifest.write_text(json.dumps({"schema": "v8-eval-manifest/1", "rows": manifest_rows}))
    path = root / "reused.json"
    path.write_text(json.dumps({"schema": "v9-eval-reused/1", "v8_manifest": str(manifest),
                                "v8_manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
                                "count": len(rows), "rows": rows}))
    return path


def write_eval_run(run: Path, rows: list[dict], mp4: Path) -> Path:
    """合成新评运行目录（结构同 V8 评估运行）：账本 accept → 结果行、site-media/manifest.jsonl、report/report.json。"""
    cells: dict[str, dict] = {p: {} for p in EVAL_POLS}
    media_rows = []
    for pol in EVAL_POLS:
        d = run / "nfs-records/run/s00" / pol
        d.mkdir(parents=True)
        results, ledger = [], []
        for r in rows:
            key = _key(r["task"], r["tier"], r["seed"])
            status = r["status"][pol]
            results.append({"attempt_id": f"{pol}-{key}", "key": key, "task": r["task"], "tier": r["tier"],
                            "seed": r["seed"], "spec_sha256": r["spec_sha256"], "status": status, "exec_steps": 400,
                            "effective_max_steps": 1600, "policy": pol})
            ledger.append({"kind": "accept", "accepted_attempt_id": f"{pol}-{key}", "key": key, "policy": pol})
            cell = cells[pol].setdefault(f"{r['task']}@{r['tier']}", {"success": 0, "fail": 0, "timeout": 0})
            cell[status] += 1
            video = run / "site-media" / pol / f"{key}.mp4"
            link(mp4, video)
            media_rows.append({"policy": pol, "key": key, "mp4": str(video), "frames": 10, "mp4_frames": 10})
        (d / "results.jsonl").write_text("".join(json.dumps(x) + "\n" for x in results))
        (d / f"{pol}.ledger.jsonl").write_text("".join(json.dumps(x) + "\n" for x in ledger))
    (run / "site-media/manifest.jsonl").write_text("".join(json.dumps(x) + "\n" for x in media_rows))
    (run / "report").mkdir()
    (run / "report/report.json").write_text(json.dumps(
        {"per_policy": {p: {"cells": c, "denominator": len(rows)} for p, c in cells.items()}}))
    return run


@pytest.fixture()
def v9reuse(tmp_path):
    """V9 小格表：StopCube 2 + InsertPeg 前 2 局复用 V8；MoveCube 两局与 InsertPeg 第 3 局新评。

    MoveCube 第 1 局与 V8 同 (task, tier, seed) 但 spec_sha256 不同（R-3），V8 站点目录与 V8 manifest 里都有它。"""
    src = build_synthetic(tmp_path, V9_SMALL)
    rows = _selected_rows(src)
    by_task = {}
    for r in sorted(rows, key=lambda r: (r["task"], r["candidate"])):
        by_task.setdefault(r["task"], []).append(r)
    reuse = by_task["StopCube"] + by_task["InsertPeg"][:2]
    mc_old = by_task["MoveCube"][0]          # 同 seed、V8 规格不同
    new = by_task["MoveCube"] + by_task["InsertPeg"][2:]
    v8_sha = "a" * 64
    quads = [{"task": r["task"], "tier": r["tier"], "seed": r["seed"], "spec_sha256": r["spec_sha256"],
              "v8_key": _key(r["task"], r["tier"], r["seed"])} for r in reuse]
    manifest_rows = [{"key": q["v8_key"], "task": q["task"], "tier": q["tier"], "seed": q["seed"],
                      "spec_sha256": q["spec_sha256"]} for q in quads]
    manifest_rows.append({"key": _key("MoveCube", "xhard4", mc_old["seed"]), "task": "MoveCube", "tier": "xhard4",
                          "seed": mc_old["seed"], "spec_sha256": v8_sha})
    mp4 = tmp_path / "_proto.mp4"
    site, _ = write_v8_site_eval(tmp_path, src, reuse + [mc_old], mp4)
    status = {"smvla": "fail", "mme": "success"}
    run = write_eval_run(tmp_path / "v9-run", [dict(r, status=status) for r in new], mp4)
    return {"src": src, "tmp": tmp_path, "quads": quads, "manifest_rows": manifest_rows, "mc_old": mc_old,
            "v8_sha": v8_sha, "site": site, "run": run, "new": new, "reuse": reuse}


def _v9src(fx: dict, reused: Path, run: Path | None) -> dict:
    return dict(fx["src"], eval_reuse=fx["site"], reused=reused, eval_new=run)


def _v9eps(catalog: dict) -> dict:
    return {(t["id"], tier, ep["seed"]): ep for t in catalog["tasks"] for tier, cell in t["tiers"].items()
            if tier != "xhard0" for ep in cell["episodes"]}


def test_v9评估复用按身份与spec_sha(v9reuse, tmp_path, capsys):
    fx = v9reuse
    mc = fx["mc_old"]
    # reused.json 里多一行：MoveCube 同 (task, tier, seed) 但 spec_sha256 是 V8 的 → 不复用、置空计数
    bad_row = {"task": "MoveCube", "tier": "xhard4", "seed": mc["seed"], "spec_sha256": fx["v8_sha"],
               "v8_key": _key("MoveCube", "xhard4", mc["seed"])}
    (tmp_path / "r1").mkdir()
    reused = write_reused(tmp_path / "r1", fx["quads"] + [bad_row], fx["manifest_rows"])
    new_wo_mc0 = [r for r in fx["new"] if r is not mc]
    run = write_eval_run(tmp_path / "v9-run-b", [dict(r, status={"smvla": "fail", "mme": "success"}) for r in new_wo_mc0],
                         tmp_path / "_proto.mp4")
    catalog, media, stats = C.build_catalog(_v9src(fx, reused, run))
    assert stats["problems"] == [], stats["problems"]
    c = stats["counts"]
    assert (c["eval_reused"], c["eval_new"], c["eval_empty"]) == (4, 2, 1)
    assert c["reuse_sha_mismatch"] == 1 and c["reuse_identity_mismatch"] == c["reuse_missing"] == c["new_sha_mismatch"] == 0
    assert c["eval_x0_reused"] == X0_TOTAL
    eps = _v9eps(catalog)
    mc_ep = eps[("MoveCube", "xhard4", mc["seed"])]
    assert mc_ep["eval_origin"] == "empty" and mc_ep["eval"]["new"] == {} and "spec_sha256 不符" in mc_ep["eval_note"]
    for r in fx["reuse"]:
        ep = eps[(r["task"], r["tier"], r["seed"])]
        assert ep["eval_origin"] == "reused" and ep["eval"]["new"]["simplememvla"]["status"] == "success"
        assert ep["eval"]["new"]["mmevla"]["status"] == "timeout" and "V9 复用" in ep["eval_source"]
        assert all(Path(media[it["media"]]).is_file() for it in ep["eval"]["new"].values())
    for r in new_wo_mc0:
        ep = eps[(r["task"], r["tier"], r["seed"])]
        assert ep["eval_origin"] == "new" and ep["eval"]["new"]["mmevla"]["status"] == "success"
        assert ep["eval"]["new"]["simplememvla"]["max_steps"] == 1600 and "media" in ep["eval"]["new"]["mmevla"]
    x0 = [ep for t in catalog["tasks"] for ep in t["tiers"]["xhard0"]["episodes"]]
    assert len(x0) == X0_TOTAL and all(ep["eval"]["new"]["mmevla"]["status"] == "success" and ep["flip"]["mmevla"] for ep in x0)
    assert catalog["eval"]["mode"] == "v9-reuse" and catalog["eval"]["reuse"]["counts"]["eval_empty"] == 1
    assert catalog["eval"]["summary"]["mmevla"] == {"success": 2, "denominator": 7}
    ip = next(t for t in catalog["tasks"] if t["id"] == "InsertPeg")["tiers"]["xhard4"]["rates"]["new"]
    assert ip == {"simplememvla": {"success": 2, "fail": 1}, "mmevla": {"timeout": 2, "success": 1}}
    # 浏览器检查器的计数纯函数：置空 1 → V9_SITE=FAIL
    O = _load("v8_oracle_browser_check_t", SITE / "v8_oracle_browser_check.py")
    counts = O.v9_eval_counts(catalog)
    assert counts == {"episodes": 7, "eval_reused": 4, "eval_new": 2, "eval_empty": 1}
    assert any("置空 1" in p for p in O.v9_problems(counts, catalog))
    # main：有置空即 FAIL 不写产物；--allow-eval-empty 照写但仍 FAIL
    args = src_args(_v9src(fx, reused, run), tmp_path / "site-a")
    assert C.main(args) == 1
    line = capsys.readouterr().out.strip().splitlines()[-1]
    assert line.startswith("V8_SITE_CATALOG=FAIL") and " eval_reused=4 eval_new=2 eval_empty=1 eval_x0_reused=192 " in line
    assert " reuse_sha_mismatch=1 " in line and not (tmp_path / "site-a").exists()
    assert C.main(src_args(_v9src(fx, reused, run), tmp_path / "site-b") + ["--allow-eval-empty"]) == 1
    assert (tmp_path / "site-b/catalog.json").is_file()
    capsys.readouterr()


def test_v9评估复用_全部对上PASS_篡改即置空(v9reuse, tmp_path, capsys):
    fx = v9reuse
    (tmp_path / "ok").mkdir()
    reused = write_reused(tmp_path / "ok", fx["quads"], fx["manifest_rows"])
    out = tmp_path / "site"
    assert C.main(src_args(_v9src(fx, reused, fx["run"]), out)) == 0
    line = capsys.readouterr().out.strip().splitlines()[-1]
    total = sum(V9_SMALL.values()) + X0_TOTAL
    assert line.startswith(f"V8_SITE_CATALOG=PASS identities={total} expected={total} ")
    assert line.endswith(" eval_reused=4 eval_new=3 eval_empty=0 eval_x0_reused=192 reuse_sha_mismatch=0 "
                         "reuse_identity_mismatch=0 reuse_missing=0 new_sha_mismatch=0")
    catalog = json.loads((out / "catalog.json").read_text())
    O = _load("v8_oracle_browser_check_t", SITE / "v8_oracle_browser_check.py")
    counts = O.v9_eval_counts(catalog)
    assert counts == {"episodes": 7, "eval_reused": 4, "eval_new": 3, "eval_empty": 0}
    assert O.v9_problems(counts, catalog, expect_reused=4, expect_new=3) == []
    assert O.v9_problems(counts, catalog, expect_reused=720, expect_new=80) != []
    assert O.v9_site_line(True, 59, 0, counts, 8082) == \
        "V9_SITE=PASS cells=59 missing=0 eval_reused=4 eval_new=3 eval_empty=0 port=8082"
    assert O.v9_eval_counts({"eval": {"status": "evaluated"}, "tasks": []}) is None  # V8 目录不出 V9 行
    assert O.with_port("http://sled-vail.eecs.umich.edu:8081/", 8082) == "http://sled-vail.eecs.umich.edu:8082"
    assert O.with_port("http://127.0.0.1:8081", None) == "http://127.0.0.1:8081" and O.base_port("http://h:8082") == 8082
    # 篡改：reused.json 的 spec_sha256 改一位（V8 manifest 同步改，文件 sha 仍对）→ 与规格不符 → 置空
    (tmp_path / "t1").mkdir()
    q = [dict(x) for x in fx["quads"]]
    m = [dict(x) for x in fx["manifest_rows"]]
    q[0]["spec_sha256"] = m[0]["spec_sha256"] = "b" * 64
    _, _, st = C.build_catalog(_v9src(fx, write_reused(tmp_path / "t1", q, m), fx["run"]))
    assert st["counts"]["reuse_sha_mismatch"] == 1 and st["counts"]["eval_empty"] == 1
    # 篡改：V8 manifest 该行 spec_sha256 不同（reused.json 照旧）→ 置空
    (tmp_path / "t2").mkdir()
    m = [dict(x) for x in fx["manifest_rows"]]
    m[1]["spec_sha256"] = "c" * 64
    _, _, st = C.build_catalog(_v9src(fx, write_reused(tmp_path / "t2", fx["quads"], m), fx["run"]))
    assert st["counts"]["reuse_sha_mismatch"] == 1 and st["counts"]["eval_empty"] == 1
    # 篡改：v8_key 指向别的身份 → 身份不符置空
    (tmp_path / "t3").mkdir()
    q = [dict(x) for x in fx["quads"]]
    q[0]["v8_key"], q[1]["v8_key"] = q[1]["v8_key"], q[0]["v8_key"]
    _, _, st = C.build_catalog(_v9src(fx, write_reused(tmp_path / "t3", q, fx["manifest_rows"]), fx["run"]))
    assert st["counts"]["reuse_identity_mismatch"] == 2 and st["counts"]["eval_empty"] == 2
    # 篡改：V8 manifest 文件被改（sha256 与 reused.json 记录不符）→ 整体拒绝
    (tmp_path / "ok" / "v8-manifest.json").write_text("{}")
    with pytest.raises(ValueError, match="sha256 不符"):
        C.build_catalog(_v9src(fx, reused, fx["run"]))
    # 新评结果行 spec_sha256 与规格不符 → 置空
    bad = [dict(r, status={"smvla": "fail", "mme": "success"}) for r in fx["new"]]
    bad[0]["spec_sha256"] = "d" * 64
    (tmp_path / "t4").mkdir()
    reused4 = write_reused(tmp_path / "t4", fx["quads"], fx["manifest_rows"])
    _, _, st = C.build_catalog(_v9src(fx, reused4, write_eval_run(tmp_path / "run-bad", bad, tmp_path / "_proto.mp4")))
    assert st["counts"]["new_sha_mismatch"] == 1 and st["counts"]["eval_empty"] == 1
    # 只给 --eval-new 不给 reused.json → 拒绝（复用集合只认 reused.json）
    with pytest.raises(ValueError, match="reused"):
        C.build_catalog(dict(fx["src"], eval_new=fx["run"]))


def _continue():
    return _load("v8_continue_after_gen_t", ROOT / "scripts/injection-dev/v8_continue_after_gen.py")


def test_接续脚本_格表推出与V9透传():
    K = _continue()
    assert K.parse_cells_arg("full", dict(H.V8_CELLS), dict(H.V9_CELLS)) == dict(H.V8_CELLS)
    assert K.parse_cells_arg("v8", dict(H.V8_CELLS), dict(H.V9_CELLS)) == dict(H.V8_CELLS)
    assert K.parse_cells_arg("v9", dict(H.V8_CELLS), dict(H.V9_CELLS)) == dict(H.V9_CELLS)
    help_text = K.cells_help()
    assert "1070 局 + xhard0 192 = 1262" in help_text and "800 局 + xhard0 192 = 992" in help_text
    # 守卫判定行 V9_* 与 V8_* 等价
    found = K.verdict_lines(["V9_DELIVERY_SET=PASS total=800", "V9_STEP_CAP=INFO filtered=3"],
                            ("V8_DELIVERY_SET", "V8_STEP_CAP"))
    assert found["V8_DELIVERY_SET"].startswith("V9_DELIVERY_SET=PASS") and K.verdict_of(found["V8_STEP_CAP"]) == "INFO"
    assert K.verdict_lines(["V9_SITE=PASS cells=59"], ("V8_SITE",))["V8_SITE"] is None  # 站点检查不做别名
    args = K.build_parser().parse_args(["--delivery", "d.json", "--specs-root", "s", "--work-dir", "w", "--site-dir",
                                        "artifacts/newtask-v9/site", "--site-only", "--cells", "v9",
                                        "--eval-reuse", "e", "--reused", "r.json", "--eval-new", "n", "--port", "8082"])
    runner = K.Runner(args)
    runner.vars = {"cmd_overrides": {}, "python": "py", "site": "S", "specs_root": "s", "delivery": "d.json",
                   "identities": "i", "xhard0_gen": "x", "path_base": "p", "site_dir": "artifacts/newtask-v9/site",
                   "cells_json": "c.json", "eval_args": ["--eval-reuse", "e", "--reused", "r.json", "--eval-new", "n"],
                   "v9_expect_args": ["--expect-reused", "720", "--expect-new", "80"], "base": "http://127.0.0.1:8082",
                   "port_actual": 8082, "shots": "sh", "expect_cells": "59"}
    cat = runner.command("catalog")
    assert cat[cat.index("--eval-reuse"):cat.index("--out")] == ["--eval-reuse", "e", "--reused", "r.json", "--eval-new", "n"]
    assert cat[cat.index("--cells-json") + 1] == "c.json"
    oracle = runner.command("oracle_check")
    assert oracle[oracle.index("--port") + 1] == "8082" and oracle[-4:] == ["--expect-reused", "720", "--expect-new", "80"]


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
