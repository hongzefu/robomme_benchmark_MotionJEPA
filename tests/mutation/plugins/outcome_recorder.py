"""植入执行器的结果记录插件：把每个用例各阶段的结局与异常类型、收集错误写到 MUT_OUTCOME_FILE（JSON）。

只在环境变量 MUT_OUTCOME_FILE 存在时生效；不改任何被测行为。
"""
from __future__ import annotations

import json
import os

import pytest

_PATH = os.environ.get("MUT_OUTCOME_FILE")
_TESTS: dict[str, dict] = {}
_COLLECT_ERRORS: list[dict] = []


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    if not _PATH:
        return
    rep = outcome.get_result()
    rec = _TESTS.setdefault(rep.nodeid, {"phases": {}})
    exc = call.excinfo.typename if call.excinfo is not None else None
    msg = None
    if rep.failed and rep.longrepr is not None:
        crash = getattr(rep.longrepr, "reprcrash", None)
        msg = (crash.message if crash is not None else str(rep.longrepr))[:400]
    rec["phases"][rep.when] = {"outcome": rep.outcome, "exc": exc, "msg": msg}


def pytest_collectreport(report):
    if _PATH and report.failed:
        _COLLECT_ERRORS.append({"nodeid": report.nodeid, "msg": str(report.longrepr)[-600:]})


def pytest_sessionfinish(session, exitstatus):
    if not _PATH:
        return
    with open(_PATH, "w", encoding="utf-8") as fh:
        json.dump({"exitstatus": int(exitstatus), "tests": _TESTS, "collect_errors": _COLLECT_ERRORS}, fh,
                  ensure_ascii=False)
