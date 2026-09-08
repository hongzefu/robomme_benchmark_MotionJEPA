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
    assert_identical(expected.frames[: len(recorded)], recorded, path="reset")
    index = len(recorded)
    while index < len(expected.frames):
        frame = expected.frames[index]
        operation = frame["info"]["operation"]
        if operation == "step":
            if frame["joint_action"] is None:
                raise RecordError(f"第{index}个物理步缺少动作")
            # 调用原版包装器，让额外终止步自然产生，不能把它当另一条外部动作。
            if frame["info"].get("internal_terminal_step", False):
                raise RecordError("内部终止步缺少对应的外部动作")
            env.native_wrapper.step(frame["joint_action"])
        elif operation == "evaluate":
            env.recorder.evaluate(
                solve_complete_eval=frame["info"]["solve_complete_eval"]
            )
        else:
            raise RecordError(f"reset之后存在未知操作：{operation}")
        end = len(recorded)
        if end <= index or end > len(expected.frames):
            raise RecordError("回放产生的内部操作数量不匹配")
        assert_identical(
            expected.frames[index:end],
            recorded[index:end],
            path=f"frames/{index}:{end}",
        )
        index = end
    check_terminal(recorded)
    return recorded
