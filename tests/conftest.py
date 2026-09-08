from __future__ import annotations

from pathlib import Path

import pytest

from tests._shared.repo_paths import ensure_src_on_path, find_repo_root

REPO_ROOT = ensure_src_on_path(__file__)


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def src_root(repo_root: Path) -> Path:
    return repo_root / "src"


def pytest_addoption(parser) -> None:
    """newtask-v2 三路对拍的自定义选项（方案第四步 4.7）。

    现有两个 conftest 原本都没有自定义选项，三路对拍测试需要显式指定运行模式、
    用例表与参考证据，因此在这里统一注册。
    """
    group = parser.getgroup("newtask-v2 parity")
    group.addoption(
        "--parity-mode",
        action="store",
        default=None,
        choices=("fresh", "regression"),
        help="fresh：冻结用例重新跑 A/B/C 并比较；regression：拿 Git 中的固定原版证据比较当前 B/C",
    )
    group.addoption("--parity-cases", action="store", default=None, help="用例表 JSON 路径")
    group.addoption("--parity-case", action="append", default=None, help="只跑指定格，可重复")
    group.addoption("--parity-reference", action="store", default=None, help="参考证据包目录")
    group.addoption("--parity-output", action="store", default=None, help="本次结果与证据的落点")


def pytest_configure(config) -> None:
    # Fallback marker registration even if pytest is invoked without pyproject parsing.
    config.addinivalue_line("markers", "slow: slow-running tests")
    config.addinivalue_line("markers", "gpu: tests requiring GPU/display/headless rendering stack")
    config.addinivalue_line("markers", "dataset: tests that generate/use temporary datasets")
    config.addinivalue_line("markers", "lightweight: tests that do not require generated dataset")

