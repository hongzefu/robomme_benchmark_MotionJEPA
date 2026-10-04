"""PatternLock／RouteStick（握杆机器人）真值表的公共演示段：按任务表演示项把 TCP 依次移到演示路径上的落点，
复位、再回到起点姿态（生产 ``solve_swingonto(record_swing_qpos=True)`` 与 ``solve_strong_reset`` 的效果）。"""
from __future__ import annotations

import torch

from robomme_hard.robomme_env.utils import reset_panda

TOUCH_Z = 0.05  # 低于两任务的落点高度阈值
TRAVEL_Z = 0.3  # 高于全部高度阈值：移动途中不碰任何落点


def stick_reset_qpos():
    return torch.as_tensor(reset_panda.get_reset_panda_param("qpos", gripper="stick"), dtype=torch.float32)


def touch(w, button):
    x, y = w.xyz(button)[:2]
    w.tcp_to((x, y, TOUCH_Z))


def hover(w, xy):
    w.tcp_to((float(xy[0]), float(xy[1]), TRAVEL_Z))


def run_demo(w, on_move=None):
    """走完演示段，停在执行段第一项；``on_move(w, target)`` 可替换演示里每一步的移动方式。"""
    env = w.env
    w.agent.robot.set_qpos(stick_reset_qpos())
    swing_pose = stick_reset_qpos() + 0.25  # 起点姿态（任意一组不同于复位的关节角）
    seen_first = False
    with w.demo_phase():
        for _ in range(500):
            if not env.task_list[w.stage]["demonstration"]:
                return
            # 与 DemonstrationWrapper 相同：每个演示任务执行前后各调一次 evaluate(solve_complete_eval=True)
            env.evaluate(solve_complete_eval=True)
            if not env.task_list[w.stage]["demonstration"]:
                return
            task = env.task_list[w.stage]
            if task["name"] == "NO RECORD" and not seen_first:
                touch(w, env.selected_buttons[0])
                w.agent.robot.set_qpos(swing_pose)
                env.swing_qpos = w.agent.robot.qpos.clone()
                seen_first = True
            elif task["name"] == "NO RECORD" and w.agent.robot.qpos.equal(swing_pose.reshape(1, -1)):
                w.agent.robot.set_qpos(stick_reset_qpos())  # 强复位
                env.after_demo = True
            elif task["name"] == "NO RECORD":
                w.agent.robot.set_qpos(env.swing_qpos)  # 回到起点姿态：TCP 在第一个落点上
                touch(w, env.selected_buttons[0])
            else:
                i = sum(1 for t in env.task_list[: w.stage] if t["name"] != "NO RECORD")
                target = env.selected_buttons[i + 1]
                (on_move or (lambda w, t: touch(w, t)))(w, target)
            assert w.step()["fail"] is False, task["name"]
            env.evaluate(solve_complete_eval=True)
    raise AssertionError("演示段未走完")
