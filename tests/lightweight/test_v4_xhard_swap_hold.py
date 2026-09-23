#!/usr/bin/env python3
"""轻量测试：两个 UnmaskSwap 环境 xhard 交换期等待函数遇碰撞拒绝必须上抛（V4 步 3b，H1）。

背景：共享函数 ``utils/subgoal_planner_func.py::solve_hold_obj`` 用裸 ``except:`` 包住
``planner.open_gripper()``；xhard 乙通道打开运行时扫掠检查后，``env.step`` 抛出的
``BinCollisionError`` 会被吞掉、``elapsed_steps`` 不前进，等待循环永不结束。本文件用假 env / 假 planner
（不起 sapien 场景）锁定：

* ``unmask_swap_xhard.solve_hold_obj_xhard`` 遇 ``BinCollisionError`` 原样上抛，只吞 ``AttributeError``；
* 共享 ``solve_hold_obj`` 的吞异常缺陷仍在（记录现状，N12 不就地修）；
* ``solve_hold_obj_absTimestep``（ButtonUnmaskSwap xhard 的按钮后等待）不含 try，异常天然上抛；
* ``VideoUnmaskSwap`` 只有 xhard 把首个 static 任务换成专用等待，原三档的 static 任务仍是原函数。

    uv run --no-sync python -m pytest tests/lightweight/test_v4_xhard_swap_hold.py -q
"""

from __future__ import annotations

import ast
import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests._shared.repo_paths import find_repo_root  # noqa: E402

REPO_ROOT = find_repo_root(__file__)
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

pytestmark = pytest.mark.lightweight

ENV_DIR = REPO_ROOT / "src" / "robomme" / "robomme_env"


def _collision_error():
    from robomme.robomme_env.utils.bin_collision import BinCollisionError, CollisionRejection

    return BinCollisionError(
        CollisionRejection(reason="contact", stage="sweep", object_a="bin_0", object_b="bin_1",
                           shape_a=0, shape_b=0, gap_m=-0.01, sweep_index=0)
    )


class _FakeEnv:
    def __init__(self):
        self.elapsed_steps = 0


class _Planner:
    """``open_gripper``/``close_gripper`` 模拟一次 env.step：前 ``fail_times`` 次抛 ``error``（步数不前进），
    之后每次推进一步。``calls`` 用来断言「抛错后没有继续重试」。"""

    def __init__(self, env, error=None, fail_times=0):
        self.env = env
        self.error = error
        self.fail_times = fail_times
        self.calls = 0

    def _step(self):
        self.calls += 1
        if self.error is not None and self.calls <= self.fail_times:
            raise self.error
        self.env.elapsed_steps += 1

    open_gripper = _step
    close_gripper = _step


def test_专用等待遇碰撞拒绝立即上抛():
    from robomme.robomme_env.utils.bin_collision import BinCollisionError
    from robomme.robomme_env.utils.unmask_swap_xhard import solve_hold_obj_xhard

    env = _FakeEnv()
    # fail_times 很大：若函数吞异常，会重试到 fail_times 用完才返回，calls 远大于 1
    planner = _Planner(env, _collision_error(), fail_times=10_000)
    with pytest.raises(BinCollisionError):
        solve_hold_obj_xhard(env, planner, static_steps=5)
    assert planner.calls == 1
    assert env.elapsed_steps == 0


def test_专用等待正常等满且只吞AttributeError():
    from robomme.robomme_env.utils.unmask_swap_xhard import solve_hold_obj_xhard

    env = _FakeEnv()
    solve_hold_obj_xhard(env, _Planner(env), static_steps=7)
    assert env.elapsed_steps == 7

    env = _FakeEnv()
    planner = _Planner(env, AttributeError("planner 没有 open_gripper"), fail_times=3)
    solve_hold_obj_xhard(env, planner, static_steps=4)
    assert env.elapsed_steps == 4 and planner.calls == 7


def test_共享solve_hold_obj仍吞碰撞拒绝_记录现状():
    """N12：共享函数不就地修。这里锁住现状，证明 xhard 必须绕开它（若日后有人修了共享函数，本断言提醒同步报告）。"""
    from robomme.robomme_env.utils.subgoal_planner_func import solve_hold_obj

    env = _FakeEnv()
    planner = _Planner(env, _collision_error(), fail_times=3)
    solve_hold_obj(env, planner, static_steps=2)  # 不抛：前 3 次碰撞拒绝全被吞掉
    assert planner.calls == 5 and env.elapsed_steps == 2


def test_absTimestep等待不含try_异常天然上抛():
    from robomme.robomme_env.utils.bin_collision import BinCollisionError
    from robomme.robomme_env.utils.subgoal_planner_func import solve_hold_obj_absTimestep

    source = (ENV_DIR / "utils" / "subgoal_planner_func.py").read_text(encoding="utf-8")
    func = next(n for n in ast.walk(ast.parse(source))
                if isinstance(n, ast.FunctionDef) and n.name == "solve_hold_obj_absTimestep")
    assert not any(isinstance(n, ast.Try) for n in ast.walk(func))

    class _TcpEnv(_FakeEnv):
        class agent:  # noqa: N801 - 模拟 env.agent.tcp.pose
            class tcp:  # noqa: N801
                pose = None

    env = _TcpEnv()
    planner = _Planner(env, _collision_error(), fail_times=10_000)
    with pytest.raises(BinCollisionError):
        solve_hold_obj_absTimestep(env, planner, absTimestep=5)
    assert planner.calls == 1


def _function_node(file_name, func_name):
    tree = ast.parse((ENV_DIR / file_name).read_text(encoding="utf-8"))
    return next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == func_name)


def _load_scene_text(file_name, func_name):
    return ast.unparse(_function_node(file_name, func_name))


def test_VideoUnmaskSwap只有xhard换用专用等待():
    func = _function_node("VideoUnmaskSwap.py", "_load_scene")
    text = ast.unparse(func)
    # 原三档：static 任务的解法逐字仍是共享 solve_hold_obj
    assert "'solve': lambda env, planner: solve_hold_obj(env, planner, static_steps=self.swap_schedule[-1][3])" in text
    # xhard：在 `if self._is_xhard:` 分支里整体替换首个任务（static）的解法，且全函数只此一处引用
    replace = "tasks[0]['solve'] = lambda env, planner: solve_hold_obj_xhard(env, planner, static_steps=self.swap_schedule[-1][3])"
    guarded = [
        node for node in ast.walk(func)
        if isinstance(node, ast.If) and ast.unparse(node.test) == "self._is_xhard"
        and any(ast.unparse(stmt) == replace for stmt in node.body)
    ]
    assert len(guarded) == 1
    assert text.count("solve_hold_obj_xhard") == 1


def test_ButtonUnmaskSwap按钮后等待走absTimestep():
    text = _load_scene_text("ButtonUnmaskSwap.py", "_solve_press_then_wait_swaps")
    assert "solve_hold_obj_absTimestep(env, planner, absTimestep=self.swap_schedule[-1][3])" in text
    assert "solve_hold_obj(" not in text
    assert "try" not in text
