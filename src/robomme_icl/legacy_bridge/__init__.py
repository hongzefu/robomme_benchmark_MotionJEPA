"""集中、延迟调用原版的固定参数工具，不修改原版模块。"""


def initial_qpos(robot_kind):
    """复用原版明确的初始姿态；调用方负责控制器复位。"""
    from robomme.robomme_env.utils.reset_panda import get_reset_panda_param

    return get_reset_panda_param("qpos", gripper="stick" if robot_kind == "panda_stick" else None).copy()


def build_fixed_cube(env, actor):
    """参与物理的方块始终建立碰撞形状，位姿来自场景清单。"""
    import math
    import sapien
    from robomme.robomme_env.utils.object_generation import spawn_fixed_cube

    q = actor["quaternion"]
    yaw = math.atan2(2 * (q[0] * q[3] + q[1] * q[2]), 1 - 2 * (q[2] ** 2 + q[3] ** 2))
    obj = spawn_fixed_cube(env, position=actor["position"], half_size=actor["half_size"][0],
                           color=actor["color"], name_prefix=actor["id"], yaw=yaw, dynamic=True)
    obj.set_pose(sapien.Pose(actor["position"], actor["quaternion"]))
    return obj


def build_fixed_button(env, actor):
    """原版构建函数会写入字段，立即把关节和组件引用收集到新版对象中。"""
    from robomme.robomme_env.utils.object_generation import build_button

    build_button(env, center_xy=actor["position"][:2], scale=1.5, randomize=False, name=actor["id"])
    return env.button
