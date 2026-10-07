#!/usr/bin/env python3
"""第三阶段 OOD 五模型视频站：按各组已验收的发布清单建目录，或复用白名单服务器托管。

只放视频与成功率，不放语言记录。版式沿用 ``official_overlay.html``（8083 Oracle 站），增加模型维度。

    uv run --no-sync python scripts/injection-dev/site/stage3_eval_site.py --run-root <R> --site-dir <R>/site-stage3
    uv run --no-sync python scripts/injection-dev/site/stage3_eval_site.py --serve --site-dir <R>/site-stage3 --media-root <R> --port 8084
"""
from __future__ import annotations

import argparse
import csv
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
TASKS = ("BinFill", "PickXtimes", "SwingXtimes", "PickHighlight", "VideoUnmask", "ButtonUnmask",
         "VideoUnmaskSwap", "ButtonUnmaskSwap", "VideoRepick", "PatternLock", "RouteStick",
         "VideoPlaceButton", "VideoPlaceOrder", "MoveCube", "InsertPeg", "StopCube")
SCHEMA = "stage3-eval-site/1"
FINAL = ("success", "fail", "timeout")
# (站内 ID, 展示名, 发布目录, 发布清单 src_rel 的候选根)；PonderPounce 用 FIX-3 后的 r2 重跑，MemER 用已接受视图。
MODELS = (
    ("smvla", "SimpleMemVLA", "publish/smvla/seed7/videos", ("media/smvla/ood/new",)),
    ("pp", "PonderPounce", "publish-pp-r2/pp/seed7/videos", ("media-pp-r2/pp/ood/new",)),
    ("groundsg-qwenvl", "GroundSG+QwenVL", "publish/groundsg/seed7/qwenvl/videos",
     ("media/groundsg-ground-sg-qwenvl/ood/new",)),
    ("groundsg-memer", "MemER", "publish/groundsg/seed7/memer/videos", ("reports/memer/accepted-view",)),
    ("framesamp", "FrameSamp+Modulation", "publish/perceptual-framesamp-modul/seed7/videos",
     ("media/perceptual-framesamp-modul/ood/new",)),
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def locate(root: Path, bases: tuple[str, ...], rel: str) -> Path:
    """src_rel 必须在候选根里恰好命中一个实体文件。"""
    hits = [root / base / rel for base in bases if (root / base / rel).is_file()]
    require(len(hits) == 1, f"源视频定位不唯一：{rel}（命中 {len(hits)}）")
    return hits[0]


def trace_ends(path: Path) -> tuple[dict, dict, dict]:
    """只读轨迹头部（header、demo）与末行（end），不整份读 NFS 上的大文件。"""
    header = demo = None
    with path.open(encoding="utf-8") as stream:
        for _, line in zip(range(20), stream):
            row = json.loads(line)
            if row.get("kind") == "header":
                header = row
            elif row.get("kind") == "demo":
                demo = row
                break
    with path.open("rb") as stream:
        stream.seek(0, 2)
        stream.seek(max(0, stream.tell() - 65536))
        end = json.loads(stream.read().decode("utf-8").rstrip("\n").rsplit("\n", 1)[-1])
    require(header is not None and demo is not None and end.get("kind") == "end", f"轨迹首尾不完整：{path}")
    return header, demo, end


def model_entries(root: Path, model: str, bases: tuple[str, ...], publish: Path) -> tuple[list, dict]:
    rows = list(csv.DictReader((publish / "index.tsv").open(encoding="utf-8"), delimiter="\t"))
    require(len(rows) == 86, f"{model} 发布清单局数 {len(rows)} 不是 86")
    entries, media, keys = [], {}, set()
    for row in rows:
        key, status = row["key"], row["terminal"]
        require(status in FINAL and key not in keys, f"{model} 终态或重复：{key}")
        keys.add(key)
        official = locate(root, bases, row["src_rel"])
        # 发布目录是硬链接：同 inode 即已验收的那一份，不再全量哈希。
        require(official.stat().st_ino == (publish / row["dst_name"]).stat().st_ino, f"{model} 发布与源不是同一文件：{key}")
        episode_dir = official.parent.parent
        original = episode_dir / "episode.mp4"
        require(original.is_file() and original.stat().st_size > 0, f"{model} 缺原始视频：{key}")
        header, demo, end = trace_ends(episode_dir / "trace.jsonl")
        require(end.get("status") == status and header.get("identity", {}).get("key") == key,
                f"{model} 轨迹终态或身份与发布清单不符：{key}")
        task, tier, seed = key.rsplit("_", 2)
        require(task in TASKS and tier.startswith("xhard"), f"{model} 身份不符：{key}")
        suffix = hashlib.sha256(f"{model}/{episode_dir.name}".encode()).hexdigest()[:32]
        media[f"official_{suffix}"], media[f"original_{suffix}"] = str(official), str(original)
        entries.append({
            "id": f"{model}/{episode_dir.name}", "model": model, "key": key, "attempt": episode_dir.name,
            "task": task, "tier": tier, "seed": int(seed), "episode_id": row["episode_id"], "status": status,
            "task_goal": (demo.get("texts") or [""])[0], "demo_frames": end["demo_frames"],
            "exec_steps": end["exec_steps"], "omitted_timeout_frames": end.get("omitted_timeout_frames", 0),
            "frames": end["frames_recorded"], "official_media": f"official_{suffix}", "original_media": f"original_{suffix}",
        })
    return entries, media


def build_site(root: Path, site_dir: Path) -> dict:
    root = root.resolve(strict=True)
    entries, media, models, rates = [], {}, [], {task: {} for task in TASKS}
    for model, name, publish_rel, bases in MODELS:
        rows, mapping = model_entries(root, model, bases, root / publish_rel)
        require(not set(media) & set(mapping), "媒体 ID 重复")
        entries += rows
        media.update(mapping)
        counts = Counter(row["task"] for row in rows)
        require(set(counts) == set(TASKS), f"{model} 任务覆盖不完整")
        for task in TASKS:
            rates[task][model] = {"success": sum(r["status"] == "success" for r in rows if r["task"] == task),
                                  "total": counts[task]}
        models.append({"id": model, "name": name, "episodes": len(rows),
                       "success": sum(r["status"] == "success" for r in rows)})
    order = [m[0] for m in MODELS]
    entries.sort(key=lambda r: (order.index(r["model"]), TASKS.index(r["task"]), r["tier"], r["seed"]))
    task_counts = Counter(row["task"] for row in entries if row["model"] == order[0])
    catalog = {
        "schema": SCHEMA, "scope": "sg-eval-gl-20261006-03 · 第三阶段 OOD",
        "notice": ("Great Lakes 第三阶段 OOD 正式评估：1800 步 strict、模型 seed 7、43 个任务难度格 × 每格 2 局 = 每模型 86 局；"
                   "每个任务难度格 n=2，成绩只看大致排序。PonderPounce 为补记 S2 输入后的 4 卡重跑（与首跑逐局一致）。"),
        "counts": {"episodes": len(entries), "models": len(models), "per_model": 86, "media": len(media)},
        "models": models, "tasks": [{"id": t, "episodes": task_counts[t]} for t in TASKS],
        "tiers": sorted({row["tier"] for row in entries}), "episodes": entries,
        "success_rates": [{"task": t, **{m: rates[t][m] for m in order}} for t in TASKS],
    }
    site_dir.mkdir(parents=True, exist_ok=True)
    for name, data in (("catalog.json", catalog), ("media-private.json", media)):
        with (site_dir / name).open("x", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=1)
            stream.write("\n")
    return catalog


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run-root", type=Path, help="GL 运行根（含 publish、media、reports）")
    parser.add_argument("--site-dir", type=Path, required=True)
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8084)
    parser.add_argument("--media-root", type=Path)
    args = parser.parse_args()
    try:
        if args.serve:
            sys.path.insert(0, str(HERE))
            from site_server import create_server
            with create_server(args.host, args.port, site_dir=args.site_dir, media_root=args.media_root,
                               html_path=HERE / "stage3_eval_site.html") as server:
                print(f"STAGE3_SITE_READY port={server.server_port} media={len(server.files.media)}", flush=True)
                server.serve_forever()
            return 0
        require(args.run_root is not None, "构建目录需要 --run-root")
        catalog = build_site(args.run_root, args.site_dir)
        c = catalog["counts"]
        print(f"STAGE3_SITE=PASS models={c['models']} episodes={c['episodes']} media={c['media']} "
              + " ".join(f"{m['id']}={m['success']}/{m['episodes']}" for m in catalog["models"]), flush=True)
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f"STAGE3_SITE=FAIL reason={exc}", flush=True)
        return 1
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
