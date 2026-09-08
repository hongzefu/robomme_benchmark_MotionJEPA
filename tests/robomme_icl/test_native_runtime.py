"""显式开启的四任务真实单局，不把素材创建成功当作任务完成。"""

import os

import pytest


@pytest.mark.gpu
@pytest.mark.skipif(
    os.environ.get("ICL_NATIVE_SMOKE") != "1",
    reason="设置ICL_NATIVE_SMOKE=1启用真实物理运行",
)
@pytest.mark.parametrize(
    "task", ["BinFill", "RouteStick", "VideoUnmaskSwap", "VideoRepick"]
)
def test_native_single_episode(task):
    from robomme_icl.runtime import configure_runtime

    configure_runtime()
    from robomme_icl.api import make_env_from_spec
    from robomme_icl.config import load_configs
    from robomme_icl.sampling.tasks import plan_slots
    from robomme_icl.sampling.compiler import candidate_for_slot
    from robomme_icl.execution.episode import run_episode
    from robomme_icl.validation.geometry import validate_scene_geometry
    from robomme_icl.errors import TaskExecutionError
    import numpy as np

    slot = plan_slots(*load_configs(), tasks=[task], episodes_per_task=1)[0]
    for candidate_index in range(16):
        spec = candidate_for_slot(slot, candidate_index)
        env = make_env_from_spec(spec)
        try:
            actors = getattr(
                env.unwrapped, "all_cubes", getattr(env.unwrapped, "spawned_cubes", [])
            )
            for actor in actors:
                assert np.array_equal(
                    actor.pose.p.cpu().numpy(), actor.initial_pose.p.cpu().numpy()
                )
            if len(actors) > 1:
                assert len(
                    {tuple(actor.pose.p[0].tolist()) for actor in actors}
                ) == len(actors)
            geometry = validate_scene_geometry(env.unwrapped, spec)
            if not geometry["ok"]:
                continue
            env.geometry_report = geometry
            try:
                frames = run_episode(env)
            except TaskExecutionError:
                continue
            assert frames[-1]["info"]["success"] is True
            assert frames[-1]["info"]["fail"] is False
            assert any(
                frame["info"]["operation"] == "reset_complete" for frame in frames
            )
            assert any(frame["info"]["operation"] == "evaluate" for frame in frames)
            print(
                f"{task}: candidate={candidate_index}，{len(frames)}操作，{frames[-1]['info']['step']}物理步，原版任务完成"
            )
            return
        finally:
            env.close()
    pytest.fail("单局smoke在16个同配额候选内没有成功")
