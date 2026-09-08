"""核对新旧源码与注册隔离；只导入类，不构建仿真环境。"""

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


def test_all_legacy_imports_are_confined_to_bridge():
    violations = []
    for path in sorted(SOURCE.rglob("*.py")):
        relative = path.relative_to(SOURCE)
        if relative.parts[0] == "legacy_bridge":
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            modules = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and not node.level:
                modules = [node.module or ""]
            elif isinstance(node, ast.Call) and node.args:
                target = node.func
                dynamic = ((isinstance(target, ast.Name) and target.id in {"__import__", "import_module"})
                           or (isinstance(target, ast.Attribute) and target.attr == "import_module"))
                if dynamic and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                    modules = [node.args[0].value]
            violations.extend(f"{relative}:{node.lineno}: {module}" for module in modules if _is_legacy(module))
    assert not violations, "原版导入越过 legacy_bridge：\n"+"\n".join(violations)


@pytest.fixture(scope="module")
def registered_classes():
    # 显式先导入旧包，随后注册新版；只访问注册表，不调用 gym.make。
    importlib.import_module("robomme.robomme_env")
    from mani_skill.utils.registration import REGISTERED_ENVS

    before = {name: record.cls for name, record in REGISTERED_ENVS.items()
              if record.cls.__module__.startswith("robomme.robomme_env.")}
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


def test_four_new_ids_use_new_base_without_old_task_mro(registered_classes):
    before, first, _ = registered_classes
    from mani_skill.envs.sapien_env import BaseEnv
    from robomme_icl.envs.base import ICLBaseEnv

    assert ICLBaseEnv.__bases__ == (BaseEnv,)
    for task in TASKS:
        cls = first[f"RoboMME-ICL/{task}-v0"]
        assert cls.__module__.startswith("robomme_icl.envs.")
        assert cls.__bases__ == (ICLBaseEnv,)
        assert cls.TASK_KIND == task
        assert not set(cls.__mro__).intersection(before.values())


def test_phase_transition_cannot_clear_a_latched_failure(registered_classes):
    from robomme_icl.envs.base import ICLBaseEnv
    from robomme_icl.errors import TaskExecutionError

    for contacts, task_result in (([{"bodies": ["cube", "robot"]}], {}), ([], {"fail": True})):
        fake = SimpleNamespace(_forbidden_contacts=contacts, _task_result=task_result)
        with pytest.raises(TaskExecutionError, match="禁止切换"):
            ICLBaseEnv.set_phase(fake, "evaluation")


def test_late_contact_masks_cached_success(registered_classes):
    import torch
    from robomme_icl.envs.base import ICLBaseEnv

    fake = SimpleNamespace(_native_ready=True, _phase="evaluation", elapsed_steps=torch.tensor([3]),
                           _evaluated_at=("evaluation", 3), _task_result={"success": True, "fail": False},
                           _forbidden_contacts=[{"bodies": ["cube", "robot"]}])
    result = ICLBaseEnv.evaluate(fake)
    assert bool(result["fail"].item())
    assert not bool(result["success"].item())


def test_unknown_robot_contacts_are_not_silently_allowed(registered_classes):
    from robomme_icl.envs.base import ICLBaseEnv

    fake = SimpleNamespace(actor_definitions={"cube": {"kind": "cube"}}, task_kind="VideoRepick",
                           definition={"task_parameters": {"target_ids": ["cube"]}},
                           _allowed_robot_pairs={frozenset(("panda_link1", "panda_link2"))})
    assert not ICLBaseEnv._allowed_contact(fake, "panda_link5", "table-workspace")
    assert not ICLBaseEnv._allowed_contact(fake, "panda_link1", "panda_link7")
    assert not ICLBaseEnv._allowed_contact(fake, "unknown_foreign_body", "cube")
    assert ICLBaseEnv._allowed_contact(fake, "panda_link0", "table-workspace")
    assert ICLBaseEnv._allowed_contact(fake, "panda_link1", "panda_link2")


@pytest.mark.parametrize("iteration_order", [
    ("container_z", "container_a", "parked_cube"),
    ("parked_cube", "container_a", "container_z"),
])
def test_animation_finishes_in_fixed_id_order_at_frozen_endpoints(registered_classes, iteration_order, monkeypatch):
    from robomme_icl.envs.base import ICLBaseEnv

    class IterationControlledSet(set):
        """模拟跨进程哈希顺序，避免测试恰巧得到字典序而漏掉回归。"""

        def __init__(self, values):
            self.order = tuple(values)
            super().__init__(self.order)

        def __iter__(self):
            return iter(name for name in self.order if name in self)

        def __sub__(self, other):
            return type(self)(name for name in self.order if name in self and name not in other)

    spec = {
        "actors": [
            {"id": "container_a", "position": [0., 0., .036], "quaternion": [1., 0., 0., 0.]},
            {"id": "container_z", "position": [.2, 0., .036], "quaternion": [1., 0., 0., 0.]},
            {"id": "parked_cube", "position": [10., 10., 10.], "quaternion": [1., 0., 0., 0.]},
        ],
        "swaps": [{"a": "container_a", "b": "container_z", "start_step": 5, "end_step": 55, "lane_offset": .07}],
    }
    fake = SimpleNamespace(_animation_enabled=True, definition=spec, episode_spec=spec,
                           _kinematic=IterationControlledSet(iteration_order), _parked={"parked_cube"})
    restored = []
    pose_queries = []
    endpoints = {
        "container_a": {"position": [.2, 0., .036], "quaternion": [1., 0., 0., 0.]},
        "container_z": {"position": [0., 0., .036], "quaternion": [1., 0., 0., 0.]},
        "parked_cube": {"position": [10., 10., 10.], "quaternion": [1., 0., 0., 0.]},
    }

    def frozen_pose_at_step(record, step):
        assert record is spec
        pose_queries.append(step)
        return copy.deepcopy(endpoints)

    monkeypatch.setattr("robomme_icl.envs.base.pose_at_step", frozen_pose_at_step)

    def restore(name, pose):
        restored.append((name, copy.deepcopy(pose)))
        # 真实 restore 会同时移出集合，外层必须先固定遍历顺序。
        fake._kinematic.discard(name)

    def drifting_snapshot():
        raise AssertionError("动画结束不得读取可能已有物理漂移的末帧 snapshot")

    fake.restore = restore
    fake.snapshot = drifting_snapshot
    ICLBaseEnv.finish_animation(fake)
    assert pose_queries == [55]
    assert not fake._animation_enabled
    assert [name for name, _ in restored] == ["container_a", "container_z"]
    assert restored[0][1]["position"] == [.2, 0., .036]
    assert restored[1][1]["position"] == [0., 0., .036]
    assert all(pose["quaternion"] == [1., 0., 0., 0.] for _, pose in restored)
    assert fake._kinematic == {"parked_cube"}
