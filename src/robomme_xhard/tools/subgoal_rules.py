"""混合档的冻结应查集合与边界计数规则；未填规则必须失败。

VideoPlaceButton::_load_scene 的 hard 配置关闭 additional_place，固定演示段
依次抓取至 target_0、target_1、桌面，共三次；执行段再抓一次。因此全序列
计数的基线为四，演示段基线为三。子类只插入 extra_groups 个演示抓放组。
"""

# 集合检查数量项，不涵盖 move_interval 等时间间隔或场景的全部属性。
# 项名使用旋钮名；固定动作另具名，不能用产物报告的旋钮替代配置期望。
EXPECTED_CHECKS = {
    "BinFill": frozenset({"target_total"}),
    "PickXtimes": frozenset({"repeats"}),
    "SwingXtimes": frozenset({"repeats"}),
    "StopCube": frozenset({"stop_k"}),
    "VideoUnmask": frozenset({"pick_count"}),
    "ButtonUnmask": frozenset({"pick_count"}),
    "VideoUnmaskSwap": frozenset({"container_pickups", "swap_count"}),
    "ButtonUnmaskSwap": frozenset({"press_count", "container_pickups", "swap_count"}),
    "PickHighlight": frozenset({"pickup", "spawn"}),
    "VideoRepick": frozenset({"repick_count", "swap_count"}),
    "VideoPlaceButton": frozenset({"extra_groups"}),
    "VideoPlaceOrder": frozenset({"num_targets"}),
    "PatternLock": frozenset({"length", "grid"}),
    "RouteStick": frozenset({"length"}),
}

SUBGOAL_RULES = {task: [] for task in EXPECTED_CHECKS}
SUBGOAL_RULES.update({
    "VideoUnmaskSwap": [
        {"name": "container_pickups", "pattern": r"^pick up the container", "expect": "const:2"},
        {"name": "swap_count", "pattern": None, "expect": "swap_runtime"},
    ],
    "ButtonUnmaskSwap": [
        {"name": "press_count", "pattern": r"^press the (first|second) button$", "expect": "knob:press_count"},
        {"name": "container_pickups", "pattern": r"^pick up the container", "expect": "const:2"},
        {"name": "swap_count", "pattern": None, "expect": "swap_runtime"},
    ],
    "VideoRepick": [
        {"name": "repick_count", "pattern": r"^pick up the correct cube for the .* time$", "expect": "knob:repick_count"},
        {"name": "swap_count", "pattern": None, "expect": "swap_runtime"},
    ],
    "VideoPlaceButton": [
        {"name": "extra_groups", "pattern": r"^pick up the cube$", "expect": "knob_plus:extra_groups:4"},
    ],
})

# 仅允许后续 W5 写入用户批准的具名豁免；当前没有获批豁免。
EXEMPT = {task: {} for task in EXPECTED_CHECKS}
