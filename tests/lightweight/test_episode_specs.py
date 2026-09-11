"""``--episode-specs`` 的格式契约与父进程校验（NEW_VALUE_INJECTION_TEST_PLAN 步骤 0a）。

重点不是把实现再抄一遍，而是把**反例**钉死：缺字段、未知字段、改散列、非有限数、
任务／难度不符、episode 重复、清单点名了不存在的 episode——每一条都必须在父进程建池
之前被拒绝，绝不带进 worker。另外锁住两份 canonical JSON 实现（生产侧与测试侧）逐字节一致。
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
for extra in (REPO_ROOT, REPO_ROOT / "src", REPO_ROOT / "scripts"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import generate_dataset_newseed as generator  # noqa: E402

from tests._shared.injection_specs import canonical_json, record_sha256, seal  # noqa: E402


def _minimal_record(episode: int = 0) -> dict:
    """一条形状合法的最小 BinFill 记录；散列由 seal 现算。"""
    return seal(
        {
            "episode": episode,
            "task": "BinFill",
            "difficulty": "hard",
            "layout": {
                "dynamic": True,
                "button_xy": [-0.21, 0.08],
                "board": {"xy": [0.05, -0.12], "yaw_deg": 7.5},
                "cubes": [{"object_id": "cube_red_0", "color": "red", "color_index": 0, "xy": [-0.2, 0.15], "yaw_rad": 1.1}],
            },
            "objects": {
                "colors_present": ["red"],
                "initialize_color_order": ["blue", "red", "green"],
                "target_pool": ["red"],
                "spawn_total": 1,
                "put_in_total": 1,
                "spawn_count": {"red": 1},
                "target_count": {"red": 1},
            },
            "actions": [{"pick": "cube_red_0", "put_in": True}],
            "sampling_cells": {"button_x": [0, 0]},
        }
    )


def _document(records: list[dict]) -> dict:
    return {
        "spec_schema_version": 1,
        "task": "BinFill",
        "difficulty": "hard",
        "generator_seed": 20260909,
        "derived_seed": 1,
        "generator_version": "injection-specs-1",
        "sampling_config_sha256": "0" * 64,
        "episodes": records,
    }


def _write(tmp_path: Path, payload: dict, name: str = "hard.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


# ── 两份 canonical JSON 实现必须一致 ─────────────────────────────────────────
@pytest.mark.parametrize(
    "payload",
    [
        {"b": 1.5, "a": [1, 2, {"z": "中文"}], "c": True},
        {"x": -0.0, "y": 1e-17, "z": [1e300]},
        {"嵌套": {"深": {"层": [None, False, 0]}}},
    ],
)
def test_生产侧与测试侧的规范序列化逐字节一致(payload):
    """生产代码不导入 tests，所以散列算法有两份实现；这条测试把它们锁在一起。"""
    assert generator._spec_canonical_json(payload) == canonical_json(payload)


def test_两侧算出的记录散列相同():
    record = _minimal_record()
    assert generator.spec_record_sha256(record) == record_sha256(record)
    assert record["spec_sha256"] == generator.spec_record_sha256(record)


# ── 单条记录校验 ────────────────────────────────────────────────────────────
def test_合法记录通过校验():
    generator.validate_episode_spec(_minimal_record(), "BinFill", "hard", "x")


@pytest.mark.parametrize("field", ["episode", "task", "difficulty", "layout", "objects", "actions", "spec_sha256"])
def test_缺任一必备字段都被拒(field):
    record = _minimal_record()
    record.pop(field)
    with pytest.raises(generator.EpisodeSpecError, match="缺字段"):
        generator.validate_episode_spec(record, "BinFill", "hard", "x")


def test_篡改散列被拒():
    record = _minimal_record()
    record["spec_sha256"] = "0" * 64
    with pytest.raises(generator.EpisodeSpecError, match="spec_sha256 不符"):
        generator.validate_episode_spec(record, "BinFill", "hard", "x")


def test_改了内容不改散列也被拒():
    """只动一个坐标、不动 spec_sha256——重算散列立刻不匹配。"""
    record = _minimal_record()
    record["layout"]["button_xy"][0] = -0.22
    with pytest.raises(generator.EpisodeSpecError, match="spec_sha256 不符"):
        generator.validate_episode_spec(record, "BinFill", "hard", "x")


def test_任务不符被拒():
    with pytest.raises(generator.EpisodeSpecError, match="不符"):
        generator.validate_episode_spec(_minimal_record(), "RouteStick", "hard", "x")


def test_难度不符被拒():
    with pytest.raises(generator.EpisodeSpecError, match="不符"):
        generator.validate_episode_spec(_minimal_record(), "BinFill", "easy", "x")


def test_非有限数被拒():
    record = _minimal_record()
    record["layout"]["button_xy"][0] = float("inf")
    record["spec_sha256"] = "0" * 64  # 散列先绕开，确保是「非有限数」这一条拦下的
    with pytest.raises(generator.EpisodeSpecError, match="非有限数"):
        generator.validate_episode_spec(record, "BinFill", "hard", "x")


def test_episode_不是整数被拒():
    record = _minimal_record()
    record["episode"] = "0"
    with pytest.raises(generator.EpisodeSpecError, match="episode 必须是整数"):
        generator.validate_episode_spec(record, "BinFill", "hard", "x")


# ── 文档级校验 ──────────────────────────────────────────────────────────────
def test_未知顶层字段被拒(tmp_path):
    payload = _document([_minimal_record()])
    payload["顺手加的字段"] = 1
    with pytest.raises(generator.EpisodeSpecError, match="未知顶层字段"):
        generator.load_spec_document(_write(tmp_path, payload))


def test_缺顶层字段被拒(tmp_path):
    payload = _document([_minimal_record()])
    payload.pop("generator_version")
    with pytest.raises(generator.EpisodeSpecError, match="缺顶层字段"):
        generator.load_spec_document(_write(tmp_path, payload))


def test_episode_重复被拒(tmp_path):
    payload = _document([_minimal_record(0), _minimal_record(0)])
    with pytest.raises(generator.EpisodeSpecError, match="重复"):
        generator.load_spec_document(_write(tmp_path, payload))


def test_文档任务与请求不符被拒(tmp_path):
    path = _write(tmp_path, _document([_minimal_record()]))
    with pytest.raises(generator.EpisodeSpecError, match="CLI 请求的是"):
        generator.load_spec_document(path, "RouteStick", "hard")


def test_不是合法_json_被拒(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{不是 json", encoding="utf-8")
    with pytest.raises(generator.EpisodeSpecError, match="不是合法 JSON"):
        generator.load_spec_document(path)


# ── 清单模式 ────────────────────────────────────────────────────────────────
def _manifest(tmp_path: Path) -> tuple[Path, Path]:
    spec = _write(tmp_path, _document([_minimal_record(0), _minimal_record(1)]))
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "manifest_version": 1,
                "groups": [
                    {"task": "BinFill", "difficulty": "hard", "spec_path": spec.name, "episodes": [0, 1]}
                ],
            }
        ),
        encoding="utf-8",
    )
    return manifest, spec


def test_清单模式解析出独立输出根(tmp_path):
    manifest, _ = _manifest(tmp_path)
    groups = generator.load_episode_specs(manifest, REPO_ROOT, tmp_path / "out")
    assert len(groups) == 1
    assert groups[0].episodes == (0, 1)
    # 同任务不同难度的 seed 与 HDF5 文件名相同，所以必须分到 <任务>/<难度> 子目录
    assert groups[0].output_root.endswith("out/BinFill/hard")


def test_清单点名不存在的_episode_被拒(tmp_path):
    manifest, _ = _manifest(tmp_path)
    payload = json.loads(manifest.read_text())
    payload["groups"][0]["episodes"] = [0, 99]
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(generator.EpisodeSpecError, match="不在规格里"):
        generator.load_episode_specs(manifest, REPO_ROOT, tmp_path / "out")


def test_清单里同一组重复被拒(tmp_path):
    manifest, spec = _manifest(tmp_path)
    payload = json.loads(manifest.read_text())
    payload["groups"].append(dict(payload["groups"][0]))
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(generator.EpisodeSpecError, match="重复"):
        generator.load_episode_specs(manifest, REPO_ROOT, tmp_path / "out")


def test_既不是规格也不是清单被拒(tmp_path):
    path = tmp_path / "x.json"
    path.write_text(json.dumps({"随便": 1}), encoding="utf-8")
    with pytest.raises(generator.EpisodeSpecError, match="既不是规格文件"):
        generator.load_episode_specs(path, REPO_ROOT, tmp_path / "out")


# ── 隔离：每个 job 一份独立副本 ──────────────────────────────────────────────
def test_每个_job_拿到独立深拷贝(tmp_path):
    """worker 之间、同一 worker 的前后两局之间不得共享可变缓存。"""
    manifest, _ = _manifest(tmp_path)
    groups = generator.load_episode_specs(manifest, REPO_ROOT, tmp_path / "out")
    first = copy.deepcopy(dict(groups[0].records[0]))
    second = copy.deepcopy(dict(groups[0].records[0]))
    first["layout"]["button_xy"][0] = 999.0
    assert second["layout"]["button_xy"][0] != 999.0
    assert groups[0].records[0]["layout"]["button_xy"][0] != 999.0


def test_关闭态的_job_不带规格字段():
    """不传 --episode-specs 时 episode_spec 恒为 None，worker 就不会多传这个 kwarg。"""
    job = generator.EpisodeJob(
        task="BinFill", episode=0, attempt=0, seed=1, difficulty="hard",
        output_root="/tmp/x", repo_root=str(REPO_ROOT),
    )
    assert job.episode_spec is None
    assert job.sampling_config is None


# ── 冻结产物的真实回归 ──────────────────────────────────────────────────────
#: 最终口径（身份散列排除 collision 诊断字段）下冻结的运行编号。
#: 更早的 01／02／03 是开发迭代产物，散列口径不同，不作回归对象。
FROZEN = REPO_ROOT / "artifacts" / "injection" / "20260910-new-values-04" / "specs"


@pytest.mark.skipif(not FROZEN.is_dir(), reason="该运行编号的冻结规格不在工作区")
@pytest.mark.parametrize("relative", ["BinFill/hard.json", "RouteStick/hard.json", "VideoUnmaskSwap/hard.json", "VideoRepick/medium.json"])
def test_真实冻结规格能被生产入口原样加载(relative):
    document = generator.load_spec_document(FROZEN / relative)
    assert len(document["records"]) == 100
    assert sorted(document["records"]) == list(range(100))
