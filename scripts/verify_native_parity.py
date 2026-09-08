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
    parser.add_argument("--capture", choices=["assets", "episode"], default="assets")
    parser.add_argument("--input-record", type=Path, help="使用现有记录的冻结输入，不重选位置或次数")
    parser.add_argument("--reference-root", type=Path, help="固定原版src所在的副本根目录")
    args = parser.parse_args()

    from robomme_icl.runtime import configure_runtime
    configure_runtime()
    import gymnasium as gym
    import h5py
    from robomme_icl.io.hdf5 import _write_node, tree_hash, read_episode, write_episode
    from robomme_icl.io.paths import output_path
    from robomme_icl.validation.assets import scene_assets, array_copy

    output = output_path(args.output_dir, create_parent=True)
    output.mkdir(exist_ok=False)
    if args.capture == "episode":
        from robomme_icl.specs import EpisodeSpec
        from robomme_icl.io.fingerprint import runtime_fingerprint, source_commit, _tree_hash
        if not args.input_record:
            parser.error("完整行为对照要求--input-record提供同一份冻结输入")
        spec = EpisodeSpec.from_dict(read_episode(args.input_record).episode_spec)
        if spec.task_kind != args.task:
            parser.error("--task与冻结输入任务不同")
        reference = None
        if args.source == "original":
            if not args.reference_root:
                parser.error("原版行为对照要求--reference-root")
            from robomme_icl.native.reference import load_reference, run_reference_episode
            reference = load_reference(args.reference_root)
            frames, names = run_reference_episode(spec, args.gpu)
        else:
            from robomme_icl.api import make_env_from_spec
            from robomme_icl.execution.episode import run_episode
            from robomme_icl.validation.geometry import validate_scene_geometry
            env = make_env_from_spec(spec, render_gpu=args.gpu)
            try:
                geometry = validate_scene_geometry(env.unwrapped, spec)
                if not geometry["ok"]:
                    raise ValueError(f"冻结输入的初态几何未通过：{geometry}")
                env.geometry_report = geometry
                frames = run_episode(env)
                names = dict(env.recorder.runtime_names)
            finally:
                env.close()
        fingerprint = runtime_fingerprint(render_gpu=args.gpu)
        if reference:
            fingerprint["legacy_source_hash"] = _tree_hash(args.reference_root / "src/robomme")
            fingerprint["reference_commit"] = reference["commit"]
        write_episode(output / "episode.h5", spec, frames, runtime_fingerprint=fingerprint, source_commit=source_commit(),
                      runtime_name_mapping=names)
        summary = {"task": args.task, "source": args.source, "seed": spec.seed,
                   "operations": len(frames), "physical_step": frames[-1]["info"]["step"],
                   "success": frames[-1]["info"]["success"], "fail": frames[-1]["info"]["fail"],
                   "frames_hash": tree_hash(frames), "reference": reference}
        (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        print(json.dumps(summary), flush=True)
        return
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
