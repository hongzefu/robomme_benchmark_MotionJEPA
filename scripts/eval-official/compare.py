"""v7.5eval 比较与统计工具（纯 CPU，只依赖 numpy 与标准库）。

子命令一览（口径见 0929-v7.5eval-restructure-plan.md §1.2、§3.1、第 0 步、第 6 步与第二部分 §2）：

- ``identities``：写死小样本 48 与全量 192 身份清单、全量队列打乱顺序（shuffle_seed=20260930）。
- ``freeze`` / ``freeze --check``：冻结官方历史成绩（E0）全部输入文件的 sha256 与字节数；复核未变。
- ``assets``：读第 0 步三份权重 sha 清单，生成资产锁，并尽量解析 HF 40 位 revision。
- ``eval-parity``：两份闭环结果逐身份比较（转移矩阵、成功率差 bootstrap CI、精确 McNemar、步数差、首个动作分叉步）。
- ``official-noise`` / ``prod-vs-official`` / ``relative-accept``：官方噪声带、主比较与最终相对标准（§3.1 原样实现）。
- ``action-diff``：开环回放动作逐维差（POLICY_REPLAY / IFACE_OPEN 判定行）。
- ``summarize-speed``：逐局计时字段汇总（EVAL_SPEED / ENV_SPEED 判定行）。

所有判定行形如 ``NAME=PASS|FAIL|INFO k=v ...``，单行；所有 jsonl / json 输出 ``sort_keys=True, ensure_ascii=False``。
计数器一律显式输出零值键（不省略为 0 的计数）。
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import math
import os
import random
import re
import sys
import time
from pathlib import Path
from typing import Any, Iterable

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
ART = REPO_ROOT / "artifacts" / "v7.5eval"
XHARD0_MANIFEST = REPO_ROOT / "scripts" / "configs" / "newtask-v7" / "xhard0_manifest.json"

NFS = Path("/nfs/turbo/coe-chaijy-unreplicated/hongzefu")
E0_ROOT = NFS / "v7-eval"
E0_MANIFEST = E0_ROOT / "eval-official-xhard0-192.jsonl"
E0_MME_GLOB = str(E0_ROOT / "mme-official-full-s*" / "mmevla-official-xhard0" / "ckpt79999" / "seed7" / "episodes.jsonl")
E0_SMVLA_GLOB = str(E0_ROOT / "smvla-official-full" / "episodes-shard*of10.jsonl")
E0_LOG_ROOT = NFS / "v7-logs"
E0_VIDEO_ROOT = REPO_ROOT / "artifacts" / "newtask-v7" / "eval-videos-official"

# 源的简写名：命令行里 --a E0-mme 即指官方历史成绩 MME 全部逐局文件
SOURCE_ALIASES = {
    "E0-mme": E0_MME_GLOB,
    "E0-smvla": E0_SMVLA_GLOB,
}

# 第 0 步资产锁：三份 sha 清单对应的权重根目录（与 preflight/hash_assets.sh 一致）
ASSET_ROOTS = {
    "mme-local": Path("/data/hongzefu/robomme_policy_learning_MotionJEPA/v1-store/models/official-mme-vla/perceptual-framesamp-modul/79999"),
    "mme-gl": NFS / "eval-out" / "mmevla-ckpt" / "perceptual-framesamp-modul" / "79999",
    "smvla": NFS / "SimpleMemVLA" / "checkpoints" / "simplememvla_robomme",
}

SHUFFLE_SEED = 20260930
BOOT_N = 10000
BOOT_SEED = 0
STATUSES = ("success", "fail", "timeout", "error")
FINAL_STATUSES = set(STATUSES)
# v6 对拍容差线，仅作参考刻度（§3.1 开环）
REF_ACTION_MAX = 0.0413
REF_STATE_MAX = 0.0411
REF_IMAGE_MAD = 0.144

# 官方噪声带三对的固定朝向（a→b）：历史→重跑一、历史→重跑二、重跑一→重跑二
NOISE_PAIRS = (("历史", "重跑一", "e0", "o1"), ("历史", "重跑二", "e0", "o2"), ("重跑一", "重跑二", "o1", "o2"))


# ---------------------------------------------------------------------------
# 通用小工具
# ---------------------------------------------------------------------------


def dumps(obj: Any, indent: int | None = None) -> str:
    """统一 json 序列化口径。"""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, indent=indent, default=_json_default)


def _json_default(o: Any) -> Any:
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, Path):
        return str(o)
    raise TypeError(f"无法序列化 {type(o)}")


def write_json(path: Path, obj: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps(obj, indent=1) + "\n", encoding="utf-8")


def sha256_file(path: Path, bufsize: int = 1 << 22) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(bufsize)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def fmt(x: Any, nd: int = 4) -> str:
    """判定行里数字的统一格式；None → n/a。"""
    if x is None:
        return "n/a"
    if isinstance(x, bool):
        return "yes" if x else "no"
    if isinstance(x, (int, np.integer)):
        return str(int(x))
    if isinstance(x, (float, np.floating)):
        x = float(x)
        if math.isinf(x) or math.isnan(x):
            return str(x)
        if x != 0 and abs(x) < 10 ** (-nd):
            return f"{x:.3e}"
        s = f"{x:.{nd}f}".rstrip("0").rstrip(".")
        return "0" if s in ("-0", "") else s
    return str(x)


def verdict(name: str, level: str, fields: dict[str, Any]) -> str:
    parts = [f"{name}={level}"] + [f"{k}={fmt(v) if not isinstance(v, str) else (v if v else 'n/a')}" for k, v in fields.items()]
    return " ".join(parts)


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


# ---------------------------------------------------------------------------
# 身份
# ---------------------------------------------------------------------------


def load_xhard0_rows(path: Path = XHARD0_MANIFEST) -> list[dict]:
    """读 xhard0 清单行（任务按规范顺序、任务内原 episode 升序）。"""
    return json.loads(Path(path).read_text(encoding="utf-8"))["rows"]


def select_small48(rows: list[dict], per_task: int = 3) -> list[dict]:
    """小样本规则：每任务按原 episode 升序取前 per_task 个（⚠ 不按官方历史清单行序）。

    任务顺序沿用输入里任务首次出现的顺序。
    """
    by_task: dict[str, list[dict]] = {}
    for r in rows:
        by_task.setdefault(r["task"], []).append(r)
    out = []
    for task, rs in by_task.items():
        out.extend(sorted(rs, key=lambda r: int(r["episode"] if "episode" in r else r["source_episode"]))[:per_task])
    return out


def build_identities(
    xhard0_rows: list[dict],
    e0_manifest_rows: list[dict],
    mme_files: list[Path],
    smvla_files: list[Path],
) -> tuple[list[dict], list[dict], list[str]]:
    """生成全量 192 与小样本 48 身份，并做全部一致性核对。

    返回 (full, small, problems)；problems 非空即运行阻塞。
    """
    problems: list[str] = []
    e0_man = {(r["task"], int(r["source_episode"])): r for r in e0_manifest_rows}
    if len(e0_man) != len(e0_manifest_rows):
        problems.append("E0 清单内 (task, source_episode) 重复")

    def order_index(files: list[Path], label: str) -> dict[tuple[str, int], tuple[int, int, int]]:
        idx: dict[tuple[str, int], tuple[int, int, int]] = {}
        for f in files:
            for i, r in enumerate(read_jsonl(f)):
                k = (r["task"], int(r["source_episode"]))
                if k in idx:
                    problems.append(f"{label} 身份重复 {k} 于 {f}")
                    continue
                idx[k] = (int(r["shard"]), i, int(r["seed"]))
        return idx

    mme_idx = order_index(mme_files, "E0 MME")
    smvla_idx = order_index(smvla_files, "E0 SMVLA")

    full = []
    for r in xhard0_rows:
        task, ep, seed = r["task"], int(r["episode"]), int(r["seed"])
        k = (task, ep)
        m = e0_man.get(k)
        if m is None:
            problems.append(f"{k} 不在 E0 清单")
            continue
        if int(m["seed"]) != seed:
            problems.append(f"{k} seed 不符：xhard0={seed} E0 清单={m['seed']}")
        shard = int(m["shard"])
        ent = {"task": task, "source_episode": ep, "seed": seed, "builder_episode": (ep - 3) // 4, "e0_shard": shard,
               "e0_mme_order": None, "e0_smvla_order": None}
        if (ep - 3) % 4 != 0 or not 0 <= (ep - 3) // 4 <= 11:
            problems.append(f"{k} 原 episode 不是 3+4i（i∈0..11）")
        for label, idx, field in (("MME", mme_idx, "e0_mme_order"), ("SMVLA", smvla_idx, "e0_smvla_order")):
            got = idx.get(k)
            if got is None:
                problems.append(f"{k} 缺 E0 {label} 记录")
                continue
            if got[0] != shard:
                problems.append(f"{k} E0 {label} 片号 {got[0]} ≠ 清单片号 {shard}")
            if got[2] != seed:
                problems.append(f"{k} E0 {label} seed {got[2]} ≠ {seed}")
            ent[field] = got[1]
        full.append(ent)
    if len(full) != 192:
        problems.append(f"全量身份数 {len(full)} ≠ 192")
    if len(e0_man) != 192:
        problems.append(f"E0 清单身份数 {len(e0_man)} ≠ 192")
    if len({(e['task'], e['seed']) for e in full}) != len(full):
        problems.append("全量 (task, seed) 重复")
    small_keys = {(r["task"], int(r["episode"])) for r in select_small48(xhard0_rows)}
    small = [e for e in full if (e["task"], e["source_episode"]) in small_keys]
    if len(small) != 48:
        problems.append(f"小样本身份数 {len(small)} ≠ 48")
    return full, small, problems


def shuffle_order(full: list[dict], seed: int = SHUFFLE_SEED) -> list[dict]:
    order = list(full)
    random.Random(seed).shuffle(order)
    return order


def cmd_identities(args: argparse.Namespace) -> int:
    out = Path(args.out_dir)
    xrows = load_xhard0_rows(Path(args.xhard0))
    man = read_jsonl(Path(args.e0_manifest))
    mme_files = sorted(Path(p) for p in glob.glob(args.e0_mme))
    smvla_files = sorted(Path(p) for p in glob.glob(args.e0_smvla))
    full, small, problems = build_identities(xrows, man, mme_files, smvla_files)
    if problems:
        for p in problems[:50]:
            print("PROBLEM", p)
        print(verdict("IDENTITY_FREEZE", "FAIL", {"small": len(small), "full": len(full), "problems": len(problems)}))
        return 1
    write_json(out / "identities-full192.json", full)
    write_json(out / "identities-small48.json", small)
    order = shuffle_order(full)
    order_sha = sha256_text(dumps(order))
    write_json(out / "queue-order-full192.json", {
        "shuffle_seed": SHUFFLE_SEED,
        "method": "random.Random(20260930).shuffle(list(identities-full192.json))",
        "source": "identities-full192.json",
        "source_sha256": sha256_file(out / "identities-full192.json"),
        "order_sha256": order_sha,
        "order_sha256_def": "sha256(json.dumps(order, sort_keys=True, ensure_ascii=False))",
        "order": order,
    })
    print(f"WROTE {out/'identities-full192.json'} sha256={sha256_file(out/'identities-full192.json')}")
    print(f"WROTE {out/'identities-small48.json'} sha256={sha256_file(out/'identities-small48.json')}")
    print(f"WROTE {out/'queue-order-full192.json'} sha256={sha256_file(out/'queue-order-full192.json')}")
    print(verdict("IDENTITY_FREEZE", "PASS", {"small": len(small), "full": len(full), "shuffle_sha256": order_sha}))
    return 0


# ---------------------------------------------------------------------------
# E0 冻结
# ---------------------------------------------------------------------------


def e0_file_groups() -> dict[str, list[Path]]:
    """E0 冻结覆盖的文件（按组）。"""
    groups: dict[str, list[Path]] = {}
    groups["manifest"] = [E0_MANIFEST]
    groups["summary"] = [E0_ROOT / "official-mmevla-summary.json", E0_ROOT / "official-simplememvla-summary.json"]
    mme = []
    for d in sorted(glob.glob(str(E0_ROOT / "mme-official-full-s*"))):
        mme += [Path(p) for p in sorted(glob.glob(os.path.join(d, "**"), recursive=True)) if os.path.isfile(p)]
    groups["mme-episodes"] = mme
    groups["smvla-episodes"] = [Path(p) for p in sorted(glob.glob(str(E0_ROOT / "smvla-official-full" / "**"), recursive=True)) if os.path.isfile(p)]
    groups["client-logs"] = sorted(Path(p) for p in glob.glob(str(E0_LOG_ROOT / "eval-mme-official-full-s*.log"))) + [E0_LOG_ROOT / "eval-smvla-official-full.log"]
    groups["videos"] = [Path(p) for p in sorted(glob.glob(str(E0_VIDEO_ROOT / "**"), recursive=True)) if os.path.isfile(p)]
    return groups


def hash_groups(groups: dict[str, list[Path]]) -> list[dict]:
    files = []
    for g, paths in groups.items():
        for p in paths:
            st = os.stat(p)
            files.append({"group": g, "path": str(p), "bytes": st.st_size, "sha256": sha256_file(p)})
    return files


def cmd_freeze(args: argparse.Namespace) -> int:
    out = Path(args.out)
    groups = e0_file_groups()
    missing = [str(p) for ps in groups.values() for p in ps if not p.exists()]
    empty = [g for g, ps in groups.items() if not ps]
    for g in empty:
        print("EMPTY_GROUP", g)
    if empty:
        print(verdict("E0_FREEZE", "FAIL", {"files": 0, "empty_groups": len(empty), "missing": len(missing)}))
        return 1
    if missing:
        for m in missing:
            print("MISSING", m)
        print(verdict("E0_FREEZE", "FAIL", {"files": 0, "missing": len(missing)}))
        return 1
    files = hash_groups(groups)
    if args.check:
        old = json.loads(out.read_text(encoding="utf-8"))
        old_map = {f["path"]: f for f in old["files"]}
        new_map = {f["path"]: f for f in files}
        changed = [p for p in new_map if p in old_map and (old_map[p]["sha256"] != new_map[p]["sha256"] or old_map[p]["bytes"] != new_map[p]["bytes"])]
        added = [p for p in new_map if p not in old_map]
        removed = [p for p in old_map if p not in new_map]
        ref_changed = []
        for ref in old.get("asset_hash_lists", []):
            if not Path(ref["path"]).exists() or sha256_file(Path(ref["path"])) != ref["sha256"]:
                ref_changed.append(ref["path"])
        for tag, lst in (("CHANGED", changed), ("ADDED", added), ("REMOVED", removed), ("REF_CHANGED", ref_changed)):
            for p in lst:
                print(tag, p)
        ok = not (changed or added or removed or ref_changed)
        print(verdict("E0_FREEZE", "PASS" if ok else "FAIL", {"files": len(files), "check": "yes", "changed": len(changed),
                                                             "added": len(added), "removed": len(removed), "ref_changed": len(ref_changed)}))
        return 0 if ok else 1
    if out.exists() and not args.force:
        print(f"REFUSE {out} 已存在；冻结文件不覆盖，确需重冻结请加 --force")
        print(verdict("E0_FREEZE", "FAIL", {"files": len(files), "reason": "exists"}))
        return 1
    refs = [{"path": str(p), "sha256": sha256_file(p), "bytes": p.stat().st_size} for p in sorted((ART / "preflight").glob("sha-*.txt"))]
    counts = {g: len(ps) for g, ps in groups.items()}
    write_json(out, {
        "schema": "v75-input-manifest/1",
        "created_unix": time.time(),
        "e0_root": str(E0_ROOT),
        "group_counts": counts,
        "total_bytes": sum(f["bytes"] for f in files),
        "files": files,
        "asset_hash_lists": refs,
    })
    print(f"WROTE {out} sha256={sha256_file(out)} groups={','.join(f'{g}:{n}' for g, n in counts.items())}")
    print(verdict("E0_FREEZE", "PASS", {"files": len(files)}))
    return 0


# ---------------------------------------------------------------------------
# 资产锁
# ---------------------------------------------------------------------------


def parse_sha_list(path: Path) -> dict[str, str]:
    """sha256sum 输出 → {相对路径: sha}。"""
    out = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        sha, rel = line.split(None, 1)
        out[rel.lstrip("*")] = sha
    return out


_HEX40 = re.compile(r"^[0-9a-f]{40}$")


def find_hf_revision(root: Path) -> tuple[str, str | None]:
    """在权重目录或其上一级的 .cache/huggingface/download/*.metadata 里找 40 位 commit。

    HF 的 metadata 文件第一行即 commit hash；找到多个不同值时视为未解析。
    返回 (revision 或 "未解析", 来源说明)。
    """
    found: dict[str, str] = {}
    for base in (root, root.parent):
        for m in sorted(glob.glob(str(base / ".cache" / "huggingface" / "download" / "*.metadata"))):
            try:
                first = Path(m).read_text(encoding="utf-8").splitlines()[0].strip()
            except (OSError, IndexError, UnicodeDecodeError):
                continue
            if _HEX40.match(first):
                found.setdefault(first, m)
        if found:
            break
    if len(found) == 1:
        rev, src = next(iter(found.items()))
        return rev, src
    return "未解析", (f"多个 revision：{sorted(found)}" if found else None)


def cmd_assets(args: argparse.Namespace) -> int:
    pre = Path(args.preflight)
    lists = {n: parse_sha_list(pre / f"sha-{n}.txt") for n in ASSET_ROOTS}
    a, b = lists["mme-local"], lists["mme-gl"]
    mismatches = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
    assets = {}
    for name, files in lists.items():
        rev, src = find_hf_revision(ASSET_ROOTS[name])
        assets[name] = {"root": str(ASSET_ROOTS[name]), "sha_list": str(pre / f"sha-{name}.txt"),
                        "sha_list_sha256": sha256_file(pre / f"sha-{name}.txt"), "files": files,
                        "n_files": len(files), "hf_revision": rev, "hf_revision_source": src}
    note = None
    if assets["mme-gl"]["hf_revision"] == "未解析" and not mismatches and assets["mme-local"]["hf_revision"] != "未解析":
        note = "mme-gl 无 HF 缓存元数据；与 mme-local 逐文件 sha256 相同，故同一 revision 以本地 sha256 为锁"
    n = sum(v["n_files"] for v in assets.values())
    write_json(Path(args.out), {"schema": "v75-assets-lock/1", "assets": assets, "mme_local_vs_gl_mismatches": mismatches, "note": note})
    for mm in mismatches:
        print("MISMATCH", mm, a.get(mm), b.get(mm))
    print(" ".join(f"REVISION {k}={v['hf_revision']}" for k, v in assets.items()))
    print(verdict("ASSETS", "PASS" if not mismatches else "FAIL", {"assets": n, "mismatches": len(mismatches)}))
    return 0 if not mismatches else 1


# ---------------------------------------------------------------------------
# 结果加载器
# ---------------------------------------------------------------------------


def expand_source(src: str) -> list[Path]:
    """源说明 → 结果文件列表。接受简写名、单个文件、目录（递归找结果文件）或 glob。"""
    src = SOURCE_ALIASES.get(src, src)
    paths: list[Path] = []
    for p in sorted(glob.glob(src, recursive=True)) or ([src] if os.path.exists(src) else []):
        pp = Path(p)
        if pp.is_dir():
            for pat in ("episodes.jsonl", "episodes-shard*.jsonl", "results.jsonl", "results-*.jsonl"):
                paths += sorted(Path(x) for x in glob.glob(str(pp / "**" / pat), recursive=True))
        elif pp.is_file():
            paths.append(pp)
    seen, uniq = set(), []
    for p in paths:
        if p.resolve() not in seen:
            seen.add(p.resolve())
            uniq.append(p)
    if not uniq:
        raise FileNotFoundError(f"源 {src} 找不到结果文件")
    return uniq


def detect_format(rec: dict) -> str:
    if "identity" in rec or "cond" in rec or "policy" in rec and isinstance(rec.get("policy"), str) and "timing" in rec:
        return "new"
    if "checkpoint" in rec or "elapsed_s" in rec:
        return "smvla"
    if "attempt" in rec:
        return "mme"
    return "new"


def normalize_record(rec: dict, src_file: str, line_no: int) -> dict:
    """任一格式 → 统一记录。"""
    seed = rec.get("seed")
    if seed is None and isinstance(rec.get("identity"), dict):
        seed = rec["identity"].get("seed")
    se = rec.get("source_episode")
    if se is None and isinstance(rec.get("identity"), dict):
        se = rec["identity"].get("source_episode")
    status = rec.get("status")
    if status is None and "task_success" in rec:
        status = "success" if rec["task_success"] else "fail"
    timing = dict(rec.get("timing") or {})
    if "elapsed_s" in rec and "elapsed_s" not in timing:
        timing["elapsed_s"] = rec["elapsed_s"]
    return {
        "task": rec["task"], "seed": int(seed), "source_episode": None if se is None else int(se),
        "status": status, "steps": rec.get("steps"), "error": rec.get("error"),
        "attempt": rec.get("attempt"), "format": detect_format(rec), "rec_dir": rec.get("rec_dir"),
        "seat": rec.get("seat"), "host": rec.get("host"), "timing": timing,
        "src": f"{src_file}:{line_no}",
    }


def load_results(src: str | list[str]) -> tuple[dict[tuple[str, int], dict], dict]:
    """加载并去重：同一 (task, seed) 取文件内与文件间顺序上最后一条带终态的记录（续评 / 重试取最新）。

    返回 (记录表, 加载统计)。
    """
    srcs = [src] if isinstance(src, str) else list(src)
    files: list[Path] = []
    for s in srcs:
        files += expand_source(s)
    table: dict[tuple[str, int], dict] = {}
    stats = {"files": len(files), "lines": 0, "non_final": 0, "superseded": 0}
    for f in files:
        for i, rec in enumerate(read_jsonl(f)):
            stats["lines"] += 1
            n = normalize_record(rec, str(f), i)
            if n["status"] not in FINAL_STATUSES:
                stats["non_final"] += 1
                continue
            k = (n["task"], n["seed"])
            if k in table:
                stats["superseded"] += 1
            table[k] = n
    stats["records"] = len(table)
    return table, stats


def load_identity_keys(path: str | None) -> list[tuple[str, int]] | None:
    if not path:
        return None
    return [(e["task"], int(e["seed"])) for e in json.loads(Path(path).read_text(encoding="utf-8"))]


# ---------------------------------------------------------------------------
# 统计
# ---------------------------------------------------------------------------


def mcnemar_exact(b: int, c: int) -> float:
    """精确（二项）McNemar 双侧 p 值：2·P(X ≤ min(b,c))，X~Bin(b+c, 1/2)，上限 1。"""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2 ** n)
    return min(1.0, 2.0 * tail)


def paired_bootstrap_ci(sa: np.ndarray, sb: np.ndarray, n_boot: int = BOOT_N, seed: int = BOOT_SEED) -> tuple[float, float]:
    """按身份配对重采样的成功率差（b−a，百分点）95% 百分位置信区间。"""
    d = (np.asarray(sb, dtype=np.float64) - np.asarray(sa, dtype=np.float64))
    n = len(d)
    if n == 0:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n, size=(n_boot, n))
    means = d[idx].mean(axis=1) * 100.0
    lo, hi = np.percentile(means, [2.5, 97.5])
    return (float(lo), float(hi))


def compare_tables(a: dict, b: dict, keys: list[tuple[str, int]] | None = None) -> dict:
    """两份结果逐身份比较，a 为参照、b 为被比方（翻转方向 a→b，成功率差 = b − a）。"""
    if keys is None:
        keys = sorted(set(a) | set(b))
    missing_a = [k for k in keys if k not in a]
    missing_b = [k for k in keys if k not in b]
    common = [k for k in keys if k in a and k in b]
    matrix = {sa: {sb: 0 for sb in STATUSES} for sa in STATUSES}
    rows = []
    s2f = f2s = 0
    new_err = new_timeout = lost_err = lost_timeout = 0
    steps_d = []
    steps_equal = 0
    for k in common:
        ra, rb = a[k], b[k]
        matrix[ra["status"]][rb["status"]] += 1
        a_s, b_s = ra["status"] == "success", rb["status"] == "success"
        flip = None
        if a_s and not b_s:
            s2f += 1
            flip = "s2f"
        elif b_s and not a_s:
            f2s += 1
            flip = "f2s"
        new_err += rb["status"] == "error" and ra["status"] != "error"
        lost_err += ra["status"] == "error" and rb["status"] != "error"
        new_timeout += rb["status"] == "timeout" and ra["status"] != "timeout"
        lost_timeout += ra["status"] == "timeout" and rb["status"] != "timeout"
        sd = None
        if ra["status"] in ("success", "fail") and rb["status"] in ("success", "fail") and ra["steps"] is not None and rb["steps"] is not None:
            sd = int(rb["steps"]) - int(ra["steps"])
            steps_d.append(sd)
            steps_equal += sd == 0
        rows.append({"task": k[0], "seed": k[1], "source_episode": ra["source_episode"] if ra["source_episode"] is not None else rb["source_episode"],
                     "status_a": ra["status"], "status_b": rb["status"], "steps_a": ra["steps"], "steps_b": rb["steps"],
                     "steps_diff": sd, "flip": flip, "src_a": ra["src"], "src_b": rb["src"]})
    sa = np.array([a[k]["status"] == "success" for k in common], dtype=np.float64)
    sb = np.array([b[k]["status"] == "success" for k in common], dtype=np.float64)
    n = len(common)
    sr_a = float(sa.mean() * 100) if n else float("nan")
    sr_b = float(sb.mean() * 100) if n else float("nan")
    ci = paired_bootstrap_ci(sa, sb) if n else (float("nan"), float("nan"))
    sdn = np.array(steps_d, dtype=np.float64)
    return {
        "compared": n, "missing_a": len(missing_a), "missing_b": len(missing_b),
        "missing_a_keys": [list(k) for k in missing_a], "missing_b_keys": [list(k) for k in missing_b],
        "success_a": int(sa.sum()), "success_b": int(sb.sum()), "sr_a_pct": sr_a, "sr_b_pct": sr_b,
        "s2f": int(s2f), "f2s": int(f2s),
        "new_err": int(new_err), "lost_err": int(lost_err), "new_timeout": int(new_timeout), "lost_timeout": int(lost_timeout),
        "status_matrix": matrix,
        "sr_diff_pp": sr_b - sr_a if n else float("nan"),
        "ci95_pp": list(ci), "ci_half_width_pp": (ci[1] - ci[0]) / 2 if n else float("nan"),
        "bootstrap": {"n": BOOT_N, "seed": BOOT_SEED, "unit": "identity", "rng": "numpy.default_rng"},
        "mcnemar_p": mcnemar_exact(s2f, f2s),
        "granularity_pp_per_episode": (100.0 / n) if n else None,
        "steps_compared": len(steps_d), "steps_equal": int(steps_equal),
        "steps_diff_p50": float(np.median(sdn)) if len(sdn) else None,
        "steps_diff_abs_p95": float(np.percentile(np.abs(sdn), 95)) if len(sdn) else None,
        "steps_def": "仅 a、b 都是环境终态 success/fail 的身份；diff = steps_b − steps_a；p50 为有符号中位数，p95 为 |diff| 的 P95",
        "flips": [r for r in rows if r["flip"]],
        "rows": rows,
    }


# ---------------------------------------------------------------------------
# 录制数组读取与动作差
# ---------------------------------------------------------------------------


def load_array(path: str | Path, name: str) -> tuple[np.ndarray, np.ndarray | None]:
    """从录制器目录或 npz 读 name 数组与可选步号 <name>.step。

    容忍：目录下 arrays.npz、arrays/<name>.npy（+<name>.step.npy）、直接 npz；
    若无整键，则收集 ``<name>/<i>``、``<name>__<i>``、``<name>.<i>`` 形式的逐步键按 i 排序堆叠。
    """
    p = Path(path)
    store: dict[str, np.ndarray] = {}
    if p.is_file() and p.suffix == ".npz":
        with np.load(p, allow_pickle=False) as z:
            store = {k: z[k] for k in z.files}
    elif p.is_dir():
        if (p / "arrays.npz").exists():
            with np.load(p / "arrays.npz", allow_pickle=False) as z:
                store = {k: z[k] for k in z.files}
        adir = p / "arrays" if (p / "arrays").is_dir() else None
        if adir is not None:
            for f in adir.glob("*.npy"):
                store[f.name[:-4]] = np.load(f, allow_pickle=False)
    elif p.is_file() and p.suffix == ".npy":
        return np.load(p, allow_pickle=False), None
    else:
        raise FileNotFoundError(f"{p} 不是录制目录或 npz")
    step = None
    for sk in (f"{name}.step", f"{name}_step", f"{name}.steps"):
        if sk in store:
            step = np.asarray(store[sk])
            break
    if name in store:
        return np.asarray(store[name]), step
    pat = re.compile(rf"^{re.escape(name)}(?:/|__|\.)(\d+)$")
    parts = sorted(((int(m.group(1)), k) for k in store if (m := pat.match(k))), key=lambda t: t[0])
    if not parts:
        raise KeyError(f"{p} 中没有数组 {name}（有：{sorted(store)[:20]}）")
    arrs = [np.asarray(store[k]) for _, k in parts]
    return np.stack(arrs), (step if step is not None else np.array([i for i, _ in parts]))


def action_diff(a: np.ndarray, b: np.ndarray) -> dict:
    """逐维动作差。数组首轴为步（或决策），末轴为动作维；中间轴（如动作块 H）并入样本。

    最大相对差 = 该维最大绝对差 ÷ a 侧该维在本局内的取值范围（范围为 0 时：有差记 inf，无差记 0）。
    注意：取值范围用 a 侧全部步（含 a 比 b 长出的部分），而差只在两侧共同长度内计算。
    """
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    if a.ndim == 1:
        a, b = a[:, None], b[:, None]
    len_a, len_b = a.shape[0], b.shape[0]
    n = min(len_a, len_b)
    shape_equal = a.shape == b.shape
    if a.shape[1:] != b.shape[1:]:
        return {"shape_a": list(a.shape), "shape_b": list(b.shape), "shape_equal": False, "comparable": False,
                "first_diff_step": 0, "neq": None}
    aa, bb = a[:n], b[:n]
    d = np.abs(aa - bb)
    D = a.shape[-1]
    d2 = d.reshape(-1, D)
    a2 = a.reshape(-1, D)
    neq_mask = aa != bb
    per_step_neq = neq_mask.reshape(n, -1).any(axis=1)
    first = int(np.argmax(per_step_neq)) if per_step_neq.any() else (n if len_a != len_b else None)
    rng = (a2.max(axis=0) - a2.min(axis=0)) if a2.size else np.zeros(D)
    dmax = d2.max(axis=0) if d2.size else np.zeros(D)
    with np.errstate(divide="ignore", invalid="ignore"):
        rel = np.where(rng > 0, dmax / np.where(rng > 0, rng, 1), np.where(dmax > 0, np.inf, 0.0))
    return {
        "shape_a": list(a.shape), "shape_b": list(b.shape), "shape_equal": bool(shape_equal), "comparable": True,
        "steps_compared": int(n),
        "dim_mean_abs": (d2.mean(axis=0) if d2.size else np.zeros(D)).tolist(),
        "dim_p95": (np.percentile(d2, 95, axis=0) if d2.size else np.zeros(D)).tolist(),
        "dim_max_abs": dmax.tolist(),
        "dim_max_rel": rel.tolist(),
        "max_abs": float(dmax.max()) if D else 0.0,
        "max_rel": float(rel.max()) if D else 0.0,
        "neq": int(neq_mask.sum()), "elements": int(neq_mask.size),
        "first_diff_step": first,
    }


def ref_line_for(name: str, arr: np.ndarray) -> tuple[str, float]:
    if "state" in name:
        return "state_max", REF_STATE_MAX
    if arr.dtype == np.uint8 or any(t in name for t in ("image", "rgb", "front", "wrist")):
        return "image_mad", REF_IMAGE_MAD
    return "action_max", REF_ACTION_MAX


def _vec(xs: Iterable[float]) -> str:
    return ",".join(fmt(float(x)) for x in xs)


def cmd_action_diff(args: argparse.Namespace) -> int:
    a, _ = load_array(args.a, args.name)
    b, _ = load_array(args.b, args.name)
    res = action_diff(a, b)
    ref_name, ref_val = ref_line_for(args.name, a)
    if res["comparable"]:
        metric = res["max_abs"]
        if ref_name == "image_mad":
            metric = float(np.mean(res["dim_mean_abs"])) / (255.0 if a.dtype == np.uint8 else 1.0)
        res["ref"] = {"name": ref_name, "value": ref_val, "metric": metric, "side": "above" if metric > ref_val else "below"}
    payload_equal = "n/a"
    if args.payload_name:
        try:
            pa, _ = load_array(args.a, args.payload_name)
            pb, _ = load_array(args.b, args.payload_name)
            payload_equal = "yes" if (pa.shape == pb.shape and np.array_equal(pa, pb)) else "no"
        except (KeyError, FileNotFoundError) as e:
            payload_equal = f"缺失:{type(e).__name__}"
    res["payload_equal"] = payload_equal
    res.update({"a": str(args.a), "b": str(args.b), "name": args.name, "kind": args.kind, "cond": args.cond, "policy": args.policy, "mode": args.mode})
    if args.out:
        write_json(Path(args.out), res)
    det = "yes" if res.get("neq") == 0 and res.get("shape_equal") else "no"
    side = res.get("ref", {}).get("side", "n/a")
    if args.kind == "iface":
        exec_equal = det if args.name == "exec_action" else "n/a"
        print(verdict("IFACE_OPEN", "INFO", {"policy": args.policy or "n/a", "name": args.name, "payload_equal": payload_equal,
                                            "action_diff": res.get("max_abs"), "exec_equal": exec_equal, "neq": res.get("neq"),
                                            "first_diff_step": res.get("first_diff_step"), f"vs_{ref_name}": side}))
    else:
        print(verdict("POLICY_REPLAY", "INFO", {"cond": args.cond or "n/a", "policy": args.policy or "n/a", "det": det, "mode": args.mode or "n/a",
                                               "name": args.name,
                                               "dim_mean_abs": _vec(res.get("dim_mean_abs", [])), "dim_p95": _vec(res.get("dim_p95", [])),
                                               "dim_max_abs": _vec(res.get("dim_max_abs", [])), "max_rel": res.get("max_rel"),
                                               "neq": res.get("neq"), "first_diff_step": res.get("first_diff_step"), f"vs_{ref_name}": side}))
    return 0


# ---------------------------------------------------------------------------
# 首个动作分叉步（闭环比较的可选项）
# ---------------------------------------------------------------------------


def index_rec_dirs(root: str | None) -> dict[tuple[str, int], Path]:
    """扫描录制根目录下各局 meta.json，按 (task, seed) 建索引。"""
    out: dict[tuple[str, int], Path] = {}
    if not root:
        return out
    for m in glob.glob(os.path.join(root, "**", "meta.json"), recursive=True):
        try:
            meta = json.loads(Path(m).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        seed = meta.get("seed", (meta.get("identity") or {}).get("seed"))
        task = meta.get("task", (meta.get("identity") or {}).get("task"))
        if task is not None and seed is not None:
            out[(task, int(seed))] = Path(m).parent
    return out


def first_divergence(rows: list[dict], a: dict, b: dict, rec_a: str | None, rec_b: str | None, name: str = "exec_action") -> dict | None:
    """逐身份首个动作分叉点。first_div 单位：有 <name>.step 时为环境步号（env_step），否则为数组首轴下标（array_index）。"""
    if not rec_a or not rec_b:
        return None
    ia, ib = index_rec_dirs(rec_a), index_rec_dirs(rec_b)
    per, missing = [], 0
    units: set[str] = set()
    for r in rows:
        k = (r["task"], r["seed"])
        da = Path(a[k]["rec_dir"]) if a[k].get("rec_dir") else ia.get(k)
        db = Path(b[k]["rec_dir"]) if b[k].get("rec_dir") else ib.get(k)
        if da is None or db is None:
            missing += 1
            r["first_div"] = None
            continue
        try:
            xa, step_a = load_array(da, name)
            xb, step_b = load_array(db, name)
        except (KeyError, FileNotFoundError):
            missing += 1
            r["first_div"] = None
            continue
        res = action_diff(xa, xb)
        fd = res["first_diff_step"]
        r["first_div_index"] = fd
        r["first_div"] = to_env_step(fd, step_a, step_b)
        r["first_div_unit"] = "env_step" if (step_a is not None or step_b is not None) else "array_index"
        units.add(r["first_div_unit"])
        per.append(r["first_div"])
    div = [x for x in per if x is not None]
    return {"name": name, "episodes": len(per), "missing": missing, "diverged": len(div),
            "unit": ",".join(sorted(units)) or "n/a",
            "min": min(div) if div else None, "p50": float(np.median(div)) if div else None}


def to_env_step(idx: int | None, step_a: np.ndarray | None, step_b: np.ndarray | None) -> int | None:
    """把数组首轴下标换成环境步号。

    有 ``<name>.step`` 数组时（录制器 add_array(step=...) 写入的环境步号），返回该下标处 a 侧的步号；
    下标越过 a 侧长度（a 更短）时用 b 侧；都没有步号数组时原样返回数组下标（单位记 array_index）。
    """
    if idx is None:
        return None
    for st in (step_a, step_b):
        if st is not None and 0 <= idx < len(st):
            return int(np.asarray(st).reshape(-1)[idx])
    return int(idx)


# ---------------------------------------------------------------------------
# 闭环比较命令
# ---------------------------------------------------------------------------


def _ci_str(ci: list[float]) -> str:
    return f"[{fmt(ci[0], 3)},{fmt(ci[1], 3)}]"


def _div_str(fd: dict | None) -> str:
    if fd is None:
        return "n/a"
    return f"diverged:{fd['diverged']}/{fd['episodes']},min:{fmt(fd['min'])},p50:{fmt(fd['p50'])},missing:{fd['missing']},unit:{fd['unit']}"


def run_pair(a_src: str, b_src: str, keys: list | None, rec_a: str | None = None, rec_b: str | None = None) -> dict:
    a, sa = load_results(a_src)
    b, sb = load_results(b_src)
    res = compare_tables(a, b, keys)
    res["load_a"], res["load_b"] = sa, sb
    res["src_a"], res["src_b"] = a_src, b_src
    res["first_div"] = first_divergence(res["rows"], a, b, rec_a, rec_b)
    return res


def cmd_eval_parity(args: argparse.Namespace) -> int:
    keys = load_identity_keys(args.identities)
    res = run_pair(args.a, args.b, keys, args.rec_a, args.rec_b)
    res.update({"pair": args.pair, "policy": args.policy, "identities": args.identities})
    if args.out:
        write_json(Path(args.out), res)
    m = res["status_matrix"]
    mat = ";".join(f"{x[0]}>{''.join(str(m[x][y]) + y[0] for y in STATUSES)}" for x in STATUSES)
    print(verdict("EVAL_PARITY", "INFO", {
        "pair": args.pair, "policy": args.policy, "compared": res["compared"], "missing_a": res["missing_a"], "missing_b": res["missing_b"],
        "s2f": res["s2f"], "f2s": res["f2s"], "new_err": res["new_err"], "lost_err": res["lost_err"],
        "new_timeout": res["new_timeout"], "lost_timeout": res["lost_timeout"],
        "sr_a": res["sr_a_pct"], "sr_b": res["sr_b_pct"], "sr_diff_pp": res["sr_diff_pp"], "ci": _ci_str(res["ci95_pp"]),
        "mcnemar_p": res["mcnemar_p"], "steps_equal": f"{res['steps_equal']}/{res['steps_compared']}",
        "steps_diff_p50": res["steps_diff_p50"], "steps_diff_p95": res["steps_diff_abs_p95"],
        "first_div": _div_str(res["first_div"]), "pp_per_ep": res["granularity_pp_per_episode"], "matrix": mat,
    }))
    return 0


def _pair_line(name: str, key: str, label: str, policy: str, r: dict) -> str:
    return verdict(name, "INFO", {key: label, "policy": policy, "compared": r["compared"], "missing_a": r["missing_a"],
                                  "missing_b": r["missing_b"], "s2f": r["s2f"], "f2s": r["f2s"],
                                  "new_err": r["new_err"], "new_timeout": r["new_timeout"], "sr_diff_pp": r["sr_diff_pp"],
                                  "ci": _ci_str(r["ci95_pp"]), "mcnemar_p": r["mcnemar_p"]})


def official_noise(e0: str, o1: str, o2: str, keys: list | None) -> list[tuple[str, dict]]:
    srcs = {"e0": e0, "o1": o1, "o2": o2}
    out = []
    for la, lb, ka, kb in NOISE_PAIRS:
        out.append((f"{la}:{lb}", run_pair(srcs[ka], srcs[kb], keys)))
    return out


def cmd_official_noise(args: argparse.Namespace) -> int:
    keys = load_identity_keys(args.identities)
    pairs = official_noise(args.e0, args.o1, args.o2, keys)
    if args.out:
        write_json(Path(args.out), {"policy": args.policy, "pairs": {k: v for k, v in pairs}})
    for label, r in pairs:
        print(_pair_line("OFFICIAL_NOISE", "pair", label, args.policy, r))
    probs = coverage_problems(pairs)
    for pr in probs:
        print("BLOCKING", pr)
    return 2 if probs else 0


def cmd_prod_vs_official(args: argparse.Namespace) -> int:
    keys = load_identity_keys(args.identities)
    out = {}
    for spec in args.ref:
        name, _, src = spec.partition("=")
        r = run_pair(src, args.prod, keys)
        out[name] = r
        print(_pair_line("PROD_VS_OFFICIAL", "ref", name, args.policy, r))
    if args.out:
        write_json(Path(args.out), {"policy": args.policy, "orientation": "a=官方参照 b=正式跑法", "refs": out})
    probs = coverage_problems(list(out.items()))
    for pr in probs:
        print("BLOCKING", pr)
    return 2 if probs else 0


def relative_accept(noise: list[tuple[str, dict]], main: dict) -> dict:
    """§3.1 最终相对标准（跑前写死，原样实现）。

    inside=yes 当且仅当：主比较 s2f ≤ 官方 3 对 s2f 的最大值，且 f2s ≤ 官方 3 对 f2s 的最大值，
    且主比较成功率差点估计 ∈ [官方 3 对成功率差最小值, 最大值]。
    朝向：官方对为 历史→重跑一、历史→重跑二、重跑一→重跑二；主比较为 重跑一→正式跑法；差 = b − a。
    ⚠ 成功率差区间检验依赖上述固定朝向（a=参照、b=被比方）：朝向反过来差值变号，结论可能不同。
    官方 3 对全部 0 翻转时：inside=None（输出 n/a），note=官方重跑无翻转，逐局列出正式跑法翻转（不套退化区间、不放宽）。
    运行阻塞：任一比较 missing_a/missing_b > 0，或 4 个比较的 compared 不一致 → inside=None、blocked=True。
    追加样本触发：主比较 CI 半宽 > 2 × 官方 3 对最大 CI 半宽。
    """
    blocking = coverage_problems(noise + [("主比较", main)])
    if blocking:
        return {"inside": None, "blocked": True, "blocking": blocking,
                "coverage": {k: {"compared": r["compared"], "missing_a": r["missing_a"], "missing_b": r["missing_b"]} for k, r in noise + [("主比较", main)]},
                "note": "身份覆盖不全，运行阻塞", "extra_sample_trigger": None, "official_all_zero_flips": None, "prod_flips": None,
                "main_s2f": main["s2f"], "main_f2s": main["f2s"], "main_sr_diff_pp": main["sr_diff_pp"], "main_ci95_pp": main["ci95_pp"]}
    max_s2f = max(r["s2f"] for _, r in noise)
    max_f2s = max(r["f2s"] for _, r in noise)
    srs = [r["sr_diff_pp"] for _, r in noise]
    lo, hi = min(srs), max(srs)
    eps = 1e-9
    cond_s2f = main["s2f"] <= max_s2f
    cond_f2s = main["f2s"] <= max_f2s
    cond_sr = lo - eps <= main["sr_diff_pp"] <= hi + eps
    all_zero = all(r["s2f"] == 0 and r["f2s"] == 0 for _, r in noise)
    max_hw = max(r["ci_half_width_pp"] for _, r in noise)
    trigger = main["ci_half_width_pp"] > 2 * max_hw
    return {
        "blocked": False, "blocking": [],
        # 官方 3 对全 0 翻转时区间退化，按 §3.1「不套区间、不放宽」不给 yes/no
        "inside": None if all_zero else bool(cond_s2f and cond_f2s and cond_sr),
        "cond_s2f": cond_s2f, "cond_f2s": cond_f2s, "cond_sr": cond_sr,
        "main_s2f": main["s2f"], "main_f2s": main["f2s"], "main_sr_diff_pp": main["sr_diff_pp"], "main_ci95_pp": main["ci95_pp"],
        "main_ci_half_width_pp": main["ci_half_width_pp"],
        "official_max_s2f": max_s2f, "official_max_f2s": max_f2s, "official_sr_min": lo, "official_sr_max": hi,
        "official_pairs": {k: {"s2f": r["s2f"], "f2s": r["f2s"], "sr_diff_pp": r["sr_diff_pp"], "ci95_pp": r["ci95_pp"],
                               "ci_half_width_pp": r["ci_half_width_pp"], "compared": r["compared"]} for k, r in noise},
        "official_max_ci_half_width_pp": max_hw,
        "extra_sample_trigger": bool(trigger),
        "official_all_zero_flips": all_zero,
        "note": "官方重跑无翻转" if all_zero else None,
        "prod_flips": main["flips"] if all_zero else None,
        "orientation": "官方对 历史→重跑一/历史→重跑二/重跑一→重跑二；主比较 重跑一→正式跑法；差=b−a",
    }


def coverage_problems(pairs: list[tuple[str, dict]]) -> list[str]:
    """身份覆盖核对（§3.1 运行阻塞：队列重复或遗漏）：任一比较有缺失、或各比较 compared 不一致即列出问题。"""
    probs = [f"{k}:missing_a={r['missing_a']},missing_b={r['missing_b']}" for k, r in pairs if r["missing_a"] or r["missing_b"]]
    comp = {r["compared"] for _, r in pairs}
    if len(comp) > 1:
        probs.append("compared 不一致:" + ",".join(f"{k}={r['compared']}" for k, r in pairs))
    return probs


def _coverage_str(pairs: list[tuple[str, dict]]) -> str:
    return ";".join(f"{k}:{r['compared']}/{r['missing_a']}/{r['missing_b']}" for k, r in pairs)


def cmd_relative_accept(args: argparse.Namespace) -> int:
    keys = load_identity_keys(args.identities)
    noise = official_noise(args.e0, args.o1, args.o2, keys)
    main = run_pair(args.o1, args.prod, keys)
    ra = relative_accept(noise, main)
    ra["policy"] = args.policy
    if args.out:
        write_json(Path(args.out), {"relative_accept": ra, "main": main, "noise": {k: v for k, v in noise}})
    for label, r in noise:
        print(_pair_line("OFFICIAL_NOISE", "pair", label, args.policy, r))
    print(_pair_line("PROD_VS_OFFICIAL", "ref", "重跑一", args.policy, main))
    if ra["blocked"]:
        print(verdict("RELATIVE_ACCEPT", "INFO", {"policy": args.policy, "inside": "n/a", "blocked": "yes",
                                                  "coverage(compared/missing_a/missing_b)": _coverage_str(noise + [("主比较", main)]),
                                                  "note": "身份覆盖不全，运行阻塞"}))
        return 2
    fields = {"policy": args.policy, "inside": "n/a" if ra["inside"] is None else ra["inside"], "s2f": ra["main_s2f"], "f2s": ra["main_f2s"],
              "max_off_s2f": ra["official_max_s2f"], "max_off_f2s": ra["official_max_f2s"],
              "sr_diff_pp": ra["main_sr_diff_pp"], "off_sr_range": f"[{fmt(ra['official_sr_min'])},{fmt(ra['official_sr_max'])}]",
              "ci": _ci_str(ra["main_ci95_pp"]),
              "off_ci": ";".join(f"{k}{_ci_str(v['ci95_pp'])}" for k, v in ra["official_pairs"].items()),
              "extra_sample_trigger": ra["extra_sample_trigger"]}
    if ra["note"]:
        fields["note"] = ra["note"]
        fields["prod_flips"] = ";".join(f"{f['task']}/{f['seed']}:{f['status_a']}>{f['status_b']}" for f in ra["prod_flips"]) or "none"
    print(verdict("RELATIVE_ACCEPT", "INFO", fields))
    return 0


# ---------------------------------------------------------------------------
# 测速汇总
# ---------------------------------------------------------------------------


def _flatten(d: dict, prefix: str = "") -> dict[str, float]:
    out = {}
    for k, v in d.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(_flatten(v, key + "."))
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            out[key] = float(v)
    return out


def summarize_speed(records: list[dict], group_by: str) -> dict[str, dict]:
    """按 group_by 字段分组，对 timing（嵌套展开）与顶层 elapsed_s 等数值字段给 n、中位数、P95。"""
    groups: dict[str, dict[str, list[float]]] = {}
    for r in records:
        g = str(r.get(group_by) if r.get(group_by) is not None else "all")
        vals = _flatten(r.get("timing") or {})
        for k in ("elapsed_s",):
            if isinstance(r.get(k), (int, float)) and k not in vals:
                vals[k] = float(r[k])
        acc = groups.setdefault(g, {})
        for k, v in vals.items():
            acc.setdefault(k, []).append(v)
    out = {}
    for g, acc in groups.items():
        out[g] = {k: {"n": len(v), "p50": float(np.median(v)), "p95": float(np.percentile(v, 95))} for k, v in sorted(acc.items())}
    return out


def cmd_summarize_speed(args: argparse.Namespace) -> int:
    recs = []
    for s in args.src:
        for f in expand_source(s):
            recs += read_jsonl(f)
    summ = summarize_speed(recs, args.group_by)
    if args.out:
        write_json(Path(args.out), summ)
    name = "EVAL_SPEED" if args.kind == "eval" else "ENV_SPEED"
    for g, fields in summ.items():
        kv = {args.group_by: g, "rows": max((v["n"] for v in fields.values()), default=0)}
        for k, v in fields.items():
            kv[f"{k}_p50"] = v["p50"]
            kv[f"{k}_p95"] = v["p95"]
        print(verdict(name, "INFO", kv))
    return 0


# ---------------------------------------------------------------------------
# 命令行
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("identities", help="写死身份清单与队列打乱顺序")
    p.add_argument("--out-dir", default=str(ART))
    p.add_argument("--xhard0", default=str(XHARD0_MANIFEST))
    p.add_argument("--e0-manifest", default=str(E0_MANIFEST))
    p.add_argument("--e0-mme", default=E0_MME_GLOB)
    p.add_argument("--e0-smvla", default=E0_SMVLA_GLOB)
    p.set_defaults(func=cmd_identities)

    p = sub.add_parser("freeze", help="冻结 E0 输入文件 sha256；--check 复核")
    p.add_argument("--out", default=str(ART / "input-manifest.json"))
    p.add_argument("--check", action="store_true")
    p.add_argument("--force", action="store_true", help="允许覆盖已存在的 input-manifest.json")
    p.set_defaults(func=cmd_freeze)

    p = sub.add_parser("assets", help="资产锁")
    p.add_argument("--preflight", default=str(ART / "preflight"))
    p.add_argument("--out", default=str(ART / "assets-lock.json"))
    p.set_defaults(func=cmd_assets)

    p = sub.add_parser("eval-parity", help="两份闭环结果逐身份比较")
    p.add_argument("--a", required=True)
    p.add_argument("--b", required=True)
    p.add_argument("--pair", required=True)
    p.add_argument("--policy", required=True)
    p.add_argument("--identities")
    p.add_argument("--rec-a")
    p.add_argument("--rec-b")
    p.add_argument("--out")
    p.set_defaults(func=cmd_eval_parity)

    p = sub.add_parser("official-noise", help="官方噪声带三对")
    for k in ("e0", "o1", "o2", "policy"):
        p.add_argument(f"--{k}", required=True)
    p.add_argument("--identities", required=True)
    p.add_argument("--out")
    p.set_defaults(func=cmd_official_noise)

    p = sub.add_parser("prod-vs-official", help="正式跑法 vs 官方各参照")
    p.add_argument("--prod", required=True)
    p.add_argument("--ref", action="append", required=True, help="名字=源，可重复")
    p.add_argument("--policy", required=True)
    p.add_argument("--identities", required=True)
    p.add_argument("--out")
    p.set_defaults(func=cmd_prod_vs_official)

    p = sub.add_parser("relative-accept", help="§3.1 最终相对标准")
    for k in ("e0", "o1", "o2", "prod", "policy"):
        p.add_argument(f"--{k}", required=True)
    p.add_argument("--identities", required=True)
    p.add_argument("--out")
    p.set_defaults(func=cmd_relative_accept)

    p = sub.add_parser("action-diff", help="开环动作逐维差")
    p.add_argument("--a", required=True)
    p.add_argument("--b", required=True)
    p.add_argument("--name", default="model_action")
    p.add_argument("--kind", choices=("replay", "iface"), default="replay")
    p.add_argument("--payload-name")
    p.add_argument("--cond")
    p.add_argument("--policy")
    p.add_argument("--mode")
    p.add_argument("--out")
    p.set_defaults(func=cmd_action_diff)

    p = sub.add_parser("summarize-speed", help="计时字段汇总")
    p.add_argument("--src", action="append", required=True)
    p.add_argument("--kind", choices=("eval", "env"), default="eval")
    p.add_argument("--group-by", default="seat")
    p.add_argument("--out")
    p.set_defaults(func=cmd_summarize_speed)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    sys.exit(main())
