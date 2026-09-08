"""从完整认证记录提取小型初态证据，绘图不必加载所有图像帧。"""

import h5py

from .hdf5 import _read_node, tree_hash, RecordError
from .paths import output_path

SCENE_FIELDS = (
    "initial_assets",
    "initial_state",
    "native_parameters",
    "task_inventory",
)


def scene_metadata(info):
    return {field: info.get(field, {}) for field in SCENE_FIELDS}


def read_scene_metadata(certification):
    paths = certification.get("record_paths", [])
    if not paths or not certification.get("initial_scene_hash"):
        raise RecordError("分布图需要认证记录中的真实初态及其摘要")
    with h5py.File(output_path(paths[0]), "r") as handle:
        if handle.attrs.get("content_hash") != certification["content_hash"]:
            raise RecordError("初态来源与认证HDF5摘要不同")
        for frame in handle["steps"].values():
            info = frame["info"]
            if (
                "operation" in info
                and _read_node(info["operation"]) == "reset_complete"
            ):
                result = {field: _read_node(info[field]) for field in SCENE_FIELDS}
                if tree_hash(result) != certification["initial_scene_hash"]:
                    raise RecordError("真实初态被修改，拒绝出图")
                return result
    raise RecordError("认证记录没有初态标记")
