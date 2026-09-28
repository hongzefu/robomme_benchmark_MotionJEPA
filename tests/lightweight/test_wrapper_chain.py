"""WRAPPER_CHAIN（0927 计划 §6.3 ★）：1 任务 × 4 个 action_space × test／test-hard 各 make 一个环境（不 reset），
比较包装链类名序列与所属包：两种 dataset 的类名序列逐项相同，且 wrapper 全部来自 robomme_hard（复制件或借用）。

需要 GPU 渲染栈；设 ``ROBOMME_OFFICIAL_SRC`` 在官方态下跑。子进程执行，避免与本进程注册表互相干扰。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

PROBE = r"""
import json
from robomme_hard.env_record_wrapper import BenchmarkEnvBuilder
from robomme_hard import UPSTREAM
borrowed = {s["target_module"] for s in UPSTREAM["shims"]}
out = {}
for space in ("joint_angle", "ee_pose", "waypoint", "multi_choice"):
    chains = {}
    for dataset in ("test", "test-hard"):
        builder = BenchmarkEnvBuilder("BinFill", dataset=dataset, action_space=space)
        env = builder.make_env_for_episode(0)
        chain, node = [], env
        while hasattr(node, "env"):
            chain.append([type(node).__name__, type(node).__module__])
            node = node.env
        chains[dataset] = chain
        env.close()
    out[space] = chains
print(json.dumps({"chains": out, "borrowed": sorted(borrowed)}))
"""


@pytest.mark.gpu
def test_wrapper_chain_same_shape():
    env = dict(os.environ)
    official = os.environ.get("ROBOMME_OFFICIAL_SRC")
    if official:
        env["PYTHONPATH"] = official + os.pathsep + env.get("PYTHONPATH", "")
    out = subprocess.run([sys.executable, "-c", PROBE], cwd=REPO, env=env, capture_output=True, text=True, timeout=900)
    assert out.returncode == 0, out.stderr[-3000:]
    result = json.loads(out.stdout.strip().splitlines()[-1])
    borrowed = set(result["borrowed"])
    equal = hard_ok = 0
    for space, chains in result["chains"].items():
        names = {dataset: [name for name, _ in chain] for dataset, chain in chains.items()}
        assert names["test"] == names["test-hard"], (space, names)
        equal += 1
        ours = {"DemonstrationWrapper", "EndeffectorDemonstrationWrapper", "MultiStepDemonstrationWrapper",
                "OraclePlannerDemonstrationWrapper", "FailAwareWrapper"}
        wrappers = [module for name, module in chains["test-hard"] if name in ours]
        assert wrappers, (space, chains["test-hard"])
        assert all(m.startswith("robomme_hard.") or m in borrowed for m in wrappers), (space, chains["test-hard"])
        hard_ok += 1
    print(f"WRAPPER_CHAIN=PASS action_spaces=4 chain_equal={equal} hard_modules_ok={hard_ok}")
