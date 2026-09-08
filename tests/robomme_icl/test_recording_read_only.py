"""模拟ManiSkill get_obs默认隐式判定，确保采集不增加求值次数。"""

from types import SimpleNamespace

import numpy as np


class CountingBase:
    def __init__(self):
        self.calls = 0
        self.elapsed_steps = np.array([0])
        self.sim_freq = 100
        self.control_freq = 20
        self.control_mode = "pd_joint_pos"
        device = SimpleNamespace(cuda_id=0, pci_string="0000:01:00.0")
        self.scene = SimpleNamespace(
            sub_scenes=[SimpleNamespace(render_system=SimpleNamespace(device=device))]
        )

    def evaluate(self, **kwargs):
        self.calls += 1
        return {"success": False, "fail": False}

    def get_obs(self, info=None):
        if info is None:
            self.evaluate()
        return {}


def test_explicit_evaluation_is_called_once_and_reset_marker_never_evaluates():
    from robomme_icl.execution.recording import RecordingEnv

    base = CountingBase()
    records = []

    def record(*args, **kwargs):
        row = {"info": {}}
        records.append(row)
        return row

    fake = SimpleNamespace(
        unwrapped=base,
        _record=record,
        initial_assets={},
        initial_state={},
        initial_sensor_parameters={},
        initial_tasks=[],
        native_parameters={},
    )
    RecordingEnv.evaluate(fake, solve_complete_eval=True)
    assert base.calls == 1
    RecordingEnv.reset_marker(fake)
    assert base.calls == 1
    assert len(records) == 2
