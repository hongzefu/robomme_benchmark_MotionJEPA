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
#: V8（v8 方案第二部分 §2.2 第 2 条，R6）：/4 在 /3 的基础上多 header ``exec_cap``，且 ``delivery_per_cell``、
#: ``select_rule``、``per_env`` 改为逐任务字典；签覆盖范围变了所以升 schema。/2、/3 的校验路径逐字不动。
SCHEMA_V8 = "hard-specs/4"
SCHEMAS = (SCHEMA, SCHEMA_V7, SCHEMA_V8)
#: 新值档（不含 xhard0）。v8 阶段 3b 换包起为五档 xhard1～xhard5，与 ``V8_TIERS`` 相同（下方断言）；
#: v7 四档另由冻结常量 ``V7_TIERS`` 保存（R10）。EXPECTED_CELLS、packaged_specs_path、builder 等依赖它。
TIERS = ("xhard1", "xhard2", "xhard3", "xhard4", "xhard5")
#: builder 档序：xhard0（官方 test 的 hard 子集，原生分支、不回注）在最前，其后新值五档（共六项）。
XHARD0 = "xhard0"
BUILDER_TIERS = (XHARD0, *TIERS)
#: xhard0 每任务 12 局＝官方 test 元数据 difficulty=="hard" 的原 episode 3,7,…,47（只作核对值，筛选按 difficulty）
XHARD0_PER_TASK = 12
XHARD0_EPISODES = tuple(range(3, 48, 4))
#: 历史 V4/V5 单档名（seed 规则 v5 只对它合法），保留以便核对旧快照。
DIFFICULTY = "xhard"
#: 评估步数上限按档（只约束执行段，演示段不计）。xhard0 取 1300，与官方 scripts/evaluation.py 的默认步数相同（v7 方案 §7.4）。
#: v8 阶段 3b 起 xhard1～xhard5 一律 1600（＝``V8_EXEC_CAP``，下方断言；v8 方案第一部分表 1 末行）：抽样时已过滤
#: 执行步超过 1600 的候选并递补，交付集按构造不超。历史值：v7 为 1500／2400／2900／3800（B4 上调，
#: 判定行 V7_STEP_HEADROOM 见 docs/validation/newtask-v7/），v6 为 1500／1700／2000／2600。
TIER_MAX_STEPS = {"xhard0": 1300, "xhard1": 1600, "xhard2": 1600, "xhard3": 1600, "xhard4": 1600, "xhard5": 1600}
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
#: V8 按档 seed 偏移（v8 方案第二部分 §2.2 第 3 条，R9）：各档布局独立抽，档与档 seed 两两不交。
#: 每档最大增量 16×100000 + 999×100 + 99 < 1.7e6，小于步长 2e6；最低 16e6 不碰 V5（4e6 起）、
#: 旧 V6 段（6e6～13.7e6）与 V7／探针段（14e6～15.7e6）。
V8_SEED_OFFSETS = {"xhard1": 16_000_000, "xhard2": 18_000_000, "xhard3": 20_000_000,
                   "xhard4": 22_000_000, "xhard5": 24_000_000}
#: 按档偏移的规则族：profile → {tier: offset}。V6（6e6～12e6）随 V6 删除已移除取值（v8 方案第二部分 §2.1b）；
#: v8 登记在此。按档偏移的规则族只认本族登记的档位（不先经全局 TIERS 拒绝，xhard5 在阶段 3b 前即可用）；
#: 新登记的偏移须与 V5（4e6）、旧 V6 段、V7（14e6）及已登记的族互不重叠。
TIER_SEED_OFFSETS: dict[str, dict[str, int]] = {"v8": V8_SEED_OFFSETS}
#: V7：四档同一 offset，同一候选号在四档里 seed 相同（母布局共用）；与 V5（4e6）、V6 历史段（6e6～12e6）互不重叠
V7_SEED_OFFSET = 14_000_000
SEED_PROFILES = ("v5", "v7", *TIER_SEED_OFFSETS)
MAX_ATTEMPTS = 100
#: 16 任务规范序（与 scripts/injection-dev/seed_layout.py::ALL_TASKS 逐字相同；src 不反向依赖 scripts）
ALL_TASKS = (
    "PickXtimes", "StopCube", "SwingXtimes", "BinFill", "VideoUnmaskSwap", "VideoUnmask",
    "ButtonUnmaskSwap", "ButtonUnmask", "VideoRepick", "VideoPlaceButton", "VideoPlaceOrder",
    "PickHighlight", "InsertPeg", "MoveCube", "PatternLock", "RouteStick",
)
#: 只在 xhard4 交付的任务（v8 阶段 3b 起：StopCube 拆成五档定值后离开，只剩 InsertPeg、MoveCube）
XHARD4_ONLY = ("InsertPeg", "MoveCube")
#: V7 冻结常量（v8 方案阶段 1）：v7 四档与 xhard4 独有任务的取值钉死在这里，load_specs_v7 与 v7 夹具只读它们；
#: 阶段 3b 把 TIERS／XHARD4_ONLY 切到 v8 后，v7 路径的行为不随之改变。
V7_TIERS = ("xhard1", "xhard2", "xhard3", "xhard4")
V7_XHARD4_ONLY = ("StopCube", "InsertPeg", "MoveCube")

# ── V8 常量（v8 方案阶段 2 新增；阶段 3b 起 TIERS／BUILDER_TIERS／EXPECTED_CELLS／TIER_MAX_STEPS 切到这里，R10）──
#: v8 新值五档（不含 xhard0）
V8_TIERS = ("xhard1", "xhard2", "xhard3", "xhard4", "xhard5")
#: v8 抽样与交付的执行步上限：执行步（不含演示帧）> 1600 的候选记 exec_over_cap 并递补；/4 header ``exec_cap`` 必须等于它
V8_EXEC_CAP = 1600


def _v8_cells() -> dict[tuple[str, str], int]:
    """v8 方案第一部分表 2 的 43 个新值格：(task, tier) → 正式交付局数（不含 xhard0）。"""
    cells: dict[tuple[str, str], int] = {}
    for tier, n in zip(("xhard1", "xhard2", "xhard3"), (17, 17, 16)):
        cells[("PickXtimes", tier)] = n
    for task in ("SwingXtimes", "StopCube"):
        for tier in V8_TIERS:
            cells[(task, tier)] = 10
    for task in ("VideoUnmask", "ButtonUnmask"):
        for tier in ("xhard1", "xhard2", "xhard3", "xhard4"):
            cells[(task, tier)] = 20
    for task in ("BinFill", "VideoUnmaskSwap", "ButtonUnmaskSwap", "VideoPlaceButton", "VideoPlaceOrder",
                 "PickHighlight", "VideoRepick"):
        for tier in ("xhard1", "xhard2"):
            cells[(task, tier)] = 40
    for task in ("RouteStick", "PatternLock"):
        for tier, n in zip(("xhard1", "xhard2", "xhard3"), (27, 27, 26)):
            cells[(task, tier)] = n
    for task in ("MoveCube", "InsertPeg"):
        cells[(task, "xhard4")] = 20
    return cells


#: 43 格逐格表 {(task, tier): 局数}：完整根传给 load_specs_v8；冒烟／分片传各自的子表（v8 冻结常量，V9 起不再改）
V8_CELLS: dict[tuple[str, str], int] = _v8_cells()
assert len(V8_CELLS) == 43 and sum(V8_CELLS.values()) == 1070, "V8_CELLS 须为表 2 的 43 格、合计 1070"
assert all(task in ALL_TASKS and tier in V8_TIERS for task, tier in V8_CELLS), "V8_CELLS 含未知任务或档位"


def _v9_cells() -> dict[tuple[str, str], int]:
    """v9 方案第一部分表 2 的 43 个新值格（档集合与 V8 相同）：每任务 50 局，在该任务 V8 交付的档里平分，
    分不均时前面的档多 1 局（17／17／16、13／13／12／12），不含 xhard0。"""
    cells: dict[tuple[str, str], int] = {}
    for task in ("PickXtimes", "RouteStick", "PatternLock"):
        for tier, n in zip(("xhard1", "xhard2", "xhard3"), (17, 17, 16)):
            cells[(task, tier)] = n
    for task in ("SwingXtimes", "StopCube"):
        for tier in V8_TIERS:
            cells[(task, tier)] = 10
    for task in ("VideoUnmask", "ButtonUnmask"):
        for tier, n in zip(("xhard1", "xhard2", "xhard3", "xhard4"), (13, 13, 12, 12)):
            cells[(task, tier)] = n
    for task in ("BinFill", "VideoUnmaskSwap", "ButtonUnmaskSwap", "VideoPlaceButton", "VideoPlaceOrder",
                 "PickHighlight", "VideoRepick"):
        for tier in ("xhard1", "xhard2"):
            cells[(task, tier)] = 25
    for task in ("MoveCube", "InsertPeg"):
        cells[(task, "xhard4")] = 50
    return cells


#: v9 交付格表（v9 方案第一部分表 2）：43 格、合计 800、每任务 50；格集合与 V8_CELLS 相同，只有局数不同
V9_CELLS: dict[tuple[str, str], int] = _v9_cells()
V9_PER_TASK = 50
assert len(V9_CELLS) == 43 and sum(V9_CELLS.values()) == 800, "V9_CELLS 须为表 2 的 43 格、合计 800"
assert set(V9_CELLS) == set(V8_CELLS), "V9_CELLS 的格集合须与 V8_CELLS 相同（不交付的档仍不抽签、不生成）"
assert all(sum(n for (t, _), n in V9_CELLS.items() if t == task) == V9_PER_TASK for task in ALL_TASKS), \
    "V9_CELLS 每任务须恰为 50 局"
#: 交付格表 {(task, tier): 正式交付局数}（v8 阶段 3b 起即 V8_CELLS 的 43 格；builder 按它断言每格行数，
#: 表外格恰好 0 行、表内格恰好等于表值）。v7 的 55 格由 V7_TIERS／V7_XHARD4_ONLY 推出，不再进全局常量。
#: v9 阶段 1 只新增 V9_CELLS、不切这一行；切到 V9_CELLS 与换包（env_metadata/test-hard/ 换为 V9 规格）在
#: v9 阶段 3b 同一提交由主会话完成（v9 方案 R7），换包前包内规格一律是 V8，表与包始终一致。
EXPECTED_CELLS: dict[tuple[str, str], int] = V8_CELLS
#: 已登记的完整交付格表（按版本）。``resolve_cell_table`` 按顺序 EXPECTED_CELLS → V8 → V9 找第一张能覆盖
#: 给定子表的表，作为单文件配额上限（``_validate_specs_v8``）与 ``load_specs_v8`` 的格配额上限。
CELL_TABLES: dict[str, dict[tuple[str, str], int]] = {"v8": V8_CELLS, "v9": V9_CELLS}
assert TIERS == V8_TIERS, "阶段 3b 起全局 TIERS 须等于 V8_TIERS"
assert all(TIER_MAX_STEPS[tier] == V8_EXEC_CAP for tier in TIERS) and tuple(TIER_MAX_STEPS) == BUILDER_TIERS, \
    "TIER_MAX_STEPS 须为 xhard0 + 五档、五档均等于 V8_EXEC_CAP"


def xhard4_only_tasks(cells: dict[tuple[str, str], int]) -> set[str]:
    """格表里只在 xhard4 出现的任务集合（XHARD4_ONLY 对参数格表的核对口径）。"""
    return {task for task in ALL_TASKS if {t for name, t in cells if name == task} == {"xhard4"}}


assert all(xhard4_only_tasks(table) == set(XHARD4_ONLY) for table in (EXPECTED_CELLS, *CELL_TABLES.values())), \
    "XHARD4_ONLY 须恰为交付格表（EXPECTED_CELLS、V8_CELLS、V9_CELLS 各自）里只在 xhard4 出现的任务"


def _fits(cells: dict[tuple[str, str], int], table: dict[tuple[str, str], int]) -> bool:
    return all(key in table and _is_int(n) and n <= table[key] for key, n in cells.items())


def resolve_cell_table(cells: dict[tuple[str, str], int]) -> dict[tuple[str, str], int]:
    """给定（子）格表 → 用作配额上限的完整交付格表：按 ``EXPECTED_CELLS``、``V8_CELLS``、``V9_CELLS`` 的顺序取第一张
    「含全部格且逐格局数 ≤ 表值」的表；都不覆盖时返回 ``EXPECTED_CELLS``（由调用方的逐项核对报出具体哪格超）。

    这样 v8 子表（冒烟、分片、完整根）照旧落到 V8，阶段 3b 切换前 V9 子表（MoveCube／InsertPeg 50）也能落到 V9；
    显式传入格表时不经本函数。"""
    for table in (EXPECTED_CELLS, *CELL_TABLES.values()):
        if _fits(cells, table):
            return table
    return EXPECTED_CELLS


def header_cell_table(header: dict[str, Any]) -> dict[tuple[str, str], int] | None:
    """/4 header 自带的逐任务配额 → ``resolve_cell_table`` 取配额上限格表（供不知道格表的单文件读取方用，如
    ``_rollout`` 回写复核）；非 /4 或配额形态不对返回 None（交给 ``validate_specs`` 报具体错）。"""
    if not isinstance(header, dict) or header.get("schema") != SCHEMA_V8:
        return None
    quota = header.get("delivery_per_cell")
    if not isinstance(quota, dict):
        return None
    return resolve_cell_table({(task, header.get("difficulty")): n for task, n in quota.items()})

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
#: 身份键按 schema 分表（各 schema 的键表一经发布即冻结，已封存文件的 identity_sha256 逐字不变）；
#: /4 = /3 的键 + ``exec_cap`` + ``delivery_per_cell``（逐任务配额与执行步上限进签，改了不重签必失败）
IDENTITY_KEYS_BY_SCHEMA = {
    SCHEMA: (IDENTITY_HEADER_KEYS, IDENTITY_ROW_KEYS),
    SCHEMA_V7: (IDENTITY_HEADER_KEYS + ("layout_rule",), IDENTITY_ROW_KEYS + ("layout_parent",)),
    SCHEMA_V8: (IDENTITY_HEADER_KEYS + ("layout_rule", "exec_cap", "delivery_per_cell"),
                IDENTITY_ROW_KEYS + ("layout_parent",)),
}
#: /4 唯一合法的布局规则：各档布局独立抽，不派生
V8_LAYOUT_RULE = {"mode": "independent"}


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
    """按档位与规则族给出 seed 规则；v5 只覆盖历史 xhard 单档，v7 四档同 offset，
    TIER_SEED_OFFSETS 里登记的规则族（v8）按档偏移、只用本族登记的档位校验（v6 已删除）。"""
    if difficulty == DIFFICULTY and profile == "v5":
        return dict(SEED_RULE)
    if profile in TIER_SEED_OFFSETS:
        offsets = TIER_SEED_OFFSETS[profile]
        if difficulty not in offsets:
            raise SpecsError(f"seed 规则 {profile} 未登记档位 {difficulty!r}，只支持 {tuple(offsets)}")
        return {**SEED_RULE, "offset": offsets[difficulty]}
    # v7 规则族只认冻结的 V7_TIERS（阶段 3b 后全局 TIERS 含 xhard5，v7 行为不随之改变）
    if difficulty not in V7_TIERS:
        raise SpecsError(f"未知档位 {difficulty!r}，只支持 {V7_TIERS}")
    if profile == "v7":
        return {**SEED_RULE, "offset": V7_SEED_OFFSET}
    known = "／".join(("v7", *TIER_SEED_OFFSETS))
    raise SpecsError(f"{difficulty} 只支持 seed 规则 {known}（收到 {profile!r}）")


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
    out = {tier: load_specs(Path(root) / tier / "specs.jsonl", check_fingerprint=check_fingerprint)
           for tier in V7_TIERS}
    rules = {tier: out[tier][0]["seed_rule"] for tier in V7_TIERS}
    if len({canonical_json(r) for r in rules.values()}) != 1 \
            or any(out[t][0]["schema"] != SCHEMA_V7 for t in V7_TIERS):
        raise SpecsError("v7 规格根：四档 schema 须为 hard-specs/3 且 seed 规则相同")
    parents = {(row["task"], int(row["candidate"])): row for row in out["xhard4"][1]}
    for tier in V7_TIERS[:-1]:
        for row in out[tier][1]:
            key = (row["task"], int(row["candidate"]))
            mother = parents.get(key)
            if mother is None or mother["spec_sha256"] != row["layout_parent"]["spec_sha256"] \
                    or int(mother["seed"]) != int(row["seed"]):
                raise SpecsError(f"{tier} 派生行找不到对应的 xhard4 母布局或摘要／seed 不符：{key}")
    return out


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _validate_specs_v8(header: dict[str, Any], rows: list[dict[str, Any]],
                       expected_cells: dict[tuple[str, str], int] | None = None) -> None:
    """``hard-specs/4`` 单文件校验（v8 方案第二部分 §2.2 第 2 条）。``expected_cells`` 是作配额上限的完整交付格表，
    缺省 ``EXPECTED_CELLS``（v9 方案 §2.1：格表参数贯通 load_specs → validate_specs → 本函数）：

    * header：字段集合；``difficulty ∈ V8_TIERS``；runtime；``seed_rule == seed_rule_for(tier, "v8")``；
      ``exec_cap == V8_EXEC_CAP``；``layout_rule == {"mode": "independent"}``；``tasks`` 不重复且每个 (task, tier)
      都在格表里；``select_rule`` 为 ``{task: [不重复非负整数]}``、``per_env`` 为 ``{task: 候选数（非负整数）}``、
      ``delivery_per_cell`` 为 ``{task: 正整数}``，三者键集合都等于 ``tasks``；逐任务配额自洽：
      ``delivery_per_cell[task] ≤ 格表[(task, tier)]``、``len(select_rule[task]) == delivery_per_cell[task]``、
      ``per_env[task] ==`` 本文件该任务行数、``select_rule[task]`` 每个索引 ``< per_env[task]``；内嵌 sampling_config 散列自洽；
    * 行：字段集合；``layout_parent is None``、``spec.spec_kind == "native-newvalue/2"``；``candidate == episode`` 且
      ``0 ≤ episode < env_block // episode_stride``；档位、规格散列、seed 公式、布尔位、rollout.status；
      逐任务 selected 行数 ≤ ``delivery_per_cell[task]``；
    * 两个身份散列（签含 exec_cap、delivery_per_cell、seed_rule，改任一项不重签即失败）。
    """
    table = EXPECTED_CELLS if expected_cells is None else expected_cells
    _, _, header_required, row_required = _schema_keys(SCHEMA_V8)
    _exact_keys(header, header_required, "specs header", HEADER_OPTIONAL)
    if header["record"] != "header":
        raise SpecsError(f"specs 版本不符：{SCHEMA_V8}")
    tier = header["difficulty"]
    if tier not in V8_TIERS or header["runtime"] != RUNTIME:
        raise SpecsError(f"hard-specs/4 档位或 runtime 不符：{tier!r}")
    if header["seed_rule"] != seed_rule_for(tier, "v8"):
        raise SpecsError(f"hard-specs/4 只接受 v8 按档 seed 规则（{tier}）")
    if not _is_int(header["exec_cap"]) or header["exec_cap"] != V8_EXEC_CAP:
        raise SpecsError(f"hard-specs/4 的 exec_cap 必须为 {V8_EXEC_CAP}：{header['exec_cap']!r}")
    if header["layout_rule"] != V8_LAYOUT_RULE:
        raise SpecsError(f"hard-specs/4 的 layout_rule 必须为 {V8_LAYOUT_RULE}：{header['layout_rule']!r}")
    tasks = header["tasks"]
    if not isinstance(tasks, list) or len(set(tasks)) != len(tasks):
        raise SpecsError(f"hard-specs/4 的 tasks 必须是不重复列表：{tasks!r}")
    stray = [task for task in tasks if (task, tier) not in table]
    if stray:
        raise SpecsError(f"hard-specs/4 的任务不在 {tier} 交付格内：{stray}")
    for name in ("select_rule", "per_env", "delivery_per_cell"):
        value = header[name]
        if not isinstance(value, dict) or set(value) != set(tasks):
            raise SpecsError(f"hard-specs/4 的 {name} 必须是键集合等于 tasks 的逐任务字典：{value!r}")
    for task in tasks:
        indices = header["select_rule"][task]
        if not isinstance(indices, list) or not all(_is_int(i) and i >= 0 for i in indices) \
                or len(set(indices)) != len(indices):
            raise SpecsError(f"hard-specs/4 的 select_rule[{task}] 必须是不重复非负整数列表：{indices!r}")
        if not _is_int(header["per_env"][task]) or header["per_env"][task] < 0:
            raise SpecsError(f"hard-specs/4 的 per_env[{task}] 必须是非负整数：{header['per_env'][task]!r}")
        quota = header["delivery_per_cell"][task]
        if not _is_int(quota) or quota <= 0:
            raise SpecsError(f"hard-specs/4 的 delivery_per_cell[{task}] 必须是正整数：{quota!r}")
        if quota > table[(task, tier)]:
            raise SpecsError(f"hard-specs/4 的 delivery_per_cell[{task}]={quota} 超过表 2 格配额 "
                             f"{table[(task, tier)]}（{tier}）")
        if len(indices) != quota:
            raise SpecsError(f"hard-specs/4 的 select_rule[{task}] 长度 {len(indices)} ≠ delivery_per_cell {quota}")
        n_rows = sum(1 for row in rows if row.get("task") == task)
        if header["per_env"][task] != n_rows:
            raise SpecsError(f"hard-specs/4 的 per_env[{task}]={header['per_env'][task]} ≠ 本文件该任务行数 {n_rows}")
        if any(i >= header["per_env"][task] for i in indices):
            raise SpecsError(f"hard-specs/4 的 select_rule[{task}] 有索引越过 per_env={header['per_env'][task]}："
                             f"{indices!r}")
    if header["sampling_config_sha256"] != digest(header["sampling_config"]):
        raise SpecsError("内嵌 sampling_config 散列不自洽")
    max_episode = SEED_RULE["env_block"] // SEED_RULE["episode_stride"]
    seen, selected_count = set(), {}
    for row in rows:
        _exact_keys(row, row_required, "specs 行")
        key = (row["task"], int(row["candidate"]))
        if row["record"] != "spec" or key in seen or row["task"] not in tasks:
            raise SpecsError(f"重复或额外的规格行：{key}")
        seen.add(key)
        # /4 行 candidate 即抽签 episode（与 _freeze 写法一致），episode 不得越过 env_block，否则跨任务 seed 会撞段
        if not _is_int(row["episode"]) or not 0 <= row["episode"] < max_episode:
            raise SpecsError(f"hard-specs/4 行 episode 必须落在 [0, {max_episode})：{key} {row['episode']!r}")
        if row["candidate"] != row["episode"]:
            raise SpecsError(f"hard-specs/4 行 candidate 必须等于 episode：{key} {row['episode']!r}")
        if row["tier"] != tier:
            raise SpecsError(f"规格行档位与 header 不符：{key}")
        if row["layout_parent"] is not None or (row.get("spec") or {}).get("spec_kind") != "native-newvalue/2":
            raise SpecsError(f"hard-specs/4 行 layout_parent 必须为 null、规格为 native-newvalue/2：{key}")
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
    over = {task: n for task, n in selected_count.items() if n > header["delivery_per_cell"][task]}
    if over:
        raise SpecsError(f"逐任务 selected 行数超过 delivery_per_cell：{over}")
    if identity_sha256(header, rows) != header["identity_sha256"]:
        raise SpecsError("identity_sha256 不符（签或来源被改过）")
    if delivery_sha256(rows) != header["delivery_sha256"]:
        raise SpecsError("delivery_sha256 不符（正式交付集合被改过）")


def validate_specs(header: dict[str, Any], rows: list[dict[str, Any]], *,
                   expected_cells: dict[tuple[str, str], int] | None = None) -> None:
    """封套校验：字段集合、runtime、seed 规则、配置散列、逐行 seed 与规格散列、两个身份散列、每格正式局数上限。
    ``hard-specs/4`` 走独立分支 ``_validate_specs_v8``（``expected_cells`` 作配额上限，缺省 ``EXPECTED_CELLS``）；
    /2、/3 走下面的原路径（不看 ``expected_cells``）。"""
    schema = header.get("schema")
    if schema == SCHEMA_V8:
        _validate_specs_v8(header, rows, EXPECTED_CELLS if expected_cells is None else expected_cells)
        return
    _, _, header_required, row_required = _schema_keys(schema)
    _exact_keys(header, header_required, "specs header", HEADER_OPTIONAL)
    if header["record"] != "header":
        raise SpecsError(f"specs 版本不符：{schema}")
    tier = header["difficulty"]
    # /2、/3 只服务 v6／v7 四档：按冻结的 V7_TIERS 校验（阶段 3b 后全局 TIERS 含 xhard5，旧路径行为不变）
    if tier not in V7_TIERS or header["runtime"] != RUNTIME:
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


def load_specs(path: str | Path, *, expected_cells: dict[tuple[str, str], int] | None = None,
               check_fingerprint: bool = True):
    """唯一读取入口：返回 ``(header, rows)``（rows 为全部规格行，调用方按 ``delivered`` 取正式局）。

    ``expected_cells``：/4 文件的配额上限格表，缺省 ``EXPECTED_CELLS``（读 V9 文件而 EXPECTED_CELLS 尚未切换时
    显式传 ``V9_CELLS``）；/2、/3 文件不看它。
    源码指纹（``provenance``）与当前环境不符只 ``warnings.warn``，不拒绝（0927 计划 §3.4）。
    """
    records = read_jsonl(path)
    header, rows = records[0], records[1:]
    validate_specs(header, rows, expected_cells=expected_cells)
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


def load_specs_v8(root: str | Path, expected_cells: dict[tuple[str, str], int], *,
                  cell_table: dict[tuple[str, str], int] | None = None,
                  check_fingerprint: bool = True) -> dict[str, tuple[dict[str, Any], list[dict[str, Any]]]]:
    """读 v8／v9 规格根（``<root>/<tier>/specs.jsonl``，``hard-specs/4``），只校验调用方给定的格表。

    ``expected_cells``：``{(task, tier): 局数}``，键必须是完整交付格表键的子集、值为正整数（值可小于表值，
    如冒烟每格 1 局）。完整根传 ``V8_CELLS``／``V9_CELLS``、冒烟传冒烟表、分片传该片子集。
    ``cell_table``：作配额上限的完整交付格表；缺省按 ``resolve_cell_table(expected_cells)`` 取（EXPECTED_CELLS →
    V8 → V9 第一张能覆盖的表），并原样传给逐份 ``load_specs``。只读 ``expected_cells``
    涉及的档位文件（其他档的文件即使存在也不读），逐份走 ``load_specs``（/4 校验），另查：

    * 每份 ``schema == "hard-specs/4"``、``difficulty`` 等于目录档名；
    * 每份 header ``tasks`` 的集合等于 ``expected_cells`` 在该档的任务集合；
    * ``expected_cells[key] ≤ cell_table[key]``；
    * 每格 header ``delivery_per_cell[task]`` 等于 ``expected_cells`` 的值；
    * 每格 ``selected`` 行数等于 ``expected_cells`` 的值（相等，不是 ≤）。只数 ``selected``，不看 rollout 结果；
      正式交付（``delivered``：selected 且 rollout ok）的逐格核对由 ``hard_regression.py delivery-set`` 的
      ``V8_DELIVERY_SET`` 负责；
    * 同任务跨档 seed 两两不交（比全部规格行，不只 selected）。

    返回 ``{tier: (header, rows)}``，与 ``load_specs_v7`` 同形态：键只含涉及的档位、按 ``V8_TIERS`` 顺序；
    rows 为该档全部规格行（调用方按 ``selected`` 或 ``delivered`` 取）。任一不符抛 ``SpecsError``。
    """
    if not isinstance(expected_cells, dict) or not expected_cells:
        raise SpecsError("expected_cells 必须是非空 {(task, tier): 局数} 字典")
    table = resolve_cell_table(expected_cells) if cell_table is None else cell_table
    stray = sorted(key for key in expected_cells if key not in table)
    if stray:
        raise SpecsError(f"expected_cells 含交付格表（V8_CELLS／V9_CELLS）之外的格：{stray}")
    bad = {key: n for key, n in expected_cells.items() if not _is_int(n) or n <= 0}
    if bad:
        raise SpecsError(f"expected_cells 的局数必须是正整数：{bad}")
    over = {key: n for key, n in expected_cells.items() if n > table[key]}
    if over:
        raise SpecsError(f"expected_cells 的局数超过表 2 格配额：{over}")
    out: dict[str, tuple[dict[str, Any], list[dict[str, Any]]]] = {}
    for tier in V8_TIERS:
        want = {task for task, t in expected_cells if t == tier}
        if not want:
            continue
        path = Path(root) / tier / "specs.jsonl"
        if not path.is_file():
            raise SpecsError(f"v8 规格根缺少 {path}")
        header, rows = load_specs(path, expected_cells=table, check_fingerprint=check_fingerprint)
        if header["schema"] != SCHEMA_V8 or header["difficulty"] != tier:
            raise SpecsError(f"{path}：schema 须为 {SCHEMA_V8}、档位须为 {tier}"
                             f"（实为 {header['schema']}／{header['difficulty']}）")
        got_tasks = set(header["tasks"])
        if got_tasks != want:
            raise SpecsError(f"{tier} 任务集合不符：缺少 {sorted(want - got_tasks)}，多出 {sorted(got_tasks - want)}")
        for task in sorted(want):
            if header["delivery_per_cell"][task] != expected_cells[(task, tier)]:
                raise SpecsError(f"{task}/{tier} delivery_per_cell={header['delivery_per_cell'][task]} ≠ "
                                 f"期望 {expected_cells[(task, tier)]}")
            got = sum(1 for row in rows if row["task"] == task and row["selected"])
            if got != expected_cells[(task, tier)]:
                raise SpecsError(f"{task}/{tier} selected 行数 {got} ≠ 期望 {expected_cells[(task, tier)]}")
        out[tier] = (header, rows)
    seeds: dict[str, dict[str, set[int]]] = {}
    for tier, (_, rows) in out.items():
        for row in rows:
            seeds.setdefault(row["task"], {}).setdefault(tier, set()).add(int(row["seed"]))
    for task, by_tier in seeds.items():
        names = list(by_tier)
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                common = by_tier[a] & by_tier[b]
                if common:
                    raise SpecsError(f"{task} 在 {a} 与 {b} 的 seed 相交：{sorted(common)[:5]}")
    return out


#: 规格根覆盖（0928 方案第二部分 §1.1）：设了即从该目录读 xhard{1..5}/specs.jsonl（按 TIERS），缺省读包内
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
