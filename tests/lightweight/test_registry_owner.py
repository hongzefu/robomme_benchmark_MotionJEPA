"""REGISTRY_OWNER／NAMESPACE_OWNER（0927 计划 §3.3、§6.3）：三种导入顺序各起一个子进程，16 个环境 id 与命名空间都归 robomme_hard。

阶段 1、2 期间 ``src/robomme`` 仍是改过的版本；设环境变量 ``ROBOMME_OFFICIAL_SRC=<官方 1fadc0ec worktree>/src``
可在「官方态」下跑（★ 闸门），阶段 3 回退之后直接跑。纯 CPU，不 reset。
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
import json, sys
order = sys.argv[1]
if order == "official_first":
    import robomme.robomme_env  # noqa: F401
    import robomme_hard
elif order == "hard_first":
    import robomme_hard
    import robomme.robomme_env  # noqa: F401
else:
    import robomme_hard.env_record_wrapper  # noqa: F401 子包先行
    import robomme_hard
import robomme
from mani_skill.utils.registration import REGISTERED_ENVS
from gymnasium.envs.registration import registry
owners = {uid: REGISTERED_ENVS[uid].cls.__module__ for uid in robomme_hard.robomme_env.ENV_IDS}
strays = robomme_hard.namespace_strays()
# 自检：把官方同名函数灌进一个环境模块，检测器必须报出来（证明 NAMESPACE_OWNER 不是空检查）
import robomme.robomme_env.utils as official_utils
mod = sys.modules["robomme_hard.robomme_env.MoveCube"]
saved = mod.spawn_random_cube
mod.spawn_random_cube = official_utils.spawn_random_cube
planted = robomme_hard.namespace_strays()
mod.spawn_random_cube = saved
print(json.dumps({"owners": owners, "strays": strays, "planted": planted,
                  "gym_ids": sorted(u for u in owners if u in registry), "robomme": robomme.__file__}))
"""


def _run(order: str) -> dict:
    env = dict(os.environ)
    official = os.environ.get("ROBOMME_OFFICIAL_SRC")
    if official:
        env["PYTHONPATH"] = official + os.pathsep + env.get("PYTHONPATH", "")
    out = subprocess.run([sys.executable, "-c", PROBE, order], cwd=REPO, env=env, capture_output=True, text=True,
                         timeout=240)
    assert out.returncode == 0, out.stderr[-3000:]
    return json.loads(out.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize("order", ["official_first", "hard_first", "subpackage_first"])
def test_registry_and_namespace_owner(order):
    result = _run(order)
    owners = result["owners"]
    assert len(owners) == 16
    assert all(module.startswith("robomme_hard.") for module in owners.values()), owners
    assert len(result["gym_ids"]) == 16
    assert result["strays"] == []
    assert any("spawn_random_cube" in item for item in result["planted"]), "命名空间检测器未能识别灌回的官方函数"
    official = os.environ.get("ROBOMME_OFFICIAL_SRC")
    if official:
        assert result["robomme"].startswith(official)
    print(f"REGISTRY_OWNER=PASS envs=16 owner=robomme_hard order={order}")
    print(f"NAMESPACE_OWNER=PASS envs=16 stray=0 order={order}")
