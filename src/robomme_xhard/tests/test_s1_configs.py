"""S1：九个 xhard 派生子类的纯 CPU 检查（不 gym.make、不起仿真）。

覆盖：注册与 MRO、每档 configs 与父类 hard 的差异、knobs 键名契约、各子类覆写方法的纯函数与
用替身实例驱动的单元测试。需要仿真的用例标 ``gpu``，由主会话合并后在主检出跑。

运行：``python -m pytest src/robomme_xhard/tests/test_s1_configs.py -q -m 'not gpu'``
"""

from __future__ import annotations

import inspect
import textwrap
import types

import pytest
import torch

import robomme.robomme_env  # noqa: F401  先注册原 16 任务
import robomme_xhard  # noqa: F401  再注册派生子类
from mani_skill.utils.registration import REGISTERED_ENVS
from robomme.robomme_env.BinFill import BinFill
from robomme.robomme_env.PatternLock import PatternLock
from robomme.robomme_env.PickHighlight import PickHighlight
from robomme.robomme_env.PickXtimes import PickXtimes
from robomme.robomme_env.RouteStick import RouteStick
from robomme.robomme_env.StopCube import StopCube
from robomme.robomme_env.SwingXtimes import SwingXtimes
from robomme.robomme_env.VideoPlaceButton import VideoPlaceButton
from robomme.robomme_env.VideoPlaceOrder import VideoPlaceOrder
from robomme.robomme_env.utils import subgoal_language
from robomme.robomme_env.utils.SceneGenerationError import SceneGenerationError
from robomme.robomme_env.utils.task_goal import num2words, num2words_2
from robomme_xhard.base import XHardMixin
from robomme_xhard.configs import TIER_CONFIGS, env_name
from robomme_xhard.envs import (
    BinFillXHard,
    PatternLockXHard,
    PickHighlightXHard,
    PickXtimesXHard,
    RouteStickXHard,
    StopCubeXHard,
    SwingXtimesXHard,
    VideoPlaceButtonXHard,
    VideoPlaceOrderXHard,
)
from robomme_xhard.envs import bin_fill, pattern_lock, pick_highlight, route_stick, stop_cube
from robomme_xhard.envs import video_place_button as vpb
from robomme_xhard.envs import video_place_order as vpo

S1 = {
    "BinFill": (BinFillXHard, BinFill),
    "PickXtimes": (PickXtimesXHard, PickXtimes),
    "SwingXtimes": (SwingXtimesXHard, SwingXtimes),
    "StopCube": (StopCubeXHard, StopCube),
    "PickHighlight": (PickHighlightXHard, PickHighlight),
    "VideoPlaceButton": (VideoPlaceButtonXHard, VideoPlaceButton),
    "VideoPlaceOrder": (VideoPlaceOrderXHard, VideoPlaceOrder),
    "PatternLock": (PatternLockXHard, PatternLock),
    "RouteStick": (RouteStickXHard, RouteStick),
}

# 每个任务子类实现读取的 knobs 键（公共契约）
KNOB_KEYS = {
    "BinFill": {"target_total"},
    "PickXtimes": {"repeats"},
    "SwingXtimes": {"repeats"},
    "StopCube": {"stop_k", "move_interval"},
    "PickHighlight": {"pickup", "spawn"},
    "VideoPlaceButton": {"extra_groups"},
    "VideoPlaceOrder": {"num_targets"},
    "PatternLock": {"length", "grid"},
    "RouteStick": {"length"},
}


# ---------------------------------------------------------------- 注册、MRO、configs、knobs


@pytest.mark.parametrize("task", list(S1))
def test_registered_and_mro(task):
    sub, parent = S1[task]
    spec = REGISTERED_ENVS[env_name(task)]
    assert spec.cls is sub
    assert sub.__mro__[1] is XHardMixin and sub.__mro__[2] is parent
    assert sub.robomme_base_id == task
    assert sub.source_difficulty == "hard"
    # 原任务注册不受影响
    assert REGISTERED_ENVS[task].cls is parent


@pytest.mark.parametrize("task", list(S1))
def test_configs_only_override_target_keys(task):
    sub, parent = S1[task]
    parent_configs = getattr(parent, "configs", None)
    if parent_configs is None:
        # StopCube 没有 configs 字典，旋钮全在 knobs
        assert task == "StopCube"
        assert getattr(sub, "configs", None) is None
        assert all(not e["config"] for e in TIER_CONFIGS[task].values())
        return
    # 父类三档原样保留、父类字典本身未被改动
    for d in ("easy", "medium", "hard"):
        assert sub.configs[d] == parent_configs[d]
    assert set(parent_configs) == {"easy", "medium", "hard"}
    assert set(sub.configs) == {"easy", "medium", "hard", *TIER_CONFIGS[task]}
    hard = parent_configs["hard"]
    for label, entry in TIER_CONFIGS[task].items():
        cfg = sub.configs[label]
        assert set(cfg) == set(hard), (task, label)
        for key in hard:
            if key in entry["config"]:
                assert cfg[key] == entry["config"][key]
            else:
                assert cfg[key] == hard[key], (task, label, key)


@pytest.mark.parametrize("task", list(S1))
def test_knob_keys_contract(task):
    for label, entry in TIER_CONFIGS[task].items():
        assert set(entry["knobs"]) == KNOB_KEYS[task], (task, label)


# ---------------------------------------------------------------- PickXtimes / SwingXtimes


@pytest.mark.parametrize("task", ["PickXtimes", "SwingXtimes"])
def test_xtimes_subclass_is_empty_and_draw_is_fixed(task):
    sub, _ = S1[task]
    own = {k for k in vars(sub) if not k.startswith("__")}
    assert own <= {"robomme_base_id", "configs", "source_difficulty"}, own
    for label, entry in TIER_CONFIGS[task].items():
        n = entry["knobs"]["repeats"]
        cfg = sub.configs[label]
        for seed in (0, 7101, 10700):
            g = torch.Generator()
            g.manual_seed(seed)
            # 与父类 __init__ 同一抽法
            assert torch.randint(cfg["number_min"], cfg["number_max"] + 1, (1,), generator=g).item() == n
        assert n in num2words
        if task == "PickXtimes":
            # 序数上限：get_subgoal_with_index 只到第 10 次
            subgoal_language.get_subgoal_with_index(n - 1, "pick up the {color} cube for the {idx} time", color="red")
        else:
            # SwingXtimes 的 max_swings 由 2n 自动派生，父类内置序数列表到 tenth
            assert n <= 10


def test_pickxtimes_ordinal_upper_bound_is_ten():
    with pytest.raises(ValueError):
        subgoal_language.get_subgoal_with_index(10, "{idx}")
    assert max(e["knobs"]["repeats"] for e in TIER_CONFIGS["PickXtimes"].values()) == 10


# ---------------------------------------------------------------- BinFill


def test_binfill_allocate_round_robin_in_active_colors():
    # 母档红 2 蓝 2，库存充足：先在活跃色 red→blue 轮流
    assert bin_fill.allocate_targets([2, 2, 0], [5, 5, 3], 5) == [3, 2, 0]
    assert bin_fill.allocate_targets([2, 2, 0], [5, 5, 3], 6) == [3, 3, 0]
    assert bin_fill.allocate_targets([2, 2, 0], [5, 5, 3], 7) == [4, 3, 0]


def test_binfill_allocate_skips_exhausted_color():
    # 红库存只有 2：红满后只给蓝
    assert bin_fill.allocate_targets([2, 1, 0], [2, 6, 3], 6) == [2, 4, 0]


def test_binfill_allocate_extends_to_other_colors_after_active_full():
    # 母档只有蓝 4，蓝库存 5：蓝满后再按 red→green 扩到其它有库存的颜色（R7）
    assert bin_fill.allocate_targets([0, 4, 0], [3, 5, 4], 7) == [1, 5, 1]
    assert bin_fill.allocate_targets([0, 4, 0], [3, 5, 4], 9) == [2, 5, 2]
    # 没有库存的颜色不选
    assert bin_fill.allocate_targets([0, 4, 0], [0, 5, 4], 8) == [0, 5, 3]


def test_binfill_allocate_identity_and_failures():
    assert bin_fill.allocate_targets([1, 2, 1], [3, 3, 3], 4) == [1, 2, 1]
    with pytest.raises(SceneGenerationError):
        bin_fill.allocate_targets([2, 2, 0], [2, 3, 0], 6)  # 总库存 5 < 6
    with pytest.raises(SceneGenerationError):
        bin_fill.allocate_targets([3, 2, 0], [5, 5, 0], 4)  # K 小于母目标
    with pytest.raises(SceneGenerationError):
        bin_fill.allocate_targets([3, 0, 0], [2, 5, 0], 5)  # 母目标已超库存


def test_binfill_allocate_never_exceeds_inventory_or_ordinal():
    g = torch.Generator()
    g.manual_seed(0)
    for _ in range(300):
        inv = torch.randint(0, 7, (3,), generator=g).tolist()
        mother = [torch.randint(0, i + 1, (1,), generator=g).item() for i in inv]
        if sum(mother) == 0:
            continue
        for k in range(sum(mother), 10):
            try:
                new = bin_fill.allocate_targets(mother, inv, k)
            except SceneGenerationError:
                assert sum(inv) < k
                continue
            assert sum(new) == k
            assert all(m <= n <= i for m, n, i in zip(mother, new, inv))
            assert max(new) <= 10  # BinFill 子目标序数上限


def test_binfill_load_scene_rewrites_targets(monkeypatch):
    def fake_parent(self, options):
        self.red_cubes_target_number, self.blue_cubes_target_number, self.green_cubes_target_number = 0, 4, 0
        self.red_cubes, self.blue_cubes, self.green_cubes = [object()] * 3, [object()] * 5, [object()] * 4

    monkeypatch.setattr(BinFill, "_load_scene", fake_parent)
    env = object.__new__(BinFillXHard)
    env.xhard_knobs = dict(TIER_CONFIGS["BinFill"]["xhard20"]["knobs"])
    BinFillXHard._load_scene(env, None)
    assert [env.red_cubes_target_number, env.blue_cubes_target_number, env.green_cubes_target_number] == [2, 5, 2]
    assert env.xhard_mother_targets_rgb == [0, 4, 0]


# ---------------------------------------------------------------- StopCube


def test_stopcube_schedule_matches_parent_formula_on_mother():
    # 母档 k=3、间隔 80：steps_press=200，窗口 (160, 240)，检查点 [100, 170]
    s = stop_cube.stopcube_schedule(3, 80, 30)
    assert s["steps_press"] == 200
    assert s["stop_time_range"] == (160, 240)
    assert s["static_checkpoints"] == [100, 170]


@pytest.mark.parametrize(
    "label,steps_press,window,checkpoints",
    [
        ("xhard14", 280, (240, 320), [100, 200, 250]),
        ("xhard16", 360, (320, 400), [100, 200, 300, 330]),
        ("xhard18", 390, (360, 420), [100, 200, 300, 360]),
        ("xhard20", 440, (400, 480), [100, 200, 300, 400, 410]),
    ],
)
def test_stopcube_schedule_xhard(label, steps_press, window, checkpoints):
    knobs = TIER_CONFIGS["StopCube"][label]["knobs"]
    s = stop_cube.stopcube_schedule(knobs["stop_k"], knobs["move_interval"], 30)
    assert s["steps_press"] == steps_press
    assert s["stop_time_range"] == window
    assert s["static_checkpoints"] == checkpoints
    # 按停窗口必须被方块往返的程数覆盖
    assert stop_cube.move_segment_count(knobs["stop_k"]) * knobs["move_interval"] >= window[1]


def test_stopcube_move_segment_count():
    assert [stop_cube.move_segment_count(k) for k in (2, 3, 4, 5, 6, 7)] == [5, 5, 5, 5, 6, 7]


def test_stopcube_parent_module_exports_used_names():
    m = stop_cube._stopcube_module
    for name in ("before_absTimestep", "solve_hold_obj_absTimestep", "is_button_pressed", "move_straight_line"):
        assert callable(getattr(m, name)), name


def _strip_body(src: str) -> list[str]:
    lines = []
    for line in textwrap.dedent(src).splitlines():
        line = line.split("  # xhard 改动")[0].rstrip()
        if line.strip():
            lines.append(line)
    return lines


def test_stopcube_step_is_verbatim_copy_except_marked_lines():
    parent = inspect.getsource(StopCube.step)
    parent = parent.replace("super().step(action)", "super(StopCube, self).step(action)")
    parent = parent.replace("for segment in range(5):", "for segment in range(move_segment_count(self.stop_time)):")
    ours = [
        line
        for line in _strip_body(inspect.getsource(StopCubeXHard.step))
        if "= _stopcube_module." not in line
    ]
    assert ours == _strip_body(parent)
    # 改动行确实带标记
    src = inspect.getsource(StopCubeXHard.step)
    assert src.count("# xhard 改动") == 2


def test_stopcube_initialize_episode_replaces_values_only(monkeypatch):
    head = {"name": "move to the top of the button to prepare"}
    tail = {"name": "press the button to stop the cube on the target"}
    calls = []

    def fake_parent(self, env_idx, options):
        calls.append(1)
        self.interval = 30
        self.move_interval = 120
        self.stop_time = 2
        self.steps_press = 180
        self.stop_time_range = (120, 240)
        self.start_pos_xy = "母起点"
        self.task_list = [head, {"name": "remain static"}, tail]

    monkeypatch.setattr(StopCube, "_initialize_episode", fake_parent)
    env = object.__new__(StopCubeXHard)
    env.xhard_knobs = dict(TIER_CONFIGS["StopCube"]["xhard18"]["knobs"])
    StopCubeXHard._initialize_episode(env, None, None)
    assert calls == [1]
    assert (env.stop_time, env.move_interval) == (7, 60)
    assert (env.xhard_mother_stop_time, env.xhard_mother_move_interval) == (2, 120)
    assert env.steps_press == 390 and env.stop_time_range == (360, 420)
    assert env.start_pos_xy == "母起点"
    assert env.task_list[0] is head and env.task_list[-1] is tail
    statics = env.task_list[1:-1]
    assert [t["name"] for t in statics] == ["remain static"] * 4
    assert all(t["specialflag"] == "swap" and t["demonstration"] is False for t in statics)


def test_stopcube_initialize_episode_rejects_unexpected_task_list(monkeypatch):
    def fake_parent(self, env_idx, options):
        self.interval, self.move_interval, self.stop_time = 30, 80, 3
        self.task_list = [{"name": "x"}, {"name": "y"}]

    monkeypatch.setattr(StopCube, "_initialize_episode", fake_parent)
    env = object.__new__(StopCubeXHard)
    env.xhard_knobs = dict(TIER_CONFIGS["StopCube"]["xhard14"]["knobs"])
    with pytest.raises(RuntimeError):
        StopCubeXHard._initialize_episode(env, None, None)


# ---------------------------------------------------------------- PickHighlight


def test_pickhighlight_counts():
    pick_highlight.check_highlight_counts(6, 6, 6, 6)  # R5：全抓保留
    with pytest.raises(SceneGenerationError):
        pick_highlight.check_highlight_counts(5, 4, 6, 4)
    with pytest.raises(SceneGenerationError):
        pick_highlight.check_highlight_counts(6, 3, 6, 4)


def test_pickhighlight_load_scene_checks(monkeypatch):
    def fake_parent(self, options):
        self.all_cubes = [object()] * 6
        self.target_cubes = self.all_cubes[:5]

    monkeypatch.setattr(PickHighlight, "_load_scene", fake_parent)
    env = object.__new__(PickHighlightXHard)
    env.xhard_knobs = dict(TIER_CONFIGS["PickHighlight"]["xhard16"]["knobs"])
    PickHighlightXHard._load_scene(env, None)
    env.xhard_knobs = dict(TIER_CONFIGS["PickHighlight"]["xhard18"]["knobs"])
    with pytest.raises(SceneGenerationError):
        PickHighlightXHard._load_scene(env, None)


# ---------------------------------------------------------------- VideoPlaceButton


def test_vpb_choose_sides():
    assert vpb.choose_sides(15500, 2, "xhard14") == ["front", "back"]
    first = vpb.choose_sides(15500, 1, "xhard12")
    assert first == vpb.choose_sides(15500, 1, "xhard12")  # 同 seed 同档可复现
    sides = {vpb.choose_sides(s, 1, "xhard12")[0] for s in range(200)}
    assert sides == {"front", "back"}
    with pytest.raises(ValueError):
        vpb.choose_sides(1, 3, "xhard16")


def test_vpb_insert_and_shift():
    tasks = list("ABCDEFG")  # D 是“放 target_1”
    new, shift = vpb.insert_extra_groups(tasks, ["front", "back"], 3, ["f1", "f2"], ["b1", "b2"])
    assert new == ["f1", "f2", "A", "B", "C", "D", "b1", "b2", "E", "F", "G"]
    for i, t in enumerate(tasks):
        assert new[shift(i)] == t
    new, shift = vpb.insert_extra_groups(tasks, ["back"], 3, ["f1", "f2"], ["b1", "b2"])
    assert new == ["A", "B", "C", "D", "b1", "b2", "E", "F", "G"]
    assert shift(None) is None
    for i, t in enumerate(tasks):
        assert new[shift(i)] == t


def _vpb_parent_task_list(env):
    def t(name, seg, demo=True):
        return {"name": name, "segment": seg, "demonstration": demo}

    return [
        t("pick up the cube", env.target_cube),
        t("drop the cube onto target", env.target_0),
        t("press the button", "cap"),
        t("pick up the cube", env.target_cube),
        t("drop the cube onto target", env.target_1),
        t("pick up the cube", env.target_cube),
        t("drop the cube onto table", None),
        t("static", None),
        t("static", None),
        t("NO RECORD", None),
        t("pick up the cube", env.target_cube, False),
        t("place the cube onto the correct target", env.target_0, False),
    ]


@pytest.mark.parametrize("label", ["xhard12", "xhard14"])
def test_vpb_load_scene_rebuilds_task_list(monkeypatch, label):
    def fake_parent(self, options):
        for name in ("target_0", "target_1", "target_2", "target_3", "target_cube"):
            setattr(self, name, types.SimpleNamespace(name=name))
        self.pre_flag = self.post_flag = 0
        self.task_list = _vpb_parent_task_list(self)
        self.fail_grasp_task_index = 5

    monkeypatch.setattr(VideoPlaceButton, "_load_scene", fake_parent)
    env = object.__new__(VideoPlaceButtonXHard)
    env.seed = 15500
    env.xhard_label = label
    env.xhard_knobs = dict(TIER_CONFIGS["VideoPlaceButton"][label]["knobs"])
    VideoPlaceButtonXHard._load_scene(env, None)
    sides = env.xhard_extra_sides
    assert sides == vpb.choose_sides(15500, env.xhard_knobs["extra_groups"], label)
    demo_drops = [
        t["segment"].name
        for t in env.task_list
        if t["demonstration"] and t["name"] == "drop the cube onto target"
    ]
    expect = (["target_2"] if "front" in sides else []) + ["target_0", "target_1"] + (["target_3"] if "back" in sides else [])
    assert demo_drops == expect
    names = [t["name"] for t in env.task_list]
    i_btn = names.index("press the button")
    # 按钮紧前落点 target_0、紧后第一落点 target_1 不变
    assert env.task_list[i_btn - 1]["segment"].name == "target_0"
    assert env.task_list[i_btn + 2]["segment"].name == "target_1"
    assert len(env.task_list) == 12 + 2 * len(sides)
    # 失败注入下标随插入平移，仍指向原第 5 项（放 target_1 之后的那次抓）
    assert env.task_list[env.fail_grasp_task_index]["name"] == "pick up the cube"
    assert env.task_list[env.fail_grasp_task_index - 1]["segment"].name == ("target_3" if "back" in sides else "target_1")
    # 新增任务全部是演示段、只用已有物体
    assert all(t["segment"] in (env.target_cube, env.target_2, env.target_3) for t in env.task_list if "func" in t)
    # 恢复索引按新清单重算
    assert env.recovery_pickup_indices == vpb._vpb_module.task4recovery(env.task_list)[0]


def test_vpb_load_scene_rejects_additional_place(monkeypatch):
    def fake_parent(self, options):
        for name in ("target_0", "target_1", "target_2", "target_3", "target_cube"):
            setattr(self, name, types.SimpleNamespace(name=name))
        self.pre_flag, self.post_flag = 1, 0
        self.task_list = _vpb_parent_task_list(self)
        self.fail_grasp_task_index = None

    monkeypatch.setattr(VideoPlaceButton, "_load_scene", fake_parent)
    env = object.__new__(VideoPlaceButtonXHard)
    env.seed, env.xhard_label = 1, "xhard14"
    env.xhard_knobs = {"extra_groups": 2}
    with pytest.raises(SceneGenerationError):
        VideoPlaceButtonXHard._load_scene(env, None)


def test_vpb_parent_module_exports_used_names():
    for name in ("is_obj_pickup", "solve_pickup", "is_obj_dropped_onto", "solve_putonto_whenhold", "task4recovery"):
        assert callable(getattr(vpb._vpb_module, name)), name


# ---------------------------------------------------------------- VideoPlaceOrder


def test_vpo_extend_targets():
    t = [types.SimpleNamespace(i=i) for i in range(4)]
    assert vpo.extend_targets([t[2], t[0], t[3]], t, 4) == [t[2], t[0], t[3], t[1]]
    assert vpo.extend_targets([t[1], t[3]], t, 4) == [t[1], t[3], t[0], t[2]]
    assert vpo.extend_targets([t[1], t[3], t[0], t[2]], t, 4) == [t[1], t[3], t[0], t[2]]
    with pytest.raises(SceneGenerationError):
        vpo.extend_targets([t[0], t[1]], t[:3], 4)
    with pytest.raises(SceneGenerationError):
        vpo.extend_targets([t[0], t[0]], t, 4)


def test_vpo_load_scene_keeps_answer(monkeypatch):
    t = [types.SimpleNamespace(i=i) for i in range(4)]

    def fake_parent(self, options):
        self.targets = t
        self.which_targets_to_pick = [t[3], t[1], t[0]]
        self.which_in_subset = 2
        self.target_target = t[1]
        self.button_task_index = 6

    monkeypatch.setattr(VideoPlaceOrder, "_load_scene", fake_parent)
    env = object.__new__(VideoPlaceOrderXHard)
    env.xhard_knobs = dict(TIER_CONFIGS["VideoPlaceOrder"]["xhard12"]["knobs"])
    VideoPlaceOrderXHard._load_scene(env, None)
    assert env.which_targets_to_pick == [t[3], t[1], t[0], t[2]]
    assert env.xhard_mother_num_targets == 3
    assert env.which_targets_to_pick[env.which_in_subset - 1] is env.target_target
    assert env.which_in_subset in num2words_2


# ---------------------------------------------------------------- PatternLock / RouteStick


def test_patternlock_check_path_length():
    pattern_lock.check_path_length(9, 9)
    with pytest.raises(SceneGenerationError):
        pattern_lock.check_path_length(8, 9)
    with pytest.raises(SceneGenerationError):
        pattern_lock.check_path_length(12, 11)


def test_patternlock_load_scene_fails_loud_on_exhausted_sampling(monkeypatch):
    def fake_parent(self, options):
        # 模拟父类拒绝采样耗尽后“用最后一条”的静默行为
        self.selected_buttons = [object()] * 6

    monkeypatch.setattr(PatternLock, "_load_scene", fake_parent)
    env = object.__new__(PatternLockXHard)
    env.xhard_knobs = dict(TIER_CONFIGS["PatternLock"]["xhard20"]["knobs"])
    with pytest.raises(SceneGenerationError):
        PatternLockXHard._load_scene(env, None)


@pytest.mark.parametrize("label", list(TIER_CONFIGS["PatternLock"]))
def test_patternlock_fixed_length_is_reachable_on_grid5(label):
    """复刻父类拒绝采样（纯 CPU、不建环境）：两个 seed 下固定长度都能在 1000 次内采到。"""
    from robomme.robomme_env.utils.adjacent import find_path_0_to_8

    cfg = PatternLockXHard.configs[label]
    lo, hi = cfg["length"]
    grid = cfg["grid"]
    for seed in (4301, 9102):
        g = torch.Generator()
        g.manual_seed(seed)
        for _ in range(1000):
            s, e = torch.randperm(grid * grid, generator=g)[:2].tolist()
            path, _, _, _ = find_path_0_to_8(start=s, target=e, R=grid, C=grid, diagonals=True, generator=g)
            if lo <= len(path) <= hi:
                break
        pattern_lock.check_path_length(len(path), TIER_CONFIGS["PatternLock"][label]["knobs"]["length"])


def test_routestick_check_route_length():
    route_stick.check_route_length(7, 6, 6)
    with pytest.raises(SceneGenerationError):
        route_stick.check_route_length(6, 5, 6)
    with pytest.raises(SceneGenerationError):
        route_stick.check_route_length(7, 5, 6)


@pytest.mark.parametrize("label", list(TIER_CONFIGS["RouteStick"]))
def test_routestick_walk_has_exact_edges(label):
    from robomme.robomme_env.utils.route import generate_dynamic_walk

    cfg = RouteStickXHard.configs[label]
    assert cfg["backtrack"] is True
    for seed in (3, 51):
        g = torch.Generator()
        g.manual_seed(seed)
        steps = int(torch.randint(cfg["length"][0], cfg["length"][1] + 1, (1,), generator=g).item())
        path = generate_dynamic_walk([0, 2, 4, 6, 8], steps=steps, allow_backtracking=True, generator=g)
        route_stick.check_route_length(len(path), steps, TIER_CONFIGS["RouteStick"][label]["knobs"]["length"])


# ---------------------------------------------------------------- 需要仿真（主会话合并后跑）


@pytest.mark.gpu
@pytest.mark.slow
@pytest.mark.parametrize("task,label", [(t, d) for t in S1 for d in TIER_CONFIGS[t]])
def test_gym_make_reset_each_tier(task, label):
    """每个有效档 gym.make + reset 一次，核对实例旋钮落地。仅主会话在主检出串行跑。"""
    import gymnasium as gym

    from robomme_xhard.configs import tier

    seeds = {
        "BinFill": 4301, "PickXtimes": 7101, "SwingXtimes": 7101, "StopCube": 10700,
        "PickHighlight": 7101, "VideoPlaceButton": 15500, "VideoPlaceOrder": 7101,
        "PatternLock": 7101, "RouteStick": 7101,
    }
    env = gym.make(
        env_name(task),
        obs_mode="rgb+depth+segmentation",
        control_mode="pd_joint_pos",
        render_mode="rgb_array",
        reward_mode="dense",
        seed=seeds[task],
        difficulty=label,
    )
    try:
        env.reset()
        u = env.unwrapped
        knobs = tier(task, label)["knobs"]
        assert u.difficulty == label and u.spec.id == task
        if task == "BinFill":
            assert u.red_cubes_target_number + u.blue_cubes_target_number + u.green_cubes_target_number == knobs["target_total"]
        elif task in ("PickXtimes", "SwingXtimes"):
            assert u.num_repeats == knobs["repeats"]
        elif task == "StopCube":
            assert (u.stop_time, u.move_interval) == (knobs["stop_k"], knobs["move_interval"])
        elif task == "PickHighlight":
            assert (len(u.all_cubes), len(u.target_cubes)) == (knobs["spawn"], knobs["pickup"])
        elif task == "VideoPlaceOrder":
            assert len(u.which_targets_to_pick) == knobs["num_targets"]
        elif task == "PatternLock":
            assert len(u.selected_buttons) == knobs["length"]
        elif task == "RouteStick":
            assert len(u.selected_buttons) - 1 == knobs["length"]
    finally:
        env.close()
