"""对照：同一批 seed 在 hard 与 xhard 下 reset 成败是否一致（布局段两档逐字相同）。用法: g8_hard_cmp.py <Task> <n>"""
import sys

sys.path.insert(0, "src")
import gymnasium as gym  # noqa: E402

import robomme.robomme_env  # noqa: E402,F401

task, n = sys.argv[1], int(sys.argv[2])
rows = []
for i in range(n):
    seed = 900000 + i * 101
    res = {}
    for diff in ("hard", "xhard"):
        env = None
        try:
            env = gym.make(task, obs_mode="rgb+depth+segmentation", control_mode="pd_joint_pos",
                           render_mode="rgb_array", reward_mode="dense", seed=seed, difficulty=diff)
            env.reset()
            b = env.unwrapped
            res[diff] = "ok"
            layout = [c.initial_pose.raw_pose.tolist() for c in b.all_cubes] + \
                     [t.initial_pose.raw_pose.tolist() for t in b.targets]
            res[diff + "_layout"] = layout
        except Exception as exc:  # noqa: BLE001
            root = exc
            while root.__context__ is not None:
                root = root.__context__
            res[diff] = f"fail:{type(exc).__name__}/{type(root).__name__}:{str(root)[:40]}"
        finally:
            if env is not None:
                env.close()
    same_layout = res.get("hard_layout") == res.get("xhard_layout")
    print(f"seed={seed} hard={res['hard']} xhard={res['xhard']} same_layout={same_layout}", flush=True)
    rows.append((res["hard"] == "ok", res["xhard"] == "ok", same_layout))
agree = sum(1 for h, x, _ in rows if h == x)
print(f"HARD_CMP task={task} n={n} hard_ok={sum(h for h, _, _ in rows)} xhard_ok={sum(x for _, x, _ in rows)} "
      f"agree={agree} layout_same_when_both_ok={sum(1 for h, x, s in rows if h and x and s)}/{sum(1 for h, x, _ in rows if h and x)}")
