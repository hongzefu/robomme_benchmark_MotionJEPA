"""注入取值域约定（契约）JSON：加载、结构校验、取值访问与「按原值回算」。

契约文件（``scripts/configs/newtask-v2/injection_contract_v*.json``）只回答表格三列的问题：
**事件叫什么**（``label``）、**能取哪些值**（``domain`` / ``domain_text``）、**怎么铺满 100 条**
（``allocation`` / ``allocation_text``）。几何常量（按钮盒尺寸、孔板边长、锚点坐标、避让间距、
``region_half_size``）一律仍在 ``native_sampling.json`` 的 ``positions``，契约里不存权威副本。

由几何或难度字典算出来的取值域在契约里是**派生结果**：数值直接写进 ``domain``，同时带
``derivation``（``recipe`` 白名单函数名 + ``inputs`` 依赖键 + 人读 ``expr``），``derive_all``
每次拿 ``native_sampling.json`` 回算比对——契约不是第二个权威源，而是一份被持续核对的快照。
有意偏离原值的字段（如 v2 的 BinFill 三处）必须登记在顶层 ``overrides``，否则回算不一致判 FAIL。

依赖键三种写法：无前缀 = ``native_sampling.json`` 路径（``positions.BinFill.board.x_offset.subtract``，
支持 ``[i]`` 下标）；``const:名`` = 本包代码常量（``CONSTS`` 白名单）；嵌套字典
``{"recipe": ..., "inputs": {...}}`` = 一层嵌套 recipe。``expr`` 只给人看，不 eval。

本模块不依赖 ``tests/``，也不在顶层 import ``specs``（``specs`` 反过来 import 本模块）。
"""

from __future__ import annotations

import hashlib
import itertools
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

#: 契约格式版本；改变字段形状时递增。
CONTRACT_SCHEMA_VERSION = 1

DOMAIN_KINDS = frozenset(
    {"int_range", "int_range_half_open", "enum", "continuous", "permutations_of", "combinations", "derived", "coupled", "constant"}
)
ALLOCATION_KINDS = frozenset({"quota", "stratify", "balanced", "rng_ep", "derived", "constant"})
#: 离散域：``values`` 是生成器按顺序消费的机器值列表。
DISCRETE_KINDS = frozenset({"int_range", "int_range_half_open", "enum", "permutations_of", "combinations"})
FIELD_KEYS = ("key", "label", "domain", "domain_text", "allocation", "allocation_text")
SECTIONS = ("初始化", "事件")
#: BinFill ``target_count`` 的分配规则：原值允许某目标色为 0；heldout（2fa5660）每个目标色至少 1 块。
TARGET_COUNT_RULES = ("allow_zero", "each_target_at_least_one")

#: 生成器侧代码常量（``const:`` 前缀可引用的名字）。数值与 ``specs.py`` 同源，由测试锁定一致。
CONSTS: dict[str, Any] = {
    "cube_half_size": 0.02,  # PICK_CUBE_CONFIGS["panda"] 的 cube_half_size
    "max_candidates": 256,  # 与 object_generation.max_trials 同值
    "SPAWN_COLOR_ORDER": ["red", "blue", "green"],
    "INITIALIZE_COLOR_DEFS": ["blue", "red", "green"],
    "UNMASK_COLOR_ORDER": ["red", "green", "blue"],
    "REPICK_COLOR_ORDER": ["red", "blue", "green"],
}
#: 回算比对时连续量端点允许的绝对容差（IEEE754 同式重算应逐位相同，容差只兜浮点求和顺序）。
DERIVE_TOL = 1e-12


class ContractError(ValueError):
    """契约格式错误、白名单外取值、或与原值回算不一致。"""


def canonical_json(payload: Any) -> str:
    """固定 UTF-8、键排序、固定分隔符、禁止 NaN 的规范序列化（与 ``specs.canonical_json`` 同式）。"""
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _tuplize(value: Any) -> Any:
    """JSON 只有 list；生成器里 ``itertools`` 产出的是 tuple。递归把 list 转 tuple，让值可散列且与源码类型一致。"""
    if isinstance(value, list):
        return tuple(_tuplize(v) for v in value)
    return value


def _listize(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return [_listize(v) for v in value]
    return value


# ── 依赖键解析 ──────────────────────────────────────────────────────────────
def resolve_path(sampling: dict[str, Any], path: str) -> Any:
    """解析 ``a.b[0].c`` 形式的路径；找不到抛 ``ContractError``。"""
    node: Any = sampling
    for token in path.split("."):
        name, *indices = token.replace("]", "").split("[")
        if not isinstance(node, dict) or name not in node:
            raise ContractError(f"依赖键 {path!r} 在原值配置里不存在（卡在 {name!r}）")
        node = node[name]
        for index in indices:
            if not isinstance(node, (list, tuple)):
                raise ContractError(f"依赖键 {path!r} 的 [{index}] 作用在非数组上")
            node = node[int(index)]
    return node


def resolve_input(sampling: dict[str, Any], spec: Any) -> Any:
    if isinstance(spec, dict) and "recipe" in spec:
        return run_recipe(sampling, spec["recipe"], spec.get("inputs", {}))
    if isinstance(spec, str) and spec.startswith("const:"):
        name = spec[len("const:"):]
        if name not in CONSTS:
            raise ContractError(f"未知的代码常量 const:{name}")
        return CONSTS[name]
    if isinstance(spec, str):
        return resolve_path(sampling, spec)
    raise ContractError(f"依赖键必须是路径字符串、const: 名或嵌套 recipe，收到 {spec!r}")


# ── recipe 白名单（纯函数，返回「要比对的字段」字典）────────────────────────
def _closed(lo: int, hi: int) -> dict[str, Any]:
    return {"lo": int(lo), "hi": int(hi), "values": list(range(int(lo), int(hi) + 1))}


def r_closed_int_range(pair: Sequence[int]) -> dict[str, Any]:
    return _closed(pair[0], pair[1])


def r_closed_int_range_from_bounds(lo: int, hi: int) -> dict[str, Any]:
    return _closed(lo, hi)


def r_half_open_int_range(low: int, high_exclusive: int) -> dict[str, Any]:
    return {"lo": int(low), "high_exclusive": int(high_exclusive), "values": list(range(int(low), int(high_exclusive)))}


def r_bool_pair(spec: dict[str, Any]) -> dict[str, Any]:
    if int(spec["low"]) != 0 or int(spec["high_exclusive"]) != 2:
        raise ContractError("bool_pair 只接受 randint(0, 2)")
    return {"values": [True, False]}


def r_enum_from_constant(pool: Sequence[Any]) -> dict[str, Any]:
    return {"values": list(pool)}


def r_range_of_n(n: int) -> dict[str, Any]:
    return {"values": list(range(int(n)))}


def r_combinations_of_color_pool(num_colors: int, pool: Sequence[str]) -> dict[str, Any]:
    combos = list(itertools.combinations(range(len(pool)), int(num_colors)))
    return {"values": [list(c) for c in combos], "value_labels": ["+".join(pool[i] for i in c) for c in combos]}


def r_permutations_of_constant(pool: Sequence[Any]) -> dict[str, Any]:
    return {"values": [list(p) for p in itertools.permutations(pool)]}


def r_permutations_of_range(n: int) -> dict[str, Any]:
    return {"values": [list(p) for p in itertools.permutations(range(int(n)))]}


def r_permutations_of_range_minus_one(n: int) -> dict[str, Any]:
    """VideoRepick 的 tail：除 target 外其余 n-1 块的全部排列（索引进 others）。"""
    return {"values": [list(p) for p in itertools.permutations(range(int(n) - 1))]}


def r_permutations_of_range_k(n: int, k: int) -> dict[str, Any]:
    return {"values": [list(p) for p in itertools.permutations(range(int(n)), int(k))]}


def r_clamped_color_counts(pair: Sequence[int], num_colors: int) -> dict[str, Any]:
    """源码先把 put_in_color 夹到 [1,3]，再夹到 [1, max(1, num_colors)]；去重后就是合法取值集合。"""
    counts = sorted({min(max(1, min(3, k)), max(1, int(num_colors))) for k in range(int(pair[0]), int(pair[1]) + 1)})
    return {"values": counts}


def r_node_values(node_indices: Sequence[int]) -> dict[str, Any]:
    return {"values": [int(v) for v in node_indices]}


def r_direction_pair(direction: dict[str, Any]) -> dict[str, Any]:
    return {"values": [direction["less_than"], direction["otherwise"]]}


def r_linear_adjacency_edges(node_indices: Sequence[int], neighbor_order: Sequence[int], backtrack: bool) -> dict[str, Any]:
    nodes = [int(v) for v in node_indices]
    universe = []
    for i in range(len(nodes)):
        for offset in neighbor_order:
            j = i + int(offset)
            if 0 <= j < len(nodes):
                universe.append([nodes[i], nodes[j]])
    return {"universe": universe, "backtrack": bool(backtrack)}


def r_layout_choice_by_bins(bins: int, order: Sequence[str]) -> dict[str, Any]:
    """bin=3 时布局在 region3_choice.order 里配额；否则恒为 region4。"""
    if int(bins) == 3:
        return {"values": list(order)}
    return {"value": "region4"}


def r_center_pm_half_range(center: float, span: float) -> dict[str, Any]:
    """``build_button``：``(torch.rand(2) - 0.5) * randomize_range`` → 中心 ± 范围/2。"""
    return {"lo": float(center) - float(span) / 2, "hi": float(center) + float(span) / 2}


def r_base_minus_subtract_span(base: float, subtract: float, scale: float) -> dict[str, Any]:
    return {"lo": float(base) - float(subtract), "hi": float(base) - float(subtract) + float(scale)}


def r_subtract_span(subtract: float, scale: float) -> dict[str, Any]:
    return {"lo": -float(subtract), "hi": -float(subtract) + float(scale)}


def r_zero_to(scale: float) -> dict[str, Any]:
    return {"lo": 0.0, "hi": float(scale)}


def r_pair(pair: Sequence[float]) -> dict[str, Any]:
    return {"lo": float(pair[0]), "hi": float(pair[1])}


def r_region_inset(center: float, half: float, inset: float) -> dict[str, Any]:
    return {"lo": float(center) - float(half) + float(inset), "hi": float(center) + float(half) - float(inset)}


def r_offset_limit(region_half: float, object_half: float) -> dict[str, Any]:
    limit = float(region_half) - float(object_half)
    return {"lo": -limit, "hi": limit}


def r_bin_half_from_cube_half(cube_half: float) -> float:
    """``spawn_random_bin`` 的 bin_half_size：``(cube_half * 2.5 + 0.005) * 0.5``。"""
    return (float(cube_half) * 2.5 + 0.005) * 0.5


def r_unit_interval_half_open() -> dict[str, Any]:
    return {"lo": 0.0, "hi": 1.0}


def r_one_to_max_trials(max_trials: int) -> dict[str, Any]:
    return {"lo": 1, "hi": int(max_trials)}


RECIPES: dict[str, Callable[..., Any]] = {
    "closed_int_range": r_closed_int_range,
    "closed_int_range_from_bounds": r_closed_int_range_from_bounds,
    "half_open_int_range": r_half_open_int_range,
    "bool_pair": r_bool_pair,
    "enum_from_constant": r_enum_from_constant,
    "range_of_n": r_range_of_n,
    "combinations_of_color_pool": r_combinations_of_color_pool,
    "permutations_of_constant": r_permutations_of_constant,
    "permutations_of_range": r_permutations_of_range,
    "permutations_of_range_k": r_permutations_of_range_k,
    "permutations_of_range_minus_one": r_permutations_of_range_minus_one,
    "clamped_color_counts": r_clamped_color_counts,
    "node_values": r_node_values,
    "direction_pair": r_direction_pair,
    "linear_adjacency_edges": r_linear_adjacency_edges,
    "layout_choice_by_bins": r_layout_choice_by_bins,
    "center_pm_half_range": r_center_pm_half_range,
    "base_minus_subtract_span": r_base_minus_subtract_span,
    "subtract_span": r_subtract_span,
    "zero_to": r_zero_to,
    "pair": r_pair,
    "region_inset": r_region_inset,
    "offset_limit": r_offset_limit,
    "bin_half_from_cube_half": r_bin_half_from_cube_half,
    "unit_interval_half_open": r_unit_interval_half_open,
    "one_to_max_trials": r_one_to_max_trials,
}


def run_recipe(sampling: dict[str, Any], recipe: str, inputs: dict[str, Any]) -> Any:
    if recipe not in RECIPES:
        raise ContractError(f"未知的派生 recipe {recipe!r}")
    kwargs = {name: resolve_input(sampling, spec) for name, spec in inputs.items()}
    return RECIPES[recipe](**kwargs)


# ── 契约对象 ────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Mismatch:
    group: str
    field: str
    component: str | None
    attribute: str
    contract_value: Any
    native_value: Any

    def as_dict(self) -> dict[str, Any]:
        return {
            "group": self.group, "field": self.field, "component": self.component, "attribute": self.attribute,
            "contract": self.contract_value, "native": self.native_value,
        }


class GroupContract:
    """一组（任务／难度）的字段表；``fields`` 按「初始化 → 事件」的渲染顺序排列。"""

    def __init__(self, group_key: str, payload: dict[str, Any]) -> None:
        self.key = group_key
        self.task = payload["task"]
        self.difficulty = payload["difficulty"]
        self.sections: dict[str, list[dict[str, Any]]] = {section: list(payload.get(section, [])) for section in SECTIONS}
        self._by_key: dict[str, tuple[str, dict[str, Any]]] = {}
        for section in SECTIONS:
            for field in self.sections[section]:
                if field["key"] in self._by_key:
                    raise ContractError(f"{group_key}: 字段 {field['key']!r} 重复")
                self._by_key[field["key"]] = (section, field)

    def field(self, key: str) -> dict[str, Any]:
        if key not in self._by_key:
            raise ContractError(f"{self.key}: 契约里没有字段 {key!r}")
        return self._by_key[key][1]

    def keys(self) -> list[str]:
        return list(self._by_key)

    def rows(self) -> list[tuple[str, str, str, str, str]]:
        """``(节, key, label, 取值域文案, 分配文案)``，顺序即事件表行序。"""
        return [
            (section, f["key"], f["label"], f["domain_text"], f["allocation_text"])
            for section in SECTIONS
            for f in self.sections[section]
        ]

    def values(self, key: str) -> list[Any]:
        """离散域按生成器消费顺序展开的机器值（内层 list 转 tuple，与 ``itertools`` 产物同型）。"""
        domain = self.field(key)["domain"]
        if domain["kind"] not in DISCRETE_KINDS or domain.get("values") is None:
            raise ContractError(f"{self.key}: 字段 {key!r} 不是可铺配额的离散域（kind={domain['kind']}）")
        return [_tuplize(v) for v in domain["values"]]

    def constant(self, key: str) -> Any:
        domain = self.field(key)["domain"]
        if domain["kind"] != "constant":
            raise ContractError(f"{self.key}: 字段 {key!r} 不是常量域")
        return _tuplize(domain["value"])

    def allocation(self, key: str) -> str:
        return self.field(key)["allocation"]["kind"]

    def rule(self, key: str) -> str:
        domain = self.field(key)["domain"]
        if "rule" not in domain:
            raise ContractError(f"{self.key}: 字段 {key!r} 没有 rule")
        return str(domain["rule"])

    def bounds(self, component: str) -> tuple[float, float]:
        """连续域分量的 ``(lo, hi)``，扫描本组全部 ``continuous`` 字段的 ``components``。"""
        for _section, field in self._by_key.values():
            domain = field["domain"]
            if domain["kind"] == "continuous" and component in domain["components"]:
                item = domain["components"][component]
                return float(item["lo"]), float(item["hi"])
        raise ContractError(f"{self.key}: 契约里没有连续分量 {component!r}")


class Contract:
    def __init__(self, payload: dict[str, Any], path: Path | None = None) -> None:
        self.payload = payload
        self.path = path
        _validate_contract(payload)
        self.version: str = payload["contract_version"]
        self.generator_seed: int = int(payload["generator_seed"])
        self.group_size: int = int(payload["group_size"])
        self.overrides: list[dict[str, Any]] = list(payload.get("overrides", []))
        self._groups = {key: GroupContract(key, value) for key, value in payload["groups"].items()}

    @property
    def sha256(self) -> str:
        """规范 JSON 散列，与文件字节（缩进、键序）无关。"""
        return hashlib.sha256(canonical_json(self.payload).encode("utf-8")).hexdigest()

    def group(self, task: str, difficulty: str) -> GroupContract:
        key = f"{task}/{difficulty}"
        if key not in self._groups:
            raise ContractError(f"契约里没有组 {key}")
        return self._groups[key]

    def groups(self) -> list[GroupContract]:
        return list(self._groups.values())


def load_contract(path: str | Path) -> Contract:
    target = Path(path)
    if not target.is_file():
        raise ContractError(f"契约文件不存在：{target}")
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ContractError(f"{target}: JSON 无法解析：{exc}") from exc
    return Contract(payload, target)


# ── 结构校验 ────────────────────────────────────────────────────────────────
def _validate_contract(payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        raise ContractError("契约顶层必须是对象")
    for key in ("contract_schema_version", "contract_version", "generator_seed", "group_size", "groups"):
        if key not in payload:
            raise ContractError(f"契约缺少顶层字段 {key!r}")
    if payload["contract_schema_version"] != CONTRACT_SCHEMA_VERSION:
        raise ContractError(f"contract_schema_version 必须为 {CONTRACT_SCHEMA_VERSION}")
    if not isinstance(payload["groups"], dict) or not payload["groups"]:
        raise ContractError("groups 必须是非空对象")
    for group_key, group in payload["groups"].items():
        if f"{group.get('task')}/{group.get('difficulty')}" != group_key:
            raise ContractError(f"组键 {group_key} 与 task/difficulty 不符")
        for section in SECTIONS:
            for field in group.get(section, []):
                _validate_field(group_key, field)
    for item in payload.get("overrides", []):
        for key in ("group", "field", "native", "contract", "source", "reason"):
            if key not in item:
                raise ContractError(f"override 缺少 {key!r}：{item}")


def _validate_field(group_key: str, field: dict[str, Any]) -> None:
    missing = [k for k in FIELD_KEYS if k not in field]
    if missing:
        raise ContractError(f"{group_key}: 字段缺少 {missing}：{field.get('key')!r}")
    tag = f"{group_key}/{field['key']}"
    domain, allocation = field["domain"], field["allocation"]
    if domain.get("kind") not in DOMAIN_KINDS:
        raise ContractError(f"{tag}: 未知的 domain.kind {domain.get('kind')!r}")
    if allocation.get("kind") not in ALLOCATION_KINDS:
        raise ContractError(f"{tag}: 未知的 allocation.kind {allocation.get('kind')!r}")
    kind = domain["kind"]
    if kind == "int_range":
        if domain.get("closed") is not True:
            raise ContractError(f"{tag}: int_range 必须显式 closed: true")
        expected = list(range(int(domain["lo"]), int(domain["hi"]) + 1))
        if domain.get("values") is not None and list(domain["values"]) != expected:
            raise ContractError(f"{tag}: values 与闭区间 [{domain['lo']}, {domain['hi']}] 不自洽")
    elif kind == "int_range_half_open":
        expected = list(range(int(domain["lo"]), int(domain["high_exclusive"])))
        if list(domain.get("values", [])) != expected:
            raise ContractError(f"{tag}: values 与半开区间 [{domain['lo']}, {domain['high_exclusive']}) 不自洽")
    elif kind in ("enum", "permutations_of", "combinations"):
        if not isinstance(domain.get("values"), list) or not domain["values"]:
            raise ContractError(f"{tag}: {kind} 必须给非空 values")
    elif kind == "continuous":
        components = domain.get("components")
        if not isinstance(components, dict) or not components:
            raise ContractError(f"{tag}: continuous 必须给 components")
        for name, item in components.items():
            for k in ("lo", "hi"):
                if not isinstance(item.get(k), (int, float)) or not math.isfinite(item[k]):
                    raise ContractError(f"{tag}/{name}: {k} 必须是有限数")
            if item["lo"] > item["hi"]:
                raise ContractError(f"{tag}/{name}: lo > hi")
    elif kind == "constant":
        if "value" not in domain:
            raise ContractError(f"{tag}: constant 必须给 value")
    elif kind == "coupled":
        if "depends_on" not in domain:
            raise ContractError(f"{tag}: coupled 必须给 depends_on")
        if "rule" in domain and domain["rule"] not in TARGET_COUNT_RULES:
            raise ContractError(f"{tag}: 未知的 rule {domain['rule']!r}")
    if kind in DISCRETE_KINDS and allocation["kind"] == "constant":
        raise ContractError(f"{tag}: 离散域不能用 constant 分配")


# ── 回算 ────────────────────────────────────────────────────────────────────
def _compare(group: str, field: str, component: str | None, contract_side: dict[str, Any], native_side: dict[str, Any]) -> list[Mismatch]:
    out: list[Mismatch] = []
    for attribute, native_value in native_side.items():
        if attribute not in contract_side:
            out.append(Mismatch(group, field, component, attribute, None, native_value))
            continue
        contract_value = contract_side[attribute]
        if isinstance(native_value, float) or isinstance(contract_value, float):
            same = abs(float(native_value) - float(contract_value)) <= DERIVE_TOL
        else:
            same = _listize(contract_value) == _listize(native_value)
        if not same:
            out.append(Mismatch(group, field, component, attribute, contract_value, native_value))
    return out


def derive_all(contract: Contract, sampling: dict[str, Any]) -> tuple[list[Mismatch], int]:
    """逐字段回算，返回 ``(不一致清单, 参与回算的字段/分量数)``。没有 ``derivation`` 的字段跳过。"""
    mismatches: list[Mismatch] = []
    checked = 0
    for gc in contract.groups():
        for _section, field in gc._by_key.values():
            domain = field["domain"]
            if domain["kind"] == "continuous":
                for name, item in domain["components"].items():
                    if "derivation" not in item:
                        continue
                    checked += 1
                    native = run_recipe(sampling, item["derivation"]["recipe"], item["derivation"].get("inputs", {}))
                    mismatches += _compare(gc.key, field["key"], name, item, native)
            elif "derivation" in domain:
                checked += 1
                native = run_recipe(sampling, domain["derivation"]["recipe"], domain["derivation"].get("inputs", {}))
                mismatches += _compare(gc.key, field["key"], None, domain, native)
    return mismatches, checked


def audit_overrides(contract: Contract, sampling: dict[str, Any]) -> tuple[list[Mismatch], list[str]]:
    """回算不一致集合必须恰好被 ``overrides`` 覆盖：未登记的不一致、登记了却其实一致的都算问题。"""
    mismatches, _checked = derive_all(contract, sampling)
    declared = {(item["group"], item["field"]) for item in contract.overrides}
    problems: list[str] = []
    seen: set[tuple[str, str]] = set()
    for item in mismatches:
        seen.add((item.group, item.field))
        if (item.group, item.field) not in declared:
            problems.append(f"{item.group}/{item.field}[{item.component or '-'}.{item.attribute}]: 契约 {item.contract_value!r} ≠ 原值回算 {item.native_value!r}，且未登记 override")
    for item in contract.overrides:
        key = (item["group"], item["field"])
        if key not in seen:
            problems.append(f"{item['group']}/{item['field']}: 登记了 override 但回算与契约一致（陈旧 override）")
        # override 记录的 native 值必须等于当场回算值
        actual = {(m.component, m.attribute): m.native_value for m in mismatches if (m.group, m.field) == key}
        for attribute, expected in item["native"].items():
            got = next((v for (comp, attr), v in actual.items() if attr == attribute), None)
            if got is not None and _listize(got) != _listize(expected):
                problems.append(f"{item['group']}/{item['field']}: override 记录的原值 {attribute}={expected!r} 与当场回算 {got!r} 不符")
    return mismatches, problems
