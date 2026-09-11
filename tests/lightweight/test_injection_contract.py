"""注入取值域契约（`scripts/configs/newtask-v2/injection_contract_v1/v2.json`）的定向测试。

钉死四件事：v1 每个派生域等于 `native_sampling.json` 回算、v1 驱动的生成器对 04 冻结规格逐位相同、
v2 只改 BinFill 三处（两档区间 + 每目标色至少 1 块）且其余组逐位不变、事件表两列逐字取自契约。
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
for extra in (REPO_ROOT, REPO_ROOT / "src"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from scripts.injection import contract as contract_mod  # noqa: E402
from scripts.injection.contract import Contract, ContractError, audit_overrides, derive_all, load_contract, resolve_path  # noqa: E402
from scripts.injection.contract_build import BINFILL_HELDOUT_OVERRIDES, build_v1, build_v2  # noqa: E402
from scripts.injection.specs import CUBE_HALF_SIZE, GROUPS, MAX_CANDIDATES, build_group, canonical_json  # noqa: E402

CONFIG_DIR = REPO_ROOT / "scripts" / "configs" / "newtask-v2"
SAMPLING_PATH = CONFIG_DIR / "native_sampling.json"
SAMPLING = json.loads(SAMPLING_PATH.read_text(encoding="utf-8"))
V1 = load_contract(CONFIG_DIR / "injection_contract_v1.json")
V2 = load_contract(CONFIG_DIR / "injection_contract_v2.json")
FROZEN_04 = REPO_ROOT / "artifacts" / "injection" / "20260910-new-values-04" / "specs"
SEED = 20260909


def _hashes(contract: Contract, task: str, difficulty: str) -> list[str]:
    return [e["spec_sha256"] for e in build_group(task, difficulty, SAMPLING, contract, SEED).episodes]


# ── v1 = 原值派生 ───────────────────────────────────────────────────────────
def test_v1_契约的每个派生域都等于原值回算且无override():
    mismatches, checked = derive_all(V1, SAMPLING)
    assert mismatches == [] and checked > 100
    assert V1.overrides == []
    _, problems = audit_overrides(V1, SAMPLING)
    assert problems == []


def test_v1_契约文件与builder现场重建逐字节相同():
    """契约是机器派生物；手改文件会在这里露馅。"""
    rebuilt = build_v1(SAMPLING, SAMPLING_PATH)
    assert canonical_json(rebuilt) == canonical_json(V1.payload)


def test_代码常量与契约白名单同源():
    assert contract_mod.CONSTS["cube_half_size"] == CUBE_HALF_SIZE
    assert contract_mod.CONSTS["max_candidates"] == MAX_CANDIDATES
    assert contract_mod.canonical_json({"b": [1, 2], "a": 1.5}) == canonical_json({"b": [1, 2], "a": 1.5})


@pytest.mark.skipif(not FROZEN_04.is_dir(), reason="04 运行的冻结规格不在工作区")
@pytest.mark.parametrize(("task", "difficulty"), [g for g in GROUPS if g[0] in ("BinFill", "RouteStick")])
def test_v1_生成的规格散列与04冻结逐条相同(task, difficulty):
    """只比 BinFill + RouteStick 六组（无碰撞扫掠，守 5 分钟预算）；五个视频组由阶段 B 的全量对拍与 SPEC_REPRODUCIBLE 覆盖。"""
    frozen = json.loads((FROZEN_04 / task / f"{difficulty}.json").read_text(encoding="utf-8"))["episodes"]
    assert [e["spec_sha256"] for e in frozen] == _hashes(V1, task, difficulty)


# ── v2 = v1 + BinFill 三处 ──────────────────────────────────────────────────
def test_v2_的偏离项恰好是两条区间override加一条规则override():
    mismatches, _ = derive_all(V2, SAMPLING)
    assert {(m.group, m.field) for m in mismatches} == {(o["group"], o["field"]) for o in V2.overrides}
    assert len(V2.overrides) == 2 and V2.overrides == BINFILL_HELDOUT_OVERRIDES
    _, problems = audit_overrides(V2, SAMPLING)
    assert problems == []
    rule_override = V2.payload["target_count_rule_override"]
    assert rule_override["contract"] == {"rule": "each_target_at_least_one"}
    for difficulty in ("easy", "medium", "hard"):
        assert V2.group("BinFill", difficulty).rule("target_count") == "each_target_at_least_one"
        assert V1.group("BinFill", difficulty).rule("target_count") == "allow_zero"


def test_v2_契约文件与builder现场重建逐字节相同():
    assert canonical_json(build_v2(V1.payload)) == canonical_json(V2.payload)


def test_v2_只改BinFill两档区间与三档规则文案():
    changed: list[str] = []
    for gc1, gc2 in zip(V1.groups(), V2.groups()):
        for r1, r2 in zip(gc1.rows(), gc2.rows()):
            if r1 != r2:
                changed.append(f"{gc1.key}/{r1[1]}")
    assert changed == ["BinFill/easy/target_count", "BinFill/medium/spawn_total", "BinFill/medium/target_count", "BinFill/hard/spawn_total", "BinFill/hard/target_count"]
    assert V2.group("BinFill", "medium").values("spawn_total") == [6, 7, 8]
    assert V2.group("BinFill", "hard").values("spawn_total") == [8, 9, 10]
    assert V1.group("BinFill", "medium").values("spawn_total") == [8, 9, 10]


@pytest.mark.parametrize(("task", "difficulty"), [("RouteStick", "easy"), ("RouteStick", "medium"), ("RouteStick", "hard"), ("BinFill", "easy")])
def test_非BinFill组与BinFill_easy在两版契约下逐位相同(task, difficulty):
    """easy 恒为单色，规则不起作用，区间也没变，所以 100 条散列全同。"""
    assert _hashes(V1, task, difficulty) == _hashes(V2, task, difficulty)


@pytest.mark.parametrize("difficulty", ["medium", "hard"])
def test_v2_多目标色时每个目标色至少一块且总数落在区间内(difficulty):
    lo, hi = V2.group("BinFill", difficulty).values("spawn_total")[0], V2.group("BinFill", difficulty).values("spawn_total")[-1]
    group = build_group("BinFill", difficulty, SAMPLING, V2, SEED)
    counts = {}
    for record in group.episodes:
        objects = record["objects"]
        assert lo <= objects["spawn_total"] <= hi
        counts[objects["spawn_total"]] = counts.get(objects["spawn_total"], 0) + 1
        assert sum(objects["spawn_count"].values()) == objects["spawn_total"]
        assert sum(objects["target_count"].values()) == objects["put_in_total"]
        for color in objects["target_pool"]:
            assert objects["target_count"][color] >= 1, record["episode"]
    assert max(counts.values()) - min(counts.values()) <= 1
    # 反向：v1 规则下确有某目标色为 0 的条，证明规则真的换了
    v1 = build_group("BinFill", difficulty, SAMPLING, V1, SEED)
    assert any(r["objects"]["target_count"][c] == 0 for r in v1.episodes for c in r["objects"]["target_pool"])


def test_投入总数少于目标色数时报缺口():
    broken = copy.deepcopy(V2.payload)
    group = broken["groups"]["BinFill/hard"]
    put = next(f for f in group["事件"] if f["key"] == "put_in_total")
    put["domain"].update({"lo": 1, "hi": 2, "values": [1, 2]})
    del put["domain"]["derivation"]
    with pytest.raises(Exception, match="少于目标色数"):
        build_group("BinFill", "hard", SAMPLING, Contract(broken), SEED)


# ── 结构与白名单 ────────────────────────────────────────────────────────────
@pytest.mark.parametrize(("mutate", "message"), [
    (lambda d: d["groups"]["BinFill/easy"]["初始化"][0]["domain"].update({"kind": "gaussian"}), "gaussian"),
    (lambda d: d["groups"]["BinFill/easy"]["初始化"][0]["allocation"].update({"kind": "handwave"}), "handwave"),
    (lambda d: d["groups"]["BinFill/easy"]["事件"][3]["domain"].update({"rule": "whatever"}), "whatever"),
    (lambda d: d["groups"]["BinFill/easy"]["初始化"][2]["domain"].update({"values": [4, 5]}), "不自洽"),
    (lambda d: d["groups"]["BinFill/easy"]["初始化"][0].pop("domain_text"), "缺少"),
])
def test_未知类型与不自洽的契约被拒绝(mutate, message):
    broken = copy.deepcopy(V1.payload)
    mutate(broken)
    with pytest.raises(ContractError, match=message):
        Contract(broken)


def test_契约散列对键序不敏感对内容敏感():
    shuffled = json.loads(json.dumps(V1.payload, sort_keys=True))
    assert Contract(shuffled).sha256 == V1.sha256
    tweaked = copy.deepcopy(V1.payload)
    tweaked["groups"]["BinFill/easy"]["初始化"][6]["domain"]["components"]["button_x"]["lo"] -= 1e-9
    assert Contract(tweaked).sha256 != V1.sha256
    assert V1.sha256 != V2.sha256


def test_闭区间与半开区间的values自洽():
    for contract in (V1, V2):
        for gc in contract.groups():
            for key in gc.keys():
                domain = gc.field(key)["domain"]
                if domain["kind"] == "int_range" and domain.get("values") is not None:
                    assert domain["values"] == list(range(domain["lo"], domain["hi"] + 1))
                if domain["kind"] == "int_range_half_open":
                    assert domain["values"] == list(range(domain["lo"], domain["high_exclusive"]))
    assert V1.group("VideoRepick", "easy").values("num_repeats") == [1, 2, 3]


def test_依赖键全部能在原值里解析到():
    for gc in V1.groups():
        for key in gc.keys():
            domain = gc.field(key)["domain"]
            derivations = [domain["derivation"]] if "derivation" in domain else []
            if domain["kind"] == "continuous":
                derivations += [c["derivation"] for c in domain["components"].values() if "derivation" in c]
            for derivation in derivations:
                for spec in derivation["inputs"].values():
                    if isinstance(spec, str) and spec.startswith("const:"):
                        assert spec[len("const:"):] in contract_mod.CONSTS
                    elif isinstance(spec, str):
                        resolve_path(SAMPLING, spec)
                    else:
                        assert spec["recipe"] in contract_mod.RECIPES


def test_未登记的偏离与陈旧override都判问题():
    drifted = copy.deepcopy(V1.payload)
    drifted["groups"]["BinFill/easy"]["初始化"][2]["domain"].update({"lo": 3, "hi": 6, "values": [3, 4, 5, 6]})
    _, problems = audit_overrides(Contract(drifted), SAMPLING)
    assert problems and "未登记 override" in problems[0]
    stale = copy.deepcopy(V2.payload)
    stale["overrides"].append({"group": "BinFill/easy", "field": "spawn_total", "native": {"lo": 4, "hi": 6}, "contract": {"lo": 4, "hi": 6}, "source": "x", "reason": "x"})
    _, problems = audit_overrides(Contract(stale), SAMPLING)
    assert any("陈旧" in p for p in problems)


# ── 事件表两列取自契约 ──────────────────────────────────────────────────────
def _event_tables():
    import importlib.util

    path = REPO_ROOT / "scripts" / "injection-before-2d" / "event_tables.py"
    spec = importlib.util.spec_from_file_location("event_tables", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.mark.skipif(not FROZEN_04.is_dir(), reason="04 运行的冻结规格不在工作区")
def test_事件表的取值域与分配两列逐字取自契约且行序一致():
    et = _event_tables()
    assert not hasattr(et, "BIN_HALF") and not hasattr(et, "SECTION_OF")
    root = FROZEN_04.parent
    for task, difficulty in (("BinFill", "medium"), ("VideoUnmaskSwap", "medium"), ("RouteStick", "hard")):
        records = et.load_group(root, task, difficulty)
        text, rows = et.render_group_table(task, difficulty, records, SAMPLING, V1)
        gc = V1.group(task, difficulty)
        table_lines = [line for line in text.splitlines() if line.startswith("| `") or line.startswith("| 起点") or line.startswith("| 每段") or line.startswith("| 方块") or line.startswith("| 9 个") or line.startswith("| 前两") or line.startswith("| 第三") or line.startswith("| 后续")]
        assert len(table_lines) == rows == len(gc.rows())
        for line, (_section, key, label, domain_text, allocation_text) in zip(table_lines, gc.rows()):
            cells = [c.strip() for c in line.strip().strip("|").split(" | ")]
            assert cells[0] == label and cells[1] == domain_text and cells[2] == allocation_text, key
        computed_keys = [k for k, *_ in et.group_rows(task, difficulty, records, SAMPLING, V1)]
        assert sorted(computed_keys) == sorted(gc.keys())
