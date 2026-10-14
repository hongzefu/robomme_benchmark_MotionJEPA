"""用完整真实 H5 夹具验证结构、内容、数量、语义与身份对账。"""

from __future__ import annotations

import ast
import copy
import json
from pathlib import Path

import h5py
import numpy as np
import pytest

from robomme_xhard.configs import DIFFICULTIES, TASK_ORDER, TIER_CONFIGS
from robomme_xhard.tools import check_mixed_h5 as checker
from robomme_xhard.tools import subgoal_rules as rules

GOLDEN_DIR = Path(checker.__file__).parent / "golden_schema"
FULL_CYCLE = tuple(checker.DEFAULT_CYCLE.split(","))


def _labels(task, difficulty):
    if difficulty not in DIFFICULTIES:
        return ["static"] * 3
    knobs = TIER_CONFIGS[task][difficulty]["knobs"]
    if task == "VideoUnmaskSwap":
        return ["pick up the container", "static", "pick up the container"]
    if task == "ButtonUnmaskSwap":
        return ["press the first button"] * knobs["press_count"] + ["pick up the container"] * 2
    if task == "VideoRepick":
        return ["pick up the correct cube for the first time", "static", "pick up the correct cube for the second time"]
    if task == "VideoPlaceButton":
        return ["pick up the cube"] * (4 + knobs["extra_groups"])
    if task == "BinFill":
        return ["put it into the bin"] * knobs["target_total"] + ["All tasks completed"]
    if task == "PickXtimes":
        return ["pick up the red cube for the first time"] * knobs["repeats"] + ["All tasks completed"]
    if task == "SwingXtimes":
        labels = ["move to the top of the right-side target for the first time",
                  "move to the top of the left-side target for the first time"]
        return labels * knobs["repeats"] + ["All tasks completed"]
    if task in ("VideoUnmask", "ButtonUnmask"):
        return ["pick up the container that hides the green cube"] * knobs["pick_count"] + ["All tasks completed"]
    if task == "PickHighlight":
        return ["pick up the first highlighted cube, which is blue"] * knobs["pickup"] + ["All tasks completed"]
    if task == "VideoPlaceOrder":
        return ["drop the cube onto target"] * knobs["num_targets"] + ["All tasks completed"]
    if task == "PatternLock":
        return ["move forward"] * (2 * (knobs["length"] - 1)) + ["All tasks completed"]
    if task == "RouteStick":
        return ["move to the nearest left target by circling around the stick clockwise"] * (2 * knobs["length"]) + ["All tasks completed"]
    return ["static"] * 3


def _dataset(group, name, spec, value=None):
    dtype = spec["dtypes"][0]
    shape = tuple(spec["shape"])
    parent, _, leaf = name.rpartition("/")
    target = group.require_group(parent) if parent else group
    if dtype == "object":
        value = value if value is not None else ("测试文本" if not shape else np.full(shape, "测试目标", dtype=object))
        target.create_dataset(leaf, data=value, dtype=h5py.string_dtype("utf-8"))
    else:
        value = value if value is not None else np.zeros(shape, dtype=dtype)
        target.create_dataset(leaf, data=value, dtype=dtype)


def write_products(root, tasks=("ButtonUnmaskSwap",), cycle=("xhard12",), start=0, episodes=1, attempt=0):
    """按原版全部叶键写完整 action/obs/info/setup，另写实际三方身份证据。"""
    root = Path(root)
    (root / "hdf5_files").mkdir(parents=True)
    (root / "videos").mkdir()
    rows = []
    for task in tasks:
        golden = json.loads((GOLDEN_DIR / f"{task}.json").read_text())
        metadata = []
        for episode in range(start, start + episodes):
            record = checker.expected_identity(task, episode, attempt, cycle)
            record.update(ok=True, task_success=True)
            if record["difficulty"] in DIFFICULTIES:
                knobs = copy.deepcopy(TIER_CONFIGS[task][record["difficulty"]]["knobs"])
                record["xhard_knobs"] = knobs
                if "swap_count" in knobs:
                    record["swap_plan"] = {"pairs": [[0, 1]] * knobs["swap_count"]}
                    record["runtime_checks"] = [{"kind": "swap_sweep", "endpoint_match": True, "sweep_index": i}
                                                 for i in range(knobs["swap_count"])]
            for previous in range(attempt):
                rows.append({**checker.expected_identity(task, episode, previous, cycle), "ok": False, "task_success": False})
            filename = f"{task}_ep{episode}_seed{record['seed']}"
            path = root / "hdf5_files" / (filename + ".h5")
            record["h5_path"] = str(path)
            rows.append(record)
            metadata.append({key: record[key] for key in ("task", "episode", "seed", "difficulty")})
            labels = _labels(task, record["difficulty"])
            with h5py.File(path, "w") as handle:
                group = handle.create_group(f"episode_{episode}")
                setup = group.create_group("setup")
                for key, spec in golden["setup"].items():
                    _dataset(setup, key, spec, record.get(key))
                for index, label in enumerate(labels):
                    step = group.create_group(f"timestep_{index}")
                    for key, spec in golden["timestep"].items():
                        value = None
                        if key in ("info/simple_subgoal", "info/simple_subgoal_online"):
                            value = label
                        elif key == "info/is_subgoal_boundary":
                            value = True
                        elif key == "info/is_completed":
                            value = index == len(labels) - 1
                        elif key == "info/is_video_demo":
                            value = index < len(labels) - 1
                        elif key in ("obs/front_rgb", "obs/wrist_rgb"):
                            value = np.arange(np.prod(spec["shape"]), dtype=np.uint8).reshape(spec["shape"])
                        _dataset(step, key, spec, value)
            (root / "videos" / (filename + "_测试.mp4")).write_bytes("夹具视频存在".encode("utf-8"))
        checker.write_json(root / f"record_dataset_{task}_metadata.json",
                           {"env_id": task, "record_count": len(metadata), "records": metadata})
    rewrite_results(root, rows)
    return root


def rewrite_results(root, rows):
    (root / "episode_results.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def run_check(root, tasks=("ButtonUnmaskSwap",), cycle=("xhard12",), **kwargs):
    return checker.check_dataset(root, GOLDEN_DIR, cycle, kwargs.pop("episodes", 1), tasks=tasks, workers=2, **kwargs)


def first_h5(root):
    return next((root / "hdf5_files").glob("*.h5"))


def test_full_fixture_four_pass_and_boundary_duplicates(tmp_path):
    root = write_products(tmp_path / "valid")
    report = run_check(root)
    assert report["pass"], report
    assert all("=PASS" in line for line in checker.check_lines(report))
    assert [item["text"] for item in report["samples"][0]["boundaries"]].count("press the first button") == 3
    assert report["plan"]["rules_expected"] == report["plan"]["rules_run"] == 3
    assert report["plan"]["exempt"] == 0


def test_unreadable_h5_cannot_pass_schema(tmp_path):
    root = write_products(tmp_path / "unreadable")
    first_h5(root).write_bytes(b"broken HDF5")
    report = run_check(root)
    assert not report["schema"]["pass"]
    assert report["schema"]["missing"] == 1
    assert report["samples"][0]["schema_errors"][0]["error"]
    assert report["samples"][0]["content_errors"]


def test_forged_base_label_and_unreadable_h5_cannot_erase_expected_rules(tmp_path):
    root = write_products(tmp_path / "disguised")
    rows = checker.read_products(root)["results"]
    rows[0]["difficulty"] = "easy"
    rewrite_results(root, rows)
    first_h5(root).write_bytes(b"broken HDF5")
    report = run_check(root)
    assert not report["plan"]["pass"]
    assert report["plan"]["files"] == 1
    assert report["plan"]["rules_expected"] == 3
    assert report["plan"]["rules_run"] == 0
    assert report["plan"]["mismatch"] == 3


@pytest.mark.parametrize("task", ("VideoUnmaskSwap", "ButtonUnmaskSwap", "VideoRepick", "VideoPlaceButton"))
def test_known_rules_real_h5(tmp_path, task):
    root = write_products(tmp_path / task, tasks=(task,))
    assert run_check(root, tasks=(task,))["pass"]


@pytest.mark.parametrize("mutation,section", (
    ("missing_key", "schema"), ("dtype", "schema"), ("extra_key", "schema"),
    ("gap", "content"), ("seed", "content"), ("terminal", "content"),
    ("constant", "content"), ("uniform_color", "content"), ("nonmonotone", "content"), ("nonprefix", "content"),
    ("joint_none", "content"), ("joint_nan", "content"), ("video", "content"),
    ("press_less", "plan"),
))
def test_corruption_reports_corresponding_failure(tmp_path, mutation, section):
    root = write_products(tmp_path / mutation)
    with h5py.File(first_h5(root), "r+") as handle:
        episode = handle["episode_0"]
        if mutation == "missing_key":
            del episode["timestep_2/obs/eef_state"]
        elif mutation == "dtype":
            del episode["timestep_2/action/waypoint_action"]
            episode["timestep_2/action"].create_dataset("waypoint_action", data=np.zeros(7, dtype=np.int32))
        elif mutation == "extra_key":
            episode["timestep_2/obs"].create_dataset("unexpected", data=0)
        elif mutation == "gap":
            episode.move("timestep_2", "timestep_9")
        elif mutation == "seed":
            episode["setup/seed"][()] = 123456
        elif mutation == "terminal":
            episode["timestep_4/info/is_completed"][()] = False
        elif mutation == "constant":
            episode["timestep_2/obs/wrist_rgb"][...] = 0
        elif mutation == "uniform_color":
            episode["timestep_2/obs/wrist_rgb"][...] = [255, 0, 0]
        elif mutation == "nonmonotone":
            episode["timestep_0/info/is_completed"][()] = True
        elif mutation == "nonprefix":
            episode["timestep_1/info/is_video_demo"][()] = False
        elif mutation == "joint_none":
            del episode["timestep_0/action/joint_action"]
            episode["timestep_0/action"].create_dataset("joint_action", data="None", dtype=h5py.string_dtype())
        elif mutation == "joint_nan":
            episode["timestep_2/action/joint_action"][...] = np.nan
        elif mutation == "press_less":
            episode["timestep_2/info/is_subgoal_boundary"][()] = False
    if mutation == "video":
        next((root / "videos").glob("*.mp4")).unlink()
    report = run_check(root)
    assert not report[section]["pass"], report
    assert not report["pass"]


def test_task_goal_length_variable_but_rank_and_nonempty_strict(tmp_path):
    root = write_products(tmp_path / "goal")
    with h5py.File(first_h5(root), "r+") as handle:
        setup = handle["episode_0/setup"]
        del setup["task_goal"]
        setup.create_dataset("task_goal", data=np.array(["甲"] * 9, dtype=object), dtype=h5py.string_dtype())
    assert run_check(root)["schema"]["pass"]
    with h5py.File(first_h5(root), "r+") as handle:
        setup = handle["episode_0/setup"]
        del setup["task_goal"]
        setup.create_dataset("task_goal", shape=(0,), dtype=h5py.string_dtype())
    assert not run_check(root)["schema"]["pass"]


def test_every_timestep_checked_even_first_joint_none(tmp_path):
    root = write_products(tmp_path / "every")
    with h5py.File(first_h5(root), "r+") as handle:
        group = handle["episode_0"]
        del group["timestep_0/action/joint_action"]
        group["timestep_0/action"].create_dataset("joint_action", data="None")
        del group["timestep_4/obs/eef_state"]
    report = run_check(root)
    assert report["schema"]["missing"] == 1
    assert report["schema"]["dtype_shape"] == 1


@pytest.mark.parametrize("mutation", ("missing_swap_index", "endpoint_false", "short_pairs", "false_success", "wrong_knobs", "missing_rule", "extra_rule"))
def test_semantic_evidence_and_exact_rule_coverage(tmp_path, monkeypatch, mutation):
    root = write_products(tmp_path / mutation)
    rows = checker.read_products(root)["results"]
    if mutation == "missing_swap_index":
        rows[0]["runtime_checks"].pop()
    elif mutation == "endpoint_false":
        rows[0]["runtime_checks"][0]["endpoint_match"] = False
    elif mutation == "short_pairs":
        rows[0]["swap_plan"]["pairs"].pop()
    elif mutation == "false_success":
        rows[0]["task_success"] = False
    elif mutation == "wrong_knobs":
        rows[0]["xhard_knobs"]["press_count"] = 2
    elif mutation == "missing_rule":
        monkeypatch.setitem(checker.SUBGOAL_RULES, "ButtonUnmaskSwap", checker.SUBGOAL_RULES["ButtonUnmaskSwap"][:-1])
    elif mutation == "extra_rule":
        monkeypatch.setitem(checker.SUBGOAL_RULES, "ButtonUnmaskSwap", checker.SUBGOAL_RULES["ButtonUnmaskSwap"] +
                            [{"name": "不存在", "pattern": "static", "expect": "const:0"}])
    rewrite_results(root, rows)
    assert not run_check(root)["plan"]["pass"]


def test_exemption_count_is_processed_and_disjoint(tmp_path, monkeypatch):
    root = write_products(tmp_path / "exempt")
    monkeypatch.setitem(checker.SUBGOAL_RULES, "ButtonUnmaskSwap", checker.SUBGOAL_RULES["ButtonUnmaskSwap"][:-1])
    monkeypatch.setitem(checker.EXEMPT, "ButtonUnmaskSwap", {"swap_count": "测试进程模拟用户批准，生产表仍为空"})
    report = run_check(root)
    assert report["plan"]["pass"]
    assert report["plan"]["rules_run"] == report["plan"]["rules_expected"] == 3
    assert report["plan"]["exempt"] == 1


def test_missing_expected_rule_never_passes(tmp_path, monkeypatch):
    monkeypatch.setitem(checker.SUBGOAL_RULES, "BinFill", [])
    root = write_products(tmp_path / "unfilled", tasks=("BinFill",))
    report = run_check(root, tasks=("BinFill",))
    assert not report["plan"]["pass"]
    assert report["plan"]["rules_expected"] == 1
    assert report["plan"]["rules_run"] == 0
    assert set((task, name) for task, items in rules.EXEMPT.items() for name in items) == {
        ("StopCube", "stop_k"), ("PickHighlight", "spawn"), ("PatternLock", "grid")}
    assert set(rules.EXPECTED_CHECKS) == set(TIER_CONFIGS)
    assert all(rules.EXPECTED_CHECKS.values())


@pytest.mark.parametrize("task,difficulty", [(task, difficulty) for task in TASK_ORDER
                                             for difficulty in TIER_CONFIGS.get(task, {})])
def test_all_xhard_quantity_rules_complete_fixture(tmp_path, task, difficulty):
    root = write_products(tmp_path / f"{task}-{difficulty}", tasks=(task,), cycle=(difficulty,))
    report = run_check(root, tasks=(task,), cycle=(difficulty,))
    assert report["pass"], report
    assert report["plan"]["rules_run"] == len(rules.EXPECTED_CHECKS[task])
    assert report["plan"]["exempt"] == len(rules.EXEMPT[task])


@pytest.mark.parametrize("task,difficulty", (
    ("BinFill", "xhard12"), ("PickXtimes", "xhard12"), ("SwingXtimes", "xhard12"),
    ("VideoUnmask", "xhard14"), ("ButtonUnmask", "xhard14"), ("PickHighlight", "xhard12"),
    ("VideoPlaceOrder", "xhard12"), ("PatternLock", "xhard12"), ("RouteStick", "xhard12"),
))
def test_w5_quantity_boundary_missing_cannot_pass(tmp_path, task, difficulty):
    root = write_products(tmp_path / task, tasks=(task,), cycle=(difficulty,))
    with h5py.File(first_h5(root), "r+") as handle:
        handle["episode_0/timestep_0/info/is_subgoal_boundary"][()] = False
    report = run_check(root, tasks=(task,), cycle=(difficulty,))
    assert report["schema"]["pass"] and report["content"]["pass"]
    assert not report["plan"]["pass"]


@pytest.mark.parametrize("task,difficulty,target", (
    ("PatternLock", "xhard12", 12), ("PatternLock", "xhard20", 20),
    ("RouteStick", "xhard12", 12), ("RouteStick", "xhard20", 20),
))
def test_affine_counts_full_sequence_and_excludes_completion(tmp_path, task, difficulty, target):
    root = write_products(tmp_path / task, tasks=(task,), cycle=(difficulty,))
    report = run_check(root, tasks=(task,), cycle=(difficulty,))
    detail = report["samples"][0]["semantic"]["details"][0]
    assert detail["expected"] == detail["actual"] == target
    assert len(report["samples"][0]["boundaries"]) == target + 1
    assert report["samples"][0]["boundaries"][-1]["text"] == "All tasks completed"


def test_exemption_draft_keeps_frozen_80_items_and_exact_coverage():
    for task, expected in rules.EXPECTED_CHECKS.items():
        executed = {rule["name"] for rule in rules.SUBGOAL_RULES[task]}
        exempted = set(rules.EXEMPT[task])
        assert executed.isdisjoint(exempted)
        assert executed | exempted == expected
    assert sum(len(rules.EXPECTED_CHECKS[task]) * len(tiers) for task, tiers in TIER_CONFIGS.items()) == 80
    assert sum(len(rules.EXEMPT[task]) * len(tiers) for task, tiers in TIER_CONFIGS.items()) == 12


def test_later_same_tier_success_cannot_replace_missing_first_sample(tmp_path):
    root = write_products(tmp_path / "missing-first", tasks=("VideoPlaceOrder",), episodes=2)
    first_h5(root).unlink()
    report = run_check(root, tasks=("VideoPlaceOrder",), episodes=2)
    assert report["schema"]["files"] == 0
    assert report["schema"]["missing"] == 1
    assert report["plan"]["rules_expected"] == 1
    assert report["plan"]["rules_run"] == 0
    assert not report["schema"]["pass"] and not report["plan"]["pass"]


@pytest.mark.parametrize("mutation", ("missing", "duplicate", "unknown_episode", "attempt_gap", "wrong_seed", "wrong_fr", "unknown_task"))
def test_identity_audit_positive_and_negative(tmp_path, mutation):
    root = write_products(tmp_path / mutation, cycle=("easy",), attempt=1)
    assert checker.audit_dataset(root, ("easy",), 0, 1, tasks=("ButtonUnmaskSwap",))["pass"]
    rows = checker.read_products(root)["results"]
    if mutation == "missing":
        rows = []
    elif mutation == "duplicate":
        rows.append(copy.deepcopy(rows[-1]))
    elif mutation == "unknown_episode":
        rows[-1]["episode"] = 400
    elif mutation == "attempt_gap":
        rows[-1]["attempt"] = 2
    elif mutation == "wrong_seed":
        rows[-1]["seed"] += 1
    elif mutation == "wrong_fr":
        rows[-1]["recovery_mode"] = "xy"
    elif mutation == "unknown_task":
        rows[-1]["task"] = "未知"
    rewrite_results(root, rows)
    report = checker.audit_dataset(root, ("easy",), 0, 1, tasks=("ButtonUnmaskSwap",))
    assert not report["pass"], report
    assert report["errors"]


def test_identity_metadata_filename_exact_and_parameters_not_authority(tmp_path):
    root = write_products(tmp_path / "identity", cycle=("easy",))
    checker.write_json(root / "run_parameters.json", {"effective_cycles": {"ButtonUnmaskSwap": ["hard"]}})
    assert checker.audit_dataset(root, ("easy",), 0, 1, tasks=("ButtonUnmaskSwap",))["pass"]
    original = first_h5(root)
    original.rename(original.with_name(original.name.replace("ep0", "ep400")))
    report = checker.audit_dataset(root, ("easy",), 0, 1, tasks=("ButtonUnmaskSwap",))
    assert report["unknown"] == 1 and report["missing"] == 1
    assert not run_check(root, cycle=("easy",))["counts"]["pass"]


def test_first_per_tier_sample_is_independent_and_100(tmp_path):
    # 文件夹具不需要放大到 128 条；独立有效循环本身锁住采样身份与数量。
    identities = [(task, ep) for task in TASK_ORDER for ep in range(len(checker.effective_cycle(task, FULL_CYCLE)))]
    assert len(identities) == 100
    assert sum(checker.expected_identity(task, ep, 0, FULL_CYCLE)["difficulty"] in DIFFICULTIES for task, ep in identities) == 52
    assert sum(len(rules.EXPECTED_CHECKS[task]) for task, ep in identities
               if checker.expected_identity(task, ep, 0, FULL_CYCLE)["difficulty"] in DIFFICULTIES) == 80
    root = write_products(tmp_path / "first", cycle=("easy", "hard"), episodes=5)
    report = run_check(root, cycle=("easy", "hard"), episodes=5)
    assert report["pass"]
    assert [row["episode"] for row in report["samples"]] == [0, 1]
    assert run_check(root, cycle=("easy", "hard"), episodes=5, sample="all")["schema"]["files"] == 5


def test_recovery_absolute_index_and_full_count():
    for task in TASK_ORDER:
        modes = [checker.expected_identity(task, ep, 0, FULL_CYCLE)["recovery_mode"] for ep in range(400)]
        if task in checker.FAIL_RECOVER_TASKS:
            assert modes.count("z") == modes.count("xy") == 3
        else:
            assert all(mode is None for mode in modes)
    assert checker.expected_identity("VideoPlaceButton", 5, 0, FULL_CYCLE)["recovery_mode"] == "xy"
    assert checker.expected_identity("VideoUnmaskSwap", 8, 0, FULL_CYCLE)["recovery_mode"] == "xy"


def test_fr_constant_matches_generator_when_w2_is_integrated():
    source = (checker.REPO_ROOT / "scripts/data-generation-newSeed/generate_dataset_newseed.py").read_text()
    module = ast.parse(source)
    constants = [node.value for node in module.body if isinstance(node, ast.Assign)
                 and any(isinstance(target, ast.Name) and target.id == "FAIL_RECOVER_TASKS" for target in node.targets)]
    if not constants:
        pytest.skip("W2 并行修改尚未合入，整合后须复跑此断言")
    value = constants[0]
    if isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id in ("set", "frozenset"):
        value = value.args[0]
    assert set(ast.literal_eval(value)) == checker.FAIL_RECOVER_TASKS


def test_golden_provenance_and_all_timestep_dtype_set():
    assert len(list(GOLDEN_DIR.glob("*.json"))) == 16
    for task in TASK_ORDER:
        golden = json.loads((GOLDEN_DIR / f"{task}.json").read_text())
        assert golden["source"] == {"file": f"/data/hongzefu/robomme_data_h5/record_dataset_{task}.h5",
                                    "revision": checker.REVISION, "episode": 0}
        assert golden["variable_shape_keys"] == ["setup/task_goal"]
        extra = list(checker.RECOVERY_KEYS) if task in checker.FAIL_RECOVER_TASKS else []
        assert golden["excluded_keys"] == list(checker.RAW_KEYS) + extra
        assert "action/joint_action" in golden["timestep"]
    assert json.loads((GOLDEN_DIR / "VideoPlaceButton.json").read_text())["timestep"]["action/waypoint_action"]["dtypes"] == ["float32", "float64"]


def test_export_golden_uses_all_steps_without_reading_arrays(tmp_path):
    root = write_products(tmp_path / "source", cycle=("easy",))
    official = tmp_path / "official"
    official.mkdir()
    source = official / "record_dataset_ButtonUnmaskSwap.h5"
    first_h5(root).rename(source)
    with h5py.File(source, "r+") as handle:
        first = handle["episode_0/timestep_0/action"]
        del first["waypoint_action"]
        first.create_dataset("waypoint_action", data=np.zeros(7, dtype="float32"))
        action = handle["episode_0/timestep_1/action"]
        del action["waypoint_action"]
        action.create_dataset("waypoint_action", data=np.zeros(7, dtype="float64"))
    exported = checker.export_golden(official, tmp_path / "golden", tasks=("ButtonUnmaskSwap",))
    golden = json.loads((tmp_path / "golden/ButtonUnmaskSwap.json").read_text())
    assert exported["files"][0]["timesteps"] == 3
    assert golden["timestep"]["action/waypoint_action"]["dtypes"] == ["float32", "float64"]


def test_compare_length_not_truncated_and_never_gate(tmp_path):
    left = write_products(tmp_path / "left")
    right = write_products(tmp_path / "right")
    with h5py.File(first_h5(right), "r+") as handle:
        del handle["episode_0/timestep_4"]
    report = run_check(left, compare_dir=right)
    assert report["pass"]
    assert report["compare"] == {"candidates": 1, "matched": 0, "seed_mismatch": 0, "len_mismatch": 1,
                                  "elements": 0, "max_abs": "na"}


def test_compare_actual_values_and_seed_mismatch(tmp_path):
    left = write_products(tmp_path / "left")
    right = write_products(tmp_path / "right")
    with h5py.File(first_h5(right), "r+") as handle:
        handle["episode_0/timestep_1/action/joint_action"][...] = 0.25
    report = run_check(left, compare_dir=right)
    assert report["compare"]["matched"] == 1
    assert report["compare"]["elements"] == 40
    assert report["compare"]["max_abs"] == 0.25
    path = first_h5(right)
    seed = checker.read_products(right)["files"][0]["seed"]
    path.rename(path.with_name(path.name.replace(f"seed{seed}", f"seed{seed + 1}")))
    assert run_check(left, compare_dir=right)["compare"]["seed_mismatch"] == 1


def test_dump_subgoals_preserves_each_boundary_and_evidence(tmp_path):
    root = write_products(tmp_path / "dump")
    output = tmp_path / "subgoals.json"
    assert checker.main(["dump-subgoals", "--output-dir", str(root), "--out", str(output)]) == 0
    dumped = json.loads(output.read_text())["samples"][0]
    assert len(dumped["boundaries"]) == 5
    assert dumped["xhard_knobs"] == {"press_count": 3, "swap_count": 4}
    assert len(dumped["runtime_checks"]) == 4


def test_check_cli_writes_four_lines_and_real_report(tmp_path, capsys):
    root = write_products(tmp_path / "cli", tasks=TASK_ORDER, cycle=("easy",))
    args = ["check", "--output-dir", str(root), "--golden-dir", str(GOLDEN_DIR), "--cycle", "easy",
            "--episodes", "1", "--workers", "2", "--out-json", str(tmp_path / "check.json"),
            "--out-md", str(tmp_path / "check.md")]
    assert checker.main(args) == 0
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 4 and all("=PASS" in line for line in lines)
    assert json.loads((tmp_path / "check.json").read_text())["schema"]["files"] == 16
    assert "混合档 H5 校验" in (tmp_path / "check.md").read_text()


def test_vpb_static_baseline_three_demo_plus_one_execution():
    # AST 读取父类字典，不导入环境、不启动仿真；additional_place=False 关闭两个条件分支。
    source = (checker.REPO_ROOT / "src/robomme/robomme_env/VideoPlaceButton.py").read_text()
    tree = ast.parse(source)
    load = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "_load_scene")
    task_block = next(node for node in load.body if isinstance(node, ast.Try))
    pickups = []
    for statement in task_block.body:
        if not isinstance(statement, ast.Expr) or not isinstance(statement.value, ast.Call):
            continue
        call = statement.value
        if not isinstance(call.func, ast.Attribute) or call.func.attr != "append" or not call.args or not isinstance(call.args[0], ast.Dict):
            continue
        fields = {key.value: value for key, value in zip(call.args[0].keys, call.args[0].values) if isinstance(key, ast.Constant)}
        name = fields.get("name")
        if isinstance(name, ast.JoinedStr) and all(isinstance(part, ast.Constant) for part in name.values):
            name_text = "".join(part.value for part in name.values)
        elif isinstance(name, ast.Constant):
            name_text = name.value
        else:
            continue
        if name_text == "pick up the cube":
            pickups.append(ast.literal_eval(fields["demonstration"]))
    assert pickups == [True, True, True, False]
    assert rules.SUBGOAL_RULES["VideoPlaceButton"][0]["expect"] == "knob_plus:extra_groups:4"
