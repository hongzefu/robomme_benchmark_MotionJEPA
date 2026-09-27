"""进程内猴补丁（不落盘、不改任何被跟踪文件）：把 V5 最终规则注入 MoveCube._load_scene（仅 xhard 分支生效）。

规则（用户已定，计划 2.9）：
- corner_bias 删除（这里把 config_xhard["corner_bias"] 置 0，corner_push(u, 0) 原样返回 u，等价删除）；
- 桌面中心圆 (0,0)、R（默认 0.05），按物体中心判，每个取值点中心拒绝达 128 次抛 SceneGenerationError：
  杆：轴线段 root+t·u，t∈PEG_SEG（默认计划口径 [-0.075, 0.025]）离原点最近 < R → 原地重抽 (x_jitter, y_jitter, yaw)；
  goal：圆盘中心 < R → spawn_random_target 循环内 continue；
  方块候选：|c_cand| < R → 与 |c−g|>0.1 同一次试验内拒绝（共用 max_cube_spawn_trials=128）；
  方块最终：|c_final| < R → spawn_random_cube 循环内 continue；
- 执行段 cube_2 用 include_existing=False。
做法：取源码做定点文本替换后 exec 回模块命名空间；每处锚点要求出现次数精确匹配，否则报错。
每局的中心拒绝计数写到 env._v5_stats（dict）。
"""
from __future__ import annotations

import inspect
import math
import sys
import textwrap

import numpy as np


def _sub(src, old, new, count=1):
    n = src.count(old)
    if n != count:
        raise RuntimeError(f"补丁锚点出现 {n} 次（期望 {count}）：{old[:90]!r}")
    return src.replace(old, new)


def apply_patch(R=0.05, peg_seg=(-0.075, 0.025), max_trials=128):
    import importlib
    import robomme.robomme_env  # noqa: F401 注册环境
    mc_mod = importlib.import_module("robomme.robomme_env.MoveCube")
    og = sys.modules["robomme.robomme_env.utils.object_generation"]
    SGE = mc_mod.SceneGenerationError

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
    src = _sub(src, """        else:
            yaw = 0.0

        # New target's circular collision detection""", """        else:
            yaw = 0.0

        if reject_xy is not None and reject_xy(x, y):
            continue

        # New target's circular collision detection""")
    exec(compile(src, "<v5_spawn_random_target>", "exec"), og.__dict__)

    def seg_dist(rx, ry, yaw):
        u = np.array([math.cos(yaw), math.sin(yaw)]); r = np.array([rx, ry], dtype=np.float64)
        t = float(np.clip(-(r @ u), peg_seg[0], peg_seg[1]))
        return float(np.linalg.norm(r + t * u))

    def make_rej(env, name):
        """返回 reject(x, y) 或 reject(dist)：True=落进圆需重抽；计数达上限抛错。"""
        env._v5_stats.setdefault(name, 0)

        def reject(*a):
            d = a[0] if len(a) == 1 else math.hypot(a[0], a[1])
            if d < R:
                env._v5_stats[name] += 1
                if env._v5_stats[name] >= max_trials:
                    raise SGE(f"MoveCube xhard V5：{name} 中心禁区拒绝 {max_trials} 次耗尽")
                return True
            return False
        return reject

    mc_mod._v5_spawn_random_cube = og._v5_spawn_random_cube
    mc_mod._v5_spawn_random_target = og._v5_spawn_random_target
    mc_mod._v5_make_rej = make_rej
    mc_mod._v5_seg_dist = seg_dist

    # 2) _load_scene 定点替换
    src = inspect.getsource(mc_mod.MoveCube._load_scene)
    src = _sub(src, "        xhard = self.difficulty == \"xhard\"\n",
               "        xhard = self.difficulty == \"xhard\"\n        self._v5_stats = {}\n")
    yaw_line = '        initial_yaw = torch.rand(1, generator=self._hb_generator).item() * (yaw_policy["span_rad"]) - (yaw_policy["offset_rad"])\n'
    src = _sub(src, yaw_line, "        pass  # V5 探针：yaw 已在杆循环里按原顺序抽过\n", count=2)
    for seg, bias, pol in (("demo", "demo_bias", "demo_peg"), ("exec", "exec_bias", "exec_peg")):
        old = (f'        x_jitter = (corner_push(torch.rand(1, generator=self._hb_generator).item(), {bias}) - 0.5) * {pol}["jitter_span"]\n'
               f'        y_jitter = (corner_push(torch.rand(1, generator=self._hb_generator).item(), {bias}) - 0.5) * {pol}["jitter_span"]\n')
        new = (f'        _peg_rej = _v5_make_rej(self, "peg_{seg}") if xhard else None\n'
               f'        while True:\n'
               f'            x_jitter = (corner_push(torch.rand(1, generator=self._hb_generator).item(), {bias}) - 0.5) * {pol}["jitter_span"]\n'
               f'            y_jitter = (corner_push(torch.rand(1, generator=self._hb_generator).item(), {bias}) - 0.5) * {pol}["jitter_span"]\n'
               f'            initial_yaw = torch.rand(1, generator=self._hb_generator).item() * (yaw_policy["span_rad"]) - (yaw_policy["offset_rad"])\n'
               f'            if _peg_rej is None or not _peg_rej(_v5_seg_dist(float(np.float32(x_jitter)), float(np.float32(base_y) + np.float32(y_jitter)), initial_yaw)):\n'
               f'                break\n')
        src = _sub(src, old, new)
    # goal
    src = _sub(src, "        self.goal_site = spawn_random_target(",
               "        self.goal_site = (_v5_spawn_random_target if xhard else spawn_random_target)(")
    src = _sub(src, "        self.goal_site_2 = spawn_random_target(",
               "        self.goal_site_2 = (_v5_spawn_random_target if xhard else spawn_random_target)(")
    src = _sub(src, """                        spec_path="layout.demo.goal_xy",
                        generator=self._hb_generator
                        )""", """                        spec_path="layout.demo.goal_xy",
                        generator=self._hb_generator,
                        **({"reject_xy": _v5_make_rej(self, "goal_demo")} if xhard else {})
                        )""")
    src = _sub(src, """                spec_path="layout.execution.goal_xy",
                generator=self._hb_generator
                )""", """                spec_path="layout.execution.goal_xy",
                generator=self._hb_generator,
                **({"reject_xy": _v5_make_rej(self, "goal_exec")} if xhard else {})
                )""")
    # 方块候选：两个 _sample_cube_center 各自一个计数器（按调用顺序 demo→exec）
    src = _sub(src, "            for _ in range(max_cube_spawn_trials):\n",
               "            _cand_rej = _v5_make_rej(self, \"cand_exec\" if \"cand_demo\" in self._v5_stats else \"cand_demo\") if xhard else None\n"
               "            for _ in range(max_cube_spawn_trials):\n", count=2)
    src = _sub(src, """                if np.linalg.norm(candidate_xy - goal_xy) > required_distance:
                    return candidate_xy""", """                if np.linalg.norm(candidate_xy - goal_xy) > required_distance and not (
                        _cand_rej is not None and _cand_rej(sampled_x, sampled_y)):
                    return candidate_xy""", count=2)
    # 方块最终
    src = _sub(src, "            self.cube = spawn_random_cube(",
               "            self.cube = (_v5_spawn_random_cube if xhard else spawn_random_cube)(")
    src = _sub(src, "            self.cube_2 = spawn_random_cube(",
               "            self.cube_2 = (_v5_spawn_random_cube if xhard else spawn_random_cube)(")
    src = _sub(src, """        demo_cube_extra = {"corner_bias": demo_bias} if xhard else {}""",
               """        demo_cube_extra = {"corner_bias": demo_bias, "reject_xy": _v5_make_rej(self, "cube_demo")} if xhard else {}""")
    src = _sub(src, """        exec_cube_extra = {"corner_bias": exec_bias} if xhard else {}""",
               """        exec_cube_extra = {"corner_bias": exec_bias, "include_existing": False,
                           "reject_xy": _v5_make_rej(self, "cube_exec")} if xhard else {}""")
    ns = mc_mod.__dict__
    exec(compile(textwrap.dedent(src), "<v5_load_scene>", "exec"), ns)
    mc_mod.MoveCube._load_scene = ns["_load_scene"]
    # 3) corner_bias 置 0（configs["xhard"] 与 config_xhard 同一个 dict；_native_decision 每次从这里读）
    mc_mod.MoveCube.config_xhard["corner_bias"] = 0.0
    return mc_mod
