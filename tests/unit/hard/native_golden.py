"""原三档（easy／medium／hard）离线导出摘要的计算与金标准生成。

摘要 = 对 16 任务 × 3 档 × 种子 ``SEEDS``，按评估链参数（runtime 四项 + seed + difficulty，不传
sampling_config 与规格，即原生分支）离线跑真实 ``_load_scene`` + 两次 ``_initialize_episode``，取导出规格文档的
``hard_specs.digest``（剔除键序影响的 canonical JSON 的 sha256）；建场抛异常的记 ``error:<异常类名>``
（例：VideoPlaceOrder 原三档的布局失败按 H2 保持官方现状，表现为 TypeError，金标准照实钉住）。

金标准文件 ``native_golden.json`` 由本模块在维护计划 BASE（``93014f27``，T4 未改任何生产代码）上生成::

    UV_PROJECT_ENVIRONMENT=<主检出 .venv> PYTHONPATH=<worktree>/src:<worktree> \\
        uv run --no-sync python -m tests.unit.hard.native_golden --write

之后生产代码改动若改变了原三档的任何取值点、随机流消费或异常类型，``test_native_golden.py`` 即失败；
确属有意的改动须重新生成并在提交说明里写明原因。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from robomme_hard.env_record_wrapper.hard_specs import digest

from . import offline_scene as O
from .world import World, cpu_world

NATIVE_TIERS = ("easy", "medium", "hard")
SEEDS = (101, 202)
GOLDEN = Path(__file__).with_name("native_golden.json")


def key(task: str, tier: str, seed: int) -> str:
    return f"{task}/{tier}/{seed}"


def summarize(task: str, tier: str, seed: int) -> str:
    try:
        with cpu_world():
            env = O.make_offline(task, seed=seed, difficulty=tier)
            World.from_env(env)
    except Exception as exc:  # noqa: BLE001 — 异常类型本身就是被钉住的行为
        return f"error:{type(exc).__name__}"
    doc = env._spec.to_dict()
    if doc["spec_kind"] != "native-parity/1":
        return f"kind:{doc['spec_kind']}"
    return digest(doc)


def compute() -> dict[str, str]:
    return {key(t, tier, s): summarize(t, tier, s) for t in O.ALL_TASKS for tier in NATIVE_TIERS for s in SEEDS}


def main(argv: list[str]) -> int:
    table = compute()
    if "--write" in argv:
        GOLDEN.write_text(json.dumps({
            "base_commit": "93014f27",
            "seeds": list(SEEDS),
            "tiers": list(NATIVE_TIERS),
            "digests": table,
        }, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        print(f"NATIVE_GOLDEN=WRITTEN entries={len(table)} path={GOLDEN}")
    else:
        print(json.dumps(table, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
