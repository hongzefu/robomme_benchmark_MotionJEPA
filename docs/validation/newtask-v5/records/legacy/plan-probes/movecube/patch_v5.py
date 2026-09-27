"""进程内猴补丁（不落盘）：把 V5 候选设计「xhard：corner_bias=0 + 各对象中心拒绝 + 执行段方块不再避让演示段方块」
注入 MoveCube._load_scene，供 reset 核验与本机演示探针使用。原三档分支完全不经过新增代码。

做法：取 MoveCube._load_scene / spawn_random_cube / spawn_random_target 源码做定点文本替换后 exec 回模块命名空间。
"""
from __future__ import annotations

import inspect
import math
import sys
import textwrap

sys.path.insert(0, "/data/hongzefu/robomme_benchmark_MotionJEPANewTask/src")

SQ = math.sqrt(0.3)
V5_DEFAULT = {
    "peg_w": SQ * 0.05,      # 杆根点相对自身抖动盒中心 (0, base_y) 的禁区半边
    "goal_w_demo": SQ * 0.11,
    "goal_w_exec": SQ * 0.06,
    "cube_w": SQ * 0.1,      # 方块候选中心与最终 xy 共用的 (0,0) 禁区半边
}


def _sub(src, old, new, count=1):
    n = src.count(old)
    if n != count:
        raise RuntimeError(f"补丁锚点出现 {n} 次（期望 {count}）：{old[:80]!r}")
    return src.replace(old, new)


def apply_patch(v5=None):
    v5 = dict(V5_DEFAULT if v5 is None else v5)
    import importlib
    import robomme.robomme_env  # noqa: F401 注册环境
    mc_mod = importlib.import_module("robomme.robomme_env.MoveCube")
    mc_mod = sys.modules["robomme.robomme_env.MoveCube"]
    og = sys.modules["robomme.robomme_env.utils.object_generation"]

    # 1) 带 reject_xy 钩子的 spawn_random_cube / spawn_random_target 副本
    src = textwrap.dedent(inspect.getsource(og.spawn_random_cube))
    src = _sub(src, "def spawn_random_cube(", "def _v5_spawn_random_cube(")
    src = _sub(src, "        corner_bias=0.0,", "        corner_bias=0.0,\n        reject_xy=None,")
    src = _sub(src, """        else:
            yaw = 0.0

        # New cube's 2D OBB""", """        else:
            yaw = 0.0

        if reject_xy is not None and reject_xy(x, y):
            continue

        # New cube's 2D OBB""")
    exec(compile(src, "<v5_spawn_random_cube>", "exec"), og.__dict__)
    src = textwrap.dedent(inspect.getsource(og.spawn_random_target))
    src = _sub(src, "def spawn_random_target(", "def _v5_spawn_random_target(")
    src = _sub(src, "        spec_path=None,  # 该取值点在 episode_spec 里的路径\n    ):",
               "        spec_path=None,  # 该取值点在 episode_spec 里的路径\n        reject_xy=None,\n    ):")
    src = _sub(src, """        if random_yaw:
            yaw = float(torch.rand(1, generator=generator).item() * 2 * np.pi - np.pi)
        else:
            yaw = 0.0
""", """        if random_yaw:
            yaw = float(torch.rand(1, generator=generator).item() * 2 * np.pi - np.pi)
        else:
            yaw = 0.0

        if reject_xy is not None and reject_xy(x, y):
            continue
""")
    exec(compile(src, "<v5_spawn_random_target>", "exec"), og.__dict__)
    mc_mod._v5_spawn_random_cube = og._v5_spawn_random_cube
    mc_mod._v5_spawn_random_target = og._v5_spawn_random_target
    mc_mod._V5 = v5

    # 2) _load_scene：定点替换
    src = inspect.getsource(mc_mod.MoveCube._load_scene)  # 保留类内缩进做替换，最后再 dedent
    peg_block = """
        if xhard:
            _k = 0
            while max(abs(x_jitter), abs(y_jitter)) < _V5["peg_w"]:
                _k += 1
                if _k >= 128:
                    raise SceneGenerationError("MoveCube xhard V5：杆根点中心拒绝 128 次耗尽")
                x_jitter = (corner_push(torch.rand(1, generator=self._hb_generator).item(), {bias}) - 0.5) * {pol}["jitter_span"]
                y_jitter = (corner_push(torch.rand(1, generator=self._hb_generator).item(), {bias}) - 0.5) * {pol}["jitter_span"]
"""
    old_demo = """        y_jitter = (corner_push(torch.rand(1, generator=self._hb_generator).item(), demo_bias) - 0.5) * demo_peg["jitter_span"]
"""
    src = _sub(src, old_demo, old_demo + peg_block.format(bias="demo_bias", pol="demo_peg"))
    old_exec = """        y_jitter = (corner_push(torch.rand(1, generator=self._hb_generator).item(), exec_bias) - 0.5) * exec_peg["jitter_span"]
"""
    src = _sub(src, old_exec, old_exec + peg_block.format(bias="exec_bias", pol="exec_peg"))
    # goal：xhard 走带钩子的副本
    src = _sub(src, "        self.goal_site = spawn_random_target(",
               "        self.goal_site = (_v5_spawn_random_target if xhard else spawn_random_target)(")
    src = _sub(src, "        self.goal_site_2 = spawn_random_target(",
               "        self.goal_site_2 = (_v5_spawn_random_target if xhard else spawn_random_target)(")
    src = _sub(src, """                        spec_path="layout.demo.goal_xy",
                        generator=self._hb_generator
                        )""", """                        spec_path="layout.demo.goal_xy",
                        generator=self._hb_generator,
                        **({"reject_xy": lambda x, y: max(abs(x), abs(y)) < _V5["goal_w_demo"]} if xhard else {})
                        )""")
    src = _sub(src, """                spec_path="layout.execution.goal_xy",
                generator=self._hb_generator
                )""", """                spec_path="layout.execution.goal_xy",
                generator=self._hb_generator,
                **({"reject_xy": lambda x, y: max(abs(x), abs(y)) < _V5["goal_w_exec"]} if xhard else {})
                )""")
    # 方块候选中心：xhard 时再加中心判据（同一次试验的两个抽样，不多抽）
    src = _sub(src, """                if np.linalg.norm(candidate_xy - goal_xy) > required_distance:
                    return candidate_xy""", """                if np.linalg.norm(candidate_xy - goal_xy) > required_distance and not (
                        xhard and max(abs(sampled_x), abs(sampled_y)) < _V5["cube_w"]):
                    return candidate_xy""", count=2)
    # 方块最终 xy：xhard 走带钩子的副本；执行段不再避让演示段方块
    src = _sub(src, "            self.cube = spawn_random_cube(",
               "            self.cube = (_v5_spawn_random_cube if xhard else spawn_random_cube)(")
    src = _sub(src, "            self.cube_2 = spawn_random_cube(",
               "            self.cube_2 = (_v5_spawn_random_cube if xhard else spawn_random_cube)(")
    src = _sub(src, """        demo_cube_extra = {"corner_bias": demo_bias} if xhard else {}""",
               """        demo_cube_extra = {"corner_bias": demo_bias,
                           "reject_xy": lambda x, y: max(abs(x), abs(y)) < _V5["cube_w"]} if xhard else {}""")
    src = _sub(src, """        exec_cube_extra = {"corner_bias": exec_bias} if xhard else {}""",
               """        exec_cube_extra = {"corner_bias": exec_bias, "include_existing": False,
                           "reject_xy": lambda x, y: max(abs(x), abs(y)) < _V5["cube_w"]} if xhard else {}""")
    ns = mc_mod.__dict__
    exec(compile(textwrap.dedent(src), "<v5_load_scene>", "exec"), ns)
    mc_mod.MoveCube._load_scene = ns["_load_scene"]
    # 3) xhard 的 corner_bias 置 0（configs["xhard"] 与 config_xhard 是同一个 dict）
    mc_mod.MoveCube.config_xhard["corner_bias"] = 0.0
    return mc_mod
