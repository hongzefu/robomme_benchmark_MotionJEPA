#!/usr/bin/env python3
"""轻量测试：四个 Unmask 环境 xhard 干扰容器「参与揭示 + 误抓即失败」（用户 2026-09-22 决策）。

不起 sapien 场景，用假 actor / 假 env 测共用件，再用 AST 锁住四个环境的挂接点：

* ``unmask_distractors.reveal_distractor_bins`` 与区域内容器走同一个 ``lift_and_drop_objects_back_to_original``：
  窗口前半段移到远处、半窗那一步放回原位；
* ``unmask_distractors.add_distractor_misgrasp_failure`` 只包装已有 ``failure_func`` 的条目、``solve`` 不动、
  原返回形态（ButtonUnmask 首抓的单元素列表）原样保留，任一干扰容器 z>0.15 即判失败；
* 四个环境的揭示调用与判失败包装都只在 xhard 分支，原三档的揭示循环逐字不变。

    uv run --no-sync python -m pytest tests/lightweight/test_v4_xhard_unmask_distractor_reveal.py -q
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests._shared.repo_paths import find_repo_root  # noqa: E402

REPO_ROOT = find_repo_root(__file__)
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

pytestmark = pytest.mark.lightweight

ENV_DIR = REPO_ROOT / "src" / "robomme" / "robomme_env"
FOUR_ENVS = ("VideoUnmask.py", "ButtonUnmask.py", "VideoUnmaskSwap.py", "ButtonUnmaskSwap.py")


class _Pose:
    def __init__(self, p):
        self.p = torch.tensor([p], dtype=torch.float32)
        self.q = torch.tensor([[1.0, 0.0, 0.0, 0.0]])


class _Actor:
    def __init__(self, xyz):
        self.pose = _Pose(xyz)

    def set_pose(self, pose):
        self.pose = _Pose(list(pose.p))

    def set_linear_velocity(self, v):
        pass

    def set_angular_velocity(self, v):
        pass


class _Env:
    def __init__(self, distractors):
        self.distractor_bins = distractors


def _z(actor):
    return float(actor.pose.p[0, 2])


def test_揭示时序与区域容器同一机制():
    from robomme.robomme_env.utils.statechange import lift_and_drop_objects_back_to_original
    from robomme.robomme_env.utils.unmask_distractors import reveal_distractor_bins

    distractors = [_Actor([0.35, 0.1, 0.052]), _Actor([-0.3, -0.3, 0.052])]
    regular = _Actor([0.0, 0.0, 0.052])
    env = _Env(distractors)
    trace = []
    for step in range(0, 70):
        lift_and_drop_objects_back_to_original(env, obj=regular, start_step=0, end_step=64, cur_step=step)
        reveal_distractor_bins(env, start_step=0, end_step=64, cur_step=step)
        trace.append((step, _z(regular), [_z(a) for a in distractors]))
    for step, z_reg, z_ds in trace:
        away = step < 32
        assert (z_reg > 5) == away
        assert all((z > 5) == away for z in z_ds), (step, z_ds)
    # 半窗那一步放回原位（xy 与 z 都等于初值）
    assert [float(v) for v in distractors[0].pose.p[0]] == pytest.approx([0.35, 0.1, 0.052])
    assert [float(v) for v in distractors[1].pose.p[0]] == pytest.approx([-0.3, -0.3, 0.052])


def test_没有干扰容器时揭示是空操作():
    from robomme.robomme_env.utils.unmask_distractors import reveal_distractor_bins

    reveal_distractor_bins(_Env([]), start_step=0, end_step=64, cur_step=3)
    reveal_distractor_bins(object(), start_step=0, end_step=64, cur_step=3)


def test_误抓判失败只包装已有failure_func且保留原形态():
    from robomme.robomme_env.utils.subgoal_evaluate_func import _coerce_failure_result
    from robomme.robomme_env.utils.unmask_distractors import add_distractor_misgrasp_failure

    distractors = [_Actor([0.35, 0.1, 0.052]), _Actor([-0.3, -0.3, 0.052])]
    env = _Env(distractors)
    solve_a = object()
    tasks = [
        {"name": "static", "failure_func": None, "solve": "hold"},
        # ButtonUnmask 首抓：返回单元素列表
        {"name": "pick 0", "failure_func": lambda: [torch.tensor([False])], "solve": solve_a},
        {"name": "put down", "failure_func": lambda: torch.tensor([False]), "solve": "putdown"},
        {"name": "预先算好的值", "failure_func": False, "solve": "x"},
    ]
    assert add_distractor_misgrasp_failure(env, tasks) == 3
    assert tasks[0]["failure_func"] is None
    assert tasks[1]["solve"] is solve_a
    first = tasks[1]["failure_func"]()
    assert isinstance(first, list) and isinstance(first[0], list) and len(first[0]) == 1
    assert not any(_coerce_failure_result(t["failure_func"]()) for t in tasks[1:])

    distractors[1].pose = _Pose([-0.3, -0.3, 0.2])  # 抬起第 2 个干扰容器（z>0.15）
    assert all(_coerce_failure_result(t["failure_func"]()) for t in tasks[1:])


def test_原判据为真时仍判失败():
    from robomme.robomme_env.utils.subgoal_evaluate_func import _coerce_failure_result
    from robomme.robomme_env.utils.unmask_distractors import add_distractor_misgrasp_failure

    tasks = [{"failure_func": lambda: torch.tensor([True])}]
    add_distractor_misgrasp_failure(_Env([_Actor([0.35, 0.1, 0.052])]), tasks)
    assert _coerce_failure_result(tasks[0]["failure_func"]())


def _step_and_scene(file_name):
    tree = ast.parse((ENV_DIR / file_name).read_text(encoding="utf-8"))
    funcs = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    return funcs


def _guarded_calls(func, callee):
    """返回 func 里所有调用 ``callee`` 的语句所在的 If 条件文本（未被 If 包住的记为 None）。"""
    found = []

    def visit(node, cond):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.If):
                visit_list(child.body, ast.unparse(child.test))
                visit_list(child.orelse, f"not ({ast.unparse(child.test)})")
            else:
                if isinstance(child, ast.Call) and ast.unparse(child.func) == callee:
                    found.append(cond)
                visit(child, cond)

    def visit_list(stmts, cond):
        for stmt in stmts:
            if isinstance(stmt, ast.If):
                visit_list(stmt.body, ast.unparse(stmt.test))
                visit_list(stmt.orelse, f"not ({ast.unparse(stmt.test)})")
            else:
                if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call) \
                        and ast.unparse(stmt.value.func) == callee:
                    found.append(cond)
                    continue
                visit(stmt, cond)

    visit_list(func.body, None)
    return found


XHARD_CONDS = {"xhard", "self._is_xhard", "self.difficulty == 'xhard'"}


@pytest.mark.parametrize("file_name", FOUR_ENVS)
def test_四环境揭示只在xhard且原揭示循环不变(file_name):
    funcs = _step_and_scene(file_name)
    step = funcs["step"]
    # V5（S3b，L14）：VideoUnmask / ButtonUnmask 改调停放版 reveal_distractor_bins_parked（签名相同）；
    # 两个 Swap 环境在 S3h 接入前仍调 V4 的 reveal_distractor_bins。两种都只许出现在 xhard 分支。
    conds = _guarded_calls(step, "reveal_distractor_bins") + _guarded_calls(step, "reveal_distractor_bins_parked")
    assert conds and all(c in XHARD_CONDS for c in conds), conds
    text = ast.unparse(step)
    # 原三档的区域内容器揭示仍在，且不在 xhard 条件下
    assert "lift_and_drop_objects_back_to_original(" in text
    assert all(c is None or c not in XHARD_CONDS for c in _guarded_calls(step, "lift_and_drop_objects_back_to_original"))


@pytest.mark.parametrize("file_name", FOUR_ENVS)
def test_四环境误抓判失败只在xhard(file_name):
    funcs = _step_and_scene(file_name)
    conds = []
    for func in funcs.values():
        conds += _guarded_calls(func, "add_distractor_misgrasp_failure")
    assert len(conds) == 1 and conds[0] in XHARD_CONDS, conds
