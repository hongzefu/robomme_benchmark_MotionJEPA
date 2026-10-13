"""只读探针：按钮关节体能否被 bin_collision 读取；底座/按帽形状与尺寸；按帽是否被底座覆盖。"""
import gymnasium as gym, numpy as np
import robomme.robomme_env  # noqa
import robomme_xhard
import robomme_xhard.envs.button_unmask_swap as bus
import robomme_xhard.envs.video_repick as vr
from robomme_xhard.collision import bin_collision as bc
bus.certify_swap_plan = lambda *a, **k: None
vr.certify_swap_plan = lambda *a, **k: None
for task, seed in [("ButtonUnmaskSwap", 10500), ("VideoRepick", 11200)]:
    env = gym.make(robomme_xhard.env_name(task), seed=seed, difficulty="xhard20", obs_mode="rgb+depth+segmentation",
                   control_mode="pd_joint_pos", render_mode="rgb_array", reward_mode="dense")
    env.reset(seed=seed); u = env.unwrapped
    names = ["button_left", "button_right"] if task == "ButtonUnmaskSwap" else ["button_left"]
    for nm in names:
        art = getattr(u, nm)
        print("PROBE", task, nm, "type", type(art).__name__)
        try:
            bc.object_state_from_actor(art, nm); print("  whole: OK")
        except Exception as e:
            print("  whole:", type(e).__name__, str(e)[:160])
        for link in art.get_links():
            ln = link.get_name()
            objs = getattr(link, "_objs", None)
            print("  link", ln, "objtype", type(objs[0]).__name__ if objs else type(link).__name__)
            try:
                st = bc.object_state_from_actor(link, ln)
                print("   bc OK p", np.round(st.p, 4).tolist(), "halves", [np.round(s.half, 4).tolist() for s in st.shapes])
            except Exception as e:
                print("   bc FAIL", type(e).__name__, str(e)[:200])
            comp = objs[0] if objs else None
            try:
                for sh in comp.get_collision_shapes():
                    d = {k: getattr(sh, k) for k in ("half_size", "radius", "half_length") if hasattr(sh, k)}
                    print("   shape", type(sh).__name__, {k: np.round(np.asarray(v), 4).tolist() for k, v in d.items()},
                          "local_p", np.round(sh.local_pose.p, 4).tolist())
            except Exception as e:
                print("   shapes FAIL", type(e).__name__, str(e)[:160])
    bins = getattr(u, "spawned_bins", None) or getattr(u, "spawned_cubes")
    st = bc.object_state_from_actor(bins[0], "obj0")
    bottoms = []
    from robomme_xhard.collision.bin_collision import quat_to_matrix
    R = quat_to_matrix(st.q)
    for s in st.shapes:
        c = st.p + R @ s.local_p
        Rs = R @ quat_to_matrix(s.local_q)
        ext = np.abs(Rs) @ s.half
        bottoms.append(round(float(c[2] - ext[2]), 4))
    print("PROBE", task, "swap-object shape bottoms z", bottoms)
    env.close()
print("EXIT_OK")
