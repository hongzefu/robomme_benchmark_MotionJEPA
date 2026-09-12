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

from scripts.injection.contract import load_contract  # noqa: E402
from scripts.injection.delivery import (  # noqa: E402
    DeliveryError,
    build_delivery_manifest,
    load_delivery_config,
    render_verdict_line,
)
from scripts.injection.run import OUTCOME_PASS  # noqa: E402
from scripts.injection.sampling import GROUP_SIZE  # noqa: E402

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


def _row(episode: int, *, outcome: str = OUTCOME_PASS, h5_path: str | None = None, **extra):
    row = {
        "task": "BinFill",
        "difficulty": "easy",
        "episode": episode,
        "seed": 1000 + episode,
        "outcome": outcome,
        "error_type": None if outcome == OUTCOME_PASS else "RuntimeError",
        "error": "" if outcome == OUTCOME_PASS else "x" * 500,
        "video_status": "complete",
        "h5_path": h5_path if h5_path is not None else f"/tmp/fake/ep{episode}.h5",
        "timestep_count": 120 + episode,
    }
    row.update(extra)
    return row


def test_严格交付按episode序取前N条成功(tmp_path):
    config = _tiny_config(tmp_path, target_h5=3)
    rows = [
        _row(0),
        _row(1, outcome="规划失败"),  # 夹在中间的失败条必须被跳过、顺延
        _row(2),
        _row(3, outcome="碰撞拒绝"),
        _row(4),
    ]
    # 故意打乱输入顺序，验证内部按 episode 升序
    manifest = build_delivery_manifest(
        list(reversed(rows)), config, run_id="t1", repo_root=tmp_path, hash_mode="none"
    )
    group = manifest["groups"]["BinFill/easy"]
    assert [item["episode"] for item in group["primary"]] == [0, 2, 4]
    assert group["spare_rows"] == []
    assert [item["episode"] for item in group["failures"]] == [1, 3]
    assert len(group["failures"][0]["error"]) <= 200
    assert group["delivered"] == 3 and group["failed"] == 2 and group["passed"] == 3
    assert manifest["envs"]["BinFill"]["delivered"] == 3
    assert manifest["shortfall"] == []
    assert manifest["passed"] is True
    assert render_verdict_line(manifest["verdicts"][0]).startswith("DELIVERY_400=PASS env=BinFill")


def test_多出的成功条标spare且保留h5路径(tmp_path):
    config = _tiny_config(tmp_path, target_h5=2)
    rows = [_row(i) for i in range(5)]
    manifest = build_delivery_manifest(rows, config, run_id="t2", repo_root=Path("/tmp"), hash_mode="none")
    group = manifest["groups"]["BinFill/easy"]
    assert [item["episode"] for item in group["primary"]] == [0, 1]
    assert [item["episode"] for item in group["spare_rows"]] == [2, 3, 4]
    assert all(item["role"] == "spare" for item in group["spare_rows"])
    assert all(item["h5_path"] for item in group["spare_rows"])  # 备件仍记 h5 路径
    assert group["spare_rows"][0]["h5_path"] == "fake/ep2.h5"  # 相对 repo_root
    assert group["spare_rows"][0]["bytes"] is None and group["spare_rows"][0]["sha256"] is None
    assert group["spare_rows"][0]["timestep_count"] == 122
    assert manifest["envs"]["BinFill"]["spare"] == 3


def test_交付不足时判定行失败并报缺口(tmp_path):
    config = _tiny_config(tmp_path, target_h5=3)
    rows = [_row(0), _row(1, outcome="超时"), _row(2, outcome="超时")]
    manifest = build_delivery_manifest(rows, config, run_id="t3", repo_root=tmp_path, hash_mode="none")
    assert manifest["passed"] is False
    assert manifest["shortfall"] == [
        {
            "env": "BinFill",
            "group": "BinFill/easy",
            "missing": 2,
            "remaining_candidates": GROUP_SIZE - 3,
        }
    ]
    line = render_verdict_line(manifest["verdicts"][0])
    assert line.startswith("DELIVERY_400=FAIL")
    assert "delivered=1" in line
    total = manifest["verdicts"][-1]
    assert total["name"] == "DELIVERY_TOTAL" and total["passed"] is False
    assert total["fields"]["h5_sha_mismatch"] == 0


def test_env_check交集标记also_env_checked(tmp_path):
    config = _tiny_config(tmp_path, target_h5=2)
    rows = [_row(0), _row(1, outcome="规划失败"), _row(2), _row(3)]
    env_check = {"groups": {"BinFill/easy": {"episodes": [1, 3, 99]}}}
    manifest = build_delivery_manifest(
        rows, config, run_id="t4", repo_root=tmp_path, env_check_result=env_check, hash_mode="none"
    )
    group = manifest["groups"]["BinFill/easy"]
    marked = {
        item["episode"]
        for item in [*group["primary"], *group["spare_rows"], *group["failures"]]
        if item.get("also_env_checked")
    }
    assert marked == {1, 3}  # 99 不在本组结果里，交集把它排除


def test_size_only模式记录字节数(tmp_path):
    config = _tiny_config(tmp_path, target_h5=2)
    files = []
    for index in range(2):
        path = tmp_path / f"ep{index}.h5"
        path.write_bytes(b"h5" * (index + 1))
        files.append(str(path))
    rows = [_row(0, h5_path=files[0]), _row(1, h5_path=files[1])]
    manifest = build_delivery_manifest(
        rows, config, run_id="t5", repo_root=tmp_path, hash_mode="size-only"
    )
    group = manifest["groups"]["BinFill/easy"]
    assert [item["bytes"] for item in group["primary"]] == [2, 4]
    assert all(item["sha256"] is None for item in group["primary"])
    assert manifest["hash_mode"] == "size-only"
    assert manifest["verdicts"][-1]["fields"]["h5_missing"] == 0


def test_full模式并行算散列且缺文件记h5_missing(tmp_path):
    import hashlib

    config = _tiny_config(tmp_path, target_h5=2)
    present = tmp_path / "ep0.h5"
    present.write_bytes(b"abc")
    rows = [_row(0, h5_path=str(present)), _row(1, h5_path=str(tmp_path / "missing.h5"))]
    manifest = build_delivery_manifest(
        rows, config, run_id="t6", repo_root=tmp_path, hash_mode="full", workers=2
    )
    primary = manifest["groups"]["BinFill/easy"]["primary"]
    assert primary[0]["sha256"] == hashlib.sha256(b"abc").hexdigest()
    assert primary[0]["bytes"] == 3
    assert primary[1]["h5_missing"] is True and primary[1]["bytes"] is None
    assert manifest["verdicts"][-1]["fields"]["h5_missing"] == 1
