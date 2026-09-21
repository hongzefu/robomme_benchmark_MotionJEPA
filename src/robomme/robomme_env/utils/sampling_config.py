"""``sampling_config`` 的统一形态与校验（newtaskRelease-v3 步 3）。

方案第三节规定配置快照按两块组织：

``decision``
    以后允许改的参数（第二节字段表里标「是，拟修改」的那些）。**原值对拍阶段
    它也必须等于原值**（红线 R7），所以本模块在原值模式下逐键比对并拒绝任何偏差。

``native``
    维持原状的随机规则与常量，沿用各环境已有的 ``{"parameters": ..., "positions": ...}``
    结构，键名、取值域、单位、dtype 与拒绝条件一律不动。

为兼容四个早于本方案就接了 ``sampling_config`` 的环境（BinFill／RouteStick／VideoRepick／
VideoUnmaskSwap）及其既有产物与工具（``scripts/injection/``、``--extract-config`` 等），
旧格式 ``{"parameters": ..., "positions": ...}`` 继续被接受，等价于只给了 ``native``。

本模块**不抽任何随机数**，也不得在解析过程中触发随机数：调用点必须落在
``torch.Generator()`` 创建之前，在这里多抽或少抽一次会平移其后全部取值。
"""

from __future__ import annotations

import copy
import json

NATIVE_KEYS = ("parameters", "positions")


class SamplingConfigError(ValueError):
    """传入的 sampling_config 不满足固定形态或在原值模式下偏离了原值。"""


def split_sampling_config(override, native_default, decision_default):
    """把外部传入的配置拆成 ``(decision, native)`` 两块副本。

    参数
    ----
    override
        ``None`` 表示不传，直接用两个默认块；
        新格式为 ``{"decision": ..., "native": ...}``（``decision`` 可省略）；
        旧格式为 ``{"parameters": ..., "positions": ...}``，等价于只给 ``native``。
    native_default / decision_default
        本环境的原值快照，用于缺省填充与原值模式校验。

    返回的两块都是 deepcopy：gymnasium 会把 kwargs 字典的引用存进
    ``env.unwrapped.spec.kwargs``，不复制就会被跨局改写。
    """
    if override is None:
        return copy.deepcopy(decision_default), copy.deepcopy(native_default)
    if not isinstance(override, dict):
        raise SamplingConfigError("sampling_config 必须是字典")

    keys = set(override)
    if keys == set(NATIVE_KEYS):
        # 旧格式：只给了 native 块
        decision, native = copy.deepcopy(decision_default), copy.deepcopy(override)
    elif keys <= {"decision", "native"} and "native" in keys:
        native = copy.deepcopy(override["native"])
        decision = copy.deepcopy(override.get("decision", decision_default))
    else:
        raise SamplingConfigError(
            "sampling_config 必须是 {decision, native} 或旧格式 {parameters, positions}，"
            f"当前键为 {sorted(keys)}"
        )
    if not isinstance(native, dict) or set(native) != set(NATIVE_KEYS):
        raise SamplingConfigError("sampling_config.native 必须只含 parameters 与 positions")
    if not isinstance(decision, dict):
        raise SamplingConfigError("sampling_config.decision 必须是字典")
    return decision, native


def assert_native_decision(decision, decision_default, task):
    """原值模式的守卫：``decision`` 必须与原值逐键相同（红线 R7）。

    第一轮只做原值导出／消费，第二节「拟修改」列的值全部不启用；任何偏差都必须是
    显式的新用户决策，不能混在「仅随机外移」里悄悄生效。
    """
    left = json.dumps(decision, sort_keys=True, ensure_ascii=False)
    right = json.dumps(decision_default, sort_keys=True, ensure_ascii=False)
    if left != right:
        raise SamplingConfigError(
            f"{task}: 原值对拍模式下 decision 必须等于原值快照；收到的与原值不同"
        )
