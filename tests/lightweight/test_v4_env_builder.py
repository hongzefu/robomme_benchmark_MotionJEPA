#!/usr/bin/env python3
"""轻量测试：推理侧 ``BenchmarkEnvBuilder.from_v4_specs``（计划第四节 4.2，步 6）。

不起环境，只验构建器的三条约束：runtime 四项不等即拒绝；episode 取值只来自快照（selected）；
recover 分档与生成侧同规则；原有 metadata 路径不带 ``_v4``。

    uv run --no-sync python -m pytest tests/lightweight/test_v4_env_builder.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests._shared.repo_paths import find_repo_root  # noqa: E402

REPO_ROOT = find_repo_root(__file__)
for extra in (REPO_ROOT, REPO_ROOT / "src", REPO_ROOT / "scripts"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from robomme.env_record_wrapper.episode_config_resolver import BenchmarkEnvBuilder  # noqa: E402
from scripts.parity import v4_specs as V  # noqa: E402

HEADER = {
    "runtime": dict(V.RUNTIME),
    "sampling_config": {"RouteStick": {"decision": {}, "native": {"parameters": {}, "positions": {}}}},
    "recovery_rule": dict(V.RECOVERY_RULE),
}
SPECS = {f"RouteStick/{e}": {"task": "RouteStick", "episode": e, "seed": V.seed_for("RouteStick", e, 0),
                             "difficulty": "xhard", "spec": {"k": e}} for e in (0, 3, 6)}


def test_runtime_mismatch_rejected() -> None:
    bad = {**HEADER, "runtime": {**V.RUNTIME, "obs_mode": "rgb"}}
    with pytest.raises(ValueError, match="runtime"):
        BenchmarkEnvBuilder.from_v4_specs("RouteStick", bad, SPECS)


def test_episodes_and_kwargs_come_from_snapshot() -> None:
    builder = BenchmarkEnvBuilder.from_v4_specs("RouteStick", HEADER, SPECS)
    assert builder.v4_episodes() == [0, 3, 6]
    assert builder.get_episode_num() == 3
    for episode in (0, 3, 6):
        kwargs = builder._v4_kwargs(episode)
        assert kwargs["seed"] == SPECS[f"RouteStick/{episode}"]["seed"]
        assert kwargs["native_episode_spec"] == {"k": episode}
        assert kwargs.get("robomme_failure_recovery_mode") == V.recovery_mode(episode)
    assert builder.resolve_episode(3) == (SPECS["RouteStick/3"]["seed"], "xhard")
    with pytest.raises(KeyError):
        builder._v4_kwargs(1)  # 落选候选不可评


def test_metadata_path_untouched() -> None:
    builder = BenchmarkEnvBuilder("RouteStick", dataset="test")
    assert builder._v4 is None
    assert builder.get_episode_num() > 0
