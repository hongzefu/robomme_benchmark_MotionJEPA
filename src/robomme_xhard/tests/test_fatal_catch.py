"""主会话合并后以 timeout 300 执行：真实 worker 的三任务 fatal 送达闸门。"""

from pathlib import Path
import json

import pytest

from robomme_xhard.tests.test_jobs import new_gen


@pytest.mark.gpu
def test_fatal_catch_three_tasks(new_gen, monkeypatch, capsys):
    from robomme_xhard.swap_plan import SwapCollisionMixin
    from robomme_xhard.tests.test_s2_configs import MOTHER_RANK0_SEEDS

    def inject(self, k):
        if k == 1:
            self._record_fatal("SwapCollisionError", "segment_start", k,
                               detail={"injected": True}, check="sweep_actual")

    # 此闸门只验证拒绝送达；真实碰撞判据由 reset/运行期几何闸门独立验证。
    monkeypatch.setattr(SwapCollisionMixin, "_check_segment_start", inject)
    monkeypatch.setattr(SwapCollisionMixin, "_substep_check", lambda self, stage: None)
    root = new_gen.REPO_ROOT / "artifacts" / "tests" / "fatal-catch"
    import time
    root = root / f"run-{time.time_ns()}"
    root.mkdir(parents=True)
    for task in ("VideoUnmaskSwap", "ButtonUnmaskSwap", "VideoRepick"):
        seed = MOTHER_RANK0_SEEDS[task]
        episode = 6 if task == "VideoRepick" else 7
        job = new_gen.EpisodeJob(task, episode, 0, seed, "xhard20", str(root / task),
                                str(new_gen.REPO_ROOT), "xhard", task + "XHard",
                                "medium" if task == "VideoRepick" else "hard")
        result = new_gen._worker(job)
        (root / task).mkdir(parents=True, exist_ok=True)
        (root / task / "worker_result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        assert result["ok"] is False and result["task_success"] is False
        assert result["failure_class"] == "task"
        assert result["error_type"] == "SwapCollisionError"
        assert result["stage"] == "segment_start"
        assert result["detail"]["k"] == 1 and result["detail"]["detail"]["injected"]
        assert not result.get("traceback"), result.get("traceback")
        assert result["runtime_checks"] is not None
        assert result["failed_artifacts"]
        assert all(Path(p).exists() and Path(p).name.startswith("FAILED_")
                   for p in result["failed_artifacts"])
    with capsys.disabled():
        print(f"XHARD_FATAL_CATCH=PASS tasks=3 hang=0 evidence={root}", flush=True)
