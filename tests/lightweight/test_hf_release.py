"""``scripts/hf_release.py``（HF dataset 发布链路）的定向测试。

全部**脱网、秒级**：真实交付清单只读 JSON（不碰 844 GiB 的 h5），端到端打包只在
``tmp_path`` 里拿 2 KB 假 h5 走一遍 ``tar | xz`` 全流程。

盯住四条最贵的错：

* **散列来源**——``MANIFEST.json`` 的 ``h5_sha256`` 必须逐字抄交付清单，发布时绝不重算；
* **成员路径**——包内路径必须是固定的 ``<top_dir>/hdf5_files/<名>``，任何能写到包外的名字硬失败；
* **归包唯一**——同一 (任务, 难度, episode) 只能出现在一个包里，1600+196 条一条不多一条不少；
* **顺序守卫**——缺前置产物就直接停，不允许拿半成品去上传。
"""

from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
for _extra in (REPO_ROOT, REPO_ROOT / "src"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

from scripts.hf_release import (  # noqa: E402
    DEFAULT_REPO_ID,
    DEFAULT_RUN_ID,
    EXPECTED_PRIMARY,
    EXPECTED_SPARE,
    ArchivePlan,
    ReleaseError,
    ReleaseLayout,
    StagedFile,
    archive_rel_path,
    archive_top_dir,
    build_archive,
    build_manifest,
    compare_digests,
    git_blob_sha1,
    load_delivery,
    make_layout,
    member_path,
    plan_archives,
    render_readme,
    render_sha256sums,
    render_tarxz_script,
    render_verdict_line,
    sha256_file,
    stage,
    upload,
    verify_archive_members,
    verify_local,
    verify_remote,
    write_manifest_files,
)

RUN_ROOT = REPO_ROOT / "artifacts" / "injection" / DEFAULT_RUN_ID
DELIVERY_CONFIG = REPO_ROOT / "scripts" / "configs" / "newtask-v2" / "delivery_400.json"


def _real_delivery():
    if not (RUN_ROOT / "delivery_manifest.json").is_file():
        pytest.skip(f"本机没有运行 {DEFAULT_RUN_ID} 的交付清单")
    return load_delivery(RUN_ROOT)


def _mini_delivery() -> dict:
    """手搓一份最小交付清单：一组、一条 primary，够 build_manifest 用。"""
    return {
        "run_id": "mini", "hash_mode": "full", "passed": True,
        "config": {"sha256": "c" * 64},
        "groups": {
            "BinFill/easy": {
                "primary": [{
                    "task": "BinFill", "difficulty": "easy", "episode": 0, "seed": 4000,
                    "spec_sha256": "s" * 64,
                    "h5_path": "feasibility/P01x20/BinFill/easy/hdf5_files/BinFill_ep0_seed4000.h5",
                    "bytes": 2048, "sha256": "a" * 64, "timestep_count": 7,
                    "video_status": "complete", "role": "primary",
                }],
                "spare_rows": [],
                "failures": [{"episode": 1, "outcome": "规划失败", "error_type": "DatasetGenerationError"}],
            }
        },
    }


def _mini_layout(tmp_path: Path) -> ReleaseLayout:
    return ReleaseLayout(
        repo_id=DEFAULT_REPO_ID, run_id="mini", run_root=tmp_path / "run",
        staging=tmp_path / "staging", repo_root=tmp_path / "repo",
        git_commit="deadbeef", git_branch="newtask-v2",
    )


# ── 1 命名与成员路径 ────────────────────────────────────────────────────────
def test_归档命名与成员路径规范():
    assert archive_rel_path("BinFill", "easy", "primary") == "record_dataset_BinFill_easy.h5.tar.xz"
    assert archive_rel_path("BinFill", "easy", "spare") == "spare/record_dataset_BinFill_easy_spare.h5.tar.xz"
    assert archive_rel_path("RouteStick", "easy", "smoke") == "smoke/record_dataset_RouteStick_easy_smoke.h5.tar.xz"
    assert archive_top_dir("BinFill", "easy", "primary") == "record_dataset_BinFill_easy"
    assert archive_top_dir("BinFill", "easy", "spare") == "record_dataset_BinFill_easy_spare"
    assert archive_top_dir("RouteStick", "easy", "smoke") == "record_dataset_RouteStick_easy_smoke"
    with pytest.raises(ReleaseError):
        archive_rel_path("BinFill", "easy", "bonus")

    top = archive_top_dir("BinFill", "easy", "primary")
    assert member_path(top, "BinFill_ep0_seed4000.h5") == f"{top}/hdf5_files/BinFill_ep0_seed4000.h5"
    # 一切能把文件写到包外的名字都必须硬失败
    for bad in ("../escape.h5", "/abs.h5", "", "  ", "sub/dir.h5", ".."):
        with pytest.raises(ReleaseError):
            member_path(top, bad)
    for bad_top in ("../x", "/abs", "", "a/b"):
        with pytest.raises(ReleaseError):
            member_path(bad_top, "ok.h5")


# ── 2 真实交付清单展开 ──────────────────────────────────────────────────────
def test_真实交付清单展开为二十八个包且每条episode恰归一包():
    delivery = _real_delivery()
    plans = plan_archives(delivery, RUN_ROOT, include_smoke=False, check_exists=False)
    assert len(plans) == 28, "14 组 × (primary + spare) = 28 个包"

    primary = [plan for plan in plans if plan.role == "primary"]
    spare = [plan for plan in plans if plan.role == "spare"]
    assert sum(len(plan.rows) for plan in primary) == EXPECTED_PRIMARY == 1600
    assert sum(len(plan.rows) for plan in spare) == EXPECTED_SPARE == 196

    # 组序与 delivery_400.json 一致
    config_groups = [
        (group["task"], group["difficulty"])
        for group in json.loads(DELIVERY_CONFIG.read_text(encoding="utf-8"))["groups"]
    ]
    assert [(plan.task, plan.difficulty) for plan in primary] == config_groups
    assert [(plan.task, plan.difficulty) for plan in spare] == config_groups

    # 每条 (任务, 难度, episode) 恰归一包；组内按 episode 升序
    owner: dict[tuple[str, str, int], str] = {}
    for plan in plans:
        episodes = [int(row["episode"]) for row in plan.rows]
        assert episodes == sorted(episodes), f"{plan.rel_path} 未按 episode 升序"
        for episode in episodes:
            key = (plan.task, plan.difficulty, episode)
            assert key not in owner, f"{key} 同时出现在 {owner.get(key)} 与 {plan.rel_path}"
            owner[key] = plan.rel_path
    assert len(owner) == EXPECTED_PRIMARY + EXPECTED_SPARE

    # 成员数 = h5 条数 + 1 份组 metadata.json，且包内路径都带 top_dir 前缀
    for plan in plans:
        assert len(plan.members) == len(plan.rows) + 1
        assert all(member.startswith(plan.top_dir + "/") for _, member in plan.members)
        assert plan.members[-1][1].endswith(f"record_dataset_{plan.task}_metadata.json")


# ── 3 散列来源 ──────────────────────────────────────────────────────────────
def test_MANIFEST的h5散列逐字来自交付清单(tmp_path):
    layout = _mini_layout(tmp_path)
    delivery = _mini_delivery()
    plans = plan_archives(delivery, layout.run_root, include_spare=False, include_smoke=False, check_exists=False)
    manifest = build_manifest(layout, delivery, plans, {}, [], [], {}, generated_utc="2026-09-12T00:00:00+00:00")

    assert len(manifest["episodes"]) == 1
    assert manifest["episodes"][0]["h5_sha256"] == "a" * 64
    assert manifest["episodes"][0]["member"] == "record_dataset_BinFill_easy/hdf5_files/BinFill_ep0_seed4000.h5"
    assert manifest["failures"][0]["task"] == "BinFill"

    # 改交付清单里的一位散列，MANIFEST 就跟着变——证明是抄过来的，不是重算的
    mutated = _mini_delivery()
    mutated["groups"]["BinFill/easy"]["primary"][0]["sha256"] = "b" + "a" * 63
    plans2 = plan_archives(mutated, layout.run_root, include_spare=False, include_smoke=False, check_exists=False)
    manifest2 = build_manifest(layout, mutated, plans2, {}, [], [], {}, generated_utc="2026-09-12T00:00:00+00:00")
    assert manifest2["episodes"][0]["h5_sha256"] == "b" + "a" * 63
    assert manifest2 != manifest

    # 缺 sha256 时宁可停，也不现场重算一个
    broken = _mini_delivery()
    broken["groups"]["BinFill/easy"]["primary"][0].pop("sha256")
    plans3 = plan_archives(broken, layout.run_root, include_spare=False, include_smoke=False, check_exists=False)
    with pytest.raises(ReleaseError, match="sha256"):
        build_manifest(layout, broken, plans3, {}, [], [], {})


# ── 4 SHA256SUMS ────────────────────────────────────────────────────────────
def test_SHA256SUMS格式并可被sha256sum回读(tmp_path):
    files = []
    for name, payload in (("b.txt", b"bbb"), ("a/x.bin", b"xxxx"), ("c.txt", b"c")):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        files.append(StagedFile(
            rel_path=name, src=path, bytes=len(payload),
            sha256=hashlib.sha256(payload).hexdigest(), kind="meta",
        ))
    # SHA256SUMS 自身不入表
    files.append(StagedFile(rel_path="SHA256SUMS", src=None, bytes=0, sha256="f" * 64, kind="doc"))

    text = render_sha256sums(files)
    assert text.endswith("\n") and "\r" not in text
    lines = text.splitlines()
    assert [line.split("  ", 1)[1] for line in lines] == ["a/x.bin", "b.txt", "c.txt"]
    assert all(line[64:66] == "  " for line in lines)

    (tmp_path / "SHA256SUMS").write_text(text, encoding="utf-8")
    done = subprocess.run(["sha256sum", "-c", "SHA256SUMS"], cwd=tmp_path, capture_output=True, text=True)
    assert done.returncode == 0, done.stdout + done.stderr

    with pytest.raises(ReleaseError):
        render_sha256sums([StagedFile(rel_path="z", src=None, bytes=1, sha256="", kind="meta")])


# ── 5 mini 端到端打包 ───────────────────────────────────────────────────────
def _mini_group(tmp_path: Path) -> tuple[ArchivePlan, dict[str, str]]:
    """在 tmp_path 里造一个两条 2 KB 假 h5 的组，返回计划与「成员 → sha256」期望表。"""
    source = tmp_path / "run" / "feasibility" / "P01x20" / "Mini" / "easy"
    (source / "hdf5_files").mkdir(parents=True)
    top = archive_top_dir("Mini", "easy", "primary")
    rows, members, expected = [], [], {}
    for episode, seed in ((0, 4000), (1, 4100)):
        name = f"Mini_ep{episode}_seed{seed}.h5"
        payload = bytes([episode]) * 2048
        (source / "hdf5_files" / name).write_bytes(payload)
        rows.append({
            "task": "Mini", "difficulty": "easy", "episode": episode, "seed": seed,
            "spec_sha256": "s" * 64, "h5_path": f"hdf5_files/{name}", "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(), "timestep_count": 3, "role": "primary",
        })
        members.append((source / "hdf5_files" / name, member_path(top, name)))
        expected[member_path(top, name)] = hashlib.sha256(payload).hexdigest()
    meta_name = "record_dataset_Mini_metadata.json"
    meta_payload = json.dumps({"episodes": 2}).encode("utf-8")
    (source / meta_name).write_bytes(meta_payload)
    members.append((source / meta_name, f"{top}/{meta_name}"))
    expected[f"{top}/{meta_name}"] = hashlib.sha256(meta_payload).hexdigest()

    plan = ArchivePlan(
        task="Mini", difficulty="easy", role="primary", rows=tuple(rows),
        rel_path=archive_rel_path("Mini", "easy", "primary"), top_dir=top,
        source_dir=source, members=tuple(members),
    )
    return plan, expected


def test_mini端到端打包与流式核验(tmp_path):
    plan, expected = _mini_group(tmp_path)
    dest = tmp_path / "staging" / plan.rel_path
    result = build_archive(plan, dest, preset=0, threads=1)

    assert dest.is_file()
    assert result.bytes == dest.stat().st_size
    assert result.sha256 == sha256_file(dest), "返回的 sha256 必须等于对落盘文件重算的结果"
    assert result.member_count == 3
    sidecar = dest.with_name(dest.name + ".sha256")
    assert sidecar.read_text(encoding="utf-8") == f"{result.sha256}  {dest.name}\n"

    listing = subprocess.run(["tar", "-tJf", str(dest)], capture_output=True, text=True, check=True)
    names = [line for line in listing.stdout.splitlines() if line]
    assert names == [member for _, member in plan.members], "包内成员顺序须与计划一致（episode 升序，metadata 垫底）"

    report = verify_archive_members(dest, expected)
    assert report["mismatch"] == [] and report["missing"] == [] and report["extra"] == []
    assert len(report["matched"]) == 3

    # 篡改期望表后，mismatch 必须点名到具体成员
    tampered = dict(expected)
    victim = member_path(plan.top_dir, "Mini_ep1_seed4100.h5")
    tampered[victim] = "0" * 64
    bad = verify_archive_members(dest, tampered)
    assert [item["member"] for item in bad["mismatch"]] == [victim]

    # 源目录之外的成员一律拒绝
    stray = ArchivePlan(
        task="Mini", difficulty="easy", role="primary", rows=plan.rows,
        rel_path=plan.rel_path, top_dir=plan.top_dir, source_dir=plan.source_dir,
        members=((tmp_path / "outside.h5", f"{plan.top_dir}/outside.h5"),),
    )
    with pytest.raises(ReleaseError):
        build_archive(stray, tmp_path / "staging" / "stray.tar.xz", preset=0, threads=1)


# ── 6 远端摘要比对 ──────────────────────────────────────────────────────────
def test_远端摘要比对五种情形():
    blob = git_blob_sha1(b"hello")
    local = {
        "big_ok.tar.xz": "1" * 64,      # LFS 且一致
        "small_ok.json": "2" * 64,      # 非 LFS，靠 blob sha1 对上
        "big_bad.tar.xz": "3" * 64,     # LFS 但散列不符
        "gone.mp4": "4" * 64,           # 远端根本没有
    }
    remote = {
        "big_ok.tar.xz": {"lfs_sha256": "1" * 64, "blob_id": "x", "size": 10},
        "small_ok.json": {"lfs_sha256": None, "blob_id": blob, "size": 5},
        "big_bad.tar.xz": {"lfs_sha256": "9" * 64, "blob_id": "y", "size": 10},
        "surprise.txt": {"lfs_sha256": None, "blob_id": "z", "size": 1},  # 本地没有
    }
    report = compare_digests(local, remote, {"small_ok.json": blob})
    assert report["lfs_sha_match"] == 1
    assert report["blob_match"] == 1
    assert [item["path"] for item in report["mismatch"]] == ["big_bad.tar.xz"]
    assert report["missing"] == ["gone.mp4"]
    assert report["extra"] == ["surprise.txt"]


# ── 7 git blob sha1 ─────────────────────────────────────────────────────────
def test_git_blob_sha1与git_hash_object一致(tmp_path):
    for payload in (b"", b"hello\n", bytes(range(256)) * 7):
        path = tmp_path / "blob.bin"
        path.write_bytes(payload)
        done = subprocess.run(
            ["git", "hash-object", "--", str(path)], capture_output=True, text=True, check=True
        )
        assert git_blob_sha1(payload) == done.stdout.strip()


# ── 8 判定行 ────────────────────────────────────────────────────────────────
def test_判定行格式():
    line = render_verdict_line({"name": "HF_PLAN", "passed": True, "fields": {"archives": 29, "primary": 1600}})
    assert line == "HF_PLAN=PASS archives=29 primary=1600"
    assert render_verdict_line({"name": "HF_PACK", "passed": False, "fields": {"failed": 2}}) == "HF_PACK=FAIL failed=2"
    assert render_verdict_line({"name": "HF_UPLOAD", "passed": True, "fields": {}}) == "HF_UPLOAD=PASS"


# ── 9 顺序守卫 ──────────────────────────────────────────────────────────────
def test_顺序守卫(tmp_path):
    layout = _mini_layout(tmp_path)
    layout.staging.mkdir(parents=True)

    # stage 需要 pack 的断点
    with pytest.raises(ReleaseError, match="pack"):
        stage(layout, "skip", False)
    # manifest 需要 stage 的断点
    with pytest.raises(ReleaseError, match="stage"):
        write_manifest_files(layout)
    # verify-local 需要 MANIFEST.json
    with pytest.raises(ReleaseError, match="manifest"):
        verify_local(layout)
    # upload 需要 manifest 写下的冻结快照
    with pytest.raises(ReleaseError, match="manifest"):
        upload(layout)
    # verify-remote 需要上传断点
    with pytest.raises(ReleaseError, match="upload"):
        verify_remote(layout)

    # 冻结快照对不上（归档被改动）时也要停
    (layout.release_dir).mkdir(parents=True, exist_ok=True)
    (layout.staging / "a.tar.xz").write_bytes(b"xx")
    (layout.release_dir / "freeze.json").write_text(
        json.dumps({"archives": {"a.tar.xz": [999, 1]}}), encoding="utf-8"
    )
    with pytest.raises(ReleaseError, match="冻结"):
        upload(layout)


# ── 10 README ───────────────────────────────────────────────────────────────
def test_readme含关键说明(tmp_path):
    layout = _mini_layout(tmp_path)
    delivery = _mini_delivery()
    plans = plan_archives(delivery, layout.run_root, include_spare=False, include_smoke=False, check_exists=False)
    manifest = build_manifest(layout, delivery, plans, {}, [], [], {})
    readme = render_readme(manifest, layout)

    assert readme.startswith("---\n")
    assert "license: apache-2.0" in readme
    assert "task_categories:" in readme and "robotics" in readme
    # 与官方数据集的形状差别必须醒目
    assert "Yinpei/robomme_data_h5" in readme
    assert "episode_0" in readme and "逐条 h5" in readme
    # 解压与校验命令
    assert "python tarxz_h5.py decompress --input_dir . --jobs 8" in readme
    assert "tar -xJf" in readme
    assert "sha256sum -c SHA256SUMS" in readme
    # 视频口径三条
    assert "success_NO_OBJECT_" in readme
    assert "没有录像" in readme and "只有录像、没有 h5" in readme
    # 回指私有 git 仓库
    assert "https://github.com/hongzefu/robomme_benchmark_MotionJEPA" in readme
    assert "私有" in readme
    assert layout.git_branch in readme and layout.git_commit in readme


# ── 11 tarxz_h5.py ──────────────────────────────────────────────────────────
def test_tarxz脚本可解析且含两个子命令():
    source = render_tarxz_script()
    tree = ast.parse(source)
    assert any(isinstance(node, ast.FunctionDef) and node.name == "main" for node in tree.body)
    assert '"compress"' in source and '"decompress"' in source
    assert "--input_dir" in source and "--jobs" in source
    assert "--remove_archive" in source and "--remove_original" in source
    # 解包前要防路径穿越
    assert ".." in source and "拒绝越界成员" in source
    # 自包含：只 import 标准库
    imported = {
        node.names[0].name.split(".")[0] if isinstance(node, ast.Import) else (node.module or "").split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
    }
    assert imported <= {"__future__", "argparse", "multiprocessing", "os", "sys", "tarfile", "pathlib", "shutil"}


def test_默认布局指向正确的运行根与staging():
    layout = make_layout()
    assert layout.run_id == DEFAULT_RUN_ID and layout.repo_id == DEFAULT_REPO_ID
    assert layout.run_root == REPO_ROOT / "artifacts" / "injection" / DEFAULT_RUN_ID
    assert layout.staging == REPO_ROOT / "artifacts" / "hf-staging" / "robomme-4task-h5-20260912-v2"
    assert layout.release_dir.name == ".release"
