"""进程地址只能通过可逆的一一映射规范化，不能丢失高亮实例。"""

from types import SimpleNamespace

import pytest

from robomme_icl.io.identities import scene_names


def test_runtime_address_maps_to_its_real_owner_and_instance():
    target = object()
    raw = f"highlight_disk_{id(target)}_2"
    base = SimpleNamespace(scene=SimpleNamespace(actors={"target_0": target, raw: object()}))
    result = scene_names(base)
    assert result == {"target_0": "target_0", raw: "highlight_disk/target_0/2"}


def test_unknown_owner_is_not_silently_discarded():
    base = SimpleNamespace(scene=SimpleNamespace(actors={"highlight_disk_12345_1": object()}))
    with pytest.raises(ValueError, match="所属物体"):
        scene_names(base)


def test_normalization_collision_is_rejected():
    target = object()
    base = SimpleNamespace(scene=SimpleNamespace(actors={
        "target_0": target,
        f"highlight_disk_{id(target)}_1": object(),
        "highlight_disk/target_0/1": object(),
    }))
    with pytest.raises(ValueError, match="一一映射"):
        scene_names(base)
