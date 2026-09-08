"""在独立 uv 子进程验证实际渲染卡；只建空 Scene，不加载任务或机械臂。"""

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.gpu


def _normalized_pci(value):
    """统一 nvidia-smi 的八位 domain 与 SAPIEN 的四位 domain 表示。"""
    domain, bus, device = value.strip().lower().split(":")
    return f"{int(domain, 16):04x}:{bus}:{device}"


@pytest.fixture(scope="module")
def gpu_inventory():
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("需要 uv 作为 GPU 检查子进程的唯一 Python runner")
    if shutil.which("nvidia-smi") is None:
        pytest.skip("没有 nvidia-smi，无法验证两张物理 GPU")
    if os.environ.get("CUDA_VISIBLE_DEVICES") is not None:
        pytest.skip("双物理卡验证要求主测试进程未设置 CUDA_VISIBLE_DEVICES")
    queried = subprocess.run(
        ["nvidia-smi", "--query-gpu=index,uuid,pci.bus_id", "--format=csv,noheader"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    if queried.returncode:
        pytest.skip(f"nvidia-smi 无法读取 GPU 清单: {queried.stderr.strip()}")
    devices = {}
    for line in queried.stdout.splitlines():
        if not line.strip():
            continue
        index, uuid, pci = (item.strip() for item in line.split(","))
        devices[int(index)] = {"uuid": uuid, "pci": _normalized_pci(pci)}
    if not {0, 1}.issubset(devices):
        pytest.skip(f"需要物理 GPU 0 和 1，当前仅有 {sorted(devices)}")
    assert devices[0]["pci"] != devices[1]["pci"]
    assert devices[0]["uuid"] != devices[1]["uuid"]
    return uv, devices


_PROBE = r"""
import json
import os
import sys
import sapien
from mani_skill.envs.scene import ManiSkillScene
from mani_skill.envs.utils.system.backend import parse_sim_and_render_backend

requested = int(sys.argv[1])
backend = parse_sim_and_render_backend("physx_cpu", f"cuda:{requested}")
subscene = sapien.Scene([
    sapien.physx.PhysxCpuSystem(),
    sapien.render.RenderSystem(backend.render_device),
])
scene = ManiSkillScene(sub_scenes=[subscene], backend=backend)
actual = scene.sub_scenes[0].render_system.device
method = scene.sub_scenes[0].get_render_system().device
unmapped_error = None
if os.environ.get("CUDA_VISIBLE_DEVICES") == "1":
    try:
        sapien.Device("cuda:1")
    except RuntimeError as error:
        unmapped_error = str(error)
result = {
    "requested": requested,
    "actual_cuda_id": actual.cuda_id,
    "actual_pci": actual.pci_string,
    "method_cuda_id": method.cuda_id,
    "method_pci": method.pci_string,
    "can_render": actual.can_render(),
    "is_cuda": actual.is_cuda(),
    "entity_count": len(subscene.entities),
    "visibility": os.environ.get("CUDA_VISIBLE_DEVICES"),
    "unmapped_error": unmapped_error,
}
print("GPU_BINDING_RESULT=" + json.dumps(result, sort_keys=True))
"""


def _run_probe(uv, requested, *, visibility=None):
    env = dict(os.environ)
    env["UV_CACHE_DIR"] = str(ROOT / ".cache" / "uv")
    if visibility is not None:
        env["CUDA_VISIBLE_DEVICES"] = visibility
    result = subprocess.run(
        [uv, "run", "--no-sync", "python", "-c", _PROBE, str(requested)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, (
        f"GPU 检查子进程失败:\n{result.stdout}\n{result.stderr}"
    )
    records = [
        line.removeprefix("GPU_BINDING_RESULT=")
        for line in result.stdout.splitlines()
        if line.startswith("GPU_BINDING_RESULT=")
    ]
    assert len(records) == 1, f"没有唯一的设备绑定证据: {result.stdout}"
    return json.loads(records[0])


@pytest.mark.parametrize("render_gpu", [0, 1])
def test_empty_scene_uses_requested_physical_gpu(gpu_inventory, render_gpu):
    uv, inventory = gpu_inventory
    result = _run_probe(uv, render_gpu)
    assert result["visibility"] is None
    assert result["actual_cuda_id"] == render_gpu
    assert result["method_cuda_id"] == render_gpu
    assert _normalized_pci(result["actual_pci"]) == inventory[render_gpu]["pci"]
    assert _normalized_pci(result["method_pci"]) == inventory[render_gpu]["pci"]
    assert result["is_cuda"] and result["can_render"]
    assert result["entity_count"] == 0


def test_visibility_remapping_is_confined_to_child_process(gpu_inventory):
    uv, inventory = gpu_inventory
    parent_visibility = os.environ.get("CUDA_VISIBLE_DEVICES")
    result = _run_probe(uv, 0, visibility="1")
    assert result["visibility"] == "1"
    assert result["actual_cuda_id"] == 0
    assert _normalized_pci(result["actual_pci"]) == inventory[1]["pci"]
    assert result["entity_count"] == 0
    assert result["unmapped_error"] == 'failed to find device "cuda:1"'
    assert os.environ.get("CUDA_VISIBLE_DEVICES") == parent_visibility
