"""候选阶段的交付配置校验，沿用原字段与配额约束。"""
from __future__ import annotations
import hashlib
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence
from .contract import Contract
from .sampling import GROUP_SIZE
DELIVERY_CONFIG_VERSION = 1
CEIL_EPSILON = 1e-9

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
