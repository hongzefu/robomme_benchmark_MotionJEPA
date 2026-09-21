#!/usr/bin/env python3
"""轻量测试：步 2 恢复的原值不得再被改回（源码级断言，不导入仿真栈）。

对应 NEWTASK_RELEASE_V3_PLAN.md 第五节步 2 与口径 8：`RouteStick.py::step` 的白球尾迹
必须是官方 dataset-gen 的 40 步，且不得写死——它会渲进 front/wrist 的 rgb 与 depth，
写死就让 A↔B 永远不可能逐位相同。

    uv run --no-sync python -m pytest tests/lightweight/test_native_restore_step2.py -q
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests._shared.repo_paths import find_repo_root  # noqa: E402

REPO_ROOT = find_repo_root(__file__)
ROUTESTICK = REPO_ROOT / "src" / "robomme" / "robomme_env" / "RouteStick.py"


def _native_sampling() -> dict:
    """只解析 NATIVE_SAMPLING 字面量，不导入 robomme（避免拉起 sapien/torch）。"""
    tree = ast.parse(ROUTESTICK.read_text(encoding="utf-8"), filename=str(ROUTESTICK))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "NATIVE_SAMPLING"
            for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError("RouteStick.py 里找不到 NATIVE_SAMPLING")


def test_tcp_trail_is_official_forty_steps() -> None:
    trail = _native_sampling()["positions"]["tcp_trail"]
    assert trail["end_offset_steps"] == 40, "白球尾迹必须是官方的 40 步"
    assert trail["disk_radius"] == 0.005


def test_step_reads_trail_from_config_not_hardcoded() -> None:
    source = ROUTESTICK.read_text(encoding="utf-8")
    assert "end_step=cur_step + int(trail_cfg[" in source
    # 不允许再出现写死的偏移量（官方值也要走配置，才能被 C 路显式传入核验）。
    assert not re.search(r"end_step\s*=\s*cur_step\s*\+\s*\d+", source)


def test_button_highlight_keeps_official_forty_steps() -> None:
    source = ROUTESTICK.read_text(encoding="utf-8")
    # 按钮高亮官方与现行一致，本轮不动；这里锁住它不被顺手改掉。
    assert "end_step=start_step + 40," in source
