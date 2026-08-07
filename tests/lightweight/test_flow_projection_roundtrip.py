"""2D flow ground truth 链路新增投影函数的把关测试。

三件事必须锁死：

1. **新旧路径逐位相等**：新的子像素投影经过 rint 取整与边界裁剪之后，必须与既有的
   ``project_world_to_pixel`` 输出完全一致。既有 ``choice_action`` 的像素口径不允许有
   任何漂移，这一条是它的保险丝。
2. **正反转换闭环**：投影再反投影必须精确还原世界坐标，这是「(u, v, z_cam) ↔ 世界坐标是
   严格双射」这一主张的直接证据。
3. **雅可比二阶收敛**：证明 2D 位移确实是 3D 位移的正确微分像，而不是碰巧数值接近。

本文件是纯 numpy 计算，不需要 GPU 也不需要渲染栈，因此**不标 gpu marker**，会进默认档
（``-m "not slow and not gpu"``）。注意同目录的 ``test_choice_action_pixel_mapping.py``
标了 gpu，默认档会把它 deselect 掉，改投影相关代码时必须单独跑那个文件。
"""

from __future__ import annotations

import importlib.util

import numpy as np
import pytest

from tests._shared.repo_paths import find_repo_root

pytestmark = [pytest.mark.lightweight]


def _load_module(module_name: str, relative_path: str):
    repo_root = find_repo_root(__file__)
    module_path = repo_root / relative_path
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


mapping_mod = _load_module(
    "choice_action_mapping_flow_under_test",
    "src/robomme/robomme_env/utils/choice_action_mapping.py",
)


IMAGE_SIZE = 256
SAMPLE_COUNT = 10_000


def _camera() -> tuple[np.ndarray, np.ndarray, tuple[int, int, int]]:
    """构造一台与 base_camera 同规格的相机：256x256、90 度 fov，外参为非平凡刚体变换。

    刻意不用单位旋转——单位阵会让「转置 == 求逆」之类的错误实现也能蒙混过关。
    """
    focal = IMAGE_SIZE / 2.0  # fov = 90 度时 f = (W/2) / tan(45 度) = W/2
    intrinsic = np.array(
        [
            [focal, 0.0, IMAGE_SIZE / 2.0],
            [0.0, focal, IMAGE_SIZE / 2.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )

    # 用三个欧拉角合成一个明确的旋转，避免依赖 scipy
    alpha, beta, gamma = 0.31, -0.47, 0.85
    rot_x = np.array(
        [
            [1.0, 0.0, 0.0],
            [0.0, np.cos(alpha), -np.sin(alpha)],
            [0.0, np.sin(alpha), np.cos(alpha)],
        ],
        dtype=np.float64,
    )
    rot_y = np.array(
        [
            [np.cos(beta), 0.0, np.sin(beta)],
            [0.0, 1.0, 0.0],
            [-np.sin(beta), 0.0, np.cos(beta)],
        ],
        dtype=np.float64,
    )
    rot_z = np.array(
        [
            [np.cos(gamma), -np.sin(gamma), 0.0],
            [np.sin(gamma), np.cos(gamma), 0.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    rotation = rot_z @ rot_y @ rot_x
    translation = np.array([0.12, -0.34, 0.56], dtype=np.float64)

    extrinsic = np.zeros((3, 4), dtype=np.float64)
    extrinsic[:, :3] = rotation
    extrinsic[:, 3] = translation
    return intrinsic, extrinsic, (IMAGE_SIZE, IMAGE_SIZE, 3)


def _sample_world_points(count: int, margin: float = 1.0) -> np.ndarray:
    """采样一批保证「深度为正且投影落在画幅内」的世界坐标点。

    做法是反着来：先在相机系里采 (u, v, z)，再反投影成世界坐标。这样正向投影时必然
    落在界内，新旧两条路径都会走主分支、都不会返回 None，等价性断言才有意义。
    """
    intrinsic, extrinsic, _ = _camera()
    rng = np.random.default_rng(20260806)

    pixels_u = rng.uniform(margin, IMAGE_SIZE - 1.0 - margin, size=count)
    pixels_v = rng.uniform(margin, IMAGE_SIZE - 1.0 - margin, size=count)
    depths = rng.uniform(0.3, 3.0, size=count)

    points = np.empty((count, 3), dtype=np.float64)
    for index in range(count):
        world = mapping_mod.unproject_pixel_to_world(
            pixels_u[index],
            pixels_v[index],
            depths[index],
            intrinsic_cv=intrinsic,
            extrinsic_cv=extrinsic,
        )
        assert world is not None
        points[index] = world
    return points


def test_subpixel_matches_legacy_projection_bit_for_bit():
    """新函数取整裁剪后与既有 project_world_to_pixel 逐位相等。"""
    intrinsic, extrinsic, image_shape = _camera()
    points = _sample_world_points(SAMPLE_COUNT)

    mismatches = 0
    for world in points:
        legacy = mapping_mod.project_world_to_pixel(
            world_xyz=world,
            intrinsic_cv=intrinsic,
            extrinsic_cv=extrinsic,
            image_shape=image_shape,
        )
        subpixel = mapping_mod.project_world_to_pixel_subpixel(
            world_xyz=world,
            intrinsic_cv=intrinsic,
            extrinsic_cv=extrinsic,
        )
        assert legacy is not None, "采样点应当都落在画幅内"
        assert subpixel is not None

        u, v, z_cam = subpixel
        assert z_cam > 0.0
        # 既有函数返回 [x=列, y=行]，即 [rint(u), rint(v)]
        if legacy != [int(np.rint(u)), int(np.rint(v))]:
            mismatches += 1
    assert mismatches == 0, f"{mismatches}/{SAMPLE_COUNT} 个点上新旧路径取整结果不一致"


def test_projection_unprojection_roundtrip_is_exact():
    """投影→反投影闭环还原 3D，且再投影回来与原像素一致。"""
    intrinsic, extrinsic, _ = _camera()
    points = _sample_world_points(SAMPLE_COUNT)

    max_world_error = 0.0
    max_pixel_error = 0.0
    for world in points:
        projected = mapping_mod.project_world_to_pixel_subpixel(
            world_xyz=world,
            intrinsic_cv=intrinsic,
            extrinsic_cv=extrinsic,
        )
        assert projected is not None
        u, v, z_cam = projected

        restored = mapping_mod.unproject_pixel_to_world(
            u, v, z_cam, intrinsic_cv=intrinsic, extrinsic_cv=extrinsic
        )
        assert restored is not None
        max_world_error = max(max_world_error, float(np.max(np.abs(restored - world))))

        reprojected = mapping_mod.project_world_to_pixel_subpixel(
            world_xyz=restored,
            intrinsic_cv=intrinsic,
            extrinsic_cv=extrinsic,
        )
        assert reprojected is not None
        max_pixel_error = max(
            max_pixel_error,
            float(max(abs(reprojected[0] - u), abs(reprojected[1] - v))),
        )

    assert max_world_error <= 1e-9, f"闭环还原误差过大：{max_world_error}"
    assert max_pixel_error <= 1e-12, f"重投影误差过大：{max_pixel_error}"


def test_projection_jacobian_is_second_order_accurate():
    """残差 ‖Δ_2d − J·Δ_3d‖ 在步长减半时约降到 1/4，证明 J 确实是一阶导数。"""
    intrinsic, extrinsic, _ = _camera()
    points = _sample_world_points(200)
    rng = np.random.default_rng(11)

    ratios = []
    for world in points:
        jacobian = mapping_mod.projection_jacobian(
            world_xyz=world,
            intrinsic_cv=intrinsic,
            extrinsic_cv=extrinsic,
        )
        assert jacobian is not None
        assert jacobian.shape == (2, 3)

        direction = rng.normal(size=3)
        direction /= np.linalg.norm(direction)

        base = mapping_mod.project_world_to_pixel_subpixel(
            world_xyz=world, intrinsic_cv=intrinsic, extrinsic_cv=extrinsic
        )
        assert base is not None
        base_uv = np.asarray(base[:2], dtype=np.float64)

        def residual(step: float) -> float:
            moved = mapping_mod.project_world_to_pixel_subpixel(
                world_xyz=world + step * direction,
                intrinsic_cv=intrinsic,
                extrinsic_cv=extrinsic,
            )
            assert moved is not None
            delta_2d = np.asarray(moved[:2], dtype=np.float64) - base_uv
            predicted = jacobian @ (step * direction)
            return float(np.linalg.norm(delta_2d - predicted))

        step = 1e-3
        coarse = residual(step)
        fine = residual(step / 2.0)
        if coarse < 1e-11:
            # 该点上一阶近似已经精确到浮点噪声，比值无意义，跳过
            continue
        ratios.append(fine / coarse)

    assert ratios, "所有采样点的残差都退化到浮点噪声，测试没有实际覆盖"
    mean_ratio = float(np.mean(ratios))
    assert 0.20 <= mean_ratio <= 0.30, f"二阶收敛比偏离 0.25：实测 {mean_ratio}"


def test_subpixel_rejects_points_behind_camera():
    """相机后方的点必须被拒绝——深度非正时双射不成立。"""
    intrinsic, extrinsic, _ = _camera()
    # 取一个界内点做对照，再单独构造一个相机后方的点
    world = _sample_world_points(1)[0]
    rotation = extrinsic[:, :3]
    translation = extrinsic[:, 3]
    # 直接在相机系构造 z = -1 的点，再变换回世界系
    camera_point = np.array([0.0, 0.0, -1.0], dtype=np.float64)
    behind_world = np.linalg.solve(rotation, camera_point - translation)

    assert (
        mapping_mod.project_world_to_pixel_subpixel(
            world_xyz=behind_world, intrinsic_cv=intrinsic, extrinsic_cv=extrinsic
        )
        is None
    )
    # 前方的点仍然正常
    assert (
        mapping_mod.project_world_to_pixel_subpixel(
            world_xyz=world, intrinsic_cv=intrinsic, extrinsic_cv=extrinsic
        )
        is not None
    )


def test_subpixel_does_not_fall_back_to_inverted_extrinsic():
    """回归测试：主解释深度非正时**必须**返回 None，绝不能改用求逆后的外参再试一次。

    这里的参数不是编的，取自 MoveCube/episode_0/timestep_0 的真实相机外参，以及 ManiSkill
    把尚未登场的 goal_site 藏起来时用的位置 (10, -10, 1)。在这组数值上：

    - 主解释（extrinsic 即 world->camera）算出的深度是 -4.87，物体在相机后方，不可投影；
    - 把 extrinsic 当 camera->world 求逆再算，深度却是 +3.98，看起来「可以投影」。

    旧的 project_world_to_pixel 会接受后者（对求单个像素点而言那只是无害的防御性兜底），但对
    flow 是致命的：投影用了求逆矩阵、反投影只认主解释，闭环还原会错到 8.63 米。实测就是这么
    发现的，四个任务的判据 1 全挂在这上面。
    """
    # MoveCube/episode_0/timestep_0 的 front_camera_extrinsic（float32 落盘后的精确值）
    extrinsic = [
        [0.0, 1.0, 0.0, 0.0],
        [0.8944271802902222, 0.0, -0.44721364974975586, -0.08944264054298401],
        [-0.4472137689590454, 0.0, -0.8944271802902222, 0.49193501472473145],
    ]
    intrinsic = [[128.0, 0.0, 128.0], [0.0, 128.0, 128.0], [0.0, 0.0, 1.0]]
    hidden_position = [10.0, -10.0, 1.0]  # ManiSkill 藏匿未登场物体的位置

    extrinsic_np = np.asarray(extrinsic, dtype=np.float64)
    world_h = np.asarray(hidden_position + [1.0], dtype=np.float64)
    depth_main = float((extrinsic_np @ world_h)[2])
    extrinsic_4x4 = np.eye(4, dtype=np.float64)
    extrinsic_4x4[:3, :4] = extrinsic_np
    depth_fallback = float((np.linalg.inv(extrinsic_4x4)[:3, :4] @ world_h)[2])

    # 先确认这组数值确实构成「主解释为负、兜底为正」的陷阱，否则测试就白测了
    assert depth_main < 0.0, f"主解释深度应为负，实测 {depth_main}"
    assert depth_fallback > 0.0, f"兜底解释深度应为正，实测 {depth_fallback}"

    assert (
        mapping_mod.project_world_to_pixel_subpixel(
            world_xyz=hidden_position,
            intrinsic_cv=intrinsic,
            extrinsic_cv=extrinsic,
        )
        is None
    ), "相机后方的点必须被拒绝，不允许退回求逆外参产生一个假的投影"

    # 雅可比走同一条外参解析路径，必须同样拒绝
    assert (
        mapping_mod.projection_jacobian(
            world_xyz=hidden_position,
            intrinsic_cv=intrinsic,
            extrinsic_cv=extrinsic,
        )
        is None
    )


def test_unproject_rejects_non_positive_depth():
    """反投影必须拒绝非正深度，不允许静默返回一个假的世界点。"""
    intrinsic, extrinsic, _ = _camera()
    for bad_depth in (0.0, -1.0, float("nan")):
        assert (
            mapping_mod.unproject_pixel_to_world(
                128.0, 128.0, bad_depth, intrinsic_cv=intrinsic, extrinsic_cv=extrinsic
            )
            is None
        )
