"""V4 xhard 档的共用常量与采样工具（NEWTASK_RELEASE_V4_PLAN 2.0①）。

只在 xhard 分支被读；原三档从不 import 本模块里的东西参与取值，所以不影响 V0/V1。

* ``DISTRACTOR_COLORS``：「其他颜色」干扰物的全局色池（B2：黄／青／品红，六个环境共用，A5 固定 3 个）。
* ``corner_push``：边角偏置映射。把 ``[0,1]`` 上的均匀抽样值按 ``corner_bias`` 推向两端，
  ``corner_bias=0`` 时**原样返回同一个对象**（调用方据此保证与现有均匀采样逐字等价）。
"""

from __future__ import annotations

# 顺序固定：黄、青、品红。名字用于任务文本与规格记录，rgba 与 B2 决策逐字一致。
DISTRACTOR_COLORS = (
    {"name": "yellow", "rgba": (1, 1, 0, 1)},
    {"name": "cyan", "rgba": (0, 1, 1, 1)},
    {"name": "magenta", "rgba": (1, 0, 1, 1)},
)

# corner_bias=1 时的幂指数 1/(1+CORNER_GAIN)；4 ⇒ 指数 0.2，t=0.5 被推到约 0.87。
CORNER_GAIN = 4.0


def corner_push(u, corner_bias):
    """把单个 ``u ∈ [0,1]`` 按边角偏置推向 0 或 1 端。

    映射：``t = 2u-1``，``t' = sign(t)·|t|^p``，``p = 1/(1+CORNER_GAIN·b)``，返回 ``(t'+1)/2``。
    单调、保端点、关于 0.5 对称；两个坐标各自独立推移 ⇒ 联合分布偏向四角。
    ``b`` 必须在 ``[0,1]``；``b == 0`` 时不做任何浮点运算、直接返回 ``u``。
    """
    b = float(corner_bias)
    if b == 0.0:
        return u
    if not 0.0 <= b <= 1.0:
        raise ValueError(f"corner_bias 必须在 [0,1]，收到 {corner_bias}")
    t = 2.0 * float(u) - 1.0
    p = 1.0 / (1.0 + CORNER_GAIN * b)
    mag = abs(t) ** p
    return (1.0 + (mag if t >= 0 else -mag)) / 2.0
