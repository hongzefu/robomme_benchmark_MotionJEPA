#!/usr/bin/env python3
"""robomme_hard 回归工具（0927 计划第二部分 §1.3）。

子命令：

* ``s4-subset``（纯 CPU）：S4 交付的 165 局（xhard1/2/3 各 13 任务 × 3 局 + xhard4 16 任务 × 3 局）必须是包内 test-hard
  交付集（1100 局）的子集——seed 匹配、规格回注点逐位相等、记录点浮点差 ≤ ``RECORDED_FLOAT_TOL``（U-13 方案甲）；
  输出 ``S4_SUBSET`` 判定行与映射表 ``s4-to-delivery.json``（S4 身份 → builder episode 号）。
* ``reset-replay``（GPU）：从 S4 每格取 candidate 最小的一局（13×3 + 16 = 55），经映射落到 test-hard 同一身份，
  经 builder 评估链 ``make_env_for_episode`` + reset，``spec_binding()`` 摘要，``task_goal`` 与多选项和
  ``s4-setup-manifest.json`` 逐字比 → ``HARD_RESET_REPLAY``。
* ``eval-smoke``（GPU，本机 1 任务 × 1 档 × 1 局）：合作者入口可用 → ``HARD_EVAL_SMOKE``。
* ``xhw-reference``（纯 CPU）：Ada 原三档存档与 A40 O 侧的跨硬件参考 → ``XHW_REFERENCE=INFO``。

    uv run --no-sync python scripts/parity/hard_regression.py s4-subset
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

S4_DELIVERY = REPO / "artifacts" / "newtask-v6" / "s4-relaunch-02" / "verification" / "final-delivery.json"
S4_SPECS = REPO / "scripts" / "configs" / "newtask-v6" / "v6-02"
MAPPING_OUT = REPO / "src" / "robomme_hard" / "env_metadata" / "test-hard" / "s4-to-delivery.json"
S4_SETUP = REPO / "src" / "robomme_hard" / "env_metadata" / "test-hard" / "s4-setup-manifest.json"


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


def delivery_index() -> dict[tuple[str, str, int], dict[str, Any]]:
    """(task, tier, seed) → {row, builder_episode}；builder 号 = 档序主序、档内 candidate 升序（与 hard_builder 相同）。"""
    hs = _hard_specs()
    index: dict[tuple[str, str, int], dict[str, Any]] = {}
    offsets: dict[str, int] = collections.Counter()
    for tier in hs.TIERS:
        _, rows = hs.load_specs(hs.packaged_specs_path(tier), check_fingerprint=False)
        for task in hs.ALL_TASKS:
            chosen = sorted((r for r in rows if r["task"] == task and hs.delivered(r)), key=lambda r: r["candidate"])
            for row in chosen:
                index[(task, tier, int(row["seed"]))] = {"row": row, "builder_episode": offsets[task]}
                offsets[task] += 1
    return index


def cmd_s4_subset(args) -> int:
    delivery = json.loads(S4_DELIVERY.read_text())["successes"]
    s4_rows: dict[tuple[str, str, int], dict[str, Any]] = {}
    for tier in _hard_specs().TIERS:
        for line in (S4_SPECS / tier / "specs.jsonl").read_text().splitlines()[1:]:
            row = json.loads(line)
            s4_rows[(row["task"], tier, int(row["episode"]))] = row
    index = delivery_index()
    seed_match = exact = within = injected_rows = 0
    max_abs = 0.0
    mapping, problems = [], []
    for s in delivery:
        key = (s["task"], s["difficulty"], int(s["seed"]))
        hit = index.get(key)
        if hit is None:
            problems.append(f"no_seed:{key}")
            continue
        seed_match += 1
        spec = s4_rows[(s["task"], s["difficulty"], int(s["episode"]))]
        if spec["spec_sha256"] != s["spec_sha256"]:
            problems.append(f"s4_spec_sha_inconsistent:{key}")
        result = compare_specs(spec["spec"], hit["row"]["spec"], record_path_patterns(s["task"]),
                               record_path_patterns(s["task"], method="value"))
        if result["injected"]:
            injected_rows += 1
            problems.append(f"injected:{key}:{result['paths'][:3]}")
        elif result["within"]:
            within += 1
            max_abs = max(max_abs, result["max_abs"])
        else:
            exact += 1
        mapping.append({"task": s["task"], "tier": s["difficulty"], "s4_episode": int(s["episode"]),
                        "seed": int(s["seed"]), "s4_spec_sha256": s["spec_sha256"],
                        "delivery_candidate": int(hit["row"]["candidate"]),
                        "delivery_spec_sha256": hit["row"]["spec_sha256"],
                        "builder_episode": hit["builder_episode"], "spec_exact": result["within"] == 0 and not result["injected"],
                        "recorded_max_abs": result["max_abs"]})
    ok = seed_match == len(delivery) == 165 and injected_rows == 0 and exact + within == 165
    mapping.sort(key=lambda m: (_hard_specs().TIERS.index(m["tier"]), m["task"], m["s4_episode"]))
    if ok and not args.no_write:
        text = json.dumps({"schema": "s4-to-delivery/1", "count": len(mapping), "entries": mapping},
                          ensure_ascii=False, indent=1, sort_keys=True) + "\n"
        if MAPPING_OUT.exists() and MAPPING_OUT.read_text() != text:
            raise SystemExit(f"{MAPPING_OUT} 已存在且内容不同")
        MAPPING_OUT.write_text(text)
    print(f"S4_SUBSET={'PASS' if ok else 'FAIL'} s4={len(delivery)} seed_match={seed_match} spec_exact={exact} "
          f"spec_within_tol={within} max_abs={max_abs:.2g} injected_diff={injected_rows}"
          + (f" detail={problems[:8]}" if problems else ""))
    return 0 if ok else 1


# ── reset-replay / eval-smoke（GPU）────────────────────────────────────────


def _replay_targets() -> list[dict[str, Any]]:
    """S4 每格 candidate 最小的一局（13×3 + 16 = 55）→ 经映射得到 builder episode 号。"""
    mapping = json.loads(MAPPING_OUT.read_text())["entries"]
    first: dict[tuple[str, str], dict[str, Any]] = {}
    for entry in mapping:
        key = (entry["task"], entry["tier"])
        if key not in first or entry["s4_episode"] < first[key]["s4_episode"]:
            first[key] = entry
    return [first[k] for k in sorted(first, key=lambda k: (_hard_specs().TIERS.index(k[1]), k[0]))]


def cmd_reset_replay(args) -> int:
    from robomme_hard.env_record_wrapper import BenchmarkEnvBuilder, TIER_MAX_STEPS, spec_binding

    setup = {(e["task"], e["tier"], e["seed"]): e for e in json.loads(S4_SETUP.read_text())["entries"]}
    targets = _replay_targets()
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
        record = {"task": target["task"], "tier": target["tier"], "seed": target["seed"],
                  "builder_episode": target["builder_episode"]}
        env = None
        try:
            builder = builders.setdefault(target["task"], BenchmarkEnvBuilder(target["task"], dataset="test-hard"))
            identity = builder.resolve_identity(target["builder_episode"])
            assert identity["seed"] == target["seed"] and identity["tier"] == target["tier"], identity
            env = builder.make_env_for_episode(target["builder_episode"], max_steps=TIER_MAX_STEPS[target["tier"]])
            obs, info = env.reset()
            binding = spec_binding(env)
            goal = info.get("task_goal")
            goal = list(goal) if isinstance(goal, (list, tuple)) else [goal]
            want = setup[key]["setup"]
            choices = info.get("available_multi_choices")
            record.update({
                "binding": binding, "identity": identity,
                "goal_equal": [str(g) for g in goal] == want["task_goal"],
                "choices_recorded": choices is not None,
                "demo_frames": len(obs.get("front_rgb_list", [])) - 1 if isinstance(obs, dict) else None,
                "s4_demo_frames": setup[key]["demo_frames"],
                "ok": True,
            })
        except Exception as exc:  # noqa: BLE001 如实记录
            record.update({"ok": False, "error": f"{type(exc).__name__}: {exc}"[:800]})
        finally:
            if env is not None:
                env.close()
        record["wall_s"] = round(time.time() - started, 1)
        with out_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        print(f"RESET_REPLAY {key} ok={record['ok']} binding={record.get('binding')} goal_equal={record.get('goal_equal')}",
              flush=True)
    rows = [json.loads(line) for line in out_path.read_text().splitlines() if line.strip()]
    rows = [r for r in rows if (r["task"], r["tier"], r["seed"]) in {(t["task"], t["tier"], t["seed"]) for t in targets}]
    injected = sum(r["binding"]["injected_mismatch"] for r in rows if r.get("ok"))
    drift = sum(r["binding"]["recorded_drift"] for r in rows if r.get("ok"))
    drift_max = max((r["binding"]["recorded_max_abs"] for r in rows if r.get("ok")), default=0.0)
    goal_bad = sum(1 for r in rows if r.get("ok") and not r["goal_equal"])
    replay = sum(1 for r in rows if r.get("ok") and r["binding"].get("mode") == "replay" and r["binding"]["value_points"] > 0)
    errors = sum(1 for r in rows if not r.get("ok"))
    ok = len(rows) == len(targets) and errors == 0 and injected == 0 and goal_bad == 0 and replay == len(targets)
    shape = "13x3+16" if len(targets) == 55 else f"limit{len(targets)}"
    print(f"HARD_RESET_REPLAY={'PASS' if ok else 'FAIL'} resets={len(rows)} replay={replay} injected_mismatch={injected} "
          f"recorded_drift={drift} max_abs={drift_max:.2g} goal_mismatch={goal_bad} errors={errors} shape={shape}")
    return 0 if ok else 1


def cmd_eval_smoke(args) -> int:
    """合作者入口：与 scripts/evaluation_hard.py 同样的构建与 max_steps 传法，只跑 1 任务 × 1 档 × 1 局。"""
    import numpy as np

    from robomme_hard.env_record_wrapper import BenchmarkEnvBuilder, TIER_MAX_STEPS, spec_binding

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
    ok = (binding.get("mode") == "replay" and binding["injected_mismatch"] == 0 and status != "error"
          and num == (20 if args.task in _hard_specs().XHARD4_ONLY else 80))
    print(f"HARD_EVAL_SMOKE={'PASS' if ok else 'FAIL'} task={args.task} episode={args.episode} tier={tier} seed={seed} "
          f"episodes={num} max_steps={TIER_MAX_STEPS[tier]} status={status} steps={steps} "
          f"injected_mismatch={binding.get('injected_mismatch')} goal={str(info.get('task_goal'))[:60] if info else None}")
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    s4 = sub.add_parser("s4-subset")
    s4.add_argument("--no-write", action="store_true")
    s4.set_defaults(func=cmd_s4_subset)
    rr = sub.add_parser("reset-replay")
    rr.add_argument("--out", required=True)
    rr.add_argument("--limit", type=int, default=0)
    rr.set_defaults(func=cmd_reset_replay)
    ev = sub.add_parser("eval-smoke")
    ev.add_argument("--task", default="BinFill")
    ev.add_argument("--episode", type=int, default=0)
    ev.add_argument("--max-policy-steps", type=int, default=50)
    ev.set_defaults(func=cmd_eval_smoke)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
