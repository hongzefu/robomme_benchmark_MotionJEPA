"""完整操作轨迹的逐位核对，包括隐藏步骤和显式判定操作。"""

from ..errors import CandidateRejected
from ..io.hdf5 import assert_identical, RecordError


def check_terminal(frames):
    if not frames:
        raise CandidateRejected("rollout 没有操作记录")
    info = frames[-1]["info"]
    if info.get("success") is not True or info.get("fail") is not False:
        raise CandidateRejected("终态必须为success=True且fail=False")


def replay_frames(env, expected):
    env.reset()
    recorded = env.recorder.frames
    assert_identical(expected.frames[:len(recorded)], recorded, path="reset")
    for index in range(len(recorded), len(expected.frames)):
        frame = expected.frames[index]
        operation = frame["info"]["operation"]
        if operation == "step":
            if frame["joint_action"] is None:
                raise RecordError(f"第{index}个物理步缺少动作")
            # 回放内部物理步，原包装器的额外终止步已经单独记录。
            env.recorder.step(frame["joint_action"])
        elif operation == "evaluate":
            env.recorder.evaluate(solve_complete_eval=frame["info"]["solve_complete_eval"])
        else:
            raise RecordError(f"reset之后存在未知操作：{operation}")
        assert_identical(frame, recorded[-1], path=f"frames/{index}")
    check_terminal(recorded)
    return recorded
