"""V4 xhard：VideoPlaceButton / VideoPlaceOrder 共用的「演示方块放回原位」工具（计划 2.14 / 2.15）。

只在 xhard 分支被调用，原三档一次都不会走到这里。

* :func:`validate_demo_plan`：核对 ``decision`` 里 ``demo_object_count`` / ``demo_return_policy`` 的取值组合。
  两个键由环境文件自己读出（审计 ``config-map`` 按环境源码找消费点），这里只做合法性判定。
* :func:`build_home_sites`：在每个演示方块的**初始位姿**上直接调 target builder 建一个落点 actor。

为什么不用 ``spawn_random_target(randomize=False)``：该形参在采样循环里根本没被读，照样
``torch.rand``（会平移随机流、落点也不在指定位置）；而 BinFill 原三档正在传 ``randomize=False``，
修这个工具函数会平移 BinFill 原三档 ⇒ 按红线 N12 不就地修，另写本 xhard 专用路径。
"""

from __future__ import annotations

import torch
from mani_skill.utils.structs.pose import Pose

from .object_generation import build_gray_white_target
from .SceneGenerationError import SceneGenerationError

# 原三档的取值：只演示 1 个方块，演示完放到随机 goal_site（z 压到桌面以下隐藏）
NATIVE_DEMO_PLAN = (1, "native_random_goal_site")
# xhard 唯一支持的返回策略：每个演示方块放回自己的初始位置
RETURN_TO_ORIGIN = "return_to_origin"

# 落点 actor 的尺寸只影响（被隐藏的）可视外观，不参与任何碰撞或判定：
# is_obj_dropped_onto 只看水平距离 ≤ 0.05，solve_putonto_whenhold 只取 pose.p。
HOME_SITE_THICKNESS = 0.005


def validate_demo_plan(count, policy, difficulty: str, n_cubes: int) -> tuple[int, str]:
    """核对演示方块数与返回策略；非法组合直接抛 ``SceneGenerationError``（不静默截断）。"""
    count = int(count)
    policy = str(policy)
    if difficulty != "xhard":
        if (count, policy) != NATIVE_DEMO_PLAN:
            raise SceneGenerationError(
                f"原三档只支持 demo_object_count=1 + native_random_goal_site，收到 {(count, policy)}"
            )
        return count, policy
    if policy != RETURN_TO_ORIGIN:
        raise SceneGenerationError(f"xhard 只支持 demo_return_policy={RETURN_TO_ORIGIN!r}，收到 {policy!r}")
    if not 1 <= count <= n_cubes:
        raise SceneGenerationError(
            f"xhard demo_object_count={count} 超出场上方块数 {n_cubes}（请求数 ≠ 可演示数）"
        )
    return count, policy


def build_home_sites(env, cubes, generator, name_prefix: str = "home_site"):
    """在每个方块的初始位姿上建一个隐藏的落点 actor，返回 ``(homes, checks)``。

    必须放在本场景**所有**其他 spawn 之后调用。两条验收（计划 2.14）当场自检，不过即抛错：

    1. 落点位姿逐位等于方块初始位姿（``raw_pose`` 7 个 float32 全等）；
    2. 建 actor 前后 ``generator.get_state()`` 逐字节相等（builder 不抽随机数）。

    落点登记进 ``env._hidden_objects``：传感器画面（录像器用的 base/hand camera）里看不到，
    与原三档把 goal_site 压到桌面以下同理——「演示完放哪」只体现在动作上，不在画面上多出标记。
    """
    state_before = generator.get_state().clone()
    homes = []
    pose_equal = []
    for cube in cubes:
        raw = cube.initial_pose.raw_pose.detach().clone()
        home = build_gray_white_target(
            scene=env.scene,
            radius=float(env.cube_half_size),
            thickness=HOME_SITE_THICKNESS,
            name=f"{name_prefix}_{cube.name}",
            body_type="kinematic",
            add_collision=False,
            initial_pose=Pose.create(raw),
        )
        home._home_of = cube
        same = torch.equal(home.initial_pose.raw_pose.detach().cpu(), raw.cpu())
        if same and not env.scene.gpu_sim_enabled:
            # CPU 仿真下还能直接读实体位姿；GPU 仿真在 _load_scene 阶段尚未初始化，只比 initial_pose
            same = torch.equal(home.pose.raw_pose.detach().cpu(), raw.cpu())
        if not same:
            raise SceneGenerationError(f"落点 {home.name} 的位姿与方块 {cube.name} 的初始位姿不逐位相等")
        pose_equal.append(same)
        env._hidden_objects.append(home)
        homes.append(home)
    rng_equal = torch.equal(state_before, generator.get_state())
    if not rng_equal:
        raise SceneGenerationError("建落点 actor 前后 generator 状态不一致（不许抽随机数）")
    checks = {"pose_equal": pose_equal, "rng_state_equal": rng_equal}
    return homes, checks


def home_pose_record(cubes, homes) -> dict:
    """``actions.return_pose_by_object_id`` 的内容：方块名 → 落点 raw_pose（p 三位 + q 四位）。"""
    return {
        cube.name: [float(v) for v in home.initial_pose.raw_pose[0].tolist()]
        for cube, home in zip(cubes, homes)
    }
