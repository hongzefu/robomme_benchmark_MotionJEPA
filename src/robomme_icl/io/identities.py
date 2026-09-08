"""为原版含进程地址的显示对象建立可持久化身份，不改原版Actor。"""

import re


def scene_names(base):
    owners = {id(actor): name for name, actor in base.scene.actors.items()}
    result = {}
    for name in base.scene.actors:
        matched = re.fullmatch(r"highlight_disk_(\d+)_(\d+)", name)
        if matched:
            owner = owners.get(int(matched[1]))
            if owner is None:
                raise ValueError(f"高亮对象找不到其原版所属物体：{name}")
            result[name] = f"highlight_disk/{owner}/{matched[2]}"
        else:
            result[name] = name
    if len(set(result.values())) != len(result):
        raise ValueError("显示对象稳定标识不是一一映射")
    return result
