"""读取实际 SAPIEN 组件，避免用名字或外包络代替素材一致性。"""

from __future__ import annotations

import numpy as np

from ..io.hdf5 import assert_identical, tree_hash


def array_copy(value):
    """物理缓冲区必须复制，不能让后续 step 改写已记录状态。"""
    if hasattr(value, "detach"):
        value = value.detach().cpu().numpy()
    return np.array(value, copy=True)


def pose_value(pose):
    return {"position": array_copy(pose.p), "quaternion": array_copy(pose.q)}


def material_asset(material):
    result = {}
    for field in ("base_color", "emission", "metallic", "roughness", "specular",
                  "transmission", "ior", "static_friction", "dynamic_friction", "restitution"):
        if hasattr(material, field):
            result[field] = array_copy(getattr(material, field))
    return result


def shape_asset(shape):
    """保留形状局部坐标、实际几何、材质与接触参数。"""
    result = {"type": type(shape).__name__, "pose": pose_value(shape.local_pose)}
    for field in ("half_size", "radius", "half_length", "scale", "vertices", "triangles",
                  "contact_offset", "rest_offset", "collision_groups"):
        if hasattr(shape, field):
            result[field] = array_copy(getattr(shape, field))
    if hasattr(shape, "parts"):
        result["mesh_parts"] = []
        for part in shape.parts:
            geometry = {}
            for field in ("vertices", "triangles", "normals", "uv"):
                if hasattr(part, field):
                    geometry[field] = array_copy(getattr(part, field))
            result["mesh_parts"].append({"geometry_hash": tree_hash(geometry),
                                         "material": material_asset(part.material)})
    elif hasattr(shape, "material"):
        result["material"] = material_asset(shape.material)
    return result


def actor_asset(actor):
    """同时记录视觉和碰撞，视觉无碰撞组件也不能遗漏。"""
    entities = []
    for entity in actor._objs:
        if not hasattr(entity, "components"):
            entity = entity.entity
        components = []
        for component in entity.components:
            if not hasattr(component, "render_shapes") and not hasattr(component, "collision_shapes"):
                continue
            entry = {"type": type(component).__name__}
            for field in ("render_shapes", "collision_shapes"):
                if hasattr(component, field):
                    entry[field] = [shape_asset(shape) for shape in getattr(component, field)]
            for field in ("mass", "inertia", "kinematic", "linear_damping", "angular_damping"):
                if hasattr(component, field):
                    entry[field] = array_copy(getattr(component, field))
            if hasattr(component, "cmass_local_pose"):
                entry["cmass_local_pose"] = pose_value(component.cmass_local_pose)
            components.append(entry)
        entities.append(components)
    return entities


def scene_assets(env):
    """每次读取当前场景；包含后来创建的轨迹和高亮对象。"""
    assets = {name: actor_asset(actor) for name, actor in sorted(env.scene.actors.items())}
    for name, articulation in sorted(env.scene.articulations.items()):
        for link in articulation.get_links():
            assets[f"{name}/{link.name}"] = actor_asset(link)
    return assets


def compare_assets(reference, actual):
    assert_identical(reference, actual, path="assets")
