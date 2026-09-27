"""看真实 demo 方块的 trimesh OBB → 2D OBB 与理想正方形的差别（seed 1000177 / 1000042）。"""
import sys, numpy as np
sys.path.insert(0, "/data/hongzefu/robomme_benchmark_MotionJEPANewTask/src")
sys.path.insert(0, "/tmp/claude-114466650/-data-hongzefu-robomme-benchmark-MotionJEPANewTask/4d4f0ebe-f95a-4495-b425-f61bacbd7855/scratchpad/v5/movecube")
import gymnasium as gym
import robomme.robomme_env  # noqa
from robomme.robomme_env.utils.object_generation import _trimesh_box_to_obb2d
from mani_skill.examples.motionplanning.base_motionplanner.utils import get_actor_obb
from mc_layout import simulate
for seed, diff in ((1000177, "xhard"), (1000042, "hard")):
    env = gym.make("MoveCube", obs_mode="rgb+depth+segmentation", control_mode="pd_joint_pos",
                   render_mode="rgb_array", reward_mode="dense", seed=seed, difficulty=diff)
    # 只建场景：reset 会跑 _load_scene；随后读 demo 方块的「初始」位姿（尚未 step）
    env.reset()
    base = env.unwrapped
    spec = base._spec.to_dict()
    d = spec["layout"]["demo"]["cube_pose"]
    obb = get_actor_obb(base.cube)
    c, A, h = _trimesh_box_to_obb2d(obb)
    print(f"OBBINSPECT seed={seed} demo_cube_spec={np.round(d,5).tolist()} obb2d c={np.round(c,5).tolist()} A={np.round(A,4).tolist()} h={np.round(h,5).tolist()} extents={np.round(getattr(obb,'primitive',obb).extents,5).tolist()}")
    m = simulate(seed, bias=0.5 if diff=="xhard" else 0.0, yaw_xhard=(diff=="xhard"))
    print(f"OBBINSPECT model demo cube={m.seg.get('demo',{}).get('cube') if m.ok else 'n/a (fail)'}")
    env.close()
