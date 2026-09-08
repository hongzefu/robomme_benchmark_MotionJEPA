"""核对原版继承、注册隔离与接口观测，不构建仿真环境。"""

import ast
import copy
import importlib
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "src" / "robomme_icl"
TASKS = ("BinFill", "RouteStick", "VideoUnmaskSwap", "VideoRepick")


def _is_legacy(name):
    return name == "robomme" or name.startswith("robomme.")


def test_all_legacy_imports_are_confined_to_native():
    violations = []
    for path in sorted(SOURCE.rglob("*.py")):
        relative = path.relative_to(SOURCE)
        if relative.parts[0] in {"native", "legacy_bridge"}:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            modules = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and not node.level:
                modules = [node.module or ""]
            elif isinstance(node, ast.Call) and node.args:
                target = node.func
                dynamic = (
                    isinstance(target, ast.Name)
                    and target.id in {"__import__", "import_module"}
                ) or (
                    isinstance(target, ast.Attribute) and target.attr == "import_module"
                )
                if (
                    dynamic
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)
                ):
                    modules = [node.args[0].value]
            violations.extend(
                f"{relative}:{node.lineno}: {module}"
                for module in modules
                if _is_legacy(module)
            )
    assert not violations, "原版导入越过 legacy_bridge：\n" + "\n".join(violations)


@pytest.fixture(scope="module")
def registered_classes():
    # 显式先导入旧包，随后注册新版；只访问注册表，不调用 gym.make。
    importlib.import_module("robomme.robomme_env")
    from mani_skill.utils.registration import REGISTERED_ENVS

    before = {
        name: record.cls
        for name, record in REGISTERED_ENVS.items()
        if record.cls.__module__.startswith("robomme.robomme_env.")
    }
    assert len(before) == 16
    from robomme_icl.envs import register_envs

    register_envs()
    first = {name: record.cls for name, record in REGISTERED_ENVS.items()}
    register_envs()
    second = {name: record.cls for name, record in REGISTERED_ENVS.items()}
    return before, first, second


def test_old_sixteen_ids_and_classes_are_unchanged(registered_classes):
    before, first, second = registered_classes
    for name, cls in before.items():
        assert first[name] is cls
        assert second[name] is cls
    assert first == second


def test_four_new_ids_inherit_corresponding_native_task(registered_classes):
    before, first, _ = registered_classes
    for task in TASKS:
        cls = first[f"RoboMME-ICL/{task}-v0"]
        assert cls.__module__.startswith("robomme_icl.envs.")
        assert cls.__bases__ == (before[task],)
        for method in (
            "step",
            "evaluate",
            "_initialize_episode",
            "_default_sensor_configs",
        ):
            assert getattr(cls, method) is getattr(before[task], method)
        assert (
            not {
                "step",
                "evaluate",
                "_before_simulation_step",
                "_after_simulation_step",
            }
            & cls.__dict__.keys()
        )


def test_joint_interface_returns_native_outer_observation_after_extra_terminal_step(
    monkeypatch,
):
    import numpy as np
    from robomme_icl.envs import wrapper

    returned = {"image": "原版外层观测"}
    extra = {"image": "原版内部额外一步"}
    base = SimpleNamespace()
    native = SimpleNamespace(
        step=lambda action: (
            {"maniskill_obs": [returned]},
            0.0,
            True,
            False,
            {"task_goal": ["原版指令"]},
        )
    )
    fake = SimpleNamespace(
        action_dimension=8,
        native_wrapper=native,
        unwrapped=base,
        recorder=SimpleNamespace(frames=[{"observation": extra}]),
    )
    monkeypatch.setattr(wrapper, "normalized_observation", lambda raw, _: raw)
    monkeypatch.setattr(wrapper, "normalized_info", lambda info, _: {"success": True})
    observation, _, terminated, _, info = wrapper.ICLJointAngleEnv.step(
        fake, np.zeros(8)
    )
    assert observation is returned
    assert observation is not extra
    assert terminated
    assert info["task_goal"] == ["原版指令"]


@pytest.mark.parametrize("action", [[0.0] * 7, [float("nan")] * 8, [[0.0] * 8]])
def test_invalid_joint_action_is_rejected_before_native_step(action):
    from robomme_icl.envs.wrapper import ICLJointAngleEnv

    fake = SimpleNamespace(
        action_dimension=8,
        native_wrapper=SimpleNamespace(
            step=lambda _: pytest.fail("非法输入不能进入原版物理")
        ),
    )
    with pytest.raises(ValueError, match="8维有限数组"):
        ICLJointAngleEnv.step(fake, action)
