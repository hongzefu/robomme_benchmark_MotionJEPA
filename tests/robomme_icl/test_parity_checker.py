"""通过完整HDF5入口注入反例，不能只测试一个底层数组比较函数。"""

import copy
import json
from pathlib import Path
import tempfile

import numpy as np
import pytest

from robomme_icl.io.hdf5 import write_episode, tree_hash
from robomme_icl.io.paths import repository_root
from robomme_icl.specs import NATIVE_REFERENCE
from robomme_icl.validation.parity import compare_episodes


@pytest.mark.parametrize(
    "mutation",
    ["missing_asset", "missing_subgoal", "late_event", "rgb", "task_parameter"],
)
def test_full_parity_entry_rejects_each_mutation(mutation):
    cache = repository_root() / ".cache" / "robomme_icl_tests"
    cache.mkdir(parents=True, exist_ok=True)
    pose = {
        "position": np.zeros((1, 3)),
        "quaternion": np.array([[1.0, 0.0, 0.0, 0.0]]),
    }
    state = {"actors": {"cube": {"pose": pose, "visibility": [1.0]}}, "task_state": {}}
    first = {
        "observation": {
            "base_rgb": np.zeros((2, 2, 3), dtype=np.uint8),
            "native_state": state,
        },
        "joint_action": None,
        "info": {
            "operation": "reset_complete",
            "step": 0,
            "subgoal_index": 0,
            "subgoal": "pick",
            "is_demonstration": False,
            "initial_assets": {"cube": ["visual", "collision"]},
            "initial_state": state,
            "initial_sensor_parameters": {},
            "task_inventory": [{"name": "pick"}, {"name": "put"}],
            "native_parameters": {"pick_count": 1},
            "success": False,
            "fail": False,
        },
    }
    second = copy.deepcopy(first)
    second["info"].update(
        operation="step", step=1, subgoal_index=1, subgoal="put", success=True
    )
    second["observation"]["native_state"]["actors"]["cube"]["pose"]["position"][
        0, 0
    ] = 10
    reference_frames = [first, second]
    frames = copy.deepcopy(reference_frames)
    if mutation == "missing_asset":
        frames[0]["info"]["initial_assets"]["cube"].pop()
    elif mutation == "missing_subgoal":
        frames[0]["info"]["task_inventory"].pop()
    elif mutation == "late_event":
        frames[1]["info"]["step"] += 1
    elif mutation == "rgb":
        frames[1]["observation"]["base_rgb"][0, 0, 0] = 1
    else:
        frames[0]["info"]["native_parameters"]["pick_count"] = 2
    spec = {"seed": 1, "env_id": "RoboMME-ICL/BinFill-v0", "testing": "合成检查器反例"}
    spec["spec_hash"] = tree_hash(spec)
    with tempfile.TemporaryDirectory(dir=cache, prefix="parity-") as directory:
        root = Path(directory)
        reference = write_episode(
            root / "reference.h5",
            spec,
            reference_frames,
            runtime_fingerprint={
                "reference_commit": NATIVE_REFERENCE,
                "legacy_source_hash": "ref",
                "testing": True,
            },
        )
        actual = write_episode(
            root / "actual.h5",
            spec,
            frames,
            runtime_fingerprint={"legacy_source_hash": "actual", "testing": True},
        )
        clean = write_episode(
            root / "clean.h5",
            spec,
            reference_frames,
            runtime_fingerprint={"legacy_source_hash": "actual", "testing": True},
        )
        assert compare_episodes(reference, clean, root / "clean.json")["passed"] is True
        report = root / "report.json"
        with pytest.raises(Exception):
            compare_episodes(reference, actual, report)
        result = json.loads(report.read_text())
        assert result["passed"] is False
        assert result["error"]
