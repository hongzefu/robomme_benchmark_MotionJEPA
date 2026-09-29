"""test-hard 四档规格（``env_metadata/test-hard/xhardN/specs.jsonl``）的读取、封套校验与回注绑定摘要。

由 ``scripts/parity/v4_specs.py`` 下沉而来（0927 计划第二部分 §1.2）；抽签与冻结留在
``scripts/injection-dev/``，本模块只放评估侧与生成侧都要用的纯函数，不导入仿真。

jsonl 一行分「签」与「结果」两段（0927 计划第一部分 §5.3，``schema="hard-specs/2"``）：

* 签：``task tier candidate episode seed attempt spec spec_sha256``——第一阶段封存，``identity_sha256`` 覆盖；
* 结果：``selected tried initial_selected rollout``——第二阶段回写，不进 ``identity_sha256``。

``delivery_sha256`` 另盖「哪几局是正式交付」：排序后的
``(task, tier, candidate, seed, spec_sha256, rollout.h5_sha256)``，只取 ``selected`` 且 ``rollout.status=="ok"`` 的行。
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import warnings
from pathlib import Path
from typing import Any

SCHEMA = "hard-specs/2"
#: V7（0928 方案第二部分 §1.1）：/3 在 /2 的基础上多 header ``layout_rule`` 与行 ``layout_parent``；
#: 身份键按 schema 分表，/2 的 identity_sha256 逐字不变（旧 v6 快照照旧可读）。
SCHEMA_V7 = "hard-specs/3"
SCHEMAS = (SCHEMA, SCHEMA_V7)
TIERS = ("xhard1", "xhard2", "xhard3", "xhard4")
#: builder 档序：xhard0（官方 test 的 hard 子集，原生分支、不回注）在最前；TIERS 只含新值四档不变
#: （EXPECTED_CELLS、freeze_specs --tier 等依赖它）。
XHARD0 = "xhard0"
BUILDER_TIERS = (XHARD0, *TIERS)
#: xhard0 每任务 12 局＝官方 test 元数据 difficulty=="hard" 的原 episode 3,7,…,47（只作核对值，筛选按 difficulty）
XHARD0_PER_TASK = 12
XHARD0_EPISODES = tuple(range(3, 48, 4))
#: 历史 V4/V5 单档名（seed 规则 v5 只对它合法），保留以便核对旧快照。
DIFFICULTY = "xhard"
#: 评估步数上限按档（用户 U-6：沿用上次评估 1500/1700/2000/2600 以便对比）；
#: 值抄自 scripts/eval/v4_eval.py::NEWVALUE_MAX_STEPS（阶段 1 cmp 留证后该文件随 scripts/eval/ 删除）。
#: xhard0 取 1300，与官方 scripts/evaluation.py 的默认步数相同（v7 方案 §7.4）。
TIER_MAX_STEPS = {"xhard0": 1300, "xhard1": 1500, "xhard2": 1700, "xhard3": 2000, "xhard4": 2600}
#: 回注绑定：只记录不回注的观测值（SpecRecorder.record）允许的浮点差（用户 U-13 方案甲，红线 R22，不做参数）。
RECORDED_FLOAT_TOL = 1e-5

# runtime 四项与 gym.make 参数逐字相同（builder 起环境时逐字比对，render_mode 放行）
RUNTIME = {
    "obs_mode": "rgb+depth+segmentation",
    "control_mode": "pd_joint_pos",
    "render_mode": "rgb_array",
    "reward_mode": "dense",
}
# seed = offset + env_code × env_block + episode × 100 + attempt；env_code 是任务在 16 任务规范序里的 1-indexed 位置
SEED_RULE = {"offset": 4_000_000, "env_block": 100_000, "episode_stride": 100,
             "formula": "offset + env_code*env_block + episode*100 + attempt"}
V6_SEED_OFFSETS = {"xhard4": 6_000_000, "xhard1": 8_000_000, "xhard2": 10_000_000, "xhard3": 12_000_000}
#: V7：四档同一 offset，同一候选号在四档里 seed 相同（母布局共用）；与 V5（4e6）、V6（6e6～12e6）段互不重叠
V7_SEED_OFFSET = 14_000_000
SEED_PROFILES = ("v5", "v6", "v7")
MAX_ATTEMPTS = 100
#: 16 任务规范序（与 scripts/injection-dev/seed_layout.py::ALL_TASKS 逐字相同；src 不反向依赖 scripts）
ALL_TASKS = (
    "PickXtimes", "StopCube", "SwingXtimes", "BinFill", "VideoUnmaskSwap", "VideoUnmask",
    "ButtonUnmaskSwap", "ButtonUnmask", "VideoRepick", "VideoPlaceButton", "VideoPlaceOrder",
    "PickHighlight", "InsertPeg", "MoveCube", "PatternLock", "RouteStick",
)
#: xhard4 独有的三个任务：xhard1～3 这三格恰好 0 行
XHARD4_ONLY = ("StopCube", "InsertPeg", "MoveCube")
#: 55 格表：(task, tier) → 是否应有正式交付局（builder 按它断言每格行数）
EXPECTED_CELLS = frozenset(
    (task, tier) for tier in TIERS for task in ALL_TASKS if tier == "xhard4" or task not in XHARD4_ONLY
)

# 签：进 identity_sha256 的 header 键与行键
IDENTITY_HEADER_KEYS = ("schema", "difficulty", "tasks", "per_env", "runtime", "seed_rule", "select_rule",
                        "sampling_config_sha256", "recovery_rule", "identity_source")
IDENTITY_ROW_KEYS = ("task", "tier", "candidate", "episode", "seed", "attempt", "spec_sha256")
HEADER_REQUIRED = {"record", *IDENTITY_HEADER_KEYS, "sampling_config", "run_id", "draw_stats", "provenance",
                   "delivery_per_cell", "identity_sha256", "delivery_sha256"}
#: 迁移来源专有键（从旧快照迁移时写；重新抽签生成的文件可以没有）
HEADER_OPTIONAL = {"drafts_sha256", "legacy_identity_sha256", "source_files", "eval_identities_sha256",
                   "dedup_dropped", "demo_frames_out_of_band", "notes"}
ROW_KEYS = {"record", *IDENTITY_ROW_KEYS, "spec", "selected", "tried", "initial_selected", "rollout"}
ROLLOUT_STATUSES = ("ok", "failed")
#: 身份键按 schema 分表（/2 原样，保证 v6 规格摘要逐字不变）
IDENTITY_KEYS_BY_SCHEMA = {
    SCHEMA: (IDENTITY_HEADER_KEYS, IDENTITY_ROW_KEYS),
    SCHEMA_V7: (IDENTITY_HEADER_KEYS + ("layout_rule",), IDENTITY_ROW_KEYS + ("layout_parent",)),
}


def _schema_keys(schema: str) -> tuple[tuple[str, ...], tuple[str, ...], set[str], set[str]]:
    if schema not in IDENTITY_KEYS_BY_SCHEMA:
        raise SpecsError(f"specs 版本不符：{schema}")
    header_keys, row_keys = IDENTITY_KEYS_BY_SCHEMA[schema]
    header_required = (HEADER_REQUIRED - set(IDENTITY_HEADER_KEYS)) | set(header_keys)
    row_required = (ROW_KEYS - set(IDENTITY_ROW_KEYS)) | set(row_keys)
    return header_keys, row_keys, header_required, row_required


class SpecsError(ValueError):
    """规格文件缺失、被篡改、来源不符或字段集合不符。"""


# ── 基础函数 ─────────────────────────────────────────────────────────────


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def spec_sha256(spec: dict[str, Any]) -> str:
    return digest(spec)


def env_code(task: str) -> int:
    if task not in ALL_TASKS:
        raise SpecsError(f"未知环境名：{task}")
    return ALL_TASKS.index(task) + 1


def seed_rule_for(difficulty: str = DIFFICULTY, profile: str = "v5") -> dict[str, Any]:
    """按档位与规则族给出 seed 规则；v5 只覆盖历史 xhard 单档，v6 按档偏移。"""
    if difficulty == DIFFICULTY and profile == "v5":
        return dict(SEED_RULE)
    if difficulty not in TIERS:
        raise SpecsError(f"未知档位 {difficulty!r}，只支持 {TIERS}")
    if profile == "v6":
        return {**SEED_RULE, "offset": V6_SEED_OFFSETS[difficulty]}
    if profile == "v7":
        return {**SEED_RULE, "offset": V7_SEED_OFFSET}
    raise SpecsError(f"{difficulty} 只支持 seed 规则 v6／v7（收到 {profile!r}）")


def _known_seed_rule(difficulty: str, rule: dict[str, Any]) -> bool:
    for profile in SEED_PROFILES:
        try:
            if rule == seed_rule_for(difficulty, profile):
                return True
        except SpecsError:
            continue
    return False


def seed_for(task: str, episode: int, attempt: int, rule: dict[str, Any] | None = None) -> int:
    rule = SEED_RULE if rule is None else rule
    if not 0 <= int(attempt) < MAX_ATTEMPTS:
        raise SpecsError(f"attempt 必须落在 [0, {MAX_ATTEMPTS})，当前为 {attempt}")
    return int(rule["offset"]) + env_code(task) * int(rule["env_block"]) + int(episode) * 100 + int(attempt)


def identity_sha256(header: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    """只盖签：header 规格键 + 每行签键；provenance、draw_stats、run_id 与结果段都不进。键集合按 header 的 schema 取。"""
    header_keys, row_keys, _, _ = _schema_keys(header.get("schema", SCHEMA))
    ordered = sorted(rows, key=lambda r: (r["task"], int(r["candidate"])))
    return digest({
        "header": {key: header[key] for key in header_keys},
        "rows": [{key: row[key] for key in row_keys} for row in ordered],
    })


def delivered(row: dict[str, Any]) -> bool:
    rollout = row.get("rollout") or {}
    return bool(row.get("selected")) and rollout.get("status") == "ok"


def delivery_sha256(rows: list[dict[str, Any]]) -> str:
    items = sorted(
        (row["task"], row["tier"], int(row["candidate"]), int(row["seed"]), row["spec_sha256"],
         (row.get("rollout") or {}).get("h5_sha256"))
        for row in rows if delivered(row)
    )
    return digest([list(item) for item in items])


# ── 源码指纹（只进 provenance，不进 identity；不符只警告）───────────────────


def _package_root(name: str) -> Path:
    import importlib.util

    spec = importlib.util.find_spec(name)
    if spec is None or not spec.submodule_search_locations:
        raise SpecsError(f"找不到包 {name}")
    return Path(list(spec.submodule_search_locations)[0])


def hard_fingerprint() -> str:
    """``robomme_hard`` 全部 .py 的相对路径与 sha256 的总散列。"""
    root = Path(__file__).resolve().parents[1]
    files = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in sorted(root.rglob("*.py")) if "__pycache__" not in p.parts}
    return digest(files)


def base_fingerprint() -> str:
    """借用的官方 shim 目标文件的总散列（按 UPSTREAM.json 清单读当前安装的 robomme）。"""
    manifest = json.loads((Path(__file__).resolve().parents[1] / "UPSTREAM.json").read_text(encoding="utf-8"))
    robomme_root = _package_root("robomme")
    files = {}
    for entry in manifest["shims"]:
        rel = entry["target_file"][len("src/robomme/"):]
        path = robomme_root / rel
        files[entry["target_file"]] = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
    return digest(files)


# ── 读写 ───────────────────────────────────────────────────────────────


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise SpecsError(f"JSON 存在重复字段：{key}")
        result[key] = value
    return result


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    with Path(path).open(encoding="utf-8") as stream:
        records = [json.loads(line, object_pairs_hook=_unique_object) for line in stream if line.strip()]
    if not records:
        raise SpecsError(f"{path} 为空")
    return records


def _exact_keys(value: dict[str, Any], required: set[str], label: str, optional: set[str] = frozenset()) -> None:
    missing, extra = required - value.keys(), value.keys() - required - optional
    if missing or extra:
        raise SpecsError(f"{label} 字段集合不符：缺少 {sorted(missing)}，多出 {sorted(extra)}")


def _check_layout_parent(row: dict[str, Any], tier: str, key) -> None:
    """/3 单文件形态：xhard4 行 layout_parent 为 null、规格为 native-newvalue/2；低档行指向同候选的 xhard4 行、规格为 native-layered/3。"""
    parent = row["layout_parent"]
    kind = (row.get("spec") or {}).get("spec_kind")
    if tier == "xhard4":
        if parent is not None or kind != "native-newvalue/2":
            raise SpecsError(f"xhard4 母布局行 layout_parent 必须为 null、规格为 native-newvalue/2：{key}")
        return
    if not isinstance(parent, dict) or set(parent) != {"tier", "candidate", "spec_sha256"} \
            or parent["tier"] != "xhard4" or int(parent["candidate"]) != int(row["candidate"]) \
            or not isinstance(parent["spec_sha256"], str):
        raise SpecsError(f"派生行 layout_parent 形态不符：{key} {parent}")
    if kind != "native-layered/3":
        raise SpecsError(f"派生行规格必须为 native-layered/3：{key}")


def load_specs_v7(root: str | Path, *, check_fingerprint: bool = True) -> dict[str, tuple]:
    """读 v7 规格根（xhard{1..4}/specs.jsonl），另做跨文件校验：四档 seed 规则相同；派生行的
    ``layout_parent.spec_sha256`` 等于 xhard4 同候选行的 ``spec_sha256``、seed 相同。返回 ``{tier: (header, rows)}``。"""
    out = {tier: load_specs(Path(root) / tier / "specs.jsonl", check_fingerprint=check_fingerprint) for tier in TIERS}
    rules = {tier: out[tier][0]["seed_rule"] for tier in TIERS}
    if len({canonical_json(r) for r in rules.values()}) != 1 or any(out[t][0]["schema"] != SCHEMA_V7 for t in TIERS):
        raise SpecsError("v7 规格根：四档 schema 须为 hard-specs/3 且 seed 规则相同")
    parents = {(row["task"], int(row["candidate"])): row for row in out["xhard4"][1]}
    for tier in ("xhard1", "xhard2", "xhard3"):
        for row in out[tier][1]:
            key = (row["task"], int(row["candidate"]))
            mother = parents.get(key)
            if mother is None or mother["spec_sha256"] != row["layout_parent"]["spec_sha256"] \
                    or int(mother["seed"]) != int(row["seed"]):
                raise SpecsError(f"{tier} 派生行找不到对应的 xhard4 母布局或摘要／seed 不符：{key}")
    return out


def validate_specs(header: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    """封套校验：字段集合、runtime、seed 规则、配置散列、逐行 seed 与规格散列、两个身份散列、每格正式局数上限。"""
    schema = header.get("schema")
    _, _, header_required, row_required = _schema_keys(schema)
    _exact_keys(header, header_required, "specs header", HEADER_OPTIONAL)
    if header["record"] != "header":
        raise SpecsError(f"specs 版本不符：{schema}")
    tier = header["difficulty"]
    if tier not in TIERS or header["runtime"] != RUNTIME:
        raise SpecsError("specs 档位或 runtime 不符")
    if not _known_seed_rule(tier, header["seed_rule"]):
        raise SpecsError("specs 的 seed 规则与档位不符")
    if schema == SCHEMA_V7:
        if header["seed_rule"] != seed_rule_for(tier, "v7"):
            raise SpecsError("hard-specs/3 只接受 v7 seed 规则（四档同 offset）")
        rule = header["layout_rule"]
        if not isinstance(rule, dict) or rule.get("mode") != "shared" or rule.get("parent_tier") != "xhard4" \
                or not isinstance(rule.get("whitelist_sha256"), str):
            raise SpecsError(f"layout_rule 形态不符：{rule}")
    if header["sampling_config_sha256"] != digest(header["sampling_config"]):
        raise SpecsError("内嵌 sampling_config 散列不自洽")
    per_cell = int(header["delivery_per_cell"])
    seen, selected_count = set(), {}
    for row in rows:
        _exact_keys(row, row_required, "specs 行")
        key = (row["task"], int(row["candidate"]))
        if schema == SCHEMA_V7:
            _check_layout_parent(row, tier, key)
        if row["record"] != "spec" or key in seen or row["task"] not in header["tasks"]:
            raise SpecsError(f"重复或额外的规格行：{key}")
        seen.add(key)
        if row["tier"] != tier:
            raise SpecsError(f"规格行档位与 header 不符：{key}")
        if row["spec_sha256"] != spec_sha256(row["spec"]):
            raise SpecsError(f"规格散列不符：{key}")
        if row["seed"] != seed_for(row["task"], row["episode"], row["attempt"], header["seed_rule"]):
            raise SpecsError(f"seed 与公式不符：{key}")
        for flag in ("selected", "tried", "initial_selected"):
            if type(row[flag]) is not bool:
                raise SpecsError(f"{flag} 必须是布尔：{key}")
        rollout = row["rollout"]
        if rollout is not None and rollout.get("status") not in ROLLOUT_STATUSES:
            raise SpecsError(f"rollout.status 非法：{key}")
        if row["selected"]:
            selected_count[row["task"]] = selected_count.get(row["task"], 0) + 1
    over = {task: n for task, n in selected_count.items() if n > per_cell}
    if over:
        raise SpecsError(f"每格 selected 行数超过 delivery_per_cell={per_cell}：{over}")
    if identity_sha256(header, rows) != header["identity_sha256"]:
        raise SpecsError("identity_sha256 不符（签或来源被改过）")
    if delivery_sha256(rows) != header["delivery_sha256"]:
        raise SpecsError("delivery_sha256 不符（正式交付集合被改过）")


def load_specs(path: str | Path, *, check_fingerprint: bool = True):
    """唯一读取入口：返回 ``(header, rows)``（rows 为全部规格行，调用方按 ``delivered`` 取正式局）。

    源码指纹（``provenance``）与当前环境不符只 ``warnings.warn``，不拒绝（0927 计划 §3.4）。
    """
    records = read_jsonl(path)
    header, rows = records[0], records[1:]
    validate_specs(header, rows)
    if check_fingerprint:
        provenance = header.get("provenance") or {}
        try:
            current = {"hard_fingerprint": hard_fingerprint(), "base_fingerprint": base_fingerprint()}
        except Exception as exc:  # noqa: BLE001 指纹只作佐证
            warnings.warn(f"无法计算源码指纹：{exc}")
            current = {}
        for key, value in current.items():
            if provenance.get(key) not in (None, value):
                warnings.warn(f"{path}：{key} 与当前源码不符（只警告，不拒绝）")
    return copy.deepcopy(header), copy.deepcopy(rows)


#: 规格根覆盖（0928 方案第二部分 §1.1）：设了即从该目录读 xhard{1..4}/specs.jsonl，缺省读包内
SPECS_ROOT_ENV = "ROBOMME_HARD_SPECS_ROOT"
PACKAGED_SPECS_ROOT = Path(__file__).resolve().parents[1] / "env_metadata" / "test-hard"
_ANNOUNCED_ROOTS: set[str] = set()


def specs_root(override: str | Path | None = None) -> Path:
    """规格根：显式参数 > 环境变量 ``ROBOMME_HARD_SPECS_ROOT`` > 包内。非包内时打印一次 ``SPECS_ROOT=``。"""
    import os

    chosen = override if override is not None else os.environ.get(SPECS_ROOT_ENV)
    root = Path(chosen).resolve() if chosen else PACKAGED_SPECS_ROOT
    if root != PACKAGED_SPECS_ROOT and str(root) not in _ANNOUNCED_ROOTS:
        _ANNOUNCED_ROOTS.add(str(root))
        print(f"SPECS_ROOT={root}", flush=True)
    return root


def packaged_specs_path(tier: str, root: str | Path | None = None) -> Path:
    if tier not in TIERS:
        raise SpecsError(f"未知档位 {tier!r}")
    return specs_root(root) / tier / "specs.jsonl"


# ── 回注绑定摘要（策略仓库唯一调用的函数；0927 计划 §4.2、R22）───────────────


def _max_abs_diff(a: Any, b: Any) -> float:
    """两棵值树的最大绝对差；结构或非数值不同返回 inf。"""
    if isinstance(a, bool) or isinstance(b, bool):
        return 0.0 if a == b else math.inf
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b))
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        if len(a) != len(b):
            return math.inf
        return max((_max_abs_diff(x, y) for x, y in zip(a, b)), default=0.0)
    if isinstance(a, dict) and isinstance(b, dict):
        if a.keys() != b.keys():
            return math.inf
        return max((_max_abs_diff(a[k], b[k]) for k in a), default=0.0)
    return 0.0 if a == b else math.inf


def spec_binding(env) -> dict[str, Any]:
    """读 ``env.unwrapped._spec``（``SpecRecorder``），返回回注绑定摘要；必须在 ``reset()`` 之后调用。

    - ``injected_mismatch``：回注点（``value()``，trace ``source="spec"``）上的不等条数，外加记录点差 > 1e-5 的条数；
    - ``recorded_drift``：只记录不回注的观测点（``record()``，trace ``source="record"``）上差 ≤ ``RECORDED_FLOAT_TOL`` 的条数；
    - ``unused``：规格里有、本局没被 ``value()``／``record()`` 访问的取值点数。
    """
    recorder = getattr(getattr(env, "unwrapped", env), "_spec", None)
    if recorder is None:
        return {"available": False}
    spec_paths = {item["path"] for item in recorder.trace if item.get("source") == "spec"}
    record_paths = {item["path"] for item in recorder.trace if item.get("source") == "record"}
    injected, drift, drift_max = 0, 0, 0.0
    for item in recorder.mismatches:
        path = item["path"]
        if path in record_paths and path not in spec_paths:
            diff = _max_abs_diff(item.get("drawn"), item.get("frozen"))
            if diff <= RECORDED_FLOAT_TOL:
                drift += 1
                drift_max = max(drift_max, diff)
                continue
        injected += 1
    consumed = set(recorder.consumed_paths())
    unused = [p for p in recorder.leaf_paths() if not any(p == c or p.startswith(c + ".") for c in consumed)]
    frozen = getattr(recorder, "_frozen", None)
    # V7 分层（§1.1）：layout_hit＝本局命中 L／N 的取值点数（回注时应等于规格 layout_paths_hit 的条数）；
    # layout_overridden＝其中注入值 ≠ 本档抽到值的条数（只报告）；layout_drift＝本档抽到值 ≠ layout_drawn 的条数（已计入 injected_mismatch）
    layered_hit = getattr(recorder, "_layered_hit", None)
    if layered_hit is not None:
        layout_hit = len({item["path"] for item in recorder.trace if item.get("path") in layered_hit})
    else:
        layout_hit = len(getattr(recorder, "layout_paths_hit", ()) or ())
    return {
        "available": True,
        "mode": recorder.mode,
        "spec_kind": recorder.spec_kind,
        "spec_sha256": spec_sha256(frozen) if recorder.mode == "replay" else None,
        "value_points": sum(1 for item in recorder.trace if item.get("source") in ("draw", "spec")),
        "injected_mismatch": injected,
        "recorded_drift": drift,
        "recorded_max_abs": drift_max,
        "unused": len(unused),
        "layered": bool(getattr(recorder, "layered", False)),
        "layout_hit": layout_hit,
        "layout_paths_expected": len(layered_hit) if layered_hit is not None else None,
        "layout_overridden": int(getattr(recorder, "layout_overridden", 0)),
        "layout_drift": int(getattr(recorder, "layout_drift", 0)),
    }
