"""三个交换任务 ``_refresh_swap_schedule`` 通式与原三分支逐项等价（xhard 扩展 S5／S8 的关闭态证明）。

不加载仿真：用生成入口的 AST 工具把方法源码抽出来，在 ``SimpleNamespace`` 上执行。
原三分支（10.56 及之前）对 n=1/2/3 的产出手写成期望表；n=0 时原分支不命中、不赋值。
V4（A7 作废旧 xhard「4~5 次、每段 50 帧」）：两个 UnmaskSwap 的 xhard 为 swap 速度 ×1.5
⇒ 每段 ``round(50/1.5)=33`` 帧、首段起点仍 64；VideoUnmaskSwap swap [8,12]、ButtonUnmaskSwap [6,8]。
两个 UnmaskSwap 的窗口从实例属性 ``swap_window_start`` / ``swap_window_steps`` 读（构造器按难度算好）。

    uv run --no-sync python -m pytest tests/lightweight/test_swap_schedule_generic.py -q
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
for extra in (REPO_ROOT, SCRIPTS_DIR):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import generate_dataset_newseed as generator  # noqa: E402

pytestmark = pytest.mark.lightweight

SOURCES = {
    "VideoUnmaskSwap": REPO_ROOT / "src" / "robomme" / "robomme_env" / "VideoUnmaskSwap.py",
    "VideoRepick": REPO_ROOT / "src" / "robomme" / "robomme_env" / "VideoRepick.py",
    "ButtonUnmaskSwap": REPO_ROOT / "src" / "robomme" / "robomme_env" / "ButtonUnmaskSwap.py",
}
UNMASK_SWAP = ["VideoUnmaskSwap", "ButtonUnmaskSwap"]


def _method(task: str):
    tree = ast.parse(SOURCES[task].read_text(encoding="utf-8"))
    class_def = generator._class_def(tree, task)
    func = generator._func_def(class_def, "_refresh_swap_schedule")
    module = ast.Module(body=[func], type_ignores=[])
    namespace: dict = {}
    exec(compile(module, str(SOURCES[task]), "exec"), namespace)
    return namespace["_refresh_swap_schedule"]


def _env(n: int, slots: int = 12, window: int = 50) -> SimpleNamespace:
    # 原三档：swap_window_start=64、swap_window_steps=50（构造器在倍率 1 时原样给出）
    env = SimpleNamespace(swap_times=n, swap_window_start=64, swap_window_steps=window)
    for k in range(1, slots + 1):
        setattr(env, f"swap_pair{k}_idx1", f"a{k}")
        setattr(env, f"swap_pair{k}_idx2", f"b{k}" if k % 2 else None)
    return env


def _legacy_expected(env: SimpleNamespace, base: int) -> list[tuple]:
    """10.56 版三个硬分支的字面产出。"""
    n = env.swap_times
    pairs = [(getattr(env, f"swap_pair{k}_idx1"), getattr(env, f"swap_pair{k}_idx2")) for k in (1, 2, 3)]
    if n == 1:
        return [(pairs[0][0], pairs[0][1], base, base + 50)]
    if n == 2:
        return [(pairs[0][0], pairs[0][1], base, base + 50), (pairs[1][0], pairs[1][1], base + 50, base + 50 * 2)]
    if n == 3:
        return [
            (pairs[0][0], pairs[0][1], base, base + 50),
            (pairs[1][0], pairs[1][1], base + 50, base + 50 * 2),
            (pairs[2][0], pairs[2][1], base + 50 * 2, base + 50 * 3),
        ]
    raise AssertionError("原分支只覆盖 1/2/3")


@pytest.mark.parametrize("task", UNMASK_SWAP)
@pytest.mark.parametrize("n", [1, 2, 3])
def test_unmask_通式与原三分支逐项相同(task, n):
    env = _env(n)
    _method(task)(env)
    assert env.swap_schedule == _legacy_expected(env, 64)


@pytest.mark.parametrize("n", [1, 2, 3])
@pytest.mark.parametrize("start", [400, 173])
def test_repick_通式与原三分支逐项相同(n, start):
    env = _env(n)
    _method("VideoRepick")(env, start)
    assert env.swap_schedule == _legacy_expected(env, start)


def test_repick_默认起点仍是400():
    env = _env(2)
    _method("VideoRepick")(env)
    assert env.swap_schedule[0][2] == 400


@pytest.mark.parametrize("task", ["VideoUnmaskSwap", "VideoRepick", "ButtonUnmaskSwap"])
def test_零次时不赋值(task):
    env = _env(0)
    _method(task)(env)
    assert not hasattr(env, "swap_schedule")


@pytest.mark.parametrize("n", [4, 5])
def test_repick_四五次首尾相接每段五十帧(n):
    # VideoRepick 的调度仍是每段 50 帧（其 xhard 语义由 VideoRepick 自己的步 3b 维护）；这里只验通式
    env = _env(n)
    _method("VideoRepick")(env)
    schedule = env.swap_schedule
    assert len(schedule) == n
    for k, (a, b, start, end) in enumerate(schedule):
        assert (a, b) == (getattr(env, f"swap_pair{k+1}_idx1"), getattr(env, f"swap_pair{k+1}_idx2"))
        assert (start, end) == (400 + 50 * k, 400 + 50 * (k + 1))
    assert all(schedule[k][3] == schedule[k + 1][2] for k in range(n - 1))


@pytest.mark.parametrize("task,n", [("VideoUnmaskSwap", 8), ("VideoUnmaskSwap", 12), ("ButtonUnmaskSwap", 6), ("ButtonUnmaskSwap", 8)])
def test_xhard_v4_首尾相接每段三十三帧(task, n):
    """V4 xhard 端点：swap 速度 ×1.5 ⇒ 每段 33 帧，首段起点 64，发起者槽位按序取。"""
    env = _env(n, window=33)
    _method(task)(env)
    schedule = env.swap_schedule
    assert len(schedule) == n
    for k, (a, b, start, end) in enumerate(schedule):
        assert (a, b) == (getattr(env, f"swap_pair{k+1}_idx1"), getattr(env, f"swap_pair{k+1}_idx2"))
        assert (start, end) == (64 + 33 * k, 64 + 33 * (k + 1))
    assert all(schedule[k][3] == schedule[k + 1][2] for k in range(n - 1))
    assert schedule[-1][3] == 64 + 33 * n


@pytest.mark.parametrize("task", ["VideoUnmaskSwap", "VideoRepick", "ButtonUnmaskSwap"])
def test_源码里不再有按次数写死的分支(task):
    source = SOURCES[task].read_text(encoding="utf-8")
    assert "self.swap_times==1" not in source and "self.swap_times==3" not in source
    for name in ("config_easy", "config_medium", "config_hard", "config_xhard"):
        assert re.search(rf"^\s+{name}\s*=", source, re.M), name  # 源码里 config_medium= 没有空格，按正则找
