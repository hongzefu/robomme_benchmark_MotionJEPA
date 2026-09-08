#!/usr/bin/env python3
"""三路对拍实测（真实生成，需 GPU；方案第四步 4.7 的「从头复现」与「当前代码回归」）。

默认跳过：必须显式给 ``--parity-mode``，因为每格四次真实生成，属于长任务预算。

从头复现（冻结用例 + 固定源码，在新目录完整跑 A/B/C 并比较）::

    uv run --no-sync python -m pytest tests/dataset/test_native_sampling_parity.py -q \\
        --parity-mode fresh --parity-case BinFill-easy-dynamicTrue \\
        --parity-output artifacts/parity-pack/<运行编号>

当前代码回归（指定 Git 中的固定原版证据，重新跑当前 B/C 并直接比较，
不自动重生成、不刷新旧基准）::

    uv run --no-sync python -m pytest tests/dataset/test_native_sampling_parity.py -q \\
        --parity-mode regression \\
        --parity-reference docs/validation/newtask-v2/<运行编号> \\
        --parity-output artifacts/parity-pack/<新运行编号>

纯离线比较（不加载仿真、不占 GPU）用另一个入口::

    uv run --no-sync python -m tests._shared.native_sampling_parity compare \\
        --reference <参考运行目录> --candidate <候选运行目录> --output <新目录>
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests._shared import native_sampling_parity as parity  # noqa: E402
from tests._shared import parity_runner as runner  # noqa: E402
from tests._shared.repo_paths import find_repo_root  # noqa: E402

REPO_ROOT = find_repo_root(__file__)
DEFAULT_CASES = REPO_ROOT / "docs" / "validation" / "newtask-v2" / "cases.json"

pytestmark = [pytest.mark.dataset, pytest.mark.gpu, pytest.mark.slow]


@pytest.fixture(scope="module")
def parity_options(request) -> dict:
    mode = request.config.getoption("--parity-mode")
    if not mode:
        pytest.skip("三路对拍是长任务，需显式给 --parity-mode fresh|regression")
    cases_path = Path(request.config.getoption("--parity-cases") or DEFAULT_CASES)
    output = request.config.getoption("--parity-output")
    if not output:
        pytest.fail("--parity-mode 必须同时给 --parity-output，结果与证据不复用旧目录")
    output_path = Path(output)
    if output_path.exists() and any(output_path.iterdir()):
        pytest.fail(f"输出目录非空，拒绝覆盖：{output_path}")
    return {
        "mode": mode,
        "cases_path": cases_path,
        "cases": json.loads(cases_path.read_text(encoding="utf-8")),
        "cells": request.config.getoption("--parity-case"),
        "reference": request.config.getoption("--parity-reference"),
        "output": output_path,
        "run_id": output_path.name or f"parity-{int(time.time())}",
    }


def _selected_cases(options: dict) -> list[dict]:
    cases = options["cases"]["cases"]
    if options["cells"]:
        wanted = set(options["cells"])
        cases = [case for case in cases if case["cell"] in wanted]
        assert cases, f"用例表里没有这些格：{sorted(wanted)}"
    return cases


def test_three_way_parity(parity_options: dict) -> None:
    """逐格跑真实生成并比较；受阻格保留记录，不因存在受阻格而把失败说成通过。"""
    options = parity_options
    cases = _selected_cases(options)
    run_id = options["run_id"]
    run_root = REPO_ROOT / "artifacts" / "parity" / run_id
    evidence_root = REPO_ROOT / "artifacts" / "parity-evidence" / run_id
    log_dir = REPO_ROOT / "artifacts" / "logs" / "parity" / run_id

    if options["mode"] == "fresh":
        labels = None
    else:
        # 回归：原版证据取自 Git 中的参考包，本次只重新跑当前 B/C
        assert options["reference"], "--parity-mode regression 必须给 --parity-reference"
        labels = ("B", "C")

    report = runner.run_matrix(
        cases_path=options["cases_path"],
        output_root=run_root,
        evidence_root=evidence_root,
        log_dir=log_dir,
        only_cells=[case["cell"] for case in cases],
        only_paths=labels,
    )
    assert report["results"], "没有任何运行结果"

    package = parity.pack_run(run_root, evidence_root, cases, options["output"])
    (options["output"] / "runner_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    if options["mode"] == "regression":
        reference = json.loads((Path(options["reference"]) / "result.json").read_text(encoding="utf-8"))
        differences: list[str] = []
        for cell, item in package["cells"].items():
            expected = reference["cells"].get(cell)
            if expected is None:
                differences.append(f"{cell}: 参考包里没有这一格")
                continue
            for label in ("B", "C"):
                got = item["paths"].get(label, {}).get("h5", {}).get("sha256")
                want = expected["paths"].get("A1", {}).get("h5", {}).get("sha256")
                if want is None:
                    continue
                if got != want:
                    differences.append(f"{cell}/{label}: HDF5 指纹与参考原版不同（{got} != {want}）")
        assert not differences, "当前代码回归失败：\n" + "\n".join(differences)
        return

    blocked = {cell: item["status"] for cell, item in package["cells"].items() if item["status"].startswith("受阻")}
    failed = {cell: item for cell, item in package["cells"].items() if item["status"] == "失败"}
    assert not failed, "存在真实失败格：" + json.dumps(
        {cell: item["comparisons"] for cell, item in failed.items()}, ensure_ascii=False
    )[:4000]
    # 受阻格按方案 4.0 的退出路径单列，不算通过、也不阻塞其余格
    if blocked:
        print("受阻格（保留记录，需另选同格其他 episode 补足）：", json.dumps(blocked, ensure_ascii=False))


def test_offline_comparison_needs_explicit_inputs() -> None:
    """纯离线比较必须显式给两份证据，不默认选最新。"""
    with pytest.raises(SystemExit):
        parity._main(["compare"])


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
