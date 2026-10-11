"""xhard 五级难度的唯一配置表（计划 1006-xhard12-env-plan.html 四.7 表与 10-11 裁决 R1–R28）。

本文件是全部派生档旋钮的唯一来源：
- ``DIFFICULTIES``：对外传入的五个 difficulty 字面值。
- ``SOURCE_DIFFICULTY``：每个任务的母配置来源（VideoRepick 为 medium，其余为 hard）。
- ``MOTHER_KNOBS``：1.0 倍固定母档的实际旋钮中位（选母 seed 时据此筛选）。
- ``TIER_CONFIGS[task][difficulty]``：52 个有效“任务 × 难度”配置；缺档的格子不出现，
  不复制相同配置凑档。

每个配置项两部分：
- ``config``：写进子类 ``configs[<xhard 值>]`` 的父类配置键覆盖（在母配置副本上覆盖）；
  没有 configs 字典或旋钮不在字典里的任务为空。
- ``knobs``：派生旋钮的语义取值，子类按它实现、语言目标按它读取；键名是公共契约。

knobs 键名约定：
- ``target_total``：BinFill 投入总块数 K。
- ``repeats``：PickXtimes / SwingXtimes 的次数 n。
- ``stop_k`` / ``move_interval``：StopCube 第几次经过时停、单程间隔。
- ``pick_count``：VideoUnmask / ButtonUnmask 抓容器个数 p。
- ``swap_count``：交换次数 S（VideoUnmaskSwap、ButtonUnmaskSwap、VideoRepick）。
- ``press_count``：ButtonUnmaskSwap 右起左右交替按按钮次数 P。
- ``pickup`` / ``spawn``：PickHighlight 高亮块数与生成块数。
- ``repick_count``：VideoRepick 重抓次数 R。
- ``extra_groups``：VideoPlaceButton 额外抓放组数 a（a=1 时前后各 50% 概率）。
- ``num_targets``：VideoPlaceOrder 不同目标数 N。
- ``length`` / ``grid``：PatternLock 节点数 L 与网格；RouteStick 用 ``length`` 表示边数 S。
"""

from __future__ import annotations

DIFFICULTIES: tuple[str, ...] = ("xhard12", "xhard14", "xhard16", "xhard18", "xhard20")

# 档名对应的目标倍数（只作报告，实测倍数另记，不据此判失败；R3、R24）
TARGET_RATIO: dict[str, float] = {
    "xhard12": 1.2,
    "xhard14": 1.4,
    "xhard16": 1.6,
    "xhard18": 1.8,
    "xhard20": 2.0,
}

# 官网四类顺序（AGENTS.md P6）
TASK_ORDER: tuple[str, ...] = (
    "BinFill",
    "PickXtimes",
    "SwingXtimes",
    "StopCube",
    "VideoUnmask",
    "ButtonUnmask",
    "VideoUnmaskSwap",
    "ButtonUnmaskSwap",
    "PickHighlight",
    "VideoRepick",
    "VideoPlaceButton",
    "VideoPlaceOrder",
    "MoveCube",
    "InsertPeg",
    "PatternLock",
    "RouteStick",
)

# 有派生档的 14 个任务（MoveCube、InsertPeg 只有母档对照）
XHARD_TASKS: tuple[str, ...] = tuple(t for t in TASK_ORDER if t not in ("MoveCube", "InsertPeg"))

SOURCE_DIFFICULTY: dict[str, str] = {t: "hard" for t in TASK_ORDER}
SOURCE_DIFFICULTY["VideoRepick"] = "medium"

# 1.0 倍固定母档（四.7 表“1.0倍固定母档”列；25 条母样本实际旋钮取中位，半整数四舍五入）
MOTHER_KNOBS: dict[str, dict] = {
    "BinFill": {"target_total": 4},
    "PickXtimes": {"repeats": 5},
    "SwingXtimes": {"repeats": 3},
    "StopCube": {"stop_k": 3, "move_interval": 80},
    "VideoUnmask": {"pick_count": 2},
    "ButtonUnmask": {"pick_count": 2},
    "VideoUnmaskSwap": {"swap_count": 2},
    "ButtonUnmaskSwap": {"press_count": 2, "swap_count": 3},
    "PickHighlight": {"pickup": 3, "spawn": 6},
    "VideoRepick": {"swap_count": 2, "repick_count": 2},
    "VideoPlaceButton": {"extra_groups": 0},
    "VideoPlaceOrder": {"num_targets": 3},
    "MoveCube": {},
    "InsertPeg": {},
    "PatternLock": {"length": 6, "grid": 5},
    "RouteStick": {"length": 5},
}


def _cfg(config: dict | None = None, **knobs) -> dict:
    return {"config": dict(config or {}), "knobs": dict(knobs)}


def _rep(n: int) -> dict:
    """PickXtimes / SwingXtimes：number_min = number_max = n。"""
    return _cfg({"number_min": n, "number_max": n}, repeats=n)


def _swap(s: int) -> dict:
    """VideoUnmaskSwap：swap_min = swap_max = S。"""
    return _cfg({"swap_min": s, "swap_max": s}, swap_count=s)


def _bus(p: int, s: int) -> dict:
    """ButtonUnmaskSwap：P 次交替按压 + S 次交换。"""
    return _cfg({"swap_min": s, "swap_max": s}, press_count=p, swap_count=s)


def _repick(s: int) -> dict:
    """VideoRepick（medium 三方块）：swap_min = swap_max = S，重抓 R=2。"""
    return _cfg({"swap_min": s, "swap_max": s}, swap_count=s, repick_count=2)


def _pattern(length: int) -> dict:
    return _cfg({"grid": 5, "length": [length, length]}, length=length, grid=5)


def _route(length: int) -> dict:
    return _cfg({"length": [length, length]}, length=length)


def _highlight(p: int) -> dict:
    return _cfg({"spawn": 6, "pickup": p}, pickup=p, spawn=6)


TIER_CONFIGS: dict[str, dict[str, dict]] = {
    "BinFill": {
        "xhard12": _cfg(target_total=5),
        "xhard14": _cfg(target_total=6),
        "xhard16": _cfg(target_total=7),
        "xhard18": _cfg(target_total=8),
        "xhard20": _cfg(target_total=9),  # R16 新增
    },
    "PickXtimes": {
        "xhard12": _rep(6),
        "xhard14": _rep(7),
        "xhard16": _rep(8),
        "xhard18": _rep(9),
        "xhard20": _rep(10),
    },
    "SwingXtimes": {
        "xhard12": _rep(4),
        "xhard14": _rep(5),
        "xhard16": _rep(7),
        "xhard18": _rep(8),
        "xhard20": _rep(9),
    },
    "StopCube": {
        # xhard12 留空
        "xhard14": _cfg(stop_k=4, move_interval=80),
        "xhard16": _cfg(stop_k=5, move_interval=80),
        "xhard18": _cfg(stop_k=7, move_interval=60),  # R16 新增，唯一不用间隔 80 的档
        "xhard20": _cfg(stop_k=6, move_interval=80),
    },
    "VideoUnmask": {
        "xhard14": _cfg({"pick": 3}, pick_count=3),
    },
    "ButtonUnmask": {
        "xhard14": _cfg({"pick": 3}, pick_count=3),
    },
    "VideoUnmaskSwap": {
        "xhard12": _swap(4),
        "xhard14": _swap(5),
        "xhard16": _swap(7),
        "xhard18": _swap(9),
        "xhard20": _swap(11),
    },
    "ButtonUnmaskSwap": {
        "xhard12": _bus(3, 4),
        "xhard14": _bus(4, 6),
        "xhard16": _bus(4, 8),
        "xhard18": _bus(5, 10),
        "xhard20": _bus(6, 12),
    },
    "PickHighlight": {
        # xhard14、xhard20 留空；R19 小规模实测后按实测倍数重新归档（先交用户确认）
        "xhard12": _highlight(4),
        "xhard16": _highlight(5),
        "xhard18": _highlight(6),
    },
    "VideoRepick": {
        "xhard12": _repick(5),
        "xhard14": _repick(7),
        "xhard16": _repick(10),
        "xhard18": _repick(13),
        "xhard20": _repick(15),
    },
    "VideoPlaceButton": {
        "xhard12": _cfg(extra_groups=1),  # 前、后各 50% 概率，同 seed 可复现
        "xhard14": _cfg(extra_groups=2),  # 前后各 1 组
    },
    "VideoPlaceOrder": {
        "xhard12": _cfg(num_targets=4),  # R3：实测约 1.132 倍仍叫 xhard12
    },
    "PatternLock": {
        "xhard12": _pattern(7),
        "xhard14": _pattern(8),
        "xhard16": _pattern(9),  # R24：实测短于 xhard14，不改旋钮
        "xhard18": _pattern(10),
        "xhard20": _pattern(11),
    },
    "RouteStick": {
        "xhard12": _route(6),
        "xhard14": _route(7),
        "xhard16": _route(8),
        "xhard18": _route(9),
        "xhard20": _route(10),
    },
}


def is_xhard(difficulty: str | None) -> bool:
    return isinstance(difficulty, str) and difficulty.strip().lower() in DIFFICULTIES


def tier(task: str, difficulty: str) -> dict:
    """取一个有效配置；缺档或未知值响亮失败，不回退、不复制邻档。"""
    label = difficulty.strip().lower()
    if label not in DIFFICULTIES:
        raise ValueError(f"未知 xhard difficulty {difficulty!r}，可选 {DIFFICULTIES}")
    try:
        return TIER_CONFIGS[task][label]
    except KeyError:
        raise KeyError(f"{task} 没有 {label} 档（缺档，不复制配置凑档）") from None


def valid_pairs() -> list[tuple[str, str]]:
    """按官网任务顺序、再按难度顺序列出全部有效 (task, difficulty)。"""
    return [(t, d) for t in TASK_ORDER for d in DIFFICULTIES if d in TIER_CONFIGS.get(t, {})]


def env_name(task: str) -> str:
    """派生子类在注册表里的名字；spec.id 由 XHardMixin 改回原任务名。"""
    return f"{task}XHard"
