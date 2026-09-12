"""候选规格「可产生环境」核验的定向测试（``scripts/injection/env_check.py``）。

全部用 ``run_env_check`` 的 ``submit`` 钩子注入假 checker：同步串行、不开进程、不碰 GPU，
因此整份测试是轻量的，可以随时跑。要钉死的四件事：

* reset 期异常按七类互斥结果翻译，且系统错误（``failure_class="code"``）归「未运行」，不冒充物理不可行；
* 核验从实跑区间之后（``start``）开始、按 episode 升序，攒够 ``need`` 条通过就停；
* 交付集是**按 episode 序最前的** ``need`` 条通过者，不是「先返回的」；
* 候选耗尽仍不足时如实判失败，并且全程零 h5、零视频产物。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
for extra in (REPO_ROOT, REPO_ROOT / "src"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from scripts.injection.env_check import (  # noqa: E402
    EnvCheckPlan,
    classify_reset_outcome,
    render_verdict_line,
    run_env_check,
)
from scripts.injection.run import (  # noqa: E402
    OUTCOME_BINDING,
    OUTCOME_COLLISION,
    OUTCOME_NOT_RUN,
    OUTCOME_PASS,
    OUTCOME_PLAN,
    OUTCOME_SPEC_REJECT,
    OUTCOME_TIMEOUT,
)

TASK = "BinFill"
DIFFICULTY = "hard"
GROUP_KEY = f"{TASK}/{DIFFICULTY}"


def 造文档(episodes):
    """造一份最小可用的组文档：字段只留 run_env_check 真正读的那几个。"""
    return {
        (TASK, DIFFICULTY): {
            "task": TASK,
            "difficulty": DIFFICULTY,
            "episodes": [
                {
                    "task": TASK,
                    "difficulty": DIFFICULTY,
                    "episode": number,
                    "spec_sha256": f"sha-{number:04d}",
                }
                for number in episodes
            ],
        }
    }


def 造通过结果(job):
    return {
        "ok": True,
        "failure_class": None,
        "error_type": None,
        "error": None,
        "wall_s": 1.5,
        "phases": {"make_s": 0.5, "reset_s": 0.9, "close_s": 0.1},
        "bound": {"gpu": "0", "pid": 4242},
        "injection_bound": True,
        "runtime_checks_total": 3,
    }


def 造失败结果(error_type: str, failure_class: str = "task"):
    return {
        "ok": False,
        "failure_class": failure_class,
        "error_type": error_type,
        "error": f"{error_type}: 造出来的失败",
        "wall_s": 0.8,
        "phases": {"make_s": 0.4, "reset_s": 0.4},
        "bound": {"gpu": "0", "pid": 4242},
        "injection_bound": False,
        "runtime_checks_total": 0,
    }


def 跑一轮(tmp_path, documents, plans, checker, *, workers_per_gpu: int = 2, gpus=("0",)):
    return run_env_check(
        documents,
        plans,
        gpus=list(gpus),
        workers_per_gpu=workers_per_gpu,
        sampling_config=None,
        out_dir=tmp_path / "env_check",
        repo_root=REPO_ROOT,
        submit=checker,
    )


# ── 七类翻译 ────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("error_type", "failure_class", "expected"),
    [
        ("EpisodeSpecError", "task", OUTCOME_SPEC_REJECT),
        ("BinCollisionError", "task", OUTCOME_COLLISION),
        ("SpecBindingError", "task", OUTCOME_BINDING),
        ("EnvResetWallClockTimeout", "timeout", OUTCOME_TIMEOUT),
        ("AttributeError", "code", OUTCOME_NOT_RUN),
        ("SceneGenerationError", "task", OUTCOME_PLAN),
    ],
)
def test_reset异常按七类翻译(error_type, failure_class, expected):
    assert classify_reset_outcome(造失败结果(error_type, failure_class)) == expected


def test_成功记录翻成通过():
    assert classify_reset_outcome({"ok": True}) == OUTCOME_PASS


# ── 派发顺序 ────────────────────────────────────────────────────────────────
def test_核验从实跑区间之后开始按序(tmp_path):
    """实跑区间是 0～29，额外候选从 30 起：第一条必须是 30，且整串严格升序。"""
    documents = 造文档(range(0, 90))
    seen: list[int] = []

    def checker(job):
        seen.append(job.episode)
        return 造通过结果(job)

    payload = 跑一轮(tmp_path, documents, [EnvCheckPlan(TASK, DIFFICULTY, start=30, need=5)], checker)

    assert seen[0] == 30
    assert seen == sorted(seen)
    assert min(seen) >= 30
    assert payload["groups"][GROUP_KEY]["delivered"] == [30, 31, 32, 33, 34]
    assert payload["passed"] is True


def test_攒够所需条数即停且交付的是最前的通过者(tmp_path):
    """30、32、35 失败：交付集应是 31/33/34，且总派发数不超过 need+失败数+一个批次。"""
    documents = 造文档(range(0, 90))
    坏 = {30, 32, 35}
    seen: list[int] = []

    def checker(job):
        seen.append(job.episode)
        if job.episode in 坏:
            return 造失败结果("BinCollisionError")
        return 造通过结果(job)

    plan = EnvCheckPlan(TASK, DIFFICULTY, start=30, need=3)
    payload = 跑一轮(tmp_path, documents, [plan], checker, workers_per_gpu=2)

    group = payload["groups"][GROUP_KEY]
    assert group["delivered"] == [31, 33, 34]
    assert group["passed"] >= 3
    assert group["shortfall"] == 0
    # 批式派发：允许多派最后一个批次，但不能没完没了地派
    失败数 = sum(1 for number in seen if number in 坏)
    assert len(seen) <= plan.need + 失败数 + 2
    assert 35 not in group["delivered"]
    assert payload["passed"] is True

    # 攒够之后仍在飞的结果照常登记，但不参与计数
    rows = 读结果行(tmp_path)
    assert all(row["counted"] for row in rows if row["episode"] in {30, 31, 32, 33, 34})
    delivered_rows = [row["episode"] for row in rows if row["delivered"]]
    assert delivered_rows == [31, 33, 34]


def test_候选耗尽仍不足时判定失败并如实登记(tmp_path):
    """文档里只有 4 条候选，却要 10 条：判 FAIL，shortfall 与 exhausted 都如实写出。"""
    documents = 造文档([30, 31, 32, 33])

    def checker(job):
        return 造失败结果("SceneGenerationError") if job.episode == 31 else 造通过结果(job)

    payload = 跑一轮(tmp_path, documents, [EnvCheckPlan(TASK, DIFFICULTY, start=30, need=10)], checker)

    group = payload["groups"][GROUP_KEY]
    assert group["checked"] == 4
    assert group["passed"] == 3
    assert group["failed"] == 1
    assert group["delivered"] == [30, 32, 33]
    assert group["shortfall"] == 7
    assert group["exhausted"] is True
    assert group["outcome_counts"][OUTCOME_PLAN] == 1
    assert payload["passed"] is False

    组判定 = [item for item in payload["verdicts"] if item["fields"].get("group") == GROUP_KEY]
    assert len(组判定) == 1 and 组判定[0]["passed"] is False
    总判定 = [item for item in payload["verdicts"] if item["name"] == "ENV_CHECK"][0]
    assert 总判定["passed"] is False and 总判定["fields"]["shortfall"] == 7
    assert render_verdict_line(总判定).startswith("ENV_CHECK=FAIL ")


def test_limit限制最多核验条数(tmp_path):
    """smoke 用：limit=2 时最多核验 2 条候选，哪怕 need 更大也不再派。"""
    documents = 造文档(range(0, 90))
    seen: list[int] = []

    def checker(job):
        seen.append(job.episode)
        return 造通过结果(job)

    payload = 跑一轮(
        tmp_path,
        documents,
        [EnvCheckPlan(TASK, DIFFICULTY, start=30, need=50, limit=2)],
        checker,
    )

    assert seen == [30, 31]
    group = payload["groups"][GROUP_KEY]
    assert group["checked"] == 2 and group["delivered"] == [30, 31]
    assert group["exhausted"] is True and group["shortfall"] == 48
    assert payload["passed"] is False


# ── 产物 ────────────────────────────────────────────────────────────────────
def 读结果行(tmp_path):
    path = tmp_path / "env_check" / TASK / f"{DIFFICULTY}.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_结果jsonl逐条落盘且不产生h5与视频目录(tmp_path):
    documents = 造文档(range(30, 40))

    def checker(job):
        return 造失败结果("SpecBindingError") if job.episode == 31 else 造通过结果(job)

    payload = 跑一轮(tmp_path, documents, [EnvCheckPlan(TASK, DIFFICULTY, start=30, need=4)], checker)

    rows = 读结果行(tmp_path)
    assert [row["episode"] for row in rows] == sorted(row["episode"] for row in rows)
    # 攒够之后同批在飞的那条也会落盘，只是 counted=false，所以计数只数 counted 行
    assert sum(1 for row in rows if row["counted"]) == payload["groups"][GROUP_KEY]["checked"]
    assert any(not row["counted"] for row in rows)
    第一行 = rows[0]
    assert 第一行["seed"] > 0  # seed 由 SeedLayout("train") 现算，不是占位
    assert 第一行["spec_sha256"] == "sha-0030"
    assert 第一行["outcome"] == OUTCOME_PASS
    assert 第一行["phases"]["reset_s"] == 0.9
    assert 第一行["bound"] == {"gpu": "0", "pid": 4242}
    assert 第一行["injection_bound"] is True
    坏行 = [row for row in rows if row["episode"] == 31][0]
    assert 坏行["outcome"] == OUTCOME_BINDING and 坏行["error_type"] == "SpecBindingError"

    产物 = {item.name for item in tmp_path.rglob("*") if item.is_dir()}
    assert "hdf5_files" not in 产物 and "videos" not in 产物
    assert not list(tmp_path.rglob("*.h5")) and not list(tmp_path.rglob("*.mp4"))
    assert "reset 通过 ≠ 能出 h5" in payload["note"]


def test_env_check模块顶层不import_gymnasium或torch():
    """spawn 子进程会重跑被引用模块的顶层；仿真依赖一旦泄到顶层，_pool_init 的绑卡就晚了。"""
    code = (
        "import importlib, sys\n"
        "importlib.import_module('scripts.injection.env_check')\n"
        "脏 = sorted({'gymnasium', 'torch', 'sapien', 'mani_skill'} & set(sys.modules))\n"
        "print('DIRTY=' + ','.join(脏))\n"
    )
    done = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=True,
    )
    assert "DIRTY=\n" in done.stdout or done.stdout.strip() == "DIRTY="
