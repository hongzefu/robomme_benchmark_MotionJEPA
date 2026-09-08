"""显式开启的四任务真实单局，不把素材创建成功当作任务完成。"""

import os

import pytest


@pytest.mark.gpu
@pytest.mark.skipif(os.environ.get("ICL_NATIVE_SMOKE") != "1", reason="设置ICL_NATIVE_SMOKE=1启用真实物理运行")
@pytest.mark.parametrize("task", ["BinFill", "RouteStick", "VideoUnmaskSwap", "VideoRepick"])
def test_native_single_episode(task):
    from robomme_icl.runtime import configure_runtime
    configure_runtime()
    from robomme_icl.api import make_env_from_spec
    from robomme_icl.config import load_configs
    from robomme_icl.sampling.tasks import plan_slots
    from robomme_icl.sampling.compiler import candidate_for_slot
    from robomme_icl.execution.episode import run_episode

    slot = plan_slots(*load_configs(), tasks=[task], episodes_per_task=1)[0]
    spec = candidate_for_slot(slot, 0)
    env = make_env_from_spec(spec)
    try:
        frames = run_episode(env)
        assert frames[-1]["info"]["success"] is True
        assert frames[-1]["info"]["fail"] is False
        assert any(frame["info"]["operation"] == "reset_complete" for frame in frames)
        assert any(frame["info"]["operation"] == "evaluate" for frame in frames)
        print(f"{task}: {len(frames)}操作，{frames[-1]['info']['step']}物理步，原版任务完成")
    finally:
        env.close()
