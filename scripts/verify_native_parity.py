"""采集原版或 ICL 的真实素材；后续行为对照共用这一证据入口。"""

import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", required=True, choices=["BinFill", "RouteStick", "VideoUnmaskSwap", "VideoRepick"])
    parser.add_argument("--source", choices=["original", "icl"], required=True)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--difficulty", choices=["easy", "medium", "hard"], default="easy")
    parser.add_argument("--gpu", type=int, default=0)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    from robomme_icl.runtime import configure_runtime
    configure_runtime()
    import gymnasium as gym
    import h5py
    from robomme_icl.io.hdf5 import _write_node, tree_hash
    from robomme_icl.io.paths import output_path
    from robomme_icl.validation.assets import scene_assets, array_copy

    output = output_path(args.output_dir, create_parent=True)
    output.mkdir(exist_ok=False)
    if args.source == "original":
        import robomme.robomme_env  # noqa: F401
        env = gym.make(args.task, seed=args.seed, difficulty=args.difficulty,
                       obs_mode="rgb", control_mode="pd_joint_pos", render_mode="rgb_array",
                       sim_backend="physx_cpu", render_backend=f"cuda:{args.gpu}")
    else:
        from robomme_icl.suite import load_configs, plan_slots, candidate_for_slot
        from robomme_icl.envs import register_envs
        register_envs()
        slots = plan_slots(*load_configs(), tasks=[args.task])
        slot = next(row for row in slots if row["difficulty"] == args.difficulty)
        spec = candidate_for_slot(slot, 0)
        env = gym.make(spec.env_id, episode_spec=spec, render_gpu=args.gpu, disable_env_checker=True)
    try:
        base = env.unwrapped
        assets = scene_assets(base)
        raw = base.get_obs()
        snapshot = {"assets": assets, "rgb": {
            name: array_copy(data["rgb"]) for name, data in raw["sensor_data"].items()
        }}
        with h5py.File(output / "assets.h5", "x") as stream:
            _write_node(stream, "snapshot", snapshot)
        summary = {"task": args.task, "source": args.source, "seed": base.seed,
                   "difficulty": args.difficulty, "asset_names": list(assets),
                   "asset_hash": tree_hash(assets), "sim_freq": base.sim_freq,
                   "control_freq": base.control_freq}
        (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        print(json.dumps(summary), flush=True)
    finally:
        env.close()


if __name__ == "__main__":
    main()
