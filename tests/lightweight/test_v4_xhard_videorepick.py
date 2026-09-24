#!/usr/bin/env python3
"""轻量测试：V4 步 3b VideoRepick 的 xhard 档（NEWTASK_RELEASE_V4_PLAN 2.13 / 2.2③ / D5）。

纯结构性检查，不起 sapien 场景：

* 原三档的 ``config_*``、``NATIVE_SAMPLING.parameters.num_repeats`` 与去掉 ``xhard`` 子键后的 decision
  与 V4 改动前逐字相同；
* xhard 的新值（6 块 clutter、pick times 半开 [4,7)、swap [8,12]、同色任意色值；V5 起加最小中心距与搭档规划）只挂在 ``xhard`` 子键下，
  守卫放行收窄、拒绝改动原三档；
* D5：四处几何检查的开关统一为 ``_sweep_checks_enabled``（甲通道或 xhard 乙通道），原三档乙通道仍关；
* xhard 不接受链路甲的 ``episode_spec``（在 ``super().__init__`` 之前就拒绝）。

    uv run --no-sync python -m pytest tests/lightweight/test_v4_xhard_videorepick.py -q
"""

from __future__ import annotations

import ast
import copy
import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests._shared.repo_paths import find_repo_root  # noqa: E402

REPO_ROOT = find_repo_root(__file__)
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

pytestmark = pytest.mark.lightweight

# 包的 __init__ 做了 ``from .VideoRepick import *``，同名类会遮住子模块属性，必须按模块路径取
MODULE = importlib.import_module("robomme.robomme_env.VideoRepick")
CLS = MODULE.VideoRepick
SOURCE = (REPO_ROOT / "src" / "robomme" / "robomme_env" / "VideoRepick.py").read_text(encoding="utf-8")

from robomme.robomme_env.utils.sampling_config import (  # noqa: E402
    SamplingConfigError,
    _strip_xhard,
    assert_native_decision,
)

# V4 改动前（00e2ef4）原三档的逐字值
PRE_V4_THREE = {
    "easy": {"cube": 3, "swap_min": 1, "swap_max": 2},
    "medium": {"cube": 3, "swap_min": 2, "swap_max": 3},
    "hard": {"cluster": True, "swap": None, "swap_min": 0, "swap_max": 0},
}
PRE_V4_DECISION_THREE = {
    "layout_mode": "native_by_difficulty",
    "num_repeats_range": {"low": 1, "high_exclusive": 4},
    "block_color_policy": "native_by_difficulty",
    "swap": {
        "hard": {"swap_min": 0, "swap_max": 0},
        "easy": {"swap_min": 1, "swap_max": 2},
        "medium": {"swap_min": 2, "swap_max": 3},
    },
}


def _decision():
    return MODULE.native_blocks(CLS)[0]


def test_原三档配置与原值快照逐字不变():
    for name, expected in PRE_V4_THREE.items():
        assert CLS.configs[name] == expected
    assert MODULE.NATIVE_SAMPLING["parameters"]["num_repeats"] == {
        "sampler": "torch.randint", "low": 1, "high_exclusive": 4, "shape": [1],
    }


def test_去掉xhard后decision与改动前相同():
    assert _strip_xhard(_decision()) == PRE_V4_DECISION_THREE


def test_xhard_新值只挂在xhard子键下():
    decision = _decision()
    assert decision["num_repeats_range"]["xhard"] == {"low": 4, "high_exclusive": 7}  # pick times [4,6] 半开
    assert decision["swap"]["xhard"] == {"swap_min": 8, "swap_max": 12}
    layout = decision["xhard"]["layout"]
    # V5（计划 2.15，L50/L51）：区域不动，新增 6 块两两最小中心距 0.12 m
    assert layout == {"mode": "clutter", "cube_count": 6, "region_center": [-0.1, 0.0], "region_half_size": [0.2, 0.25],
                      "min_center_dist_m": 0.12}
    # V5（L47 a'、L48、L49、L54）：发起者 k%6 轮转、reset 规划搭档（3 个最近可行、5 mm 余量、按钮作障碍）
    assert decision["xhard"]["swap_plan"] == {
        "initiator_rule": "target_then_randperm_k_mod_cube_count",
        "partner_rule": "reset_plan_nearest_feasible",
        "nearest_k": 3, "sweep_margin_m": 0.005, "button_obstacle": True,
    }
    color = decision["xhard"]["block_color"]
    assert color["policy"] == "same_color_hsv_floor"
    assert (color["h_range"], color["s_range"], color["v_range"]) == ([0.0, 1.0], [0.5, 1.0], [0.4, 1.0])
    # A7：旧 xhard {cube 3, swap [4,5]} 已被覆盖
    assert CLS.configs["xhard"]["cube"] == 6
    assert (CLS.configs["xhard"]["swap_min"], CLS.configs["xhard"]["swap_max"]) == (8, 12)


def test_守卫放行xhard收窄且拒绝改原三档():
    default = _decision()
    narrowed = copy.deepcopy(default)
    narrowed["swap"]["xhard"] = {"swap_min": 12, "swap_max": 12}
    narrowed["num_repeats_range"]["xhard"] = {"low": 4, "high_exclusive": 5}
    narrowed["xhard"]["layout"]["cube_count"] = 6
    assert_native_decision(narrowed, default, "VideoRepick")
    resolved = MODULE._resolve_sampling_config(CLS, {"decision": narrowed, "native": MODULE.native_blocks(CLS)[1]})
    assert resolved["decision"]["swap"]["xhard"] == {"swap_min": 12, "swap_max": 12}
    for mutate in (
        lambda d: d["swap"]["medium"].__setitem__("swap_max", 4),
        lambda d: d["num_repeats_range"].__setitem__("high_exclusive", 7),
        lambda d: d["xhard"].__setitem__("extra", 1),
    ):
        bad = copy.deepcopy(default)
        mutate(bad)
        with pytest.raises(SamplingConfigError):
            assert_native_decision(bad, default, "VideoRepick")


@pytest.mark.parametrize(
    "episode_spec,difficulty,expected",
    [
        (None, "easy", False), (None, "medium", False), (None, "hard", False),
        (None, "xhard", True),
        ({"task": "VideoRepick"}, "easy", True), ({"task": "VideoRepick"}, "medium", True),
    ],
)
def test_D5_开关只在甲通道或xhard乙通道打开(episode_spec, difficulty, expected):
    fake = SimpleNamespace(_episode_spec=episode_spec, difficulty=difficulty)
    assert CLS._sweep_checks_enabled(fake) is expected


def test_D5_四处检查都改走统一开关():
    tree = ast.parse(SOURCE)
    funcs = {node.name: node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
    for name in ("_before_simulation_step", "_after_simulation_step", "_initialize_episode", "step"):
        text = ast.unparse(funcs[name])
        assert "_sweep_checks_enabled()" in text, name
    for name in ("_before_simulation_step", "_after_simulation_step"):
        assert "self._episode_spec is None" not in ast.unparse(funcs[name]), name
    step = ast.unparse(funcs["step"])
    # 搭档身份核验仍只在甲通道（只有甲的规格预写了搭档）；扫掠检查走统一开关
    assert "if self._episode_spec is not None:\n" in step and "self._verify_swap_binding" in step
    assert step.index("_sweep_checks_enabled()") < step.index("self._check_swap_sweep_from_actual")


def test_xhard_走独立方法且原分支不被改写():
    tree = ast.parse(SOURCE)
    funcs = {node.name: node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
    scene = ast.unparse(funcs["_load_scene"])
    assert "self._load_cubes_xhard(avoid)" in scene
    # 原三档的颜色名注入分支（甲的旧通道）保留不动
    assert "[item['name'] for item in options].index(spec['objects']['color'])" in scene
    xhard = ast.unparse(funcs["_load_cubes_xhard"])
    for path in ("objects.color_rgb", "objects.target", "objects.swap_initiators_remaining",
                 "objects.cube_count.requested", "objects.cube_count.actual", "layout.cubes."):
        assert path in xhard, path
    assert "SceneGenerationError" in xhard


def test_xhard_拒绝链路甲的episode_spec():
    with pytest.raises(ValueError, match="链路甲"):
        CLS(seed=0, difficulty="xhard", episode_spec={"task": "VideoRepick"})


@pytest.mark.parametrize("n", [8, 10, 12])
def test_xhard_交换调度八到十二次首尾相接(n):
    env = SimpleNamespace(swap_times=n)
    for k in range(n):
        setattr(env, f"swap_pair{k+1}_idx1", f"init{k % 6}")
        setattr(env, f"swap_pair{k+1}_idx2", None)
    CLS._refresh_swap_schedule(env)
    assert len(env.swap_schedule) == n
    assert [s[2] for s in env.swap_schedule] == [400 + 50 * k for k in range(n)]
    assert all(env.swap_schedule[k][3] == env.swap_schedule[k + 1][2] for k in range(n - 1))
    # V5 L47 a'（原 V4 B12「发起者 3 个」作废）：6 块按 k%6 轮流发起，n≥8 时 6 块都当过发起者
    assert {s[0] for s in env.swap_schedule} == {f"init{j}" for j in range(6)}


class _FakeEnv:
    def __init__(self):
        self.elapsed_steps = 0


class _Planner:
    def __init__(self, env, error=None):
        self.env, self.error = env, error

    def open_gripper(self):
        if self.error is not None:
            raise self.error
        self.env.elapsed_steps += 1


def test_xhard_等待函数不吞碰撞拒绝():
    """solve_hold_obj 的裸 except 会吞掉 D5 的 BinCollisionError 并死循环；xhard 专用版只吞 AttributeError。"""
    from robomme.robomme_env.utils.bin_collision import BinCollisionError

    env = _FakeEnv()
    MODULE._solve_hold_obj_xhard(env, _Planner(env), static_steps=5)
    assert env.elapsed_steps == 5
    with pytest.raises(RuntimeError):
        MODULE._solve_hold_obj_xhard(env, _Planner(env, RuntimeError("碰撞")), static_steps=5)
    assert issubclass(BinCollisionError, RuntimeError)


def test_只有xhard换用专用等待函数():
    tree = ast.parse(SOURCE)
    init = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_initialize_episode")
    text = ast.unparse(init)
    assert "hold_fn = _solve_hold_obj_xhard if self.difficulty == 'xhard' else solve_hold_obj" in text
    assert text.count("hold_fn(env, planner") == 2
