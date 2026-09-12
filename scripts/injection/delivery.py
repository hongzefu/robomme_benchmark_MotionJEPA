"""每 env 400 条 h5 的交付配置与交付清单（delivery manifest）。

本模块只回答两个问题：

* **要跑多少条** —— 由 ``scripts/configs/newtask-v2/delivery_400.json`` 声明：每个 env（任务）
  交付 ``per_env_target`` 条 h5，按难度平均（4 档 env 每档 100；3 档 env 按契约组序 134/133/133），
  实跑条数 ``run_episodes = ceil(target_h5 × margin)`` 留失败余量，另有 ``extra_candidates``
  条只做 env-check、不出 h5 的额外候选；``blocks × GROUP_SIZE`` 是这一组的候选池总量，
  必须装得下「实跑 + 额外候选」。
* **跑完之后哪几条算交付** —— :func:`build_delivery_manifest`：每组按 episode 升序，
  ``outcome == OUTCOME_PASS`` 的**前 target_h5 条**是 primary（严格交付），其余通过的是 spare
  （备件，h5 路径照样记录），非通过的进 failures。交付不足 ``target_h5`` 直接判 FAIL 并报缺口。

**这里的校验一律硬失败、不静默修正**：配置手改出与 ``margin`` 不符的 ``run_episodes``、
每 env 合计不等于 ``per_env_target``、组列表与契约组序不一致，全部抛 :class:`DeliveryError`，
避免「配置写错了但链路照跑」这种最贵的错。

本模块**不 import campaign**（campaign 反过来会用本模块），只依赖 ``.contract`` / ``.sampling`` / ``.run``。
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import math
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

from .contract import Contract
from .run import OUTCOME_PASS
from .sampling import GROUP_SIZE

#: 本模块认得的交付配置格式版本。
DELIVERY_CONFIG_VERSION = 1
#: ``run_episodes`` 回算时的向下松弛量：``100 × 1.15`` 在 IEEE754 下是 114.999…，
#: 直接 ``math.ceil`` 会得 115（正确），但 ``134 × 1.15`` 可能是 154.100…0002，
#: 统一减去一个极小量再取整，两侧都稳。
CEIL_EPSILON = 1e-9
#: failures 里 error 文本保留的字符数。
ERROR_SNIPPET = 200


class DeliveryError(RuntimeError):
    """交付配置格式错误、与契约不一致，或清单构建时的硬失败。"""


# ── 配置 ────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class DeliveryGroup:
    """一个 (task, difficulty) 组的交付口径。"""

    task: str
    difficulty: str
    target_h5: int
    run_episodes: int
    blocks: int
    extra_candidates: int

    @property
    def candidates(self) -> int:
        """候选池总量：``blocks × GROUP_SIZE``（规格生成的条数上限）。"""
        return self.blocks * GROUP_SIZE

    @property
    def run_range(self) -> range:
        """实跑的 episode 号（0 起连续）。"""
        return range(self.run_episodes)

    @property
    def env_check_start(self) -> int:
        """额外候选（只做 env-check、不出 h5）的起始 episode 号。"""
        return self.run_episodes

    @property
    def key(self) -> tuple[str, str]:
        return (self.task, self.difficulty)


@dataclass
class DeliveryConfig:
    """一份交付配置文件的解析结果。"""

    path: Path
    sha256: str
    per_env_target: int
    margin: float
    extra_candidates: int
    contract_path: str
    contract_sha256: str
    groups: list[DeliveryGroup] = field(default_factory=list)

    def group(self, task: str, difficulty: str) -> DeliveryGroup:
        for item in self.groups:
            if item.key == (task, difficulty):
                return item
        raise DeliveryError(f"交付配置里没有组 {task}/{difficulty}")

    def by_env(self) -> dict[str, list[DeliveryGroup]]:
        """按 env（任务）聚合，env 之间与 env 内部都保持配置里的出现顺序。"""
        result: dict[str, list[DeliveryGroup]] = {}
        for item in self.groups:
            result.setdefault(item.task, []).append(item)
        return result

    def episodes_by_group(
        self, groups: Sequence[tuple[str, str]] | None = None
    ) -> dict[tuple[str, str], list[int]]:
        """每组的实跑 episode 列表；``groups`` 给定时只取这几组（顺序照给定的来）。"""
        keys = list(groups) if groups is not None else [item.key for item in self.groups]
        return {
            (task, difficulty): list(self.group(task, difficulty).run_range)
            for task, difficulty in keys
        }

    def blocks_by_group(self) -> dict[tuple[str, str], int]:
        return {item.key: item.blocks for item in self.groups}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise DeliveryError(message)


def expected_run_episodes(target_h5: int, margin: float) -> int:
    """``ceil(target × margin)``，先减去 :data:`CEIL_EPSILON` 抵消浮点误差。"""
    return math.ceil(target_h5 * margin - CEIL_EPSILON)


def load_delivery_config(path: Path, contract: Contract | None = None) -> DeliveryConfig:
    """读取并**硬校验**交付配置；任一条不满足直接抛 :class:`DeliveryError`。

    给了 ``contract`` 时额外校验：组列表与 ``contract.groups()`` 同序同名，且契约散列一致。
    """
    target = Path(path)
    _require(target.is_file(), f"交付配置文件不存在：{target}")
    raw = target.read_bytes()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:  # pragma: no cover - 格式错误路径
        raise DeliveryError(f"{target}: JSON 无法解析：{exc}") from exc
    _require(isinstance(payload, dict), "交付配置顶层必须是对象")

    version = payload.get("config_version")
    _require(
        version == DELIVERY_CONFIG_VERSION,
        f"config_version 必须为 {DELIVERY_CONFIG_VERSION}，收到 {version!r}",
    )
    for key in ("contract_path", "contract_sha256", "per_env_target", "margin", "extra_candidates", "groups"):
        _require(key in payload, f"交付配置缺少顶层字段 {key!r}")

    per_env_target = int(payload["per_env_target"])
    margin = float(payload["margin"])
    extra_candidates = int(payload["extra_candidates"])
    _require(per_env_target > 0, "per_env_target 必须为正")
    _require(margin >= 1.0, f"margin 必须 ≥ 1.0，收到 {margin}")
    _require(extra_candidates >= 0, "extra_candidates 不能为负")

    raw_groups = payload["groups"]
    _require(isinstance(raw_groups, list) and raw_groups, "groups 必须是非空数组")

    groups: list[DeliveryGroup] = []
    seen: set[tuple[str, str]] = set()
    for item in raw_groups:
        _require(isinstance(item, dict), f"groups 的元素必须是对象：{item!r}")
        for key in ("task", "difficulty", "target_h5", "run_episodes", "blocks"):
            _require(key in item, f"组 {item.get('task')}/{item.get('difficulty')} 缺少字段 {key!r}")
        group = DeliveryGroup(
            task=str(item["task"]),
            difficulty=str(item["difficulty"]),
            target_h5=int(item["target_h5"]),
            run_episodes=int(item["run_episodes"]),
            blocks=int(item["blocks"]),
            extra_candidates=extra_candidates,
        )
        _require(group.key not in seen, f"组 {group.task}/{group.difficulty} 重复出现")
        seen.add(group.key)
        _require(group.target_h5 > 0, f"{group.task}/{group.difficulty}: target_h5 必须为正")
        _require(group.blocks >= 1, f"{group.task}/{group.difficulty}: blocks 必须 ≥ 1")
        expected = expected_run_episodes(group.target_h5, margin)
        _require(
            group.run_episodes == expected,
            f"{group.task}/{group.difficulty}: run_episodes 应为 ceil({group.target_h5}×{margin})={expected}，"
            f"收到 {group.run_episodes}",
        )
        need = group.run_episodes + extra_candidates
        _require(
            group.candidates >= need,
            f"{group.task}/{group.difficulty}: 候选池 blocks×{GROUP_SIZE}={group.candidates} "
            f"装不下实跑 {group.run_episodes} + 额外候选 {extra_candidates} = {need}",
        )
        groups.append(group)

    # 每 env 合计与档间均衡
    per_env: dict[str, list[DeliveryGroup]] = {}
    for group in groups:
        per_env.setdefault(group.task, []).append(group)
    for task, items in per_env.items():
        total = sum(item.target_h5 for item in items)
        _require(
            total == per_env_target,
            f"{task}: 各难度 target_h5 合计 {total}，应为 per_env_target={per_env_target}",
        )
        targets = [item.target_h5 for item in items]
        _require(
            max(targets) - min(targets) <= 1,
            f"{task}: 难度间 target_h5 计数差 {max(targets) - min(targets)} > 1（应按难度平均）",
        )

    config = DeliveryConfig(
        path=target,
        sha256=hashlib.sha256(raw).hexdigest(),
        per_env_target=per_env_target,
        margin=margin,
        extra_candidates=extra_candidates,
        contract_path=str(payload["contract_path"]),
        contract_sha256=str(payload["contract_sha256"]),
        groups=groups,
    )

    if contract is not None:
        contract_keys = [(g.task, g.difficulty) for g in contract.groups()]
        config_keys = [g.key for g in groups]
        _require(
            contract_keys == config_keys,
            f"交付配置组列表与契约组列表不一致：\n  配置 {config_keys}\n  契约 {contract_keys}",
        )
        _require(
            contract.sha256 == config.contract_sha256,
            f"契约散列不符：配置记 {config.contract_sha256}，实际 {contract.sha256}",
        )
    return config


# ── 交付清单 ────────────────────────────────────────────────────────────────
def _hash_file(path_text: str) -> tuple[str, int | None, str | None]:
    """子进程里算一份文件的字节数与 sha256；文件不存在返回 ``(path, None, None)``。"""
    path = Path(path_text)
    try:
        size = path.stat().st_size
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
        return (path_text, size, digest.hexdigest())
    except OSError:
        return (path_text, None, None)


def _env_check_episodes(env_check_result: dict[str, Any] | None) -> dict[tuple[str, str], set[int]]:
    """把 env-check 结果翻成 ``(task, difficulty) -> episode 集合``。

    容忍三种写法：顶层直接 ``{"任务/难度": [...]}``、包一层 ``{"groups": {...}}``、
    以及每组是 ``{"episodes": [...]}`` 而非裸列表。
    """
    if not env_check_result:
        return {}
    payload = env_check_result.get("groups", env_check_result)
    if not isinstance(payload, dict):
        raise DeliveryError("env_check_result 的 groups 必须是对象")
    result: dict[tuple[str, str], set[int]] = {}
    for raw_key, value in payload.items():
        if isinstance(raw_key, (tuple, list)) and len(raw_key) == 2:
            key = (str(raw_key[0]), str(raw_key[1]))
        else:
            task, _, difficulty = str(raw_key).partition("/")
            key = (task, difficulty)
        episodes: Iterable[Any]
        if isinstance(value, dict):
            episodes = value.get("episodes", [])
        else:
            episodes = value
        result[key] = {int(item) for item in episodes}
    return result


def _relative(path_text: str, repo_root: Path) -> str:
    try:
        return os.path.relpath(Path(path_text), repo_root)
    except ValueError:  # pragma: no cover - 跨盘符（Windows）才会走到
        return path_text


def build_delivery_manifest(
    rows: Sequence[dict[str, Any]],
    config: DeliveryConfig,
    *,
    run_id: str,
    repo_root: Path,
    env_check_result: dict[str, Any] | None = None,
    hash_mode: str = "full",
    workers: int = 8,
    spec_sha_by_key: dict[tuple[str, str, int], str] | None = None,
) -> dict[str, Any]:
    """按「每组 episode 升序取前 target_h5 条通过」的严格口径构建交付清单。

    ``rows`` 是 :func:`scripts.injection.run.read_result_rows` 的输出行，另需由调用方补上
    ``h5_path``（h5 绝对路径）与 ``timestep_count`` 两个键；本函数只用 ``row.get(...)`` 读，
    缺了不报错、记为 ``None``。

    ``hash_mode``：``"full"`` 用进程池并行算 sha256 与字节数；``"size-only"`` 只 stat 字节数；
    ``"none"`` 两者都不算（单元测试与快速预览用）。
    """
    if hash_mode not in ("full", "size-only", "none"):
        raise DeliveryError(f"未知的 hash_mode {hash_mode!r}（可选 full / size-only / none）")
    repo_root = Path(repo_root)
    env_checked = _env_check_episodes(env_check_result)

    by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        key = (str(row.get("task")), str(row.get("difficulty")))
        by_key.setdefault(key, []).append(row)

    # 第一遍：分好 primary / spare / failures，收集待散列的 h5 路径
    group_payloads: dict[str, dict[str, Any]] = {}
    pending_paths: set[str] = set()
    for group in config.groups:
        group_rows = sorted(by_key.get(group.key, []), key=lambda item: int(item.get("episode", -1)))
        primary: list[dict[str, Any]] = []
        spare: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []
        checked = env_checked.get(group.key, set())
        for row in group_rows:
            episode = int(row.get("episode", -1))
            if row.get("outcome") != OUTCOME_PASS:
                item = {
                    "episode": episode,
                    "outcome": row.get("outcome"),
                    "error_type": row.get("error_type"),
                    "error": (row.get("error") or "")[:ERROR_SNIPPET],
                }
                if episode in checked:
                    item["also_env_checked"] = True
                failures.append(item)
                continue
            role = "primary" if len(primary) < group.target_h5 else "spare"
            h5_path = row.get("h5_path")
            entry = {
                "task": group.task,
                "difficulty": group.difficulty,
                "episode": episode,
                "seed": row.get("seed"),
                "spec_sha256": (spec_sha_by_key or {}).get((group.task, group.difficulty, episode)),
                "h5_path": _relative(str(h5_path), repo_root) if h5_path else None,
                "bytes": None,
                "sha256": None,
                "timestep_count": row.get("timestep_count"),
                "video_status": row.get("video_status"),
                "role": role,
            }
            if h5_path:
                entry["_abs_h5"] = str(h5_path)
                if hash_mode != "none":
                    pending_paths.add(str(h5_path))
            else:
                entry["h5_missing"] = True
            if episode in checked:
                entry["also_env_checked"] = True
            (primary if role == "primary" else spare).append(entry)

        group_payloads[f"{group.task}/{group.difficulty}"] = {
            "target_h5": group.target_h5,
            "run_episodes": group.run_episodes,
            "rows": len(group_rows),
            "passed": len(primary) + len(spare),
            "delivered": len(primary),
            "spare": len(spare),
            "failed": len(failures),
            "primary": primary,
            "spare_rows": spare,
            "failures": failures,
        }

    # 第二遍：算字节数与散列
    stats: dict[str, tuple[int | None, str | None]] = {}
    if hash_mode == "full" and pending_paths:
        ordered = sorted(pending_paths)
        max_workers = max(1, min(int(workers), len(ordered)))
        with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as pool:
            for path_text, size, digest in pool.map(_hash_file, ordered):
                stats[path_text] = (size, digest)
    elif hash_mode == "size-only":
        for path_text in pending_paths:
            try:
                stats[path_text] = (Path(path_text).stat().st_size, None)
            except OSError:
                stats[path_text] = (None, None)

    h5_missing = 0
    for payload in group_payloads.values():
        for entry in [*payload["primary"], *payload["spare_rows"]]:
            abs_path = entry.pop("_abs_h5", None)
            if abs_path is None:
                h5_missing += 1
                continue
            if hash_mode == "none":
                # none 模式完全不碰磁盘：bytes/sha256 留 None，也不判文件在不在
                continue
            size, digest = stats.get(abs_path, (None, None))
            entry["bytes"] = size
            entry["sha256"] = digest
            if size is None:
                entry["h5_missing"] = True
                h5_missing += 1

    # env 汇总、缺口与判定行
    envs: dict[str, dict[str, Any]] = {}
    shortfall: list[dict[str, Any]] = []
    verdicts: list[dict[str, Any]] = []
    for task, items in config.by_env().items():
        keys = [f"{item.task}/{item.difficulty}" for item in items]
        delivered = sum(group_payloads[key]["delivered"] for key in keys)
        spare = sum(group_payloads[key]["spare"] for key in keys)
        failed = sum(group_payloads[key]["failed"] for key in keys)
        envs[task] = {
            "target": config.per_env_target,
            "delivered": delivered,
            "spare": spare,
            "failed": failed,
            "groups": keys,
        }
        for group, key in zip(items, keys):
            missing = group.target_h5 - group_payloads[key]["delivered"]
            if missing > 0:
                shortfall.append(
                    {
                        "env": task,
                        "group": key,
                        "missing": missing,
                        "remaining_candidates": group.candidates - group.run_episodes,
                    }
                )
        verdicts.append(
            {
                "name": "DELIVERY_400",
                "passed": delivered >= config.per_env_target,
                "fields": {
                    "env": task,
                    "target": config.per_env_target,
                    "delivered": delivered,
                    "spare": spare,
                    "failed": failed,
                    "groups": len(keys),
                },
            }
        )

    total_delivered = sum(item["delivered"] for item in envs.values())
    total_spare = sum(item["spare"] for item in envs.values())
    total_target = config.per_env_target * len(envs)
    verdicts.append(
        {
            "name": "DELIVERY_TOTAL",
            "passed": total_delivered >= total_target,
            "fields": {
                "envs": len(envs),
                "delivered": total_delivered,
                "spare": total_spare,
                "h5_missing": h5_missing,
                # 本轮不与旧散列比对，恒 0 占位；将来接 h5_compare 时填实数
                "h5_sha_mismatch": 0,
            },
        }
    )

    return {
        "run_id": run_id,
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "config": {
            "path": str(config.path),
            "sha256": config.sha256,
            "per_env_target": config.per_env_target,
            "margin": config.margin,
            "extra_candidates": config.extra_candidates,
        },
        "hash_mode": hash_mode,
        "envs": envs,
        "groups": group_payloads,
        "shortfall": shortfall,
        "verdicts": verdicts,
        "passed": all(item["passed"] for item in verdicts),
    }


def render_verdict_line(verdict: dict[str, Any]) -> str:
    """判定行渲染成 ``NAME=PASS k=v k=v``（与 campaign 的 ``Verdicts`` 同式）。"""
    status = "PASS" if verdict.get("passed") else "FAIL"
    fields = " ".join(f"{key}={value}" for key, value in (verdict.get("fields") or {}).items())
    return f"{verdict['name']}={status}" + (f" {fields}" if fields else "")
