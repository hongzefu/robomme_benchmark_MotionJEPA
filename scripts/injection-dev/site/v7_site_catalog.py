#!/usr/bin/env python3
"""v7 对照站点目录（0929 站点方案 §2）：把 1292 个评估身份的生成视频与两策略评估视频逐局拼到一起。

拼接键一律为 ``(tier, task, seed)``。三类视频各自的 episode 编号口径不同，所以不按 episode 号拼。

- **v7 生成**（xhard1～4，1100 局）：``gen1/delivery.json`` 的 ``rows[]``。在同一 episode 目录 ``videos/`` 下，
  取文件名不以 ``FAILED``／``success_NO_OBJECT`` 开头、且含 ``_seed<seed>_`` 的那一个 mp4，每行必须恰好 1 个。
- **xhard0 生成**（新入口 H／旧入口 O，各 192 局）：``v7_render_xhard0.py`` 的 ``manifest-{H,O}.jsonl``。
  其中 2 局是官方原版就生成失败的空 h5，页面照实标注。
- **新入口评估**：状态与步数取两策略 v7 逐局记录，同一身份取最后一个终态行；视频取
  ``eval-videos/<策略>/moved.jsonl``，跳过冒烟行。MME 两局 error 取 ``eval-videos/mmevla/_errors/*.errorN.mp4``。
- **旧入口评估**（xhard0）：状态与步数取 ``official-<策略>-summary.json``，视频取
  ``eval-videos-official/<策略>/moved.jsonl``。

逐格核对：新入口成败数与 ``eval/<策略>-table.json`` 逐格相等；旧入口成功数与官方汇总相等。
输出 ``catalog.json``（schema ``v7-site-catalog/1``）与 ``media-private.json``（媒体 ID 到绝对路径的白名单）。
两个文件都以 ``open("x")`` 写入，拒绝覆盖。末行打印 ``V7_SITE_CATALOG=PASS|FAIL …``。

    uv run --no-sync python scripts/injection-dev/site/v7_site_catalog.py --out artifacts/newtask-v7/site
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
ART = REPO_ROOT / "artifacts/newtask-v7"
NFS = Path("/nfs/turbo/coe-chaijy-unreplicated/hongzefu")
TIERS = ("xhard0", "xhard1", "xhard2", "xhard3", "xhard4")
POLICIES = (("simplememvla", "SimpleMemVLA"), ("mmevla", "MME-VLA"))
FINAL = ("success", "fail", "timeout")
NAMES = {
    "BinFill": "分类投放", "PickXtimes": "重复抓取", "SwingXtimes": "重复摆动",
    "PickHighlight": "高亮目标抓取", "VideoUnmask": "视频遮挡记忆", "ButtonUnmask": "按钮遮挡记忆",
    "VideoUnmaskSwap": "视频遮挡交换", "ButtonUnmaskSwap": "按钮遮挡交换", "VideoRepick": "视频重复抓取",
    "PatternLock": "图案解锁", "RouteStick": "路线引导", "VideoPlaceButton": "视频放置与按钮",
    "VideoPlaceOrder": "视频放置顺序", "MoveCube": "移动方块", "InsertPeg": "插入插销", "StopCube": "停止方块",
}
DEFAULT_SOURCES = {
    "identities": ART / "eval-identities-1292.jsonl",
    "delivery": ART / "gen1/delivery.json",
    "xhard0_gen": ART / "site-media/xhard0-gen",
    "records_simplememvla": str(NFS / "SimpleMemVLA/logs/testhard/v7/results-r*-shard*.jsonl"),
    "records_mmevla": str(NFS / "v7-eval/mme-v7-r*-s*/mmevla-testhard/ckpt79999/seed7/episodes.jsonl"),
    "official_simplememvla": NFS / "v7-eval/official-simplememvla-summary.json",
    "official_mmevla": NFS / "v7-eval/official-mmevla-summary.json",
    "eval_videos": ART / "eval-videos",
    "eval_videos_official": ART / "eval-videos-official",
    "tables": ART / "eval",
}
ERROR_NAME = re.compile(r"(?P<task>[A-Za-z]+)_(?P<tier>xhard\d)_(?P<ep>\d+)_(?P<seed>\d+)\.error(?P<n>\d+)\.mp4\Z")


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
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def pick_gen1_video(h5: Path, seed: int) -> Path:
    videos = h5.parent.parent / "videos"
    hits = [p for p in sorted(videos.glob("*.mp4"))
            if not p.name.startswith(("FAILED", "success_NO_OBJECT")) and f"_seed{seed}_" in p.name]
    if len(hits) != 1:
        raise ValueError(f"{videos} 下符合条件的 mp4 有 {len(hits)} 个（应为 1）")
    return hits[0]


def last_terminal(rows: list[dict]) -> tuple[dict | None, list[dict]]:
    """同一身份：取最后一个终态行；另返回 error 行（MME 三遍重评仍失败的局只有 error 行）。"""
    final = [r for r in rows if r.get("status") in FINAL]
    return (final[-1] if final else None), [r for r in rows if r.get("status") == "error"]


def load_new_records(pattern: str) -> dict[tuple, list[dict]]:
    grouped: dict[tuple, list[dict]] = defaultdict(list)
    for path in sorted(glob.glob(pattern)):
        for row in jsonl(Path(path)):
            tier = row.get("tier") or (row.get("identity") or {}).get("tier")
            grouped[(tier, row["task"], int(row["seed"]))].append(row)
    return grouped


def load_moved(path: Path) -> dict[tuple, dict]:
    out = {}
    for row in jsonl(path):
        if "/smoke/" in row["src"]:
            continue  # 冒烟局与正式局同名，已被正式版覆盖
        out[(row["tier"], row["task"], int(row["seed"]))] = row
    return out


def build_catalog(src: dict) -> tuple[dict, dict, dict]:
    media = Media()
    problems: list[str] = []
    idents = jsonl(src["identities"])
    by_key = {(r["tier"], r["task"], int(r["seed"])): r for r in idents}
    if len(by_key) != len(idents):
        problems.append("评估清单 (tier, task, seed) 不唯一")

    gen1 = {(r["tier"], r["task"], int(r["seed"])): r for r in json.loads(Path(src["delivery"]).read_text())["rows"]}
    xgen = {side: {(r["task"], int(r["seed"])): r for r in jsonl(Path(src["xhard0_gen"]) / f"manifest-{side}.jsonl")}
            for side in ("H", "O")}
    new_rec = {p: load_new_records(src[f"records_{p}"]) for p, _ in POLICIES}
    new_vid = {p: load_moved(Path(src["eval_videos"]) / p / "moved.jsonl") for p, _ in POLICIES}
    old_rec = {p: {(r["task"], int(r["seed"])): r for r in json.loads(Path(src[f"official_{p}"]).read_text())["records"]}
               for p, _ in POLICIES}
    old_vid = {p: {(r["task"], int(r["seed"])): r for r in jsonl(Path(src["eval_videos_official"]) / p / "moved.jsonl")}
               for p, _ in POLICIES}
    errors: dict[tuple, list[Path]] = defaultdict(list)
    for p, _ in POLICIES:
        for path in sorted((Path(src["eval_videos"]) / p / "_errors").glob("*.mp4")):
            m = ERROR_NAME.match(path.name)
            if m:
                errors[(p, m["tier"], m["task"], int(m["seed"]))].append(path)

    counts = Counter()
    cells: dict[tuple, list[dict]] = defaultdict(list)
    for key in sorted(by_key, key=lambda k: (TIERS.index(k[0]), k[1], by_key[k].get("candidate") or 0,
                                             by_key[k].get("source_episode") or 0)):
        tier, task, seed = key
        ident = by_key[key]
        ep = {"seed": seed, "eval_episode": ident["episode"], "round": ident["round"],
              "candidate": ident.get("candidate"), "source_episode": ident.get("source_episode"),
              "gen": {}, "eval": {"new": {}}}
        # 生成
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
                    item["media"] = media.add(f"gen/{entry}/{tier}/{task}/{seed}", REPO_ROOT / row["mp4"])
                    counts[f"gen_{entry}_xhard0"] += 1
                ep["gen"][entry] = item
        else:
            row = gen1.get(key)
            if row is None:
                problems.append(f"gen1 缺交付 {key}")
            else:
                try:
                    video = pick_gen1_video(ART / "gen1" / row["path"], seed)
                    ep["gen"]["new"] = {"frames": row["frames"],
                                        "media": media.add(f"gen/new/{tier}/{task}/{seed}", video)}
                    counts["gen_v7"] += 1
                except ValueError as exc:
                    problems.append(str(exc))
        # 新入口评估
        for p, _ in POLICIES:
            final, err_rows = last_terminal(new_rec[p].get(key, []))
            if final is not None:
                vid = new_vid[p].get(key)
                item = {"status": final["status"], "steps": final.get("steps"), "max_steps": final.get("max_steps")}
                if vid is None:
                    problems.append(f"{p} 新入口缺视频 {key}")
                else:
                    item["media"] = media.add(f"eval/new/{p}/{tier}/{task}/{seed}", Path(vid["dest"]))
                    counts[f"eval_new_{p}"] += 1
                    if vid["status"] != final["status"]:
                        problems.append(f"{p} 视频状态与记录不符 {key}")
            elif err_rows:
                clips = errors.get((p, tier, task, seed), [])
                item = {"status": "error", "steps": err_rows[-1].get("steps"), "max_steps": err_rows[-1].get("max_steps"),
                        "attempts": [media.add(f"eval/new/{p}/{tier}/{task}/{seed}/{c.name}", c) for c in clips]}
                counts[f"eval_new_{p}_error"] += 1
                counts[f"eval_new_{p}_error_clips"] += len(clips)
            else:
                problems.append(f"{p} 新入口缺记录 {key}")
                continue
            ep["eval"]["new"][p] = item
        # 旧入口评估（仅 xhard0）
        if tier == "xhard0":
            ep["eval"]["old"] = {}
            ep["flip"] = {}
            for p, _ in POLICIES:
                rec, vid = old_rec[p].get((task, seed)), old_vid[p].get((task, seed))
                if rec is None or vid is None:
                    problems.append(f"{p} 旧入口缺记录或视频 {task}/{seed}")
                    continue
                ep["eval"]["old"][p] = {"status": rec["status"], "steps": rec.get("steps"), "max_steps": rec.get("max_steps"),
                                        "media": media.add(f"eval/old/{p}/{tier}/{task}/{seed}", Path(vid["dest"]))}
                counts[f"eval_old_{p}"] += 1
                new = ep["eval"]["new"].get(p, {}).get("status")
                ep["flip"][p] = new != rec["status"]
                counts[f"flip_{p}"] += new != rec["status"]
        cells[(task, tier)].append(ep)

    # 逐格核对与汇总
    mismatch = 0
    tasks = []
    for task in NAMES:
        tiers = {}
        for tier in TIERS:
            eps = cells.get((task, tier))
            if not eps:
                continue
            for i, ep in enumerate(eps, 1):
                ep["idx"] = i
            rates = {"new": {}}
            for p, _ in POLICIES:
                rates["new"][p] = dict(Counter(ep["eval"]["new"][p]["status"] for ep in eps if p in ep["eval"]["new"]))
            if tier == "xhard0":
                rates["old"] = {p: dict(Counter(ep["eval"]["old"][p]["status"] for ep in eps if p in ep["eval"]["old"]))
                                for p, _ in POLICIES}
            for p, _ in POLICIES:
                table = json.loads((Path(src["tables"]) / f"{p}-table.json").read_text()).get(f"{task}/{tier}", {})
                if {k: v for k, v in table.items() if v} != {k: v for k, v in rates["new"][p].items() if v}:
                    mismatch += 1
                    problems.append(f"{p} {task}/{tier} 成败数与 table.json 不符：{rates['new'][p]} vs {table}")
            tiers[tier] = {"rates": rates, "episodes": eps}
        tasks.append({"id": task, "name": NAMES[task], "tiers": tiers})
    for p, _ in POLICIES:
        want = json.loads(Path(src[f"official_{p}"]).read_text())["records"]
        got = sum(t["tiers"]["xhard0"]["rates"]["old"][p].get("success", 0) for t in tasks if "xhard0" in t["tiers"])
        if got != sum(r["status"] == "success" for r in want):
            mismatch += 1
            problems.append(f"{p} 旧入口成功数 {got} 与官方汇总不符")

    catalog = {
        "schema": "v7-site-catalog/1",
        "tiers": list(TIERS),
        "policies": [{"id": p, "label": label} for p, label in POLICIES],
        "tasks": tasks,
        "notes": {
            "xhard0_gen": "xhard0 生成视频由 h5 离线合成（左前视、右腕部，左上角 DEMO／EXEC），版式与 v7 录像器的 1280×768 视频不同。"
                          "新入口 h5 与旧入口逐字节相同（PARITY_O_H xhard0 sha_equal=192），两行生成视频因此相同；"
                          "新旧入口的差别看评估栏。",
            "gen_failed": "VideoPlaceOrder seed 610701、611101：官方原版在该 seed 上即生成失败（DatasetGenerationError），两入口相同，无生成视频；评估照常进行。",
            "error": "error 局不计入成功，列出三遍重评的录像。",
        },
    }
    stats = {"identities": len(by_key), "counts": dict(counts), "table_mismatch": mismatch,
             "problems": problems, "media": len(media.paths)}
    return catalog, media.paths, stats


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, required=True)
    for name, default in DEFAULT_SOURCES.items():
        ap.add_argument(f"--{name.replace('_', '-')}", dest=name, default=default)
    args = ap.parse_args(argv)
    src = {name: getattr(args, name) for name in DEFAULT_SOURCES}
    catalog, media, stats = build_catalog(src)
    for problem in stats["problems"][:40]:
        print(f"# {problem}", flush=True)
    c = stats["counts"]
    ok = not stats["problems"] and stats["identities"] == 1292
    line = (f"V7_SITE_CATALOG={'PASS' if ok else 'FAIL'} identities={stats['identities']} "
            f"gen_v7={c.get('gen_v7', 0)} gen_xhard0_new={c.get('gen_new_xhard0', 0)} gen_xhard0_old={c.get('gen_old_xhard0', 0)} "
            f"gen_failed={c.get('gen_failed', 0)} "
            + " ".join(f"eval_new_{p}={c.get(f'eval_new_{p}', 0)}(+{c.get(f'eval_new_{p}_error', 0)}err/"
                       f"{c.get(f'eval_new_{p}_error_clips', 0)}clips) eval_old_{p}={c.get(f'eval_old_{p}', 0)} "
                       f"flip_{p}={c.get(f'flip_{p}', 0)}" for p, _ in POLICIES)
            + f" media={stats['media']} table_mismatch={stats['table_mismatch']} problems={len(stats['problems'])}")
    if ok:
        args.out.mkdir(parents=True, exist_ok=True)
        with (args.out / "catalog.json").open("x", encoding="utf-8") as handle:
            json.dump(catalog, handle, ensure_ascii=False, separators=(",", ":"))
        with (args.out / "media-private.json").open("x", encoding="utf-8") as handle:
            json.dump(media, handle, ensure_ascii=False, indent=0)
    print(line, flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
