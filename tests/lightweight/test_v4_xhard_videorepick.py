# robomme_hard：本测试测新值档／改动行为，阶段 3 起 src/robomme 回到官方 1fadc0ec，故改测 robomme_hard（0927 计划 R8 第③类）
#!/usr/bin/env python3
"""轻量测试：VideoRepick 原三档冻结、V6 四档新值与 D5 扫掠开关。

纯结构性检查，不起 sapien 场景：

* 原三档的 ``config_*``、``NATIVE_SAMPLING.parameters.num_repeats`` 与去掉新值子键后的 decision
  与 V4 改动前逐字相同；
* xhard1～xhard4 的块数、repick 与 swap 次数按定稿分档，同色任意色值、最小中心距和 S5 机制沿用；
  守卫放行收窄、拒绝改动原三档；
* D5：四处几何检查的开关统一为 ``_sweep_checks_enabled``（甲通道或新值档乙通道），原三档乙通道仍关；
* 新值档不接受链路甲的 ``episode_spec``（在 ``super().__init__`` 之前就拒绝）。

    PYTHONPATH="$PWD/src" uv run --project /data/hongzefu/robomme_benchmark_MotionJEPANewTask --no-sync python -m pytest tests/lightweight/test_v4_xhard_videorepick.py -q
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
MODULE = importlib.import_module("robomme_hard.robomme_env.VideoRepick")
from robomme_hard.robomme_env.utils import swap_uniform  # noqa: E402  V6 S5 申报值
CLS = MODULE.VideoRepick
SOURCE = (REPO_ROOT / "src" / "robomme_hard" / "robomme_env" / "VideoRepick.py").read_text(encoding="utf-8")

from robomme_hard.robomme_env.utils.sampling_config import (  # noqa: E402
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


def test_去掉新值后decision与改动前相同():
    assert _strip_xhard(_decision()) == PRE_V4_DECISION_THREE


def test_四档新值decision含逐档配置与S5():
    decision = _decision()
    # V7 定值（0928 方案 §3.2.2）：块数 4/5/6/7 不变，swap 4/6/8/10 定值，repick 2/3/4/5 定值
    expected = {"xhard1": (4, 4, 4, 2, 3), "xhard2": (5, 6, 6, 3, 4),
                "xhard3": (6, 8, 8, 4, 5), "xhard4": (7, 10, 10, 5, 6)}
    for tier, (cubes, swap_min, swap_max, repeat_low, repeat_high) in expected.items():
        layout = decision[tier]["layout"]
        assert layout == {"mode": "clutter", "cube_count": cubes, "region_center": [-0.1, 0.0],
                          "region_half_size": [0.2, 0.25], "min_center_dist_m": 0.12}
        assert decision["num_repeats_range"][tier] == {"low": repeat_low, "high_exclusive": repeat_high}
        assert decision["swap"][tier] == {"swap_min": swap_min, "swap_max": swap_max}
        plan = decision[tier]["swap_plan"]
        assert plan["initiator_rule"] == "s5_balanced_pair"
        assert plan["partner_rule"] == "s5_balanced_greedy"
        assert plan["s5"] == swap_uniform.inner_swap_plan_cfg(require_connected=False, score="sum_max")
        assert (plan["sweep_margin_m"], plan["button_obstacle"]) == (0.005, True)
        color = decision[tier]["block_color"]
        assert color["policy"] == "same_color_hsv_floor"
        assert (color["h_range"], color["s_range"], color["v_range"]) == ([0.0, 1.0], [0.5, 1.0], [0.4, 1.0])


def test_守卫放行新值收窄且拒绝改原三档():
    default = _decision()
    narrowed = copy.deepcopy(default)
    narrowed["swap"]["xhard1"] = {"swap_min": 4, "swap_max": 4}
    narrowed["num_repeats_range"]["xhard1"] = {"low": 2, "high_exclusive": 3}
    narrowed["xhard1"]["layout"]["cube_count"] = 4
    assert_native_decision(narrowed, default, "VideoRepick")
    resolved = MODULE._resolve_sampling_config(CLS, {"decision": narrowed, "native": MODULE.native_blocks(CLS)[1]})
    assert resolved["decision"]["swap"]["xhard1"] == {"swap_min": 4, "swap_max": 4}
    for mutate in (
        lambda d: d["swap"]["medium"].__setitem__("swap_max", 4),
        lambda d: d["num_repeats_range"].__setitem__("high_exclusive", 7),
        lambda d: d["xhard1"].__setitem__("extra", 1),
    ):
        bad = copy.deepcopy(default)
        mutate(bad)
        with pytest.raises(SamplingConfigError):
            assert_native_decision(bad, default, "VideoRepick")


@pytest.mark.parametrize(
    "episode_spec,difficulty,expected",
    [
        (None, "easy", False), (None, "medium", False), (None, "hard", False),
        (None, "xhard4", True),
        ({"task": "VideoRepick"}, "easy", True), ({"task": "VideoRepick"}, "medium", True),
    ],
)
def test_D5_开关只在甲通道或新值档乙通道打开(episode_spec, difficulty, expected):
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


def test_新值档走独立方法且原分支不被改写():
    tree = ast.parse(SOURCE)
    funcs = {node.name: node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
    scene = ast.unparse(funcs["_load_scene"])
    assert "self._load_cubes_newvalue(avoid)" in scene
    # 原三档的颜色名注入分支（甲的旧通道）保留不动
    assert "[item['name'] for item in options].index(spec['objects']['color'])" in scene
    xhard = ast.unparse(funcs["_load_cubes_newvalue"])
    for path in ("objects.color_rgb", "objects.target", "objects.swap_initiators_remaining",
                 "objects.cube_count.requested", "objects.cube_count.actual", "layout.cubes."):
        assert path in xhard, path
    assert "SceneGenerationError" in xhard


def test_新值档拒绝链路甲的episode_spec():
    with pytest.raises(ValueError, match="链路甲"):
        CLS(seed=0, difficulty="xhard4", episode_spec={"task": "VideoRepick"})


# V7 定值 swap 4/6/8/10；「6 块都当过发起者」要求 n ≥ 6，故取 6/8/10（调度函数本身与档位无关）
@pytest.mark.parametrize("n", [6, 8, 10])
def test_xhard_交换调度六到十次首尾相接(n):
    env = SimpleNamespace(swap_times=n)
    for k in range(n):
        setattr(env, f"swap_pair{k+1}_idx1", f"init{k % 6}")
        setattr(env, f"swap_pair{k+1}_idx2", None)
    CLS._refresh_swap_schedule(env)
    assert len(env.swap_schedule) == n
    assert [s[2] for s in env.swap_schedule] == [400 + 50 * k for k in range(n)]
    assert all(env.swap_schedule[k][3] == env.swap_schedule[k + 1][2] for k in range(n - 1))
    # V5 L47 a'（原 V4 B12「发起者 3 个」作废）：6 块按 k%6 轮流发起，n≥6 时 6 块都当过发起者
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
    from robomme_hard.robomme_env.utils.bin_collision import BinCollisionError

    env = _FakeEnv()
    MODULE._solve_hold_obj_xhard(env, _Planner(env), static_steps=5)
    assert env.elapsed_steps == 5
    with pytest.raises(RuntimeError):
        MODULE._solve_hold_obj_xhard(env, _Planner(env, RuntimeError("碰撞")), static_steps=5)
    assert issubclass(BinCollisionError, RuntimeError)


def test_只有新值档换用专用等待函数():
    tree = ast.parse(SOURCE)
    init = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_initialize_episode")
    text = ast.unparse(init)
    assert "hold_fn = _solve_hold_obj_xhard if is_newvalue_difficulty(self.difficulty) else solve_hold_obj" in text
    assert text.count("hold_fn(env, planner") == 2
