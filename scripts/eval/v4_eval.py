#!/usr/bin/env python3
"""V4 新值评估入口（NEWTASK_RELEASE_V4_PLAN 第四节，步 6；E1 批准的 ``scripts/eval/``）。

按冻结的 ``specs.jsonl`` 逐局起环境跑策略，边跑边写 ``eval_results.jsonl``，结束写 ``eval_summary.json``。
**不改 ``scripts/evaluation.py``**（口径 9：它与上游逐字节相同）；评估循环照抄它的写法。

环境构建走 ``BenchmarkEnvBuilder.from_v4_specs``：seed / difficulty / sampling_config / 规格 / recover 分档
全部取自快照，runtime 四项逐字比对；每局结束读 ``env.unwrapped._spec`` 做规格绑定核验
（``missing`` / ``unused`` / 归因后的 ``mismatch``），与生成侧 ``results.jsonl`` 按
``(task, difficulty, episode, seed, spec_sha256)`` 直接 join。

默认策略是与 ``scripts/evaluation.py`` 同构的 ``DummyModel``（只验证链路，不代表任何真实策略）。

    uv run --no-sync python -m scripts.eval.v4_eval --specs <specs.jsonl> --out artifacts/newtask-v4/eval/<run> \
        [--tasks PatternLock,RouteStick] [--max-steps 1300] [--limit-per-task 1]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
for extra in (REPO_ROOT, REPO_ROOT / "scripts", REPO_ROOT / "src"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from scripts.parity.v4_specs import load_specs  # noqa: E402


class DummyModel:
    """与 scripts/evaluation.py 的 DummyModel 同构：固定基准动作 + 小噪声。"""

    policy_id = "dummy-evaluation-py"

    def __init__(self, seed: int):
        import numpy as np
        import torch

        self.np = np
        self.base_action = np.array([0.0, 0.0, 0.0, -np.pi / 2, 0.0, np.pi / 2, np.pi / 4, 1.0], dtype=np.float32)
        torch.manual_seed(seed)
        np.random.seed(seed)
        random.seed(seed)

    def predict(self, *args, **kwargs):
        noise = self.np.random.normal(0, 0.01, self.base_action.shape)
        noise[..., -1:] = 0.0
        return self.base_action + noise


def _binding(env) -> dict:
    recorder = getattr(env.unwrapped, "_spec", None)
    if recorder is None:
        return {"available": False}
    consumed = set(recorder.consumed_paths())
    unused = [p for p in recorder.leaf_paths() if not any(p == c or p.startswith(c + ".") for c in consumed)]
    return {"available": True, "mode": recorder.mode, "mismatch": len(recorder.mismatches),
            "unattributed_mismatch": len(recorder.unattributed_mismatches()), "unused": len(unused)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--specs", required=True)
    parser.add_argument("--tasks", default="all")
    parser.add_argument("--action-space", default="joint_angle")
    parser.add_argument("--max-steps", type=int, default=1300, help="MME-VLA 实验口径 1300；演示帧不计入")
    parser.add_argument("--model-seed", type=int, default=7)
    parser.add_argument("--limit-per-task", type=int, default=0)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--join-results", default=None,
                        help="生成侧 results.jsonl；给了就在收尾按身份 join 并打印 V5e 判定行")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    from robomme.env_record_wrapper import BenchmarkEnvBuilder

    header, _, specs_by_identity = load_specs(args.specs)
    tasks = header["tasks"] if args.tasks == "all" else args.tasks.split(",")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    results_path = out / "eval_results.jsonl"
    if results_path.exists():
        raise SystemExit(f"{results_path} 已存在，禁止覆盖")
    model = DummyModel(args.model_seed)
    policy_sha = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    per_task: dict[str, dict] = {}
    for task in tasks:
        builder = BenchmarkEnvBuilder.from_v4_specs(task, header, specs_by_identity,
                                                    action_space=args.action_space, max_steps=args.max_steps)
        episodes = builder.v4_episodes()
        if args.limit_per_task:
            episodes = episodes[: args.limit_per_task]
        successes = 0
        for episode in episodes:
            row_spec = specs_by_identity[f"{task}/{episode}"]
            started = time.time()
            status, steps, error_type, error, binding, runtime_ok = "error", 0, None, None, None, True
            env = None
            try:
                env = builder.make_env_for_episode(episode)
                obs, info = env.reset()
                binding = _binding(env)
                task_goal = info["task_goal"][0]
                front, wrist = obs["front_rgb_list"][-1], obs["wrist_rgb_list"][-1]
                while True:
                    action = model.predict(front, wrist, task_goal)
                    obs, reward, terminated, truncated, info = env.step(action)
                    steps += 1
                    if info is not None and info.get("status") == "error":
                        status, error = "error", str(info.get("error_message"))[:500]
                        break
                    if terminated or truncated:
                        status = info.get("status", "unknown")
                        break
                    front, wrist = obs["front_rgb_list"][-1], obs["wrist_rgb_list"][-1]
            except ValueError as exc:
                if "runtime" in str(exc):
                    runtime_ok = False
                error_type, error = type(exc).__name__, str(exc)[:500]
            except Exception as exc:  # noqa: BLE001 如实记录
                error_type, error = type(exc).__name__, str(exc)[:500]
            finally:
                if env is not None:
                    env.close()
            successes += status == "success"
            record = {
                "task": task, "difficulty": row_spec["difficulty"], "episode": episode, "seed": row_spec["seed"],
                "spec_sha256": row_spec["spec_sha256"], "run_id": args.run_id or out.name,
                "status": status, "steps": steps, "wall_s": round(time.time() - started, 1),
                "policy_id": model.policy_id, "policy_sha256": policy_sha, "action_space": args.action_space,
                "max_steps": args.max_steps, "model_seed": args.model_seed,
                "runtime_ok": runtime_ok, "spec_binding": binding, "error_type": error_type, "error": error,
            }
            with results_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            print(f"EVAL {task}/{episode} status={status} steps={steps} binding={binding}", flush=True)
        per_task[task] = {"avg_success": successes / len(episodes) if episodes else 0.0,
                          "success_count": successes, "num_episodes": len(episodes)}
    total = sum(v["num_episodes"] for v in per_task.values())
    summary = {"specs_identity_sha256": header["identity_sha256"], "per_task": per_task,
               "overall": {"avg_success": sum(v["success_count"] for v in per_task.values()) / total if total else 0.0,
                           "success_count": sum(v["success_count"] for v in per_task.values()), "num_episodes": total}}
    (out / "eval_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"EVAL_DONE episodes={total} out={out}")
    if args.join_results:
        return join_check(results_path, Path(args.join_results))
    return 0


JOIN_KEY = ("task", "difficulty", "episode", "seed", "spec_sha256")


def join_check(eval_path: Path, results_path: Path) -> int:
    """V5e：runtime_ok 全真、行数与分片一致、每行都能按身份 join 上生成侧 results.jsonl。"""
    evals = [json.loads(line) for line in eval_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    produced = {tuple(r[k] for k in JOIN_KEY)
                for r in (json.loads(line) for line in results_path.read_text(encoding="utf-8").splitlines() if line.strip())}
    runtime_ok = sum(1 for r in evals if r["runtime_ok"])
    join_missing = sum(1 for r in evals if tuple(r[k] for k in JOIN_KEY) not in produced)
    ok = runtime_ok == len(evals) and join_missing == 0 and evals
    print(f"EVAL_PIPELINE={'PASS' if ok else 'FAIL'} episodes={len(evals)} runtime_ok={runtime_ok} join_missing={join_missing}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
