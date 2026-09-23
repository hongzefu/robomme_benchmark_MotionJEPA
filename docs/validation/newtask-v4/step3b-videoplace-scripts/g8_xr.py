"""g8 xhard reset 冒烟：VideoPlaceButton / VideoPlaceOrder 只 reset，核对新值与两条落点验收。

用法: g8_xr.py <Task> <n>
"""
import sys
from collections import Counter

sys.path.insert(0, "src")
import gymnasium as gym  # noqa: E402
import torch  # noqa: E402

import robomme.robomme_env  # noqa: E402,F401
from robomme.robomme_env.utils.vqa_options import get_vqa_options  # noqa: E402

task, n = sys.argv[1], int(sys.argv[2])
ok = 0
fails = Counter()
stats = Counter()
for i in range(n):
    seed = 900000 + i * 101
    env = None
    try:
        env = gym.make(task, obs_mode="rgb+depth+segmentation", control_mode="pd_joint_pos",
                       render_mode="rgb_array", reward_mode="dense", seed=seed, difficulty="xhard")
        env.reset()
        b = env.unwrapped
        problems = []
        if b._spec.spec_kind != "native-newvalue/1":
            problems.append(f"kind={b._spec.spec_kind}")
        if len(b.all_cubes) != 3 or len(b.targets) != 4:
            problems.append(f"cubes={len(b.all_cubes)} targets={len(b.targets)}")
        if len(b.demo_cubes) != 2 or len(set(id(c) for c in b.demo_cubes)) != 2:
            problems.append("demo_cubes 非 2 个互异")
        if len(b.xhard_home_sites) != 2:
            problems.append("home 数 != 2")
        # 验收①：落点位姿逐位等于方块初始位姿（reset 后仍成立，且与方块当前位姿一致）
        for cube, home in zip(b.demo_cubes, b.xhard_home_sites):
            if not torch.equal(home.pose.raw_pose.cpu(), cube.initial_pose.raw_pose.cpu()):
                problems.append(f"home≠cube.initial_pose {cube.name}")
            if not torch.equal(home.pose.raw_pose.cpu(), cube.pose.raw_pose.cpu()):
                stats["home≠cube.pose(reset后)"] += 1
        # 验收②：建 actor 前后 generator 状态逐字节相等（build_home_sites 当场自检的结果）
        if not b._xhard_home_checks["rng_state_equal"] or not all(b._xhard_home_checks["pose_equal"]):
            problems.append(f"checks={b._xhard_home_checks}")
        if any(h not in b._hidden_objects for h in b.xhard_home_sites):
            problems.append("home 未登记为隐藏")
        if b.target_cube not in b.demo_cubes or b.target_target not in b.targets:
            problems.append("答案方块/答案台不在范围内")
        names = [t["name"] for t in b.task_list]
        demo_names = [t["name"] for t in b.task_list if t.get("demonstration")]
        n_home = names.count("put the cube back to its original position")
        if n_home != 2:
            problems.append(f"放回原位步数={n_home}")
        bi = names.index("press the button")
        if names.count("press the button") != 1:
            problems.append("按钮次数≠1")
        if bi == 0 or not names[bi - 1].startswith(("drop", "put the cube back")):
            problems.append(f"按钮前一步不是放置：{names[bi - 1] if bi else None}")
        if task == "VideoPlaceOrder":
            if bi != b.button_task_index:
                problems.append(f"button_task_index={b.button_task_index} 实际 {bi}")
            if names[bi - 1] == "put the cube back to its original position":
                problems.append("按钮落在放回原位之后（公式应排在其前）")
            visits = [len(v) for v in b.demo_visit_targets]
            stats[f"visits={visits}"] += 1
            # 答案：答案方块的第 which_in_subset 次访问
            if b.target_target is not b.which_targets_to_pick[b.which_in_subset - 1]:
                problems.append("which_in_subset 映射不符")
        else:
            stats[f"lang={b.target_target_language}"] += 1
            k = b.demo_cubes.index(b.target_cube)
            expect = b.demo_before_targets[k] if b.target_target_language == "before" else b.demo_after_targets[k]
            if b.target_target is not expect:
                problems.append("before/after 映射不符")
        stats[f"answer_idx={b.demo_cubes.index(b.target_cube)}"] += 1
        # vqa：drop onto 的候选里含两个落点
        opts = get_vqa_options(env, None, {"obj": None}, task)
        avail = [o for o in opts if o.get("action") == "drop onto"][0]["available"]
        if not all(any(h is a for a in avail) for h in b.xhard_home_sites) or len(avail) != 6:
            problems.append(f"vqa available={len(avail)}")
        if problems:
            fails["检查不过"] += 1
            print(f"seed={seed} PROBLEM {problems}", flush=True)
        else:
            ok += 1
        print(f"seed={seed} kind={b._spec.spec_kind} demo={[c.name for c in b.demo_cubes]} "
              f"answer={b.target_color_name} tt={b.targets.index(b.target_target)} "
              f"n_tasks={len(names)} n_demo={len(demo_names)} button@{bi}", flush=True)
    except Exception as exc:  # noqa: BLE001
        root = exc
        while root.__context__ is not None:
            root = root.__context__
        fails[f"root={type(root).__name__}"] += 1
        fails[type(exc).__name__] += 1
        print(f"seed={seed} FAIL {type(exc).__name__}: {exc}", flush=True)
    finally:
        if env is not None:
            env.close()
print(f"XHARD_RESET task={task} ok={ok}/{n} fails={dict(fails)} stats={dict(stats)}")
