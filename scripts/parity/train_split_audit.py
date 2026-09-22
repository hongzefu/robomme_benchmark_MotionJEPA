#!/usr/bin/env python3
"""离线核对器：G2 配置外提完整、G3 字段归属完整、C1 失败与子集覆盖。

三个子命令都只读源码、方案与运行产物，**不创建环境、不抽随机数、不占 GPU**：

* ``config-map``（G2 `SAMPLING_ORIGINAL`）：十六环境的 decision／native 每个叶子键是否在
  本环境源码里有消费点；类属性派生的键是否与类属性逐值相同；三种传法解析后 dtype 是否不变。
* ``field-ownership``（G3 `FIELD_OWNERSHIP`）：方案第二节字段表里的每个
  ``sampling_config.decision|native.<名字>`` 是否都能落到快照的对应块上；标「规则不改」的
  native 项不得出现在 decision 里。
* ``coverage``（C1 `TRAIN_COVERAGE`）：运行目录里 144 条身份是否都有终态，按状态分类计数。

    uv run --no-sync python scripts/parity/train_split_audit.py config-map
    uv run --no-sync python scripts/parity/train_split_audit.py field-ownership
    uv run --no-sync python scripts/parity/train_split_audit.py coverage --run <运行目录> [--run ...]
"""

from __future__ import annotations

import argparse
import ast
import importlib
import json
import re
import sys
from pathlib import Path

def _find_repo_root() -> Path:
    """脚本可能被放到仓库外执行（例如集群上的临时目录），所以按标志文件定位仓库。"""
    here = Path(__file__).resolve().parents[2]
    for candidate in (here, Path.cwd(), *Path.cwd().parents):
        if (candidate / "scripts" / "seed_layout.py").exists():
            return candidate
    return here


REPO_ROOT = _find_repo_root()
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from seed_layout import ALL_TASKS  # noqa: E402

ENV_DIR = REPO_ROOT / "src" / "robomme" / "robomme_env"
PLAN = REPO_ROOT / "NEWTASK_RELEASE_V3_PLAN.md"

# 方案第二节的字段名是「概念名」，与快照里的实际键名有少数是同义改写；
# 每条都写清楚为什么，不允许无理由的放行。
# 方案第二节写的是「概念名」，快照里是实现名；下表逐条交代每个概念名落在哪、为什么。
# 通用规则放 "*"：所有环境共用。没有理由的放行一律不允许。
FIELD_ALIASES: dict[str, dict[str, str]] = {
    "*": {
        # decision.distractor.{count,palette,placement}：本轮不启用干扰物，
        # 快照里只有 decision.distractor=None，子键要等启用时才出现。
        "count": "decision.distractor=None（本轮不启用，子键未展开）",
        "palette": "decision.distractor=None（本轮不启用，子键未展开）",
        "placement": "decision.distractor=None（本轮不启用，子键未展开）",
        # 「规则不改、由规则计算」的动作展开类概念，不是采样键，落在 episode_spec.actions 上
        "task_expansion": "按规则计算的动作展开，落 episode_spec.actions，非采样键",
        "recovery": "恢复规格落 episode_spec.actions.recovery；规则本身不参数化",
        "pick_rule": "拾取顺序按规则计算，native.parameters.pick_rule 为说明键",
        "hidden_rule": "藏物关系按规则计算，native.parameters.hidden_rule 为说明键",
        "partner_rule": "最近邻搭档按实际 XY 计算，落 episode_spec.actions.swap_pairs",
        "cube_pose": "native.positions.cubes（逐块位姿的采样域）",
        "color": "按难度取原值的颜色数，落 native.parameters.color 或 positions.cube_color",
    },
    "StopCube": {
        "route_rotation": "native.parameters.route_rotation_deg",
        "time_rules": "native.parameters.steps_press_expression / stop_window_expression",
    },
    "SwingXtimes": {
        "cube_region": "native.positions.cubes",
        "target_regions": "native.positions.targets（两个圆盘）",
    },
    "BinFill": {
        "color_selection": "配额分配规则，消费点在 _load_scene 的 color_pool/put_in_color",
        "initialize_color_order": "按初始化序号记进 episode_spec.initializations.<n>.color_order",
        "put_in_order": "由 episode_spec.actions.pick_place 按规则计算，非独立采样键",
    },
    "VideoUnmask": {
        "bin_pose": "native.positions.bins",
        "reveal_timing": "native.positions.reveal_window",
    },
    "ButtonUnmask": {
        "bin_pose": "native.positions.bins",
        "button_trigger": "native.positions.button + parameters.pick_rule",
    },
    "VideoUnmaskSwap": {
        "swap_path": "native.parameters.swap_path",
    },
    "ButtonUnmaskSwap": {
        "bin_pose": "native.positions.bins",
        "container_offsets": "native.positions.anchors.offset_scale 及三套锚点",
        "object_selection": "native.parameters.color_order / hidden_rule 与 decision 的次数范围共同承担",
    },
    "PickHighlight": {
        "highlight_count_range": "decision.highlight_count（原值是定值不是范围）",
    },
    "VideoRepick": {
        "swap_enabled": "decision.swap（按难度给 swap_min/max，0 即关闭）",
        "swap_count_range": "decision.swap",
        "layout_draw": "native.positions.easy_medium_cubes / hard_cubes",
        "swap_timing": "交换窗口按规则计算，落 episode_spec.actions.swap_windows",
    },
    "VideoPlaceButton": {
        "object_pose": "native.positions.cubes",
        "task_flag": "native.parameters.task_mapping",
        "demo_template": "native.parameters.task_mapping",
        "swap_selection": "decision.swap 决定是否交换，选哪两台由原 randperm 规则",
    },
    "VideoPlaceOrder": {
        "object_pose": "native.positions.cubes",
        "answer_mapping": "native.parameters.answer_selection",
        "action_expansion": "按规则计算的动作展开，落 episode_spec.actions",
    },
    "InsertPeg": {
        "box_pose": "native.positions.box",
        "box_geometry": "native.positions.box 的 inner/outer_radius_factor",
        "peg_pose": "native.positions.peg_sampling",
        "rejection": "native.positions.peg_sampling 的 max_attempts 与两条距离判据",
        "target_rule": "native.parameters.target_peg（目标恒 peg_0）",
        "reference_id": "decision.near_target_distractor=None（本轮不启用）",
        "radial_range": "decision.near_target_distractor=None（本轮不启用）",
        "azimuth_policy": "decision.near_target_distractor=None（本轮不启用）",
    },
    "MoveCube": {
        "goal_regions": "native.positions.goal_demo / goal_execution",
        "pose_draw": "native.positions 里的各采样域与 peg_size 的兼容抽样",
    },
    "PatternLock": {
        "grid_geometry": "native.positions.grid_center / grid_spacing",
    },
    "RouteStick": {
        "grid_geometry": "native.positions.grid_center / grid_spacing_x / grid_spacing_y",
        "length": "native.parameters.configs[<难度>].length",
        "motion_template": "按规则计算的动作模板，落 episode_spec.actions",
        "node_mapping": "网格节点由公式定位，非采样键",
        "trail_steps": "native.positions.tcp_trail.end_offset_steps（步 2 恢复为官方 40）",
        "yaw": "native.positions.yaw_deg",
    },
}


# G2 的显式豁免：快照里记了数值、但本轮**确实没有消费点**的键，逐条写明理由。
# 与别名表同样纪律——不允许无理由放行；启用相应功能时这些键就会长出消费点。
NEUTRAL_KEYS: dict[str, str] = {
    "VideoUnmaskSwap.decision.swap_speed_multiplier":
        "原值 1＝不乘倍率，原代码里没有「乘速度倍率」这一步；启用 1.5 倍时才会出现消费点",
    "ButtonUnmaskSwap.decision.swap_speed_multiplier":
        "同上",
    "VideoPlaceButton.decision.demo_object_count":
        "原值 1＝只演示一个 target_cube，原代码没有按数量循环的结构；扩到 2 块时才会出现消费点",
    "VideoPlaceOrder.decision.demo_object_count":
        "同上",
    "MoveCube.native.parameters.dir_sample.consumed":
        "记录型元数据：标明这次 randint 抽了但未被消费（抽样本身按红线 R8 保留，落 sampling_trace）",
    "MoveCube.native.parameters.obj_selection.mapping[0]":
        "映射语义写死在 `-1 if obj_sample == 0 else 1`，记录它只为让规格可读，不是可调参数",
    "MoveCube.native.parameters.obj_selection.mapping[1]":
        "同上",
}


def _leaf_keys(node, prefix: str = "") -> list[str]:
    return [path for path, _ in _leaves(node, prefix)]


def _leaves(node, prefix: str = "") -> list[tuple[str, object]]:
    """返回 (路径, 叶子值) 列表；路径里保留层级，供按祖先判定消费点。"""
    out: list[tuple[str, object]] = []
    if isinstance(node, dict):
        for key, value in node.items():
            out.extend(_leaves(value, f"{prefix}.{key}" if prefix else str(key)))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            out.extend(_leaves(value, f"{prefix}[{index}]"))
    else:
        out.append((prefix, node))
    return out


def _key_names(node) -> set[str]:
    """快照里出现过的全部键名（不含层级），用于宽松匹配方案里的概念名。"""
    names: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            names.add(str(key))
            names |= _key_names(value)
    elif isinstance(node, list):
        for value in node:
            names |= _key_names(value)
    return names


def _source_without_snapshot(task: str) -> str:
    """去掉 NATIVE_SAMPLING 字面量与 _native_decision 函数体后的源码，用于找真正的消费点。"""
    path = ENV_DIR / f"{task}.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    spans: list[tuple[int, int]] = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "NATIVE_SAMPLING" for t in node.targets
        ):
            spans.append((node.lineno, node.end_lineno or node.lineno))
        if isinstance(node, ast.FunctionDef) and node.name in ("_native_decision", "native_blocks"):
            spans.append((node.lineno, node.end_lineno or node.lineno))
    lines = source.splitlines()
    keep = [
        line
        for index, line in enumerate(lines, start=1)
        if not any(start <= index <= end for start, end in spans)
    ]
    return "\n".join(keep)


def cmd_config_map(args: argparse.Namespace) -> int:
    """G2：每个叶子键要么在源码里被消费，要么明示为「只作留档的说明键」。"""
    unmapped: list[str] = []
    value_mismatch: list[str] = []
    documentation_only: list[str] = []
    checked = 0
    for task in ALL_TASKS:
        module = importlib.import_module(f"robomme.robomme_env.{task}")
        cls = getattr(module, task)
        decision, native = module.native_blocks(cls)
        consumers = _source_without_snapshot(task)
        for block_name, block in (("decision", decision), ("native", native)):
            for leaf, value in _leaves(block):
                checked += 1
                # 叶子或任一祖先被消费即算落地：代码里通常整块取出（cfg = self._sampling[...][...]）
                parts = [p for p in re.split(r"[.\[]", leaf) if p and not p.rstrip("]").isdigit()]
                names = [p.rstrip("]") for p in parts]
                if any(f'"{n}"' in consumers or f"'{n}'" in consumers for n in names):
                    continue
                # 未被消费时按值的类型分流：说明性字符串／已关闭的开关只作留档，
                # **数值型的键必须有消费点**，否则就是真的漏接。
                if isinstance(value, str) or value is None:
                    documentation_only.append(f"{task}.{block_name}.{leaf}")
                    continue
                full = f"{task}.{block_name}.{leaf}"
                if full in NEUTRAL_KEYS:
                    documentation_only.append(f"{full}（豁免：{NEUTRAL_KEYS[full]}）")
                    continue
                unmapped.append(f"{full} = {value!r}")
        # 类属性派生值必须与类属性逐值相同（StopCube／MoveCube／InsertPeg 没有难度配置，跳过）
        for difficulty, cfg in getattr(cls, "configs", {}).items():
            for key, value in cfg.items():
                for block in (decision, native.get("parameters", {})):
                    holder = block.get(key) if isinstance(block, dict) else None
                    if isinstance(holder, dict) and difficulty in holder:
                        snapshot = holder[difficulty]
                        expected = list(value) if isinstance(value, (list, tuple)) else value
                        if isinstance(snapshot, dict):
                            continue
                        if snapshot != expected:
                            value_mismatch.append(f"{task}.{key}[{difficulty}] {snapshot} != {expected}")
        # 三种传法解析结果必须逐字相同（含 dtype：JSON 序列化后类型不变）
        dump = lambda payload: json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)  # noqa: E731
        if not (
            dump(module._resolve_sampling_config(cls, None))
            == dump(module._resolve_sampling_config(cls, {"decision": decision, "native": native}))
            == dump(module._resolve_sampling_config(cls, native))
        ):
            value_mismatch.append(f"{task}: 三种传法解析结果不一致")

    status = "PASS" if not unmapped and not value_mismatch else "FAIL"
    print(
        f"SAMPLING_ORIGINAL={status} tasks={len(ALL_TASKS)} "
        f"value_mismatch={len(value_mismatch)} unmapped={len(unmapped)}"
    )
    print(f"# 检查叶子键 {checked} 个；其中只作留档的说明键 {len(documentation_only)} 个（不计入 unmapped）")
    for item in unmapped[: args.show]:
        print(f"# 未找到消费点：{item}")
    for item in value_mismatch[: args.show]:
        print(f"# 取值不符：{item}")
    return 0 if status == "PASS" else 1


def cmd_field_ownership(args: argparse.Namespace) -> int:
    """G3：方案第二节的每个字段 token 都要落到快照的对应块上。"""
    text = PLAN.read_text(encoding="utf-8")
    # 每节到下一个 ## / ### 标题为止：不这样切的话，最后一节会吞掉第二部分的映射说明，
    # 把别的环境的字段名算到 RouteStick 头上。
    sections = [
        match.group(1) + "\n" + match.group(2)
        for match in re.finditer(
            r"^### 2\.\d+ (\S+)\n(.*?)(?=^#{2,3} |\Z)", text, flags=re.M | re.S
        )
    ]
    total = 0
    unmapped: list[str] = []
    overrides: list[str] = []
    snapshots: dict[str, tuple[set[str], set[str]]] = {}
    for task in ALL_TASKS:
        module = importlib.import_module(f"robomme.robomme_env.{task}")
        cls = getattr(module, task)
        decision, native = module.native_blocks(cls)
        # 用解析后的 native（含 _resolve 注入的 configs）核对，否则 configs 里的键会被误判未落
        resolved = module._resolve_sampling_config(cls, None)
        snapshots[task] = (_key_names(decision), _key_names(resolved))

    for section in sections:
        task = section.splitlines()[0].strip()
        if task not in snapshots:
            continue
        decision_names, native_names = snapshots[task]
        aliases = {**FIELD_ALIASES.get("*", {}), **FIELD_ALIASES.get(task, {})}
        for match in re.finditer(r"`sampling_config\.(decision|native)\.([^`]+)`", section):
            block, raw = match.group(1), match.group(2)
            # 一个 token 可能是 a/b/c 或 a.{x,y} 的组合，拆成单个概念名
            # a.{x,y}_suffix 展开成 a.x_suffix、a.y_suffix，不能直接删花括号
            variants = [raw]
            brace = re.search(r"\{([^}]*)\}", raw)
            if brace:
                variants = [
                    raw[: brace.start()] + option.strip() + raw[brace.end():]
                    for option in brace.group(1).split(",")
                ]
            names_in_token = [n for variant in variants for n in re.split(r"[/.]", variant) if n]
            for name in names_in_token:
                total += 1
                names = decision_names if block == "decision" else native_names
                other = native_names if block == "decision" else decision_names
                if name in names or name in aliases:
                    continue
                if name in other:
                    overrides.append(f"{task}.{block}.{name}（落在了另一块）")
                    continue
                unmapped.append(f"{task}.{block}.{name}")
    status = "PASS" if not unmapped and not overrides else "FAIL"
    print(
        f"FIELD_OWNERSHIP={status} tasks={len(ALL_TASKS)} "
        f"unmapped={len(unmapped)} native_rule_overrides={len(overrides)}"
    )
    print(f"# 方案第二节字段 token 展开后共 {total} 项")
    for item in unmapped[:30]:
        print(f"# 未落到快照：{item}")
    for item in overrides[:20]:
        print(f"# 归属块不符：{item}")
    return 0 if status == "PASS" else 1


def cmd_coverage(args: argparse.Namespace) -> int:
    """C1：144 条身份是否都有终态，按状态分类。"""
    manifest = json.loads(
        (REPO_ROOT / "scripts" / "configs" / "newtask-v3" / "subset_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    expected = {f"{row['task']}/{row['episode']}" for row in manifest["rows"]}
    terminal: dict[str, dict[str, str]] = {}
    for run in args.run:
        run_dir = Path(run)
        for results_path in sorted((run_dir / "results").glob("*.json")) if (run_dir / "results").is_dir() else []:
            path_name = results_path.stem
            for item in json.loads(results_path.read_text(encoding="utf-8"))["results"]:
                identity = f"{item['task']}/{item['episode']}"
                state = "ok" if item.get("ok") else f"error:{item.get('error_type')}"
                terminal.setdefault(identity, {})[path_name] = state
    paths_wanted = set(args.paths.split(",")) if args.paths else None
    complete = {
        identity
        for identity, states in terminal.items()
        if paths_wanted is None or paths_wanted <= set(states)
    }
    missing = sorted(expected - complete)
    failures = sorted(
        f"{identity}/{path}={state}"
        for identity, states in terminal.items()
        for path, state in states.items()
        if state != "ok"
    )
    status = "PASS" if not missing and not failures else "FAIL"
    print(
        f"TRAIN_COVERAGE={status} expected={len(expected)} terminal={len(complete)} "
        f"missing={len(missing)}"
    )
    print(f"# 非 ok 的终态 {len(failures)} 条" + ("：" + "；".join(failures[:10]) if failures else ""))
    for item in missing[:15]:
        print(f"# 缺终态：{item}")
    return 0 if status == "PASS" else 1


def cmd_branch_coverage(args: argparse.Namespace) -> int:
    """5b：144 条子集实际覆盖了哪些分支；未出现的列为缺口，不含糊带过。

    只读两处证据，不重跑仿真：
    * 冻结的 144 条 manifest（task／难度／恢复模式）；
    * C 路导出的 episode_spec（本局真实取到的值，如 dynamic、交换次数、拾取数）。
    """
    manifest = json.loads(
        (REPO_ROOT / "scripts" / "configs" / "newtask-v3" / "subset_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    rows = manifest["rows"]
    cells = {(row["task"], row["difficulty"]) for row in rows}
    recovery = {"z": 0, "xy": 0, "off": 0}
    for row in rows:
        mode = row["recovery_mode"]
        recovery["off" if mode is None else str(mode)] += 1

    # 从 C 路规格里读本局真实取值
    branch: dict[str, set] = {}
    specs_read = 0
    for run in args.run:
        run_dir = Path(run)
        for identity_dir in sorted((run_dir / "C").glob("*_episode_*")) if (run_dir / "C").is_dir() else []:
            spec_file = identity_dir / "episode_spec.json"
            if not spec_file.exists():
                continue
            specs_read += 1
            spec = json.loads(spec_file.read_text(encoding="utf-8"))
            task = spec.get("identity", {}).get("task") or spec.get("task")
            layout = spec.get("layout", {})
            objects = spec.get("objects", {})
            if "dynamic" in layout:
                branch.setdefault(f"{task}.dynamic", set()).add(bool(layout["dynamic"]))
            for key in ("n_swaps", "n_picks", "num_repeats", "put_in_color", "target_choice"):
                if key in objects and isinstance(objects[key], (int, float, bool)):
                    branch.setdefault(f"{task}.{key}", set()).add(objects[key])
            if "type_choice" in layout:
                branch.setdefault(f"{task}.layout_type", set()).add(layout["type_choice"])

    missing_cells = sorted(
        {(task, difficulty) for task in ALL_TASKS for difficulty in ("easy", "medium", "hard")}
        - cells
    )
    gaps: list[str] = []
    # 方案点名要覆盖的分支：BinFill 两种 dynamic、零／非零交换、单双拾取
    for name, values in sorted(branch.items()):
        if name.endswith(".dynamic") and len(values) < 2:
            gaps.append(f"{name} 只出现 {sorted(values)}（缺另一种）")
        if name.endswith(".n_swaps"):
            # 「零／非零交换都要覆盖」只对**原配置允许零交换**的环境成立：
            # VideoRepick/hard 是 swap_min=swap_max=0；两个 Swap 环境各档 swap_min 都 ≥1，
            # 原值下零交换不可能出现，把它们也算缺口是套错了规则。
            task_name = name.split(".")[0]
            allows_zero = any(
                int(cfg.get("swap_min", 1)) == 0
                for cfg in getattr(
                    importlib.import_module(f"robomme.robomme_env.{task_name}"), task_name
                ).configs.values()
            )
            if allows_zero and not ({0} & values and {v for v in values if v}):
                gaps.append(f"{name} 只出现 {sorted(values)}（该环境允许零交换却未覆盖）")
        if name.endswith(".n_picks") and len(values) < 2:
            gaps.append(f"{name} 只出现 {sorted(values)}（单双拾取未同时覆盖）")
    status = "PASS" if not missing_cells else "FAIL"
    print(
        f"SUBSET_BRANCH_COVERAGE={status} cells={len(cells)}/48 "
        f"recovery_z={recovery['z']} recovery_xy={recovery['xy']} recovery_off={recovery['off']} "
        f"specs_read={specs_read} gaps={len(gaps)}"
    )
    for task, difficulty in missing_cells[:10]:
        print(f"# 缺格：{task}/{difficulty}")
    for gap in gaps[: args.show]:
        print(f"# 覆盖缺口：{gap}")
    if not gaps and specs_read:
        print("# 方案点名的分支（dynamic 两种、零／非零交换、单双拾取）在已读规格里均已出现")
    return 0 if status == "PASS" else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="G2／G3／C1 离线核对器")
    sub = parser.add_subparsers(dest="command", required=True)
    cfgmap = sub.add_parser("config-map", help="G2 SAMPLING_ORIGINAL")
    cfgmap.add_argument("--show", type=int, default=20, help="最多列出多少条明细")
    cfgmap.set_defaults(func=cmd_config_map)
    sub.add_parser("field-ownership", help="G3 FIELD_OWNERSHIP").set_defaults(func=cmd_field_ownership)
    cov = sub.add_parser("coverage", help="C1 TRAIN_COVERAGE")
    cov.add_argument("--run", action="append", required=True, help="运行目录，可重复")
    cov.add_argument("--paths", default=None, help="要求齐备的路径，如 A1,A2,B,C,D")
    cov.set_defaults(func=cmd_coverage)
    branch = sub.add_parser("branch-coverage", help="5b：144 条子集的分支覆盖清单")
    branch.add_argument("--run", action="append", required=True, help="运行目录，可重复")
    branch.add_argument("--show", type=int, default=20)
    branch.set_defaults(func=cmd_branch_coverage)
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
