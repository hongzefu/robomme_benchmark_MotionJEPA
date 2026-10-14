"""回归测试：冻结 ENV 模块里的 SceneGenerationError 必须绑定到异常类本身。

背景：`robomme.robomme_env.utils` 没有 `__all__`，子模块 `utils/SceneGenerationError.py`
被导入后成为包属性；若先显式导入异常类、再写 `from .utils import *`，通配导入会把同名
绑定覆盖成子模块，`raise SceneGenerationError(...)` 变成 TypeError，`except` 也会报
「catching classes that do not inherit from BaseException」。正确顺序是先通配、后显式。
VideoPlaceButton 原本就是正确顺序，作为对照一并检查。
"""

import importlib

import pytest

from robomme.robomme_env.utils.SceneGenerationError import SceneGenerationError as 期望类

模块名列表 = ["SwingXtimes", "VideoRepick", "VideoPlaceOrder", "VideoPlaceButton"]


@pytest.mark.parametrize("name", 模块名列表)
def test_scene_error_binding(name):
    mod = importlib.import_module(f"robomme.robomme_env.{name}")
    绑定 = mod.SceneGenerationError
    # 必须是异常类，而不是被通配导入覆盖成的子模块
    assert isinstance(绑定, type) and issubclass(绑定, Exception), type(绑定)
    # 必须就是 utils.SceneGenerationError 子模块里定义的那个类
    assert 绑定 is 期望类
