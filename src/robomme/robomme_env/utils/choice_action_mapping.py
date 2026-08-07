from typing import Any, Dict, List, Optional

import numpy as np


def _collect_candidates(item: Any, out: List[Any]) -> None:
    if isinstance(item, (list, tuple)):
        for child in item:
            _collect_candidates(child, out)
        return
    if isinstance(item, dict):
        for child in item.values():
            _collect_candidates(child, out)
        return
    if item is not None:
        out.append(item)


def _unique_candidates(available: Any) -> List[Any]:
    candidates: List[Any] = []
    _collect_candidates(available, candidates)
    # Keep object identity uniqueness to avoid redundant scans.
    return list(dict.fromkeys(candidates))


def _to_numpy_array(value: Any, dtype: np.dtype = np.float64) -> Optional[np.ndarray]:
    if value is None:
        return None
    if hasattr(value, "detach"):
        value = value.detach()
    if hasattr(value, "cpu"):
        value = value.cpu()
    try:
        arr = np.asarray(value, dtype=dtype)
    except (TypeError, ValueError):
        return None
    return arr


def normalize_pixel_xy(pixel_like: Any) -> Optional[np.ndarray]:
    arr = _to_numpy_array(pixel_like, dtype=np.float64)
    if arr is None:
        return None
    arr = arr.reshape(-1)
    if arr.size < 2:
        return None
    pixel = arr[:2]
    if not np.all(np.isfinite(pixel)):
        return None
    return pixel


def normalize_position_xyz(position_like: Any) -> Optional[np.ndarray]:
    arr = _to_numpy_array(position_like, dtype=np.float64)
    if arr is None:
        return None
    arr = arr.reshape(-1)
    if arr.size < 3:
        return None
    pos = arr[:3]
    if not np.all(np.isfinite(pos)):
        return None
    return pos


def extract_actor_position_xyz(actor: Any) -> Optional[np.ndarray]:
    pose = getattr(actor, "pose", None)
    if pose is None and hasattr(actor, "get_pose"):
        try:
            pose = actor.get_pose()
        except Exception:
            return None
    if pose is None:
        return None
    pos = getattr(pose, "p", None)
    if pos is None:
        return None
    return normalize_position_xyz(pos)


def _normalize_intrinsic_cv(intrinsic_cv: Any) -> Optional[np.ndarray]:
    intrinsic = _to_numpy_array(intrinsic_cv, dtype=np.float64)
    if intrinsic is None:
        return None
    intrinsic = intrinsic.reshape(-1)
    if intrinsic.size < 9:
        return None
    intrinsic = intrinsic[:9].reshape(3, 3)
    if not np.all(np.isfinite(intrinsic)):
        return None
    return intrinsic


def _normalize_extrinsic_cv(extrinsic_cv: Any) -> Optional[np.ndarray]:
    extrinsic = _to_numpy_array(extrinsic_cv, dtype=np.float64)
    if extrinsic is None:
        return None
    extrinsic = extrinsic.reshape(-1)
    if extrinsic.size < 12:
        return None
    extrinsic = extrinsic[:12].reshape(3, 4)
    if not np.all(np.isfinite(extrinsic)):
        return None
    return extrinsic


def _normalize_image_shape(image_shape: Any) -> Optional[tuple[int, int]]:
    if image_shape is None:
        return None
    try:
        shape_arr = np.asarray(image_shape, dtype=np.int64).reshape(-1)
    except (TypeError, ValueError):
        return None
    if shape_arr.size < 2:
        return None
    h = int(shape_arr[0])
    w = int(shape_arr[1])
    if h <= 0 or w <= 0:
        return None
    return h, w


def project_world_to_pixel(
    world_xyz: Any,
    intrinsic_cv: Any,
    extrinsic_cv: Any,
    image_shape: Any,
) -> Optional[List[int]]:
    world = normalize_position_xyz(world_xyz)
    intrinsic = _normalize_intrinsic_cv(intrinsic_cv)
    extrinsic = _normalize_extrinsic_cv(extrinsic_cv)
    hw = _normalize_image_shape(image_shape)
    if world is None or intrinsic is None or extrinsic is None or hw is None:
        return None

    def _project(extrinsic_mat: np.ndarray) -> Optional[List[int]]:
        world_h = np.concatenate([world, [1.0]], axis=0)
        camera_xyz = extrinsic_mat @ world_h
        z = float(camera_xyz[2])
        if not np.isfinite(z) or z <= 1e-8:
            return None

        pixel_h = intrinsic @ camera_xyz
        x = float(pixel_h[0] / z)
        y = float(pixel_h[1] / z)
        if not np.isfinite(x) or not np.isfinite(y):
            return None

        px = int(np.rint(x))
        py = int(np.rint(y))
        h, w = hw
        if px < 0 or px >= w or py < 0 or py >= h:
            return None
        return [px, py]

    # Most pipelines use extrinsic_cv as world->camera.
    projected = _project(extrinsic)
    if projected is not None:
        return projected

    # Fallback: treat extrinsic_cv as camera->world and invert to world->camera.
    extrinsic_4x4 = np.eye(4, dtype=np.float64)
    extrinsic_4x4[:3, :4] = extrinsic
    try:
        world_to_camera = np.linalg.inv(extrinsic_4x4)[:3, :4]
    except np.linalg.LinAlgError:
        return None
    return _project(world_to_camera)


# ---------------------------------------------------------------------------
# 以下为 2D flow ground truth 链路新增的投影工具。
#
# 上面的 project_world_to_pixel 会 rint 取整并在越界时返回 None，这两个行为都会
# 破坏投影的可逆性，没法用来做「世界坐标 ↔ 像素坐标」的严格双射。因此这里追加三个
# 新函数，**不修改上面任何既有函数**（既有 choice_action 口径必须逐位保持不变）：
#
#   - project_world_to_pixel_subpixel : 子像素、不裁剪的正向投影，额外返回相机系深度
#   - unproject_pixel_to_world        : 由 (u, v, z_cam) 反解世界坐标
#   - projection_jacobian             : 正向投影对世界坐标的 2x3 雅可比
#
# 仓库硬性规定「世界→像素只准有一处实现」，因此三者与既有函数同处本模块，禁止在别处
# 另写 K / extrinsic 的矩阵运算。新旧两条路径的数值一致性由
# tests/lightweight/test_flow_projection_roundtrip.py 逐位断言保证。
# ---------------------------------------------------------------------------


def _resolve_world_to_camera(extrinsic_cv: Any) -> Optional[np.ndarray]:
    """把 extrinsic_cv 解析成 (3, 4) 的 world->camera 矩阵，**只按主解释，不做兜底**。

    ⚠ 这里刻意不复制上面 project_world_to_pixel 的兜底行为（主解释深度非正时改把 extrinsic_cv
    当 camera->world 求逆再试一次）。那个兜底对「求一个像素点」是无害的防御，但对本模块要保证的
    双射是致命的：投影时若走了兜底矩阵，反投影却无从知道该用哪一个（反解过程拿不到世界点），
    结果就是「用矩阵 A 投影、用矩阵 B 反投影」，闭环还原会错到米级。

    实测踩过这个坑：MoveCube 里 ManiSkill 把尚未登场的 goal_site 藏到 (10, -10, 1)，主解释深度是
    -4.87（相机后方），兜底矩阵下却算出 +3.98 的「深度」，于是落盘了一个看似合法、实则无意义的
    投影点，闭环还原误差 8.63 米。

    正确语义是：主解释下深度非正 ⇒ 物体确实在相机后方 ⇒ 不可投影 ⇒ 返回 None，由调用方写 NaN 哨兵。
    本仓库 base_camera 的 extrinsic_cv 本来就是 world->camera（ManiSkill / OpenCV 约定），
    主解释永远是对的那一个。
    """
    return _normalize_extrinsic_cv(extrinsic_cv)


def project_world_to_pixel_subpixel(
    world_xyz: Any,
    intrinsic_cv: Any,
    extrinsic_cv: Any,
) -> Optional[tuple[float, float, float]]:
    """世界坐标投影到像素平面，返回 (u, v, z_cam)，float64，不取整也不裁剪。

    u 是列坐标、v 是行坐标（OpenCV 约定）；z_cam 是相机系深度（米）。只有 (u, v, z_cam)
    三者齐全才构成对世界坐标的双射，所以深度必须一并返回、一并落盘。

    仅在深度非正（物体在相机后方）或出现非有限值时返回 None；点落在图像外仍会正常返回，
    由调用方按需要判断是否在画幅内。

    运算顺序与 project_world_to_pixel 内部的 _project 完全一致（先 intrinsic @ camera_xyz
    再除以 z），保证两条路径在同一输入上的浮点结果逐位相同。

    ⚠ 与旧函数的唯一行为差异：旧函数在主解释深度非正时会改用「extrinsic 求逆」再试一次，本函数
    **不做这个兜底**，直接返回 None。原因见 _resolve_world_to_camera 的说明——兜底会让投影与反
    投影用上不同的矩阵，双射当场失效。
    """
    world = normalize_position_xyz(world_xyz)
    intrinsic = _normalize_intrinsic_cv(intrinsic_cv)
    if world is None or intrinsic is None:
        return None
    extrinsic = _resolve_world_to_camera(extrinsic_cv)
    if extrinsic is None:
        return None

    world_h = np.concatenate([world, [1.0]], axis=0)
    camera_xyz = extrinsic @ world_h
    z = float(camera_xyz[2])
    if not np.isfinite(z) or z <= 1e-8:
        return None

    pixel_h = intrinsic @ camera_xyz
    u = float(pixel_h[0] / z)
    v = float(pixel_h[1] / z)
    if not np.isfinite(u) or not np.isfinite(v):
        return None
    return u, v, z


def unproject_pixel_to_world(
    u: float,
    v: float,
    z_cam: float,
    intrinsic_cv: Any,
    extrinsic_cv: Any,
) -> Optional[np.ndarray]:
    """由 (u, v, z_cam) 反解世界坐标，返回 (3,) 的 float64 数组。

    这是 project_world_to_pixel_subpixel 的逆映射：在 z_cam > 0 的半空间上，内参可逆
    (fx, fy != 0) 且外参旋转部分可逆，正向映射是双射，本函数即其逆的显式构造。

    先解 X_c = z * K^-1 @ [u, v, 1]，再解 R @ X_w = X_c - t。旋转部分用 np.linalg.solve 而不是
    直接转置：h5 里落盘的 extrinsic 是 float32，其旋转部分的正交性误差实测约 1.4e-7，用转置代替
    求逆会让重投影误差劣化到 4e-4 像素，而解线性方程组只有 3 ulp。
    """
    intrinsic = _normalize_intrinsic_cv(intrinsic_cv)
    extrinsic = _resolve_world_to_camera(extrinsic_cv)
    if intrinsic is None or extrinsic is None:
        return None
    try:
        pixel_values = np.asarray([float(u), float(v), float(z_cam)], dtype=np.float64)
    except (TypeError, ValueError):
        return None
    if not np.all(np.isfinite(pixel_values)):
        return None
    z = float(pixel_values[2])
    if z <= 1e-8:
        return None

    pixel_h = np.asarray([pixel_values[0], pixel_values[1], 1.0], dtype=np.float64)
    try:
        camera_xyz = z * np.linalg.solve(intrinsic, pixel_h)
    except np.linalg.LinAlgError:
        return None

    rotation = extrinsic[:, :3]
    translation = extrinsic[:, 3]
    try:
        world = np.linalg.solve(rotation, camera_xyz - translation)
    except np.linalg.LinAlgError:
        return None
    if not np.all(np.isfinite(world)):
        return None
    return world.astype(np.float64)


def projection_jacobian(
    world_xyz: Any,
    intrinsic_cv: Any,
    extrinsic_cv: Any,
) -> Optional[np.ndarray]:
    """正向投影对世界坐标的雅可比 d(u, v) / d(X, Y, Z)，返回 (2, 3) 的 float64 数组。

    用途是验证「落盘的 2D 位移确实是 3D 位移的正确微分像」：当 3D 位移足够小时应有
    Δ_2d ≈ J @ Δ_3d，且残差随步长二阶收敛。

    推导按通用内参写（不假设 K 是上三角）：记 p = K @ X_c，则 u = p0 / p2、v = p1 / p2，
    对相机系求导得
        du/dX_c = (K[0] * p2 - p0 * K[2]) / p2^2
        dv/dX_c = (K[1] * p2 - p1 * K[2]) / p2^2
    再右乘 dX_c/dX_w = R 即得对世界坐标的雅可比。
    """
    world = normalize_position_xyz(world_xyz)
    intrinsic = _normalize_intrinsic_cv(intrinsic_cv)
    if world is None or intrinsic is None:
        return None
    extrinsic = _resolve_world_to_camera(extrinsic_cv)
    if extrinsic is None:
        return None

    world_h = np.concatenate([world, [1.0]], axis=0)
    camera_xyz = extrinsic @ world_h
    pixel_h = intrinsic @ camera_xyz
    denominator = float(pixel_h[2])
    # 与 project_world_to_pixel_subpixel 同口径：深度非正时物体在相机后方，投影无物理意义，
    # 雅可比也不该给。数学上 z < 0 时导数仍有定义，但那描述的是一个不存在的成像点。
    if not np.isfinite(denominator) or denominator <= 1e-8:
        return None

    d_uv_d_camera = np.empty((2, 3), dtype=np.float64)
    for row in range(2):
        d_uv_d_camera[row] = (
            intrinsic[row] * denominator - float(pixel_h[row]) * intrinsic[2]
        ) / (denominator * denominator)

    jacobian = d_uv_d_camera @ extrinsic[:, :3]
    if not np.all(np.isfinite(jacobian)):
        return None
    return jacobian


def select_target_with_position(
    available: Any,
    position_like: Any,
) -> Optional[Dict[str, Any]]:
    target_pos = normalize_position_xyz(position_like)
    if target_pos is None:
        return None

    unique_candidates = _unique_candidates(available)
    if not unique_candidates:
        return None

    best_actor: Optional[Any] = None
    best_pos: Optional[np.ndarray] = None
    best_dist: Optional[float] = None

    for actor in unique_candidates:
        actor_pos = extract_actor_position_xyz(actor)
        if actor_pos is None:
            continue
        dist = float(np.linalg.norm(actor_pos - target_pos))
        if best_dist is None or dist < best_dist:
            best_actor = actor
            best_pos = actor_pos
            best_dist = dist

    if best_actor is None or best_pos is None or best_dist is None:
        return None

    return {
        "obj": best_actor,
        "name": getattr(best_actor, "name", "unknown"),
        "position": best_pos.astype(np.float64).tolist(),
        "match_distance": best_dist,
        "selection_mode": "nearest_position",
    }


def select_target_with_pixel(
    available: Any,
    pixel_like: Any,
    intrinsic_cv: Any,
    extrinsic_cv: Any,
    image_shape: Any,
) -> Optional[Dict[str, Any]]:
    target_pixel = normalize_pixel_xy(pixel_like)
    if target_pixel is None:
        return None

    unique_candidates = _unique_candidates(available)
    if not unique_candidates:
        return None

    best_actor: Optional[Any] = None
    best_pos: Optional[np.ndarray] = None
    best_pixel: Optional[List[int]] = None
    best_dist: Optional[float] = None

    for actor in unique_candidates:
        actor_pos = extract_actor_position_xyz(actor)
        if actor_pos is None:
            continue
        projected = project_world_to_pixel(
            actor_pos,
            intrinsic_cv=intrinsic_cv,
            extrinsic_cv=extrinsic_cv,
            image_shape=image_shape,
        )
        if projected is None:
            continue
        projected_np = np.asarray(projected, dtype=np.float64)
        dist = float(np.linalg.norm(projected_np - target_pixel))
        if best_dist is None or dist < best_dist:
            best_actor = actor
            best_pos = actor_pos
            best_pixel = projected
            best_dist = dist

    if best_actor is None or best_pos is None or best_dist is None or best_pixel is None:
        return None

    return {
        "obj": best_actor,
        "name": getattr(best_actor, "name", "unknown"),
        "position": best_pos.astype(np.float64).tolist(),
        "projected_pixel": [int(best_pixel[0]), int(best_pixel[1])],
        "match_distance": best_dist,
        "selection_mode": "nearest_pixel_projection",
    }
