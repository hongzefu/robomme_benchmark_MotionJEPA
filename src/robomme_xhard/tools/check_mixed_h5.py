"""原版 schema、混合档内容、动作语义与独立身份对账的 CPU 校验入口。"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import re
import sys
import time

import h5py
import numpy as np

from ..configs import DIFFICULTIES, TASK_ORDER, TIER_CONFIGS
from .subgoal_rules import EXEMPT, EXPECTED_CHECKS, SUBGOAL_RULES

REPO_ROOT = Path(__file__).resolve().parents[3]
for directory in (REPO_ROOT / "scripts/data-generation", REPO_ROOT / "scripts/data-generation-newSeed"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))
from validate_generated_dataset_contract import inspect_episode_terminal, timestep_indices  # noqa: E402
from seed_layout import get_layout, parse_difficulty_cycle  # noqa: E402

REVISION = "a5e4e25ffe8af34f64944f9533d06455ce5f8337"
DEFAULT_CYCLE = "easy,medium,hard,xhard12,xhard14,xhard16,xhard18,xhard20"
BASE_TIERS = frozenset({"easy", "medium", "hard"})
# 独立常量，不能从生成器或 run_parameters.json 读回自证。
FAIL_RECOVER_TASKS = frozenset({
    "BinFill", "PickXtimes", "SwingXtimes", "VideoUnmask", "ButtonUnmask",
    "VideoUnmaskSwap", "ButtonUnmaskSwap", "PickHighlight", "VideoRepick",
    "VideoPlaceButton", "VideoPlaceOrder",
})
RAW_KEYS = tuple(f"{prefix}/{part}" for prefix in ("obs/eef_state_raw", "action/eef_action_raw")
                 for part in ("pose", "quat", "rpy"))
RECOVERY_KEYS = ("setup/fail_recover_mode", "setup/fail_recover_seed_anchor")
FILE_RE = re.compile(r"(?P<task>[A-Za-z]+)_ep(?P<episode>\d+)_seed(?P<seed>\d+)\.h5")


def effective_cycle(task, cycle):
    """独立用冻结配置的键过滤循环，不读取产物 effective_cycles。"""
    available = TIER_CONFIGS.get(task, {})
    result = tuple(tier for tier in cycle if tier in BASE_TIERS or tier in available)
    if not result:
        raise ValueError(f"{task} 有效循环为空")
    return result


def expected_identity(task, episode, attempt, cycle):
    tiers = effective_cycle(task, cycle)
    difficulty = tiers[episode % len(tiers)]
    mode = None
    if task in FAIL_RECOVER_TASKS and difficulty in BASE_TIERS:
        ordinal = sum(tiers[index % len(tiers)] in BASE_TIERS for index in range(episode))
        mode = "z" if ordinal < 3 else "xy" if ordinal < 6 else None
    return {"task": task, "episode": episode, "attempt": attempt,
            "seed": get_layout("train").seed(task, episode, attempt),
            "difficulty": difficulty, "recovery_mode": mode}


def leaf_datasets(group):
    leaves = {}
    group.visititems(lambda name, obj: leaves.__setitem__(name, obj) if isinstance(obj, h5py.Dataset) else None)
    return leaves


def text(dataset):
    value = dataset[()]
    return value.decode("utf-8") if isinstance(value, bytes) else str(value)


def export_golden(official, out_dir, tasks=TASK_ORDER):
    """仅遍历 episode_0 的元数据，不读取观测数组。"""
    started = time.monotonic()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    exported = []
    for task in tasks:
        source = Path(official) / f"record_dataset_{task}.h5"
        with h5py.File(source, "r") as handle:
            episode = handle["episode_0"]
            indices, errors = timestep_indices(episode, str(source))
            if errors:
                raise ValueError("；".join(errors))
            excluded = list(RAW_KEYS) + [key for key in RECOVERY_KEYS if key in episode]
            golden = {"task": task, "source": {"file": str(source.resolve()), "revision": REVISION, "episode": 0},
                      "excluded_keys": excluded, "variable_shape_keys": ["setup/task_goal"],
                      "setup": {}, "timestep": {}}
            for section, groups in (("setup", [episode["setup"]]),
                                    ("timestep", [episode[f"timestep_{index}"] for index in indices])):
                observed_keys = None
                for group in groups:
                    leaves = {key: dataset for key, dataset in leaf_datasets(group).items()
                              if (f"setup/{key}" if section == "setup" else key) not in excluded}
                    if observed_keys is not None and set(leaves) != observed_keys:
                        raise ValueError(f"{source}/{group.name} 原版键集随 timestep 变化")
                    observed_keys = set(leaves)
                    for key, dataset in leaves.items():
                        spec = golden[section].setdefault(key, {"dtypes": [], "shape": list(dataset.shape)})
                        if spec["shape"] != list(dataset.shape):
                            raise ValueError(f"{source}/{group.name}/{key} 原版 shape 随 timestep 变化")
                        dtype = str(dataset.dtype)
                        if dtype not in spec["dtypes"]:
                            spec["dtypes"].append(dtype)
                for spec in golden[section].values():
                    spec["dtypes"].sort()
            destination = out_dir / f"{task}.json"
            destination.write_text(json.dumps(golden, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            exported.append({"task": task, "source": golden["source"], "excluded_keys": excluded,
                             "timesteps": len(indices), "out": str(destination)})
    return {"files": exported, "elapsed_s": round(time.monotonic() - started, 3)}


def read_products(output_dir):
    """保留重复记录，供身份级对账；失败与崩溃前缀文件不进入成功集合。"""
    root = Path(output_dir)
    errors = []
    results = []
    result_file = root / "episode_results.jsonl"
    if not result_file.is_file():
        errors.append(f"缺少 {result_file}")
    else:
        for line_number, line in enumerate(result_file.read_text(encoding="utf-8").splitlines(), 1):
            try:
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise ValueError("记录不是对象")
                results.append(row)
            except (ValueError, TypeError) as exc:
                errors.append(f"{result_file} 第 {line_number} 行无效：{exc}")
    metadata = []
    for path in sorted(root.glob("record_dataset_*_metadata.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            rows = payload["records"]
            if payload.get("record_count") != len(rows):
                errors.append(f"{path} record_count 不符")
            for row in rows:
                if not isinstance(row, dict):
                    raise ValueError("metadata 记录不是对象")
                if row.get("task") != payload.get("env_id") or path.name != f"record_dataset_{row.get('task')}_metadata.json":
                    errors.append(f"{path} task/env_id 不符")
                metadata.append(row)
        except (ValueError, KeyError, TypeError) as exc:
            errors.append(f"{path} 无效：{exc}")
    files = []
    for path in sorted((root / "hdf5_files").glob("*.h5")):
        if path.name.startswith(("FAILED_", "CRASHED_")):
            continue
        match = FILE_RE.fullmatch(path.name)
        if match is None:
            errors.append(f"未知成功文件名 {path}")
            files.append({"task": None, "episode": None, "seed": None, "path": str(path)})
        else:
            files.append({"task": match["task"], "episode": int(match["episode"]),
                          "seed": int(match["seed"]), "path": str(path)})
    return {"results": results, "metadata": metadata, "files": files, "errors": errors}


def audit_dataset(output_dir, cycle, episode_start, episodes, max_attempts=100, tasks=TASK_ORDER, products=None):
    products = products or read_products(output_dir)
    expected = {(task, episode) for task in tasks for episode in range(episode_start, episode_start + episodes)}
    errors = list(products["errors"])
    counts = {"episodes": len(expected), "missing": 0, "dup": 0, "unknown": 0, "mismatch": len(errors)}
    grouped = {}
    for section in ("results", "metadata", "files"):
        groups = defaultdict(list)
        for row in products[section]:
            key = (row.get("task"), row.get("episode"))
            # bool 与浮点 episode 不能借 Python 数值相等冒充整数身份。
            if not isinstance(key[1], int) or isinstance(key[1], bool) or key not in expected:
                counts["unknown"] += 1
                errors.append(f"{section} 未知身份 {key}")
                continue
            groups[key].append(row)
        grouped[section] = groups
    for key in sorted(expected):
        rows = grouped["results"][key]
        success = [row for row in rows if row.get("ok") is True]
        metadata, files = grouped["metadata"][key], grouped["files"][key]
        for name, collection in (("成功记录", success), ("metadata", metadata), ("H5", files)):
            if not collection:
                counts["missing"] += 1
                errors.append(f"{key} 缺少{name}")
            if len(collection) > 1:
                counts["dup"] += len(collection) - 1
                errors.append(f"{key} {name}重复")
        attempts = [row.get("attempt") for row in rows]
        if (not rows or any(type(attempt) is not int for attempt in attempts)
                or attempts != list(range(len(rows))) or len(rows) > max_attempts
                or any(row.get("ok") is not False for row in rows[:-1])
                or rows[-1].get("ok") is not True):
            counts["mismatch"] += 1
            errors.append(f"{key} attempt 必须为连续失败后唯一成功，实际 {attempts}")
        for row in rows:
            attempt = row.get("attempt")
            if type(attempt) is not int or not 0 <= attempt < max_attempts or attempt >= 100:
                counts["mismatch"] += 1
                continue
            target = expected_identity(*key, attempt, cycle)
            if type(row.get("seed")) is not int or any(row.get(field) != target[field] for field in ("seed", "difficulty", "recovery_mode")):
                counts["mismatch"] += 1
                errors.append(f"{key} 结果 seed/difficulty/recovery_mode 不符，预期 {target}")
        if len(success) == 1:
            final = success[0]
            if final.get("task_success") is not True:
                counts["mismatch"] += 1
                errors.append(f"{key} 成功记录没有 task_success=True")
            for name, collection in (("metadata", metadata), ("H5", files)):
                fields = ("seed", "difficulty") if name == "metadata" else ("seed",)
                for row in collection:
                    if type(row.get("seed")) is not int or any(row.get(field) != final.get(field) for field in fields):
                        counts["mismatch"] += 1
                        errors.append(f"{key} {name} 与成功记录不符")
            if len(files) == 1 and (not isinstance(final.get("h5_path"), str)
                                   or Path(final["h5_path"]).name != Path(files[0]["path"]).name):
                counts["mismatch"] += 1
                errors.append(f"{key} 成功记录 h5_path 与成功文件名不符")
    counts["pass"] = not any(counts[field] for field in ("missing", "dup", "unknown", "mismatch"))
    return {**counts, "errors": errors}


def schema_errors(group, golden, section):
    leaves = leaf_datasets(group)
    actual = {key: dataset for key, dataset in leaves.items()
              if (f"setup/{key}" if section == "setup" else key) not in golden["excluded_keys"]}
    expected = golden[section]
    missing, extra = set(expected) - set(actual), set(actual) - set(expected)
    wrong = []
    for key in set(expected) & set(actual):
        dataset, spec = actual[key], expected[key]
        shape_ok = list(dataset.shape) == spec["shape"]
        if section == "setup" and key == "task_goal":
            shape_ok = dataset.ndim == len(spec["shape"]) and dataset.size > 0
        if str(dataset.dtype) not in spec["dtypes"] or not shape_ok:
            wrong.append(key)
    return {"missing": sorted(missing), "extra": sorted(extra), "dtype_shape": sorted(wrong)}


def subgoal_boundaries(episode, indices):
    """每个显式边界独立保留，连续同名边界也不能压缩。"""
    boundaries = []
    for index in indices:
        step = episode[f"timestep_{index}"]
        if bool(step["info/is_subgoal_boundary"][()]):
            boundaries.append({"timestep": index, "text": text(step["info/simple_subgoal"]),
                               "is_video_demo": bool(step["info/is_video_demo"][()])})
    return boundaries


def semantic_checks(task, difficulty, boundaries, record):
    expected = EXPECTED_CHECKS[task]
    rules, exemptions = SUBGOAL_RULES[task], EXEMPT[task]
    names = [rule["name"] for rule in rules]
    executed, exempted = set(names), set(exemptions)
    errors, details = [], []
    if (executed | exempted != set(expected) or executed & exempted or len(names) != len(executed)
            or any(not isinstance(reason, str) or not reason.strip() for reason in exemptions.values())):
        errors.append(f"规则覆盖不符：期望 {sorted(expected)}，执行 {names}，豁免 {exemptions}")
    knobs = TIER_CONFIGS[task][difficulty]["knobs"]
    # 字段由生成器报告，但期望仍取冻结配置；报告缺失不能默默跳过。
    if record.get("xhard_knobs") != knobs:
        errors.append(f"xhard_knobs 与冻结配置不符：{record.get('xhard_knobs')} != {knobs}")
    for rule in rules:
        try:
            expression = rule["expect"]
            if expression == "swap_runtime":
                target = int(knobs["swap_count"])
                checks = [item for item in record.get("runtime_checks", []) if item.get("kind") == "swap_sweep"]
                indices = {item.get("sweep_index") for item in checks if item.get("endpoint_match") is True}
                actual = sorted(indices, key=str)
                passed = (indices == set(range(target))
                          and all(type(item.get("sweep_index")) is int and item.get("endpoint_match") is True for item in checks)
                          and len(record.get("swap_plan", {}).get("pairs", [])) == target
                          and record.get("ok") is True and record.get("task_success") is True)
            else:
                parts = expression.split(":")
                if parts[0] == "const":
                    target = int(parts[1])
                elif parts[0] == "knob":
                    target = int(knobs[parts[1]])
                elif parts[0] == "knob_plus":
                    target = int(knobs[parts[1]]) + int(parts[2])
                elif parts[0] == "knob_affine":
                    target = int(knobs[parts[1]]) * int(parts[2]) + int(parts[3])
                else:
                    raise ValueError(f"未知 expect {expression}")
                actual = sum(re.search(rule["pattern"], boundary["text"]) is not None for boundary in boundaries)
                passed = actual == target
            details.append({"name": rule["name"], "expected": target, "actual": actual, "pass": passed})
            if not passed:
                errors.append(f"{rule['name']} 实际 {actual}，期望 {target}")
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            errors.append(f"{rule['name']} 规则执行失败：{exc}")
            details.append({"name": rule["name"], "pass": False, "error": str(exc)})
    return {"rules_expected": len(expected), "rules_run": len(details) + len(exemptions),
            "exempt": len(exemptions), "mismatch": len(errors), "errors": errors, "details": details}


def check_file(file_row, record, metadata, golden, cycle):
    task, episode_number = file_row["task"], file_row["episode"]
    path = Path(file_row["path"])
    result = {"file": str(path), "task": task, "episode": episode_number,
              "difficulty": record.get("difficulty"), "seed": file_row["seed"],
              "steps": 0, "schema": {"missing": 0, "extra": 0, "dtype_shape": 0},
              "content_errors": [], "schema_errors": [], "semantic": None}
    try:
        with h5py.File(path, "r") as handle:
            expected_group = f"episode_{episode_number}"
            if set(handle) != {expected_group}:
                result["content_errors"].append(f"H5 根组必须唯一为 {expected_group}")
            episode = handle[expected_group]
            indices, completed, errors = inspect_episode_terminal(episode, str(path))
            result["steps"] = len(indices)
            result["content_errors"].extend(errors)
            if completed is not True:
                result["content_errors"].append("末步未完成")
            target = expected_identity(task, episode_number, record["attempt"], cycle)
            for section, group in [("setup", episode["setup"])] + [("timestep", episode[f"timestep_{index}"]) for index in indices]:
                findings = schema_errors(group, golden, section)
                for kind, keys in findings.items():
                    result["schema"][kind] += len(keys)
                    if keys:
                        result["schema_errors"].append({"group": group.name, "kind": kind, "keys": keys})
            try:
                if (int(episode["setup/seed"][()]) != target["seed"]
                        or file_row["seed"] != target["seed"] or text(episode["setup/difficulty"]) != target["difficulty"]
                        or any(record.get(key) != target[key] for key in ("seed", "difficulty"))
                        or len(metadata) != 1 or any(metadata[0].get(key) != target[key] for key in ("seed", "difficulty"))):
                    result["content_errors"].append("setup/文件名/metadata/记录与独立 seed 或 difficulty 不符")
            except (KeyError, ValueError, TypeError) as exc:
                result["content_errors"].append(f"setup 内容无效：{exc}")
            done_seen, demo_ended = False, False
            for index in indices:
                group = episode[f"timestep_{index}"]
                try:
                    done, demo = bool(group["info/is_completed"][()]), bool(group["info/is_video_demo"][()])
                    if done_seen and not done:
                        result["content_errors"].append(f"{group.name} is_completed 非单调")
                    if demo_ended and demo:
                        result["content_errors"].append(f"{group.name} is_video_demo 非前缀")
                    done_seen |= done
                    demo_ended |= not demo
                    joint = group["action/joint_action"]
                    if joint.shape != (8,) or joint.dtype != np.dtype("float64") or not np.isfinite(joint[()]).all():
                        result["content_errors"].append(f"{group.name} joint_action 非有限 (8,) float64")
                except (KeyError, ValueError, TypeError) as exc:
                    result["content_errors"].append(f"{group.name} 内容无效：{exc}")
            for index in sorted({indices[0], indices[len(indices) // 2], indices[-1]}) if indices else []:
                for key in ("obs/front_rgb", "obs/wrist_rgb"):
                    image = episode[f"timestep_{index}/{key}"][()]
                    pixels = image.reshape(-1, image.shape[-1]) if image.ndim == 3 else image.reshape(-1, 1)
                    if not image.size or np.array_equal(np.min(pixels, axis=0), np.max(pixels, axis=0)):
                        result["content_errors"].append(f"timestep_{index}/{key} 图像为常量")
            prefix = path.stem
            video_dir = path.parent.parent / "videos"
            if not any(video_dir.glob(prefix + "_*.mp4")) and not (video_dir / (prefix + ".mp4")).is_file():
                result["content_errors"].append("缺少同身份 mp4")
            boundaries = subgoal_boundaries(episode, indices)
            result["boundaries"] = boundaries
            if target["difficulty"] in DIFFICULTIES:
                result["semantic"] = semantic_checks(task, target["difficulty"], boundaries, record)
    except (OSError, KeyError, ValueError, TypeError, IndexError) as exc:
        result["content_errors"].append(f"无法完整读取校验：{exc}")
        # 文件不可读或缺少键使结构未能完整检查，必须同时记录结构失败。
        if isinstance(exc, (OSError, KeyError)) and not any(result["schema"].values()):
            result["schema"]["missing"] += 1
            result["schema_errors"].append({"error": str(exc)})
    return result


def check_counts(products, cycle, episode_start, episodes, tasks):
    expected = Counter((task, effective_cycle(task, cycle)[ep % len(effective_cycle(task, cycle))])
                       for task in tasks for ep in range(episode_start, episode_start + episodes))
    actual = Counter((row.get("task"), row.get("difficulty")) for row in products["results"] if row.get("ok") is True)
    # 文件数与 metadata 的每档数同时对账，不能用结果记录代替真实文件。
    metadata = Counter((row.get("task"), row.get("difficulty")) for row in products["metadata"])
    file_counts = Counter(row.get("task") for row in products["files"])
    counts_ok = actual == expected and metadata == expected and file_counts == Counter({task: episodes for task in tasks})
    audit = audit_dataset(".", cycle, episode_start, episodes, tasks=tasks, products=products)
    return {"pass": counts_ok and audit["pass"], "tasks": len(tasks), "episodes": episodes,
            "per_tier_ok": int(counts_ok and audit["pass"]),
            "per_tier": [{"task": task, "difficulty": tier, "expected": count, "actual": actual[(task, tier)],
                          "metadata": metadata[(task, tier)]} for (task, tier), count in expected.items()], "audit": audit}


def compare_joint_actions(samples, compare_dir):
    result = {"candidates": len(samples), "matched": 0, "seed_mismatch": 0, "len_mismatch": 0,
              "elements": 0, "max_abs": "na"}
    right_files = defaultdict(list)
    for file in read_products(compare_dir)["files"]:
        right_files[(file["task"], file["episode"])].append(file)
    maximum = None
    for row in samples:
        other = right_files[(row["task"], row["episode"])]
        if len(other) != 1:
            continue
        if other[0]["seed"] != row["seed"]:
            result["seed_mismatch"] += 1
            continue
        try:
            with h5py.File(row["file"], "r") as left, h5py.File(other[0]["path"], "r") as right:
                name = f"episode_{row['episode']}"
                if int(left[f"{name}/setup/seed"][()]) != int(right[f"{name}/setup/seed"][()]):
                    result["seed_mismatch"] += 1
                    continue
                a, ae = timestep_indices(left[name], row["file"])
                b, be = timestep_indices(right[name], other[0]["path"])
                if ae or be or len(a) != len(b):
                    result["len_mismatch"] += 1
                    continue
                la = np.asarray([left[f"{name}/timestep_{i}/action/joint_action"][()] for i in a])
                ra = np.asarray([right[f"{name}/timestep_{i}/action/joint_action"][()] for i in b])
                if la.shape != ra.shape:
                    result["len_mismatch"] += 1
                    continue
                delta = np.abs(la - ra)
                if not np.isfinite(delta).all():
                    continue
                value = float(delta.max())
                maximum = value if maximum is None else max(value, maximum)
                result["matched"] += 1
                result["elements"] += int(delta.size)
        except (OSError, KeyError, ValueError, TypeError):
            continue
    result["max_abs"] = maximum if maximum is not None else "na"
    return result


def check_dataset(output_dir, golden_dir, cycle, episodes, sample="first-per-tier", workers=32,
                  episode_start=0, tasks=TASK_ORDER, compare_dir=None):
    products = read_products(output_dir)
    success = defaultdict(list)
    metadata = defaultdict(list)
    files = defaultdict(list)
    for section, target in (("results", success), ("metadata", metadata), ("files", files)):
        for row in products[section]:
            if section != "results" or row.get("ok") is True:
                target[(row.get("task"), row.get("episode"))].append(row)
    selected = []
    missing_samples = []
    expected_xhard = {}
    for task in tasks:
        seen = set()
        tiers = effective_cycle(task, cycle)
        for ep in range(episode_start, episode_start + episodes):
            tier = tiers[ep % len(tiers)]
            if sample == "first-per-tier" and tier in seen:
                continue
            seen.add(tier)
            key = (task, ep)
            if tier in DIFFICULTIES:
                expected_xhard[key] = len(EXPECTED_CHECKS[task])
            if len(files[key]) != 1 or len(success[key]) != 1:
                missing_samples.append(f"{key} 首条样本缺失或重复")
                continue
            selected.append((files[key][0], success[key][0], metadata[key],
                             json.loads((Path(golden_dir) / f"{task}.json").read_text(encoding="utf-8")), cycle))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        samples = list(pool.map(lambda values: check_file(*values), selected))
    schema = {"files": len(samples), "steps": sum(row["steps"] for row in samples),
              **{kind: sum(row["schema"][kind] for row in samples) for kind in ("missing", "extra", "dtype_shape")}}
    schema["missing"] += len(missing_samples)
    schema["pass"] = not any(schema[kind] for kind in ("missing", "extra", "dtype_shape"))
    content = {"files": len(samples), "fails": sum(bool(row["content_errors"]) for row in samples) + len(missing_samples)}
    content["pass"] = content["fails"] == 0
    semantics = {(row["task"], row["episode"]): row["semantic"] for row in samples
                 if (row["task"], row["episode"]) in expected_xhard and row["semantic"] is not None}
    # 应查集合在读产物前由有效循环与身份冻结，产物 difficulty 与读取失败不能缩小它。
    plan = {"files": len(expected_xhard), "rules_expected": sum(expected_xhard.values()),
            **{key: sum(item[key] for item in semantics.values()) for key in ("rules_run", "mismatch", "exempt")}}
    plan["mismatch"] += sum(expected_xhard[key] for key in set(expected_xhard) - set(semantics))
    plan["pass"] = plan["mismatch"] == 0 and plan["rules_expected"] == plan["rules_run"]
    report = {"schema": schema, "content": content,
              "counts": check_counts(products, cycle, episode_start, episodes, tasks), "plan": plan,
              "sample": sample, "samples": samples, "missing_samples": missing_samples,
              "product_errors": products["errors"]}
    if compare_dir is not None:
        report["compare"] = compare_joint_actions(samples, compare_dir)
    report["pass"] = all(report[key]["pass"] for key in ("schema", "content", "counts", "plan"))
    return report


def dump_subgoals(output_dir):
    products = read_products(output_dir)
    successes = {(row["task"], row["episode"], row["seed"]): row for row in products["results"] if row.get("ok") is True}
    dumped = []
    for row in products["files"]:
        key = (row["task"], row["episode"], row["seed"])
        record = successes.get(key)
        if record is None or record.get("difficulty") not in DIFFICULTIES:
            continue
        with h5py.File(row["path"], "r") as handle:
            episode = handle[f"episode_{row['episode']}"]
            indices, errors = timestep_indices(episode, row["path"])
            dumped.append({**row, "difficulty": record["difficulty"], "boundaries": subgoal_boundaries(episode, indices),
                           "xhard_knobs": record.get("xhard_knobs"), "swap_plan": record.get("swap_plan"),
                           "runtime_checks": record.get("runtime_checks"), "errors": errors})
    return {"samples": dumped, "errors": products["errors"]}


def decision_line(name, values, fields):
    return f"{name}={'PASS' if values['pass'] else 'FAIL'} " + " ".join(f"{field}={values[field]}" for field in fields)


def check_lines(report):
    lines = [decision_line("H5_SCHEMA", report["schema"], ("files", "steps", "missing", "extra", "dtype_shape")),
             decision_line("H5_CONTENT", report["content"], ("files", "fails")),
             decision_line("H5_COUNTS", report["counts"], ("tasks", "episodes", "per_tier_ok")),
             decision_line("PLAN_VS_RECORD", report["plan"], ("files", "rules_expected", "rules_run", "mismatch", "exempt"))]
    if "compare" in report:
        lines.append("XMACHINE_JOINT_DIFF " + " ".join(f"{key}={value}" for key, value in report["compare"].items()))
    return lines


def write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", help="检查首条样本、全量条数与语义")
    check.add_argument("--golden-dir", type=Path, required=True)
    check.add_argument("--sample", choices=("first-per-tier", "all"), default="first-per-tier")
    check.add_argument("--workers", type=int, default=32)
    check.add_argument("--out-json", type=Path, required=True)
    check.add_argument("--out-md", type=Path, required=True)
    check.add_argument("--compare-dir", type=Path)
    audit = commands.add_parser("audit", help="独立审查全部成功身份")
    audit.add_argument("--max-attempts", type=int, default=100)
    for command in (check, audit):
        command.add_argument("--output-dir", type=Path, required=True)
        command.add_argument("--cycle", default=DEFAULT_CYCLE)
        command.add_argument("--episode-start", type=int, default=0)
        command.add_argument("--episodes", type=int, required=True)
    export = commands.add_parser("export-golden", help="从原版 episode_0 导出结构")
    export.add_argument("--official", type=Path, required=True)
    export.add_argument("--out-dir", type=Path, required=True)
    dump = commands.add_parser("dump-subgoals", help="导出显式子目标边界与证据")
    dump.add_argument("--output-dir", type=Path, required=True)
    dump.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command in ("check", "audit"):
        if args.episodes <= 0 or args.episode_start < 0:
            parser.error("episodes 必须为正整数，episode-start 不能为负")
        cycle = parse_difficulty_cycle(args.cycle, DIFFICULTIES)
    if args.command == "export-golden":
        print(json.dumps(export_golden(args.official, args.out_dir), ensure_ascii=False))
        return 0
    if args.command == "dump-subgoals":
        write_json(args.out, dump_subgoals(args.output_dir))
        return 0
    if args.command == "audit":
        if not 1 <= args.max_attempts <= 100:
            parser.error("max-attempts 必须在 1..100")
        report = audit_dataset(args.output_dir, cycle, args.episode_start, args.episodes, args.max_attempts)
        print(decision_line("IDENTITY_AUDIT", report, ("episodes", "missing", "dup", "unknown", "mismatch")))
        for error in report["errors"]:
            print(error)
        return 0 if report["pass"] else 1
    if args.workers < 1:
        parser.error("workers 必须为正整数")
    report = check_dataset(args.output_dir, args.golden_dir, cycle, args.episodes, args.sample, args.workers,
                           args.episode_start, compare_dir=args.compare_dir)
    lines = check_lines(report)
    write_json(args.out_json, report)
    args.out_md.parent.mkdir(parents=True, exist_ok=True)
    failures = [{"file": row["file"], "schema": row["schema_errors"], "content": row["content_errors"],
                 "semantic": row["semantic"]} for row in report["samples"]
                if row["schema_errors"] or row["content_errors"] or (row["semantic"] and row["semantic"]["mismatch"])]
    args.out_md.write_text("# 混合档 H5 校验\n\n```text\n" + "\n".join(lines) + "\n```\n\n"
                           + "## 样本与失败证据\n\n```json\n" + json.dumps({"missing": report["missing_samples"],
                              "product_errors": report["product_errors"], "failures": failures,
                              "identity": report["counts"]["audit"]}, ensure_ascii=False, indent=2) + "\n```\n", encoding="utf-8")
    print("\n".join(lines))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
