"""新图表读取与旧算法像素回归，使用仓库内小夹具，不依赖未入库的图片或 HDF5。"""
import hashlib
import json
import subprocess
import tempfile
import types
from pathlib import Path

import h5py

from scripts.injection.candidates import figures
from scripts.injection.candidates.io import load_candidates
from scripts.injection.rollout import windows
from scripts.injection.rollout.state import ROOT


def temporary():
    parent = ROOT / "artifacts/test-tmp"
    parent.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix="refactor-figures-", dir=parent))


def test_position_image_bytes_match_frozen_old_algorithm():
    source = subprocess.check_output(["git", "show", "e53173d:scripts/injection-before-2d/plot_injection_before_2d.py"], text=True)
    source = source.replace("from window_timeline import GROUPS", "from scripts.injection.rollout.windows import GROUPS")
    old = types.ModuleType("old_before_figure")
    old.__file__ = str(ROOT / "scripts/injection-before-2d/plot_injection_before_2d.py")
    exec(compile(source, old.__file__, "exec"), old.__dict__)
    header, rows = load_candidates(ROOT / "artifacts/injection/20260912-contract-v3-10/candidates/candidates.jsonl")
    records = [r["spec"] for r in rows if (r["task"], r["difficulty"]) == ("RouteStick", "easy")][:30]
    root = temporary()
    old.use_cjk_font()
    old.plot_positions("RouteStick", "easy", records, header["sampling_config"]["positions"]["RouteStick"], root / "old.png")
    figures.use_cjk_font()
    figures.plot_positions("RouteStick", "easy", records, header["sampling_config"]["positions"]["RouteStick"], root / "new.png")
    assert hashlib.sha256((root / "old.png").read_bytes()).digest() == hashlib.sha256((root / "new.png").read_bytes()).digest()


def test_results_to_timeline_figures_and_report():
    root = temporary()
    path = root / "episode.h5"
    with h5py.File(path, "w") as handle:
        group = handle.create_group("episode_0")
        for frame in range(70):
            info = group.create_group(f"timestep_{frame}").create_group("info")
            info["is_video_demo"] = False
            info["is_subgoal_boundary"] = frame in (0, 35)
            info["simple_subgoal"] = "press the button" if frame < 35 else "press the button to finish"
    row = {"kind": "h5", "task": "RouteStick", "difficulty": "easy", "episode": 0,
           "seed": 16000, "ok": True, "h5_path": str(path), "timestep_count": 70}
    candidate = {"task": "RouteStick", "difficulty": "easy", "episode": 0, "spec": {}}
    store = types.SimpleNamespace(state=root, logs=root / "logs", load=lambda: ({"run_id": "fixture"}, [candidate], [row]))
    result = windows.generate_windows(store)
    assert result["episodes_before_exclusion"] == result["episodes"] == 1
    assert not result["excluded_slow"] and not result["skipped"]
    assert (root / "WINDOWS.md").is_file()
    assert (root / "figures/RouteStick/easy/4_windows.png").is_file()
    assert (root / "figures/windows_overview.png").is_file()
    assert len(list((root / "figures").rglob("*.png"))) == 2


def test_all_card_text_keeps_legacy_color_order_and_swap_projection():
    source = subprocess.check_output(["git", "show", "e53173d:scripts/injection-before-2d/plot_injection_before_2d.py"], text=True)
    source = source.replace("from window_timeline import GROUPS", "from scripts.injection.rollout.windows import GROUPS")
    old = types.ModuleType("old_cards")
    old.__file__ = str(ROOT / "scripts/injection-before-2d/plot_injection_before_2d.py")
    exec(compile(source, old.__file__, "exec"), old.__dict__)
    run = ROOT / "artifacts/injection/20260912-contract-v3-10"
    header, rows = load_candidates(run / "candidates/candidates.jsonl")
    index = {(r["task"], r["difficulty"], r["episode"]): r["spec"] for r in rows}
    count = 0
    for task, difficulty in windows.GROUPS:
        path = run / "specs" / task / f"{difficulty}.json"
        if not path.exists():
            path = run / "candidates/logs/legacy/specs" / task / f"{difficulty}.json"
        records = json.loads(path.read_text())["episodes"]
        for record in records[:30]:
            current = index[(task, difficulty, record["episode"])]
            before = json.dumps(current, sort_keys=True)
            assert old.card_lines(task, record) == figures.card_lines(task, current)
            assert json.dumps(current, sort_keys=True) == before
            count += 1
        if task in windows.SWAP_TASKS:
            for record in records:
                projected = windows.swap_spec(index[(task, difficulty, record["episode"])])
                assert projected == {"n_swaps": int(record["objects"]["n_swaps"]),
                                     "pairs": [{"initiator": p["initiator"], "partner": p["partner"]} for p in record["actions"]["swap_pairs"]]}
    assert count == 420
