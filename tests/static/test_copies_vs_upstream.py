"""L0：hard 包的三个录制复制件与官方只差白名单；``UPSTREAM.json`` 的 shim 与自签 sha 成立（C01 shim 部分、C18）。

官方一侧一律从 git 对象 ``<src_commit>:src/robomme/...`` 读，不依赖工作区 ``src/robomme`` 的状态。
白名单按行精确列出（删去的行、加入的行），任何额外差异——包括注释——都算越界。
"""
from __future__ import annotations

import difflib
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from tests._support.loaders import REPO

HARD = REPO / "src" / "robomme_hard"
MANIFEST = HARD / "UPSTREAM.json"

#: 复制件 → 与官方逐行差异白名单：[(官方删去的行, 复制件加入的行), ...]，按出现顺序。
WHITELIST: dict[str, list[tuple[list[str], list[str]]]] = {
    "env_record_wrapper/RecordWrapper.py": [
        (
            [
                "        # Force terminate episode if environment steps exceed preset safety limit (2000 steps)",
                "        fail_safe_limit = 2000",
            ],
            [
                "        # Force terminate episode if environment steps exceed preset safety limit (原 2000 steps，V4 起 5000)",
                "        # V4（2026-09-22 用户明确授权解冻此一处：「录像放开2000步 改为5000步」）：",
                "        # PickXtimes xhard num 取到 15 时演示约 136+138×num≈2206 步，原 2000 步上限必然误杀。",
                "        # 原三档成功局都在 2000 步内结束，放宽上限不改变它们的任何产物（V1 本机前后对比验证）。",
                "        fail_safe_limit = 5000",
            ],
        ),
        (
            ["                from robomme.robomme_env.utils.vqa_options import get_vqa_options"],
            ["                from robomme_hard.robomme_env.utils.vqa_options import get_vqa_options"],
        ),
    ],
    "env_record_wrapper/OraclePlannerDemonstrationWrapper.py": [
        (
            ["from robomme.robomme_env.utils.vqa_options import get_vqa_options"],
            ["from robomme_hard.robomme_env.utils.vqa_options import get_vqa_options"],
        ),
    ],
    "env_record_wrapper/DemonstrationWrapper.py": [],
}


def _manifest_raw() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _git_show(commit: str, rel: str) -> bytes:
    return subprocess.run(["git", "show", f"{commit}:{rel}"], cwd=REPO, check=True, capture_output=True).stdout


def line_diff(official: str, copy: str) -> list[tuple[list[str], list[str]]]:
    """逐行差异块：[(官方删去的行, 复制件加入的行)]（不含相同部分）。"""
    a, b = official.splitlines(), copy.splitlines()
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    return [(a[i1:i2], b[j1:j2]) for tag, i1, i2, j1, j2 in sm.get_opcodes() if tag != "equal"]


@pytest.mark.parametrize("rel", sorted(WHITELIST))
def test_copy_differs_from_official_exactly_by_whitelist(rel):
    src_commit = _manifest_raw()["src_commit"]
    official = _git_show(src_commit, f"src/robomme/{rel}").decode()
    copy = (HARD / rel).read_text(encoding="utf-8")
    assert line_diff(official, copy) == WHITELIST[rel]
    if not WHITELIST[rel]:
        # 逐字节相同（连行尾与文件末换行）。
        assert (HARD / rel).read_bytes() == official.encode()


def test_line_diff_detects_reverted_limit_and_extra_comment():
    """判定器负例：把 5000 改回 2000、或多加一行注释，差异都不再等于白名单。"""
    rel = "env_record_wrapper/RecordWrapper.py"
    official = _git_show(_manifest_raw()["src_commit"], f"src/robomme/{rel}").decode()
    copy = (HARD / rel).read_text(encoding="utf-8")
    assert line_diff(official, copy.replace("fail_safe_limit = 5000", "fail_safe_limit = 2000")) != WHITELIST[rel]
    assert line_diff(official, copy.replace("import gymnasium", "# 多一行\nimport gymnasium", 1)) != WHITELIST[rel]
    assert line_diff(official, official) == []


# ---------------------------------------------------------------- UPSTREAM.json


def test_manifest_self_signature_holds():
    m = _manifest_raw()
    claimed = m.pop("manifest_sha256")
    canonical = json.dumps(m, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    assert hashlib.sha256(canonical.encode()).hexdigest() == claimed


def test_manifest_signature_detects_tamper():
    m = _manifest_raw()
    claimed = m.pop("manifest_sha256")
    m["shims"] = m["shims"][1:]
    canonical = json.dumps(m, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    assert hashlib.sha256(canonical.encode()).hexdigest() != claimed


SHIM_IMPORT = "import importlib, sys"


def _shim_files() -> set[str]:
    """hard 包里形态上是 shim 的文件（含 ``sys.modules[__name__] = importlib.import_module``）。"""
    out = set()
    for p in HARD.rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        if "sys.modules[__name__] = importlib.import_module(" in p.read_text(encoding="utf-8"):
            out.add(str(p.relative_to(REPO)))
    return out


def test_shim_registry_equals_shim_files_on_disk():
    m = _manifest_raw()
    registered = [s["shim"] for s in m["shims"]]
    assert len(registered) == len(set(registered))
    assert set(registered) == _shim_files()


@pytest.mark.parametrize("entry", _manifest_raw()["shims"], ids=lambda e: e["target_module"])
def test_shim_form_and_target(entry):
    m = _manifest_raw()
    path = REPO / entry["shim"]
    lines = path.read_text(encoding="utf-8").splitlines()
    # 恰好三行：一行注释（指向本清单）、导入、别名；多一行少一行都不行。
    assert len(lines) == 3, lines
    assert lines[0].startswith("# 借用：")
    rel_manifest = lines[0].rsplit("清单见 ", 1)[1].strip()
    assert (path.parent / rel_manifest).resolve() == MANIFEST.resolve()
    assert lines[1] == SHIM_IMPORT
    assert lines[2] == f'sys.modules[__name__] = importlib.import_module("{entry["target_module"]}")'
    # shim 在 hard 包里的位置与目标模块同名同层。
    mod = entry["target_module"]
    assert entry["shim"] == "src/robomme_hard/" + mod.split(".", 1)[1].replace(".", "/") + ".py"
    assert entry["target_file"] == "src/" + mod.replace(".", "/") + ".py"
    # 目标文件的 sha 与字节数对官方 git 对象独立复算。
    blob = _git_show(m["src_commit"], entry["target_file"])
    assert entry["target_sha256"] == hashlib.sha256(blob).hexdigest()
    assert entry["target_bytes"] == len(blob)
    assert m["robomme_files"][entry["target_file"]] == entry["target_sha256"]
