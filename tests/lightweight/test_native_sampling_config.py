#!/usr/bin/env python3
"""轻量测试：原版采样配置的提取、防漂移核对与输入校验（不加载仿真、不占 GPU）。

对应方案第四步 4.4 的 ④.1「输入检查」与 4.6 的定向检查清单：
配置提取与 ``--check-config``、缺失／未知输入、同级 seed 独立导入、提取模式不加载仿真。

    uv run --no-sync python -m pytest tests/lightweight/test_native_sampling_config.py -q
"""

from __future__ import annotations

import ast
import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests._shared.repo_paths import find_repo_root  # noqa: E402

REPO_ROOT = find_repo_root(__file__)
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import generate_dataset_newseed as generator  # noqa: E402
import seed_layout  # noqa: E402

CONFIG_PATH = REPO_ROOT / "scripts" / "configs" / "newtask-v2" / "native_sampling.json"
BASELINE_COMMIT = "94449db0a068a6b454b55a13ebd48f0394d89cc8"

pytestmark = pytest.mark.lightweight


@pytest.fixture(scope="module")
def snapshot() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def test_seed_layout_is_a_sibling_standard_library_module() -> None:
    """平铺后 seed 模块与主生成器同级，且只依赖标准库。"""
    assert Path(seed_layout.__file__).parent == SCRIPTS_DIR
    assert Path(generator.__file__).parent == SCRIPTS_DIR
    assert len(seed_layout.ALL_TASKS) == 16
    assert seed_layout.ALL_TASKS[3] == "BinFill"
    assert seed_layout.MAX_EPISODES == 100
    assert seed_layout.MAX_ATTEMPTS == 100
    assert seed_layout.EPISODE_STRIDE == 100
    # 按 AST 取实际 import，不看文档字符串 —— 迁移说明里会提到旧路径与 sys.path
    tree = ast.parse(Path(seed_layout.__file__).read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported <= {"__future__", "dataclasses"}, imported


def test_check_config_matches_working_tree() -> None:
    """快照与当前工作树源码逐项一致（防漂移检查针对实际运行的源码）。"""
    report = generator.run_extract_config(CONFIG_PATH, REPO_ROOT, check_only=True, source_ref=None)
    assert report["working_tree"] == "一致"


def test_check_config_matches_fixed_baseline_operands() -> None:
    """与固定基线的原版操作元逐项一致：证明接入没有改动任何原值。"""
    if subprocess.run(["git", "-C", str(REPO_ROOT), "cat-file", "-e", BASELINE_COMMIT]).returncode:
        pytest.skip("固定基线提交不可达")
    report = generator.run_extract_config(
        CONFIG_PATH, REPO_ROOT, check_only=True, source_ref=BASELINE_COMMIT
    )
    assert report["source_ref_operands"] == f"{len(generator.SAMPLING_OPERAND_PATHS)} 项一致"


def test_extract_config_is_repeatable(tmp_path: Path, snapshot: dict) -> None:
    """重复导出得到相同原值；说明性块从既有文件原样带过。"""
    target = tmp_path / "native_sampling.json"
    target.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    generator.run_extract_config(target, REPO_ROOT, check_only=False, source_ref=None)
    first = json.loads(target.read_text(encoding="utf-8"))
    generator.run_extract_config(target, REPO_ROOT, check_only=False, source_ref=None)
    second = json.loads(target.read_text(encoding="utf-8"))
    assert first == second
    for block in generator.SAMPLING_EXTRACTED_BLOCKS:
        assert first[block] == snapshot[block]
    assert first["native_semantics"] == snapshot["native_semantics"]


def test_load_sampling_config_slices_four_tasks() -> None:
    """父进程读一次配置，按任务切好；其余 12 个任务不出现在结果里。"""
    configs = generator.load_sampling_config(CONFIG_PATH, REPO_ROOT)
    assert sorted(configs) == sorted(generator.SAMPLING_TASKS)
    for task, payload in configs.items():
        assert set(payload) == {"parameters", "positions"}
        # 2026-09-11 起 RouteStick／VideoUnmaskSwap／VideoRepick 多一档 xhard，BinFill 仍三档
        expected = {"easy", "medium", "hard"} | ({"xhard"} if task != "BinFill" else set())
        assert set(payload["parameters"]["configs"]) == expected
    # 其余 12 个任务照原默认值生成，不因为没有配置而报错
    others = set(seed_layout.ALL_TASKS) - set(generator.SAMPLING_TASKS)
    assert len(others) == 12
    assert not others & set(configs)


def _write(tmp_path: Path, payload: dict) -> Path:
    target = tmp_path / "candidate.json"
    target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return target


@pytest.mark.parametrize(
    "mutate, expected",
    [
        (lambda p: p["parameters"]["BinFill"].pop("dynamic"), "缺少字段"),
        (lambda p: p["parameters"]["BinFill"].update({"新字段": 1}), "未知字段"),
        (lambda p: p["positions"]["BinFill"]["cubes"].pop("region_center"), "缺少字段"),
        (lambda p: p["positions"].pop("RouteStick"), "缺少任务"),
        (lambda p: p["parameters"].update({"NotATask": {}}), "未知任务名"),
        (lambda p: p["positions"]["BinFill"]["button"].update({"scale": "1.5"}), "应为数值"),
        (lambda p: p["positions"]["BinFill"]["cubes"].update({"random_yaw": 1}), "应为布尔值"),
        (lambda p: p["positions"]["BinFill"]["cubes"]["region_center"].append(0.0), "数组长度"),
        (lambda p: p.update({"schema_version": 1}), "schema_version"),
        (lambda p: p["sources"]["BinFill"].update({"sha256": "0" * 64}), "SHA-256 与快照不符"),
        (lambda p: p.pop("sources"), "缺少 sources"),
    ],
)
def test_invalid_config_is_rejected(tmp_path: Path, snapshot: dict, mutate, expected: str) -> None:
    """未知字段、缺失字段、类型或单位不符、来源指纹不符一律拒绝，不静默放行。"""
    payload = copy.deepcopy(snapshot)
    mutate(payload)
    with pytest.raises(generator.SamplingConfigError) as excinfo:
        generator.load_sampling_config(_write(tmp_path, payload), REPO_ROOT)
    assert expected in str(excinfo.value)


def test_config_branch_does_not_load_simulation(tmp_path: Path) -> None:
    """提取分支必须不导入 torch / sapien / cv2 / robomme（spawn 子进程会重跑主模块顶层）。"""
    script = (
        "import sys, json, pathlib\n"
        f"sys.path.insert(0, {str(SCRIPTS_DIR)!r})\n"
        "import generate_dataset_newseed as g\n"
        f"g.run_extract_config({str(CONFIG_PATH)!r}, pathlib.Path({str(REPO_ROOT)!r}), True, None)\n"
        "print(json.dumps(sorted(m for m in sys.modules "
        "if m.split('.')[0] in {'torch','sapien','cv2','robomme','gymnasium','mani_skill'})))\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, cwd=str(REPO_ROOT)
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout.strip().splitlines()[-1]) == []


def test_generator_top_level_has_no_heavy_imports() -> None:
    """主文件顶层与 seed 模块都不得出现重依赖 import。"""
    source = Path(generator.__file__).read_text(encoding="utf-8")
    # 顶层 import 一律顶格；函数体内的重依赖 import 有缩进，因此按行首匹配即可区分
    top_level = [line for line in source.splitlines() if line and not line[0].isspace()]
    for line in top_level:
        assert not line.startswith(("import torch", "import sapien", "import cv2", "import robomme")), line
        assert not line.startswith(("from torch", "from sapien", "from cv2", "from robomme")), line
    assert "import h5py  # noqa: E402" in source
    assert "import numpy as np  # noqa: E402" in source


def test_cli_rejects_check_config_without_extract(capsys) -> None:
    """--check-config / --source-ref 只能配合 --extract-config。"""
    assert generator.main(["--check-config", "--output-dir", "artifacts/x"]) == 1
    assert "只能配合 --extract-config" in capsys.readouterr().err


def test_cli_requires_output_dir_for_generation(capsys) -> None:
    """--output-dir 改为非 required 后，常规生成仍必须自己校验。"""
    assert generator.main(["--env", "BinFill"]) == 1
    assert "常规生成需要 --output-dir" in capsys.readouterr().err


def test_cli_merge_only_requires_input_dir(capsys) -> None:
    assert generator.main(["--merge-only"]) == 1
    assert "--merge-only 需要 --input-dir" in capsys.readouterr().err


def test_extract_and_merge_modes_are_mutually_exclusive() -> None:
    with pytest.raises(SystemExit):
        generator._args(["--extract-config", "x.json", "--merge-only"])


def test_episode_job_carries_independent_config_copies() -> None:
    """每个 job 拿一份独立副本；改一份不影响另一份，也不回写父进程配置。"""
    configs = generator.load_sampling_config(CONFIG_PATH, REPO_ROOT)
    first = generator.EpisodeJob(
        task="BinFill", episode=0, attempt=0, seed=4000, difficulty="easy",
        output_root="/tmp/a", repo_root=str(REPO_ROOT),
        sampling_config=copy.deepcopy(configs["BinFill"]),
    )
    second = generator.EpisodeJob(
        task="BinFill", episode=1, attempt=0, seed=4100, difficulty="easy",
        output_root="/tmp/a", repo_root=str(REPO_ROOT),
        sampling_config=copy.deepcopy(configs["BinFill"]),
    )
    first.sampling_config["positions"]["cubes"]["region_center"][0] = 999.0
    assert second.sampling_config["positions"]["cubes"]["region_center"][0] != 999.0
    assert configs["BinFill"]["positions"]["cubes"]["region_center"][0] != 999.0


def test_bumped_job_keeps_its_config() -> None:
    """attempt 重试沿用同一份配置，只换 seed。"""
    configs = generator.load_sampling_config(CONFIG_PATH, REPO_ROOT)
    job = generator.EpisodeJob(
        task="BinFill", episode=0, attempt=0, seed=4000, difficulty="easy",
        output_root="/tmp/a", repo_root=str(REPO_ROOT),
        sampling_config=configs["BinFill"],
    )
    layout = seed_layout.get_layout("train")
    bumped = job.bump(layout.seed("BinFill", 0, 1))
    assert bumped.seed == 4001 and bumped.attempt == 1
    assert bumped.sampling_config == job.sampling_config


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
