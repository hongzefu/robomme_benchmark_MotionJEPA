"""真实空腔、连续轨迹和扫掠碰撞证书的可复现反例。"""

import copy
import math

import pytest

from robomme_icl.geometry import actor_boxes, box_clearance, box_components, pose_at_step, validate_spec_geometry


def _actor(name, x, y, kind="container", z=.036):
    return {"id": name, "kind": kind, "position": [x, y, z], "quaternion": [1, 0, 0, 0],
            "half_size": [.030, .030, .036], "color": [1, 0, 0, 1], "role": "object"}


def _rectangle(pair=("a", "d")):
    return {"actors": [_actor("a", -.07, -.07), _actor("b", -.07, .07),
                       _actor("c", .07, -.07), _actor("d", .07, .07)],
            "geometry": {"safety_clearance": .005},
            "swaps": [{"a": pair[0], "b": pair[1], "start_step": 0, "end_step": 50, "lane_offset": .07}]}


def test_compound_container_preserves_hidden_cube_clearance():
    container = _actor("container", 0, 0)
    cube = _actor("cube", 0, 0, "cube", .02/1.2)
    cube["half_size"] = [.02/1.2]*3
    cube["parent_id"] = "container"
    components = box_components(container)
    central = next(part for part in components if part["name"] == "central")
    assert central["half_size"][2]*2 == .030
    assert container["position"][2]+central["position"][2]+central["half_size"][2] == pytest.approx(.072)
    boxes, small_box = actor_boxes(container), actor_boxes(cube)[0]
    assert box_clearance(boxes[0], small_box) == pytest.approx(.00866666666666666)
    assert min(box_clearance(box, small_box) for box in boxes) == pytest.approx(.00833333333333333)
    assert validate_spec_geometry({"actors": [container, cube]})["ok"]
    old = validate_spec_geometry({"actors": [container, cube], "geometry": {"central_box_thickness": .040}})
    assert not old["ok"]
    assert old["min_clearance"] == pytest.approx(-.001333333333333333)


def test_diagonal_swap_is_rejected_between_control_frames():
    data = _rectangle()
    report = validate_spec_geometry(data)
    assert not report["ok"]
    assert report["min_clearance"] < 0
    assert any("交换" in reason for reason in report["reasons"])


def test_diagonal_swap_two_mm_compound_wall_penetration():
    data = _rectangle()
    half_span = .0555+.07/math.sqrt(2)
    for actor in data["actors"]:
        actor["position"][0] = math.copysign(half_span, actor["position"][0])
        actor["position"][1] = math.copysign(half_span, actor["position"][1])
    report = validate_spec_geometry(data)
    assert not report["ok"]
    assert report["min_clearance"] == pytest.approx(-.002)


@pytest.mark.parametrize("pair", [("a", "b"), ("a", "c"), ("b", "d"), ("c", "d")])
def test_all_edge_swaps_have_continuous_five_mm_certificate(pair):
    report = validate_spec_geometry(_rectangle(pair))
    assert report["ok"], report
    assert report["min_clearance"] >= .005
    assert report["subdivisions"] > 0


def test_stateless_sequential_swap_and_attached_cube():
    data = _rectangle(("a", "b"))
    child = _actor("hidden", -.07, -.07, "cube", .02/1.2)
    child["half_size"] = [.02/1.2]*3
    child["parent_id"] = "a"
    data["actors"].append(child)
    data["swaps"].append({"a": "b", "b": "d", "start_step": 50, "end_step": 100, "lane_offset": .07})
    baseline = copy.deepcopy(data)
    end = pose_at_step(data, 100)
    for time in (74.333, 0, 25, 50, 1, 100):
        pose_at_step(data, time)
    assert end == pose_at_step(data, 100)
    assert end["hidden"]["position"][:2] == end["a"]["position"][:2]
    assert end["hidden"]["position"][2] == pytest.approx(.02/1.2)
    assert data == baseline


def test_rotated_box_separation_uses_all_axes():
    first = _actor("first", 0, 0, "cube", .02)
    first["half_size"] = [.02]*3
    second = copy.deepcopy(first)
    second["position"][0] = .05
    second["quaternion"] = [math.cos(math.pi/8), 0, 0, math.sin(math.pi/8)]
    assert 0 < box_clearance(actor_boxes(first)[0], actor_boxes(second)[0]) < .005


def test_table_edge_rejection_includes_object_extent():
    data = {"actors": [_actor("edge", .48, 0)]}
    assert not validate_spec_geometry(data)["ok"]


def test_rejects_overlapping_swap_time_windows():
    data = _rectangle(("a", "b"))
    data["swaps"].append({"a": "c", "b": "d", "start_step": 49, "end_step": 99, "lane_offset": .07})
    with pytest.raises(ValueError, match="不能重叠"):
        validate_spec_geometry(data)


def test_rotated_cube_corners_must_fit_initial_support():
    cube = _actor("cube", 0, 0, "cube", .02)
    cube["half_size"] = [.02]*3
    cube["quaternion"] = [math.cos(math.pi/8), 0, 0, math.sin(math.pi/8)]
    cube["initial_xy_bounds"] = {"x": [-.02, .02], "y": [-.02, .02]}
    report = validate_spec_geometry({"actors": [cube]})
    assert not report["ok"]
    assert any("完整物体越出位置支持框" in reason for reason in report["reasons"])
    # 初始支持越界与碰撞距离是两个量，不能把越界量伪装成负物理净距。
    assert report["min_clearance"] > .005


def test_rotated_cube_can_touch_initial_support_without_extra_collision_margin():
    cube = _actor("cube", 0, 0, "cube", .02)
    cube["half_size"] = [.02]*3
    cube["quaternion"] = [math.cos(math.pi/8), 0, 0, math.sin(math.pi/8)]
    extent = math.sqrt(2)*.02
    cube["initial_xy_bounds"] = {"x": [-extent, extent], "y": [-extent, extent]}
    report = validate_spec_geometry({"actors": [cube]})
    assert report["ok"], report
    assert report["min_clearance"] > .005


def test_initial_support_checks_container_walls_not_only_roof_or_center():
    container = _actor("container", 0, 0)
    container["initial_xy_bounds"] = {"x": [-.0275, .0275], "y": [-.0275, .0275]}
    report = validate_spec_geometry({"actors": [container]})
    assert not report["ok"]
    assert any("位置支持框" in reason for reason in report["reasons"])
    container["initial_xy_bounds"] = {"x": [-.030, .030], "y": [-.030, .030]}
    assert validate_spec_geometry({"actors": [container]})["ok"]


def test_swap_may_leave_an_actor_initial_support_window():
    data = _rectangle(("a", "b"))
    for actor in data["actors"]:
        x, y = actor["position"][:2]
        actor["initial_xy_bounds"] = {"x": [x-.03, x+.03], "y": [y-.03, y+.03]}
    report = validate_spec_geometry(data)
    assert report["ok"], report
    assert report["min_clearance"] >= .005
    middle = pose_at_step(data, 25)["a"]["position"]
    assert middle[0] < data["actors"][0]["initial_xy_bounds"]["x"][0]


def test_compiler_zero_width_support_rejection_cannot_be_rescued_by_tolerance():
    cube = _actor("cube", 0, 0, "cube", .02)
    cube["half_size"] = [.02]*3
    cube["initial_xy_bounds"] = {"x": [-.02, .02], "y": [-.02, .02]}
    assert validate_spec_geometry({"actors": [cube]})["ok"]
    cube["initial_support_rejection"] = "固定中心层与旋转后完整物体可行域交集宽度为零"
    report = validate_spec_geometry({"actors": [cube]})
    assert not report["ok"]
    assert any("初始支持层不可采样" in reason for reason in report["reasons"])
    assert report["min_clearance"] > .005
