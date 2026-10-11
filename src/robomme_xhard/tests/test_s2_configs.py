"""S2 五个派生子类（VideoUnmask、ButtonUnmask、VideoUnmaskSwap、ButtonUnmaskSwap、VideoRepick）的定向测试。

不标 gpu 的用例纯 CPU：只导入模块、读类属性、在假对象上调用调度 / 任务清单辅助函数，不 gym.make、不起仿真。
标 gpu 的用例需要 gym.make 与渲染栈，由主会话合并后在主检出跑。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
import torch

import robomme.robomme_env  # noqa: F401  先注册原任务
import robomme_xhard
from mani_skill.utils.registration import REGISTERED_ENVS
from robomme.robomme_env.ButtonUnmaskSwap import ButtonUnmaskSwap
from robomme.robomme_env.VideoRepick import VideoRepick
from robomme.robomme_env.VideoUnmaskSwap import VideoUnmaskSwap
from robomme.robomme_env.utils import task4recovery
from robomme_xhard.configs import SOURCE_DIFFICULTY, TIER_CONFIGS
from robomme_xhard.envs.button_unmask import ButtonUnmaskXHard
from robomme_xhard.envs.button_unmask_swap import (
    SIDE_BUTTON_NAME,
    AlternatingPressCounter,
    ButtonUnmaskSwapXHard,
    build_press_tasks,
    press_sides,
    swap_settle_step,
)
from robomme_xhard.envs.video_repick import VideoRepickXHard
from robomme_xhard.envs.video_unmask import VideoUnmaskXHard, append_extra_picks
from robomme_xhard.envs.video_unmask_swap import (
    VideoUnmaskSwapXHard,
    build_extended_swap_schedule,
    clear_extended_swap_pairs,
    cyclic_base_index,
    swap_windows,
)

S2_CLASSES = {
    "VideoUnmask": VideoUnmaskXHard,
    "ButtonUnmask": ButtonUnmaskXHard,
    "VideoUnmaskSwap": VideoUnmaskSwapXHard,
    "ButtonUnmaskSwap": ButtonUnmaskSwapXHard,
    "VideoRepick": VideoRepickXHard,
}
ALLOWED_PRESS_NAMES = {"press the first button", "press the second button"}


# ---------------------------------------------------------------- 注册与配置

@pytest.mark.parametrize("task", list(S2_CLASSES))
def test_registered_and_configs_merge(task):
    cls = S2_CLASSES[task]
    assert robomme_xhard.env_name(task) in REGISTERED_ENVS
    assert cls.robomme_base_id == task
    assert cls.source_difficulty == SOURCE_DIFFICULTY[task]
    parent = cls.__mro__[2]
    assert parent.__name__ == task
    for label, entry in TIER_CONFIGS[task].items():
        assert cls.configs[label] == {**parent.configs[cls.source_difficulty], **entry["config"]}
    # 父类三档原样保留
    for k in ("easy", "medium", "hard"):
        assert cls.configs[k] == parent.configs[k]


def test_unmask_knobs():
    for task in ("VideoUnmask", "ButtonUnmask"):
        cls = S2_CLASSES[task]
        assert set(TIER_CONFIGS[task]) == {"xhard14"}
        assert cls.configs["xhard14"]["pick"] == 3
        assert TIER_CONFIGS[task]["xhard14"]["knobs"] == {"pick_count": 3}


def test_swap_knobs_match_config():
    expect_bus = {"xhard12": (3, 4), "xhard14": (4, 6), "xhard16": (4, 8), "xhard18": (5, 10), "xhard20": (6, 12)}
    for label, (p, s) in expect_bus.items():
        knobs = TIER_CONFIGS["ButtonUnmaskSwap"][label]["knobs"]
        assert (knobs["press_count"], knobs["swap_count"]) == (p, s)
        cfg = ButtonUnmaskSwapXHard.configs[label]
        assert cfg["swap_min"] == cfg["swap_max"] == s
        assert cfg["pick_min"] == cfg["pick_max"] == 2
    expect_vus = {"xhard12": 4, "xhard14": 5, "xhard16": 7, "xhard18": 9, "xhard20": 11}
    for label, s in expect_vus.items():
        cfg = VideoUnmaskSwapXHard.configs[label]
        assert cfg["swap_min"] == cfg["swap_max"] == s == TIER_CONFIGS["VideoUnmaskSwap"][label]["knobs"]["swap_count"]
        assert cfg["pick_min"] == cfg["pick_max"] == 2
    expect_rep = {"xhard12": 5, "xhard14": 7, "xhard16": 10, "xhard18": 13, "xhard20": 15}
    for label, s in expect_rep.items():
        cfg = VideoRepickXHard.configs[label]
        assert cfg["swap_min"] == cfg["swap_max"] == s
        assert cfg["cube"] == 3  # medium 三方块
        assert TIER_CONFIGS["VideoRepick"][label]["knobs"] == {"swap_count": s, "repick_count": 2}


def test_randint_stream_unchanged_by_fixed_range():
    """父类 __init__ 里 swap / repeats 的 torch.randint 改成固定区间后，随机流后续抽样不变。"""
    for seed in (0, 7, 12900, 9500):
        g1, g2 = torch.Generator(), torch.Generator()
        g1.manual_seed(seed)
        g2.manual_seed(seed)
        torch.randint(1, 4, (1,), generator=g1)
        torch.randint(2, 4, (1,), generator=g1)
        torch.randint(1, 4, (1,), generator=g2)
        torch.randint(15, 16, (1,), generator=g2)
        assert torch.equal(torch.rand(4, generator=g1), torch.rand(4, generator=g2))


# ---------------------------------------------------------------- 交换调度

def _fake_swap_env(swap_times):
    return SimpleNamespace(
        swap_times=swap_times,
        swap_pair1_idx1="A", swap_pair2_idx1="B", swap_pair3_idx1="C",
        swap_pair1_idx2=None, swap_pair2_idx2=None, swap_pair3_idx2=None,
    )


@pytest.mark.parametrize("s", [4, 5, 7, 9, 11, 12, 13, 15])
def test_extended_schedule_shape_and_first_three(s):
    env = _fake_swap_env(s)
    sched = build_extended_swap_schedule(env, s, 64)
    assert len(sched) == s
    assert [(a, b) for _, _, a, b in sched] == swap_windows(s, 64)
    # 前三次与父类 3 次分支完全一致
    parent_env = _fake_swap_env(3)
    VideoUnmaskSwap._refresh_swap_schedule(parent_env)
    assert sched[:3] == parent_env.swap_schedule
    ButtonUnmaskSwap._refresh_swap_schedule(parent_env)
    assert sched[:3] == parent_env.swap_schedule
    # 第 4 次起 idx1 循环复用 A、B、C
    assert [x[0] for x in sched] == [["A", "B", "C"][cyclic_base_index(k) - 1] for k in range(1, s + 1)]
    # 首尾相接、末段结束于 64 + 50S
    for (_, _, _, e), (_, _, st, _) in zip(sched, sched[1:]):
        assert e == st
    assert sched[-1][3] == 64 + 50 * s


def test_repick_schedule_matches_parent_with_start_step():
    env = _fake_swap_env(7)
    sched = build_extended_swap_schedule(env, 7, 431)
    parent_env = _fake_swap_env(3)
    VideoRepick._refresh_swap_schedule(parent_env, 431)
    assert sched[:3] == parent_env.swap_schedule
    assert sched[-1][3] == 431 + 50 * 7


def test_schedule_reentry_keeps_resolved_idx2_and_reload_clears():
    env = _fake_swap_env(6)
    build_extended_swap_schedule(env, 6, 64)
    env.swap_pair5_idx2 = "X"  # step 在第 5 段起点求出 idx2
    env.swap_pair2_idx2 = "Y"
    sched = build_extended_swap_schedule(env, 6, 64)
    assert sched[4][1] == "X" and sched[1][1] == "Y"
    assert env.swap_pair4_idx1 == "A" and env.swap_pair6_idx1 == "C"
    clear_extended_swap_pairs(env)
    assert not hasattr(env, "swap_pair4_idx1") and not hasattr(env, "swap_pair5_idx2")
    assert env.swap_pair3_idx1 == "C"  # 父类 1..3 不动


def test_swaps_settle_before_first_pick():
    for label, entry in TIER_CONFIGS["ButtonUnmaskSwap"].items():
        s = entry["knobs"]["swap_count"]
        sched = build_extended_swap_schedule(_fake_swap_env(s), s, 64)
        assert swap_settle_step(sched) == 64 + 50 * s + 1
        assert swap_settle_step(sched) > sched[-1][3]


# ---------------------------------------------------------------- 按钮交替与命名（R27 方案甲）

def test_press_sides_right_first_alternating():
    assert press_sides(6) == ["right", "left", "right", "left", "right", "left"]
    assert press_sides(3) == ["right", "left", "right"]
    with pytest.raises(ValueError):
        press_sides(0)


def _fake_bus_env(press_count, swap_times):
    env = _fake_swap_env(swap_times)
    env.button_right, env.button_left = "BR", "BL"
    env.cap_links = {"button_right": "CAP_R", "button_left": "CAP_L"}
    env.xhard_knobs = {"press_count": press_count, "swap_count": swap_times}
    env.selected_bins = ["bin_a", "bin_b", "bin_c"]
    env.spawned_bins = ["bin_a", "bin_b", "bin_c", "bin_d"]
    env.color_names = ["red", "green", "blue"]
    env.pick_times = 2
    env.device = "cpu"
    env.table_scene = SimpleNamespace(initialize=lambda idx: None)
    env.agent = SimpleNamespace(reset=lambda q: None)
    env.swap_schedule = build_extended_swap_schedule(env, swap_times, 64)
    return env


@pytest.mark.parametrize("label", list(TIER_CONFIGS["ButtonUnmaskSwap"]))
def test_bus_task_list_names_and_order(label):
    knobs = TIER_CONFIGS["ButtonUnmaskSwap"][label]["knobs"]
    p, s = knobs["press_count"], knobs["swap_count"]
    env = _fake_bus_env(p, s)
    ButtonUnmaskSwapXHard._initialize_episode(env, torch.tensor([0]), {})
    names = [t["name"] for t in env.task_list]
    press = env.task_list[:p]
    # 按按钮步骤名字、segment、choice_label 只取自原任务两个名字，且右起交替
    assert {t["name"] for t in press} <= ALLOWED_PRESS_NAMES
    assert [t["name"] for t in press] == [SIDE_BUTTON_NAME[x] for x in press_sides(p)]
    assert all(t["choice_label"] == t["name"] for t in press)
    assert all(t["subgoal_segment"] == t["name"] + " at <>" for t in press)
    assert [t["segment"] for t in press] == ["CAP_R" if i % 2 == 0 else "CAP_L" for i in range(p)]
    assert [t["solve"].__defaults__[0] for t in press] == ["BR" if i % 2 == 0 else "BL" for i in range(p)]
    # 原两抓尾段
    assert names[p:] == [
        "pick up the container that hides the red cube",
        "put down the container",
        "pick up the container that hides the green cube",
    ]
    assert len(env.task_list) == p + 3
    # 只有 P 个按按钮项，其余名字不含 “press”
    assert sum("press" in n for n in names) == p
    # recovery 识别两抓（第一抓 solve 仍引用 solve_pickup_bin）
    assert env.recovery_pickup_indices == [p, p + 2]
    assert env.fail_grasp_task_index is None
    # 判据：第 i 项在计数推进到 i+1 时才完成
    c = env._xhard_press_counter
    assert c.count == 0 and c.sides == tuple(press_sides(p))
    for i, side in enumerate(press_sides(p)):
        assert not press[i]["func"]()
        c.update(side == "right", side == "left")
        assert press[i]["func"]()
        c.update(False, False)
    assert c.done


def test_bus_press_tasks_static_names_only():
    env = _fake_bus_env(6, 12)
    env._xhard_press_counter = AlternatingPressCounter(press_sides(6))
    tasks = build_press_tasks(env, 6)
    assert [t["name"] for t in tasks] == [
        "press the first button", "press the second button"] * 3


# ---------------------------------------------------------------- 边沿计数状态机

def test_counter_basic_alternation():
    c = AlternatingPressCounter(press_sides(4))
    seq = [(1, 0), (0, 0), (0, 1), (0, 0), (1, 0), (0, 0), (0, 1)]
    counts = [c.update(*x) for x in seq]
    assert counts == [1, 1, 2, 2, 3, 3, 4]
    assert c.done
    assert c.update(1, 0) == 4  # 完成后不再推进


def test_counter_hold_not_repeated_and_repress_same_side():
    c = AlternatingPressCounter(["right", "left", "right"])
    assert c.update(True, False) == 1
    for _ in range(20):  # 按住不放 / 多次 evaluate
        assert c.update(True, False) == 1
    assert c.update(False, False) == 1
    assert c.update(False, True) == 2
    assert c.update(False, True) == 2
    assert c.update(False, False) == 2
    assert c.update(True, False) == 3  # 第三次再按右


def test_counter_wrong_side_and_simultaneous():
    c = AlternatingPressCounter(["right", "left"])
    assert c.update(False, True) == 0  # 错侧
    assert c.update(False, False) == 0
    assert c.update(True, True) == 0  # 同时按
    assert c.update(True, False) == 0  # 右侧未经释放，不算新的上升沿
    assert c.update(False, False) == 0
    assert c.update(True, False) == 1
    assert c.update(False, False) == 1
    assert c.update(True, False) == 1  # 期望左却按右
    assert c.update(True, True) == 1  # 左上升时右仍按着：同时按，不推进
    assert c.update(False, False) == 1
    assert c.update(False, True) == 2


def test_counter_reset():
    c = AlternatingPressCounter(["right", "left"])
    c.update(True, False)
    c.update(False, True)
    assert c.count == 2
    c.reset()
    assert c.count == 0 and not c.done
    assert c.update(False, False) == 0
    assert c.update(True, False) == 1


# ---------------------------------------------------------------- Unmask 第三抓

def _fake_unmask_env(task):
    bins = [f"bin{i}" for i in range(5)]
    env = SimpleNamespace(
        spawned_bins=bins,
        color_names=["blue", "red", "green"],
        configs=S2_CLASSES[task].configs,
        difficulty="xhard14",
        xhard_knobs={"pick_count": 3},
    )
    for i, b in enumerate(bins):
        setattr(env, f"bin_{i}", b)
    # 父类两抓清单的名字骨架（VideoUnmask 前缀 static 演示；ButtonUnmask 前缀按按钮）
    prefix = [{"name": "static", "choice_label": "static", "demonstration": True, "solve": None}]
    if task == "ButtonUnmask":
        prefix = [{"name": "press the button", "choice_label": "press the button", "demonstration": False,
                   "solve": None}]
    env.task_list = prefix + [
        {"name": "pick up the container that hides the blue cube", "choice_label": "pick up the container",
         "demonstration": False, "solve": None},
        {"name": "put down the container", "choice_label": "put down the container",
         "demonstration": False, "solve": None},
        {"name": "pick up the container that hides the red cube", "choice_label": "pick up the container",
         "demonstration": False, "solve": None},
    ]
    return env


@pytest.mark.parametrize("task", ["VideoUnmask", "ButtonUnmask"])
def test_unmask_third_pick_appended(task):
    env = _fake_unmask_env(task)
    append_extra_picks(env)
    names = [t["name"] for t in env.task_list]
    assert names[-5:] == [
        "pick up the container that hides the blue cube",
        "put down the container",
        "pick up the container that hides the red cube",
        "put down the container",
        "pick up the container that hides the green cube",  # color_names[2]
    ]
    putdown, pick3 = env.task_list[-2], env.task_list[-1]
    assert putdown["func"].__defaults__ == ("bin1",)  # 放下第二抓的 bin_1
    assert pick3["func"].__defaults__ == ("bin2",)
    assert pick3["solve"].__defaults__ == ("bin2",)
    assert pick3["segment"] == "bin2"
    assert pick3["choice_label"] == "pick up the container"
    # 新增的第三抓被 recovery 识别（solve 引用 solve_pickup_bin）
    assert len(env.task_list) - 1 in env.recovery_pickup_indices
    assert task4recovery([pick3])[0] == [0]


def test_unmask_fails_loud_without_three_bins():
    env = _fake_unmask_env("VideoUnmask")
    env.spawned_bins = env.spawned_bins[:2]
    with pytest.raises(Exception, match="至少 3 个"):
        append_extra_picks(env)


def test_unmask_and_bus_reject_failure_recovery():
    for cls in (VideoUnmaskXHard, ButtonUnmaskXHard, ButtonUnmaskSwapXHard):
        with pytest.raises(ValueError, match="robomme_failure_recovery"):
            cls(difficulty="xhard14", robomme_failure_recovery=True)


# ---------------------------------------------------------------- VideoRepick 重抓固定为 2

def test_repick_num_repeats_intercepted():
    inst = VideoRepickXHard.__new__(VideoRepickXHard)
    inst.__dict__["xhard_knobs"] = {"swap_count": 5, "repick_count": 2}
    for raw in (1, 2, 3):
        inst.num_repeats = raw
        assert inst.num_repeats == 2
    bare = VideoRepickXHard.__new__(VideoRepickXHard)
    bare.num_repeats = 3  # 没有 knobs 时不改
    assert bare.num_repeats == 3


# ---------------------------------------------------------------- 需要仿真的用例（主会话合并后跑）

GPU_CASES = [
    ("VideoUnmask", "xhard14"),
    ("ButtonUnmask", "xhard14"),
    ("VideoUnmaskSwap", "xhard12"),
    ("VideoUnmaskSwap", "xhard20"),
    ("ButtonUnmaskSwap", "xhard12"),
    ("ButtonUnmaskSwap", "xhard20"),
    ("VideoRepick", "xhard12"),
    ("VideoRepick", "xhard20"),
]


@pytest.mark.gpu
@pytest.mark.parametrize("task,label", GPU_CASES)
def test_gym_make_reset_contract(task, label):
    import gymnasium as gym

    seed = 12900
    env = gym.make(robomme_xhard.env_name(task), obs_mode="rgb+depth+segmentation",
                   control_mode="pd_joint_pos", render_mode="rgb_array", reward_mode="dense",
                   seed=seed, difficulty=label)
    try:
        env.reset(seed=seed)
        u = env.unwrapped
        assert u.spec.id == task
        assert u.difficulty == label
        knobs = TIER_CONFIGS[task][label]["knobs"]
        assert u.xhard_knobs == knobs
        names = [t["name"] for t in u.task_list]
        if task in ("VideoUnmask", "ButtonUnmask"):
            assert len(u.color_names) >= 3
            picks = [n for n in names if n.startswith("pick up the container")]
            assert picks == [f"pick up the container that hides the {c} cube" for c in u.color_names[:3]]
        else:
            assert u.swap_times == knobs["swap_count"]
            assert len(u.swap_schedule) == knobs["swap_count"]
            for k in range(1, u.swap_times + 1):
                assert hasattr(u, f"swap_pair{k}_idx1")
        if task == "ButtonUnmaskSwap":
            p = knobs["press_count"]
            assert [n for n in names if "press" in n] == [SIDE_BUTTON_NAME[x] for x in press_sides(p)]
            assert u._xhard_press_counter.count == 0
            for _ in range(3):
                u.evaluate()
            assert u._xhard_press_counter.count == 0
        if task == "VideoRepick":
            assert u.num_repeats == 2
            assert u.configs[u.difficulty]["cube"] == 3
            assert sum(1 for t in u.task_list if t.get("specialflag") == "swap") == knobs["swap_count"]
            assert sum(1 for n in names if n.startswith("pick up the correct cube")) == 2
    finally:
        env.close()
