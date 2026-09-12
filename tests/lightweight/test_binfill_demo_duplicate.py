"""BinFill「同一条重复两遍」交付版转换（生成入口 close() 之后的后处理）。

用 h5py 造一条 N=3 的迷你 episode、用 imageio 写 3 帧 32×32 的 mp4，跑
``_binfill_demo_deliverable``，核对：timestep 0..2N-1 连续；前 N 帧 ``is_video_demo`` 为真且
``is_completed`` 为假；后 N 帧逐字段原样；末帧 ``is_completed`` 为真 bool 标量；``setup`` 原样；
mp4 帧数 2N 且前半段四边为红；原件已带 demo 时报错；失败时原件不动、临时文件被清掉。
"""
from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

import h5py
import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
GENERATOR = REPO_ROOT / "scripts" / "generate_dataset_newseed.py"

pytestmark = pytest.mark.skipif(shutil.which("ffprobe") is None, reason="需要 ffprobe 数帧")


@pytest.fixture(scope="module")
def gen():
    spec = importlib.util.spec_from_file_location("generate_dataset_newseed", GENERATOR)
    module = importlib.util.module_from_spec(spec)
    sys.modules["generate_dataset_newseed"] = module
    spec.loader.exec_module(module)
    return module


def _write_episode(path: Path, episode: int, steps: int, *, demo_prefix: int = 0) -> None:
    """按录像器 close() 的写法造 h5：info 用 bytes 字符串、三个 bool 标量；setup 用 utf-8 string dtype。"""
    with h5py.File(path, "w") as handle:
        group = handle.create_group(f"episode_{episode}")
        for index in range(steps):
            ts = group.create_group(f"timestep_{index}")
            obs = ts.create_group("obs")
            obs.create_dataset("front_rgb", data=np.full((4, 4, 3), index, dtype=np.uint8))
            obs.create_dataset("joint_state", data=np.arange(7, dtype=np.float32) + index)
            action = ts.create_group("action")
            action.create_dataset("joint_action", data=np.zeros(8, dtype=np.float64) + index)
            action.create_dataset("choice_action", data='{"choice": "A"}', dtype=h5py.special_dtype(vlen=str))
            info = ts.create_group("info")
            info.create_dataset("simple_subgoal", data=f"subgoal {index}".encode("utf-8"))
            info.create_dataset("is_completed", data=bool(index == steps - 1))
            info.create_dataset("is_video_demo", data=bool(index < demo_prefix))
            info.create_dataset("is_subgoal_boundary", data=bool(index == 0))
        setup = group.create_group("setup")
        setup.create_dataset("seed", data=4000)
        setup.create_dataset("difficulty", data="easy", dtype=h5py.string_dtype(encoding="utf-8"))
        setup.create_dataset(
            "task_goal", data=np.asarray(["goal a", "goal b"], dtype=object), dtype=h5py.string_dtype(encoding="utf-8")
        )


def _write_video(path: Path, frames: int) -> None:
    import imageio

    with imageio.get_writer(str(path), fps=30, codec="libx264", quality=8) as writer:
        for index in range(frames):
            frame = np.full((32, 32, 3), 40 + 50 * index, dtype=np.uint8)
            writer.append_data(frame)


def _job(gen, output_root: Path):
    return gen.EpisodeJob(
        task="BinFill", episode=0, attempt=0, seed=4000, difficulty="easy",
        output_root=str(output_root), repo_root=str(REPO_ROOT), binfill_demo=True,
    )


def _frames(path: Path) -> int:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames", "-show_entries",
         "stream=nb_read_frames", "-of", "default=nokey=1:noprint_wrappers=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return int(out.stdout.strip())


def test_转换后帧数翻倍且前一遍标_demo_后一遍原样(gen, tmp_path: Path):
    root = tmp_path / "out"
    (root / "hdf5_files").mkdir(parents=True)
    (root / "videos").mkdir()
    job = _job(gen, root)
    h5_path = gen._h5_path(root, job)
    _write_episode(h5_path, 0, 3)
    video = root / "videos" / "BinFill_ep0_seed4000_easy_goal.mp4"
    _write_video(video, 3)

    result = gen._binfill_demo_deliverable(root, job, 3)

    assert result["applied"] is True
    assert (result["original_timesteps"], result["final_timesteps"]) == (3, 6)
    assert result["video_frames_in"] == 3 and result["video_frames_out"] == 6
    assert not list((root / "hdf5_files").glob("*demo-tmp*")) and not list((root / "videos" / ".demo-tmp").glob("*"))
    with h5py.File(h5_path, "r") as handle:
        group = handle["episode_0"]
        names = sorted(name for name in group if name.startswith("timestep_"))
        assert names == sorted(f"timestep_{i}" for i in range(6))
        for index in range(3):
            demo, exec_ = group[f"timestep_{index}"], group[f"timestep_{index + 3}"]
            assert bool(demo["info/is_video_demo"][()]) is True
            assert bool(demo["info/is_completed"][()]) is False
            assert bool(exec_["info/is_video_demo"][()]) is False
            # 后一遍逐字段原样（含 bytes 字符串与 dtype）
            assert exec_["info/simple_subgoal"][()] == f"subgoal {index}".encode("utf-8")
            assert exec_["info/simple_subgoal"].dtype == demo["info/simple_subgoal"].dtype
            assert np.array_equal(exec_["obs/front_rgb"][()], np.full((4, 4, 3), index, dtype=np.uint8))
            assert np.array_equal(demo["obs/front_rgb"][()], exec_["obs/front_rgb"][()])
            assert exec_["action/choice_action"][()] in ('{"choice": "A"}', b'{"choice": "A"}')
        last = group["timestep_5/info/is_completed"]
        assert last.shape == () and last.dtype == np.bool_ and bool(last[()]) is True
        assert bool(group["timestep_2/info/is_completed"][()]) is False
        assert bool(group["timestep_0/info/is_subgoal_boundary"][()]) and bool(group["timestep_3/info/is_subgoal_boundary"][()])
        assert int(group["setup/seed"][()]) == 4000
        assert [g.decode() if isinstance(g, bytes) else g for g in group["setup/task_goal"][()]] == ["goal a", "goal b"]
        indices, done, errors = gen.inspect_episode_terminal(group, "x")
        assert (len(indices), done, errors) == (6, True, [])
    assert _frames(video) == 6
    import imageio

    # 不能 list(reader)：imageio 的 __len__ 返回 inf 会直接 MemoryError，只能迭代
    frames = [frame for frame in imageio.get_reader(str(video))]
    assert len(frames) == 6
    first, fourth = frames[0], frames[3]
    # 前半段四边红框（有损编码给 30 的容差），中心保留原灰度；后半段无红框
    assert first[0, 16, 0] > 200 and first[0, 16, 1] < 60 and first[16, 0, 0] > 200 and first[-1, 16, 0] > 200 and first[16, -1, 0] > 200
    assert abs(int(first[16, 16, 0]) - 40) < 30
    assert abs(int(fourth[0, 16, 0]) - 40) < 30 and abs(int(fourth[16, 16, 0]) - 40) < 30


def test_原件已带_demo_帧时报错且原件不动(gen, tmp_path: Path):
    root = tmp_path / "out"
    (root / "hdf5_files").mkdir(parents=True)
    (root / "videos").mkdir()
    job = _job(gen, root)
    h5_path = gen._h5_path(root, job)
    _write_episode(h5_path, 0, 3, demo_prefix=1)
    before = h5_path.read_bytes()
    _write_video(root / "videos" / "BinFill_ep0_seed4000_easy_goal.mp4", 3)
    with pytest.raises(gen.BinFillDemoError, match="已是 demo 帧"):
        gen._binfill_demo_deliverable(root, job, 3)
    assert h5_path.read_bytes() == before
    assert not [p for p in root.rglob("*") if p.is_file() and ".demo-tmp" in str(p)]


def test_视频帧数与_timestep_不符时报错并清理临时文件(gen, tmp_path: Path):
    root = tmp_path / "out"
    (root / "hdf5_files").mkdir(parents=True)
    (root / "videos").mkdir()
    job = _job(gen, root)
    h5_path = gen._h5_path(root, job)
    _write_episode(h5_path, 0, 3)
    video = root / "videos" / "BinFill_ep0_seed4000_easy_goal.mp4"
    _write_video(video, 2)
    before_h5, before_video = h5_path.read_bytes(), video.read_bytes()
    with pytest.raises(gen.BinFillDemoError, match="!= HDF5 timestep 数"):
        gen._binfill_demo_deliverable(root, job, 3)
    assert h5_path.read_bytes() == before_h5 and video.read_bytes() == before_video
    assert not [p for p in root.rglob("*") if p.is_file() and ".demo-tmp" in str(p)]


def test_没有主视频或_FAILED_视频不算主视频(gen, tmp_path: Path):
    root = tmp_path / "out"
    (root / "hdf5_files").mkdir(parents=True)
    (root / "videos").mkdir()
    job = _job(gen, root)
    _write_episode(gen._h5_path(root, job), 0, 3)
    _write_video(root / "videos" / "FAILED_BinFill_ep0_seed4000_easy_goal.mp4", 3)
    with pytest.raises(gen.BinFillDemoError, match="恰好一个成功主视频"):
        gen._binfill_demo_deliverable(root, job, 3)


def test_不开关时_worker_默认关闭(gen):
    job = gen.EpisodeJob(task="BinFill", episode=0, attempt=0, seed=1, difficulty="easy", output_root="x", repo_root="y")
    assert job.binfill_demo is False
