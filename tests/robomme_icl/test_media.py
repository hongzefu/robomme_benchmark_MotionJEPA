"""用真实 FFmpeg 和小型场景清单检查视频、分布图的保存及断点恢复。"""

import copy
import json
from pathlib import Path
import subprocess
import tempfile

import numpy as np
import pytest

from robomme_icl.io.hdf5 import read_episode, tree_hash, write_episode
from robomme_icl.io.paths import repository_root
from robomme_icl.suite import candidate_for_slot, load_configs, plan_slots, save_suite
from scripts._icl import plots, video


@pytest.fixture
def local_dir():
    """所有媒体测试产物都保存在本仓库缓存，退出只清理本 fixture 的目录。"""
    cache = repository_root() / ".cache" / "robomme_icl_tests"
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=cache, prefix="media-") as directory:
        yield Path(directory)


@pytest.fixture
def synthetic_record(local_dir):
    """构造短片专用记录，测试保存过程，不冒充仿真认证。"""
    spec = {
        "seed": 2_000_000_000,
        "env_id": "RoboMME-ICL/BinFill-v0",
        "schedule": {"control_freq": 20},
    }
    spec["spec_hash"] = tree_hash(spec)
    frames = []
    for index in range(8):
        frames.append(
            {
                "observation": {
                    "base_rgb": np.full(
                        (256, 256, 3), (30 + index, 80, 100), dtype=np.uint8
                    ),
                    "wrist_rgb": np.full(
                        (256, 256, 3), (100, 100 + index, 40), dtype=np.uint8
                    ),
                },
                "joint_action": np.arange(8, dtype=np.float64),
                "info": {
                    "is_demonstration": index < 4,
                    "step": index,
                    "success": index == 7,
                    "operation": "step",
                    "deliver_frame": True,
                },
            }
        )
    marker = copy.deepcopy(frames[0])
    marker["info"].update(
        operation="reset_complete",
        deliver_frame=False,
        native_runtime={"control_freq": 20},
    )
    frames.append(marker)
    return write_episode(local_dir / "source.h5", spec, frames)


def test_compose_frame_has_red_border_without_mutating_source():
    frame = {
        "observation": {
            "base_rgb": np.full((256, 256, 3), 80, dtype=np.uint8),
            "wrist_rgb": np.full((256, 256, 3), 120, dtype=np.uint8),
        },
        "info": {"is_demonstration": True},
    }
    before = tree_hash(frame)
    result = video.compose_frame(frame)
    assert result.shape == (256, 512, 3)
    assert np.all(result[:6] == np.array([255, 0, 0], dtype=np.uint8))
    assert np.all(result[10:20, 10:20] == 80)
    assert tree_hash(frame) == before
    assert not np.shares_memory(result, frame["observation"]["base_rgb"])


def test_real_video_export_verify_resume_and_missing_video_rebuild(
    local_dir, synthetic_record
):
    before = video._sha256(synthetic_record)
    target = local_dir / "videos" / "seed_2000000000.mp4"
    first = video.export_video(synthetic_record, target)
    assert first["verification"] == {
        "frames": 8,
        "fps": 20,
        "width": 512,
        "height": 256,
        "decodable": True,
    }
    assert first["resumed"] is False
    assert (
        json.loads(target.with_suffix(".json").read_text())["source_content_hash"]
        == read_episode(synthetic_record).content_hash
    )
    second = video.export_video(synthetic_record, target)
    assert second["resumed"] is True
    assert first["video_sha256"] == second["video_sha256"]
    target.unlink()
    restored = video.export_video(synthetic_record, target)
    assert restored["video_sha256"] == first["video_sha256"]
    assert video._sha256(synthetic_record) == before
    decoded = subprocess.run(
        [
            video.FFMPEG,
            "-v",
            "error",
            "-threads",
            "1",
            "-i",
            str(target),
            "-frames:v",
            "1",
            "-threads",
            "1",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "pipe:1",
        ],
        capture_output=True,
        check=True,
    ).stdout
    rgb = np.frombuffer(decoded, dtype=np.uint8).reshape(256, 512, 3)
    assert rgb[0, 0, 0] > 200 and rgb[0, 0, 1] < 40


def test_video_unknown_output_and_tampering_are_rejected(local_dir, synthetic_record):
    unknown = local_dir / "unknown.mp4"
    unknown.write_bytes("未知来源".encode())
    with pytest.raises(FileExistsError, match="缺少来源"):
        video.export_video(synthetic_record, unknown)
    target = local_dir / "known.mp4"
    video.export_video(synthetic_record, target)
    with target.open("ab") as stream:
        stream.write("篡改".encode())
    before = target.read_bytes()
    with pytest.raises(ValueError, match="摘要不匹配"):
        video.export_video(synthetic_record, target)
    assert target.read_bytes() == before


def test_video_failure_keeps_hdf5_and_allows_retry(
    local_dir, synthetic_record, monkeypatch
):
    before = video._sha256(synthetic_record)
    target = local_dir / "retry.mp4"
    real_popen = subprocess.Popen

    def fail_encoder(command, *args, **kwargs):
        """只让编码命令失败，版本读取和其他验证继续使用真实程序。"""
        command = list(command)
        if "-c:v" in command:
            command[command.index("-c:v") + 1] = "missing_test_encoder"
        return real_popen(command, *args, **kwargs)

    with monkeypatch.context() as context:
        context.setattr(video.subprocess, "Popen", fail_encoder)
        with pytest.raises(RuntimeError, match="FFmpeg 编码"):
            video.export_video(synthetic_record, target)
    assert not target.exists() and not target.with_suffix(".json").exists()
    assert video._sha256(synthetic_record) == before
    assert video.export_video(synthetic_record, target)["frames"] == 8


def test_video_rejects_different_record_identity(local_dir, synthetic_record):
    target = local_dir / "different.mp4"
    video.export_video(synthetic_record, target)
    record = read_episode(synthetic_record)
    frames = copy.deepcopy(record.frames)
    frames[0]["observation"]["base_rgb"][0, 0, 0] += 1
    other = write_episode(local_dir / "other.h5", record.episode_spec, frames)
    with pytest.raises(ValueError, match="来源或编码参数不匹配"):
        video.export_video(other, target)


@pytest.fixture
def synthetic_suite(local_dir):
    """媒体函数只需清单合同；轻量测试用明确伪认证避免启动仿真。"""
    configs = load_configs()
    specs = [
        candidate_for_slot(slot, 0)
        for slot in plan_slots(*configs, episodes_per_task=1)
    ]
    from robomme_icl.io.scene_metadata import scene_metadata

    certification = {}
    pose = {
        "position": np.array([[0.0, 0.0, 0.02]]),
        "quaternion": np.array([[1.0, 0.0, 0.0, 0.0]]),
    }
    for spec in specs:
        info = {
            "operation": "reset_complete",
            "initial_state": {
                "actors": {"synthetic": {"pose": pose}},
                "articulations": {},
            },
            "initial_assets": {
                "synthetic": [
                    [
                        {
                            "render_shapes": [
                                {
                                    "half_size": np.array([0.02] * 3),
                                    "pose": {
                                        "position": np.zeros(3),
                                        "quaternion": np.array([1.0, 0.0, 0.0, 0.0]),
                                    },
                                }
                            ]
                        }
                    ]
                ]
            },
            "native_parameters": {},
            "task_inventory": [],
        }
        path = write_episode(local_dir / f"{spec.seed}.h5", spec, [{"info": info}])
        certification[spec.spec_hash] = {
            "passed": True,
            "repeat_equal": True,
            "testing": "媒体轻量测试伪认证",
            "record_paths": [str(path)],
            "content_hash": read_episode(path).content_hash,
            "initial_scene_hash": tree_hash(scene_metadata(info)),
        }
    return save_suite(local_dir / "suite", specs, configs, certification)


def test_real_distribution_images_summary_resume_and_missing_plot(
    local_dir, synthetic_suite
):
    destination = local_dir / "distributions"
    first = plots.plot_distributions(synthetic_suite, destination)
    assert first["episodes_total"] == 4 and first["resumed"] is False
    assert len(first["figures"]) == 4
    for figure in first["figures"]:
        assert Path(figure["path"]).is_file()
        assert len(figure["episode_spec_hashes"]) == 1
        assert figure["image_sha256"] == plots._sha256(figure["path"])
    binfill = first["tasks"]["BinFill"]
    assert binfill["episodes"] == 1
    assert binfill["difficulties"]["medium"]["episodes"] == 0
    dimensions = binfill["difficulties"]["easy"]["position_groups"][0]["dimensions"]
    assert all(
        sum(dimension["index_counts"].values()) == 1
        for dimension in dimensions.values()
    )
    second = plots.plot_distributions(synthetic_suite, destination)
    assert second["resumed"] is True
    Path(first["figures"][0]["path"]).unlink()
    restored = plots.plot_distributions(synthetic_suite, destination)
    assert restored["figures"] == first["figures"]
    assert restored["resumed"] is False
    sidecar = Path(first["figures"][0]["sidecar"])
    metadata = json.loads(sidecar.read_text())
    metadata["suite_hash"] = "其他来源"
    sidecar.write_text(json.dumps(metadata), encoding="utf-8")
    with pytest.raises(ValueError, match="来源不匹配"):
        plots.plot_distributions(synthetic_suite, destination)


def test_plot_unknown_file_is_never_overwritten(local_dir, synthetic_suite):
    destination = local_dir / "unknown-plots"
    destination.mkdir()
    target = destination / "binfill.png"
    target.write_bytes("未知来源".encode())
    with pytest.raises(FileExistsError, match="缺少来源"):
        plots.plot_distributions(synthetic_suite, destination)
    assert target.read_bytes() == "未知来源".encode()


def test_media_rejects_reference_dataset_outputs(synthetic_record, synthetic_suite):
    reference = repository_root() / "data" / "robomme_data_h5"
    with pytest.raises(ValueError, match="官方参考数据"):
        video.export_video(synthetic_record, reference / "forbidden.mp4")
    with pytest.raises(ValueError, match="官方参考数据"):
        plots.plot_distributions(synthetic_suite, reference / "forbidden-plots")
