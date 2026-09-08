"""用已认证的四任务套件验证同一对象多次 reset 的真实物理与图像复现。"""

import os

import pytest


@pytest.mark.gpu
@pytest.mark.parametrize(
    "task", ["BinFill", "RouteStick", "VideoUnmaskSwap", "VideoRepick"]
)
def test_same_environment_reset_reproduces_all_frames(task):
    """显式设置 ICL_TEST_SUITE 后运行，不能以纯逻辑 mock 替代。"""
    path = os.environ.get("ICL_TEST_SUITE")
    if not path:
        pytest.skip("真实复现测试需要 ICL_TEST_SUITE 指向已认证套件")
    from robomme_icl import make_env
    from robomme_icl.io.hdf5 import assert_identical, read_episode
    from robomme_icl.execution.episode import run_episode
    from robomme_icl.suite import load_suite

    suite = load_suite(path)
    spec = next(row for row in suite["episodes"] if row["task_kind"] == task)
    env = make_env(task=task, seed=spec["seed"], suite=path)
    try:
        first = run_episode(env)
        second = run_episode(env)
        assert first[-1]["info"]["success"] is True
        assert first[-1]["info"]["fail"] is False
        certified = suite["certification"][spec["spec_hash"]]["record_paths"][0]
        assert_identical(
            read_episode(certified).frames,
            first,
            path=f"{task}/certified_vs_same_process",
        )
        assert_identical(first, second, path=f"{task}/same_env_reset")
    finally:
        env.close()
