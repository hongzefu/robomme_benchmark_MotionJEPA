"""只验证实际碰撞组件的几何计算，不维护另一份任务素材定义。"""

from types import SimpleNamespace
import math

import numpy as np
import pytest

from robomme_icl.validation.geometry import (
    Box,
    actual_boxes,
    box_clearance,
    quaternion_matrix,
)


def actor(
    position=(0.0, 0.0, 0.0),
    quaternion=(1.0, 0.0, 0.0, 0.0),
    offsets=((0.0, 0.0, 0.0),),
    half_size=(0.02, 0.02, 0.02),
):
    shapes = [
        SimpleNamespace(
            half_size=np.array(half_size),
            local_pose=SimpleNamespace(
                p=np.array(offset), q=np.array([1.0, 0.0, 0.0, 0.0])
            ),
        )
        for offset in offsets
    ]
    return SimpleNamespace(
        pose=SimpleNamespace(p=np.array([position]), q=np.array([quaternion])),
        _bodies=[SimpleNamespace(collision_shapes=shapes)],
    )


def test_actual_shape_local_pose_is_transformed_to_world():
    half_angle = math.pi / 4
    value = actor(
        position=(1.0, 2.0, 3.0),
        quaternion=(math.cos(half_angle), 0.0, 0.0, math.sin(half_angle)),
        offsets=((0.1, 0.0, 0.0),),
    )
    box = actual_boxes(value)[0]
    assert np.allclose(box.center, (1.0, 2.1, 3.0), rtol=0, atol=1e-14)


def test_actual_compound_hole_is_not_replaced_by_solid_envelope():
    compound = actual_boxes(actor(offsets=((-0.1, 0.0, 0.0), (0.1, 0.0, 0.0))))
    center = actual_boxes(actor(half_size=(0.01, 0.01, 0.01)))[0]
    assert len(compound) == 2
    assert min(box_clearance(part, center) for part in compound) == pytest.approx(0.07)


@pytest.mark.parametrize("distance,expected", [(0.0, -0.04), (0.04, 0.0), (0.07, 0.03)])
def test_separation_sign_and_contact_boundary(distance, expected):
    first = actual_boxes(actor())[0]
    second = actual_boxes(actor(position=(distance, 0.0, 0.0)))[0]
    assert box_clearance(first, second) == pytest.approx(expected)


def test_rotated_box_projection_keeps_true_corners():
    rotation = quaternion_matrix(
        (math.cos(math.pi / 8), 0.0, 0.0, math.sin(math.pi / 8))
    )
    box = Box((0.0, 0.0, 0.0), tuple(zip(*rotation)), (0.02, 0.02, 0.02))
    assert box.radius_on((1.0, 0.0, 0.0)) == pytest.approx(0.02 * math.sqrt(2))


def test_unknown_collision_type_fails_instead_of_being_ignored():
    value = actor()
    value._bodies[0].collision_shapes = [
        SimpleNamespace(
            local_pose=SimpleNamespace(p=np.zeros(3), q=np.array([1.0, 0.0, 0.0, 0.0]))
        )
    ]
    with pytest.raises(ValueError, match="尚未支持"):
        actual_boxes(value)
