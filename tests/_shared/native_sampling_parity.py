#!/usr/bin/env python3
"""newtask-v2 三路对拍的测试侧工具：证据编码、HDF5 全字段比较与离线比较入口。

本模块只服务测试与对拍留档，产品生成路径（``scripts/generate_dataset_newseed.py``、
``src/robomme``）不导入它；它也不使用 ``tests/_shared/dataset_generation.py``
——后者会自动换 seed、另写求解循环，不能用于逐位对拍。

三路口径（方案第四步 4.0）：

* A：固定原版，来自 ``94449db`` 的 detached worktree，入口为原路径脚本
* B：新版不传 ``--sampling-config``
* C：新版显式传入冻结的原值配置

HDF5 判据（4.3）：遍历实际落盘树，逐 group / dataset / attribute 比较全集、dtype、
shape、字符串编码与逐元素内容；浮点按原 dtype 的位模式比较，不设容差。
不比较 HDF5 容器封装字节（group 默认 ``track_times=True``），也不比较带时间戳的视频文件。

离线比较入口（须在仓库根目录执行，``tests`` 是命名空间包）：

    uv run --no-sync python -m tests._shared.native_sampling_parity compare \\
        --reference <证据包或运行目录> --candidate <同上> --output <新目录>
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Iterator, Sequence

import h5py
import numpy as np


# ── HDF5 比较核已抽到 scripts/injection/h5_compare.py（注入链路不得依赖 tests/），这里反向 import 并 re-export ──
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
from scripts.injection.h5_compare import (  # noqa: E402
    ParityError,
    _dataset_signature,
    _first_element_difference,
    _raw_bytes,
    _walk,
    compare_h5,
)

def h5_fingerprint(path: str | Path) -> dict[str, Any]:
    """整份 HDF5 的结构与内容指纹：路径 → 签名（含内容 SHA-256）。"""
    source = Path(path)
    if not source.is_file():
        raise ParityError(f"缺少 HDF5：{source}")
    entries: dict[str, Any] = {}
    with h5py.File(source, "r") as handle:
        for name in sorted(handle.attrs.keys()):
            entries[f"@{name}"] = {
                "kind": "attribute",
                "sha256": hashlib.sha256(_raw_bytes(handle.attrs[name])).hexdigest(),
            }
        for node_path, node in _walk(handle):
            if isinstance(node, h5py.Group):
                entries[node_path] = {"kind": "group"}
            elif isinstance(node, h5py.Dataset):
                signature = _dataset_signature(node)
                signature["sha256"] = hashlib.sha256(_raw_bytes(node[()])).hexdigest()
                entries[node_path] = signature
            else:
                entries[node_path] = {
                    "kind": "attribute",
                    "sha256": hashlib.sha256(_raw_bytes(node)).hexdigest(),
                }
    return {"file": source.name, "entries": entries}


def h5_digest(fingerprint: dict[str, Any]) -> dict[str, Any]:
    """HDF5 指纹的入库形态：整份总散列 + 逐 timestep（及 setup）聚合散列。

    能力边界：能判断整份是否相同并定位到「哪一帧」，精确到字段要回 artifacts/
    用同一份完整指纹或原 HDF5 展开；本形态不能还原画面、也不能算像素差幅度。
    """
    entries = fingerprint["entries"]
    groups: dict[str, list[str]] = {}
    for path in sorted(entries):
        parts = path.split("/")
        key = "/".join(parts[:2]) if len(parts) >= 2 else parts[0]
        groups.setdefault(key, []).append(
            f"{path}|{json.dumps(entries[path], sort_keys=True, ensure_ascii=False)}"
        )
    return {
        "file": fingerprint["file"],
        "object_count": len(entries),
        "sha256": hashlib.sha256(
            json.dumps(entries, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest(),
        "group_count": len(groups),
        "group_sha256": {
            key: hashlib.sha256("".join(value).encode("utf-8")).hexdigest()[:HASH_WIDTH]
            for key, value in groups.items()
        },
    }


def episode_files(run_dir: str | Path) -> dict[str, Path]:
    """列出一个生成输出目录里的逐 episode HDF5，键为文件名。"""
    root = Path(run_dir)
    hdf5_dir = root / "hdf5_files"
    if not hdf5_dir.is_dir():
        raise ParityError(f"缺少 hdf5_files 目录：{hdf5_dir}")
    return {path.name: path for path in sorted(hdf5_dir.glob("*.h5"))}


def compare_runs(reference: str | Path, candidate: str | Path) -> dict[str, Any]:
    """比较两个生成输出目录里的全部逐 episode HDF5。"""
    left = episode_files(reference)
    right = episode_files(candidate)
    result: dict[str, Any] = {
        "reference": str(reference),
        "candidate": str(candidate),
        "reference_files": sorted(left),
        "candidate_files": sorted(right),
        "missing_in_candidate": sorted(set(left) - set(right)),
        "extra_in_candidate": sorted(set(right) - set(left)),
        "files": {},
    }
    for name in sorted(set(left) & set(right)):
        differences = compare_h5(left[name], right[name])
        result["files"][name] = {
            "difference_count": len(differences),
            "differences": differences[:50],
        }
    result["passed"] = (
        not result["missing_in_candidate"]
        and not result["extra_in_candidate"]
        and all(item["difference_count"] == 0 for item in result["files"].values())
        and bool(result["files"])
    )
    return result



# ── 观察器证据的读取、比较与轻量打包 ──────────────────────────────────────────

# 逐运行必然不同、不参与判定的字段
VOLATILE_EVIDENCE_FIELDS = ("pid", "label", "evidence_version")
# 逐条比较的证据段，对应方案第四步的对拍编号
EVIDENCE_SECTIONS = (
    ("rng", "④ 随机调用序列与流状态"),
    ("boundaries", "②.1 构造与初态边界"),
    ("events", "②.2/②.3 求值细节与事件"),
    ("steps", "②.2 逐步状态"),
    ("recordings", "②/③ 环境步与真实落盘记录映射"),
)


def load_evidence(
    path: str | Path, difficulty: str | None = None, index: int | None = None
) -> dict[str, Any]:
    """读取观察器写出的单局证据（.json.gz）。

    证据目录按 (task, seed) 切分，而 seed 不含难度——同一 episode 跑三个难度会落在同一个
    目录里，因此给了 ``difficulty`` 时按它消歧；仍不唯一才报错，不静默取第一份。
    """
    source = Path(path)
    if source.is_dir():
        candidates = sorted(source.glob("pid*.json.gz"))
        if len(candidates) > 1 and difficulty is not None:
            matched = []
            for candidate in candidates:
                with gzip.open(candidate, "rt", encoding="utf-8") as handle:
                    if json.load(handle).get("difficulty") == difficulty:
                        matched.append(candidate)
            candidates = matched
        if index is not None:
            # ⑤ 的同一 worker 会把同一个用例跑两次（甲→乙→甲），文件名带进程内序号，
            # 这时必须按出现次序显式选，不能靠难度消歧。
            if not 0 <= index < len(candidates):
                raise ParityError(f"{source}: 只有 {len(candidates)} 份证据，取不到第 {index} 份")
            source = candidates[index]
        else:
            if len(candidates) != 1:
                raise ParityError(
                    f"{source}: 期望恰好一份证据（难度={difficulty}），实际 {len(candidates)} 份"
                )
            source = candidates[0]
    if not source.is_file():
        raise ParityError(f"缺少证据文件：{source}")
    with gzip.open(source, "rt", encoding="utf-8") as handle:
        payload = json.load(handle)
    payload["_path"] = str(source)
    return payload


# 逐条散列全量入库会让证据包到几十 MB；小段保留逐条链，大段按块散列。
# 能力边界：块级只能把首个分歧缩到一个块内，精确到条要回 artifacts/ 的全量证据。
FULL_CHAIN_LIMIT = 512
CHAIN_BLOCK = 64
HASH_WIDTH = 16


def _record_hash(record: Any) -> str:
    return hashlib.sha256(
        json.dumps(record, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _chain(hashes: list[str]) -> dict[str, Any]:
    """逐条散列链；超过阈值就按块聚合，块大小写进结果里，便于换算下标区间。"""
    short = [item[:HASH_WIDTH] for item in hashes]
    if len(short) <= FULL_CHAIN_LIMIT:
        return {"granularity": "record", "block_size": 1, "chain": short}
    blocks = [
        hashlib.sha256("".join(short[start : start + CHAIN_BLOCK]).encode("utf-8")).hexdigest()[:HASH_WIDTH]
        for start in range(0, len(short), CHAIN_BLOCK)
    ]
    return {"granularity": "block", "block_size": CHAIN_BLOCK, "chain": blocks}


def evidence_digest(evidence: dict[str, Any]) -> dict[str, Any]:
    """轻量证据：逐段计数、整段散列与逐条散列链，可据此定位首个分歧而不必带全量。"""
    digest: dict[str, Any] = {
        "task": evidence.get("task"),
        "seed": evidence.get("seed"),
        "difficulty": evidence.get("difficulty"),
        "rrt_fallback_count": evidence.get("rrt_fallback_count"),
        "rng_total": evidence.get("rng_total"),
        "sections": {},
    }
    for name, _title in EVIDENCE_SECTIONS:
        records = evidence.get(name) or []
        hashes = [_record_hash(item) for item in records]
        chain = _chain(hashes)
        digest["sections"][name] = {
            "count": len(records),
            "sha256": hashlib.sha256("".join(hashes).encode("utf-8")).hexdigest(),
            "granularity": chain["granularity"],
            "block_size": chain["block_size"],
            "record_sha256": chain["chain"],
        }
    initial = evidence.get("initial_obs")
    digest["initial_obs_sha256"] = _record_hash(initial) if initial is not None else None
    return digest


def compare_evidence(reference: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    """逐段、逐条比较两份证据，定位首个分歧并附上下文。"""
    result: dict[str, Any] = {
        "reference": reference.get("_path"),
        "candidate": candidate.get("_path"),
        "reference_label": reference.get("label"),
        "candidate_label": candidate.get("label"),
        "rrt_fallback_count": {
            "reference": reference.get("rrt_fallback_count"),
            "candidate": candidate.get("rrt_fallback_count"),
        },
        "sections": {},
    }
    for key in ("task", "seed", "difficulty"):
        if reference.get(key) != candidate.get(key):
            result.setdefault("context_mismatch", []).append(
                f"{key}: {reference.get(key)!r} != {candidate.get(key)!r}"
            )
    for name, title in EVIDENCE_SECTIONS:
        left = reference.get(name) or []
        right = candidate.get(name) or []
        section: dict[str, Any] = {
            "title": title,
            "reference_count": len(left),
            "candidate_count": len(right),
            "first_divergence": None,
            "passed": True,
        }
        for index in range(min(len(left), len(right))):
            if _record_hash(left[index]) != _record_hash(right[index]):
                section["passed"] = False
                section["first_divergence"] = {
                    "index": index,
                    "reference": left[index],
                    "candidate": right[index],
                    "previous": left[index - 1] if index else None,
                }
                break
        if section["passed"] and len(left) != len(right):
            section["passed"] = False
            shorter = min(len(left), len(right))
            section["first_divergence"] = {
                "index": shorter,
                "note": "一侧提前结束",
                "reference": left[shorter] if shorter < len(left) else None,
                "candidate": right[shorter] if shorter < len(right) else None,
            }
        result["sections"][name] = section

    left_initial = reference.get("initial_obs")
    right_initial = candidate.get("initial_obs")
    result["initial_obs"] = {
        "title": "①.1 外层 reset 返回的初态观测",
        "passed": _record_hash(left_initial) == _record_hash(right_initial),
        "reference_present": left_initial is not None,
        "candidate_present": right_initial is not None,
    }
    result["passed"] = (
        not result.get("context_mismatch")
        and all(item["passed"] for item in result["sections"].values())
        and result["initial_obs"]["passed"]
    )
    return result


def compare_evidence_dirs(reference_dir: str | Path, candidate_dir: str | Path) -> dict[str, Any]:
    """比较两条路径下同名（任务_seed）的全部单局证据。"""
    left_root, right_root = Path(reference_dir), Path(candidate_dir)
    left = {path.name: path for path in sorted(left_root.glob("*_seed*")) if path.is_dir()}
    right = {path.name: path for path in sorted(right_root.glob("*_seed*")) if path.is_dir()}
    result: dict[str, Any] = {
        "reference": str(left_root),
        "candidate": str(right_root),
        "missing_in_candidate": sorted(set(left) - set(right)),
        "extra_in_candidate": sorted(set(right) - set(left)),
        "episodes": {},
    }
    for name in sorted(set(left) & set(right)):
        result["episodes"][name] = compare_evidence(load_evidence(left[name]), load_evidence(right[name]))
    result["passed"] = (
        not result["missing_in_candidate"]
        and not result["extra_in_candidate"]
        and bool(result["episodes"])
        and all(item["passed"] for item in result["episodes"].values())
    )
    return result


# ── 一次运行的打包、逐格结论与离线复验 ────────────────────────────────────────

PATH_LABELS = ("A1", "A2", "B", "C")
# 逐格必须成立的比较对；A1↔A2 是原版重复性与观察器校准，其余三对是三路对拍
COMPARISONS = (("A1", "A2"), ("A1", "B"), ("A1", "C"), ("B", "C"))


def _episode_dir(run_root: Path, cell: str, label: str) -> Path:
    """A 路产物落基线 worktree、B/C 落主工作树，两边的相对结构相同。"""
    if label.startswith("A"):
        return run_root.parent.parent / "native-baseline" / "artifacts" / "parity" / run_root.name / cell / label
    return run_root / cell / label


def _single_h5(run_dir: Path) -> Path | None:
    files = episode_files(run_dir) if (run_dir / "hdf5_files").is_dir() else {}
    if len(files) != 1:
        return None
    return next(iter(files.values()))


def pack_run(
    run_root: Path,
    evidence_root: Path,
    cases: list[dict[str, Any]],
    output: Path,
) -> dict[str, Any]:
    """把一次运行压成轻量证据包：逐格 HDF5 指纹、证据指纹与逐对比较结论。

    完整 HDF5、视频、逐步全量证据留在 ``artifacts/``；这里只写指纹、逐条散列链
    与结论，内容相同的路径互相引用同一份证据，不重复存。
    """
    output.mkdir(parents=True, exist_ok=True)
    evidence_dir = output / "evidence"
    evidence_dir.mkdir(exist_ok=True)
    store: dict[str, str] = {}
    result: dict[str, Any] = {"run": run_root.name, "cells": {}}

    for case in cases:
        cell = case["cell"]
        cell_result: dict[str, Any] = {
            "case": {key: case[key] for key in ("task", "episode", "difficulty", "seed", "branch") if key in case},
            "paths": {},
            "comparisons": {},
        }
        payloads: dict[str, dict[str, Any]] = {}
        for label in PATH_LABELS:
            run_dir = _episode_dir(run_root, cell, label)
            summary_path = run_dir / "run_summary.json"
            entry: dict[str, Any] = {"output_dir": str(run_dir)}
            if summary_path.is_file():
                summary = json.loads(summary_path.read_text(encoding="utf-8"))
                entry["success_count"] = summary.get("success_count")
                entry["exhausted_count"] = summary.get("exhausted_count")
                entry["elapsed_s"] = summary.get("elapsed_s")
            h5_path = _single_h5(run_dir)
            if h5_path is not None:
                fingerprint = h5_fingerprint(h5_path)
                entry["h5"] = {
                    "file": fingerprint["file"],
                    "object_count": len(fingerprint["entries"]),
                    "sha256": hashlib.sha256(
                        json.dumps(fingerprint["entries"], sort_keys=True).encode("utf-8")
                    ).hexdigest(),
                }
                entry["h5_fingerprint_ref"] = _store(
                    evidence_dir, store, f"{cell}.{label}.h5", h5_digest(fingerprint)
                )
            episode_evidence = evidence_root / label / f"{case['task']}_seed{case['seed']}"
            if episode_evidence.is_dir() and list(episode_evidence.glob("pid*.json.gz")):
                payload = load_evidence(episode_evidence, case.get("difficulty"))
                payloads[label] = payload
                digest = evidence_digest(payload)
                entry["rrt_fallback_count"] = payload.get("rrt_fallback_count")
                entry["sections"] = {
                    name: digest["sections"][name]["count"] for name, _ in EVIDENCE_SECTIONS
                }
                entry["evidence_ref"] = _store(evidence_dir, store, f"{cell}.{label}.evidence", digest)
            cell_result["paths"][label] = entry

        for left, right in COMPARISONS:
            key = f"{left}-{right}"
            comparison: dict[str, Any] = {}
            left_dir = _episode_dir(run_root, cell, left)
            right_dir = _episode_dir(run_root, cell, right)
            left_h5 = _single_h5(left_dir)
            right_h5 = _single_h5(right_dir)
            if left_h5 and right_h5:
                differences = compare_h5(left_h5, right_h5)
                comparison["h5"] = {
                    "passed": not differences,
                    "difference_count": len(differences),
                    "differences": differences[:20],
                }
            else:
                comparison["h5"] = {"passed": None, "note": "一侧没有有效 HDF5（原版失败时只记失败行为对照）"}
            if left in payloads and right in payloads:
                evidence_result = compare_evidence(payloads[left], payloads[right])
                comparison["evidence"] = {
                    "passed": evidence_result["passed"],
                    "sections": {
                        name: section["passed"] for name, section in evidence_result["sections"].items()
                    },
                    "initial_obs": evidence_result["initial_obs"]["passed"],
                    "first_divergence": {
                        name: section["first_divergence"]["index"]
                        for name, section in evidence_result["sections"].items()
                        if section["first_divergence"] is not None
                    },
                }
            else:
                comparison["evidence"] = {"passed": None, "note": "一侧没有证据"}
            cell_result["comparisons"][key] = comparison

        fallbacks = [
            cell_result["paths"][label].get("rrt_fallback_count")
            for label in ("A1", "A2")
            if label in cell_result["paths"]
        ]
        native_ok = all(
            cell_result["paths"].get(label, {}).get("success_count") == 1 for label in ("A1", "A2")
        )
        deterministic = native_ok and all(value == 0 for value in fallbacks if value is not None)
        all_passed = all(
            item["h5"].get("passed") and item["evidence"].get("passed")
            for item in cell_result["comparisons"].values()
        )
        if not native_ok:
            cell_result["status"] = "受阻-原版首次尝试失败"
        elif not deterministic:
            cell_result["status"] = "受阻-规划器非确定"
        elif all_passed:
            cell_result["status"] = "通过"
        else:
            cell_result["status"] = "失败"
        cell_result["rrt_fallback_count"] = {"A1": fallbacks[0] if fallbacks else None,
                                             "A2": fallbacks[1] if len(fallbacks) > 1 else None}
        result["cells"][cell] = cell_result
        print(f"对拍检查完成 {cell}：{cell_result['status']}", flush=True)

    counter: dict[str, int] = {}
    for item in result["cells"].values():
        counter[item["status"]] = counter.get(item["status"], 0) + 1
    result["status_counts"] = counter
    result["passed"] = counter.get("通过", 0) == len(result["cells"])
    (output / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    manifest = {
        "evidence_files": sorted(path.name for path in evidence_dir.glob("*.json")),
        "dedup_map": store,
        "total_bytes": sum(path.stat().st_size for path in evidence_dir.glob("*.json")),
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return result


def _store(evidence_dir: Path, store: dict[str, str], name: str, payload: dict[str, Any]) -> str:
    """内容去重：相同内容只落一份文件，其余引用同一个散列名。"""
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]
    target = evidence_dir / f"{digest}.json"
    if not target.is_file():
        target.write_text(body, encoding="utf-8")
    store[name] = digest
    return digest


# ── ⑤ 连续 worker 隔离的比较 ──────────────────────────────────────────────────

# 「甲 → 乙 → 甲」三个槽位，各自对应哪一格的独立运行
ISOLATION_SLOTS = (
    ("first-a", "BinFill-easy-dynamicTrue", "BinFill", 4000, "easy", 0),
    ("second-b", "VideoRepick-easy", "VideoRepick", 9000, "easy", 0),
    ("first-again", "BinFill-easy-dynamicTrue", "BinFill", 4000, "easy", 1),
)


def compare_worker_isolation(
    run_root: Path, evidence_root: Path, label: str, independent_label: str
) -> dict[str, Any]:
    """⑤.3：连续 worker 里的每一局，与对应的独立运行逐项比较。

    覆盖不传配置（``S-default`` ↔ 独立 ``B``）与显式原值配置（``S-config`` ↔ 独立 ``C``）两路。
    """
    isolation_root = run_root / "worker-isolation" / label
    report: dict[str, Any] = {"label": label, "independent_label": independent_label, "slots": {}}
    for slot, cell, task, seed, difficulty, occurrence in ISOLATION_SLOTS:
        entry: dict[str, Any] = {"cell": cell, "task": task, "seed": seed, "difficulty": difficulty}
        continuous_h5 = _single_h5(isolation_root / slot)
        independent_h5 = _single_h5(_episode_dir(run_root, cell, independent_label))
        if continuous_h5 is None or independent_h5 is None:
            entry["h5"] = {"passed": None, "note": "一侧没有有效 HDF5"}
        else:
            differences = compare_h5(independent_h5, continuous_h5)
            entry["h5"] = {
                "passed": not differences,
                "difference_count": len(differences),
                "differences": differences[:20],
            }
        try:
            continuous = load_evidence(
                evidence_root / label / f"{task}_seed{seed}", index=occurrence
            )
            independent = load_evidence(
                evidence_root / independent_label / f"{task}_seed{seed}", difficulty
            )
        except ParityError as exc:
            entry["evidence"] = {"passed": None, "note": str(exc)}
        else:
            result = compare_evidence(independent, continuous)
            entry["evidence"] = {
                "passed": result["passed"],
                "sections": {
                    name: section["passed"] for name, section in result["sections"].items()
                },
                "initial_obs": result["initial_obs"]["passed"],
                "rrt_fallback_count": result["rrt_fallback_count"],
            }
        report["slots"][slot] = entry
    report["passed"] = all(
        item["h5"].get("passed") and item["evidence"].get("passed")
        for item in report["slots"].values()
    )
    return report

def _main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="newtask-v2 三路对拍的离线比较")
    sub = parser.add_subparsers(dest="command", required=True)
    compare = sub.add_parser("compare", help="比较两个生成输出目录的 HDF5 全字段内容")
    compare.add_argument("--reference", required=True)
    compare.add_argument("--candidate", required=True)
    compare.add_argument("--output", default=None, help="把结果写到该目录的 result.json")
    evidence = sub.add_parser("compare-evidence", help="比较两条路径下的观察器证据（②/④/①.1）")
    evidence.add_argument("--reference", required=True)
    evidence.add_argument("--candidate", required=True)
    evidence.add_argument("--output", default=None)
    digest = sub.add_parser("digest", help="把一条路径下的证据压成可入 Git 的轻量指纹")
    digest.add_argument("--evidence", required=True)
    digest.add_argument("--output", required=True)
    pack = sub.add_parser("pack", help="把一次运行压成逐格结论与可入 Git 的轻量证据包")
    pack.add_argument("--run-root", required=True, help="artifacts/parity/<run-id>")
    pack.add_argument("--evidence-root", required=True, help="artifacts/parity-evidence/<run-id>")
    pack.add_argument("--cases", required=True)
    pack.add_argument("--output", required=True)
    isolation = sub.add_parser("isolation", help="⑤：连续 worker 的每一局与对应独立运行比较")
    isolation.add_argument("--run-root", required=True)
    isolation.add_argument("--evidence-root", required=True)
    isolation.add_argument("--output", default=None)
    args = parser.parse_args(argv)

    if args.command == "isolation":
        reports = [
            compare_worker_isolation(
                Path(args.run_root).resolve(), Path(args.evidence_root).resolve(), label, independent
            )
            for label, independent in (("S-default", "B"), ("S-config", "C"))
        ]
        if args.output:
            out = Path(args.output)
            out.mkdir(parents=True, exist_ok=True)
            (out / "worker_isolation.json").write_text(
                json.dumps(reports, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        for report in reports:
            print(f"{report['label']} ↔ 独立 {report['independent_label']}: passed={report['passed']}")
            for slot, item in report["slots"].items():
                print(
                    f"  {slot} ({item['cell']}): h5={item['h5'].get('passed')} "
                    f"evidence={item['evidence'].get('passed')} "
                    f"sections={item['evidence'].get('sections')}"
                )
        return 0 if all(report["passed"] for report in reports) else 1

    if args.command == "pack":
        cases = json.loads(Path(args.cases).read_text(encoding="utf-8"))["cases"]
        result = pack_run(
            Path(args.run_root).resolve(),
            Path(args.evidence_root).resolve(),
            cases,
            Path(args.output),
        )
        print(json.dumps({"status_counts": result["status_counts"], "passed": result["passed"]}, ensure_ascii=False, indent=2))
        for cell, item in result["cells"].items():
            summary = ", ".join(
                f"{key}:h5={value['h5'].get('passed')}/ev={value['evidence'].get('passed')}"
                for key, value in item["comparisons"].items()
            )
            print(f"  {cell}: {item['status']} | {summary}")
        return 0 if result["passed"] else 1

    if args.command == "digest":
        root = Path(args.evidence)
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            path.name: evidence_digest(load_evidence(path))
            for path in sorted(root.glob("*_seed*"))
            if path.is_dir()
        }
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"digest": str(out), "episodes": sorted(payload)}, ensure_ascii=False))
        return 0

    if args.command == "compare-evidence":
        result = compare_evidence_dirs(args.reference, args.candidate)
        if args.output:
            out = Path(args.output)
            out.mkdir(parents=True, exist_ok=True)
            (out / "evidence_result.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        print(json.dumps({k: v for k, v in result.items() if k != "episodes"}, ensure_ascii=False, indent=2))
        for name, item in result["episodes"].items():
            print(f"  {name}: passed={item['passed']} " + ", ".join(
                f"{key}({sec['reference_count']}/{sec['candidate_count']})={sec['passed']}"
                for key, sec in item["sections"].items()
            ))
        return 0 if result["passed"] else 1

    result = compare_runs(args.reference, args.candidate)
    if args.output:
        out = Path(args.output)
        out.mkdir(parents=True, exist_ok=True)
        (out / "result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(_main())
