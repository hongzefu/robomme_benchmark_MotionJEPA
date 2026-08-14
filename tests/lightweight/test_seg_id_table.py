"""seg_id 枚举表的逻辑测试（假 env + 内存 h5，毫秒级）。

这张表是 GT 三类映射的唯一依据：没有它，逐帧落盘的 segmentation 就只是一堆无法解释的
整数。覆盖四件事：

1. **剔除判据**：机器人 articulation 的 link → `robot_link`；背景黑名单 →
   `background_prop`；其余留作任务物体。判据用「所属 articulation 是不是机器人」而不是
   `panda_` 名字前缀——stick 环境命名不同，靠前缀会漏。
2. **TCP 加回**：它属于机器人 articulation，会被第一条剔掉，必须单独加回并标
   `kind == "tcp"`（下游据此把它归机械臂而非任务物体）。
3. **key 命名**：`<原名>__<seg_id>`。link 名只在自己 articulation 内唯一，带上 seg_id
   才能保证 h5 里的 group 名不撞。
4. **端到端闭环**：落盘字段名是 `segmentation_objects` / `segmentation_excluded`，且
   写出去的表能被 `color_model.class_ids_from_setup` 正确读回成三类——这一条把生产侧
   与消费侧的字段名钉在一起，任何一边改名都会红。
"""

from __future__ import annotations

import importlib
import io
import sys
from pathlib import Path

import h5py
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
GT_DATA_DIR = REPO_ROOT / "scripts" / "data-generation" / "gt-data"
if str(GT_DATA_DIR) not in sys.path:
    sys.path.insert(0, str(GT_DATA_DIR))

seg_id_table = importlib.import_module("seg_id_table")
color_model = importlib.import_module("color_model")

SegIdTable = seg_id_table.SegIdTable
write_seg_id_table = seg_id_table.write_seg_id_table
REASON_ROBOT_LINK = seg_id_table.REASON_ROBOT_LINK
REASON_BACKGROUND = seg_id_table.REASON_BACKGROUND
class_ids_from_setup = color_model.class_ids_from_setup


class _Obj:
    """最小的 duck-typing 替身：模块只读 .name 与 .articulation。"""

    def __init__(self, name: str, articulation=None):
        self.name = name
        self.articulation = articulation


class _Agent:
    def __init__(self, robot, tcp):
        self.robot = robot
        self.tcp = tcp


class _Env:
    def __init__(self, id_map, agent):
        self.segmentation_id_map = id_map
        self.agent = agent


def _fake_env():
    """一个机器人（2 个 link）+ 桌面 + 地面 + 2 个任务物体 + TCP。"""
    robot = _Obj("panda")
    tcp = _Obj("panda_hand_tcp", articulation=robot)
    id_map = {
        1: _Obj("panda_link0", articulation=robot),
        2: _Obj("panda_link1", articulation=robot),
        16: _Obj("table-workspace"),
        17: _Obj("ground"),
        22: _Obj("fixed_cube"),
        18: _Obj("peg_head", articulation=_Obj("peg")),  # 非机器人 articulation → 物体
        11: tcp,
    }
    return _Env(id_map, _Agent(robot, tcp))


def test_剔除判据按articulation归属而非名字前缀():
    table = SegIdTable(_fake_env())
    excluded = {item.seg_id: item.reason for item in table.excluded}
    assert excluded == {1: REASON_ROBOT_LINK, 2: REASON_ROBOT_LINK,
                        16: REASON_BACKGROUND, 17: REASON_BACKGROUND}
    # peg_head 的 articulation 不是机器人，必须留作任务物体
    assert {item.seg_id for item in table.objects} == {22, 18, 11}


def test_tcp被加回且标kind为tcp():
    table = SegIdTable(_fake_env())
    tcp_entries = [item for item in table.objects if item.kind == "tcp"]
    assert len(tcp_entries) == 1
    assert tcp_entries[0].seg_id == 11
    # 加回后不得同时残留在剔除表里
    assert 11 not in {item.seg_id for item in table.excluded}


def test_key命名是原名加seg_id():
    table = SegIdTable(_fake_env())
    keys = {item.key for item in table.objects} | {item.key for item in table.excluded}
    assert "panda_link0__1" in keys
    assert "fixed_cube__22" in keys
    assert "panda_hand_tcp__11" in keys


def test_同名link带不同seg_id不撞key():
    """两个 button articulation 各有一个同名 link——这正是 key 要带 seg_id 的理由。"""
    robot = _Obj("panda")
    id_map = {
        30: _Obj("handle", articulation=_Obj("button_a")),
        31: _Obj("handle", articulation=_Obj("button_b")),
    }
    table = SegIdTable(_Env(id_map, _Agent(robot, None)))
    keys = [item.key for item in table.objects]
    assert sorted(keys) == ["handle__30", "handle__31"]


def test_落盘字段名与三类映射端到端闭环():
    table = SegIdTable(_fake_env())
    with h5py.File(io.BytesIO(), "w") as handle:
        setup = handle.create_group("setup")
        write_seg_id_table(setup, table)

        # 字段名必须是 segmentation_*（消费侧 class_ids_from_setup 按此读）
        assert set(setup.keys()) == {"segmentation_objects", "segmentation_excluded"}

        ids = class_ids_from_setup(setup)
        # 机器人两个 link + TCP 归机械臂；桌面地面 + seg_id 0 归背景；其余归物体
        assert ids["arm"] == {1, 2, 11}
        assert ids["background"] == {0, 16, 17}
        assert ids["object"] == {22, 18}


def test_拒绝覆盖已存在的表():
    table = SegIdTable(_fake_env())
    with h5py.File(io.BytesIO(), "w") as handle:
        setup = handle.create_group("setup")
        write_seg_id_table(setup, table)
        with pytest.raises(ValueError, match="拒绝覆盖"):
            write_seg_id_table(setup, table)


def test_空场景不炸():
    table = SegIdTable(_Env({}, _Agent(None, None)))
    assert table.objects == []
    assert table.excluded == []
