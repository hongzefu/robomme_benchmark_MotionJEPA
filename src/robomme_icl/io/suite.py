"""冻结清单读写：候选不能冒充已通过完整认证的环境。"""

from __future__ import annotations

import json
from pathlib import Path

from ..config import validate_configs
from ..specs import EpisodeSpec, canonical_json, content_hash


def _suite_path(path) -> Path:
    path = Path(path)
    return path if path.suffix == ".json" else path / "suite.json"


def _check_manifest(value: dict) -> list[EpisodeSpec]:
    if value.get("schema_version") != 2 or value.get("status") != "certified":
        raise ValueError("只能加载已认证的 schema_version=2 清单")
    configs = value["configs"]
    validate_configs(configs["task"], configs["position"])
    specs = [EpisodeSpec.from_dict(row) for row in value["episodes"]]
    if not specs:
        raise ValueError("不能发布空清单")
    if len({spec.seed for spec in specs}) != len(specs):
        raise ValueError("清单中 episode seed 必须全局唯一")
    if len({(spec.task_kind, spec.episode) for spec in specs}) != len(specs):
        raise ValueError("同一任务的 episode 编号重复")
    hashes = {spec.spec_hash for spec in specs}
    certification = value["certification"]
    if set(certification) != hashes:
        raise ValueError("每条场景必须恰好有一条绑定 spec_hash 的认证结果")
    for spec in specs:
        report = certification[spec.spec_hash]
        if report.get("passed") is not True or report.get("repeat_equal") is not True:
            raise ValueError("碰撞／任务／重复运行认证未通过，禁止发布")
        provenance = spec.to_dict()["provenance"]
        if provenance.get("task_config_hash") != content_hash(configs["task"]) or provenance.get("position_config_hash") != content_hash(configs["position"]):
            raise ValueError("spec 所用配置与套件内配置快照不一致")
    return specs


def save_suite(path, specs, configs, certification) -> Path:
    """所有认证通过后使用排他创建写入；已发布路径绝不自动覆盖。"""
    from robomme_icl.io.paths import output_path

    task_config, position_config = configs
    value = {
        "schema_version": 2, "status": "certified",
        "configs": {"task": task_config, "position": position_config},
        "episodes": [spec.to_dict() for spec in specs], "certification": certification,
    }
    _check_manifest(value)
    value["suite_hash"] = content_hash(value)
    destination = output_path(_suite_path(path), create_parent=True)
    with destination.open("x", encoding="utf-8") as stream:
        stream.write(canonical_json(value) + "\n")
    return destination


def load_suite(path) -> dict:
    """加载时重新验证外层哈希、逐局哈希、引用以及全部认证结果。"""
    with _suite_path(path).open(encoding="utf-8") as stream:
        value = json.load(stream)
    declared = value.pop("suite_hash", None)
    if declared is None or declared != content_hash(value):
        raise ValueError("suite 哈希缺失或不匹配")
    _check_manifest(value)
    value["suite_hash"] = declared
    return value


def find_spec(suite_or_path, task, seed) -> EpisodeSpec:
    """按任务和 seed 严格解析，不缺省读取旧 train metadata。"""
    value = suite_or_path if isinstance(suite_or_path, dict) else load_suite(suite_or_path)
    # dict 入口同样校验，避免内存修改绕过文件入口的完整性检查。
    unhashed = {key: item for key, item in value.items() if key != "suite_hash"}
    if value.get("suite_hash") != content_hash(unhashed):
        raise ValueError("内存中的 suite 哈希不匹配")
    specs = _check_manifest(value)
    matches = [spec for spec in specs if spec.task_kind == task and spec.seed == seed]
    if len(matches) != 1:
        raise ValueError(f"清单中未唯一找到 {task} seed={seed}")
    return matches[0]
