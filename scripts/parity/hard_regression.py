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
* ``env-digest``（GPU，v7.5eval）：身份逐层摘要 + 原始数组 + 测速 → ``ENV_DIGEST_DONE``、``ENV_SPEED=INFO``。
* ``env-digest-compare``（纯 CPU，v7.5eval）：两格逐层对拍，只报告 → ``ENV_DIGEST_PARITY``。

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
    rows = []
    tasks = [t for t in hs.ALL_TASKS if not args.tasks or t in args.tasks.split(",")]
    for task in tasks:
        episodes = [r["episode"] for r in manifest["rows"] if r["task"] == task]
        official = _run_probe("official", task, Path(args.src_root), episodes, args.gpu)
        hard = _run_probe("hard", task, REPO, list(range(len(episodes))), args.gpu)
        for o, h in zip(official, hard):
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
            # 演示前状态逐名不等、但每类 actor 的状态值集合相等 ⇒ 只是命名不同（如 robomme_hard BUS 的 F3 左右按钮改名），
            # 场景逐位相同：单列 name_only，不计 det_diff（v7 方案 D-16 的实现细节，写进留档）
            name_only = bad == ["pre_demo_state"] and _name_agnostic(o["pre_demo_state"]) == _name_agnostic(h["pre_demo_state"])
            rows.append({"task": task, "source_episode": o["episode"], "hard_episode": h["episode"],
                         "det_bad": [] if name_only else bad, "name_only": name_only,
                         "demo_frames": [o["demo_frames"], h["demo_frames"]],
                         "demo_equal": o["demo_digest"] == h["demo_digest"], "post_equal": o["post_state"] == h["post_state"],
                         "pre_state": [o["pre_demo_state"], h["pre_demo_state"]]})
        mine = [r for r in rows if r["task"] == task]
        print(f"XHARD0_RESET_TASK {task} compared={len(mine)} det_bad={sum(bool(r['det_bad']) for r in mine)} "
              f"name_only={sum(r['name_only'] for r in mine)}", flush=True)
    if args.merge_with:
        rows += [r for r in map(json.loads, Path(args.merge_with).read_text().splitlines()) if r["task"] not in tasks]
    (out / args.report_name).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    return _xhard0_reset_verdict(rows, hs.XHARD0_PER_TASK)


def _name_agnostic(state: Any) -> Any:
    """状态摘要按类（actors／articulations…）取值的有序多重集，忽略实体名字。"""
    if isinstance(state, dict) and all(isinstance(v, dict) for v in state.values()):
        return {section: sorted(json.dumps(v, sort_keys=True) for v in items.values()) for section, items in state.items()}
    return state


def _xhard0_reset_verdict(rows: list[dict[str, Any]], per_task: int) -> int:
    det = [r for r in rows if r["det_bad"]]
    first = f"{det[0]['task']}/ep{det[0]['source_episode']}:{det[0]['det_bad']}" if det else "-"
    name_only = [r for r in rows if r.get("name_only")]
    ok = not det and len(rows) == 16 * per_task
    print(f"XHARD0_RESET_PARITY={'PASS' if ok else 'FAIL'} shape=16x1x12 compared={len(rows)} det_diff={len(det)} "
          f"name_only={len(name_only)} first_det_diff={first}"
          + (f" name_only_tasks={sorted({r['task'] for r in name_only})}" if name_only else ""))
    print(f"XHARD0_DEMO_DIFF=INFO frames_equal={sum(r['demo_frames'][0] == r['demo_frames'][1] for r in rows)} "
          f"max_frame_diff={max((abs(r['demo_frames'][0] - r['demo_frames'][1]) for r in rows), default=0)} "
          f"demo_equal={sum(r['demo_equal'] for r in rows)} post_equal={sum(r['post_equal'] for r in rows)}")
    return 0 if ok else 1


#: 两策略的逐局结果文件名：SimpleMemVLA 官方路线 episodes-shard*of10.jsonl、v7 路线 results-r<轮>-shard*of10.jsonl；
#: MME-VLA 两路线都是 episodes.jsonl
_RESULT_GLOBS = {"simplememvla": ("episodes-shard*.jsonl", "results-r*-shard*.jsonl", "results-shard*.jsonl"),
                 "mmevla": ("episodes.jsonl",)}
_FINAL_STATUS = ("success", "fail", "timeout")


def _final_records(paths: list[Path], policy: str) -> list[dict[str, Any]]:
    """逐局终态记录：``paths`` 可以是文件或目录（目录按策略的文件名递归找）。同一局多行时取最后一个终态行，
    没有终态行的取最后一行（如 error）。局以 (task, seed 或 episode 号) 区分。"""
    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            for pattern in _RESULT_GLOBS[policy]:
                files.extend(sorted(path.rglob(pattern)))
        else:
            files.append(path)
    out: dict[tuple, dict[str, Any]] = {}
    for file in files:
        for text in file.read_text().splitlines():
            if not text.strip():
                continue
            r = json.loads(text)
            if r.get("status") is None:
                continue
            ident = r.get("identity") or {}
            key = (r.get("task") or r.get("env_id"), ident.get("seed", r.get("seed")),
                   r.get("episode", r.get("source_episode")))
            if key in out and out[key]["status"] in _FINAL_STATUS and r["status"] not in _FINAL_STATUS:
                continue
            out[key] = r
    return list(out.values())


def cmd_xhard0_eval_parity(args) -> int:
    """XHARD0_EVAL_PARITY（只报告，D-16）：官方路线与 v7 评估的 xhard0 局按 (task, seed) 对齐，列终态与步数差异；
    官方记录不带 seed 时经清单由原 episode 号映射。缺失或多余是数据完整性问题，报错。"""
    manifest = json.loads(Path(args.manifest).read_text())
    seed_of = {(r["task"], r["episode"]): r["seed"] for r in manifest["rows"]}
    official = {}
    for r in _final_records([Path(p) for p in args.official], args.policy):
        task = r.get("task") or r.get("env_id")
        seed = r.get("seed")
        if seed is None:
            seed = seed_of.get((task, int(r.get("source_episode", r.get("episode", -1)))))
        if seed is not None and (task, int(seed)) in {(t, s) for (t, _e), s in seed_of.items()}:
            official[(task, int(seed))] = r
    hard = {}
    for r in _final_records([Path(p) for p in args.hard], args.policy):
        ident = r.get("identity") or {}
        if (ident.get("tier") or r.get("tier")) == "xhard0":
            hard[(r["task"], int(ident.get("seed", r.get("seed"))))] = r
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
    lengths: dict[tuple[str, str], list[tuple[int, int]]] = collections.defaultdict(list)
    for row in rows:
        path = delivery.parent / row["path"]
        with h5py.File(path, "r") as handle:
            episode = handle[list(handle.keys())[0]]
            steps = [k for k in episode if k.startswith("timestep_")]
            demo = sum(bool(episode[k]["info/is_video_demo"][()]) for k in steps)
        per_cell[(row["task"], row["tier"])].append(len(steps) - demo)
        lengths[(row["task"], row["tier"])].append((demo, len(steps) - demo))
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
              "per_cell_max": {f"{t}/{d}": max(v) for (t, d), v in per_cell.items()},
              # README 第 3 节 episode 长度表：每格 演示段 / 执行段 / 全部 的均值（四舍五入到整数）
              "per_cell_mean": {f"{t}/{d}": {"demo": round(sum(a for a, _ in v) / len(v)),
                                             "exec": round(sum(b for _, b in v) / len(v)),
                                             "total": round(sum(a + b for a, b in v) / len(v)), "n": len(v)}
                                for (t, d), v in lengths.items()}}
    if args.out:
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n")
    label = "INFO" if args.info else ("PASS" if not over else "FAIL")
    print(f"V7_STEP_HEADROOM={label} cells={len(per_cell)} over_90pct={len(over)} "
          f"worst={ {t: f'{w}/{hs.TIER_MAX_STEPS[t]}' for t, w in sorted(worst.items())} }"
          + (f" b4_proposal={proposal}" if proposal else ""))
    return 0 if label != "FAIL" else 1


# ── v7.5eval 环境检测（env-digest / env-digest-compare）───────────────────────
# 0929-v7.5eval-restructure-plan.md §3.2 第 1 步第 1 项、2.1、§4 测速、口径 9。
# 每个身份逐层存摘要（rows.jsonl）与原始数组（每身份一个 npz，np.savez_compressed 无损），对拍时摘要不等再读原始数组算差值。

#: 层的固定顺序（first_diff 取这个顺序里第一个不等的层）
ENV_DIGEST_LAYERS = ("identity", "pre_demo_state", "demo_frames", "reset_obs", "post_demo_state",
                     "step_frames", "step_obs", "step_state", "step_status")
#: 状态类层：键是 ``<分区>/<实体名>``，可做「仅改名」判定
_ENV_STATE_LAYERS = ("pre_demo_state", "post_demo_state", "step_state")
#: 数值观测层：摘要不等时算最大绝对差（单列 obs_max_abs）
_ENV_NUMERIC_OBS_LAYERS = ("reset_obs", "step_obs")
#: 两个摇杆任务动作只有 7 维
_STICK_TASKS = ("PatternLock", "RouteStick")
#: 未采到的计时段一律写这个字符串，不填 0
UNCOLLECTED = "uncollected"
#: 计时字段 → 实际包到的调用（写进每行 timing_notes，便于核对口径）
ENV_TIMING_NOTES = {
    "proc.import_numpy_s": "import numpy",
    "proc.import_torch_s": "import torch",
    "proc.import_sapien_s": "import sapien",
    "proc.import_mani_skill_s": "import mani_skill + mani_skill.envs",
    "proc.import_robomme_hard_s": "import robomme_hard.env_record_wrapper（连带注册 16 个任务类）",
    "proc.spawn_to_worker_s": "父进程 Popen 前 time.time() → 子进程进入 worker 函数（解释器启动 + 本文件导入）",
    "proc.first_vulkan_s": "进程内第一次 BaseEnv._setup_scene（含首个 sapien.render.RenderSystem 即首次 Vulkan 设备创建；"
                           "另含 physx 场景构造，无法单独拆出）",
    "make_env_s": "BenchmarkEnvBuilder.make_env_for_episode 整体",
    "gym_make_s": "make_env_for_episode 内 gymnasium.make（任务类 __init__，含 BaseEnv 构造期 reset(reconfigure=True)）",
    "wrapper_chain_s": "make_env_s − gym_make_s（DemonstrationWrapper / FailAwareWrapper 等包装链构造）",
    "eval_reset_s": "评估实例 env.reset()（FailAwareWrapper 起整条链）",
    "inner_reset_s": "eval reset 期间 mani_skill BaseEnv.reset 最外层调用累计",
    "initialize_episode_s": "eval reset 期间任务类 _initialize_episode 累计",
    "demo_s": "eval_reset_s − inner_reset_s（演示轨迹生成 + 初始一步）",
    "demo_s_per_frame": "demo_s / 演示帧数",
    "choices_s": "reset 后直接调 get_vqa_options 取多选项（评估实例不带 include_available_multi_choices）",
    "step_s": "每步 env.step() 墙钟（列表）",
    "step_physics_s": "每步内 BaseEnv._step_action 累计（物理步 + 控制器）",
    "step_get_obs_s": "每步内 BaseEnv.get_obs 累计（含传感器渲染）",
    "close_s": "env.close()",
    "probe_make_s": "演示前状态探针：另建底层环境 gymnasium.make（原始实参）",
    "probe_reset_s": "演示前状态探针：底层环境 reset()",
    "probe_close_s": "演示前状态探针：底层环境 close()",
    "class_timers": "按阶段（probe/make/reset/step/close）累计的类级计时：16 任务类 × {_load_agent,_load_scene,"
                    "_initialize_episode}（口径 9 批准清单）+ BaseEnv.{_setup_scene,_setup_sensors,_load_lighting,"
                    "_reconfigure,reset,_step_action,get_obs}；只计时、不改参数与返回值、只在本进程内",
}


def _env_digest(x: Any) -> str:
    """与 ``_PROBE.digest`` 同一口径：数组字节 + dtype + shape 的 sha256。"""
    import hashlib

    import numpy as np

    arr = np.ascontiguousarray(np.asarray(x))
    return hashlib.sha256(arr.tobytes() + str(arr.dtype).encode() + str(arr.shape).encode()).hexdigest()


def _env_json_digest(value: Any) -> str:
    import hashlib

    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def _env_layer(keys: dict[str, str]) -> dict[str, Any]:
    """一层的摘要：逐键摘要 + 整层摘要（逐键摘要字典的 json sha256）。"""
    return {"digest": _env_json_digest(keys), "keys": dict(sorted(keys.items()))}


def _env_np(x: Any):
    """torch 张量 / 列表 → numpy（不改 dtype）。"""
    import numpy as np

    if hasattr(x, "detach"):
        x = x.detach().cpu().numpy()
    return np.asarray(x)


def _env_flatten(tree: Any, prefix: str = "") -> dict[str, Any]:
    """嵌套状态字典（get_state_dict）→ ``{"actors/<名>": ndarray, ...}``。"""
    out: dict[str, Any] = {}
    if isinstance(tree, dict):
        for key, value in sorted(tree.items()):
            out.update(_env_flatten(value, f"{prefix}/{key}" if prefix else str(key)))
    else:
        out[prefix] = _env_np(tree)
    return out


def _env_identity_key(row: dict[str, Any]) -> str:
    return f"{row['task']}/ep{row['source_episode']}/seed{row['seed']}/b{row['builder_episode']}"


def _env_rng_probe() -> dict[str, str]:
    """全局随机状态 sha：torch CPU 生成器、numpy 全局 RandomState、python random（不碰 CUDA 生成器，免得提前初始化 CUDA）。"""
    import hashlib
    import random

    import numpy as np
    import torch

    kind, keys, pos, has_gauss, cached = np.random.get_state()
    np_bytes = np.asarray(keys).tobytes() + f"{kind}|{pos}|{has_gauss}|{cached!r}".encode()
    return {"torch": hashlib.sha256(torch.random.get_rng_state().numpy().tobytes()).hexdigest(),
            "numpy": hashlib.sha256(np_bytes).hexdigest(),
            "python": hashlib.sha256(repr(random.getstate()).encode()).hexdigest()}


def _env_rng_save():
    import random

    import numpy as np
    import torch

    return torch.random.get_rng_state(), np.random.get_state(), random.getstate()


def _env_rng_restore(saved) -> None:
    import random

    import numpy as np
    import torch

    torch.random.set_rng_state(saved[0])
    np.random.set_state(saved[1])
    random.setstate(saved[2])


class _EnvTimerHub:
    """类级计时：按当前阶段累计秒数与调用次数；同一标签递归调用只计最外层。"""

    def __init__(self) -> None:
        self.phase = "init"
        self.buckets: dict[str, dict[str, float]] = collections.defaultdict(lambda: collections.defaultdict(float))
        self.counts: dict[str, dict[str, int]] = collections.defaultdict(lambda: collections.defaultdict(int))
        self.first: dict[str, float] = {}
        self.depth: dict[str, int] = collections.defaultdict(int)
        self.wrapped: list[str] = []
        self.missing: list[str] = []

    def wrap(self, cls: type, name: str, label: str) -> None:
        import functools

        orig = cls.__dict__.get(name)
        if orig is None:
            self.missing.append(label)
            return
        hub = self

        @functools.wraps(orig)
        def timed(*a, **k):
            hub.depth[label] += 1
            started = time.perf_counter()
            try:
                return orig(*a, **k)
            finally:
                hub.depth[label] -= 1
                if hub.depth[label] == 0:
                    dt = time.perf_counter() - started
                    hub.buckets[hub.phase][label] += dt
                    hub.counts[hub.phase][label] += 1
                    hub.first.setdefault(label, dt)

        setattr(cls, name, timed)
        self.wrapped.append(label)

    def total(self, phase: str, label: str) -> float | str:
        return round(self.buckets[phase][label], 6) if self.counts[phase].get(label) else UNCOLLECTED

    def snapshot(self, phase: str) -> dict[str, float]:
        return dict(self.buckets[phase])

    def take(self, phase: str) -> dict[str, Any]:
        return {"s": {k: round(v, 6) for k, v in sorted(self.buckets[phase].items())},
                "n": dict(sorted(self.counts[phase].items()))}


def _env_install_timers(tasks) -> _EnvTimerHub:
    """口径 9：16 任务类各自的 _load_agent/_load_scene/_initialize_episode（48 个）+ BaseEnv 几个方法；只在本进程内。"""
    from mani_skill.envs.sapien_env import BaseEnv
    from mani_skill.utils.registration import REGISTERED_ENVS

    hub = _EnvTimerHub()
    for task in tasks:
        cls = REGISTERED_ENVS[task].cls
        for name in ("_load_agent", "_load_scene", "_initialize_episode"):
            hub.wrap(cls, name, f"{task}.{name}")
    for name in ("_setup_scene", "_setup_sensors", "_load_lighting", "_reconfigure", "reset", "_step_action", "get_obs"):
        hub.wrap(BaseEnv, name, f"BaseEnv.{name}")
    return hub


def _env_fs_type(path: str) -> dict[str, str]:
    """路径所在挂载点与文件系统类型（区分 NVMe / NFS 介质）。"""
    best = ("", "?", "?")
    try:
        for line in Path("/proc/mounts").read_text().splitlines():
            dev, mnt, fstype = line.split()[:3]
            if (path == mnt or path.startswith(mnt.rstrip("/") + "/")) and len(mnt) > len(best[0]):
                best = (mnt, fstype, dev)
    except OSError:
        pass
    return {"path": path, "mount": best[0], "fstype": best[1], "device": best[2]}


def _env_host_info() -> dict[str, Any]:
    """主机、GPU（按 CUDA_VISIBLE_DEVICES 对到 nvidia-smi 一次性查询，不采样）、CPU、affinity、包版本、代码与 venv 介质。"""
    import importlib.metadata as md
    import os
    import platform
    import socket
    import subprocess

    visible = os.environ.get("CUDA_VISIBLE_DEVICES")
    gpu: dict[str, Any] = {"cuda_visible_devices": visible}
    try:
        text = subprocess.run(["nvidia-smi", "--query-gpu=index,uuid,name,driver_version", "--format=csv,noheader"],
                              capture_output=True, text=True, timeout=30).stdout
        cards = [dict(zip(("index", "uuid", "name", "driver"), (c.strip() for c in l.split(",")))) for l in text.splitlines() if l.strip()]
        want = (visible or "0").split(",")[0].strip()
        hit = next((c for c in cards if want in (c["index"], c["uuid"])), None)
        gpu.update(hit or {"name": UNCOLLECTED, "uuid": UNCOLLECTED, "driver": UNCOLLECTED})
    except (OSError, subprocess.SubprocessError):
        gpu.update({"name": UNCOLLECTED, "uuid": UNCOLLECTED, "driver": UNCOLLECTED})
    cpu = UNCOLLECTED
    try:
        cpu = next(l.split(":", 1)[1].strip() for l in Path("/proc/cpuinfo").read_text().splitlines() if l.startswith("model name"))
    except (OSError, StopIteration):
        pass
    versions = {}
    for pkg in ("torch", "sapien", "mani_skill", "numpy", "gymnasium"):
        try:
            versions[pkg] = md.version(pkg)
        except md.PackageNotFoundError:
            versions[pkg] = UNCOLLECTED
    return {"host": socket.gethostname(), "gpu": gpu, "cpu_model": cpu, "affinity_cores": len(os.sched_getaffinity(0)),
            "python": platform.python_version(), "versions": versions,
            "code_medium": _env_fs_type(str(REPO)), "venv_medium": _env_fs_type(sys.prefix)}


def _env_stack(values: list, name: str, arrays: dict[str, Any], keys: dict[str, str]) -> None:
    """逐元素转 numpy 后 stack，存进 arrays 并记摘要；参差不齐时退化为逐元素摘要的 json 摘要（不进 npz）。"""
    import numpy as np

    try:
        arr = np.stack([_env_np(v) for v in values]) if len(values) else np.zeros((0,))
    except (ValueError, TypeError):
        keys[name] = _env_json_digest([_env_digest(_env_np(v)) if v is not None else None for v in values])
        return
    arrays[name] = arr
    keys[name] = _env_digest(arr)


def _env_digest_one(ident: dict[str, Any], builder, hub: _EnvTimerHub, fixed_steps: int, npz_path: Path) -> dict[str, Any]:
    """单个身份：演示前状态探针 → make_env → reset → 取多选项 → 固定动作 N 步 → close；逐层摘要 + 原始数组。"""
    import gymnasium as gym
    import numpy as np

    from robomme_hard.env_record_wrapper import TIER_MAX_STEPS
    from robomme_hard.robomme_env.utils.vqa_options import get_vqa_options

    task = ident["task"]
    arrays: dict[str, Any] = {}
    layers: dict[str, dict[str, str]] = {name: {} for name in ENV_DIGEST_LAYERS}
    timing: dict[str, Any] = {}
    rng: dict[str, Any] = {}
    resolved = builder.resolve_identity(int(ident["builder_episode"]))
    if int(resolved["seed"]) != int(ident["seed"]) or int(resolved.get("source_episode", -1)) != int(ident["source_episode"]):
        raise RuntimeError(f"身份不符：输入 {ident}，builder {resolved}")
    seed, tier = builder.resolve_episode(int(ident["builder_episode"]))

    calls: list[tuple[str, dict[str, Any]]] = []
    orig_make = gym.make

    def make_spy(env_id, **kw):
        started = time.perf_counter()
        try:
            return orig_make(env_id, **kw)
        finally:
            calls.append((env_id, kw))
            timing["gym_make_s"] = round(time.perf_counter() - started, 6)

    # ① 与 _PROBE 同序：先经 builder 建评估实例（顺带截获 gym.make 实参），再用同一实参另建底层环境 reset 取演示前状态，
    #    最后才 reset 评估实例。探针前后保存/恢复全局随机状态，使探针对评估实例的全局随机流不可见。
    rng["before_make"] = _env_rng_probe()
    hub.phase = "make"
    gym.make = make_spy
    started = time.perf_counter()
    try:
        env = builder.make_env_for_episode(int(ident["builder_episode"]), max_steps=TIER_MAX_STEPS[tier])
    finally:
        gym.make = orig_make
    timing["make_env_s"] = round(time.perf_counter() - started, 6)
    timing.setdefault("gym_make_s", UNCOLLECTED)
    timing["wrapper_chain_s"] = (round(timing["make_env_s"] - timing["gym_make_s"], 6)
                                 if timing["gym_make_s"] != UNCOLLECTED else UNCOLLECTED)
    rng["after_make"] = _env_rng_probe()
    env_id, make_kw = calls[-1]

    saved = _env_rng_save()
    hub.phase = "probe"
    started = time.perf_counter()
    base = orig_make(env_id, **make_kw)
    timing["probe_make_s"] = round(time.perf_counter() - started, 6)
    started = time.perf_counter()
    base.reset()  # 与 _PROBE 一致：seed 已随 gym.make 传入，reset 不另传（用户 2026-09-29 批准每局多 1 次底层 reset）
    timing["probe_reset_s"] = round(time.perf_counter() - started, 6)
    pre = _env_flatten(base.unwrapped.get_state_dict())
    started = time.perf_counter()
    base.close()
    timing["probe_close_s"] = round(time.perf_counter() - started, 6)
    del base
    _env_rng_restore(saved)
    for key, value in pre.items():
        arrays[f"pre_demo_state/{key}"] = value
        layers["pre_demo_state"][key] = _env_digest(value)

    chain, e = [], env
    while hasattr(e, "env"):
        chain.append(type(e).__name__)
        e = e.env
    chain.append(type(e.unwrapped).__name__)
    big = {k: _env_json_digest(v) for k, v in make_kw.items() if k in ("native_episode_spec", "sampling_config")}
    small = {k: v for k, v in make_kw.items() if k not in big}

    # ② 评估实例 reset（演示生成在内）
    rng["before_reset"] = _env_rng_probe()
    hub.phase = "reset"
    started = time.perf_counter()
    obs, info = env.reset()
    timing["eval_reset_s"] = round(time.perf_counter() - started, 6)
    rng["after_reset"] = _env_rng_probe()
    timing["inner_reset_s"] = hub.total("reset", "BaseEnv.reset")
    timing["inner_reset_calls"] = hub.counts["reset"].get("BaseEnv.reset", 0)
    timing["initialize_episode_s"] = hub.total("reset", f"{task}._initialize_episode")
    timing["demo_s"] = (round(timing["eval_reset_s"] - timing["inner_reset_s"], 6)
                        if timing["inner_reset_s"] != UNCOLLECTED else UNCOLLECTED)
    post = _env_flatten(env.unwrapped.get_state_dict())
    for key, value in post.items():
        arrays[f"post_demo_state/{key}"] = value
        layers["post_demo_state"][key] = _env_digest(value)
    obs = obs if isinstance(obs, dict) else {}
    front, wrist = list(obs.get("front_rgb_list", [])), list(obs.get("wrist_rgb_list", []))
    demo_frames = max(len(front) - 1, 0)
    timing["demo_frames"] = demo_frames
    timing["demo_s_per_frame"] = (round(timing["demo_s"] / demo_frames, 6)
                                  if demo_frames and timing["demo_s"] != UNCOLLECTED else UNCOLLECTED)
    demo_arrays: dict[str, Any] = {}
    reset_arrays: dict[str, Any] = {}
    for stream, frames in (("front", front), ("wrist", wrist)):
        # 演示帧 = 列表去掉最后一个元素；最后一个元素是初始帧，归 reset_obs 层
        _env_stack(frames[:-1], stream, demo_arrays, layers["demo_frames"])
        if frames:
            reset_arrays[f"{stream}_init"] = _env_np(frames[-1])
            layers["reset_obs"][f"{stream}_init"] = _env_digest(reset_arrays[f"{stream}_init"])
    for key, values in sorted(obs.items()):
        if key not in ("front_rgb_list", "wrist_rgb_list"):
            _env_stack(list(values), key, reset_arrays, layers["reset_obs"])
    arrays.update({f"demo_frames/{k}": v for k, v in demo_arrays.items()})
    arrays.update({f"reset_obs/{k}": v for k, v in reset_arrays.items()})

    # ③ 多选项：评估实例不开 include_available_multi_choices（与评估一致），reset 后直接调同一函数取一次
    demo_wrapper = env
    while not hasattr(demo_wrapper, "include_available_multi_choices") and hasattr(demo_wrapper, "env"):
        demo_wrapper = demo_wrapper.env
    hub.phase = "choices"
    started = time.perf_counter()
    try:
        raw = get_vqa_options(demo_wrapper, None, {"obj": None, "name": None, "seg_id": None}, task)
        choices = [{"label": o.get("label"), "action": o.get("action", "Unknown"), "need_parameter": bool(o.get("available"))}
                   for o in raw]
    except Exception as exc:  # noqa: BLE001 如实记录
        # 只记异常类型名：消息里可能带对象地址，进摘要会造成假差异；完整消息另存 choices_error_message（不进摘要）
        choices = {"error": type(exc).__name__}
        timing["choices_error_message"] = f"{exc}"[:300]
    timing["choices_s"] = round(time.perf_counter() - started, 6)
    rng["after_choices"] = _env_rng_probe()
    goal = info.get("task_goal") if isinstance(info, dict) else None
    identity_fields = {
        "seed": int(seed), "tier": tier, "resolve_identity": resolved, "make_env_id": env_id,
        "make_kwargs": json.loads(json.dumps(small, default=str)), "make_kwargs_big_sha256": big,
        "wrapper_chain": chain, "task_goal": [str(g) for g in (goal if isinstance(goal, (list, tuple)) else [goal])],
        "available_multi_choices": json.loads(json.dumps(choices, default=str)),
    }
    layers["identity"] = {k: _env_json_digest(v) for k, v in identity_fields.items()}

    # ④ 固定动作 N 步：动作 = reset 返回的最后一个关节状态（7 维）+ 夹爪 1.0（摇杆任务只有 7 维），与 eval-smoke 同为「原地保持」
    joint = np.asarray(_env_np(obs["joint_state_list"][-1]), dtype=np.float64).reshape(-1)[:7]
    action = joint if task in _STICK_TASKS else np.concatenate([joint, [1.0]])
    step_rows: dict[str, list] = collections.defaultdict(list)
    statuses, step_s, physics_s, get_obs_s = [], [], [], []
    hub.phase = "step"
    for _ in range(fixed_steps):
        before = hub.snapshot("step")
        started = time.perf_counter()
        obs_t, reward, terminated, truncated, info_t = env.step(action.copy())
        step_s.append(round(time.perf_counter() - started, 6))
        after = hub.snapshot("step")
        physics_s.append(round(after.get("BaseEnv._step_action", 0.0) - before.get("BaseEnv._step_action", 0.0), 6))
        get_obs_s.append(round(after.get("BaseEnv.get_obs", 0.0) - before.get("BaseEnv.get_obs", 0.0), 6))
        status = (info_t or {}).get("status")
        statuses.append({"status": status, "terminated": bool(_env_np(terminated).any()), "truncated": bool(_env_np(truncated).any()),
                         "n_elems": len((obs_t or {}).get("front_rgb_list", []) or []),
                         "error": (info_t or {}).get("error_message")})
        if status == "error" or not isinstance(obs_t, dict):
            break
        for key, values in obs_t.items():
            step_rows[key].append(values[-1] if len(values) else None)
        step_rows["__reward"].append(_env_np(reward))
        for key, value in _env_flatten(env.unwrapped.get_state_dict()).items():
            step_rows[f"__state/{key}"].append(value)
        if statuses[-1]["terminated"] or statuses[-1]["truncated"]:
            break
    for key, values in sorted(step_rows.items()):
        if key in ("front_rgb_list", "wrist_rgb_list"):
            name, layer = key.split("_")[0], "step_frames"
        elif key.startswith("__state/"):
            name, layer = key[len("__state/"):], "step_state"
        else:
            name, layer = key.lstrip("_"), "step_obs"
        tmp: dict[str, Any] = {}
        _env_stack(values, name, tmp, layers[layer])
        for k, v in tmp.items():
            arrays[f"{layer}/{k}"] = v
    layers["step_status"] = {"statuses": _env_json_digest(statuses), "action": _env_digest(action)}
    arrays["step_status/action"] = action
    timing.update({"step_s": step_s, "step_physics_s": physics_s if hub.wrapped else UNCOLLECTED,
                   "step_get_obs_s": get_obs_s if hub.wrapped else UNCOLLECTED})

    hub.phase = "close"
    started = time.perf_counter()
    env.close()
    timing["close_s"] = round(time.perf_counter() - started, 6)
    timing["class_timers"] = {phase: hub.take(phase) for phase in ("probe", "make", "reset", "choices", "step", "close")}
    for phase in ("probe", "make", "reset", "choices", "step", "close"):
        hub.buckets.pop(phase, None)
        hub.counts.pop(phase, None)
    hub.phase = "idle"

    npz_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = npz_path.with_suffix(".tmp.npz")
    np.savez_compressed(tmp_path, **arrays)
    tmp_path.replace(npz_path)
    rng_consumed = {
        "torch_rng_consumed_reset": rng["before_reset"]["torch"] != rng["after_reset"]["torch"],
        "np_rng_consumed_reset": rng["before_reset"]["numpy"] != rng["after_reset"]["numpy"],
        "py_rng_consumed_reset": rng["before_reset"]["python"] != rng["after_reset"]["python"],
        "torch_rng_consumed_make": rng["before_make"]["torch"] != rng["after_make"]["torch"],
        "np_rng_consumed_make": rng["before_make"]["numpy"] != rng["after_make"]["numpy"],
        "torch_rng_consumed_choices": rng["after_reset"]["torch"] != rng["after_choices"]["torch"],
        "np_rng_consumed_choices": rng["after_reset"]["numpy"] != rng["after_choices"]["numpy"],
    }
    return {"layers": {name: _env_layer(keys) for name, keys in layers.items()}, "identity_fields": identity_fields,
            "rng": rng, **rng_consumed, "torch_rng_consumed": rng_consumed["torch_rng_consumed_reset"],
            "np_rng_consumed": rng_consumed["np_rng_consumed_reset"], "timing": timing,
            "steps_done": len(statuses), "step_statuses": statuses, "fixed_action": action.tolist(),
            "npz": str(npz_path.relative_to(npz_path.parents[1])), "npz_bytes": npz_path.stat().st_size}


def cmd_env_digest_worker(args) -> int:
    """子进程：分记 import 耗时 → 装计时包装 → 逐身份跑 _env_digest_one，每身份一行追加到 rows.jsonl。"""
    import os

    entered = time.time()
    proc: dict[str, Any] = {}
    spawn = os.environ.get("V75_ENV_DIGEST_SPAWN_T")
    proc["spawn_to_worker_s"] = round(entered - float(spawn), 6) if spawn else UNCOLLECTED
    for label, mods in (("numpy", ("numpy",)), ("torch", ("torch",)), ("sapien", ("sapien",)),
                        ("mani_skill", ("mani_skill", "mani_skill.envs")),
                        ("robomme_hard", ("robomme_hard.env_record_wrapper",))):
        started = time.perf_counter()
        for mod in mods:
            __import__(mod)
        proc[f"import_{label}_s"] = round(time.perf_counter() - started, 6)
    from robomme_hard.env_record_wrapper import BenchmarkEnvBuilder

    hs = _hard_specs()
    hub = _env_install_timers(hs.ALL_TASKS)
    proc["timers_wrapped"] = len(hub.wrapped)
    proc["timers_missing"] = hub.missing
    host = _env_host_info()
    idents = json.loads(Path(args.batch).read_text())
    cell_dir = Path(args.out) / args.cell
    rows_path = cell_dir / "rows.jsonl"
    builders: dict[str, Any] = {}
    for position, ident in enumerate(idents):
        started = time.time()
        row = {k: ident[k] for k in ("task", "source_episode", "seed", "builder_episode")}
        row.update({"cell": args.cell, "mode": args.mode, "order_index": ident["_order_index"], "proc_index": args.proc_index,
                    "position_in_proc": position, "pid": os.getpid(), "host": host, "timing_notes": ENV_TIMING_NOTES,
                    "include_available_multi_choices": False, "fixed_steps": args.fixed_steps,
                    "resume_generation": args.resume_generation, "resumed": args.resume_generation > 0,
                    "proc_init": proc if position == 0 else {"note": "见本进程 position_in_proc=0 的行"}, "error": None})
        try:
            builder = builders.setdefault(ident["task"], BenchmarkEnvBuilder(
                env_id=ident["task"], dataset="test-hard", action_space="joint_angle", max_steps=1300))
            npz = cell_dir / "arrays" / f"{ident['task']}-ep{ident['source_episode']}-b{ident['builder_episode']}.npz"
            row.update(_env_digest_one(ident, builder, hub, args.fixed_steps, npz))
        except Exception as exc:  # noqa: BLE001 如实记录，续跑时重做
            import traceback

            row["error"] = f"{type(exc).__name__}: {exc}"[:800]
            row["traceback"] = traceback.format_exc()[-3000:]
            hub.phase = "idle"
        if position == 0:
            # 第一个身份出错也照记（只要 _setup_scene 被调到过）
            first = hub.first.get("BaseEnv._setup_scene")
            proc["first_vulkan_s"] = round(first, 6) if first is not None else UNCOLLECTED
        row["wall_s"] = round(time.time() - started, 3)
        with rows_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True, default=str) + "\n")
        print(f"ENV_DIGEST_ROW cell={args.cell} id={_env_identity_key(row)} wall_s={row['wall_s']} "
              f"npz_mib={row.get('npz_bytes', 0) / 2**20:.1f} steps={row.get('steps_done')} "
              f"torch_rng_consumed={row.get('torch_rng_consumed')} np_rng_consumed={row.get('np_rng_consumed')} "
              f"error={row['error']}", flush=True)
    return 0


def _env_rows(cell_dir: Path) -> dict[str, dict[str, Any]]:
    """rows.jsonl → {身份键: 最后一行无错的行}（有错的行不算完成）。"""
    out: dict[str, dict[str, Any]] = {}
    path = cell_dir / "rows.jsonl"
    if not path.exists():
        return out
    for text in path.read_text().splitlines():
        if not text.strip():
            continue
        try:
            row = json.loads(text)
        except json.JSONDecodeError:
            continue  # 半行（进程被杀）
        if row.get("error") is None and "layers" in row:
            out[_env_identity_key(row)] = row
    return out


def _env_resume_generation(cell_dir: Path) -> int:
    """本次运行的续跑代数：rows.jsonl 无任何行 → 0；否则 = 已有行里最大 resume_generation + 1（旧行缺字段按 0）。"""
    path = cell_dir / "rows.jsonl"
    gens = []
    if path.exists():
        for text in path.read_text().splitlines():
            try:
                gens.append(int(json.loads(text).get("resume_generation") or 0))
            except (json.JSONDecodeError, ValueError, AttributeError):
                continue
    return max(gens) + 1 if gens else 0


def _env_p50(values: list) -> str:
    nums = sorted(v for v in values if isinstance(v, (int, float)))
    if not nums:
        return UNCOLLECTED
    return f"{nums[len(nums) // 2]:.3f}"


def _env_speed_line(cell: str, rows: list[dict[str, Any]]) -> str:
    t = [r["timing"] for r in rows]
    firsts = [r["proc_init"] for r in rows if r.get("position_in_proc") == 0 and isinstance(r.get("proc_init"), dict)]
    host = rows[0]["host"] if rows else {}
    fields = {
        "rows": len(rows), "host": host.get("host", UNCOLLECTED),
        "gpu": str((host.get("gpu") or {}).get("name", UNCOLLECTED)).replace(" ", "_"),
        "cores": host.get("affinity_cores", UNCOLLECTED),
        "procs": len(firsts),
        "import_torch_s_p50": _env_p50([p.get("import_torch_s") for p in firsts]),
        "import_sapien_s_p50": _env_p50([p.get("import_sapien_s") for p in firsts]),
        "import_mani_skill_s_p50": _env_p50([p.get("import_mani_skill_s") for p in firsts]),
        "import_robomme_hard_s_p50": _env_p50([p.get("import_robomme_hard_s") for p in firsts]),
        "first_vulkan_s_p50": _env_p50([p.get("first_vulkan_s") for p in firsts]),
        "make_env_s_p50": _env_p50([x.get("make_env_s") for x in t]),
        "gym_make_s_p50": _env_p50([x.get("gym_make_s") for x in t]),
        "eval_reset_s_p50": _env_p50([x.get("eval_reset_s") for x in t]),
        "inner_reset_s_p50": _env_p50([x.get("inner_reset_s") for x in t]),
        "demo_s_p50": _env_p50([x.get("demo_s") for x in t]),
        "demo_s_per_frame_p50": _env_p50([x.get("demo_s_per_frame") for x in t]),
        "step_s_p50": _env_p50([s for x in t for s in (x.get("step_s") or [])]),
        "step_physics_s_p50": _env_p50([s for x in t if isinstance(x.get("step_physics_s"), list) for s in x["step_physics_s"]]),
        "step_get_obs_s_p50": _env_p50([s for x in t if isinstance(x.get("step_get_obs_s"), list) for s in x["step_get_obs_s"]]),
        "close_s_p50": _env_p50([x.get("close_s") for x in t]),
        "wall_s_p50": _env_p50([r.get("wall_s") for r in rows]),
    }
    return f"ENV_SPEED=INFO cell={cell} " + " ".join(f"{k}={v}" for k, v in fields.items())


def cmd_env_digest(args) -> int:
    """ENV_DIGEST_DONE：按身份清单逐个建环境、固定动作走 N 步，逐层存摘要与原始数组（不接策略）。
    默认每任务一个新进程（正序）；--resident 全部放进一个常驻进程；--reverse 倒序；已在 rows.jsonl 的身份跳过（续跑）。
    ⚠ 演示前场景状态取自另建的底层环境 reset 后的状态（_PROBE 的做法），不是评估实例本身的瞬间状态。"""
    import os
    import subprocess

    idents = json.loads(Path(args.identities).read_text())
    for index, ident in enumerate(idents):
        ident["_order_index"] = index
    if args.reverse:
        idents = idents[::-1]
    if args.limit:
        idents = idents[: args.limit]
    cell_dir = Path(args.out) / args.cell
    (cell_dir / "batches").mkdir(parents=True, exist_ok=True)
    done = _env_rows(cell_dir)
    todo = [i for i in idents if _env_identity_key(i) not in done]
    generation = _env_resume_generation(cell_dir)
    if args.resident and generation > 0 and not args.allow_resume_resident:
        # 常驻条件的含义是「全部身份在同一进程里连续跑」；续跑会拆成多个进程，条件被静默改变
        print(f"ENV_DIGEST_RESUME_REFUSED cell={args.cell} mode=resident resume_generation={generation} "
              f"done={len(idents) - len(todo)} todo={len(todo)}（换新 --cell 重跑，或显式加 --allow-resume-resident）",
              flush=True)
        return 2
    batches: list[list[dict[str, Any]]] = []
    if args.resident:
        batches = [todo] if todo else []
    else:
        for ident in todo:
            if batches and batches[-1][0]["task"] == ident["task"]:
                batches[-1].append(ident)
            else:
                batches.append([ident])
    mode = "resident" if args.resident else "per-task"
    mode += "-reverse" if args.reverse else "-forward"
    print(f"ENV_DIGEST_PLAN cell={args.cell} identities={len(idents)} done={len(idents) - len(todo)} "
          f"resume_generation={generation} resumed={generation > 0} "
          f"todo={len(todo)} procs={len(batches)} mode={mode}", flush=True)
    env = dict(os.environ)
    if args.gpu is not None:
        env["CUDA_VISIBLE_DEVICES"] = str(args.gpu)
    failures = 0
    for proc_index, batch in enumerate(batches):
        batch_path = cell_dir / "batches" / f"proc{proc_index:03d}-{os.getpid()}.json"
        batch_path.write_text(json.dumps(batch, ensure_ascii=False))
        env["V75_ENV_DIGEST_SPAWN_T"] = repr(time.time())
        code = subprocess.run([sys.executable, str(Path(__file__).resolve()), "env-digest-worker", "--cell", args.cell,
                               "--out", args.out, "--batch", str(batch_path), "--fixed-steps", str(args.fixed_steps),
                               "--proc-index", str(proc_index), "--mode", mode,
                               "--resume-generation", str(generation)], env=env, cwd=str(REPO)).returncode
        if code != 0:
            failures += 1
            print(f"ENV_DIGEST_PROC_FAIL cell={args.cell} proc={proc_index} code={code} tasks={sorted({b['task'] for b in batch})}",
                  flush=True)
    done = _env_rows(cell_dir)
    rows = [done[k] for k in (_env_identity_key(i) for i in idents) if k in done]
    print(_env_speed_line(args.cell, rows), flush=True)
    print(f"ENV_DIGEST_DONE cell={args.cell} rows={len(rows)}", flush=True)
    return 0 if len(rows) == len(idents) and not failures else 1


def _env_name_agnostic(keys: dict[str, str]) -> dict[str, list[str]]:
    """与 _name_agnostic 同一思路：按分区（键的第一段）取逐键摘要的有序多重集，忽略实体名。"""
    out: dict[str, list[str]] = collections.defaultdict(list)
    for key, value in keys.items():
        out[key.split("/")[0]].append(value)
    return {k: sorted(v) for k, v in sorted(out.items())}


def _env_load_npz(cell_dir: Path, row: dict[str, Any]):
    import numpy as np

    path = cell_dir / row["npz"]
    return np.load(path) if path.exists() else None


def _env_is_image(arr) -> bool:
    """uint8 且形如 (H,W,3) 或 (N,H,W,3) 的数组按图像处理（含 reset_obs 的 front_init/wrist_init）。"""
    return arr.dtype == "uint8" and arr.ndim in (3, 4) and arr.shape[-1] == 3


def _env_image_diff(x, y) -> dict[str, Any] | None:
    """逐帧 MAD（每帧在 H、W、通道上取平均绝对差，0–255 刻度）：最大值、均值、第一个不等帧、不等帧数；
    帧数不同只比公共前缀并记两边帧数；单帧尺寸不同则不可测（返回 None）。"""
    import numpy as np

    if x.ndim == 3:
        x, y = x[None], y[None]
    if x.shape[1:] != y.shape[1:]:
        return None
    n = min(len(x), len(y))
    out: dict[str, Any] = {"frames": [int(len(x)), int(len(y))]}
    if n == 0:
        out.update({"per_frame_mad_max": None, "per_frame_mad_mean": None, "first_diff_frame": None, "diff_frames": 0})
        return out
    mad = np.abs(x[:n].astype(np.int16) - y[:n].astype(np.int16)).mean(axis=(1, 2, 3))
    bad = np.nonzero(mad > 0)[0]
    out.update({"per_frame_mad_max": float(mad.max()), "per_frame_mad_mean": float(mad.mean()),
                "first_diff_frame": int(bad[0]) if len(bad) else None, "diff_frames": int(len(bad))})
    return out


def _env_compare_row(a: dict[str, Any], b: dict[str, Any], dir_a: Path, dir_b: Path) -> dict[str, Any]:
    """单个身份逐层比：相等 / 仅改名 / 键集合差 / 数值差（状态最大绝对差、图像逐帧 MAD）。
    量不出来的（npz 缺失、形状或 dtype 不符、参差回退未存数组、只有键集合差）一律记 None 并计入 unmeasured，不填 0。"""
    import numpy as np

    detail: dict[str, Any] = {"id": _env_identity_key(a), "layers": {}, "npz_missing": [], "unmeasured": 0}
    za = zb = None
    loaded = False
    first_diff = None
    for layer in ENV_DIGEST_LAYERS:
        la, lb = a["layers"].get(layer), b["layers"].get(layer)
        if la is None or lb is None:
            detail["layers"][layer] = {"equal": False, "missing": "a" if la is None else "b"}
            first_diff = first_diff or layer
            continue
        if la["digest"] == lb["digest"]:
            detail["layers"][layer] = {"equal": True}
            continue
        ka, kb = la["keys"], lb["keys"]
        info: dict[str, Any] = {"equal": False}
        only_a, only_b = sorted(set(ka) - set(kb)), sorted(set(kb) - set(ka))
        if only_a or only_b:
            info.update({"only_a": only_a[:20], "only_b": only_b[:20], "key_set_diff": True})
            # 只有键集合不同时才可能「仅改名」；键集合相同而值不同（如两个同形 actor 互换位姿）是真差异
            if layer in _ENV_STATE_LAYERS and _env_name_agnostic(ka) == _env_name_agnostic(kb):
                info["name_only"] = True
                detail["layers"][layer] = info
                continue
        diff_keys = sorted(k for k in set(ka) & set(kb) if ka[k] != kb[k])
        info["diff_keys"] = diff_keys[:20]
        info["diff_key_count"] = len(diff_keys)
        first_diff = first_diff or layer
        info["max_abs"] = None
        info["image"] = None
        if layer in ("identity", "step_status"):
            detail["layers"][layer] = info
            continue
        if not diff_keys:
            # 只有键集合差：公共键全相等，没有可量的数值
            detail["unmeasured"] += 1
            detail["layers"][layer] = info
            continue
        if not loaded:
            za, zb, loaded = _env_load_npz(dir_a, a), _env_load_npz(dir_b, b), True
            detail["npz_missing"] = [side for side, z in (("a", za), ("b", zb)) if z is None]
        if za is None or zb is None:
            detail["unmeasured"] += len(diff_keys)
            detail["layers"][layer] = info
            continue
        worst: float | None = None
        images: dict[str, Any] = {}
        unmeasured: list[str] = []
        for key in diff_keys:
            name = f"{layer}/{key}"
            if name not in za.files or name not in zb.files:
                unmeasured.append(key)  # 参差回退只存了摘要
                continue
            x, y = za[name], zb[name]
            if _env_is_image(x) and _env_is_image(y):
                got = _env_image_diff(x, y)
                if got is None:
                    unmeasured.append(key)
                else:
                    images[key] = got
                continue
            if x.shape != y.shape or x.dtype.kind not in "biuf" or y.dtype.kind not in "biuf":
                unmeasured.append(key)
                continue
            value = float(np.abs(x.astype(np.float64) - y.astype(np.float64)).max(initial=0.0))
            worst = value if worst is None else max(worst, value)
        info["max_abs"] = worst
        if images:
            maxes = [v["per_frame_mad_max"] for v in images.values() if v["per_frame_mad_max"] is not None]
            means = [v["per_frame_mad_mean"] for v in images.values() if v["per_frame_mad_mean"] is not None]
            info["image"] = {"per_frame_mad_max": max(maxes) if maxes else None,
                             "per_frame_mad_mean": max(means) if means else None, "keys": images}
        if unmeasured:
            info["unmeasured_keys"] = unmeasured[:20]
            detail["unmeasured"] += len(unmeasured)
        detail["layers"][layer] = info
    detail["first_diff"] = first_diff
    return detail


def _env_fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.6g}"


def cmd_env_digest_compare(args) -> int:
    """ENV_DIGEST_PARITY（只报告）：两格按身份对齐逐层比，打一行汇总并写 json 明细。
    state_max_abs／obs_max_abs／image_mad 在没有任何可量差异时为 n/a（全同时也是 n/a：摘要相等不再读数组）。"""
    dir_a, dir_b = Path(args.a), Path(args.b)
    rows_a, rows_b = _env_rows(dir_a), _env_rows(dir_b)
    common = [k for k in rows_a if k in rows_b]
    common.sort(key=lambda k: rows_a[k].get("order_index", 0))
    details = [_env_compare_row(rows_a[k], rows_b[k], dir_a, dir_b) for k in common]
    layer_equal = {layer: sum(d["layers"][layer]["equal"] for d in details) for layer in ENV_DIGEST_LAYERS}
    name_only = {layer: sum(bool(d["layers"][layer].get("name_only")) for d in details) for layer in ENV_DIGEST_LAYERS}
    key_set = sum(any(v.get("key_set_diff") for v in d["layers"].values()) for d in details)
    firsts = [d["first_diff"] for d in details if d["first_diff"]]
    first = min(firsts, key=ENV_DIGEST_LAYERS.index) if firsts else "-"
    first_id = next((d["id"] for d in details if d["first_diff"] == first), "-")

    def pick(layers, field):
        vals = [v.get(field) for d in details for layer, v in d["layers"].items() if layer in layers]
        vals = [x for x in vals if x is not None]
        return max(vals) if vals else None

    state = pick(_ENV_STATE_LAYERS, "max_abs")
    obs = pick(_ENV_NUMERIC_OBS_LAYERS, "max_abs")
    imgs = [v["image"] for d in details for v in d["layers"].values() if v.get("image")]
    mad_max = max((i["per_frame_mad_max"] for i in imgs if i["per_frame_mad_max"] is not None), default=None)
    mad_mean = max((i["per_frame_mad_mean"] for i in imgs if i["per_frame_mad_mean"] is not None), default=None)
    frame_hits = [(d["id"], layer, key, v["first_diff_frame"], v["diff_frames"]) for d in details
                  for layer, lv in d["layers"].items() if lv.get("image") for key, v in lv["image"]["keys"].items()]
    first_frame = next((f"{layer}/{key}@{idx}" for _i, layer, key, idx, _n in frame_hits if idx is not None), "-")
    diff_frames = sum(n for *_x, n in frame_hits)
    npz_missing = sum(bool(d["npz_missing"]) for d in details)
    unmeasured = sum(d["unmeasured"] for d in details)
    missing_a = sorted(set(rows_b) - set(rows_a))
    missing_b = sorted(set(rows_a) - set(rows_b))
    resumed = {"a": sum(bool(r.get("resumed")) for r in rows_a.values()),
               "b": sum(bool(r.get("resumed")) for r in rows_b.values())}
    summary = {
        "pair": f"{dir_a.name}:{dir_b.name}", "a": str(dir_a), "b": str(dir_b), "compared": len(details),
        "rows_a": len(rows_a), "rows_b": len(rows_b), "missing_in_a": missing_a, "missing_in_b": missing_b,
        "layer_equal": layer_equal, "name_only": name_only, "key_set_diff": key_set,
        "first_diff": first, "first_diff_id": first_id, "identities_with_diff": len(firsts),
        "state_max_abs": state, "obs_max_abs": obs,
        "image_mad": mad_max, "image_mad_unit": None if mad_max is None else mad_max / 255.0,
        "image_mad_mean": mad_mean, "image_first_diff_frame": first_frame, "image_diff_frames": diff_frames,
        "npz_missing": npz_missing, "unmeasured": unmeasured, "resumed_rows": resumed,
        "note": "演示前场景状态取自另建底层环境 reset 后的状态（_PROBE 做法），非评估实例瞬间状态；"
                "image_mad = 各身份各图像键逐帧 MAD（0–255 刻度，每帧在 H、W、通道上平均）的最大值，image_mad_unit 为 ÷255，"
                "image_mad_mean = 各图像键逐帧 MAD 均值的最大值；量不出来记 None（行里 n/a）并计入 unmeasured",
        "details": details,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=1) + "\n")
    print(f"ENV_DIGEST_PARITY pair={summary['pair']} compared={len(details)} "
          f"layer_equal={','.join(f'{k}:{v}' for k, v in layer_equal.items())} first_diff={first} "
          f"state_max_abs={_env_fmt(state)} image_mad={_env_fmt(mad_max)} "
          f"image_mad_unit={_env_fmt(None if mad_max is None else mad_max / 255.0)} image_mad_mean={_env_fmt(mad_mean)} "
          f"image_first_diff_frame={first_frame} image_diff_frames={diff_frames} obs_max_abs={_env_fmt(obs)} "
          f"name_only={sum(name_only.values())} key_set_diff={key_set} npz_missing={npz_missing} unmeasured={unmeasured} "
          f"rows_a={len(rows_a)} rows_b={len(rows_b)} missing_in_a={len(missing_a)} missing_in_b={len(missing_b)} "
          f"resumed_a={resumed['a']} resumed_b={resumed['b']} first_diff_id={first_id}", flush=True)
    return 0


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
    x0.add_argument("--merge-with", default=None, help="与上一轮 jsonl 合并：本轮重跑的任务整段替换，其余沿用")
    x0.add_argument("--report-name", default="xhard0-reset-parity.jsonl")
    x0.set_defaults(func=cmd_xhard0_reset_parity)
    xe = sub.add_parser("xhard0-eval-parity")
    xe.add_argument("--official", nargs="+", required=True, help="官方路线结果文件或目录（可多个）")
    xe.add_argument("--hard", nargs="+", required=True, help="v7 路线结果文件或目录（可多个；只取 tier=xhard0 的局）")
    xe.add_argument("--policy", required=True, choices=("simplememvla", "mmevla"))
    xe.add_argument("--manifest", default=str(REPO / "scripts" / "configs" / "newtask-v7" / "xhard0_manifest.json"))
    xe.add_argument("--out", required=True)
    xe.set_defaults(func=cmd_xhard0_eval_parity)
    sh = sub.add_parser("step-headroom")
    sh.add_argument("--delivery", required=True, help="gen1 的 delivery.json（行里 path 相对其所在目录）")
    sh.add_argument("--out", default=None)
    sh.add_argument("--info", action="store_true", help="冒烟外推只报告（阶段 3），不判 PASS/FAIL")
    sh.set_defaults(func=cmd_step_headroom)
    ed = sub.add_parser("env-digest", help="v7.5eval 环境检测：逐层摘要 + 原始数组 + 测速（GPU）")
    ed.add_argument("--cell", required=True, help="条件名（输出子目录）")
    ed.add_argument("--identities", required=True, help="身份清单 json：[{task, source_episode, seed, builder_episode, ...}]")
    ed.add_argument("--out", required=True)
    ed.add_argument("--resident", action="store_true", help="全部身份放进一个常驻进程（默认每任务一个新进程）")
    ed.add_argument("--reverse", action="store_true", help="身份倒序")
    ed.add_argument("--fixed-steps", type=int, default=30)
    ed.add_argument("--gpu", default=None, help="子进程的 CUDA_VISIBLE_DEVICES（不给则继承）")
    ed.add_argument("--limit", type=int, default=0)
    ed.add_argument("--allow-resume-resident", action="store_true",
                    help="--resident 下允许续跑（续跑会把一个常驻进程拆成多个，改变条件；默认拒绝）")
    ed.set_defaults(func=cmd_env_digest)
    ew = sub.add_parser("env-digest-worker", help=argparse.SUPPRESS)
    ew.add_argument("--cell", required=True)
    ew.add_argument("--out", required=True)
    ew.add_argument("--batch", required=True)
    ew.add_argument("--fixed-steps", type=int, default=30)
    ew.add_argument("--proc-index", type=int, default=0)
    ew.add_argument("--mode", default="per-task-forward")
    ew.add_argument("--resume-generation", type=int, default=0)
    ew.set_defaults(func=cmd_env_digest_worker)
    ec = sub.add_parser("env-digest-compare", help="两格环境检测结果逐层对拍（纯 CPU，只报告）")
    ec.add_argument("--a", required=True, help="<out>/<cell> 目录")
    ec.add_argument("--b", required=True)
    ec.add_argument("--out", required=True, help="json 明细")
    ec.set_defaults(func=cmd_env_digest_compare)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
