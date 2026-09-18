"""只依赖标准库的候选封套读取；管理状态与旧规格身份分别校验。"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


class CandidateError(ValueError):
    """候选缺失、重复、被篡改或快照与当前源码不一致。"""


RUNTIME = {"layout": "train", "kwargs": {
    "obs_mode": "rgb+depth+segmentation", "control_mode": "pd_joint_pos",
    "render_mode": "rgb_array", "reward_mode": "dense",
}}
_CANDIDATE_KEYS = set("record task difficulty episode block seed spec_sha256 split role error_type spec screening".split())
_HEADER_KEYS = set("record run_id candidate_schema_version spec_schema_version generator_seed generator_version contract contract_sha256 sampling_config_sha256 sampling_file_sha256 delivery_config delivery_config_sha256 groups candidates group_provenance sampling_config delivery_config_snapshot runtime identity_sha256 purpose".split())
_HEADER_OPTIONAL = {"roles", "parent_run_id", "parent_candidates_sha256", "evidence_source"}
_MUTABLE = {"run_id", "role", "error_type", "roles", "screening", "parent_run_id", "parent_candidates_sha256", "evidence_source", "identity_sha256"}
_ENV_CODES = {"BinFill": 4, "VideoUnmaskSwap": 5, "VideoRepick": 9, "RouteStick": 16}


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def record_sha256(spec: dict[str, Any]) -> str:
    return digest({k: v for k, v in spec.items() if k not in {"spec_sha256", "collision"}})


def candidate_key(row: dict[str, Any]) -> tuple[str, str, int]:
    return row["task"], row["difficulty"], row["episode"]


def seed_for(task: str, episode: int) -> int:
    return _ENV_CODES[task] * 1000 + episode * 100


def identity_sha256(header: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    return digest({"header": {k: v for k, v in header.items() if k not in _MUTABLE},
                   "candidates": [{k: v for k, v in row.items() if k not in _MUTABLE}
                                  for row in sorted(rows, key=candidate_key)]})


def _keys(value: dict[str, Any], required: set[str], optional: set[str], label: str) -> None:
    missing = required - value.keys()
    extra = value.keys() - required - optional
    if missing or extra:
        raise CandidateError(f"{label} 字段集合不符：缺少 {sorted(missing)}，多出 {sorted(extra)}")


def project_spec(row: dict[str, Any]) -> dict[str, Any]:
    """返回深拷贝；绝不向旧规格补键或移除未知键。"""
    _keys(row, _CANDIDATE_KEYS, set(), "候选")
    spec = row["spec"]
    if row["record"] != "candidate" or not isinstance(spec, dict):
        raise CandidateError("不是候选封套")
    if any(row[k] != spec.get(k) for k in ("task", "difficulty", "episode")):
        raise CandidateError("外层主键与旧规格不一致")
    if row["spec_sha256"] != spec.get("spec_sha256") or record_sha256(spec) != row["spec_sha256"]:
        raise CandidateError("旧规格散列不一致")
    return copy.deepcopy(spec)


def _validate_screening(row: dict[str, Any]) -> None:
    screening = row["screening"]
    if not isinstance(screening, dict):
        raise CandidateError("筛查证据必须是对象")
    _keys(screening, set("geometry collision_initial collision_sweeps min_g_m evidence_origin count_unit candidates_tried accepted rejected_before_accept".split()), set(), "筛查证据")
    if screening["geometry"] != "PASS" or screening["evidence_origin"] not in {"generated", "reconstructed"}:
        raise CandidateError("候选缺少通过筛查的观测证据")
    spec = row["spec"]
    collision = spec.get("collision", {})
    for outer, inner in (("collision_initial", "initial"), ("collision_sweeps", "sweeps"), ("min_g_m", "min_g_m")):
        if screening[outer] != collision.get(inner):
            raise CandidateError("筛查与旧碰撞诊断不一致")
    if row["task"] == "RouteStick":
        if screening["count_unit"] != "not_applicable" or any(screening[k] is not None for k in ("candidates_tried", "accepted", "rejected_before_accept")):
            raise CandidateError("RouteStick 不适用拒绝计数，必须为 null")
        return
    unit = "object_proposal" if row["task"] == "BinFill" else "episode_proposal"
    accepted = len(spec["layout"]["cubes"]) if row["task"] == "BinFill" else 1
    rejected = screening["rejected_before_accept"]
    if not isinstance(rejected, dict) or set(rejected) != {"geometry", "contact", "numerical_boundary", "uncertified"}:
        raise CandidateError("拒绝计数缺少分类")
    counts = [screening["candidates_tried"], screening["accepted"], *rejected.values()]
    if any(type(v) is not int or v < 0 for v in counts):
        raise CandidateError("尝试计数必须为非负整数")
    if screening["count_unit"] != unit or screening["accepted"] != accepted or screening["candidates_tried"] != accepted + sum(rejected.values()):
        raise CandidateError("尝试计数单位或守恒关系不符")
    if collision and collision["candidates_used"] != screening["candidates_tried"]:
        raise CandidateError("旧碰撞尝试数与观测不一致")


def validate_candidates(header: dict[str, Any], rows: list[dict[str, Any]], *, repo_root: Path | None = None) -> None:
    _keys(header, _HEADER_KEYS, _HEADER_OPTIONAL, "header")
    if header["record"] != "header" or header["candidate_schema_version"] != 1 or header["spec_schema_version"] != 1:
        raise CandidateError("不支持的候选格式版本")
    if header["purpose"] not in {"delivery", "smoke"} or header["runtime"] != RUNTIME:
        raise CandidateError("运行目的或固定环境参数不符")
    sampling = header["sampling_config"]
    if sampling.get("schema_version") != 3:
        raise CandidateError("采样快照版本不符")
    provenance = header["group_provenance"]
    if header["groups"] != len(provenance) or header["candidates"] != len(rows) or not rows:
        raise CandidateError("声明的组数或候选数不符")
    delivery = header["delivery_config_snapshot"]
    groups = {(g["task"], g["difficulty"]): g for g in delivery["groups"]}
    if len(groups) != len(delivery["groups"]):
        raise CandidateError("交付配置存在重复组")
    expected = set()
    for name, p in provenance.items():
        task, difficulty = name.split("/")
        _keys(p, set("spec_schema_version task difficulty generator_seed derived_seed generator_version sampling_config_sha256".split()), {"blocks"}, "组溯源")
        if (task, difficulty) not in groups or p["task"] != task or p["difficulty"] != difficulty:
            raise CandidateError("组溯源主键不一致")
        if p["generator_seed"] != header["generator_seed"] or p["generator_version"] != header["generator_version"] or p["spec_schema_version"] != 1:
            raise CandidateError("组溯源生成器不一致")
        blocks = p.get("blocks", 1)
        if type(blocks) is not int or blocks < 1:
            raise CandidateError("组溯源 block 数非法")
        expected.update((task, difficulty, ep) for ep in range(blocks * 100))
    seen = set()
    for row in rows:
        project_spec(row)
        key = candidate_key(row)
        if key in seen or key not in expected:
            raise CandidateError(f"重复或额外候选键：{key}")
        seen.add(key)
        task, difficulty, ep = key
        if type(ep) is not int or ep < 0 or row["block"] != ep // 100 or row["seed"] != seed_for(task, ep):
            raise CandidateError(f"候选编号、block 或 seed 不符：{key}")
        split = "train" if ep < groups[(task, difficulty)]["run_episodes"] else "test"
        if row["split"] != split or row["role"] not in {"pending", "primary", "spare", "failed", "unused"}:
            raise CandidateError(f"候选划分或角色非法：{key}")
        if (split == "train" and row["role"] == "unused") or (row["role"] != "failed" and row["error_type"] is not None):
            raise CandidateError(f"角色与错误状态冲突：{key}")
        _validate_screening(row)
    if seen != expected:
        raise CandidateError(f"候选缺失：{len(expected - seen)}")
    parameters = copy.deepcopy(sampling["parameters"])
    difficulties = {key[1] for key in expected}
    for value in parameters.values():
        if isinstance(value, dict) and isinstance(value.get("configs"), dict):
            value["configs"] = {k: v for k, v in value["configs"].items() if k in difficulties}
    operands = digest({"parameters": parameters, "positions": sampling["positions"]})
    if header["sampling_config_sha256"] != operands or any(p["sampling_config_sha256"] != operands for p in provenance.values()):
        raise CandidateError("采样取值域散列不符")
    if identity_sha256(header, rows) != header["identity_sha256"]:
        raise CandidateError("候选或快照身份散列不符")
    if repo_root is not None:
        root = repo_root.resolve()
        for source in sampling["sources"].values():
            path = (root / source["path"]).resolve()
            if not path.is_relative_to(root) or hashlib.sha256(path.read_bytes()).hexdigest() != source["sha256"]:
                raise CandidateError(f"采样源码指纹不符：{source['path']}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise CandidateError(f"JSON 存在重复字段：{key}")
        result[key] = value
    return result


def load_candidates(path: str | Path, *, repo_root: Path | None = None, allow_migrating: bool = False) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    path = Path(path)
    if not allow_migrating:
        for parent in path.resolve().parents:
            state = parent / "rollout/logs/migration/state.json"
            if state.is_file() and json.loads(state.read_text())["state"] != "complete":
                raise CandidateError("所属运行正在迁移，须恢复完成后才能读取候选启动环境")
            if repo_root is not None and parent == repo_root.resolve():
                break
    with path.open(encoding="utf-8") as stream:
        records = [json.loads(line, object_pairs_hook=_unique_object) for line in stream]
    if not records:
        raise CandidateError("候选文件为空")
    header, rows = records[0], records[1:]
    validate_candidates(header, rows, repo_root=repo_root)
    return header, rows


def write_candidates(path: Path, header: dict[str, Any], rows: list[dict[str, Any]], *, replace: bool = False) -> None:
    """默认禁止覆盖；单文件原子发布，调用方负责运行级独占锁。"""
    validate_candidates(header, rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".candidates-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            for row in [header, *rows]:
                stream.write(canonical_json(row) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        if replace:
            os.replace(temporary, path)
        else:
            os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
