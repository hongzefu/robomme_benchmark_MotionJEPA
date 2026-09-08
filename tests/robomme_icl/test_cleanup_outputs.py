"""清理维护工具的可重复安全回归；所有删除只发生在仓库缓存中的假仓库。"""

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace

import h5py
import pytest

from robomme_icl.io.paths import repository_root
import robomme_icl.suite
from scripts.legacy.robomme_icl import cleanup_previous_outputs as cleanup


@pytest.fixture
def scenario(monkeypatch):
    """构造96条最小规格和真实HDF5头；仅替换规格解析与外部进程观察。"""
    cache = repository_root() / ".cache" / "robomme_icl_tests"
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="cleanup-fake-only-", dir=cache) as directory:
        root = Path(directory)
        monkeypatch.setattr(cleanup, "ROOT", root)
        # 本组只测试文件系统删除安全，进程观察不读取测试进程以外的宿主状态。
        monkeypatch.setattr(cleanup, "_active_users", lambda paths: None)
        # 规格校验已有独立测试；此处读取自造最小规格，绝不依赖真实旧套件。
        monkeypatch.setattr(robomme_icl.suite, "load_suite", lambda path: json.loads(Path(path).read_text()))
        run = root / "artifacts/generated/robomme-icl/scripts-v1"
        report = root / "artifacts/reports/robomme-icl/scripts-v1"
        run.mkdir(parents=True)
        report.mkdir(parents=True)
        (run / "suite").mkdir()
        (run / "provenance").mkdir()
        (root / "FIXTURE_ONLY.md").write_text("仅测试用假规格、假媒体及假验收，不能作为正式验收证据。\n")
        suite = {"episodes": [], "certification": {}, "configs": {"test_fixture_only": True}, "suite_hash": "fake-new-suite"}
        verified = []
        for task_index, task in enumerate(cleanup.TASKS):
            for episode in range(24):
                seed = 2_000_000_000 + task_index * 24 + episode
                spec_hash = hashlib.sha256(f"fake-spec-{seed}".encode()).hexdigest()
                spec = {"task_kind": task, "seed": seed, "difficulty": ("easy", "medium", "hard")[episode // 8],
                        "spec_hash": spec_hash, "schedule": {"control_freq": 20}, "test_fixture_only": True}
                certification = {"content_hash": f"fake-content-{seed}", "frame_count": 1,
                                 "render_gpu": seed % 2, "source_frames_equal": True, "record_paths": []}
                suite["episodes"].append(spec)
                suite["certification"][spec_hash] = certification
                videos = []
                for stage in ("cert0", "cert1", "generate", "replay"):
                    base = run / "suite" / stage if stage.startswith("cert") else (run if stage == "generate" else run / "replay")
                    h5 = base / "hdf5_files" / task / f"seed_{seed}.h5"
                    h5.parent.mkdir(parents=True, exist_ok=True)
                    with h5py.File(h5, "w") as handle:
                        handle.attrs.update(complete=True, content_hash=certification["content_hash"])
                        handle.create_group("setup").create_dataset("episode_spec", data=json.dumps(spec))
                        handle.create_group("steps").attrs["length"] = 1
                    if stage.startswith("cert"):
                        certification["record_paths"].append(str(h5))
                        continue
                    staging = h5.parent / ".staging" / h5.name / "attempt_0000.h5"
                    staging.parent.mkdir(parents=True)
                    os.link(h5, staging)
                    video = base / "videos" / task / f"seed_{seed}.mp4"
                    video.parent.mkdir(parents=True, exist_ok=True)
                    video.write_bytes(b"FAKE_VIDEO_FOR_CLEANUP_TEST_ONLY")
                    digest = hashlib.sha256(video.read_bytes()).hexdigest()
                    sidecar = video.with_suffix(".json")
                    sidecar.write_text(json.dumps({"video_sha256": digest, "spec_hash": spec_hash,
                                                   "source_content_hash": certification["content_hash"]}))
                    videos.append({"stage": stage, "path": str(video), "sidecar": str(sidecar), "sha256": digest})
                verified.append({"spec_hash": spec_hash, "task_kind": task, "seed": seed, "strict_equal": True,
                                 "content_hash": certification["content_hash"], "frames": 1,
                                 "render_gpu": certification["render_gpu"], "videos": videos})
        source = deepcopy(suite)
        source["suite_hash"] = "fake-source-suite"
        (run / "suite/suite.json").write_text(json.dumps(suite))
        (run / "provenance/source_suite.json").write_text(json.dumps(source))
        distribution = run / "distributions"
        distribution.mkdir()
        images = []
        for task, stem in zip(cleanup.TASKS, cleanup.STEMS):
            image = distribution / f"{stem}.png"
            image.write_bytes(b"FAKE_IMAGE_FOR_CLEANUP_TEST_ONLY")
            image.with_suffix(".json").write_text("{}")
            images.append({"task_kind": task, "path": str(image), "image_sha256": hashlib.sha256(image.read_bytes()).hexdigest()})
        (distribution / "distribution_summary.json").write_text(json.dumps({"suite_hash": suite["suite_hash"], "episodes_total": 96}))
        verification = {"schema_version": 1, "status": "passed", "test_fixture_only": True,
                        "run_root": str(run), "suite": str(run / "suite/suite.json"),
                        "suite_hash": suite["suite_hash"], "source_suite_hash": source["suite_hash"],
                        "episodes": 96, "hdf5_verified": 384, "videos_verified": 192,
                        "source_specs_unchanged": True, "configs_unchanged": True, "strict_original_frames_equal": True,
                        "episodes_verified": verified, "frames_per_pass": 96,
                        "figures": {"image_count": 4, "actual_counts_equal": True, "position_coverage_equal": True, "figures": images}}

        def save_verification(value):
            """只为本假仓库写带摘要的凭证，不向正式报告目录写入。"""
            (report / "verification.json").write_text(json.dumps(cleanup._signed(value)))

        save_verification(verification)
        old = root / "artifacts/generated/robomme-icl/old-fixture"
        old.mkdir()
        (old / "old.h5").write_bytes(b"FAKE_OLD_HDF5")
        unlisted = old.parent / "unlisted-fixture"
        unlisted.mkdir()
        (unlisted / "must-remain.log").write_text("未列入库存，不得删除")
        reference = root / "data/robomme_data_h5/reference-fixture.h5"
        reference.parent.mkdir(parents=True)
        reference.write_bytes(b"FAKE_REFERENCE_MUST_REMAIN")
        (old / "reference-link").symlink_to(reference)
        inventory = report / "inventory.json"

        def save_inventory(path=old):
            """只改变库存测试输入，不能自动扩展删除范围。"""
            inventory.write_text(json.dumps({"schema_version": 1, "repository_root": str(root),
                                            "candidates": [{"path": str(path), "relative_path": path.relative_to(root).as_posix(),
                                                            "type": "directory", "apparent_file_bytes": 0}]}))

        save_inventory()
        yield SimpleNamespace(root=root, run=run, report=report, old=old, unlisted=unlisted, reference=reference,
                              inventory=inventory, verification=verification, save_verification=save_verification,
                              save_inventory=save_inventory)


def test_default_cleanup_only_plans_and_preserves_every_candidate(scenario):
    """默认入口真实走完整门禁和盘点，但不删除候选或创建执行结果。"""
    before = (scenario.old / "old.h5").read_bytes()
    result = cleanup.cleanup(scenario.inventory, scenario.run, scenario.report)
    assert result["status"] == "planned"
    assert (scenario.old / "old.h5").read_bytes() == before
    assert (scenario.old / "reference-link").is_symlink()
    assert scenario.unlisted.is_dir()
    assert (scenario.report / "cleanup-plan.json").is_file()
    assert not (scenario.report / "cleanup-result.json").exists()


def test_apply_only_deletes_listed_artifacts_without_following_symlinks(scenario):
    """显式执行仅清除库存中的假目录；未列出的目录及链接目标完整保留。"""
    reference = scenario.reference.read_bytes()
    cleanup.cleanup(scenario.inventory, scenario.run, scenario.report)
    result = cleanup.cleanup(scenario.inventory, scenario.run, scenario.report, apply=True)
    assert result["status"] == "passed"
    assert not scenario.old.exists()
    assert scenario.reference.read_bytes() == reference
    assert (scenario.unlisted / "must-remain.log").read_text() == "未列入库存，不得删除"
    receipt = cleanup._read_signed(scenario.report / "cleanup-result.json")
    assert {Path(row["path"]).name for row in receipt["deletions"]} == {"old-fixture", "old.h5", "reference-link"}
    assert receipt["completed_roots"] == [str(scenario.old)]
    assert sum(path.is_file() for path in (scenario.run / "hdf5_files").rglob("*.h5")) == 192


@pytest.mark.parametrize("relative", [
    "data/robomme_data_h5", "artifacts/generated", "artifacts/generated/robomme-icl/scripts-v1",
    "artifacts/reports", ".cache/uv", ".cache/maniskill", "src", "scripts/_icl",
])
def test_protected_data_new_batch_ancestors_and_dependencies_are_rejected(scenario, relative):
    """即使把保护目录写进库存并指定apply，也不能开始删除。"""
    scenario.save_inventory(scenario.root / relative)
    with pytest.raises(ValueError):
        cleanup.cleanup(scenario.inventory, scenario.run, scenario.report, apply=True)
    assert scenario.reference.read_bytes() == b"FAKE_REFERENCE_MUST_REMAIN"
    assert (scenario.old / "old.h5").exists()
    assert not (scenario.report / "cleanup-plan.json").exists()


def test_staging_hardlinks_are_excluded_but_unknown_published_hdf5_blocks_cleanup(scenario):
    """真实门禁接受隐藏重试硬链接，但额外的正式文件必须阻止清理。"""
    assert sum(path.is_file() for path in (scenario.run / "hdf5_files").rglob("*.h5")) == 192
    cleanup.cleanup(scenario.inventory, scenario.run, scenario.report)
    unknown = scenario.run / "hdf5_files/UNKNOWN.h5"
    unknown.write_bytes(b"UNKNOWN_PUBLISHED_HDF5")
    with pytest.raises(ValueError, match="正式文件集合不同"):
        cleanup.cleanup(scenario.inventory, scenario.run, scenario.report, apply=True)
    assert unknown.read_bytes() == b"UNKNOWN_PUBLISHED_HDF5"
    assert scenario.old.exists()
    assert not (scenario.report / "cleanup-result.json").exists()


@pytest.mark.parametrize("key,value", [("status", "failed"), ("episodes", 95), ("videos_verified", 191)])
def test_incomplete_signed_verification_blocks_cleanup(scenario, key, value):
    """自造报告即使摘要正确，只要未完整通过仍不能删除。"""
    scenario.verification[key] = value
    scenario.save_verification(scenario.verification)
    with pytest.raises(ValueError):
        cleanup.cleanup(scenario.inventory, scenario.run, scenario.report, apply=True)
    assert (scenario.old / "old.h5").exists()
    assert not (scenario.report / "cleanup-plan.json").exists()


def test_unsigned_verification_blocks_cleanup(scenario):
    """删除摘要字段后，真实门禁拒绝凭证，不接受仅有passed文字。"""
    (scenario.report / "verification.json").write_text(json.dumps(scenario.verification))
    with pytest.raises(ValueError, match="报告摘要不符"):
        cleanup.cleanup(scenario.inventory, scenario.run, scenario.report, apply=True)
    assert scenario.old.exists()


def test_source_file_in_candidate_blocks_cleanup(scenario):
    """库存目录中混入源码时整体停止，不能为了清理数据顺便删除代码。"""
    source = scenario.old / "must_keep.py"
    source.write_text("VALUE = 1\n")
    with pytest.raises(ValueError, match="候选混入源码"):
        cleanup.cleanup(scenario.inventory, scenario.run, scenario.report, apply=True)
    assert source.read_text() == "VALUE = 1\n"
    assert (scenario.old / "old.h5").exists()


def test_symlink_ancestor_is_rejected_before_deletion(scenario):
    """库存路径通过符号链接转向另一目录时，逐层路径检查直接拒绝。"""
    link = scenario.old.parent / "alias-fixture"
    link.symlink_to(scenario.old, target_is_directory=True)
    scenario.save_inventory(link)
    with pytest.raises(ValueError, match="符号链接"):
        cleanup.cleanup(scenario.inventory, scenario.run, scenario.report, apply=True)
    assert scenario.old.exists() and scenario.reference.exists()


def test_changed_plan_refuses_apply_without_overwriting_evidence(scenario):
    """计划后出现新文件时，第二次调用必须保留旧计划和所有候选。"""
    cleanup.cleanup(scenario.inventory, scenario.run, scenario.report)
    plan = (scenario.report / "cleanup-plan.json").read_bytes()
    added = scenario.old / "new-unknown.log"
    added.write_text("计划之后出现的内容")
    with pytest.raises(ValueError, match="已有清理计划"):
        cleanup.cleanup(scenario.inventory, scenario.run, scenario.report, apply=True)
    assert (scenario.report / "cleanup-plan.json").read_bytes() == plan
    assert added.exists() and (scenario.old / "old.h5").exists()
