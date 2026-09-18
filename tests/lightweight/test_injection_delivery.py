"""每 env 400 条 h5 的交付配置与交付清单的定向测试。

两类断言：

* **配置侧**：真实 ``delivery_400.json`` 与真实契约 v3 必须能加载且组序一致；手改出的
  不一致（run_episodes 与 margin 不符、每 env 合计不是 400、组名与契约对不上）必须**硬失败**，
  不能被静默修正——配置写错却照跑是最贵的错。
* **清单侧**：严格交付口径是「按 episode 升序取前 N 条通过」，中间夹着失败条时必须顺延，
  多出来的通过条降级为 spare 且仍保留 h5 路径。
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

from scripts.injection.candidates.contract import load_contract  # noqa: E402
from scripts.injection.candidates.config import DeliveryError, load_delivery_config
from scripts.injection.delivery import render_verdict_line
from scripts.injection.rollout.state import assign_roles, StateError, file_sha
from scripts.injection.rollout.report import report
from types import SimpleNamespace
from scripts.injection.rollout.run import OUTCOME_PASS  # noqa: E402
from scripts.injection.candidates.sampling import GROUP_SIZE  # noqa: E402

CONFIG_PATH = REPO_ROOT / "scripts" / "configs" / "newtask-v2" / "delivery_400.json"
CONTRACT_PATH = REPO_ROOT / "scripts" / "configs" / "newtask-v2" / "injection_contract_v3.json"
CONTRACT_V3 = load_contract(CONTRACT_PATH)


def _load_real():
    return load_delivery_config(CONFIG_PATH, CONTRACT_V3)


def _write_variant(tmp_path: Path, mutate) -> Path:
    """复制真实配置、就地改一处，再落到 tmp_path 供加载。"""
    payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    mutate(payload)
    target = tmp_path / "delivery_variant.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


# ── 配置 ────────────────────────────────────────────────────────────────────
def test_每个env目标合计四百且难度计数差不超过一():
    config = _load_real()
    assert config.per_env_target == 400
    assert config.extra_candidates == 50
    assert len(config.groups) == 14
    # 与契约 v3 同序同名
    assert [g.key for g in config.groups] == [(g.task, g.difficulty) for g in CONTRACT_V3.groups()]
    assert config.contract_sha256 == CONTRACT_V3.sha256
    by_env = config.by_env()
    assert set(by_env) == {"BinFill", "RouteStick", "VideoUnmaskSwap", "VideoRepick"}
    for task, items in by_env.items():
        targets = [item.target_h5 for item in items]
        assert sum(targets) == 400, task
        assert max(targets) - min(targets) <= 1, task
    assert [g.target_h5 for g in by_env["BinFill"]] == [134, 133, 133]
    assert [g.target_h5 for g in by_env["RouteStick"]] == [100, 100, 100, 100]


def test_实跑条数等于目标乘余量向上取整():
    config = _load_real()
    seen = {(g.target_h5, g.run_episodes) for g in config.groups}
    assert seen == {(134, 155), (133, 153), (100, 115)}
    # episodes_by_group 就是 range(run_episodes)
    episodes = config.episodes_by_group([("BinFill", "easy"), ("RouteStick", "xhard")])
    assert episodes[("BinFill", "easy")] == list(range(155))
    assert episodes[("RouteStick", "xhard")] == list(range(115))
    group = config.group("BinFill", "easy")
    assert group.env_check_start == 155
    assert list(group.run_range) == list(range(155))


def test_block数足够容纳实跑加额外候选():
    config = _load_real()
    for group in config.groups:
        assert group.candidates == group.blocks * GROUP_SIZE
        assert group.candidates >= group.run_episodes + group.extra_candidates
    blocks = config.blocks_by_group()
    assert blocks[("BinFill", "easy")] == 3  # 300 ≥ 155 + 50
    assert blocks[("RouteStick", "easy")] == 2  # 200 ≥ 115 + 50


def test_配置与契约组列表不一致直接拒(tmp_path):
    def rename(payload):
        # 只改难度名，env 合计仍是 400，因此唯一能拦住它的就是与契约的组序比对
        payload["groups"][0]["difficulty"] = "easyX"

    target = _write_variant(tmp_path, rename)
    # 不给契约时只是组名不同，能加载；给了契约必须拒
    load_delivery_config(target)
    with pytest.raises(DeliveryError, match="组列表与契约组列表不一致"):
        load_delivery_config(target, CONTRACT_V3)


def test_手改run_episodes与margin不符直接拒(tmp_path):
    def bump(payload):
        payload["groups"][0]["run_episodes"] = 154

    target = _write_variant(tmp_path, bump)
    with pytest.raises(DeliveryError, match="run_episodes 应为"):
        load_delivery_config(target, CONTRACT_V3)


def test_每env目标合计不等于四百直接拒(tmp_path):
    def shrink(payload):
        payload["groups"][0]["target_h5"] = 133
        payload["groups"][0]["run_episodes"] = 153

    target = _write_variant(tmp_path, shrink)
    with pytest.raises(DeliveryError, match="合计 399"):
        load_delivery_config(target, CONTRACT_V3)


# ── 清单 ────────────────────────────────────────────────────────────────────
def _tiny_config(tmp_path: Path, *, target_h5: int = 3):
    """造一份只有单 env 单组的小配置，避开 400 条的规模。"""
    run_episodes = int(round(target_h5 * 1.0))
    payload = {
        "config_version": 1,
        "note": "测试用",
        "contract_path": "unused",
        "contract_sha256": "0" * 64,
        "per_env_target": target_h5,
        "margin": 1.0,
        "extra_candidates": 2,
        "groups": [
            {"task": "BinFill", "difficulty": "easy", "target_h5": target_h5, "run_episodes": run_episodes, "blocks": 1}
        ],
    }
    path = tmp_path / "tiny.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return load_delivery_config(path)


def _state(tmp_path, successes, target=3, resets=2):
    """小文件经过真实角色分配及报告核验，不绕过成品散列。"""
    header = {"run_id": "fixture", "group_provenance": {"BinFill/easy": {}},
              "delivery_config_snapshot": {"groups": [{"task": "BinFill", "difficulty": "easy", "target_h5": target}],
                                           "extra_candidates": 2}}
    candidates, rows = [], []
    for episode, ok in enumerate([*successes, *([True] * resets)]):
        kind = "h5" if episode < len(successes) else "reset"
        candidate = {"task": "BinFill", "difficulty": "easy", "episode": episode, "seed": 1000 + episode,
                     "spec_sha256": str(episode), "split": "train" if kind == "h5" else "test"}
        candidates.append(candidate)
        row = {**candidate, "kind": kind, "ok": ok, "error_type": None if ok else "测试失败",
               "outcome": "通过" if ok else "规划失败"}
        if kind == "h5" and ok:
            path = tmp_path / f"ep{episode}.h5"
            path.write_bytes(b"fixture" * (episode + 1))
            row.update(h5_path=str(path), h5_sha256=file_sha(path), h5_bytes=path.stat().st_size)
        rows.append(row)
    rows = assign_roles(header, candidates, list(reversed(rows)))
    return SimpleNamespace(state=tmp_path, logs=tmp_path / "logs",
                           load=lambda: (header, candidates, rows),
                           audit=lambda: {"pending": 0, "unused": 0, "results": len(rows)})


def test_严格交付按episode序取前N条成功(tmp_path):
    store = _state(tmp_path, [True, False, True, False, True])
    rows = store.load()[2]
    assert [r["episode"] for r in rows if r["kind"] == "h5" and r["role"] == "primary"] == [0, 2, 4]
    assert [r["episode"] for r in rows if r["role"] == "failed"] == [1, 3]
    assert report(store)["passed"] is True


def test_多出的成功条标spare且保留h5路径(tmp_path):
    store = _state(tmp_path, [True] * 5, target=2)
    rows = [r for r in store.load()[2] if r["kind"] == "h5"]
    assert [r["episode"] for r in rows if r["role"] == "primary"] == [0, 1]
    assert [r["episode"] for r in rows if r["role"] == "spare"] == [2, 3, 4]
    assert all(Path(r["h5_path"]).is_file() and r["h5_sha256"] for r in rows)
    assert report(store)["passed"]


def test_交付不足时失败且局部运行不冒充完整交付(tmp_path):
    store = _state(tmp_path, [True, False, False])
    with pytest.raises(StateError, match="配额不足"):
        report(store)
    result = report(store, purpose="smoke")
    assert result["quota_gaps"] == ["BinFill/easy"] and result["purpose"] == "smoke"


def test_reset与h5角色分开且不能交叉冒充(tmp_path):
    store = _state(tmp_path, [True, False, True, True], target=2, resets=3)
    header, candidates, rows = store.load()
    assert [r["episode"] for r in rows if r["kind"] == "reset" and r["role"] == "primary"] == [4, 5]
    assert next(r for r in rows if r["episode"] == 6)["role"] == "spare"
    rows[0]["kind"] = "reset"
    with pytest.raises(StateError, match="身份不符"):
        assign_roles(header, candidates, rows)


def test_报告记录实际大小与散列(tmp_path):
    store = _state(tmp_path, [True, True], target=2)
    report(store)
    integrity = json.loads((store.logs / "h5_integrity.json").read_text())
    assert integrity["passed"] and integrity["checked"] == 2
    assert [r["bytes"] for r in integrity["files"]] == [7, 14]
    assert all(r["sha256"] == file_sha(Path(r["path"])) for r in integrity["files"])


@pytest.mark.parametrize("change", ["missing", "same_size_changed"])
def test_缺文件与等长篡改均拒绝(tmp_path, change):
    store = _state(tmp_path, [True, True], target=2)
    path = Path(store.load()[2][0]["h5_path"])
    if change == "missing":
        path.unlink()
    else:
        path.write_bytes(b"x" * path.stat().st_size)
    with pytest.raises(StateError, match="缺失或散列不符"):
        report(store)
