#!/usr/bin/env python3
"""v8 逐局站点目录（v8 方案第一部分 §2.2 站点行、第二部分 §2.2 第 9 条、§2.8 第 16 条）。

与 ``v7_site_catalog.py`` 同形态（``tasks[].tiers[tier].episodes[]``），页面 ``v8_site.html`` 与 v7 布局逐一一致；
差别只在数据来源与评估位：

- **新值局**（xhard1～5，43 格 1070 局）：身份与配置取 v8 规格根（``<specs-root>/<tier>/specs.jsonl``，
  ``hard-specs/4``，经 ``hard_specs.load_specs_v8`` 校验），h5 与执行步取生成产物 ``delivery.json``
  （schema ``v8-delivery/1``）。生成视频在 h5 所在 episode 目录的 ``videos/`` 下（与 v7 gen1 同一约定），
  或在 ``--gen-videos`` 给出的目录下按 ``<tier>/<task>_episode_<episode>/videos`` 查找；
  取文件名不以 ``FAILED``／``success_NO_OBJECT`` 开头、且含 ``_seed<seed>_`` 的那一个 mp4，必须恰好 1 个。
  ``delivery.json`` 口径（S2-B）：顶层 ``schema``、``rows``、``counts``、``cells``；每行 ``task``、``tier``、``episode``、
  ``candidate``、``seed``、``exec_steps``、``frames``、``h5``（绝对路径，优先）、``path``（相对 delivery.json 目录）、
  ``h5_sha256``、``env_module``、可选 ``video``（绝对路径）。缺 ``exec_steps``／``frames`` 即 FAIL。
- **xhard0**（16 任务 × 12 局）：复用 v7 已渲染的 ``site-media/xhard0-gen``（``manifest-{H,O}.jsonl``，0 次渲染），
  新入口 H／旧入口 O 两行，与 v7 相同。
- **评估**：v8 不做 SimpleMemVLA／MME-VLA 两策略评估（用户 2026-10-01，§2.8 第 16 条）。评估来源（v7 的
  ``records_*``、``official_*``、``eval_videos*``、``tables``、``rerun11``）一律不读；每局 ``eval`` 为空字典、
  ``eval_status = "unevaluated"``——「未评估」是独立状态，不是失败，页面任何成败筛选都不得命中。
- **配置**：每局从规格行 ``spec.objects``／``spec.actions`` 按 ``DIMS`` 抽取表 1 的维度值（不写死数值），
  逐格汇总取值集合；``TABLE1`` 是表 1 的参照值，只用来核对（``config_mismatch``），不进页面。
- **身份清单**：``eval-identities-1262.jsonl``（S2-B ``export_eval_identities.py`` 产出），总数由表 2 推出
  （``sum(V8_CELLS) + 16 × 12 = 1262``），非 xhard0 身份必须与交付集逐一相等。

输出 ``catalog.json``（schema ``v8-site-catalog/1``）与 ``media-private.json``（媒体 ID → 绝对路径白名单），
都以 ``open("x")`` 写入、拒绝覆盖。末行打印
``V8_SITE_CATALOG=PASS|FAIL identities=<n> expected=<n> gen_v8=<n> gen_xhard0_new=<n> gen_xhard0_old=<n>
gen_failed=<n> eval_unevaluated=<n> eval_filled=0 config_mismatch=0 media=<n> problems=<n>``。

    uv run --no-sync python scripts/injection-dev/site/v8_site_catalog.py \\
      --specs-root artifacts/newtask-v8/specs-root --delivery artifacts/newtask-v8/gen1/delivery.json \\
      --identities artifacts/newtask-v8/eval-identities-1262.jsonl \\
      --xhard0-gen artifacts/newtask-v7/site-media/xhard0-gen --out artifacts/newtask-v8/site

本模块只用标准库（``DIMS``／``TABLE1``／路径解析供 ``v8_subgoal_lengths.py`` 与浏览器检查器复用）；
``hard_specs`` 按文件路径加载（它只依赖标准库），不导入 ``robomme_hard`` 包。
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
ART8 = REPO_ROOT / "artifacts/newtask-v8"
ART7 = REPO_ROOT / "artifacts/newtask-v7"
TIERS = ("xhard0", "xhard1", "xhard2", "xhard3", "xhard4", "xhard5")
NEW_TIERS = TIERS[1:]
POLICIES = (("simplememvla", "SimpleMemVLA"), ("mmevla", "MME-VLA"))
XHARD0_PER_TASK = 12
DELIVERY_SCHEMA = "v8-delivery/1"
NAMES = {
    "BinFill": "分类投放", "PickXtimes": "重复抓取", "SwingXtimes": "重复摆动",
    "PickHighlight": "高亮目标抓取", "VideoUnmask": "视频遮挡记忆", "ButtonUnmask": "按钮遮挡记忆",
    "VideoUnmaskSwap": "视频遮挡交换", "ButtonUnmaskSwap": "按钮遮挡交换", "VideoRepick": "视频重复抓取",
    "PatternLock": "图案解锁", "RouteStick": "路线引导", "VideoPlaceButton": "视频放置与按钮",
    "VideoPlaceOrder": "视频放置顺序", "MoveCube": "移动方块", "InsertPeg": "插入插销", "StopCube": "停止方块",
}
DEFAULT_SOURCES = {
    "specs_root": ART8 / "specs-root",
    "delivery": ART8 / "gen1/delivery.json",
    "identities": ART8 / "eval-identities-1262.jsonl",
    "xhard0_gen": ART7 / "site-media/xhard0-gen",
    "gen_videos": None,
    "path_base": REPO_ROOT,
    "cells_json": None,
}


# ── 表 1 维度：从规格行抽值（不写死数值）──────────────────────────────────

def _objects(spec: dict) -> dict:
    return spec.get("objects") or {}


def _actions(spec: dict) -> dict:
    return spec.get("actions") or {}


def _swap_count(spec: dict):
    obj = _objects(spec)
    if obj.get("n_swaps") is not None:
        return obj["n_swaps"]
    pairs = _actions(spec).get("swap_pairs")
    return len(pairs) if pairs is not None else None


#: 任务 → [(维度名, 从 spec 取值的函数)]；维度名与表 1 的「维度」列一一对应（复合列拆成多行）。
DIMS = {
    "PickXtimes": [("抓放次数", lambda s: _objects(s).get("num_repeats")),
                   ("干扰块", lambda s: (_objects(s).get("distractor_count") or {}).get("actual"))],
    "SwingXtimes": [("摆动轮数", lambda s: _objects(s).get("num_repeats")),
                    ("干扰块", lambda s: (_objects(s).get("distractor_count") or {}).get("actual"))],
    "StopCube": [("停止序号 stop_time", lambda s: _actions(s).get("stop_time")),
                 ("方块速度 move_interval", lambda s: _actions(s).get("move_interval"))],
    "BinFill": [("投入块数", lambda s: sum(_objects(s)["target_numbers"]) if _objects(s).get("target_numbers") else None)],
    "VideoUnmask": [("抓取数", lambda s: _objects(s).get("n_picks")),
                    ("干扰容器", lambda s: (_objects(s).get("distractors") or {}).get("placed")),
                    ("干扰方块", lambda s: (_objects(s).get("distractors") or {}).get("cube_count"))],
    "VideoUnmaskSwap": [("换位次数", _swap_count), ("抓取数", lambda s: _objects(s).get("n_picks")),
                        ("外圈干扰", lambda s: (_objects(s).get("distractors") or {}).get("placed"))],
    "VideoPlaceButton": [("放置次数", lambda s: _actions(s).get("target_placement_count"))],
    "VideoPlaceOrder": [("访问总次数", lambda s: _actions(s).get("target_placement_count"))],
    "PickHighlight": [("抓取数", lambda s: _objects(s).get("highlight_count")),
                      ("总方块数", lambda s: _objects(s).get("n_cubes"))],
    "VideoRepick": [("方块数", lambda s: (_objects(s).get("cube_count") or {}).get("actual")),
                    ("换位", lambda s: _objects(s).get("n_swaps")),
                    ("重抓", lambda s: _objects(s).get("num_repeats"))],
    "RouteStick": [("路线段数", lambda s: _objects(s).get("L"))],
    "PatternLock": [("图案节点数", lambda s: len(_actions(s)["path_nodes"]) if _actions(s).get("path_nodes") else None)],
    "MoveCube": [],
    "InsertPeg": [],
}
DIMS["ButtonUnmask"] = DIMS["VideoUnmask"]
DIMS["ButtonUnmaskSwap"] = DIMS["VideoUnmaskSwap"]

#: 表 1 参照值（v8 方案第一部分 §1）：任务 → 维度 → 档 → 定值或 [lo, hi] 闭区间。只用于核对，不进页面。
TABLE1 = {
    "PickXtimes": {"抓放次数": {"xhard1": 6, "xhard2": 7, "xhard3": 8},
                   "干扰块": {"xhard1": 1, "xhard2": 2, "xhard3": 3}},
    "SwingXtimes": {"摆动轮数": {"xhard1": 4, "xhard2": 5, "xhard3": 6, "xhard4": 7, "xhard5": 8},
                    "干扰块": {"xhard1": 1, "xhard2": 2, "xhard3": 3, "xhard4": 4, "xhard5": 4}},
    "StopCube": {"停止序号 stop_time": {"xhard1": 6, "xhard2": 7, "xhard3": 8, "xhard4": 9, "xhard5": 10},
                 "方块速度 move_interval": {t: 60 for t in NEW_TIERS}},
    "BinFill": {"投入块数": {"xhard1": 6, "xhard2": 7}},
    "VideoUnmask": {"抓取数": {"xhard1": 2, "xhard2": 3, "xhard3": 3, "xhard4": 3},
                    "干扰容器": {"xhard1": 4, "xhard2": 4, "xhard3": 8, "xhard4": 12},
                    "干扰方块": {"xhard1": 2, "xhard2": 2, "xhard3": 4, "xhard4": 6}},
    "VideoUnmaskSwap": {"换位次数": {"xhard1": 5, "xhard2": 7}, "抓取数": {"xhard1": 2, "xhard2": 3},
                        "外圈干扰": {"xhard1": 2, "xhard2": 4}},
    "ButtonUnmaskSwap": {"换位次数": {"xhard1": 3, "xhard2": 5}, "抓取数": {"xhard1": 2, "xhard2": 3},
                         "外圈干扰": {"xhard1": 2, "xhard2": 4}},
    "VideoPlaceButton": {"放置次数": {"xhard1": 3, "xhard2": 4}},
    "VideoPlaceOrder": {"访问总次数": {"xhard1": 5, "xhard2": 6}},
    "PickHighlight": {"抓取数": {"xhard1": 4, "xhard2": 5}, "总方块数": {"xhard1": 7, "xhard2": 8}},
    "VideoRepick": {"方块数": {"xhard1": 4, "xhard2": 5}, "换位": {"xhard1": 4, "xhard2": 6},
                    "重抓": {"xhard1": 2, "xhard2": 3}},
    "RouteStick": {"路线段数": {"xhard1": [8, 10], "xhard2": [11, 13], "xhard3": [14, 16]}},
    "PatternLock": {"图案节点数": {"xhard1": [9, 12], "xhard2": [13, 15], "xhard3": [16, 18]}},
    "MoveCube": {}, "InsertPeg": {},
}
TABLE1["ButtonUnmask"] = TABLE1["VideoUnmask"]
NO_DIM_TEXT = "官方 xhard4 配置（本任务没有档位梯度，表 1「不动」）"
XHARD0_TEXT = "官方 hard（xhard0 不动），各局配置随机；逐局页列出能从本局 subgoal 数出的值"


def table1_ok(task: str, dim: str, tier: str, value) -> bool:
    """值是否符合表 1：定值相等，区间落在 [lo, hi] 内。"""
    want = TABLE1.get(task, {}).get(dim, {}).get(tier)
    if want is None or value is None:
        return False
    if isinstance(want, list):
        return want[0] <= value <= want[1]
    return value == want


def spec_config(task: str, spec: dict) -> dict:
    """一局的维度值 {维度名: 值}（取不到为 None）。"""
    out = {}
    for dim, fn in DIMS[task]:
        try:
            out[dim] = fn(spec)
        except (KeyError, TypeError):
            out[dim] = None
    return out


# ── 路径与通用读写 ────────────────────────────────────────────────────


class Media:
    """媒体白名单：ID = sha256(键)[:24]，值为解析后的绝对路径。"""

    def __init__(self):
        self.paths: dict[str, str] = {}

    def add(self, key: str, path: Path) -> str:
        path = Path(path).resolve(strict=True)
        if path.suffix.lower() != ".mp4":
            raise ValueError(f"不是 mp4：{path}")
        ident = hashlib.sha256(key.encode()).hexdigest()[:24]
        if self.paths.setdefault(ident, str(path)) != str(path):
            raise ValueError(f"媒体 ID 冲突：{key}")
        return ident


def jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def resolve(path: str | Path, *bases: Path) -> Path:
    """绝对路径原样；相对路径依次相对各 base 查找，取第一个存在的（都不存在时返回第一个 base 下的拼接）。"""
    p = Path(path)
    if p.is_absolute():
        return p
    for base in bases:
        if base is not None and (Path(base) / p).exists():
            return Path(base) / p
    return Path(bases[0]) / p


def load_delivery(path: Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("schema") != DELIVERY_SCHEMA:
        raise ValueError(f"delivery.json schema 应为 {DELIVERY_SCHEMA}，实为 {data.get('schema')!r}")
    return data


def delivery_h5(row: dict, delivery_path: Path, path_base: Path) -> Path:
    """逐局 h5：按 ``h5``（S2-B 口径为绝对路径，优先）→ ``h5_path`` → ``path``（相对 delivery.json 目录）取第一个；相对路径先相对 delivery.json 所在目录，再相对 path_base。"""
    raw = row.get("h5") or row.get("h5_path") or row.get("path")
    if not raw:
        raise ValueError(f"delivery 行缺 h5 路径：{row.get('task')}/{row.get('tier')}/{row.get('seed')}")
    return resolve(raw, Path(delivery_path).resolve().parent, path_base)


def pick_gen_video(h5: Path, row: dict, gen_videos: Path | None, delivery_path: Path | None = None,
                   path_base: Path | None = None) -> Path:
    """生成视频：先看 ``video``／``mp4`` 字段（相对路径与 h5 同口径：先相对 delivery.json 所在目录、再相对
    ``path_base``），再看 h5 同 episode 的 ``videos/``，再看 ``--gen-videos``。"""
    seed = int(row["seed"])
    if row.get("video") or row.get("mp4"):
        bases = [b for b in (Path(delivery_path).resolve().parent if delivery_path else None, path_base) if b is not None]
        return resolve(row.get("video") or row.get("mp4"), *(bases or [REPO_ROOT]))
    dirs = [h5.parent.parent / "videos"]
    if gen_videos is not None:
        dirs.append(Path(gen_videos) / row["tier"] / f"{row['task']}_episode_{row['episode']}" / "videos")
    for videos in dirs:
        if not videos.is_dir():
            continue
        hits = [p for p in sorted(videos.glob("*.mp4"))
                if not p.name.startswith(("FAILED", "success_NO_OBJECT")) and f"_seed{seed}_" in p.name]
        if len(hits) == 1:
            return hits[0]
        if hits:
            raise ValueError(f"{videos} 下符合条件的 mp4 有 {len(hits)} 个（应为 1）")
    raise ValueError(f"找不到生成视频：{row['task']}/{row['tier']}/seed {seed}（查过 {[str(d) for d in dirs]}）")


def load_hard_specs():
    """按文件路径加载 ``hard_specs``（只依赖标准库），不触发 ``robomme_hard`` 包导入（torch／sapien）。"""
    name = "_v8_site_hard_specs"
    if name in sys.modules:
        return sys.modules[name]
    path = REPO_ROOT / "src/robomme_hard/env_record_wrapper/hard_specs.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_cells(cells_json) -> dict[tuple[str, str], int]:
    """交付格表：缺省 ``V8_CELLS``（43 格 1070）；``--cells-json`` 给 {"Task/tier": n} 子表（冒烟／合成夹具）。"""
    H = load_hard_specs()
    if cells_json is None:
        return dict(H.V8_CELLS)
    raw = json.loads(Path(cells_json).read_text(encoding="utf-8"))
    return {tuple(key.split("/")): int(n) for key, n in raw.items()}


def expected_identities(cells: dict[tuple[str, str], int], n_tasks: int = len(NAMES)) -> int:
    """表 2 推出的身份总数：新值局 + 16 任务 × 12 局 xhard0（完整根 = 1070 + 192 = 1262）。"""
    return sum(cells.values()) + n_tasks * XHARD0_PER_TASK


# ── 构建 ────────────────────────────────────────────────────────────


def build_catalog(src: dict) -> tuple[dict, dict, dict]:
    H = load_hard_specs()

    media = Media()
    problems: list[str] = []
    counts = Counter()
    path_base = Path(src.get("path_base") or REPO_ROOT)
    cells_want = load_cells(src.get("cells_json"))
    full = cells_want == dict(H.V8_CELLS)
    expected = expected_identities(cells_want)
    if full and expected != 1262:
        problems.append(f"表 2 推出的身份总数 {expected} ≠ 1262")

    # 规格（/4，load_specs_v8 校验格表、selected 行数、跨档 seed 不交）
    specs = H.load_specs_v8(src["specs_root"], cells_want, check_fingerprint=False)
    spec_rows: dict[tuple, dict] = {}
    exec_cap: dict[str, int] = {}
    for tier, (header, rows) in specs.items():
        exec_cap[tier] = header["exec_cap"]
        for row in rows:
            if row["selected"]:
                spec_rows[(tier, row["task"], int(row["seed"]))] = row

    # 生成交付
    delivery_path = Path(src["delivery"])
    delivery = load_delivery(delivery_path)
    gen = {}
    for row in delivery["rows"]:
        key = (row["tier"], row["task"], int(row["seed"]))
        if key in gen:
            problems.append(f"delivery 身份重复 {key}")
        gen[key] = row
    if set(gen) != set(spec_rows):
        problems.append(f"delivery 与规格 selected 行不一致：缺 {sorted(set(spec_rows) - set(gen))[:5]}，"
                        f"多 {sorted(set(gen) - set(spec_rows))[:5]}")

    # xhard0 生成（v7 已渲染，0 次渲染）
    xgen = {side: {(r["task"], int(r["seed"])): r for r in jsonl(Path(src["xhard0_gen"]) / f"manifest-{side}.jsonl")}
            for side in ("H", "O")}

    # 身份清单
    idents = jsonl(src["identities"])
    by_key = {(r["tier"], r["task"], int(r["seed"])): r for r in idents}
    if len(by_key) != len(idents):
        problems.append("身份清单 (tier, task, seed) 不唯一")
    new_keys = {k for k in by_key if k[0] != "xhard0"}
    if new_keys != set(gen):
        problems.append(f"身份清单新值局与 delivery 不一致：缺 {sorted(set(gen) - new_keys)[:5]}，"
                        f"多 {sorted(new_keys - set(gen))[:5]}")
    x0_per_task = Counter(k[1] for k in by_key if k[0] == "xhard0")
    if x0_per_task != Counter({task: XHARD0_PER_TASK for task in NAMES}):
        problems.append(f"xhard0 身份应为 16 任务 × {XHARD0_PER_TASK}：{dict(x0_per_task)}")

    cells: dict[tuple, list[dict]] = defaultdict(list)
    order = lambda k: (TIERS.index(k[0]), k[1], by_key[k].get("candidate") if by_key[k].get("candidate") is not None
                       else -1, by_key[k].get("source_episode") or 0, by_key[k].get("episode") or 0)
    for key in sorted(by_key, key=order):
        tier, task, seed = key
        if tier not in TIERS or task not in NAMES:
            problems.append(f"未知档位或任务 {key}")
            continue
        ident = by_key[key]
        ep = {"seed": seed, "eval_episode": ident.get("episode"), "round": ident.get("round"),
              "shard": ident.get("shard"), "candidate": ident.get("candidate"),
              "source_episode": ident.get("source_episode"),
              "gen": {}, "eval": {}, "eval_status": "unevaluated"}
        counts["eval_unevaluated"] += 1
        if tier == "xhard0":
            for side, entry in (("H", "new"), ("O", "old")):
                row = xgen[side].get((task, seed))
                if row is None:
                    problems.append(f"xhard0 {side} 缺生成记录 {task}/{seed}")
                    continue
                item = {"frames": row["frames"], "demo_frames": row["demo_frames"], "h5_sha12": row["h5_sha256"][:12]}
                if row.get("generation_failed"):
                    item["status"] = "generation_failed"
                    counts["gen_failed"] += 1
                else:
                    try:
                        item["media"] = media.add(f"gen/{entry}/{tier}/{task}/{seed}", resolve(row["mp4"], path_base))
                        counts[f"gen_{entry}_xhard0"] += 1
                    except (OSError, ValueError) as exc:
                        problems.append(f"xhard0 {side} 视频不可用 {task}/{seed}：{exc}")
                ep["gen"][entry] = item
        else:
            row = gen.get(key)
            spec = spec_rows.get(key)
            if row is None or spec is None:
                problems.append(f"缺交付或规格行 {key}")
            else:
                ep["episode"] = row.get("episode")
                ep["exec_cap"] = exec_cap.get(tier)
                try:
                    h5 = delivery_h5(row, delivery_path, path_base)
                    missing_keys = [k for k in ("exec_steps", "frames") if row.get(k) is None]
                    if missing_keys:
                        raise ValueError(f"delivery 行缺 {missing_keys}：{key}")
                    video = pick_gen_video(h5, row, src.get("gen_videos"), delivery_path, path_base)
                    item = {"frames": row.get("frames"), "exec_steps": row.get("exec_steps"),
                            "media": media.add(f"gen/new/{tier}/{task}/{seed}", video)}
                    if row.get("frames") is not None and row.get("exec_steps") is not None:
                        item["demo_frames"] = row["frames"] - row["exec_steps"]
                    ep["gen"]["new"] = item
                    counts["gen_v8"] += 1
                except (OSError, ValueError) as exc:
                    problems.append(str(exc))
                cfg = spec_config(task, spec["spec"])
                ep["config"] = cfg
                for dim, value in cfg.items():
                    if not table1_ok(task, dim, tier, value):
                        counts["config_mismatch"] += 1
                        problems.append(f"配置与表 1 不符 {task}/{tier}/seed {seed}：{dim}={value!r}")
        cells[(task, tier)].append(ep)

    tasks = []
    for task in NAMES:
        tiers = {}
        for tier in TIERS:
            eps = cells.get((task, tier))
            if not eps:
                continue
            for i, ep in enumerate(eps, 1):
                ep["idx"] = i
            entry = {"episodes": eps, "rates": {}, "eval_status": "unevaluated"}
            if tier == "xhard0":
                entry["config"] = [{"dim": None, "values": [], "text": XHARD0_TEXT}]
            elif not DIMS[task]:
                entry["config"] = [{"dim": None, "values": [], "text": NO_DIM_TEXT}]
            else:
                entry["config"] = []
                for dim, _ in DIMS[task]:
                    dist = Counter(ep["config"][dim] for ep in eps if "config" in ep)
                    entry["config"].append({"dim": dim, "values": sorted(v for v in dist if v is not None),
                                            "dist": {str(k): n for k, n in sorted(dist.items(), key=lambda x: str(x[0]))}})
            tiers[tier] = entry
        tasks.append({"id": task, "name": NAMES[task], "tiers": tiers})

    catalog = {
        "schema": "v8-site-catalog/1",
        "tiers": list(TIERS),
        "policies": [{"id": p, "label": label} for p, label in POLICIES],
        "eval": {"status": "unevaluated",
                 "reason": "v8 新局不做 SimpleMemVLA／MME-VLA 两策略评估（用户 2026-10-01）；评估板块原位保留、内容置空。"},
        "tasks": tasks,
        "notes": {
            "eval": "评估位一律显示「未评估」：v8 不做两策略评估，评估板块（成功率、成败筛选、两段策略视频、旧入口对照、翻转标记）"
                    "原位保留、内容置空。「未评估」不是失败，任何成败筛选都不会命中。",
            "config": "xhard1～5 的任务配置逐局取自 v8 冻结规格（hard-specs/4）的规格行，格内汇总为取值集合；"
                      "RouteStick／PatternLock 是区间，列出实际取值分布。",
            "xhard0_gen": "xhard0 生成视频复用 v7 由 h5 离线合成的版本（左前视、右腕部，左上角 DEMO／EXEC），版式与录像器视频不同；"
                          "新入口 h5 与旧入口逐字节相同，两行生成视频因此相同。",
            "gen_failed": "VideoPlaceOrder 有 2 局官方原版在该 seed 上即生成失败（DatasetGenerationError），两入口相同，无生成视频。",
        },
    }
    stats = {"identities": len(by_key), "expected": expected, "counts": dict(counts),
             "problems": problems, "media": len(media.paths)}
    return catalog, media.paths, stats


def verdict_line(stats: dict, ok: bool) -> str:
    c = stats["counts"]
    return (f"V8_SITE_CATALOG={'PASS' if ok else 'FAIL'} identities={stats['identities']} expected={stats['expected']} "
            f"gen_v8={c.get('gen_v8', 0)} gen_xhard0_new={c.get('gen_new_xhard0', 0)} "
            f"gen_xhard0_old={c.get('gen_old_xhard0', 0)} gen_failed={c.get('gen_failed', 0)} "
            f"eval_unevaluated={c.get('eval_unevaluated', 0)} eval_filled=0 "
            f"config_mismatch={c.get('config_mismatch', 0)} media={stats['media']} problems={len(stats['problems'])}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, required=True)
    for name, default in DEFAULT_SOURCES.items():
        ap.add_argument(f"--{name.replace('_', '-')}", dest=name, default=default, type=Path)
    args = ap.parse_args(argv)
    src = {name: getattr(args, name) for name in DEFAULT_SOURCES}
    try:
        catalog, media, stats = build_catalog(src)
    except Exception as exc:  # 规格校验、文件缺失等：照实 FAIL，不写产物
        print(f"# {type(exc).__name__}: {exc}", flush=True)
        print("V8_SITE_CATALOG=FAIL identities=0 expected=0 gen_v8=0 gen_xhard0_new=0 gen_xhard0_old=0 gen_failed=0 "
              "eval_unevaluated=0 eval_filled=0 config_mismatch=0 media=0 problems=1", flush=True)
        return 1
    for problem in stats["problems"][:40]:
        print(f"# {problem}", flush=True)
    ok = not stats["problems"] and stats["identities"] == stats["expected"]
    targets = [args.out / "catalog.json", args.out / "media-private.json"]
    exists = [str(t) for t in targets if t.exists()]
    if ok and exists:  # 写入前确认两个目标都不存在，不留半份产物
        print(f"# 目标文件已存在，拒绝覆盖：{exists}", flush=True)
        stats["problems"].append("目标文件已存在")
        ok = False
    if stats["identities"] != stats["expected"]:
        print(f"# 身份总数 {stats['identities']} ≠ 表 2 推出的 {stats['expected']}", flush=True)
    if ok:
        args.out.mkdir(parents=True, exist_ok=True)
        with (args.out / "catalog.json").open("x", encoding="utf-8") as handle:
            json.dump(catalog, handle, ensure_ascii=False, separators=(",", ":"))
        with (args.out / "media-private.json").open("x", encoding="utf-8") as handle:
            json.dump(media, handle, ensure_ascii=False, indent=0)
    print(verdict_line(stats, ok), flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
