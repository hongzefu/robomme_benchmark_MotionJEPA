"""episode_strip_video 的 CPU 轻量测试：用 tmp_path 造极小假 H5，验证六列横排与标注口径。"""

from __future__ import annotations

import json
from pathlib import Path

import h5py
import imageio
import numpy as np
import pytest

from robomme.env_record_wrapper.RecordWrapper import RobommeRecordWrapper as RecordWrapper
from robomme_xhard import configs
from robomme_xhard.tools import episode_strip_video as esv

COLORS = {
    "mother": (200, 30, 30),
    "xhard12": (30, 200, 30),
    "xhard14": (30, 30, 200),
    "xhard16": (200, 200, 30),
    "xhard18": (30, 200, 200),
    "xhard20": (200, 30, 200),
}
GOALS = ["put the red cube into the bin", "drop the red cube in the bin"]


def _h5(root: Path, level: str, task: str, ep: int, seed: int, n: int, demo: int = 0, goals=GOALS) -> Path:
    path = root / level / "hdf5_files" / f"{task}_ep{ep}_seed{seed}.h5"
    path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "w") as f:
        g = f.create_group(f"episode_{ep}")
        s = g.create_group("setup")
        if goals:
            s.create_dataset("task_goal", data=np.asarray(goals, dtype=object), dtype=h5py.string_dtype("utf-8"))
        # 故意乱序创建，验证按整数序读
        for i in sorted(range(n), key=str):
            t = g.create_group(f"timestep_{i}")
            frame = np.zeros((16, 16, 3), dtype=np.uint8)
            frame[:] = COLORS[level]
            frame[0, 0] = (i, i, i)  # 帧号印记（放大后左上角）
            t.create_dataset("obs/front_rgb", data=frame)
            t.create_dataset("info/is_video_demo", data=np.bool_(i < demo))
    return path


def _card(task, role, diff, ep, seed, ts, ok=True):
    return {"task": task, "role": role, "difficulty": diff, "mother_episode": ep, "seed": seed, "timesteps": ts, "ok": ok}


def _summary(root: Path, cards) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "run_summary.json").write_text(json.dumps({"cards": cards}), encoding="utf-8")


@pytest.fixture
def recorded_writes(monkeypatch):
    calls = []

    def fake(self, frames, output_path):
        calls.append({"self": self, "path": output_path, "frames": [np.array(f) for f in frames]})
        Path(output_path).write_bytes(b"")

    monkeypatch.setattr(RecordWrapper, "_video_write_mp4", fake)
    return calls


@pytest.fixture
def painter():
    return esv.CjkPainter()


def _body(frame, layout_top, col):
    return frame[layout_top : layout_top + esv.BODY, col * esv.BODY : (col + 1) * esv.BODY]


def test_knob_names_cover_all_config_keys():
    seen = set()
    for task, tiers in configs.TIER_CONFIGS.items():
        for tier in tiers.values():
            esv.knob_text(task, tier["knobs"])  # 未知键会抛错
            seen.update(tier["knobs"])
    for task, knobs in configs.MOTHER_KNOBS.items():
        esv.knob_text(task, knobs)
        seen.update(knobs)
    assert seen <= set(esv.KNOB_NAMES)
    assert esv.knob_text("BinFill", {"target_total": 7}) == "投入方块数 7"
    assert esv.knob_text("PickXtimes", {"repeats": 6}) == "抓放次数 6"
    assert esv.knob_text("SwingXtimes", {"repeats": 6}) == "往返次数 6"
    assert esv.knob_text("PatternLock", {"length": 7, "grid": 5}) == "路径节点数 7，网格边长 5"
    assert esv.knob_text("RouteStick", {"length": 6}) == "移动边数 6"
    assert esv.knob_text("VideoPlaceButton", {"extra_groups": 1}) == "额外抓放组数 1（前或后随机）"
    assert esv.knob_text("VideoPlaceButton", {"extra_groups": 2}) == "额外抓放组数 2（前后各一）"
    assert esv.knob_text("MoveCube", {}) == "无旋钮"
    with pytest.raises(KeyError):
        esv.knob_text("BinFill", {"bogus": 1})


def test_strip_layout_labels_timeline_and_border(tmp_path, recorded_writes, painter):
    root = tmp_path / "root"
    task, ep, seed = "BinFill", 7, 4701
    _h5(root, "mother", task, ep, seed, 3, demo=1)
    _h5(root, "xhard12", task, ep, seed, 5)
    _h5(root, "xhard16", task, ep, seed, 2, goals=GOALS + ["a third much longer alternative goal " * 3])
    _h5(root, "xhard18", task, ep, seed, 4)
    _summary(
        root,
        [
            _card(task, "mother", "hard", ep, seed, 100),
            _card(task, "xhard", "xhard12", ep, seed, 168),
            _card(task, "xhard", "xhard14", ep, seed, 0, ok=False),
            _card(task, "xhard", "xhard16", ep, seed, 150),
            _card(task, "xhard", "xhard18", ep, seed, 200),
        ],
    )
    units = esv.discover(root)
    cols = esv.build_columns(units[(task, ep, seed)])
    assert [c.level for c in cols] == list(esv.LEVELS)
    assert [c.status for c in cols] == [esv.OK, esv.OK, esv.FAILED, esv.OK, esv.OK, esv.ABSENT]
    assert cols[0].segments == ["母档（hard）", "投入方块数 4", "100 步"]
    k12 = configs.TIER_CONFIGS[task]["xhard12"]["knobs"]["target_total"]
    assert cols[1].segments == ["xhard12", f"投入方块数 {k12}", "168 步", "母档的 1.68 倍"]
    assert cols[2].segments[-1] == "失败"
    assert cols[5].segments[-1] == "无产物"
    assert cols[0].goals == GOALS
    layout = esv.build_layout(cols, painter)
    for c in cols:
        if c.stream:
            c.stream.close()

    out = tmp_path / "out"
    stats = esv.render_all(root, out)
    assert stats == {**stats, "videos": 1, "columns": 6, "missing": 1}
    assert len(recorded_writes) == 1
    call = recorded_writes[0]
    assert call["self"] is None
    assert Path(call["path"]).name == "1.1_BinFill_ep7_seed4701.mp4"
    frames = call["frames"]
    assert len(frames) == 5  # 总长 = 最长一列
    h, w = frames[0].shape[:2]
    assert h % 16 == 0 and w % 16 == 0 and w == 6 * esv.BODY
    assert all(f.shape == frames[0].shape for f in frames)
    top = layout.top_h
    assert h == esv._round_up(top + esv.BODY)
    # 中文旋钮行确由 PIL 渲染：首列旋钮区有白色像素
    assert frames[0][: layout.header_h, : esv.BODY].max() == 255
    # goal 区非空，且 xhard16 的 goal 更长，各列画面顶边对齐（top 处即画面颜色）
    assert layout.goal_h > esv.goal_block(GOALS).shape[0]
    assert tuple(_body(frames[0], top, 1)[esv.BODY // 2, esv.BODY // 2]) == COLORS["xhard12"]
    assert tuple(_body(frames[0], top, 3)[esv.BODY // 2, esv.BODY // 2]) == COLORS["xhard16"]
    # 演示段红框：母档第 0 帧是演示段，第 1 帧不是
    assert tuple(_body(frames[0], top, 0)[esv.BODY // 2, 2]) == (255, 0, 0)
    assert tuple(_body(frames[1], top, 0)[esv.BODY // 2, 2]) == COLORS["mother"]
    # 短列停在末帧：xhard16 只有 2 帧，第 4 帧画面与第 1 帧画面（末帧）相同
    np.testing.assert_array_equal(_body(frames[4], top, 3), _body(frames[1], top, 3))
    # “结束”：xhard16 第 1 帧（末帧）旋钮行与第 0 帧相同，第 2 帧起追加结束而变化
    hdr = lambda f, c: f[: layout.header_h, c * esv.BODY : (c + 1) * esv.BODY]  # noqa: E731
    np.testing.assert_array_equal(hdr(frames[0], 3), hdr(frames[1], 3))
    assert not np.array_equal(hdr(frames[1], 3), hdr(frames[2], 3))
    np.testing.assert_array_equal(hdr(frames[2], 3), layout.headers[3][1])
    # xhard12 最长，全程不出现结束
    for f in frames:
        np.testing.assert_array_equal(hdr(f, 1), layout.headers[1][0])
    # 灰底列（失败、无产物）
    assert tuple(_body(frames[0], top, 2)[5, 5]) == (esv.GRAY,) * 3
    assert tuple(_body(frames[0], top, 5)[5, 5]) == (esv.GRAY,) * 3


def test_missing_tier_and_task_seed_filters(tmp_path, recorded_writes):
    root = tmp_path / "root"
    _h5(root, "mother", "MoveCube", 7, 14700, 2)
    _h5(root, "mother", "BinFill", 7, 4701, 2)
    _summary(root, [_card("MoveCube", "mother", "hard", 7, 14700, 2), _card("BinFill", "mother", "hard", 7, 4701, 2)])
    cols = esv.build_columns(esv.discover(root)[("MoveCube", 7, 14700)])
    assert [c.status for c in cols] == [esv.OK] + [esv.MISSING] * 5
    assert cols[0].segments[:2] == ["母档（hard）", "无旋钮"]
    assert cols[1].segments == ["xhard12", "缺档"]
    cols[0].stream.close()

    stats = esv.render_all(root, tmp_path / "o1", task="MoveCube")
    assert stats["videos"] == 1 and stats["missing"] == 5
    manifest = {"tasks": {"BinFill": [{"seed": 4701}]}}
    stats = esv.render_all(root, tmp_path / "o2", manifest=manifest)
    assert [Path(p).name for p in stats["outputs"]] == ["1.1_BinFill_ep7_seed4701.mp4"]


def test_video_repick_mother_is_medium():
    assert esv.level_name("VideoRepick", esv.MOTHER) == "母档（medium）"


def test_failed_columns_keep_error_type_and_six_column_canvas(tmp_path, painter):
    card = _card("VideoRepick", "xhard", "xhard12", 6, 1, 0, ok=False)
    card["error_type"] = "SwapCollisionError"
    _summary(tmp_path, [card])
    columns = esv.build_columns(esv.discover(tmp_path)[("VideoRepick", 6, 1)])
    assert len(columns) == 6
    assert columns[1].failure_text == "失败：SwapCollisionError"
    assert columns[1].segments[-1] == columns[1].failure_text
    frames = list(esv.compose_frames(columns, painter))
    imageio.imwrite(tmp_path / "failure-preview.png", frames[0])
    assert len(frames) == 1 and frames[0].shape[1] == 6 * esv.BODY
    gray = esv.build_layout(columns, painter).statics[1]
    assert tuple(gray[0, 0]) == (esv.GRAY,) * 3
    assert gray.max() == 255


def test_failed_jsonl_card_is_not_absent(tmp_path):
    card = _card("VideoRepick", "xhard", "xhard12", 6, 1, 0, ok=False)
    card["error_type"] = "SwapBindingError"
    (tmp_path / "episode_results.jsonl").write_text(json.dumps(card) + "\n")
    columns = esv.build_columns(esv.discover(tmp_path)[("VideoRepick", 6, 1)])
    assert columns[1].status == esv.FAILED
    assert columns[1].failure_text == "失败：SwapBindingError"


def test_missing_font_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        esv.CjkPainter(tmp_path / "nofont.ttc")


def test_main_and_real_write(tmp_path, capsys):
    """不 monkeypatch：真正走原版 _video_write_mp4 写出，读回帧数与尺寸。"""
    root = tmp_path / "root"
    _h5(root, "mother", "RouteStick", 7, 16700, 3)
    _h5(root, "xhard20", "RouteStick", 7, 16700, 4)
    _summary(root, [_card("RouteStick", "mother", "hard", 7, 16700, 3), _card("RouteStick", "xhard", "xhard20", 7, 16700, 4)])
    assert esv.main(["--root", str(root), "--out-dir", str(tmp_path / "out")]) == 0
    last = capsys.readouterr().out.strip().splitlines()[-1]
    assert last == "EPISODE_STRIP_VIDEO=PASS videos=1 columns=6 missing=4"
    path = tmp_path / "out" / "4.4_RouteStick_ep7_seed16700.mp4"
    reader = imageio.get_reader(path.as_posix())
    frames = [f for f in reader]
    reader.close()
    assert len(frames) == 4
    assert frames[0].shape[1] == 6 * esv.BODY and frames[0].shape[0] % 16 == 0
