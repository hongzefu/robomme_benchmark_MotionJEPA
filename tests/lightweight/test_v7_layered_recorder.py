#!/usr/bin/env python3
"""轻量测试：``SpecRecorder`` 的 V7 派生（derive）与分层回注（layered replay）（0928 方案第二部分 §1.2、§7.3.2）。

用一份假的 xhard4 母规格（``native-newvalue/2``）与一张小白名单，不起环境、直接按取值点调用：

* derive：L 返回母值（``[:n]`` 按本档抽到的长度取母值前缀）、G 返回本档抽到的值、N 按 ``NEST_RULES`` 嵌套派生，
  未分类路径抛 ``EpisodeSpecError``；导出 ``native-layered/3``，带 ``layout_drawn``／``layout_paths_hit``；
* layered replay：同样的抽样 → ``layout_drift`` 0；L 点抽到值变了 → ``layout_drift`` 1 且记 mismatch；
  G 点变了是普通 mismatch；``hard_specs.spec_binding`` 的分层计数与之一致；
* derive 信封与分层规格的非法形态被拒。

    uv run --no-sync python -m pytest tests/lightweight/test_v7_layered_recorder.py -q
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests._shared.repo_paths import find_repo_root  # noqa: E402

REPO_ROOT = find_repo_root(__file__)
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from robomme_hard.env_record_wrapper import hard_specs  # noqa: E402
from robomme_hard.robomme_env.utils.episode_spec import (  # noqa: E402
    SPEC_KIND_LAYERED,
    SPEC_KIND_NEWVALUE,
    EpisodeSpecError,
    SpecRecorder,
    nest_binfill_targets,
)

TASK = "BinFill"
SEED = 14_400_300
IDENTITY = {"seed": SEED}
LAYOUT = {
    "L": ["layout.button_xy", "layout.cubes.*", "actions.path_nodes[:n]"],
    "G": ["objects.num_repeats"],
    "N": ["objects.target_numbers"],
}
#: 本档（xhard1）的抽样：与母档不同，才能看出 L／N 被改写
DRAWS = [
    ("layout.button_xy", [0.9, 0.9]),
    ("layout.cubes.red_0", [0.5, 0.5, 30.0]),
    ("layout.cubes.blue_0", [0.6, 0.6, 45.0]),
    ("actions.path_nodes", [7, 8, 9]),
    ("objects.target_numbers", [6, 0, 0]),
    ("objects.num_repeats", 5),
]
L_OR_N = [path for path, _ in DRAWS if path != "objects.num_repeats"]


def _parent():
    rec = SpecRecorder(None, TASK, IDENTITY, difficulty="xhard4")
    rec.value("layout.button_xy", [0.1, 0.2])
    rec.value("layout.cubes.red_0", [0.0, 0.1, 10.0])
    rec.value("layout.cubes.blue_0", [0.2, 0.1, 20.0])
    rec.value("actions.path_nodes", [1, 2, 3, 4, 5])
    rec.value("objects.target_numbers", [3, 3, 3])
    rec.value("objects.num_repeats", 9)
    doc = rec.to_dict()
    assert doc["spec_kind"] == SPEC_KIND_NEWVALUE
    return doc


def _envelope(parent=None, layout=None):
    return {"envelope": "derive", "parent": parent if parent is not None else _parent(),
            "layout": copy.deepcopy(layout if layout is not None else LAYOUT)}


def _derive():
    rec = SpecRecorder(_envelope(), TASK, dict(IDENTITY), difficulty="xhard1")
    used = {path: rec.value(path, copy.deepcopy(drawn)) for path, drawn in DRAWS}
    rec.record("layout.observed_height", 0.5)
    return rec, used


def _env(rec):
    return SimpleNamespace(unwrapped=SimpleNamespace(_spec=rec))


# ── derive ──────────────────────────────────────────────────────────────────
def test_derive按LGN取值():
    rec, used = _derive()
    assert rec.mode == "derive" and rec.layered and rec.newvalue and rec.spec_kind == SPEC_KIND_LAYERED
    assert used["layout.button_xy"] == [0.1, 0.2]                 # L：母值
    assert used["layout.cubes.red_0"] == [0.0, 0.1, 10.0]         # L（*）：母值
    assert used["layout.cubes.blue_0"] == [0.2, 0.1, 20.0]
    assert used["actions.path_nodes"] == [1, 2, 3]                # L（[:n]）：母值前 3 个
    assert used["objects.target_numbers"] == nest_binfill_targets([3, 3, 3], [6, 0, 0], seed=SEED, tier="xhard1")
    assert sum(used["objects.target_numbers"]) == 6               # N：嵌套派生，总数取本档
    assert used["objects.num_repeats"] == 5                       # G：本档抽到的值
    assert rec.layout_overridden == 5  # 五个 L／N 点的使用值都不等于本档抽到的值
    assert rec.mismatches == []


def test_derive导出分层规格():
    rec, used = _derive()
    doc = rec.to_dict()
    assert doc["spec_kind"] == SPEC_KIND_LAYERED and doc["task"] == TASK and doc["identity"] == IDENTITY
    assert doc["provenance"]["mode"] == "derive"
    assert doc["layout_paths_hit"] == sorted(L_OR_N)
    assert doc["layout_drawn"] == {path: drawn for path, drawn in DRAWS if path in L_OR_N}
    # 文档里存的是本局使用值（L／N 为母值或派生值，G 为抽到值），记录点照常记本档实际值
    assert doc["layout"]["button_xy"] == [0.1, 0.2]
    assert doc["actions"]["path_nodes"] == [1, 2, 3]
    assert doc["objects"]["target_numbers"] == used["objects.target_numbers"]
    assert doc["objects"]["num_repeats"] == 5
    assert doc["layout"]["observed_height"] == 0.5


def test_derive未分类路径抛错():
    rec = SpecRecorder(_envelope(), TASK, dict(IDENTITY), difficulty="xhard2")
    with pytest.raises(EpisodeSpecError, match="命中 0 个模式"):
        rec.value("objects.never_listed", 1)


def test_derive前缀比母值长即拒绝():
    rec = SpecRecorder(_envelope(), TASK, dict(IDENTITY), difficulty="xhard3")
    with pytest.raises(EpisodeSpecError, match="前缀"):
        rec.value("actions.path_nodes", [1, 2, 3, 4, 5, 6])


def test_derive信封非法形态被拒():
    parent = _parent()
    with pytest.raises(EpisodeSpecError, match="新值族"):
        SpecRecorder(_envelope(parent), TASK, dict(IDENTITY), difficulty="hard")
    wrong_kind = {**parent, "spec_kind": "native-parity/1"}
    with pytest.raises(EpisodeSpecError, match="native-newvalue/2"):
        SpecRecorder(_envelope(wrong_kind), TASK, dict(IDENTITY), difficulty="xhard1")
    with pytest.raises(EpisodeSpecError):
        SpecRecorder(_envelope({**parent, "task": "PickXtimes"}), TASK, dict(IDENTITY), difficulty="xhard1")
    with pytest.raises(EpisodeSpecError, match="三表"):
        SpecRecorder(_envelope(parent, {**LAYOUT, "X": []}), TASK, dict(IDENTITY), difficulty="xhard1")


# ── layered replay ────────────────────────────────────────────────────────────
def _layered_doc():
    rec, _ = _derive()
    return rec.to_dict()


def _replay(doc, draws):
    rec = SpecRecorder(copy.deepcopy(doc), TASK, dict(IDENTITY), difficulty="xhard1")
    used = {path: rec.value(path, copy.deepcopy(drawn)) for path, drawn in draws}
    rec.record("layout.observed_height", 0.5)
    return rec, used


def test_分层回注同样抽样无漂移():
    doc = _layered_doc()
    rec, used = _replay(doc, DRAWS)
    assert rec.mode == "replay" and rec.layered and rec.spec_kind == SPEC_KIND_LAYERED and rec.newvalue
    assert rec.layout_drift == 0 and rec.mismatches == []
    # 使用值一律是冻结值
    assert used["layout.button_xy"] == [0.1, 0.2] and used["actions.path_nodes"] == [1, 2, 3]
    assert used["objects.num_repeats"] == 5
    binding = hard_specs.spec_binding(_env(rec))
    assert binding["available"] and binding["mode"] == "replay" and binding["spec_kind"] == SPEC_KIND_LAYERED
    assert binding["spec_sha256"] == hard_specs.spec_sha256(doc)
    assert binding["layered"] is True
    assert binding["layout_hit"] == binding["layout_paths_expected"] == len(L_OR_N)
    assert binding["layout_overridden"] == 5 and binding["layout_drift"] == 0
    assert binding["injected_mismatch"] == 0 and binding["unused"] == 0


def test_分层回注L点抽样变化记漂移():
    doc = _layered_doc()
    draws = [(p, [0.8, 0.8] if p == "layout.button_xy" else d) for p, d in DRAWS]
    rec, used = _replay(doc, draws)
    assert used["layout.button_xy"] == [0.1, 0.2]  # 仍用冻结值
    assert rec.layout_drift == 1
    assert len(rec.mismatches) == 1
    entry = rec.mismatches[0]
    assert entry["path"] == "layout.button_xy" and entry.get("layout_drift") is True
    binding = hard_specs.spec_binding(_env(rec))
    assert binding["layout_drift"] == 1 and binding["injected_mismatch"] == 1


def test_分层回注G点变化是普通不等():
    doc = _layered_doc()
    draws = [(p, 6 if p == "objects.num_repeats" else d) for p, d in DRAWS]
    rec, used = _replay(doc, draws)
    assert used["objects.num_repeats"] == 5
    assert rec.layout_drift == 0 and len(rec.mismatches) == 1
    assert rec.mismatches[0]["path"] == "objects.num_repeats" and not rec.mismatches[0].get("layout_drift")


def test_分层回注缺点时layout_hit少于期望():
    doc = _layered_doc()
    rec, _ = _replay(doc, [d for d in DRAWS if d[0] != "layout.cubes.blue_0"])
    binding = hard_specs.spec_binding(_env(rec))
    assert binding["layout_hit"] == len(L_OR_N) - 1 and binding["layout_paths_expected"] == len(L_OR_N)
    assert binding["unused"] == 1


def test_分层规格非法形态被拒():
    doc = _layered_doc()
    bad = copy.deepcopy(doc)
    bad["layout_paths_hit"] = bad["layout_paths_hit"][:-1]
    with pytest.raises(EpisodeSpecError, match="layout_drawn"):
        SpecRecorder(bad, TASK, dict(IDENTITY), difficulty="xhard1")
    # 原值难度不接受新值／分层规格（不许互喂）
    with pytest.raises(EpisodeSpecError):
        SpecRecorder(copy.deepcopy(doc), TASK, dict(IDENTITY), difficulty="hard")
    # V6 全量规格照旧可在新值难度回注，且不是分层
    rec = SpecRecorder(_parent(), TASK, dict(IDENTITY), difficulty="xhard4")
    assert rec.mode == "replay" and not rec.layered and rec.spec_kind == SPEC_KIND_NEWVALUE
    binding = hard_specs.spec_binding(_env(rec))
    assert binding["layered"] is False and binding["layout_paths_expected"] is None and binding["layout_drift"] == 0
