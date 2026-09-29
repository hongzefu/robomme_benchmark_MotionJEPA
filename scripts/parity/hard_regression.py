#!/usr/bin/env python3
"""robomme_hard 回归工具（v7：0928-newtask-v7-xhard0-shared-layout-plan.md 第二部分 §1.5、§7.6）。

子命令：

* ``layout-shared``（静态）：派生档与 xhard4 母布局共用 → ``V7_LAYOUT_SHARED``。
* ``prefix-geometry``（静态）：派生行位置类注入值是母值或前缀、几何约束与 xhard4 相同 → ``V7_PREFIX_GEOMETRY``。
* ``reset-replay``（GPU）：v7 每格 candidate 最小的正式局（(13 任务 × 3 档 + 16 任务 × 1 档) × 1 局 = 55）经评估链
  ``make_env_for_episode`` + reset，``spec_binding()`` 零差 → ``V7_RESET_REPLAY``（换包前用 ``--specs-root``）。
* ``eval-smoke``（GPU，1 任务 × 1 档 × 1 局）：合作者入口可用；xhard0 局须为导出模式 → ``HARD_EVAL_SMOKE``。
* ``xhard0-reset-parity``（GPU）：官方 robomme 与 robomme_hard 两进程各 reset 192 局，确定性层逐位比 →
  ``XHARD0_RESET_PARITY``；演示层只报告 ``XHARD0_DEMO_DIFF=INFO``。
* ``xhard0-eval-parity``（纯 CPU）：两策略官方路线与 v7 xhard0 终态对照，只报告 → ``XHARD0_EVAL_PARITY=INFO``。

旧的 ``s4-subset`` 与 S4 映射表随 v6 规格一起退役（git 历史可取回）。
"""

from __future__ import annotations

import argparse
import ast
import collections
import json
import math
import sys
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
for extra in (REPO / "src", REPO):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))



def _hard_specs():
    from robomme_hard.env_record_wrapper import hard_specs

    return hard_specs


# ── 记录点路径（静态收集 SpecRecorder.record 的第一个参数）─────────────────────


def record_path_patterns(task: str, root: Path = REPO / "src" / "robomme_hard" / "robomme_env",
                         method: str = "record") -> set[str]:
    """该任务环境文件与共用 utils 里 ``*.record(<路径>, …)`` 的路径正则（按任务分开，不同任务同名路径可能一记一注）；
    f-string 的占位符只匹配一个路径段（``[^.]+``）。"""
    import re

    patterns: set[str] = set()
    for path in [root / f"{task}.py", *sorted((root / "utils").glob("*.py"))]:
        for node in ast.walk(ast.parse(path.read_text())):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == method
                    and node.args):
                continue
            arg = node.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                patterns.add(re.escape(arg.value))
            elif isinstance(arg, ast.JoinedStr):
                parts = [re.escape(str(v.value)) if isinstance(v, ast.Constant) else "[^.]+" for v in arg.values]
                pattern = "".join(parts)
                if not pattern.startswith("[^.]+"):  # 整条路径都是变量（如 f"{spec_prefix}.placed"）无法静态归类，不收
                    patterns.add(pattern)
    return patterns


def is_record_path(key: str, patterns: set[str]) -> bool:
    import re

    return any(re.fullmatch(p, key) or re.match(p + r"\.", key) for p in patterns)


def _flatten(node: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(node, dict):
        out: dict[str, Any] = {}
        for key, value in node.items():
            out.update(_flatten(value, f"{prefix}.{key}" if prefix else str(key)))
        return out
    return {prefix: node}


def _leaf_diff(a: Any, b: Any) -> float:
    from robomme_hard.env_record_wrapper.hard_specs import _max_abs_diff

    return _max_abs_diff(a, b)


def compare_specs(s4_spec: dict[str, Any], hard_spec: dict[str, Any], record_prefixes: set[str],
                  value_patterns: set[str] = frozenset()) -> dict[str, Any]:
    """逐叶比对（忽略 provenance 与 identity 两个说明性分支）；返回回注点差、记录点差与最大差。"""
    skip = ("provenance", "identity")
    a = {k: v for k, v in _flatten(s4_spec).items() if k.split(".")[0] not in skip}
    b = {k: v for k, v in _flatten(hard_spec).items() if k.split(".")[0] not in skip}
    injected, within, max_abs, paths = 0, 0, 0.0, []
    tol = _hard_specs().RECORDED_FLOAT_TOL
    for key in sorted(set(a) | set(b)):
        if key in a and key in b and a[key] == b[key]:
            continue
        diff = _leaf_diff(a.get(key), b.get(key)) if key in a and key in b else math.inf
        is_record = is_record_path(key, record_prefixes) and not is_record_path(key, value_patterns)
        if is_record and diff <= tol:
            within += 1
            max_abs = max(max_abs, diff)
        else:
            injected += 1
            paths.append(key)
    return {"injected": injected, "within": within, "max_abs": max_abs, "paths": paths}


def delivery_index(specs_root: str | None = None) -> dict[tuple[str, str, int], dict[str, Any]]:
    """(task, tier, seed) → {row, builder_episode}；builder 号与 hard_builder 相同：xhard0 12 局在前，
    之后档序主序、档内 candidate 升序（v7 方案第二部分 §7.2）。"""
    hs = _hard_specs()
    index: dict[tuple[str, str, int], dict[str, Any]] = {}
    offsets: dict[str, int] = collections.Counter({task: hs.XHARD0_PER_TASK for task in hs.ALL_TASKS})
    for tier in hs.TIERS:
        _, rows = hs.load_specs(hs.packaged_specs_path(tier, specs_root), check_fingerprint=False)
        for task in hs.ALL_TASKS:
            chosen = sorted((r for r in rows if r["task"] == task and hs.delivered(r)), key=lambda r: r["candidate"])
            for row in chosen:
                index[(task, tier, int(row["seed"]))] = {"row": row, "builder_episode": offsets[task]}
                offsets[task] += 1
    return index


# ── V7 静态闸门：母布局共用、前缀几何 ─────────────────────────────────────────


def _whitelist(path: Path | None = None) -> dict[str, dict[str, list[str]]]:
    path = path or (_hard_specs().PACKAGED_SPECS_ROOT / "layout_whitelist.json")
    return json.loads(Path(path).read_text())["tasks"]


def _get(tree: dict[str, Any], path: str):
    node = tree
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            raise KeyError(path)
        node = node[part]
    return node


def cmd_layout_shared(args) -> int:
    """V7_LAYOUT_SHARED（静态）：派生行 layout_parent 摘要等于 xhard4 同候选；每个 L 点的使用值等于母值
    （``[:n]`` 为前缀），N 点逐色不超过母值；非通配的 L 模式在每个派生行都必须出现（反向核对 missing_l）；四档 seed 相同。"""
    hs = _hard_specs()
    from robomme_hard.robomme_env.utils.episode_spec import PREFIX_SUFFIX, classify_path

    loaded = hs.load_specs_v7(args.specs_root, check_fingerprint=False)
    whitelist = _whitelist()
    mothers = {(r["task"], int(r["candidate"])): r for r in loaded["xhard4"][1]}
    rows = parent_mismatch = seed_mismatch = value_mismatch = missing_l = 0
    problems: list[str] = []
    tasks: set[str] = set()
    for tier in ("xhard1", "xhard2", "xhard3"):
        for row in loaded[tier][1]:
            rows += 1
            tasks.add(row["task"])
            mother = mothers.get((row["task"], int(row["candidate"])))
            if mother is None or mother["spec_sha256"] != row["layout_parent"]["spec_sha256"]:
                parent_mismatch += 1
                problems.append(f"parent:{row['task']}/{tier}/{row['candidate']}")
                continue
            seed_mismatch += int(int(mother["seed"]) != int(row["seed"]))
            spec, table = row["spec"], whitelist[row["task"]]
            hit = set(spec.get("layout_paths_hit") or ())
            for pattern in table["L"]:
                if "*" not in pattern and pattern.removesuffix(PREFIX_SUFFIX) not in hit:
                    missing_l += 1
                    problems.append(f"missing_l:{row['task']}/{tier}/{row['candidate']}:{pattern}")
            for path in sorted(hit):
                cls, pattern = classify_path(table, path)
                used, parent_value = _get(spec, path), _get(mother["spec"], path)
                if cls == "L":
                    ok = used == (parent_value[: len(used)] if pattern.endswith(PREFIX_SUFFIX) else parent_value)
                elif pattern == "objects.distractors.bins.*":  # N（D-19）：外环容器取自母布局外环（弧，逐个不重复）
                    family = list(_get(mother["spec"], "objects.distractors.bins").values())
                    siblings = [_get(spec, p) for p in hit if p.startswith("objects.distractors.bins.")]
                    ok = used in family and siblings.count(used) == 1
                else:  # N（D-15）：BinFill 嵌套派生，逐项不超过母值
                    ok = len(used) == len(parent_value) and all(int(u) <= int(p) for u, p in zip(used, parent_value))
                if not ok:
                    value_mismatch += 1
                    problems.append(f"value:{row['task']}/{tier}/{row['candidate']}:{path}")
    ok = parent_mismatch == seed_mismatch == value_mismatch == missing_l == 0 and rows > 0
    print(f"V7_LAYOUT_SHARED={'PASS' if ok else 'FAIL'} tasks={len(tasks)} rows={rows} parent_mismatch={parent_mismatch} "
          f"seed_mismatch={seed_mismatch} value_mismatch={value_mismatch} missing_l={missing_l}"
          + ("" if ok else f" detail={problems[:6]}"), flush=True)
    return 0 if ok else 1


#: 与摆放合法性有关的 decision 键（区域、最小中心距、间隙、环带、OBB 规则）：派生档必须与 xhard4 逐字相同
GEOMETRY_KEY_HINTS = ("region", "min_center", "min_gap", "ring", "gap_factor", "obb", "margin", "half_size")


def _geometry_leaves(tree: Any, prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    if isinstance(tree, dict):
        for key, value in tree.items():
            out.update(_geometry_leaves(value, f"{prefix}.{key}" if prefix else str(key)))
    elif any(h in prefix.split(".")[-1] for h in GEOMETRY_KEY_HINTS):
        out[prefix] = tree
    return out


def cmd_prefix_geometry(args) -> int:
    """V7_PREFIX_GEOMETRY（静态，不依赖环境复核）：派生行的每个位置类注入值（坐标、槽位、路径节点）都是母布局
    同名点的原值或前缀，且该任务在派生档与 xhard4 的几何约束（区域、最小中心距、间隙、环带）逐字相同。
    依序放置只对已放对象查成对距离／OBB，母布局在同一约束下合法 ⇒ 其子集（前缀）在派生档下合法（v7 §7.3.2）。"""
    hs = _hard_specs()
    loaded = hs.load_specs_v7(args.specs_root, check_fingerprint=False)
    mothers = {(r["task"], int(r["candidate"])): r for r in loaded["xhard4"][1]}
    rows = violations = 0
    problems: list[str] = []
    for tier in ("xhard1", "xhard2", "xhard3"):
        header = loaded[tier][0]
        for task in {r["task"] for r in loaded[tier][1]}:
            block = header["sampling_config"][task]["decision"]
            mine = _geometry_leaves(block.get(tier, {}))
            top = _geometry_leaves(block.get("xhard4", {}))
            diff = sorted(k for k in set(mine) | set(top) if mine.get(k) != top.get(k))
            if diff:
                violations += 1
                problems.append(f"geometry:{task}/{tier}:{diff[:3]}")
        for row in loaded[tier][1]:
            rows += 1
            mother = mothers[(row["task"], int(row["candidate"]))]["spec"]
            for path in row["spec"].get("layout_paths_hit") or ():
                if not any(seg in path for seg in ("layout.", "path_nodes", "actions.nodes", "slots", "distractors.bins")):
                    continue
                used, parent_value = _get(row["spec"], path), _get(mother, path)
                if path.startswith("objects.distractors.bins."):
                    # D-19：外环弧取自母布局外环集合（位置、朝向逐字不变）
                    if used not in list(_get(mother, "objects.distractors.bins").values()):
                        violations += 1
                        problems.append(f"position:{row['task']}/{tier}/{row['candidate']}:{path}")
                    continue
                if used != parent_value and not (isinstance(used, list) and parent_value[: len(used)] == used):
                    violations += 1
                    problems.append(f"position:{row['task']}/{tier}/{row['candidate']}:{path}")
    ok = violations == 0 and rows > 0
    print(f"V7_PREFIX_GEOMETRY={'PASS' if ok else 'FAIL'} rows={rows} violations={violations}"
          + ("" if ok else f" detail={problems[:6]}"), flush=True)
    return 0 if ok else 1


# ── reset-replay / eval-smoke（GPU）────────────────────────────────────────


def _replay_targets(specs_root: str | None) -> list[dict[str, Any]]:
    """v7 每格 candidate 最小的正式局（13×3 + 16 = 55）→ builder episode 号。"""
    first: dict[tuple[str, str], dict[str, Any]] = {}
    for (task, tier, seed), hit in delivery_index(specs_root).items():
        key = (task, tier)
        if key not in first or hit["row"]["candidate"] < first[key]["candidate"]:
            first[key] = {"task": task, "tier": tier, "seed": seed, "candidate": int(hit["row"]["candidate"]),
                          "builder_episode": hit["builder_episode"]}
    return [first[k] for k in sorted(first, key=lambda k: (_hard_specs().TIERS.index(k[1]), k[0]))]


def cmd_reset_replay(args) -> int:
    """V7_RESET_REPLAY：每格 1 局经评估链 make_env_for_episode + reset，spec_binding 须 injected_mismatch==0、
    layout_drift==0、unused==0，派生局 layout_hit == layout_paths_hit 条数。"""
    import os

    if args.specs_root:
        os.environ[_hard_specs().SPECS_ROOT_ENV] = str(Path(args.specs_root).resolve())
    from robomme_hard.env_record_wrapper import BenchmarkEnvBuilder, TIER_MAX_STEPS, spec_binding

    targets = _replay_targets(args.specs_root)
    if args.limit:
        targets = targets[: args.limit]
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if out_path.exists():
        done = {(r["task"], r["tier"], r["seed"]) for r in map(json.loads, out_path.read_text().splitlines()) if r.get("ok") is not None}
    builders: dict[str, Any] = {}
    for target in targets:
        key = (target["task"], target["tier"], target["seed"])
        if key in done:
            continue
        started = time.time()
        record = dict(target)
        env = None
        try:
            builder = builders.setdefault(target["task"], BenchmarkEnvBuilder(target["task"], dataset="test-hard"))
            identity = builder.resolve_identity(target["builder_episode"])
            assert identity["seed"] == target["seed"] and identity["tier"] == target["tier"], identity
            env = builder.make_env_for_episode(target["builder_episode"], max_steps=TIER_MAX_STEPS[target["tier"]])
            obs, info = env.reset()
            record.update({"binding": spec_binding(env), "identity": identity, "ok": True,
                           "demo_frames": len(obs.get("front_rgb_list", [])) - 1 if isinstance(obs, dict) else None})
        except Exception as exc:  # noqa: BLE001 如实记录
            record.update({"ok": False, "error": f"{type(exc).__name__}: {exc}"[:800]})
        finally:
            if env is not None:
                env.close()
        record["wall_s"] = round(time.time() - started, 1)
        with out_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        print(f"RESET_REPLAY {key} ok={record['ok']} binding={record.get('binding')}", flush=True)
    want = {(t["task"], t["tier"], t["seed"]) for t in targets}
    rows = [r for r in map(json.loads, out_path.read_text().splitlines()) if (r["task"], r["tier"], r["seed"]) in want]
    good = [r for r in rows if r.get("ok")]
    injected = sum(r["binding"]["injected_mismatch"] for r in good)
    drift = sum(r["binding"].get("layout_drift", 0) for r in good)
    unused = sum(r["binding"]["unused"] for r in good)
    hit_bad = sum(1 for r in good if r["binding"].get("layered")
                  and r["binding"].get("layout_hit") != r["binding"].get("layout_paths_expected"))
    replay = sum(1 for r in good if r["binding"].get("mode") == "replay")
    errors = len(rows) - len(good)
    ok = len(rows) == len(targets) and errors == 0 and injected == drift == unused == hit_bad == 0 and replay == len(targets)
    shape = "13x3+16" if len(targets) == 55 else f"cells{len(targets)}"
    print(f"V7_RESET_REPLAY={'PASS' if ok else 'FAIL'} shape={shape} resets={len(rows)} replay={replay} "
          f"injected_mismatch={injected} layout_drift={drift} unused={unused} layout_hit_bad={hit_bad} errors={errors}")
    return 0 if ok else 1


def cmd_eval_smoke(args) -> int:
    """合作者入口：与 scripts/evaluation_hard.py 同样的构建与 max_steps 传法，只跑 1 任务 × 1 档 × 1 局。
    xhard0 局须为导出模式（原生 hard 分支）、回注局须为 replay 且 injected_mismatch==0。"""
    import os

    import numpy as np

    if args.specs_root:
        os.environ[_hard_specs().SPECS_ROOT_ENV] = str(Path(args.specs_root).resolve())
    from robomme_hard.env_record_wrapper import BenchmarkEnvBuilder, TIER_MAX_STEPS, spec_binding

    hs = _hard_specs()
    builder = BenchmarkEnvBuilder(env_id=args.task, dataset="test-hard", action_space="joint_angle", max_steps=1300)
    num = builder.get_episode_num()
    seed, tier = builder.resolve_episode(args.episode)
    env = builder.make_env_for_episode(args.episode, max_steps=TIER_MAX_STEPS[tier])
    obs, info = env.reset()
    binding = spec_binding(env)
    base = np.array([0.0, 0.0, 0.0, -np.pi / 2, 0.0, np.pi / 2, np.pi / 4, 1.0], dtype=np.float32)
    steps, status = 0, "unknown"
    while True:
        obs, reward, terminated, truncated, info = env.step(base)
        steps += 1
        if info is not None and info.get("status") == "error":
            status = "error"
            break
        if terminated or truncated:
            status = info.get("status", "unknown")
            break
        if steps >= args.max_policy_steps:
            status = "smoke_cut"
            break
    env.close()
    if tier == hs.XHARD0:
        mode_ok = binding.get("mode") == "export" and binding.get("spec_kind") == "native-parity/1"
    else:
        mode_ok = binding.get("mode") == "replay"
    expected = 32 if args.task in hs.XHARD4_ONLY else 92
    ok = mode_ok and binding.get("injected_mismatch") == 0 and status != "error" and num == expected
    print(f"HARD_EVAL_SMOKE={'PASS' if ok else 'FAIL'} task={args.task} episode={args.episode} tier={tier} seed={seed} "
          f"episodes={num} max_steps={TIER_MAX_STEPS[tier]} mode={binding.get('mode')} status={status} steps={steps} "
          f"injected_mismatch={binding.get('injected_mismatch')} goal={str(info.get('task_goal'))[:60] if info else None}")
    return 0 if ok else 1


# ── xhard0：reset 层对拍（判定）与策略层对照（只报告）──────────────────────────


_PROBE = r'''
import json, sys, importlib
side, task, src, eps, gpu = sys.argv[1], sys.argv[2], sys.argv[3], json.loads(sys.argv[4]), sys.argv[5]
import os
os.environ["CUDA_VISIBLE_DEVICES"] = gpu
sys.path = [p for p in sys.path if not os.path.isfile(os.path.join(p, "robomme", "__init__.py"))]
sys.path.insert(0, os.path.join(src, "src"))
import numpy as np, gymnasium as gym, hashlib
calls = []
_orig = gym.make
def _make(env_id, **kw):
    calls.append({"env_id": env_id, **{k: v for k, v in kw.items() if k not in ("native_episode_spec", "sampling_config")},
                  "has_sampling_config": "sampling_config" in kw, "has_native_episode_spec": "native_episode_spec" in kw})
    return _orig(env_id, **kw)
gym.make = _make
if side == "official":
    from robomme.env_record_wrapper import BenchmarkEnvBuilder
    assert "robomme_hard" not in sys.modules
    builder = BenchmarkEnvBuilder(task, dataset="test")
else:
    from robomme_hard.env_record_wrapper import BenchmarkEnvBuilder
    builder = BenchmarkEnvBuilder(task, dataset="test-hard")
def digest(x):
    if hasattr(x, "detach"):
        x = x.detach().cpu().numpy()
    if isinstance(x, dict):
        return {k: digest(v) for k, v in sorted(x.items())}
    arr = np.ascontiguousarray(np.asarray(x))
    return hashlib.sha256(arr.tobytes() + str(arr.dtype).encode() + str(arr.shape).encode()).hexdigest()
out = []
for ep in eps:
    calls.clear()
    seed, diff = builder.resolve_episode(ep)
    env = builder.make_env_for_episode(ep, max_steps=1300, include_available_multi_choices=True)
    kw = dict(calls[-1]); make_kw = {k: v for k, v in kw.items()}
    base = _orig(kw["env_id"], **{k: v for k, v in kw.items() if k not in ("env_id", "has_sampling_config", "has_native_episode_spec")})
    base.reset()  # 与评估链一致：seed 已随 gym.make 传入，reset 不另传（用户 2026-09-29 批准每局多 1 次底层 reset）
    pre = digest(base.unwrapped.get_state_dict())
    base.close()
    chain, e = [], env
    while hasattr(e, "env"):
        chain.append(type(e).__name__); e = e.env
    chain.append(type(e.unwrapped).__name__)
    obs, info = env.reset()
    goal = info.get("task_goal"); choices = info.get("available_multi_choices")
    demo = obs.get("front_rgb_list", []) if isinstance(obs, dict) else []
    out.append({"episode": ep, "seed": seed, "difficulty": diff, "make_kwargs": make_kw, "wrapper_chain": chain,
                "pre_demo_state": pre, "task_goal": [str(g) for g in (goal if isinstance(goal, (list, tuple)) else [goal])],
                "choices": json.loads(json.dumps(choices, default=str)) if choices is not None else None,
                "demo_frames": max(len(demo) - 1, 0), "demo_digest": digest(np.stack([np.asarray(f) for f in demo])) if len(demo) else None,
                "post_state": digest(env.unwrapped.get_state_dict())})
    env.close()
print("PROBE_JSON " + json.dumps(out))
'''


def _run_probe(side: str, task: str, src: Path, eps: list[int], gpu: str) -> list[dict[str, Any]]:
    import subprocess

    proc = subprocess.run([sys.executable, "-c", _PROBE, side, task, str(src), json.dumps(eps), gpu],
                          capture_output=True, text=True, cwd=str(REPO))
    line = next((l for l in reversed(proc.stdout.splitlines()) if l.startswith("PROBE_JSON ")), None)
    if proc.returncode != 0 or line is None:
        raise RuntimeError(f"{side}/{task} 探针失败：{proc.stderr[-1500:]}")
    return json.loads(line[len("PROBE_JSON "):])


def cmd_xhard0_reset_parity(args) -> int:
    """XHARD0_RESET_PARITY（D-16）：同卡两进程——官方侧只导入 robomme（dataset="test"，原 episode 号），
    robomme_hard 侧 dataset="test-hard" episode 0～11。确定性层逐位比：gym.make 实参（除 hard 侧不应有的键）、
    包装链类名序列、演示回放前的底层状态（另起底层环境 reset 取 get_state_dict）、seed、task_goal、多选项；
    演示层（演示帧数、演示帧、演示后状态）只报告。"""
    hs = _hard_specs()
    manifest = json.loads(Path(args.manifest).read_text())
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    det_diff, compared, frames_equal, max_frame_diff, first_diff = 0, 0, 0, 0, None
    rows = []
    tasks = [t for t in hs.ALL_TASKS if not args.tasks or t in args.tasks.split(",")]
    for task in tasks:
        episodes = [r["episode"] for r in manifest["rows"] if r["task"] == task]
        official = _run_probe("official", task, Path(args.src_root), episodes, args.gpu)
        hard = _run_probe("hard", task, REPO, list(range(len(episodes))), args.gpu)
        for o, h in zip(official, hard):
            compared += 1
            fields = {
                "seed": o["seed"] == h["seed"],
                "difficulty": o["difficulty"] == "hard" and h["difficulty"] == "xhard0",
                "make_kwargs": o["make_kwargs"] == h["make_kwargs"],
                "wrapper_chain": o["wrapper_chain"] == h["wrapper_chain"],
                "pre_demo_state": o["pre_demo_state"] == h["pre_demo_state"],
                "task_goal": o["task_goal"] == h["task_goal"],
                "choices": o["choices"] == h["choices"],
            }
            bad = [k for k, v in fields.items() if not v]
            det_diff += int(bool(bad))
            if bad and first_diff is None:
                first_diff = f"{task}/ep{o['episode']}:{bad}"
            frames_equal += int(o["demo_frames"] == h["demo_frames"])
            max_frame_diff = max(max_frame_diff, abs(o["demo_frames"] - h["demo_frames"]))
            rows.append({"task": task, "source_episode": o["episode"], "hard_episode": h["episode"], "det_bad": bad,
                         "demo_frames": [o["demo_frames"], h["demo_frames"]],
                         "demo_equal": o["demo_digest"] == h["demo_digest"], "post_equal": o["post_state"] == h["post_state"]})
        print(f"XHARD0_RESET_TASK {task} compared={len(official)} det_bad={sum(bool(r['det_bad']) for r in rows if r['task'] == task)}",
              flush=True)
    (out / "xhard0-reset-parity.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    ok = det_diff == 0 and compared == 16 * hs.XHARD0_PER_TASK
    print(f"XHARD0_RESET_PARITY={'PASS' if ok else 'FAIL'} shape=16x1x12 compared={compared} det_diff={det_diff} "
          f"first_det_diff={first_diff or '-'}")
    print(f"XHARD0_DEMO_DIFF=INFO frames_equal={frames_equal} max_frame_diff={max_frame_diff} "
          f"demo_equal={sum(r['demo_equal'] for r in rows)} post_equal={sum(r['post_equal'] for r in rows)}")
    return 0 if ok else 1


def _final_records(path: Path, policy: str) -> dict[tuple[str, int], dict[str, Any]]:
    """终态记录：SimpleMemVLA 读 results-shard*.jsonl，MME-VLA 读 episodes.jsonl；同一局多行取最后一个终态行。"""
    files = sorted(path.rglob("results-shard*.jsonl")) if policy == "simplememvla" else sorted(path.rglob("episodes.jsonl"))
    out: dict[tuple[str, int], dict[str, Any]] = {}
    for file in files:
        for text in file.read_text().splitlines():
            if text.strip():
                r = json.loads(text)
                if r.get("status") is not None:
                    out[(r.get("task") or r.get("env_id"), int(r["episode"]))] = r
    return out


def cmd_xhard0_eval_parity(args) -> int:
    """XHARD0_EVAL_PARITY（只报告，D-16）：官方路线（原 episode 号）经清单映射到 seed，与 v7 评估的 xhard0 局按
    (task, seed) 对齐，列终态与步数差异；缺失或多余是数据完整性问题，报错。"""
    manifest = json.loads(Path(args.manifest).read_text())
    seed_of = {(r["task"], r["episode"]): r["seed"] for r in manifest["rows"]}
    official = {(t, seed_of[(t, e)]): r for (t, e), r in _final_records(Path(args.official), args.policy).items()
                if (t, e) in seed_of}
    hard = {}
    for (t, _e), r in _final_records(Path(args.hard), args.policy).items():
        ident = r.get("identity") or {}
        if (ident.get("tier") or r.get("tier")) == "xhard0":
            hard[(t, int(ident.get("seed", r.get("seed"))))] = r
    if set(official) != set(hard) or len(official) != 192:
        raise SystemExit(f"xhard0 对齐失败：官方 {len(official)}、v7 {len(hard)}，差集 {len(set(official) ^ set(hard))}")
    diffs = [{"task": k[0], "seed": k[1], "official": [official[k]["status"], official[k].get("steps")],
              "hard": [hard[k]["status"], hard[k].get("steps")]} for k in sorted(official)
             if official[k]["status"] != hard[k]["status"] or official[k].get("steps") != hard[k].get("steps")]
    Path(args.out).write_text("".join(json.dumps(d, ensure_ascii=False) + "\n" for d in diffs))
    status_diff = sum(d["official"][0] != d["hard"][0] for d in diffs)
    steps_diff = sum(d["official"][1] != d["hard"][1] for d in diffs)
    print(f"XHARD0_EVAL_PARITY=INFO policy={args.policy} compared={len(official)} status_diff={status_diff} steps_diff={steps_diff}")
    return 0


def cmd_step_headroom(args) -> int:
    """V7_STEP_HEADROOM（§1.8、B4）：交付清单逐局 h5 执行步数 = 总帧 − ``info/is_video_demo`` 帧，按格与
    ``TIER_MAX_STEPS`` 的 90% 比；超 90% 的档给出 B4 上调值（该档实测最大执行步数 × 1.25 向上取整到百）。"""
    import h5py

    hs = _hard_specs()
    delivery = Path(args.delivery)
    rows = json.loads(delivery.read_text())["rows"]
    per_cell: dict[tuple[str, str], list[int]] = collections.defaultdict(list)
    for row in rows:
        path = delivery.parent / row["path"]
        with h5py.File(path, "r") as handle:
            episode = handle[list(handle.keys())[0]]
            steps = [k for k in episode if k.startswith("timestep_")]
            demo = sum(bool(episode[k]["info/is_video_demo"][()]) for k in steps)
        per_cell[(row["task"], row["tier"])].append(len(steps) - demo)
    over, worst = [], {}
    for (task, tier), values in sorted(per_cell.items()):
        cap = hs.TIER_MAX_STEPS[tier]
        worst[tier] = max(worst.get(tier, 0), max(values))
        if max(values) > 0.9 * cap:
            over.append({"task": task, "tier": tier, "max_exec": max(values), "cap": cap})
    proposal = {}
    for tier in {o["tier"] for o in over}:
        proposal[tier] = int(math.ceil(worst[tier] * 1.25 / 100.0) * 100)
    report = {"cells": len(per_cell), "worst_by_tier": worst, "over_90pct": over, "b4_proposal": proposal,
              "per_cell_max": {f"{t}/{d}": max(v) for (t, d), v in per_cell.items()}}
    if args.out:
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n")
    label = "INFO" if args.info else ("PASS" if not over else "FAIL")
    print(f"V7_STEP_HEADROOM={label} cells={len(per_cell)} over_90pct={len(over)} "
          f"worst={ {t: f'{w}/{hs.TIER_MAX_STEPS[t]}' for t, w in sorted(worst.items())} }"
          + (f" b4_proposal={proposal}" if proposal else ""))
    return 0 if label != "FAIL" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    rr = sub.add_parser("reset-replay")
    rr.add_argument("--out", required=True)
    rr.add_argument("--limit", type=int, default=0)
    rr.add_argument("--specs-root", default=None, help="v7 规格根（换包前经 ROBOMME_HARD_SPECS_ROOT 读）")
    rr.set_defaults(func=cmd_reset_replay)
    ls = sub.add_parser("layout-shared")
    ls.add_argument("--specs-root", required=True)
    ls.set_defaults(func=cmd_layout_shared)
    pg = sub.add_parser("prefix-geometry")
    pg.add_argument("--specs-root", required=True)
    pg.set_defaults(func=cmd_prefix_geometry)
    ev = sub.add_parser("eval-smoke")
    ev.add_argument("--task", default="BinFill")
    ev.add_argument("--episode", type=int, default=0)
    ev.add_argument("--max-policy-steps", type=int, default=50)
    ev.add_argument("--specs-root", default=None)
    ev.set_defaults(func=cmd_eval_smoke)
    x0 = sub.add_parser("xhard0-reset-parity")
    x0.add_argument("--src-root", required=True, help="官方 1fadc0ec worktree（只导入其 robomme）")
    x0.add_argument("--manifest", default=str(REPO / "scripts" / "configs" / "newtask-v7" / "xhard0_manifest.json"))
    x0.add_argument("--gpu", default="0")
    x0.add_argument("--tasks", default=None)
    x0.add_argument("--out", required=True)
    x0.set_defaults(func=cmd_xhard0_reset_parity)
    xe = sub.add_parser("xhard0-eval-parity")
    xe.add_argument("--official", required=True)
    xe.add_argument("--hard", required=True)
    xe.add_argument("--policy", required=True, choices=("simplememvla", "mmevla"))
    xe.add_argument("--manifest", default=str(REPO / "scripts" / "configs" / "newtask-v7" / "xhard0_manifest.json"))
    xe.add_argument("--out", required=True)
    xe.set_defaults(func=cmd_xhard0_eval_parity)
    sh = sub.add_parser("step-headroom")
    sh.add_argument("--delivery", required=True, help="gen1 的 delivery.json（行里 path 相对其所在目录）")
    sh.add_argument("--out", default=None)
    sh.add_argument("--info", action="store_true", help="冒烟外推只报告（阶段 3），不判 PASS/FAIL")
    sh.set_defaults(func=cmd_step_headroom)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
