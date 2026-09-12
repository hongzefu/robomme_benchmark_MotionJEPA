"""新值注入专项的编排入口（NEW_VALUE_INJECTION_TEST_PLAN 第五节）。

子命令：

* ``plan``  —— 按契约里的组列表生成并冻结每组 100 条规格，写运行根目录与清单（步骤 0）。
* ``check`` —— 从冻结的规格**独立重算**全部计数与几何，打第 5.7 节的判定行。
* ``plot``  —— 出跑前／跑后三类图（委托 :mod:`scripts.injection.plots`）。
* ``run``   —— 校准与实跑的编排（步骤 2～5），复用生产入口 ``generate_dataset_newseed``。

``plan`` 拒绝已存在的运行根目录；``check``／``plot`` 只从该编号的冻结清单读输入。
本模块属于测试侧工具，**生产代码不导入它**。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Sequence

# 本文件位于 scripts/injection/，向上两级是仓库根（与搬迁前 tests/_shared/ 同深度，勿改成 parents[1]）
REPO_ROOT = Path(__file__).resolve().parents[2]
#: feasibility 实跑的单条 episode 墙钟上限（秒），用户 2026-09-11 定「卡死降低到600」
FEASIBILITY_EPISODE_TIMEOUT_S = 600.0
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from robomme.robomme_env.utils import bin_collision as bc  # noqa: E402

from .categories import legal_categories, observed_values  # noqa: E402
from .contract import Contract, ContractError, audit_overrides, derive_all, load_contract  # noqa: E402
from .delivery import DeliveryConfig, DeliveryError, build_delivery_manifest, load_delivery_config  # noqa: E402
from .sampling import COARSE_BINS, GROUP_SIZE  # noqa: E402
from .specs import (  # noqa: E402
    CUBE_HALF_SIZE,
    EXCLUDED_GROUPS,
    GENERATOR_VERSION,
    SPEC_SCHEMA_VERSION,
    DEFAULT_SEED,
    build_group,
    difficulties_of,
    operand_sha256,
    canonical_json,
    record_sha256,
    rotate_xy,
    button_obb,
    board_obbs,
    cube_obb,
    obb2d_intersect,
)

DEFAULT_SAMPLING_CONFIG = REPO_ROOT / "scripts" / "configs" / "newtask-v2" / "native_sampling.json"
INJECTION_ROOT = REPO_ROOT / "artifacts" / "injection"


class CampaignError(RuntimeError):
    """编排层的错误：目录冲突、清单缺失、判据不通过等。"""


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def run_root(run_id: str) -> Path:
    if not run_id or "/" in run_id or run_id.startswith("."):
        raise CampaignError(f"运行编号不合法：{run_id!r}")
    return INJECTION_ROOT / run_id


# ── plan ────────────────────────────────────────────────────────────────────
def cmd_plan(
    run_id: str,
    seed: int,
    per_group: int,
    sampling_config: Path,
    contract_path: Path,
    delivery_config: Path | None = None,
) -> dict[str, Any]:
    """按契约里的组列表生成规格并冻结（v2 契约 11 组，v3 契约 14 组）。运行编号不可复用：清单已存在直接拒绝。

    ``contract_path`` 是取值域与分配的约定（``injection_contract_v*.json``），是候选分布的派生依据；
    ``sampling_config`` 只再提供几何常量。两者的身份都写进清单。

    ``delivery_config``（2026-09-12 每 env 400 条交付引入）：给出时每组候选数 = 该组 ``blocks × 100``
    （block 0 与不给配置时逐条散列相同），配置文件的路径与散列一并冻结进清单；不给时每组固定 100 条，
    07/08/09 的命令行行为逐字不变。

    ⚠ 目录存在判据改为「``manifest.json`` 已存在」而不是「目录已存在」：全量日志要先落到
    ``<运行根>/logs/`` 里（该目录被 git 跟踪），tmux 的 ``tee`` 必须先建目录，plan 不能因此拒绝。
    """
    if per_group != GROUP_SIZE:
        raise CampaignError(f"本轮固定每组 {GROUP_SIZE} 条（多 block 时每 block 100 条），收到 --per-group {per_group}")
    root = run_root(run_id)
    if (root / "manifest.json").exists() or (root / "specs").exists():
        raise CampaignError(f"运行编号已冻结过，编号不可复用：{root}")

    sampling = json.loads(sampling_config.read_text(encoding="utf-8"))
    contract = load_contract(contract_path)
    if contract.generator_seed != seed:
        raise CampaignError(f"契约声明 generator_seed={contract.generator_seed}，命令行给的是 {seed}")
    delivery: DeliveryConfig | None = None
    blocks_by_group: dict[tuple[str, str], int] = {}
    if delivery_config is not None:
        try:
            delivery = load_delivery_config(delivery_config, contract)
        except DeliveryError as exc:
            raise CampaignError(f"交付配置不合法：{exc}") from exc
        blocks_by_group = delivery.blocks_by_group()
    _mismatches, problems = audit_overrides(contract, sampling)
    if problems:
        raise CampaignError("契约与原值回算不一致且未登记 override，拒绝冻结：\n  " + "\n  ".join(problems[:5]))
    # 组列表由契约驱动（v2 契约恰是原 11 组同序，v3 多出三个 xhard 组），不再读模块常量 GROUPS
    groups = [(group.task, group.difficulty) for group in contract.groups()]
    # 冻结进规格的是「取值域散列」（parameters + positions，只取本次消费到的难度档），不是文件字节散列；
    # 文件字节散列另存一份作参考，源码指纹刷新时它会变，但不影响验收。
    config_sha = operand_sha256(sampling, difficulties_of(groups))
    file_sha = _sha256_file(sampling_config)

    started = time.monotonic()
    groups_meta: list[dict[str, Any]] = []
    stats_all: dict[str, Any] = {}
    for task, difficulty in groups:
        blocks = int(blocks_by_group.get((task, difficulty), 1))
        group = build_group(task, difficulty, sampling, contract, seed, blocks=blocks)
        relative = Path("specs") / task / f"{difficulty}.json"
        _write_json(root / relative, group.as_document(config_sha))
        meta = {
            "task": task,
            "difficulty": difficulty,
            "path": str(relative),
            "file_sha256": _sha256_file(root / relative),
            "episodes": len(group.episodes),
            "derived_seed": group.derived_seed,
        }
        if blocks > 1:
            meta["blocks"] = blocks
        groups_meta.append(meta)
        stats_all[f"{task}/{difficulty}"] = {k: v for k, v in group.stats.items() if k != "rejections"}
        stats_all[f"{task}/{difficulty}"]["rejection_samples"] = group.stats["rejections"][:8]
        print(f"  冻结 {task}/{difficulty}: {len(group.episodes)} 条（{blocks} 个 block）", flush=True)

    manifest = {
        "run_id": run_id,
        "spec_schema_version": SPEC_SCHEMA_VERSION,
        "generator_version": GENERATOR_VERSION,
        "generator_seed": seed,
        "per_group": per_group,
        "sampling_config_path": str(sampling_config.relative_to(REPO_ROOT)),
        "sampling_operands_sha256": config_sha,
        "sampling_config_file_sha256": file_sha,
        "contract_path": str(contract_path.resolve().relative_to(REPO_ROOT)),
        "contract_sha256": contract.sha256,
        "contract_version": contract.version,
        "groups": groups_meta,
        "excluded_groups": [list(item) for item in EXCLUDED_GROUPS],
        "elapsed_s": round(time.monotonic() - started, 1),
    }
    if delivery is not None:
        manifest["delivery_config_path"] = str(delivery_config.resolve().relative_to(REPO_ROOT))
        manifest["delivery_config_sha256"] = delivery.sha256
        manifest["blocks"] = {f"{task}/{difficulty}": blocks for (task, difficulty), blocks in blocks_by_group.items()}
    _write_json(root / "manifest.json", manifest)
    _write_json(root / "plan_stats.json", stats_all)
    total = sum(item["episodes"] for item in groups_meta)
    print(f"PLAN=OK run_id={run_id} groups={len(groups_meta)} specs={total} elapsed_s={manifest['elapsed_s']}")
    return manifest


def resolve_contract(manifest: dict[str, Any], override: Path | None = None) -> Contract:
    """按清单里的 ``contract_path``／``contract_sha256`` 加载契约；``override`` 只在文件被挪动时用，散列仍须一致。"""
    recorded = manifest.get("contract_path")
    if recorded is None and override is None:
        raise CampaignError("清单没有记录契约（历史运行），请用 --contract 显式指定")
    path = override if override is not None else (REPO_ROOT / recorded)
    contract = load_contract(path)
    expected = manifest.get("contract_sha256")
    if expected is not None and contract.sha256 != expected:
        raise CampaignError(
            f"契约散列与冻结时不符：当前 {contract.sha256[:12]}…（{path}），冻结时 {expected[:12]}…；"
            "拒绝在漂移的依据上验收"
        )
    return contract


def load_manifest(run_id: str) -> tuple[Path, dict[str, Any]]:
    root = run_root(run_id)
    path = root / "manifest.json"
    if not path.is_file():
        raise CampaignError(f"找不到清单：{path}；先跑 plan")
    return root, json.loads(path.read_text(encoding="utf-8"))


def load_group_documents(run_id: str) -> tuple[Path, dict[str, Any], dict[tuple[str, str], dict[str, Any]]]:
    root, manifest = load_manifest(run_id)
    documents: dict[tuple[str, str], dict[str, Any]] = {}
    for item in manifest["groups"]:
        path = root / item["path"]
        actual = _sha256_file(path)
        if actual != item["file_sha256"]:
            raise CampaignError(f"{path} 的散列与清单不符：{actual} != {item['file_sha256']}")
        documents[(item["task"], item["difficulty"])] = json.loads(path.read_text(encoding="utf-8"))
    return root, manifest, documents


# ── check ───────────────────────────────────────────────────────────────────
class Verdicts:
    """收集判定行；任一项 FAIL 则整体不通过。"""

    def __init__(self, echo: bool = False) -> None:
        self.lines = []
        self.records = []
        # echo=True 时每判完一项就打印一行，长阶段中途能看到进度，
        # 不必等全部检查跑完（check 要跑 6 分钟以上，闷着看不到任何输出）
        self.echo = echo

    def add(self, name: str, passed: bool | None, **fields: Any) -> None:
        status = "NOT_RUN" if passed is None else ("PASS" if passed else "FAIL")
        rendered = " ".join(f"{key}={value}" for key, value in fields.items())
        line = f"{name}={status}" + (f" {rendered}" if rendered else "")
        self.lines.append(line)
        self.records.append({"name": name, "status": status, **fields})
        if self.echo:
            print(line, flush=True)

    @property
    def passed(self) -> bool:
        return all(item["status"] == "PASS" for item in self.records)


def _blocks_of(doc: dict[str, Any]) -> int:
    """规格文档由几个 100 条 block 组成；07/09 的文档没有 ``blocks`` 键，即 1。"""
    return int(doc.get("blocks", 1))


def _check_scope(documents: dict[tuple[str, str], dict[str, Any]], verdicts: Verdicts) -> None:
    problems: list[str] = []
    total = 0
    blocks_seen: set[int] = set()
    for (task, difficulty), doc in documents.items():
        episodes = doc["episodes"]
        total += len(episodes)
        blocks = _blocks_of(doc)
        blocks_seen.add(blocks)
        numbers = [item["episode"] for item in episodes]
        # 多 block 时 episode 号恰为 range(blocks × 100)；文档写的 blocks 与条数不符也算问题
        if blocks < 1 or sorted(numbers) != list(range(GROUP_SIZE * blocks)):
            problems.append(f"{task}/{difficulty} 的 episode 号有缺号／重复／越界（blocks={blocks}）")
        for item in episodes:
            if item["task"] != task or item["difficulty"] != difficulty:
                problems.append(f"{task}/{difficulty}/episode {item['episode']} 的任务或难度不符")
            if record_sha256(item) != item["spec_sha256"]:
                problems.append(f"{task}/{difficulty}/episode {item['episode']} 的 spec_sha256 不符")
    excluded_present = [key for key in documents if list(key) in [list(e) for e in EXCLUDED_GROUPS]]
    if excluded_present:
        problems.append(f"排除组仍被生成：{excluded_present}")
    fields: dict[str, Any] = {"groups": len(documents), "specs": total}
    if blocks_seen != {1}:
        # 只在有多 block 组时打 blocks 字段，07/09 的判定行逐字不变
        fields["blocks"] = "/".join(str(b) for b in sorted(blocks_seen))
    verdicts.add(
        "SPEC_SCOPE",
        not problems,
        **fields,
        excluded="+".join(f"{task}-{difficulty}" for task, difficulty in EXCLUDED_GROUPS),
        problems=len(problems),
    )
    if problems:
        verdicts.records[-1]["detail"] = problems[:10]


def _check_reproducible(
    documents: dict[tuple[str, str], dict[str, Any]], sampling: dict[str, Any], contract: Contract, seed: int, verdicts: Verdicts
) -> None:
    """同 seed、**不同组调度顺序**独立再生成一次，逐记录散列必须相同。"""
    compared = 0
    differences = 0
    for task, difficulty in reversed(list(documents)):  # 按清单倒序调度全部组，证明结果与顺序无关
        doc = documents[(task, difficulty)]
        rebuilt = build_group(task, difficulty, sampling, contract, seed, blocks=_blocks_of(doc))
        frozen = doc["episodes"]
        # ⚠ 两边条数不一致也是差异：zip 会静默截断，blocks 记错时会被判成 PASS
        if len(frozen) != len(rebuilt.episodes):
            differences += abs(len(frozen) - len(rebuilt.episodes))
        for left, right in zip(frozen, rebuilt.episodes):
            compared += 1
            if left["spec_sha256"] != right["spec_sha256"]:
                differences += 1
    verdicts.add("SPEC_REPRODUCIBLE", differences == 0, compared=compared, differences=differences)


def _check_contract_derived(contract: Contract, sampling: dict[str, Any], verdicts: Verdicts) -> None:
    """契约里每个带派生表达式的域用 native_sampling.json 回算；不一致项必须全部落在 overrides 白名单里。"""
    mismatches, checked = derive_all(contract, sampling)
    _, problems = audit_overrides(contract, sampling)
    verdicts.add(
        "CONTRACT_DERIVED", not problems, fields=checked, mismatches=len(mismatches),
        overrides=len(contract.overrides), version=contract.version, problems=len(problems),
    )
    if problems:
        verdicts.records[-1]["detail"] = problems[:10]


def _check_quota(
    documents: dict[tuple[str, str], dict[str, Any]], contract: Contract, verdicts: Verdicts
) -> dict[str, Any]:
    """独立类别按完整合法集合补零后计数差 ≤1；连续量验粗箱与批次覆盖。"""
    gaps: list[str] = []
    report: dict[str, Any] = {}
    blocks_seen: set[int] = set()
    for (task, difficulty), doc in documents.items():
        categories = legal_categories(task, difficulty, contract)
        blocks = _blocks_of(doc)
        blocks_seen.add(blocks)
        # 多 block 时按 block 切片各自判（每个 block 自成一份 100 条均衡样本；两个各自 spread≤1 的 block
        # 合并后可能 spread=2，整组判会假阳）。blocks=1 时 report 形状与此前逐字相同。
        ordered = sorted(doc["episodes"], key=lambda item: int(item["episode"]))
        block_reports: list[dict[str, Any]] = []
        for block in range(blocks):
            block_reports.append(
                _quota_block_report(task, difficulty, categories, ordered[block * GROUP_SIZE : (block + 1) * GROUP_SIZE], gaps, block if blocks > 1 else None)
            )
        report[f"{task}/{difficulty}"] = block_reports[0] if blocks == 1 else {"blocks": block_reports}

    fields: dict[str, Any] = {"groups": len(documents), "batches": COARSE_BINS}
    if blocks_seen != {1}:
        fields["blocks"] = "/".join(str(b) for b in sorted(blocks_seen))
    verdicts.add("COVERAGE_QUOTA", not gaps, **fields, quota_gaps=len(gaps))
    if gaps:
        verdicts.records[-1]["detail"] = gaps[:10]
    return report


def _quota_block_report(
    task: str,
    difficulty: str,
    categories: dict[str, Any],
    records: Sequence[dict[str, Any]],
    gaps: list[str],
    block: int | None,
) -> dict[str, Any]:
    """一个 100 条 block 的配额报告；``block`` 为 None 表示单 block 组（报错文案不带 block 号）。"""
    where = f"{task}/{difficulty}" + (f"/block{block}" if block is not None else "")
    counts: dict[str, Counter] = {}
    for record in records:
        for field, values in observed_values(task, record).items():
            bucket = counts.setdefault(field, Counter())
            for value in values:
                bucket[canonical_json(value)] += 1
    group_report: dict[str, Any] = {"independent": {}, "coupled": {}, "continuous": {}}

    for field, legal in categories["independent"].items():
        observed = counts.get(field, Counter())
        # ⚠ 按完整合法类别补零，否则「100 条全为同一值」也会算出计数差 0
        table = {canonical_json(value): observed.get(canonical_json(value), 0) for value in legal}
        spread = max(table.values()) - min(table.values())
        group_report["independent"][field] = {"counts": table, "spread": spread}
        if spread > 1:
            gaps.append(f"{where} 的 {field} 计数差 {spread} > 1")

    for field, legal in categories["coupled"].items():
        observed = counts.get(field, Counter())
        table = dict(observed)
        uncovered = [canonical_json(v) for v in legal if canonical_json(v) not in table]
        group_report["coupled"][field] = {"counts": table, "uncovered": uncovered}

    # 连续量：从 sampling_cells 独立重算粗箱与批次覆盖
    cells: dict[str, list[int]] = {}
    for record in records:
        for name, (coarse, _fine) in record["sampling_cells"].items():
            cells.setdefault(name, []).append(int(coarse))
    for name, series in cells.items():
        per_bin = Counter(series)
        batch_cover = [len(set(series[t * COARSE_BINS : (t + 1) * COARSE_BINS])) for t in range(COARSE_BINS)]
        ok = all(per_bin.get(b, 0) == GROUP_SIZE // COARSE_BINS for b in range(COARSE_BINS)) and all(
            value == COARSE_BINS for value in batch_cover
        )
        group_report["continuous"][name] = {
            "per_bin": {str(b): per_bin.get(b, 0) for b in range(COARSE_BINS)},
            "batch_coverage": batch_cover,
            "ok": ok,
        }
        if not ok:
            gaps.append(f"{where} 的连续量 {name} 分箱或批次覆盖不达标")
    return group_report


def _check_static_geometry(
    documents: dict[tuple[str, str], dict[str, Any]], sampling: dict[str, Any], verdicts: Verdicts
) -> None:
    """逐条检查难度、索引、取值范围、避让、路线合法性与动作长度。"""
    problems: list[str] = []
    checked = 0
    for (task, difficulty), doc in documents.items():
        parameters = sampling["parameters"][task]
        positions = sampling["positions"][task]
        config = parameters["configs"][difficulty]
        for record in doc["episodes"]:
            checked += 1
            tag = f"{task}/{difficulty}/ep{record['episode']}"
            problems.extend(_static_problems(task, difficulty, tag, record, config, parameters, positions))
    verdicts.add("STATIC_GEOMETRY", not problems, checked=checked, rejected=len(problems))
    if problems:
        verdicts.records[-1]["detail"] = problems[:10]


def _in_range(value: float, lo: float, hi: float, tol: float = 1e-9) -> bool:
    return math.isfinite(value) and lo - tol <= value <= hi + tol


def _static_problems(
    task: str,
    difficulty: str,
    tag: str,
    record: dict[str, Any],
    config: dict[str, Any],
    parameters: dict[str, Any],
    positions: dict[str, Any],
) -> list[str]:
    problems: list[str] = []
    layout = record["layout"]
    objects = record["objects"]
    actions = record["actions"]

    if task == "BinFill":
        button = positions["button"]
        bx, by = (float(v) for v in button["center_xy"])
        rx, ry = (float(v) for v in button["randomize_range"])
        if not (_in_range(layout["button_xy"][0], bx - rx / 2, bx + rx / 2) and _in_range(layout["button_xy"][1], by - ry / 2, by + ry / 2)):
            problems.append(f"{tag}: 按钮越界")
        board = positions["board"]
        base_x = float(board["base_position"][0])
        if not _in_range(layout["board"]["xy"][0], base_x - board["x_offset"]["subtract"], base_x - board["x_offset"]["subtract"] + board["x_offset"]["scale"]):
            problems.append(f"{tag}: 孔板 x 越界")
        if not _in_range(layout["board"]["xy"][1], -board["y_offset"]["subtract"], -board["y_offset"]["subtract"] + board["y_offset"]["scale"]):
            problems.append(f"{tag}: 孔板 y 越界")
        if not _in_range(layout["board"]["yaw_deg"], -board["yaw_deg"]["subtract"], -board["yaw_deg"]["subtract"] + board["yaw_deg"]["scale"]):
            problems.append(f"{tag}: 孔板朝向越界")

        cubes_cfg = positions["cubes"]
        center = [float(v) for v in cubes_cfg["region_center"]]
        half = [float(v) for v in cubes_cfg["region_half_size"]]
        obstacles = [
            button_obb(layout["button_xy"], float(button["scale"])),
            *board_obbs(layout["board"]["xy"], float(board["board_side"]), float(board["hole_side"])),
        ]
        placed: list[Any] = []
        for cube in layout["cubes"]:
            if not (
                _in_range(cube["xy"][0], center[0] - half[0] + CUBE_HALF_SIZE, center[0] + half[0] - CUBE_HALF_SIZE)
                and _in_range(cube["xy"][1], center[1] - half[1] + CUBE_HALF_SIZE, center[1] + half[1] - CUBE_HALF_SIZE)
            ):
                problems.append(f"{tag}: 方块 {cube['object_id']} 越界")
            if not _in_range(cube["yaw_rad"], 0.0, 2 * math.pi):
                problems.append(f"{tag}: 方块 {cube['object_id']} 朝向越界")
            candidate = cube_obb(cube["xy"][0], cube["xy"][1], CUBE_HALF_SIZE, cube["yaw_rad"], pad=CUBE_HALF_SIZE)
            if any(obb2d_intersect(*item, *candidate) for item in obstacles + placed):
                problems.append(f"{tag}: 方块 {cube['object_id']} 未满足 min_gap 或压在按钮／孔板上")
            placed.append(cube_obb(cube["xy"][0], cube["xy"][1], CUBE_HALF_SIZE, cube["yaw_rad"]))

        # 数量与动作
        if len(layout["cubes"]) != sum(objects["spawn_count"].values()):
            problems.append(f"{tag}: 方块数与 spawn_count 不符")
        if len(actions) != sum(objects["target_count"].values()):
            problems.append(f"{tag}: 动作数与 target_count 不符")
        colors = objects["colors_present"]
        if len(colors) != int(config["color"]):
            problems.append(f"{tag}: 场上颜色数与难度不符")
        for color, count in objects["spawn_count"].items():
            if count < objects["target_count"].get(color, 0):
                problems.append(f"{tag}: {color} 的生成数少于目标数")
        # B7：每种目标颜色抓的必须是该色生成列表最前面的几块
        by_color: dict[str, list[str]] = {}
        for cube in layout["cubes"]:
            by_color.setdefault(cube["color"], []).append(cube["object_id"])
        taken: dict[str, int] = {}
        for action in actions:
            object_id = action["pick"]
            color = next((c["color"] for c in layout["cubes"] if c["object_id"] == object_id), None)
            if color is None:
                problems.append(f"{tag}: 动作引用了不存在的方块 {object_id}")
                continue
            index = taken.get(color, 0)
            if by_color[color][index] != object_id:
                problems.append(f"{tag}: {color} 的第 {index} 次抓取不是生成列表最前面的一块")
            taken[color] = index + 1
        return problems

    if task == "RouteStick":
        walk = parameters["walk"]
        nodes = actions["nodes"]
        slots = actions["node_slots"]
        length_lo, length_hi = (int(v) for v in config["length"])
        if not length_lo <= objects["L"] <= length_hi:
            problems.append(f"{tag}: 段数越界")
        if len(nodes) != objects["L"] + 1 or len(actions["directions"]) != objects["L"]:
            problems.append(f"{tag}: 节点数或方向数与段数不符")
        node_indices = [int(v) for v in walk["node_indices"]]
        if any(node not in node_indices for node in nodes):
            problems.append(f"{tag}: 路线经过了非按钮节点")
        for i in range(len(slots) - 1):
            if abs(slots[i + 1] - slots[i]) != 1:
                problems.append(f"{tag}: 第 {i} 段不是相邻按钮")
            if not config["backtrack"] and i > 0 and slots[i + 1] == slots[i - 1]:
                # 不允许回退的难度里只有走到两端才可以被迫掉头
                if 0 < slots[i] < len(node_indices) - 1:
                    problems.append(f"{tag}: 第 {i} 段在非端点主动回退")
        if any(d not in (walk["direction"]["less_than"], walk["direction"]["otherwise"]) for d in actions["directions"]):
            problems.append(f"{tag}: 出现非法绕行方向")
        yaw = positions["yaw_deg"]
        if not _in_range(layout["rotation_deg"], -yaw["subtract"], -yaw["subtract"] + yaw["scale"]):
            problems.append(f"{tag}: 整排旋转角越界")
        if len(layout["obstacle_rgb"]) != int(positions["obstacle_color"]["count"]):
            problems.append(f"{tag}: 障碍柱颜色数不符")
        return problems

    if task in ("VideoUnmaskSwap", "VideoRepick"):
        is_unmask = task == "VideoUnmaskSwap"
        block = positions["containers"] if is_unmask else positions["easy_medium_cubes"]
        theta_lo, theta_hi = (float(v) for v in block["layout_rotation_range_rad"])
        if not _in_range(layout["theta_rad"], theta_lo, theta_hi):
            problems.append(f"{tag}: 整组旋转越界")
        region_half = float(block["region_half_size"])
        limit = region_half - ((CUBE_HALF_SIZE * 2.5 + 0.005) * 0.5 if is_unmask else CUBE_HALF_SIZE)
        anchors = rotate_xy([list(p) for p in block[layout["type"]]], layout["theta_rad"])
        items = layout["bins"] if is_unmask else layout["cubes"]
        if len(items) != len(anchors):
            problems.append(f"{tag}: 对象数与锚点数不符")
        for index, item in enumerate(items):
            dx = item["xy"][0] - anchors[index][0]
            dy = item["xy"][1] - anchors[index][1]
            if not (_in_range(dx, -limit, limit) and _in_range(dy, -limit, limit)):
                problems.append(f"{tag}: {item['object_id']} 的偏移超出上限 {limit}")
            if is_unmask and not _in_range(item["yaw_deg"], 0.0, float(block["yaw_scale_deg"])):
                problems.append(f"{tag}: {item['object_id']} 的朝向越界")
            if not is_unmask and not _in_range(item["yaw_rad"], 0.0, 2 * math.pi):
                problems.append(f"{tag}: {item['object_id']} 的朝向越界")
        swaps = actions["swap_pairs"]
        if len(swaps) != objects["n_swaps"]:
            problems.append(f"{tag}: 交换次数与 n_swaps 不符")
        for item in swaps:
            if item["initiator"] == item["partner"]:
                problems.append(f"{tag}: 交换发起者与搭档相同")
        # 第 k 段发起者 = 循环基 swap_initiators[k mod 3]（xhard 4～5 次时循环沿用；≤3 次时与逐个取用等价）
        initiators = objects["swap_initiators"]
        for index, item in enumerate(swaps):
            if not initiators or item["initiator"] != initiators[index % len(initiators)]:
                problems.append(f"{tag}: 第 {index} 段发起者不是 swap_initiators[{index} mod {len(initiators)}]")
        if is_unmask:
            if len(objects["selected"]) != 3 or len(set(objects["selected"])) != 3:
                problems.append(f"{tag}: 藏物排序不是 3 个互异容器")
            if len(objects["pick_order"]) != objects["n_picks"]:
                problems.append(f"{tag}: 抓取个数与 n_picks 不符")
            if sorted(objects["hidden"]) != sorted(["red", "green", "blue"]):
                problems.append(f"{tag}: 藏物颜色不是红绿蓝三色")
            if len(objects["empty"]) != objects["n_bins"] - 3:
                problems.append(f"{tag}: 空容器数不符")
        else:
            if swaps and swaps[0]["initiator"] != objects["target"]:
                problems.append(f"{tag}: 首次交换不是由目标方块发起")
            if objects["target"] not in {item["object_id"] for item in items}:
                problems.append(f"{tag}: 目标方块不在场上")
            button = positions["button"]
            bx, by = (float(v) for v in button["center_xy"])
            rx, ry = (float(v) for v in button["randomize_range"])
            if not (_in_range(layout["button_xy"][0], bx - rx / 2, bx + rx / 2) and _in_range(layout["button_xy"][1], by - ry / 2, by + ry / 2)):
                problems.append(f"{tag}: 按钮越界")
        return problems

    problems.append(f"{tag}: 未知任务")
    return problems


def _check_collision(documents: dict[tuple[str, str], dict[str, Any]], verdicts: Verdicts) -> None:
    """几何描述对齐第 8.1 节，并对 500 条视频规格重跑初态与全部预定交换的连续检查。"""
    expected = [
        ([0.0, 0.0, 0.0], [0.02, 0.02, 0.02]),
        ([0.0, 0.0, 0.002], [0.0275, 0.0275, 0.002]),
        ([-0.0275, 0.0, 0.027], [0.0025, 0.0275, 0.025]),
        ([0.0275, 0.0, 0.027], [0.0025, 0.0275, 0.025]),
        ([0.0, -0.0275, 0.027], [0.0275, 0.0025, 0.025]),
        ([0.0, 0.0275, 0.027], [0.0275, 0.0025, 0.025]),
    ]
    shapes = bc.bin_shape_specs(CUBE_HALF_SIZE)
    geometry_ok = len(shapes) == len(expected) and len(bc.cube_shape_specs(CUBE_HALF_SIZE)) == 1
    for shape, (p, half) in zip(shapes, expected):
        geometry_ok = geometry_ok and all(abs(a - b) < 1e-12 for a, b in zip(shape.local_p, p))
        geometry_ok = geometry_ok and all(abs(a - b) < 1e-12 for a, b in zip(shape.half, half))
    verdicts.add(
        "COLLISION_GEOMETRY",
        geometry_ok,
        bin_shapes=len(shapes),
        cube_shapes=1,
        four_object_pairs=6,
        note="真实-actor-对照在步骤2冒烟",
    )

    specs = 0
    rejected = 0
    uncertified = 0
    worst = math.inf
    details: list[str] = []
    for (task, difficulty), doc in documents.items():
        if task not in ("VideoUnmaskSwap", "VideoRepick"):
            continue
        for record in doc["episodes"]:
            specs += 1
            states = _states_of(task, record)
            gap, rejection = bc.check_bin_layout(list(states.values()), stage="initial")
            if rejection is not None:
                rejected += 1
                uncertified += rejection.reason == "uncertified"
                details.append(f"{task}/{difficulty}/ep{record['episode']} 初态 {rejection.summary()}")
                continue
            worst = min(worst, gap)
            current = dict(states)
            for index, pair in enumerate(record["actions"]["swap_pairs"]):
                a = int(pair["initiator"].rsplit("_", 1)[1])
                b = int(pair["partner"].rsplit("_", 1)[1])
                bystanders = [state for key, state in sorted(current.items()) if key not in (a, b)]
                gap, rejection = bc.check_swap_sweep(current[a], current[b], bystanders, sweep_index=index)
                if rejection is not None:
                    rejected += 1
                    uncertified += rejection.reason == "uncertified"
                    details.append(f"{task}/{difficulty}/ep{record['episode']} 第 {index} 段 {rejection.summary()}")
                    break
                worst = min(worst, gap)
                sa, sb = current[a], current[b]
                current[a] = bc.ObjectState(sa.name, [sb.p[0], sb.p[1], sa.p[2]], sb.q, sa.shapes)
                current[b] = bc.ObjectState(sb.name, [sa.p[0], sa.p[1], sb.p[2]], sa.q, sb.shapes)
    verdicts.add(
        "COLLISION_SWEEP",
        rejected == 0,
        specs=specs,
        rejected=rejected,
        uncertified=uncertified,
        min_g_m=round(worst, 9) if math.isfinite(worst) else None,
    )
    if details:
        verdicts.records[-1]["detail"] = details[:10]


def _states_of(task: str, record: dict[str, Any]) -> dict[int, bc.ObjectState]:
    states: dict[int, bc.ObjectState] = {}
    if task == "VideoUnmaskSwap":
        for index, item in enumerate(record["layout"]["bins"]):
            p, q = bc.bin_actor_pose(item["xy"], item["yaw_deg"], CUBE_HALF_SIZE)
            states[index] = bc.ObjectState(item["object_id"], p, q, bc.bin_shape_specs(CUBE_HALF_SIZE))
    else:
        for index, item in enumerate(record["layout"]["cubes"]):
            p, q = bc.cube_actor_pose(item["xy"], item["yaw_rad"], CUBE_HALF_SIZE)
            states[index] = bc.ObjectState(item["object_id"], p, q, bc.cube_shape_specs(CUBE_HALF_SIZE))
    return states


def cmd_check(run_id: str, sampling_config: Path, contract_override: Path | None = None) -> dict[str, Any]:
    root, manifest, documents = load_group_documents(run_id)
    sampling = json.loads(sampling_config.read_text(encoding="utf-8"))
    contract = resolve_contract(manifest, contract_override)
    frozen = manifest.get("sampling_operands_sha256") or manifest.get("sampling_config_sha256")
    # 只算清单里各组消费到的难度档：源码后来加了别的档（如 xhard）不会把旧冻结判成依据漂移
    current_sha = operand_sha256(sampling, {item["difficulty"] for item in manifest["groups"]})
    if current_sha != frozen:
        raise CampaignError(
            "原值取值域（parameters / positions）的散列与冻结时不符，拒绝在漂移的依据上验收；"
            f"当前 {current_sha[:12]}…，冻结时 {str(frozen)[:12]}…"
        )
    current_file_sha = _sha256_file(sampling_config)
    if manifest.get("sampling_config_file_sha256") not in (None, current_file_sha):
        # 文件动过但取值域没动：正常情况是接入新值后刷新了 sources.sha256，如实报告不拦
        print(
            f"  注意：{sampling_config.name} 文件散列已变（多半是刷新了源码指纹），"
            "但 parameters / positions 未变，继续验收"
        )

    verdicts = Verdicts(echo=True)
    started = time.monotonic()
    _check_scope(documents, verdicts)
    _check_contract_derived(contract, sampling, verdicts)
    quota_report = _check_quota(documents, contract, verdicts)
    _check_static_geometry(documents, sampling, verdicts)
    _check_collision(documents, verdicts)
    _check_reproducible(documents, sampling, contract, manifest["generator_seed"], verdicts)

    payload = {
        "run_id": run_id,
        "elapsed_s": round(time.monotonic() - started, 1),
        "verdicts": verdicts.records,
        "quota_report": quota_report,
        "passed": verdicts.passed,
    }
    _write_json(root / "check_result.json", payload)
    print(f"CHECK={'PASS' if verdicts.passed else 'FAIL'} elapsed_s={payload['elapsed_s']}")
    return payload


# ── compare：两个运行目录的 HDF5 逐位对拍 ───────────────────────────────────
def _index_h5(root: Path) -> dict[tuple[str, str, int], Path]:
    """按 ``(任务, 难度, episode)`` 索引一个运行目录下的全部 HDF5。

    清单模式下每组落在 ``<根>/<任务>/<难度>/hdf5_files/`` 里，单组模式落在
    ``<根>/hdf5_files/``，所以递归找、从相对路径推难度，不假设固定层级。

    ⚠ key 必须带难度。同一任务不同难度的 HDF5 **文件名完全相同**（`<任务>_ep<k>_seed<s>`，
    seed 只由任务与 episode 决定），只靠 `(任务, episode)` 会让 easy/medium/hard 互相覆盖，
    比较时凭空少掉三分之二的样本还看不出来。
    """
    index: dict[tuple[str, str, int], Path] = {}
    for path in sorted(root.rglob("hdf5_files/*.h5")):
        name = path.stem  # <任务>_ep<k>_seed<s>
        try:
            task, rest = name.split("_ep", 1)
            episode = int(rest.split("_seed", 1)[0])
        except (ValueError, IndexError):
            continue
        parts = path.relative_to(root).parts  # <任务>/<难度>/hdf5_files/<名>.h5 或 hdf5_files/<名>.h5
        difficulty = parts[-3] if len(parts) >= 3 else ""
        index[(task, difficulty, episode)] = path
    return index


def _select_groups(groups: Sequence[tuple[str, str]], groups_filter: Sequence[str] | None) -> list[tuple[str, str]]:
    """按 ``--groups``（``任务/难度`` 列表）从清单组里选子集，保持清单顺序；未知键直接拒绝，不静默忽略。"""
    if not groups_filter:
        return list(groups)
    wanted = [tuple(key.split("/", 1)) for key in groups_filter]
    unknown = [key for key in wanted if key not in groups]
    if unknown:
        raise CampaignError(f"--groups 里有清单没有的组：{['/'.join(k) for k in unknown]}；清单组：{['/'.join(g) for g in groups]}")
    return [group for group in groups if group in wanted]


def cmd_specs_diff(
    left_run: str, right_run: str, label: str = "OLD_GROUPS_EQUIVALENCE", episode_scope: str = "union"
) -> dict[str, Any]:
    """两次冻结运行里**共有的组**逐条比 ``spec_sha256``（xhard 扩展：06 的旧 11 组必须与 05 逐条相同）。

    只比两边都有的组；一边独有的组只报告、不判失败。判定行 ``<label>=PASS compared=<n> differences=<n> shared_groups=<n>``。

    ``episode_scope``（2026-09-12 多 block 扩容引入）：
    * ``union``（默认，历史语义不变）：比两边 episode 号的并集，一边独有的号算差异；
    * ``intersection``：只比两边都有的号；
    * ``block0``：只比 ``episode < 100``，且**要求两边在每个共有组上都完整覆盖 range(100)**，缺号即差异——
      用来证明扩容后的 block 0 与 07/09 逐条相同（``BLOCK0_EQUIVALENCE``），不会因为缺条而假 PASS。
    """
    if episode_scope not in ("union", "intersection", "block0"):
        raise CampaignError(f"--episode-scope 只能是 union / intersection / block0：{episode_scope}")
    _, _, left_docs = load_group_documents(left_run)
    _, _, right_docs = load_group_documents(right_run)
    shared = [key for key in left_docs if key in right_docs]
    compared = differences = 0
    left_only_eps = right_only_eps = 0
    diff_samples: list[str] = []
    for task, difficulty in shared:
        left_eps = {item["episode"]: item["spec_sha256"] for item in left_docs[(task, difficulty)]["episodes"]}
        right_eps = {item["episode"]: item["spec_sha256"] for item in right_docs[(task, difficulty)]["episodes"]}
        if episode_scope == "union":
            scope = sorted(set(left_eps) | set(right_eps))
        elif episode_scope == "intersection":
            scope = sorted(set(left_eps) & set(right_eps))
        else:
            scope = list(range(GROUP_SIZE))
        left_only_eps += len(set(left_eps) - set(right_eps))
        right_only_eps += len(set(right_eps) - set(left_eps))
        for episode in scope:
            compared += 1
            if left_eps.get(episode) != right_eps.get(episode):
                differences += 1
                if len(diff_samples) < 10:
                    diff_samples.append(f"{task}/{difficulty}/ep{episode}")
    payload = {
        "left": left_run, "right": right_run, "shared_groups": ["/".join(k) for k in shared],
        "left_only": ["/".join(k) for k in left_docs if k not in right_docs],
        "right_only": ["/".join(k) for k in right_docs if k not in left_docs],
        "episode_scope": episode_scope, "left_only_episodes": left_only_eps, "right_only_episodes": right_only_eps,
        "compared": compared, "differences": differences, "samples": diff_samples,
        "passed": differences == 0 and compared > 0,
    }
    scope_text = "" if episode_scope == "union" else f" scope={episode_scope}"
    print(f"{label}={'PASS' if payload['passed'] else 'FAIL'} compared={compared} differences={differences} shared_groups={len(shared)}{scope_text} "
          f"right_only={','.join(payload['right_only']) or '-'}")
    return payload


def cmd_compare(left_dir: Path, right_dir: Path, label: str, *, subset_only: bool = False) -> dict[str, Any]:
    """逐位比较两个运行目录里同名 episode 的完整 HDF5。

    复用 ``scripts/injection/h5_compare.py::compare_h5``——它显式遍历全部
    group、dataset 及各层 attribute，检查类型、形状与内容。保持这个全集覆盖，
    不能只挑动作字段比较。

    只在一侧出现的 episode 单列为 ``only_left``／``only_right``，默认**不算通过**：
    少产物和内容不一致是两种不同的失败，不能互相掩盖。

    ``subset_only=True`` 时只判交集——负载阶梯拿 120 条清单里的那 16 条固定样本去比
    16 条的串行参考，另外 104 条本来就只在一侧，不该因此判失败。⚠ 这个开关只放宽
    「一侧多出」，交集内的任何差异照样是 FAIL，两侧交集为空也是 FAIL。
    """
    from .h5_compare import compare_h5

    left = _index_h5(left_dir)
    right = _index_h5(right_dir)
    shared = sorted(set(left) & set(right))
    only_left = sorted(set(left) - set(right))
    only_right = sorted(set(right) - set(left))

    differences: list[dict[str, Any]] = []
    for key in shared:
        detail = compare_h5(left[key], right[key])
        if detail:
            differences.append(
                {"task": key[0], "difficulty": key[1], "episode": key[2],
                 "differences": detail[:20], "count": len(detail)}
            )

    passed = not differences and bool(shared)
    if not subset_only:
        passed = passed and not only_left and not only_right
    payload = {
        "label": label,
        "left": str(left_dir),
        "right": str(right_dir),
        "compared": len(shared),
        "only_left": [f"{task}/{difficulty}/ep{episode}" for task, difficulty, episode in only_left],
        "only_right": [f"{task}/{difficulty}/ep{episode}" for task, difficulty, episode in only_right],
        "difference_episodes": differences,
        "subset_only": subset_only,
        "passed": passed,
    }
    print(
        f"{label}={'PASS' if passed else 'FAIL'} compared={len(shared)} "
        f"differences={len(differences)} only_left={len(only_left)} only_right={len(only_right)}"
        + (" subset_only=1" if subset_only else "")
    )
    for item in differences[:5]:
        print(f"  {item['task']}/{item['difficulty']}/ep{item['episode']}: {item['count']} 处差异，首条 {item['differences'][0]}")
    return payload


# ── run：步骤 3～5 的执行编排 ───────────────────────────────────────────────
def cmd_run(
    run_id: str,
    phase: str,
    sampling_config: Path,
    tiers: Sequence[int] | None = None,
    *,
    skip_ladder: bool = False,
    tier_override: int | None = None,
    gpus: str = "0",
    groups_filter: Sequence[str] | None = None,
    episodes_per_group: int | None = None,
    delivery_config: Path | None = None,
    episode_range: tuple[int, int] | None = None,
    skip_done: bool = False,
    wall_limit_h: float = 6.0,
    label: str | None = None,
) -> dict[str, Any]:
    """按阶段跑：``calibration``（步骤 3+4）或 ``feasibility``（步骤 5）。

    2026-09-12 每 env 400 条交付新增（都只对 ``feasibility`` 生效）：
    * ``delivery_config``：每组实跑 ``range(run_episodes)``（各组条数不同），与 ``--episodes`` 互斥；
    * ``episode_range=(a, b)``：每组只跑 episode ``a～b-1``（缺口补跑用），与上两者互斥；
    * ``skip_done``：从既有 ``episode_results.jsonl`` 里剔除已「通过」的 (任务, 难度, episode)，中断后同命令续跑；
    * ``wall_limit_h``：整批墙钟上限（小时），默认 6 与 07 相同；
    * ``label``：清单文件名后缀 ``manifests/feasibility_<label>_<n>.json``，不给时沿用 ``feasibility<n>.json``。
    日志改落 ``<运行根>/logs/``（被 git 跟踪），不再落 ``artifacts/logs/``。

    ``episodes_per_group``（2026-09-12 引入，08 RouteStick 四档各 5 条专项重出）只对 ``feasibility``
    生效：每组实跑 episode ``0～N-1``；默认 ``None`` 沿用 ``FEASIBILITY_EPISODES``（30 条，07 及之前逐字不变）。

    ``groups_filter``（2026-09-11 加 xhard 时引入）只对 ``feasibility`` 生效：逗号分隔的 ``任务/难度``，
    只跑清单里这些组；默认 ``None`` 跑清单全部组（05 及之前的行为逐字不变）。未知键直接拒绝。

    ``gpus`` 只对 ``feasibility`` + ``--tier`` 生效：逗号分隔的物理卡号，每卡 worker 数由 ``tier`` 给，
    传给生成器的 ``--workers`` 是总数 ``tier × 卡数``（生成器按 ``workers // len(gpus)`` 摊到每卡）。
    默认 ``"0"`` 与 04 之前的单卡行为逐字相同；校准阶段不受此参数影响。

    每一步都复用生产入口 ``scripts/generate_dataset_newseed.py``，命令、退出码、墙钟与
    资源采样全部留档；本函数只做编排与判定，不自己建仿真。
    """
    from .run import (
        CALIBRATION_GROUPS,
        FEASIBILITY_EPISODES,
        LOAD_EPISODES,
        OUTCOME_PASS,
        SERIAL_EPISODES,
        WORKER_TIERS,
        invoke_generator,
        overlap_report,
        solve_windows,
        tier_is_unusable,
        tier_throughput,
        write_manifest,
    )

    root, manifest_doc, documents = load_group_documents(run_id)
    specs_root = root / "specs"
    logs = root / "logs"
    verdicts = Verdicts()
    payload: dict[str, Any] = {"run_id": run_id, "phase": phase, "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}

    if phase == "calibration":
        # ── 步骤 3：16 条固定样本单卡单 worker 跑两遍，建立「标准答案」──────────
        serial_manifest = write_manifest(
            root / "manifests" / "serial16.json", CALIBRATION_GROUPS, SERIAL_EPISODES, specs_root,
            "步骤 3 串行参考：四个校准组各 episode 0～3，共 16 条固定样本",
        )
        runs: dict[str, dict[str, Any]] = {}
        for label in ("S0a", "S0b"):
            print(f"[串行参考] {label} 开跑（GPU 0，单 worker，16 条）", flush=True)
            runs[label] = invoke_generator(
                output_dir=root / "calibration" / label, manifest=serial_manifest,
                gpus="0", workers=1, log_path=logs / f"{label}.log", sampling_config=sampling_config,
            )
            print(f"[串行参考] {label} 完成，墙钟 {runs[label]['wall_s']} 秒，退出码 {runs[label]['exit_code']}", flush=True)

        serial = cmd_compare(root / "calibration" / "S0a", root / "calibration" / "S0b", "SERIAL_REFERENCE")
        # 两遍同失败的条从可比数里扣除：重复失败不构成成功参考
        failed_a = {(row["task"], row["difficulty"], row["episode"]) for row in runs["S0a"]["rows"] if row["outcome"] != OUTCOME_PASS}
        failed_b = {(row["task"], row["difficulty"], row["episode"]) for row in runs["S0b"]["rows"] if row["outcome"] != OUTCOME_PASS}
        both_failed = sorted(failed_a & failed_b)
        verdicts.add(
            "SERIAL_REFERENCE", serial["passed"], unique=len(SERIAL_EPISODES) * len(CALIBRATION_GROUPS),
            comparable=serial["compared"], both_failed=len(both_failed), differences=len(serial["difference_episodes"]),
        )
        payload["serial"] = {
            "runs": {label: {k: v for k, v in item.items() if k != "rows"} for label, item in runs.items()},
            "compare": serial,
            "both_failed": [f"{task}/{difficulty}/ep{episode}" for task, difficulty, episode in both_failed],
            "rows": {label: item["rows"] for label, item in runs.items()},
        }
        if not serial["passed"]:
            print("SERIAL_REFERENCE 未通过：两遍不一致，按计划停止，不进档位阶梯", flush=True)
            payload["verdicts"] = verdicts.records
            _write_json(root / "calibration_result.json", payload)
            for line in verdicts.lines:
                print(line)
            return payload

        if skip_ladder:
            # 步骤 4 被显式跳过（2026-09-10 用户决定：机器被另一个用户占了 639% CPU 与
            # GPU 1 的 33.7 GB，单条从 98.6 秒慢到 316 秒，吞吐测量会严重失真）。
            # ⚠ 并行三项如实记 NOT_RUN，**不假装测过吞吐**，也不拿一个没测过的档冒充选出的档。
            reason = (
                "按用户决定跳过档位校准：机器被另一用户重度占用（GPU1 33.7 GB、639% CPU、"
                "load 15），单条 BinFill hard 实测 316.31 秒 / RouteStick hard 167.27 秒，"
                "分别是空闲时 98.6 / 47.0 秒的 3.2 / 3.6 倍，吞吐测量失真"
            )
            for name in ("PARALLEL_CONTENT", "PARALLEL_OVERLAP", "PARALLEL_SCALE"):
                verdicts.add(name, None, reason="档位校准被跳过")
            payload.update({"ladder": [], "chosen": None, "max_stable": None, "stopped_at": None,
                            "skip_ladder": True, "skip_reason": reason})
            print(reason, flush=True)
            payload["verdicts"] = verdicts.records
            payload["passed"] = verdicts.passed
            _write_json(root / f"{phase}_result.json", payload)
            for line in verdicts.lines:
                print(line)
            print(f"RUN={'PASS' if verdicts.passed else 'FAIL'} phase={phase}（并行三项 NOT_RUN）")
            return payload

        # ── 步骤 4：120 条清单，每卡 worker 数一路往上探到 OOM／超时为止 ────────
        load_manifest = write_manifest(
            root / "manifests" / "load120.json", CALIBRATION_GROUPS, LOAD_EPISODES, specs_root,
            "步骤 4 负载阶梯：四个校准组各 episode 0～29，共 120 条，每档同一份清单",
        )
        # ⚠ 本轮档位阶梯在**单 GPU（GPU 0）**上测（2026-09-10 用户决定：
        # 「改为在gpu0上测速 单gpu 的worker数量不变」）。原因是 GPU 1 被另一个用户的进程
        # 占了 33.7 GB，双卡高档位跑不起来。每卡 worker 的阶梯刻度保持不变，
        # 只是不再乘 2、不再开第二张卡；因此 PARALLEL_* 的结论只覆盖单卡多 worker，
        # 双卡逐位一致本轮没有取得新值证据，报告里单列。
        gpu_ids = ["0"]
        ladder: list[dict[str, Any]] = []
        stopped_at: dict[str, Any] | None = None
        for tier in (tiers or WORKER_TIERS):
            mode = f"P0x{tier}"
            print(f"[档位阶梯] GPU 0 单卡 {tier} worker（--gpus 0 --workers {tier}）开跑，120 条", flush=True)
            result = invoke_generator(
                output_dir=root / "calibration" / mode, manifest=load_manifest,
                gpus=",".join(gpu_ids), workers=tier, log_path=logs / f"{mode}.log", sampling_config=sampling_config,
            )
            unusable, reason = tier_is_unusable(result)
            throughput, delivered, failed = tier_throughput(result)
            overlap = overlap_report(solve_windows(root / "calibration" / mode), gpu_ids, tier)
            content = cmd_compare(
                root / "calibration" / "S0a", root / "calibration" / mode,
                f"PARALLEL_CONTENT@{mode}", subset_only=True,
            )
            entry = {
                "tier": tier, "mode": mode, "gpus": list(gpu_ids), "workers": tier,
                "unusable": unusable, "reason": reason,
                "wall_s": result["wall_s"], "exit_code": result["exit_code"], "timed_out": result["timed_out"],
                "delivered": delivered, "failed": failed, "delivered_per_min": round(throughput, 3),
                "overlap": overlap, "content": content,
                "resources_before": result["resources_before"], "resources_after": result["resources_after"],
                "peak_rss_mb": max((row["peak_rss_mb"] or 0 for row in result["rows"]), default=0),
                "command": result["command"], "log": result["log"],
            }
            ladder.append(entry)
            print(
                f"[档位阶梯] {mode}：{'不可用（' + reason + '）' if unusable else '可用'}，"
                f"交付 {delivered} 条 / 失败 {failed} 条 / 墙钟 {result['wall_s']} 秒 / "
                f"吞吐 {throughput:.3f} 条每分钟 / 峰值 RSS {entry['peak_rss_mb']:.0f} MB",
                flush=True,
            )
            if unusable:
                # 实测到 OOM／池崩溃／超时：不再往上探，用最后一个可用档
                stopped_at = entry
                break

        usable = [item for item in ladder if not item["unusable"] and item["content"]["passed"] and item["overlap"]["passed"]]
        chosen = max(usable, key=lambda item: item["delivered_per_min"]) if usable else None
        max_stable = max((item["tier"] for item in ladder if not item["unusable"]), default=None)

        content_ok = bool(ladder) and all(item["content"]["passed"] for item in ladder if not item["unusable"])
        overlap_ok = bool(ladder) and all(item["overlap"]["passed"] for item in ladder if not item["unusable"])
        verdicts.add(
            "PARALLEL_CONTENT", content_ok, unique=16, configs=len([i for i in ladder if not i["unusable"]]),
            differences=sum(len(item["content"]["difference_episodes"]) for item in ladder),
        )
        for item in ladder:
            if item["unusable"]:
                continue
            verdicts.add(
                "PARALLEL_OVERLAP", item["overlap"]["passed"], mode=item["mode"], gpus=len(gpu_ids),
                workers_per_gpu=item["tier"], peak_distinct_pids=item["overlap"]["peak_distinct_pids"],
                both_busy_s=item["overlap"]["both_busy_seconds"],
            )
        verdicts.add(
            "PARALLEL_SCALE", chosen is not None,
            chosen=chosen["mode"] if chosen else "none",
            workers_per_gpu=chosen["tier"] if chosen else 0,
            delivered_per_min=chosen["delivered_per_min"] if chosen else 0,
            failed=chosen["failed"] if chosen else 0,
            peak_rss_gb=round((chosen["peak_rss_mb"] if chosen else 0) / 1024, 1),
            max_stable=f"P0x{max_stable}" if max_stable else "none",
            highest_failed=stopped_at["mode"] if stopped_at else "none",
        )
        payload.update({"ladder": ladder, "chosen": chosen, "max_stable": max_stable, "stopped_at": stopped_at})
        payload["gpu_note"] = (
            "本轮档位阶梯在 GPU 0 单卡上测；GPU 1 被另一个用户的进程占用 33.7 GB，"
            "双卡对拍未做，PARALLEL_* 的结论只覆盖单卡多 worker"
        )
        if chosen is None:
            print("没有任何合格的档：按计划停止并报告，不放宽判据、不换规格", flush=True)

    elif phase == "feasibility":
        calibration = root / "calibration_result.json"
        if not calibration.is_file() and tier_override is None:
            raise CampaignError(f"实跑前必须先跑校准：缺 {calibration}（或显式传 --tier）")
        chosen = (
            json.loads(calibration.read_text(encoding="utf-8")).get("chosen")
            if calibration.is_file()
            else None
        )
        if not chosen and tier_override is None:
            raise CampaignError(
                "校准没有选出合格的档，拒绝启动实跑；确要在未校准的情况下实跑，"
                "请显式传 --tier <每卡 worker 数>（PARALLEL_SCALE 会保持 NOT_RUN）"
            )
        if tier_override is not None:
            # 显式指定档位：档位不是测出来的，报告里必须写明这一点。
            # 2026-09-11 用户要求「2gpu并行跑 每个gpu并行worker数量20」：卡号改由 --gpus 给，
            # 档名 P<卡号串>x<每卡 worker>（单卡仍是 P0x12 这种老名字，双卡如 P01x20）。
            tier = int(tier_override)
            gpu_ids = [item.strip() for item in gpus.split(",") if item.strip()]
            if not gpu_ids or len(gpu_ids) != len(set(gpu_ids)):
                raise CampaignError(f"--gpus 非法：{gpus!r}（须是逗号分隔、不重复的物理卡号）")
            chosen = {"tier": tier, "mode": f"P{''.join(gpu_ids)}x{tier}", "gpus": gpu_ids, "measured": False}
        else:
            tier = int(chosen["tier"])
            gpu_ids = chosen.get("gpus") or ["0"]
        groups = _select_groups([(item["task"], item["difficulty"]) for item in manifest_doc["groups"]], groups_filter)
        available = {(item["task"], item["difficulty"]): int(item.get("episodes", GROUP_SIZE)) for item in manifest_doc["groups"]}
        if sum(x is not None for x in (episodes_per_group, delivery_config, episode_range)) > 1:
            raise CampaignError("--episodes、--delivery-config、--episode-range 三者互斥，只能给一个")
        episodes_by_group: dict[tuple[str, str], list[int]]
        if delivery_config is not None:
            try:
                delivery = load_delivery_config(delivery_config, resolve_contract(manifest_doc))
            except DeliveryError as exc:
                raise CampaignError(f"交付配置不合法：{exc}") from exc
            if manifest_doc.get("delivery_config_sha256") not in (None, delivery.sha256):
                raise CampaignError("交付配置与冻结时不符（散列不同），拒绝按漂移的口径实跑")
            episodes_by_group = delivery.episodes_by_group(groups)
            scope_note = "按交付配置各组实跑 range(run_episodes)"
        elif episode_range is not None:
            lo, hi = int(episode_range[0]), int(episode_range[1])
            if not 0 <= lo < hi:
                raise CampaignError(f"--episode-range 须满足 0 ≤ a < b：{episode_range}")
            episodes_by_group = {group: list(range(lo, hi)) for group in groups}
            scope_note = f"缺口补跑：每组 episode {lo}～{hi - 1}"
        elif episodes_per_group is not None:
            if int(episodes_per_group) < 1:
                raise CampaignError(f"--episodes 必须 ≥ 1：{episodes_per_group}")
            episodes_by_group = {group: list(range(int(episodes_per_group))) for group in groups}
            scope_note = f"每组 episode 0～{int(episodes_per_group) - 1}"
        else:
            episodes_by_group = {group: list(FEASIBILITY_EPISODES) for group in groups}
            scope_note = f"每组 episode 0～{len(FEASIBILITY_EPISODES) - 1}"
        for group, wanted in episodes_by_group.items():
            if wanted and max(wanted) >= available[group]:
                raise CampaignError(
                    f"--episodes/--episode-range 越界：{'/'.join(group)} 只冻结了 {available[group]} 条，"
                    f"实跑区间到 episode {max(wanted)}；不静默截断"
                )
        mode = chosen.get("mode") or f"P0x{tier}"
        skipped = 0
        if skip_done:
            from .run import read_result_rows

            done = {
                (row["task"], str(row["difficulty"]), int(row["episode"]))
                for row in read_result_rows(root / "feasibility" / mode)
                if row["outcome"] == OUTCOME_PASS
            }
            for group, wanted in list(episodes_by_group.items()):
                kept = [ep for ep in wanted if (group[0], group[1], ep) not in done]
                skipped += len(wanted) - len(kept)
                episodes_by_group[group] = kept
            episodes_by_group = {group: wanted for group, wanted in episodes_by_group.items() if wanted}
            groups = [group for group in groups if group in episodes_by_group]
            if not groups:
                raise CampaignError("--skip-done 后没有剩余可跑的条：全部已通过")
        total_episodes = sum(len(v) for v in episodes_by_group.values())
        manifest_name = f"feasibility_{label}_{total_episodes}.json" if label else f"feasibility{total_episodes}.json"
        feas_manifest = write_manifest(
            root / "manifests" / manifest_name, groups, episodes_by_group, specs_root,
            f"步骤 5 实跑：{len(groups)} 组，{scope_note}，共 {total_episodes} 条"
            + (f"（--skip-done 剔除已通过 {skipped} 条）" if skip_done else "")
            + f"；冻结候选合计 {sum(available.values())} 条，其余本轮不实跑",
        )
        source = "校准选出的" if chosen.get("measured", True) else "显式指定（未经测速）的"
        total_workers = tier * len(gpu_ids)  # 生成器的 --workers 是总数，按卡数摊成每卡 tier 个
        print(f"[实跑] 用{source} {mode}（--gpus {','.join(gpu_ids)} --workers {total_workers}，每卡 {tier}）跑 {total_episodes} 条", flush=True)
        result = invoke_generator(
            output_dir=root / "feasibility" / mode, manifest=feas_manifest,
            gpus=",".join(gpu_ids), workers=total_workers,
            # 同一档多次 invoke（smoke、--skip-done 续跑、缺口补跑）各自留一份生成器日志，不互相覆盖
            log_path=logs / (f"feasibility-{mode}.log" if not (logs / f"feasibility-{mode}.log").exists() else f"feasibility-{mode}-{time.strftime('%Y%m%dT%H%M%S')}.log"),
            sampling_config=sampling_config, timeout_s=int(float(wall_limit_h) * 3600),
            # 07 起：单条墙钟 600 秒（pebble 只杀该 worker）；BinFill 交付版直出「同一条重复两遍」的 demo
            episode_timeout_s=FEASIBILITY_EPISODE_TIMEOUT_S, binfill_demo=True,
        )
        rows = result["rows"]
        # 分母：这一档目录里累计应有的行数（清单条数 + 之前已通过而被 --skip-done 剔除的条），
        # 否则续跑一次后 FEASIBILITY 的 executed 会大于 unique
        payload.update(
            _summarize_feasibility(
                root, rows, groups, verdicts, tier, mode, gpu_ids, chosen,
                expected_rows=total_episodes + skipped,
            )
        )
        payload["run"] = {k: v for k, v in result.items() if k != "rows"}
        payload["scope"] = {"note": scope_note, "skipped_done": skipped, "manifest": str(feas_manifest.relative_to(REPO_ROOT))}
        payload["verdicts"] = verdicts.records
        payload["passed"] = verdicts.passed
        _write_json(root / f"{phase}_result.json", payload)
        # 每档另留一份，smoke（P0x1）与正式档（P01x20）不互相覆盖
        _write_json(root / f"{phase}_result_{mode}.json", payload)
        for line in verdicts.lines:
            print(line)
        print(f"RUN={'PASS' if verdicts.passed else 'FAIL'} phase={phase}")
        return payload

    raise CampaignError(f"未知阶段 {phase}")


def _feasibility_manifest_scope(output_dir: Path, plan_manifest: dict[str, Any]) -> tuple[list[tuple[str, str]], int]:
    """读这一档实跑用的清单，返回（组列表，应有行数 = 各组 episodes 之和）。

    清单路径取 ``run_parameters.json`` 的 ``episode_specs``；找不到时退回计划清单全部组 × 30
    （05／07 的口径），保证旧产物仍能 ``summarize``。
    """
    from .run import FEASIBILITY_EPISODES

    fallback_groups = [(item["task"], item["difficulty"]) for item in plan_manifest["groups"]]
    run_parameters = output_dir / "run_parameters.json"
    manifest_path: Path | None = None
    if run_parameters.is_file():
        recorded = json.loads(run_parameters.read_text(encoding="utf-8")).get("episode_specs")
        if recorded:
            manifest_path = Path(recorded)
    if manifest_path is None or not manifest_path.is_file():
        return fallback_groups, len(fallback_groups) * len(FEASIBILITY_EPISODES)
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    groups = [(item["task"], item["difficulty"]) for item in document["groups"]]
    return groups, sum(len(item["episodes"]) for item in document["groups"])


def cmd_summarize(run_id: str, mode: str | None = None) -> dict[str, Any]:
    """**不重跑仿真**，用当前代码重新统计既有的 ``episode_results.jsonl``。

    ⚠ 这是必需的退路，不是便利功能。父进程在启动那一刻就把 ``read_result_rows`` 等
    统计代码加载进内存了，跑到一半修好的 bug 对它无效；而仿真产物（jsonl、HDF5、视频）
    是完整的。实测踩过一次：旧版 key 少了 difficulty，330 行被统计成 120 行。
    没有这条退路就只能重跑几小时。
    """
    root, manifest_doc, _documents = load_group_documents(run_id)
    feasibility_root = root / "feasibility"
    if not feasibility_root.is_dir():
        raise CampaignError(f"找不到实跑产物：{feasibility_root}")
    modes = sorted(item.name for item in feasibility_root.iterdir() if item.is_dir())
    if mode is None:
        if len(modes) != 1:
            raise CampaignError(f"{feasibility_root} 下有多个档 {modes}，请用 --mode 指定")
        mode = modes[0]
    output_dir = feasibility_root / mode
    if not output_dir.is_dir():
        raise CampaignError(f"找不到该档的产物：{output_dir}")

    from .run import read_result_rows

    rows = read_result_rows(output_dir)
    # 组与分母以这一档实跑用的清单为准（run_parameters.json 记的 episode_specs），
    # 不再假定「计划清单全部组 × 30 条」——06 只跑 3 组、08 每组 5 条都不符合那个假定。
    groups, expected_rows = _feasibility_manifest_scope(output_dir, manifest_doc)
    tier = int(mode.rsplit("x", 1)[1]) if "x" in mode else 0
    previous = root / "feasibility_result.json"
    chosen = json.loads(previous.read_text(encoding="utf-8")).get("chosen") if previous.is_file() else None
    # 没有先前结论时卡号从生成器落盘的 run_parameters.json 取（双卡实跑后不能再假定只有 GPU 0）
    run_parameters = output_dir / "run_parameters.json"
    recorded_gpus = json.loads(run_parameters.read_text(encoding="utf-8")).get("gpus") if run_parameters.is_file() else None
    chosen = chosen or {"tier": tier, "mode": mode, "gpus": [str(g) for g in (recorded_gpus or ["0"])], "measured": False}

    verdicts = Verdicts(echo=True)
    payload: dict[str, Any] = {
        "run_id": run_id,
        "phase": "feasibility",
        "recomputed_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "recomputed_from": str(output_dir / "episode_results.jsonl"),
        "expected_rows": expected_rows,
    }
    payload.update(
        _summarize_feasibility(
            root, rows, groups, verdicts, tier, mode, chosen.get("gpus") or ["0"], chosen, expected_rows=expected_rows
        )
    )
    payload["verdicts"] = verdicts.records
    payload["passed"] = verdicts.passed
    _write_json(root / "feasibility_result.json", payload)
    print(f"SUMMARIZE={'PASS' if verdicts.passed else 'FAIL'} mode={mode} rows={len(rows)}")
    return payload

def _summarize_feasibility(
    root: Path,
    rows: list[dict[str, Any]],
    groups: Sequence[tuple[str, str]],
    verdicts: "Verdicts",
    tier: int,
    mode: str,
    gpu_ids: Sequence[str],
    chosen: dict[str, Any],
    expected_rows: int | None = None,
) -> dict[str, Any]:
    """从实跑结果行（05 为 330 行，按 组数 × 30 参数化）算出实跑阶段的全部判定与计数。

    ``expected_rows`` 是应有行数（各组 episodes 之和）；不传时按 组数 × 30 算（05／07 口径）。

    ⚠ 抽成独立函数是为了让 ``summarize`` 子命令能在**不重跑仿真**的前提下，
    用当前代码重新统计既有的 ``episode_results.jsonl``。实测踩过一次：父进程启动时
    加载的是旧版 ``read_result_rows``（key 少了 difficulty），330 行被统计成 120 行，
    而原始 jsonl 是完整的——这种情况必须能独立重算，不能被迫重跑几小时的仿真。
    """
    from .run import FEASIBILITY_EPISODES, OUTCOME_PASS

    outcomes = Counter(row["outcome"] for row in rows)
    videos = Counter(row["video_status"] for row in rows)
    states = Counter(row["execution_state"] for row in rows)
    # ⚠ 「规划失败」这一类实际混装三种来源：ScrewPlanFailure／PlannerExhausted（真规划无解）、
    # SceneGenerationError（场景生成失败）、DatasetGenerationError（环境 evaluate 判定任务失败）。
    # 七类状态互斥是计划定死的，不能擅自加第八类，但必须把 error_type 分布一并报出来，
    # 否则「规划失败 N 条」会掩盖掉它们是完全不同的失败。
    error_types = Counter(
        str(row["error_type"] or "-") for row in rows if row["outcome"] != OUTCOME_PASS
    )
    expected = len(groups) * len(FEASIBILITY_EPISODES) if expected_rows is None else int(expected_rows)
    verdicts.add(
        "FEASIBILITY", len(rows) == expected, unique=expected, executed=len(rows),
        unclassified=sum(1 for row in rows if row["outcome"] not in outcomes),
        succeeded=outcomes.get(OUTCOME_PASS, 0), attempt=0,
    )
    verdicts.add(
        "RESULT_COVERAGE", len(rows) == expected,
        all_recorded=len(rows), all_success=outcomes.get(OUTCOME_PASS, 0),
    )
    untraceable = sum(
        1 for row in rows if row["video_status"] in ("missing", "no_close") and not row["video_reason"]
    )
    verdicts.add(
        "VIDEO_INDEX", len(rows) == expected and untraceable == 0, rows=len(rows),
        complete=videos.get("complete", 0), frame_mismatch=videos.get("frame_mismatch", 0),
        missing=videos.get("missing", 0), no_close=videos.get("no_close", 0), untraceable=untraceable,
    )
    # COLLISION_RUNTIME：只覆盖本次实跑里的两个视频任务组（05 是 5 组 × 30 = 150 条，06 只跑 xhard 时是 2 组 × 30 = 60 条）
    video_rows = [row for row in rows if row["task"] in ("VideoUnmaskSwap", "VideoRepick")]
    checked = sum(1 for row in video_rows if row["runtime_checks_total"] > 0)
    # 「应检查但既未检查也未阻断」：跑完了、任务也通过了，却一条检查记录都没有
    missing_checks = sum(
        1 for row in video_rows
        if row["runtime_checks_total"] == 0 and row["outcome"] == OUTCOME_PASS
    )
    runtime_rejected = sum(1 for row in video_rows if row["runtime_rejections"])
    # 作用域里根本没有视频任务组（08 只跑 RouteStick 四组）时，「一条检查都没有」不是漏检而是无从检查：
    # 只在作用域含视频任务组却一行视频结果都没有时才判 FAIL，避免把不适用当成失败；scope 字段写明口径。
    video_groups = [group for group in groups if group[0] in ("VideoUnmaskSwap", "VideoRepick")]
    verdicts.add(
        "COLLISION_RUNTIME", missing_checks == 0 and (bool(video_rows) or not video_groups),
        unique=len(video_rows), checked=checked, missing_checks=missing_checks,
        rejected=runtime_rejected, scope=f"{len(video_groups)}_video_groups",
    )
    # INJECTION_BINDING：每条成功样本都要有创建输入 vs 创建后位姿的绑定证据
    bound = sum(1 for row in rows if row["injection_bound"])
    unbound_success = sum(1 for row in rows if row["outcome"] == OUTCOME_PASS and not row["injection_bound"])
    verdicts.add(
        "INJECTION_BINDING", unbound_success == 0 and bound > 0,
        unique=len(rows), bound=bound, mismatches=unbound_success,
    )

    success_rows = [row for row in rows if row["outcome"] == OUTCOME_PASS]
    decoded = sum(1 for row in success_rows if row["video_frames"] == row["video_frames_expected"])
    failed_videos = sum(1 for row in rows if row["outcome"] != OUTCOME_PASS and row["video_status"] == "complete")
    verdicts.add(
        "VIDEO_DECODE", decoded == len(success_rows), success_rows=len(success_rows),
        decoded_eq_timesteps=decoded, failed_videos=failed_videos,
        mismatches=len(success_rows) - decoded,
    )
    summary = {
            "tier": tier, "mode": mode, "gpus": list(gpu_ids),
            "tier_measured": chosen.get("measured", True),
            "rows": rows,
            "outcome_counts": dict(outcomes), "video_counts": dict(videos), "execution_counts": dict(states),
            "error_type_counts": dict(error_types),
            "runtime_check_summary": {
                "video_rows": len(video_rows), "checked": checked,
                "missing_checks": missing_checks, "rejected": runtime_rejected,
            },
            "per_group": {
                f"{task}/{difficulty}": dict(
                    Counter(row["outcome"] for row in rows if row["task"] == task and row["difficulty"] == difficulty)
                )
                for task, difficulty in groups
            },
    }
    _write_json(root / "feasibility_results.json", {"run_id": root.name, "tier": tier, "rows": rows})
    return summary


# ── env-check：额外候选「可以产生环境」的核验（2026-09-12）──────────────────
def cmd_env_check(
    run_id: str,
    delivery_config: Path,
    sampling_config: Path,
    *,
    tier: int,
    gpus: str = "0",
    groups_filter: Sequence[str] | None = None,
    limit: int | None = None,
    label: str | None = None,
    timeout_s: float = 120.0,
) -> dict[str, Any]:
    """对每组实跑区间之后的候选按序做 ``gym.make + reset + close``（不套录像器、零产物），
    攒够交付配置里的 ``extra_candidates`` 条 reset 通过者即停。

    产物：``<运行根>/env_check/<任务>/<难度>.jsonl`` 与 ``env_check_result.json``（``label`` 给出时落
    ``env_check/_<label>/``，smoke 用，不计入正式）。判定行 ``ENV_RESET``（每组）与 ``ENV_CHECK``（汇总）。
    ⚠ 语义边界见 :data:`scripts.injection.env_check.SEMANTIC_NOTE`：reset 通过 ≠ 能出 h5。
    """
    from .env_check import EnvCheckPlan, run_env_check

    root, manifest_doc, documents = load_group_documents(run_id)
    try:
        delivery = load_delivery_config(delivery_config, resolve_contract(manifest_doc))
    except DeliveryError as exc:
        raise CampaignError(f"交付配置不合法：{exc}") from exc
    if manifest_doc.get("delivery_config_sha256") not in (None, delivery.sha256):
        raise CampaignError("交付配置与冻结时不符（散列不同），拒绝按漂移的口径核验")
    gpu_ids = [item.strip() for item in gpus.split(",") if item.strip()]
    if not gpu_ids or len(gpu_ids) != len(set(gpu_ids)):
        raise CampaignError(f"--gpus 非法：{gpus!r}")
    groups = _select_groups([(item["task"], item["difficulty"]) for item in manifest_doc["groups"]], groups_filter)
    plans = []
    for task, difficulty in groups:
        group = delivery.group(task, difficulty)
        if group.env_check_start >= len(documents[(task, difficulty)]["episodes"]):
            raise CampaignError(f"{task}/{difficulty} 实跑区间之后没有剩余候选可核验")
        plans.append(EnvCheckPlan(task, difficulty, group.env_check_start, group.extra_candidates, limit))
    out_dir = root / "env_check" / (f"_{label}" if label else "")
    print(f"[env-check] {len(plans)} 组，每组从实跑区间之后按序核验、攒够 {delivery.extra_candidates} 条通过即停；"
          f"--gpus {','.join(gpu_ids)} 每卡 {tier} worker，单条 {timeout_s:.0f} 秒", flush=True)
    payload = run_env_check(
        documents, plans, gpus=gpu_ids, workers_per_gpu=int(tier), sampling_config=sampling_config,
        out_dir=out_dir, repo_root=REPO_ROOT, timeout_s=float(timeout_s),
    )
    payload["run_id"] = run_id
    payload["delivery_config"] = {"path": str(delivery.path), "sha256": delivery.sha256}
    payload["label"] = label
    target = root / (f"env_check_result_{label}.json" if label else "env_check_result.json")
    _write_json(target, payload)
    verdicts = Verdicts()
    for item in payload["verdicts"]:
        verdicts.add(item["name"], item["passed"], **item["fields"])
    for line in verdicts.lines:
        print(line)
    print(f"ENV_CHECK_RUN={'PASS' if payload['passed'] else 'FAIL'} run_id={run_id} out={target.relative_to(REPO_ROOT)}")
    return payload


# ── delivery：严格交付清单（2026-09-12）───────────────────────────────────────
def cmd_delivery(run_id: str, delivery_config: Path, *, hash_mode: str = "full", workers: int = 8) -> dict[str, Any]:
    """扫全部实跑档目录的结果行，每组按 episode 升序取前 ``target_h5`` 条通过为正式、其余通过为 spare，
    写 ``delivery_manifest.json``；判定行 ``DELIVERY_400``（每 env）与 ``DELIVERY_TOTAL``。"""
    from .run import read_result_rows

    root, manifest_doc, documents = load_group_documents(run_id)
    try:
        delivery = load_delivery_config(delivery_config, resolve_contract(manifest_doc))
    except DeliveryError as exc:
        raise CampaignError(f"交付配置不合法：{exc}") from exc
    feasibility_root = root / "feasibility"
    if not feasibility_root.is_dir():
        raise CampaignError(f"找不到实跑产物：{feasibility_root}")
    # 合并全部档目录（smoke 的 P0x1 与正式的 P01x20）；同一条在多个档里都有时保留正式档（按目录名排序靠后者）
    merged: dict[tuple[str, str, int], dict[str, Any]] = {}
    modes = sorted(item.name for item in feasibility_root.iterdir() if item.is_dir())
    for mode in modes:
        for row in read_result_rows(feasibility_root / mode):
            key = (row["task"], str(row["difficulty"]), int(row["episode"]))
            if key not in merged or row["outcome"] == "通过" or merged[key]["outcome"] != "通过":
                merged[key] = {**row, "mode": mode}
    rows = [merged[key] for key in sorted(merged)]
    spec_sha = {
        (task, difficulty, int(item["episode"])): item["spec_sha256"]
        for (task, difficulty), doc in documents.items()
        for item in doc["episodes"]
    }
    env_check_path = root / "env_check_result.json"
    env_check_result = json.loads(env_check_path.read_text(encoding="utf-8")) if env_check_path.is_file() else None
    payload = build_delivery_manifest(
        rows, delivery, run_id=run_id, repo_root=REPO_ROOT, env_check_result=env_check_result,
        hash_mode=hash_mode, workers=int(workers), spec_sha_by_key=spec_sha,
    )
    payload["modes"] = modes
    _write_json(root / "delivery_manifest.json", payload)
    verdicts = Verdicts()
    for item in payload["verdicts"]:
        verdicts.add(item["name"], item["passed"], **item["fields"])
    for line in verdicts.lines:
        print(line)
    print(f"DELIVERY_RUN={'PASS' if payload['passed'] else 'FAIL'} run_id={run_id} rows={len(rows)} modes={','.join(modes)}")
    return payload


# ── report：步骤 6 的轻量包与交付核对 ───────────────────────────────────────
def cmd_report(run_id: str) -> dict[str, Any]:
    """汇总全部阶段的判定与计数，写轻量包到 ``docs/validation/newtask-v2/<运行编号>/``。

    轻量**不表示只留成功条目**：没有 HDF5 的失败也必须能定位到规格与错误阶段。
    重产物（HDF5、视频、PNG）留在 ``artifacts/`` 原地，这里只存路径、帧数与 SHA-256。
    """
    root, manifest, documents = load_group_documents(run_id)
    target = REPO_ROOT / "docs" / "validation" / "newtask-v2" / run_id
    target.mkdir(parents=True, exist_ok=True)

    def _load(name: str) -> dict[str, Any] | None:
        path = root / name
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None

    check = _load("check_result.json")
    calibration = _load("calibration_result.json")
    feasibility = _load("feasibility_result.json")
    plots = {phase: _load(f"plot_manifest_{phase}.json") for phase in ("before", "after")}

    verdicts: list[dict[str, Any]] = []
    for payload in (check, calibration, feasibility):
        if payload:
            verdicts.extend(payload.get("verdicts", []))

    # 在别处取得、但属于同一次验收的判定（关闭态对拍、冒烟、固定案例复现、出图）。
    # 它们的产物分散在其它运行编号或 collision-replay 目录下，这里按证据路径并入，
    # 每条都带 evidence 字段指回原始文件，不凭空造数字。
    external = _load("external_evidence.json")
    if external:
        verdicts.extend(external.get("verdicts", []))

    # 2026-09-12：env-check 与严格交付的判定并入（两份 JSON 也复制进轻量包）
    env_check = _load("env_check_result.json")
    delivery_manifest = _load("delivery_manifest.json")
    for payload_extra in (env_check, delivery_manifest):
        if payload_extra:
            extra = Verdicts()
            for item in payload_extra.get("verdicts", []):
                extra.add(item["name"], item["passed"], **item["fields"])
            verdicts.extend(extra.records)

    # 单独跑出来的并行实测覆盖校准阶段的 NOT_RUN 占位。
    # ⚠ 只覆盖「确实另行测过」的项：PARALLEL_SCALE 没测过，它的 NOT_RUN 必须原样保留。
    measured = _load("parallel_content.json")
    if measured:
        verdicts = [item for item in verdicts if item["name"] != "PARALLEL_CONTENT"]
        extra = Verdicts()
        extra.add(
            "PARALLEL_CONTENT", measured["passed"], unique=measured["compared"],
            differences=len(measured["difference_episodes"]),
            note="实跑12worker对S0a单worker",
        )
        verdicts.extend(extra.records)
    overlap = _load("parallel_overlap.json")
    if overlap:
        verdicts = [item for item in verdicts if item["name"] != "PARALLEL_OVERLAP"]
        extra = Verdicts()
        extra.add(
            "PARALLEL_OVERLAP", overlap["passed"], mode="P0x12", gpus=1,
            workers_per_gpu=overlap["workers_per_gpu"],
            peak_distinct_pids=overlap["peak_distinct_pids"],
            samples=overlap["samples"],
        )
        verdicts.extend(extra.records)

    # 规格清单散列：每组一条，独立重算，不信任 plan 写下的值
    spec_digest = []
    for item in manifest["groups"]:
        path = root / item["path"]
        spec_digest.append(
            {
                "task": item["task"], "difficulty": item["difficulty"], "path": item["path"],
                "episodes": item["episodes"], "file_sha256": _sha256_file(path),
                "matches_manifest": _sha256_file(path) == item["file_sha256"],
            }
        )

    # 交付核对：逐条核 videos/ 下的实际文件与散列
    rows = (feasibility or {}).get("rows", [])
    videos_expected = sum(1 for row in rows if row["video_status"] not in ("missing", "no_close"))
    videos_on_disk = 0
    video_sha_mismatch = 0
    for row in rows:
        path_text = row.get("video_path")
        if not path_text:
            continue
        path = Path(path_text)
        if not path.is_file():
            continue
        videos_on_disk += 1
        if row.get("video_sha256") and _sha256_file(path) != row["video_sha256"]:
            video_sha_mismatch += 1

    delivery = Verdicts()
    expected_specs = sum(item["episodes"] for item in manifest["groups"])
    delivery.add(
        "DELIVERY",
        all(item["matches_manifest"] for item in spec_digest)
        and videos_on_disk == videos_expected
        and video_sha_mismatch == 0
        and bool(rows),
        specs=expected_specs, result_rows=len(rows),
        missing=sum(1 for row in rows if row["video_status"] == "missing"),
        videos_on_disk=videos_on_disk, videos_expected=videos_expected,
        video_sha_mismatch=video_sha_mismatch,
    )
    verdicts.extend(delivery.records)

    payload = {
        "run_id": run_id,
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "manifest": {key: value for key, value in manifest.items() if key != "groups"},
        "spec_digest": spec_digest,
        "verdicts": verdicts,
        "outcome_counts": (feasibility or {}).get("outcome_counts"),
        "error_type_counts": (feasibility or {}).get("error_type_counts"),
        "video_counts": (feasibility or {}).get("video_counts"),
        "execution_counts": (feasibility or {}).get("execution_counts"),
        "per_group": (feasibility or {}).get("per_group"),
        "external_evidence": external,
        "parallel_content": measured,
        "parallel_overlap": overlap,
        "calibration_ladder": (calibration or {}).get("ladder"),
        "calibration_chosen": (calibration or {}).get("chosen"),
        "gpu_note": (calibration or {}).get("gpu_note"),
        "plots": {phase: (item or {}).get("groups") for phase, item in plots.items()},
        "rows": rows,
    }
    payload["env_check"] = {k: v for k, v in (env_check or {}).items() if k != "verdicts"} or None
    payload["delivery_400"] = (
        {k: v for k, v in delivery_manifest.items() if k not in ("verdicts", "groups")} | {
            "groups": {
                key: {k: v for k, v in value.items() if k not in ("primary", "spare_rows", "failures")}
                for key, value in delivery_manifest.get("groups", {}).items()
            }
        }
        if delivery_manifest else None
    )
    _write_json(target / "report.json", payload)
    _write_json(target / "result_rows.json", {"run_id": run_id, "rows": rows})
    if env_check:
        _write_json(target / "env_check_result.json", env_check)
    if delivery_manifest:
        _write_json(target / "delivery_manifest.json", delivery_manifest)
    (target / "README.md").write_text(_render_readme(payload), encoding="utf-8")

    for record in delivery.records:
        print(" ".join([f"{record['name']}={record['status']}"] + [
            f"{key}={value}" for key, value in record.items() if key not in ("name", "status", "detail")
        ]))
    print(f"REPORT=OK run_id={run_id} 轻量包 {target.relative_to(REPO_ROOT)}")
    return payload


def _render_readme(payload: dict[str, Any]) -> str:
    """轻量包的中文 README：判定行、计数表、档位记录、失败清单一页可查。"""
    lines = [
        f"# 新值注入专项实测报告 · {payload['run_id']}",
        "",
        f"生成时间（UTC）：{payload['generated_utc']}",
        "",
        "> 本报告由 `scripts.injection.campaign report` 从各阶段的原始产物汇总，",
        "> 数字均为实测。重产物（HDF5、视频、PNG）留在 `artifacts/injection/` 原地，",
        "> 这里只存路径、帧数与 SHA-256。",
        "",
        "## 一、判定行",
        "",
        "| 判定项 | 结果 | 关键数字 |",
        "|---|---|---|",
    ]
    for record in payload["verdicts"]:
        numbers = " ".join(
            f"{key}={value}" for key, value in record.items()
            if key not in ("name", "status", "detail") and not isinstance(value, (dict, list))
        )
        lines.append(f"| `{record['name']}` | {record['status']} | {numbers} |")

    if payload.get("gpu_note"):
        lines += ["", f"⚠ {payload['gpu_note']}"]

    if payload.get("outcome_counts"):
        total_rows = sum(payload["outcome_counts"].values())
        lines += ["", f"## 二、实跑 {total_rows} 条的七类结果", "", "| 结果 | 条数 |", "|---|---:|"]
        for key, value in payload["outcome_counts"].items():
            lines.append(f"| {key} | {value} |")
        lines += ["", "### 每组明细", "", "| 组 | " + " | ".join(payload["outcome_counts"]) + " |",
                  "|---" * (len(payload["outcome_counts"]) + 1) + "|"]
        for group, counts in (payload.get("per_group") or {}).items():
            lines.append(f"| {group} | " + " | ".join(str(counts.get(key, 0)) for key in payload["outcome_counts"]) + " |")

    if payload.get("error_type_counts"):
        lines += [
            "", "### 失败样本的 error_type 分布", "",
            "> ⚠ 「规划失败」一类混装三种来源：`ScrewPlanFailure`／`PlannerExhausted`（规划无解）、",
            "> `SceneGenerationError`（场景生成失败）、`DatasetGenerationError`（环境判定任务失败）。",
            "> 七类状态按计划互斥、不加第八类，但这里把 `error_type` 分开列，避免一个数字掩盖三种失败。",
            "", "| error_type | 条数 |", "|---|---:|",
        ]
        for key, value in sorted(payload["error_type_counts"].items(), key=lambda item: -item[1]):
            lines.append(f"| `{key}` | {value} |")

    if payload.get("video_counts"):
        lines += ["", "## 三、视频状态", "", "| 状态 | 条数 |", "|---|---:|"]
        for key, value in payload["video_counts"].items():
            lines.append(f"| `{key}` | {value} |")

    if payload.get("calibration_ladder"):
        lines += [
            "", "## 四、档位阶梯", "",
            "| 档 | worker | 可用 | 交付 | 失败 | 墙钟(秒) | 吞吐(条/分) | 峰值RSS(MB) | 备注 |",
            "|---|---:|---|---:|---:|---:|---:|---:|---|",
        ]
        for item in payload["calibration_ladder"]:
            lines.append(
                f"| `{item.get('mode', item['tier'])}` | {item['workers']} | "
                f"{'否' if item['unusable'] else '是'} | {item['delivered']} | {item['failed']} | "
                f"{item['wall_s']} | {item['delivered_per_min']} | {item['peak_rss_mb']:.0f} | {item['reason'] or '—'} |"
            )
        chosen = payload.get("calibration_chosen")
        lines += ["", f"选中档位：**{chosen['mode'] if chosen else '无'}**"]

    delivery_400 = payload.get("delivery_400")
    if delivery_400:
        lines += [
            "", "## 三·一、严格交付（每 env 400 条，按 episode 序取前 N 条通过为正式）", "",
            "| env | 目标 | 交付 | spare | 失败 | 组数 |", "|---|---:|---:|---:|---:|---:|",
        ]
        for env, item in delivery_400.get("envs", {}).items():
            lines.append(f"| {env} | {item.get('target')} | {item.get('delivered')} | {item.get('spare')} | {item.get('failed')} | {len(item.get('groups', []))} |")
        lines += ["", "| 组 | 目标 | 实跑 | 结果行 | 通过 | 交付 | spare | 失败 |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
        for key, item in delivery_400.get("groups", {}).items():
            lines.append(
                f"| {key} | {item.get('target_h5')} | {item.get('run_episodes')} | {item.get('rows')} | {item.get('passed')} | "
                f"{item.get('delivered')} | {item.get('spare')} | {item.get('failed')} |"
            )
        if delivery_400.get("shortfall"):
            lines += ["", "⚠ 缺口：" + "; ".join(f"{s['group']} 缺 {s['missing']}（剩余候选 {s['remaining_candidates']}）" for s in delivery_400["shortfall"])]
    env_check = payload.get("env_check")
    if env_check:
        lines += [
            "", "## 三·二、额外候选 env-check（只 make + reset + close，零产物）", "",
            f"> {env_check.get('note', '')}", "",
            "| 组 | 起点 | 核验 | 通过 | 失败 | 交付 | 缺口 |", "|---|---:|---:|---:|---:|---:|---:|",
        ]
        for key, item in env_check.get("groups", {}).items():
            lines.append(
                f"| {key} | {item.get('start')} | {item.get('checked')} | {item.get('passed')} | {item.get('failed')} | "
                f"{len(item.get('delivered', []))} | {item.get('shortfall')} |"
            )

    failures = [row for row in payload.get("rows", []) if row["outcome"] != "通过"]
    if failures:
        lines += [
            "", "## 五、失败样本清单（保留在分母里，不换 seed、不补位）", "",
            "| 组 | episode | 任务结果 | 执行状态 | error_type | 视频状态 |", "|---|---:|---|---|---|---|",
        ]
        for row in failures:
            lines.append(
                f"| {row['task']}/{row['difficulty']} | {row['episode']} | {row['outcome']} | "
                f"{row['execution_state']} | `{row['error_type'] or '—'}` | `{row['video_status']}` |"
            )

    lines += [
        "", "## 六、规格清单散列", "",
        "| 组 | 条数 | 文件 SHA-256（前 16 位） | 与清单一致 |", "|---|---:|---|---|",
    ]
    for item in payload["spec_digest"]:
        lines.append(
            f"| {item['task']}/{item['difficulty']} | {item['episodes']} | "
            f"`{item['file_sha256'][:16]}…` | {'是' if item['matches_manifest'] else '**否**'} |"
        )
    lines.append("")
    return "\n".join(lines)


# ── collision-reproduce：固定案例的轨迹重算 ────────────────────────────────
COLLISION_CASE_ROOT = REPO_ROOT / "artifacts" / "collision-preplan" / "20260909-bin-contact-v2"


def cmd_collision_reproduce(source_dir: Path, output_dir: Path, mode: str) -> dict[str, Any]:
    """从保存的初态重算 9 例交换轨迹，逐步核对位姿、SAT 判定值与最危险对象对。

    ⚠ 只读原目录。复现产物落 ``output_dir``，目录已存在即拒绝——编号用过就换新的，
    绝不覆盖已获用户目视确认的原件。
    ⚠ ``--mode render``（从保存轨迹重渲染）需要 SAPIEN 渲染，本子命令不做，如实记 `NOT_RUN`。
    """
    from .replay import replay_case, verify_source_files

    if not source_dir.is_dir():
        raise CampaignError(f"找不到固定案例目录：{source_dir}")
    if output_dir.exists():
        raise CampaignError(f"输出目录已存在，编号不可复用：{output_dir}")

    integrity = verify_source_files(source_dir)
    manifest = json.loads((source_dir / "manifest.json").read_text(encoding="utf-8"))
    epsilon = float(manifest["epsilon_m"])

    results = [replay_case(case, epsilon=epsilon) for case in manifest["cases"]]
    accepted = sum(1 for item in results if item["recomputed_status"] == "PASS")
    rejected = sum(1 for item in results if item["recomputed_status"] == "REJECT")
    all_passed = all(item["passed"] for item in results)

    verdicts = Verdicts(echo=True)
    verdicts.add(
        "COLLISION_REPRODUCE", all_passed and not integrity["file_problems"],
        cases=len(results), accepted=accepted, rejected=rejected,
        original_unchanged=0 if integrity["file_problems"] else 1,
        max_pose_diff_m=f"{max((item['max_pose_diff_m'] for item in results), default=0.0):.3g}",
        max_gap_diff_m=f"{max((item['max_gap_diff_m'] for item in results), default=0.0):.3g}",
        mode=mode,
    )
    if mode != "trajectory":
        verdicts.add("COLLISION_RERENDER", None, reason="从保存轨迹重渲染需要 SAPIEN，本子命令不做")

    if integrity["geometry_source_drift"]:
        # 显式报告，不隐瞒：几何来源文件动过就要说清动的是哪里、为什么不影响几何
        for item in integrity["geometry_source_drift"]:
            print(
                f"  ⚠ 几何来源散列漂移 {item['path']}：记录 {item['recorded'][:12]}…，"
                f"当前 {(item['current'] or 'None')[:12]}…；"
                "逐步重算 9/9 一致本身证明盒体几何未变（本轮只给该文件加了 fixed_xy/fixed_yaw 参数）",
                flush=True,
            )

    payload = {
        "source_dir": str(source_dir),
        "output_dir": str(output_dir),
        "mode": mode,
        "epsilon_m": epsilon,
        "integrity": integrity,
        "cases": results,
        "verdicts": verdicts.records,
        "passed": all_passed and not integrity["file_problems"],
    }
    _write_json(output_dir / "replay_result.json", payload)
    print(f"REPRODUCE={'PASS' if payload['passed'] else 'FAIL'} 产物 {output_dir.relative_to(REPO_ROOT)}")
    return payload


# ── CLI ─────────────────────────────────────────────────────────────────────
def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="新值注入专项：规格生成、静态检查、出图与实跑编排")
    sub = parser.add_subparsers(dest="command", required=True)

    plan = sub.add_parser("plan", help="按契约里的组列表生成并冻结每组 100 条规格（v2 为 11 组，v3 为 14 组）")
    plan.add_argument("--run-id", required=True)
    plan.add_argument("--seed", type=int, default=DEFAULT_SEED)
    plan.add_argument("--per-group", type=int, default=GROUP_SIZE)
    plan.add_argument("--sampling-config", default=str(DEFAULT_SAMPLING_CONFIG))
    plan.add_argument(
        "--contract", required=True,
        help="取值域与分配的约定 JSON（scripts/configs/newtask-v2/injection_contract_v*.json）；必填，不给默认值",
    )
    plan.add_argument(
        "--delivery-config", default=None,
        help="交付配置 JSON（scripts/configs/newtask-v2/delivery_400.json）：每组候选 = blocks × 100；不给时每组 100 条",
    )

    check = sub.add_parser("check", help="从冻结规格独立重算全部计数与几何")
    check.add_argument("--run-id", required=True)
    check.add_argument("--sampling-config", default=str(DEFAULT_SAMPLING_CONFIG))
    check.add_argument("--contract", default=None, help="默认按清单 contract_path 加载；只在文件被挪动时显式指定，散列仍须一致")

    plot = sub.add_parser("plot", help="出跑前／跑后三类图")
    plot.add_argument("--run-id", required=True)
    plot.add_argument("--phase", default="before", choices=("before", "after"))

    runner = sub.add_parser("run", help="步骤 3～5 的执行编排")
    runner.add_argument("--run-id", required=True)
    runner.add_argument("--phase", required=True, choices=("calibration", "feasibility"))
    runner.add_argument("--sampling-config", default=str(DEFAULT_SAMPLING_CONFIG))
    runner.add_argument(
        "--tiers", default=None,
        help="逗号分隔的每卡 worker 档位，默认 12,16,20,24,28,32；一路向上探到 OOM／超时为止",
    )
    runner.add_argument(
        "--skip-ladder", action="store_true",
        help="calibration 只做串行参考，跳过档位阶梯；并行三项如实记 NOT_RUN",
    )
    runner.add_argument(
        "--tier", type=int, default=None,
        help="feasibility 显式指定每卡 worker 数（跳过档位校准时必须给），报告里会标明该档未经测速",
    )
    runner.add_argument(
        "--gpus", default="0",
        help="feasibility + --tier 时用的物理卡号，逗号分隔（如 0,1）；每卡 worker 数由 --tier 给，总 worker = tier × 卡数；默认只用 GPU 0",
    )
    runner.add_argument(
        "--groups", default=None,
        help="feasibility 只跑清单里这些组，逗号分隔的 任务/难度（如 RouteStick/xhard,VideoRepick/xhard）；默认跑清单全部组",
    )
    runner.add_argument(
        "--episodes", type=int, default=None,
        help="feasibility 每组实跑条数（episode 0～N-1）；默认 30（07 及之前的口径）。08 RouteStick 四档各 5 条用 5",
    )
    runner.add_argument("--delivery-config", default=None, help="feasibility 按交付配置各组实跑 range(run_episodes)；与 --episodes 互斥")
    runner.add_argument("--episode-range", default=None, help="feasibility 每组只跑 episode a-b（含 a 不含 b），缺口补跑用；如 155-170")
    runner.add_argument("--skip-done", action="store_true", help="剔除该档目录里已通过的条，中断后同命令续跑")
    runner.add_argument("--wall-limit-h", type=float, default=6.0, help="整批墙钟上限（小时），默认 6")
    runner.add_argument("--label", default=None, help="清单文件名后缀 manifests/feasibility_<label>_<n>.json")

    env_check = sub.add_parser("env-check", help="额外候选核验：对实跑区间之后的候选只做 make+reset+close，零产物")
    env_check.add_argument("--run-id", required=True)
    env_check.add_argument("--delivery-config", required=True)
    env_check.add_argument("--sampling-config", default=str(DEFAULT_SAMPLING_CONFIG))
    env_check.add_argument("--tier", type=int, required=True, help="每卡 worker 数")
    env_check.add_argument("--gpus", default="0")
    env_check.add_argument("--groups", default=None, help="只核验这些组，逗号分隔的 任务/难度")
    env_check.add_argument("--limit", type=int, default=None, help="每组最多核验多少条候选（smoke 用）")
    env_check.add_argument("--label", default=None, help="给出时产物落 env_check/_<label>/ 与 env_check_result_<label>.json，不计入正式")
    env_check.add_argument("--timeout", type=float, default=120.0, help="单条 make+reset 墙钟上限（秒）")

    delivery = sub.add_parser("delivery", help="严格交付清单：每组按 episode 序取前 target_h5 条通过为正式")
    delivery.add_argument("--run-id", required=True)
    delivery.add_argument("--delivery-config", required=True)
    delivery.add_argument("--hash", default="full", choices=("full", "size-only", "none"), help="h5 校验和口径")
    delivery.add_argument("--workers", type=int, default=8)

    summarize = sub.add_parser("summarize", help="不重跑仿真，用当前代码重算既有实跑结果")
    summarize.add_argument("--run-id", required=True)
    summarize.add_argument("--mode", default=None, help="档目录名，如 P0x12；只有一个档时可省")

    report = sub.add_parser("report", help="汇总各阶段判定与计数，写轻量包")
    report.add_argument("--run-id", required=True)

    reproduce = sub.add_parser("collision-reproduce", help="固定碰撞案例的轨迹重算")
    reproduce.add_argument("--source-dir", default=str(COLLISION_CASE_ROOT))
    reproduce.add_argument("--output-dir", required=True, help="复现产物目录，必须是新目录")
    reproduce.add_argument("--mode", default="trajectory", choices=("trajectory", "both"))

    specs_diff = sub.add_parser("specs-diff", help="两次冻结运行共有组的规格散列逐条对拍（新契约冻结后证明旧组不变）")
    specs_diff.add_argument("--left", required=True, help="参考侧 run id")
    specs_diff.add_argument("--right", required=True, help="候选侧 run id")
    specs_diff.add_argument("--label", default="OLD_GROUPS_EQUIVALENCE")
    specs_diff.add_argument("--episode-scope", default="union", choices=("union", "intersection", "block0"),
                            help="union=并集（历史语义）；intersection=只比共有号；block0=只比前 100 条且要求两边都完整")

    compare = sub.add_parser("compare", help="两个运行目录的完整 HDF5 逐位对拍")
    compare.add_argument("--left", required=True, help="参考侧目录")
    compare.add_argument("--right", required=True, help="候选侧目录")
    compare.add_argument("--label", default="COMPARE", help="判定行名，如 DEFAULT_PARITY")
    compare.add_argument("--out", default=None, help="把完整结果写到该 JSON")
    compare.add_argument(
        "--subset-only", action="store_true",
        help="只判交集：一侧多出的 episode 照常报告但不判失败（负载阶梯对串行参考时用）",
    )

    args = parser.parse_args(argv)
    try:
        if args.command == "plan":
            cmd_plan(
                args.run_id, args.seed, args.per_group, Path(args.sampling_config).resolve(), Path(args.contract).resolve(),
                delivery_config=Path(args.delivery_config).resolve() if args.delivery_config else None,
            )
            return 0
        if args.command == "check":
            contract_override = Path(args.contract).resolve() if args.contract else None
            return 0 if cmd_check(args.run_id, Path(args.sampling_config).resolve(), contract_override)["passed"] else 1
        if args.command == "plot":
            from .plots import cmd_plot

            cmd_plot(args.run_id, args.phase)
            return 0
        if args.command == "run":
            tiers = [int(item) for item in args.tiers.split(",")] if args.tiers else None
            result = cmd_run(
                args.run_id, args.phase, Path(args.sampling_config).resolve(), tiers,
                skip_ladder=args.skip_ladder, tier_override=args.tier, gpus=args.gpus,
                groups_filter=[item.strip() for item in args.groups.split(",") if item.strip()] if args.groups else None,
                episodes_per_group=args.episodes,
                delivery_config=Path(args.delivery_config).resolve() if args.delivery_config else None,
                episode_range=tuple(int(x) for x in args.episode_range.split("-", 1)) if args.episode_range else None,
                skip_done=args.skip_done, wall_limit_h=args.wall_limit_h, label=args.label,
            )
            return 0 if result.get("passed") else 1
        if args.command == "env-check":
            result = cmd_env_check(
                args.run_id, Path(args.delivery_config).resolve(), Path(args.sampling_config).resolve(),
                tier=args.tier, gpus=args.gpus,
                groups_filter=[item.strip() for item in args.groups.split(",") if item.strip()] if args.groups else None,
                limit=args.limit, label=args.label, timeout_s=args.timeout,
            )
            return 0 if result.get("passed") else 1
        if args.command == "delivery":
            result = cmd_delivery(args.run_id, Path(args.delivery_config).resolve(), hash_mode=args.hash, workers=args.workers)
            return 0 if result.get("passed") else 1
        if args.command == "collision-reproduce":
            payload = cmd_collision_reproduce(
                Path(args.source_dir).resolve(), Path(args.output_dir).resolve(), args.mode
            )
            return 0 if payload["passed"] else 1
        if args.command == "summarize":
            result = cmd_summarize(args.run_id, args.mode)
            return 0 if result.get("passed") else 1
        if args.command == "report":
            cmd_report(args.run_id)
            return 0
        if args.command == "specs-diff":
            return 0 if cmd_specs_diff(args.left, args.right, args.label, args.episode_scope)["passed"] else 1
        if args.command == "compare":
            payload = cmd_compare(
                Path(args.left).resolve(), Path(args.right).resolve(), args.label,
                subset_only=args.subset_only,
            )
            if args.out:
                _write_json(Path(args.out), payload)
            return 0 if payload["passed"] else 1
    except CampaignError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
