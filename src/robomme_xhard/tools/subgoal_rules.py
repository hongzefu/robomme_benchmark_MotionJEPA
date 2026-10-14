"""混合档的冻结应查集合与边界计数规则；未填规则必须失败。

VideoPlaceButton::_load_scene 的 hard 配置关闭 additional_place，固定演示段
依次抓取至 target_0、target_1、桌面，共三次；执行段再抓一次。因此全序列
计数的基线为四，演示段基线为三。子类只插入 extra_groups 个演示抓放组。

PatternLock 的 L 个节点在演示、执行各形成 L−1 个移动边界；RouteStick 的
length 表示 S 条边，两阶段各形成 S 个移动边界，均只数具名动作，不数完成标记。
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
    "BinFill": [
        {"name": "target_total", "pattern": r"^put it into the bin$", "expect": "knob:target_total"},
    ],
    "PickXtimes": [
        {"name": "repeats", "pattern": r"^pick up the (red|green|blue) cube for the .* time$", "expect": "knob:repeats"},
    ],
    "SwingXtimes": [
        {"name": "repeats", "pattern": r"^move to the top of the right-side target for the .* time$", "expect": "knob:repeats"},
    ],
    "VideoUnmask": [
        {"name": "pick_count", "pattern": r"^pick up the container that hides the (red|green|blue) cube$", "expect": "knob:pick_count"},
    ],
    "ButtonUnmask": [
        {"name": "pick_count", "pattern": r"^pick up the container that hides the (red|green|blue) cube$", "expect": "knob:pick_count"},
    ],
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
    "PickHighlight": [
        {"name": "pickup", "pattern": r"^pick up the .* highlighted cube, which is (red|green|blue)$", "expect": "knob:pickup"},
    ],
    "VideoPlaceButton": [
        {"name": "extra_groups", "pattern": r"^pick up the cube$", "expect": "knob_plus:extra_groups:4"},
    ],
    "VideoPlaceOrder": [
        {"name": "num_targets", "pattern": r"^drop the cube onto target$", "expect": "knob:num_targets"},
    ],
    "PatternLock": [
        {"name": "length", "pattern": r"^move (forward|backward|left|right|forward-left|forward-right|backward-left|backward-right)$", "expect": "knob_affine:length:2:-2"},
    ],
    "RouteStick": [
        {"name": "length", "pattern": r"^move to the nearest (left|right) target by circling around the stick (clockwise|counterclockwise)$", "expect": "knob_affine:length:2:0"},
    ],
})

# 以下三项具名豁免用户已批准，可合入主分支并用于正式校验。
# 应查集合保持原样；处理豁免仍计入 rules_run，并由 exempt 单列。
EXEMPT = {task: {} for task in EXPECTED_CHECKS}
EXEMPT["StopCube"]["stop_k"] = (
    "用户已批准：stop_k 是方块经过目标的序号，remain static 是按时间生成的检查点，"
    "不能等同经过次数；真实 xhard18 的 stop_k=7 却只有 4 个 remain static 边界。"
)
EXEMPT["PickHighlight"]["spawn"] = (
    "用户已批准：H5 边界只记录被高亮并抓取的 4、5、6 块，不记录未选方块；"
    "无法由这些边界独立数出场景生成总数 6，xhard_knobs 只是配置报告。"
)
EXEMPT["PatternLock"]["grid"] = (
    "用户已批准：H5 边界只记录路径移动方向，没有全部网格节点的身份或数量；"
    "可真数 length 对应移动次数，但无法由方向序列独立证明网格边长 5。"
)
