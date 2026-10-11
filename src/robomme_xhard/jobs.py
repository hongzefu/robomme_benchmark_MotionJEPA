"""xhard 作业展开：由母 seed 清单展开“任务 × 母 seed × difficulty”卡片（纯函数，可在 CPU 上测）。

本模块只读 ``configs`` 的公共契约，不 import gym / mani_skill，不起仿真。生成器
``scripts/data-generation-newSeed/generate_dataset_newseed.py`` 在父进程里调用这里的函数，
再把卡片转成自己的 ``EpisodeJob`` 交给进程池。

母 seed 清单格式（S4 产出，本模块校验）::

    {"version": 1,
     "tasks": {"<Task>": [{"episode": <int>, "seed": <int>,
                           "source_difficulty": "hard"|"medium", "rank": 0|1}, ...]}}

卡片身份 = (task, mother_episode, seed, difficulty)；attempt 恒为 0，失败不换 seed（RL3）。
xhard 卡写 ``<output>/<difficulty>/``，母卡写 ``<output>/mother/``（RL9）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .configs import DIFFICULTIES, SOURCE_DIFFICULTY, TASK_ORDER, TIER_CONFIGS, env_name

MANIFEST_VERSION = 1
MOTHER_SUBDIR = "mother"
ROLE_XHARD = "xhard"
ROLE_MOTHER = "mother"
VALID_RANKS = (0, 1)


class XHardJobError(ValueError):
    """xhard 作业参数或母 seed 清单不合约定。"""


@dataclass(frozen=True)
class XHardCard:
    """一张生成卡片。xhard 卡 difficulty 为 xhard 值；母卡 difficulty 等于 source_difficulty。"""

    task: str
    mother_episode: int
    seed: int
    difficulty: str
    source_difficulty: str
    role: str
    rank: int
    attempt: int = 0

    @property
    def identity(self) -> tuple[str, int, int, str]:
        return (self.task, self.mother_episode, self.seed, self.difficulty)

    @property
    def subdir(self) -> str:
        return self.difficulty if self.role == ROLE_XHARD else MOTHER_SUBDIR


def make_name(card: XHardCard) -> str:
    """gym.make 用的名字：xhard 卡为 ``<Task>XHard``，母卡为原任务名。"""
    if card.role == ROLE_XHARD:
        return env_name(card.task)
    if card.role == ROLE_MOTHER:
        return card.task
    raise XHardJobError(f"未知卡片角色 {card.role!r}")


def card_output_root(output: str | Path, card: XHardCard) -> Path:
    """卡片的输出根：xhard 卡按档分目录，母卡统一进 mother/。"""
    return Path(output) / card.subdir


def looks_like_xhard(value: str | None) -> bool:
    """--difficulty 的取值里是否出现 xhard 字面值（用于判断是否进入 xhard 模式）。"""
    if not isinstance(value, str):
        return False
    return any(item.strip().lower().startswith("xhard") for item in value.split(","))


def parse_difficulties(value: str) -> tuple[str, ...]:
    """解析逗号分隔的 xhard 列表；与旧比例参数混用、未知值、重复值一律报错。

    返回值按 ``DIFFICULTIES`` 的顺序排列。
    """
    if not isinstance(value, str) or not value.strip():
        raise XHardJobError("--difficulty 不能为空")
    items = [item.strip().lower() for item in value.split(",")]
    if any(not item for item in items):
        raise XHardJobError(f"--difficulty 含空项：{value!r}")
    non_xhard = [item for item in items if not item.startswith("xhard")]
    if non_xhard:
        raise XHardJobError(
            f"--difficulty 不能把 xhard 值与旧比例参数混用：{value!r}（非 xhard 项 {non_xhard}）"
        )
    unknown = [item for item in items if item not in DIFFICULTIES]
    if unknown:
        raise XHardJobError(f"未知 xhard difficulty {unknown}，可选 {DIFFICULTIES}")
    if len(items) != len(set(items)):
        raise XHardJobError(f"--difficulty 有重复项：{value!r}")
    return tuple(d for d in DIFFICULTIES if d in items)


def _strict_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def validate_manifest(data: Any) -> dict[str, list[dict[str, Any]]]:
    """校验母 seed 清单，返回 {task: [entry, ...]}（按 rank、episode 排序的拷贝）。"""
    if not isinstance(data, Mapping):
        raise XHardJobError("母 seed 清单顶层必须是对象")
    if data.get("version") != MANIFEST_VERSION:
        raise XHardJobError(f"母 seed 清单 version 必须为 {MANIFEST_VERSION}，收到 {data.get('version')!r}")
    tasks = data.get("tasks")
    if not isinstance(tasks, Mapping) or not tasks:
        raise XHardJobError("母 seed 清单缺少非空的 tasks 对象")
    result: dict[str, list[dict[str, Any]]] = {}
    for task, entries in tasks.items():
        if task not in TASK_ORDER:
            raise XHardJobError(f"母 seed 清单含未知任务 {task!r}")
        if not isinstance(entries, list) or not entries:
            raise XHardJobError(f"{task}: 母条目必须是非空列表")
        seen_ranks: set[int] = set()
        seen_episodes: set[int] = set()
        cleaned: list[dict[str, Any]] = []
        for index, entry in enumerate(entries):
            where = f"{task}[{index}]"
            if not isinstance(entry, Mapping):
                raise XHardJobError(f"{where}: 母条目必须是对象")
            missing = [key for key in ("episode", "seed", "source_difficulty", "rank") if key not in entry]
            if missing:
                raise XHardJobError(f"{where}: 缺少字段 {missing}")
            episode, seed, source, rank = (
                entry["episode"],
                entry["seed"],
                entry["source_difficulty"],
                entry["rank"],
            )
            if not _strict_int(episode) or episode < 0:
                raise XHardJobError(f"{where}: episode 必须是非负整数，收到 {episode!r}")
            if not _strict_int(seed) or seed < 0:
                raise XHardJobError(f"{where}: seed 必须是非负整数，收到 {seed!r}")
            if not _strict_int(rank) or rank not in VALID_RANKS:
                raise XHardJobError(f"{where}: rank 必须是 {VALID_RANKS} 之一，收到 {rank!r}")
            if source != SOURCE_DIFFICULTY[task]:
                raise XHardJobError(
                    f"{where}: source_difficulty 应为 {SOURCE_DIFFICULTY[task]!r}，收到 {source!r}"
                )
            if rank in seen_ranks:
                raise XHardJobError(f"{where}: rank {rank} 重复")
            if episode in seen_episodes:
                raise XHardJobError(f"{where}: episode {episode} 重复")
            seen_ranks.add(rank)
            seen_episodes.add(episode)
            cleaned.append({"episode": episode, "seed": seed, "source_difficulty": source, "rank": rank})
        result[task] = sorted(cleaned, key=lambda item: (item["rank"], item["episode"]))
    return result


def load_manifest(path: str | Path) -> dict[str, list[dict[str, Any]]]:
    """读取并校验母 seed 清单文件。"""
    manifest_path = Path(path)
    if not manifest_path.is_file():
        raise XHardJobError(f"母 seed 清单不存在：{manifest_path}")
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise XHardJobError(f"母 seed 清单不是合法 JSON：{manifest_path}：{exc}") from None
    return validate_manifest(data)


def expand_cards(
    manifest: Mapping[str, Sequence[Mapping[str, Any]]],
    difficulties: Iterable[str],
    tasks: Iterable[str] | None = None,
    with_mother: bool = False,
    mother_rank: int | None = None,
) -> list[XHardCard]:
    """展开卡片。

    * 对清单里每个 (task, 母条目) × 每个请求的 difficulty，(task, difficulty) 在 TIER_CONFIGS
      里才出卡；缺档不出卡、不复制邻档。
    * ``with_mother`` 时每个母条目另出一张母卡（原任务名、difficulty=source_difficulty）。
    * ``tasks`` 为 None 取清单全部任务；给定时只取交集，给定但清单里没有的任务报错。
    * ``mother_rank`` 给定时只取该 rank 的母条目；某任务没有该 rank 报错。
    * 排序：官网任务顺序 → difficulty 顺序（母卡排最前）→ rank → mother_episode。
    """
    if isinstance(manifest, Mapping) and "version" in manifest:
        manifest = validate_manifest(manifest)
    requested = tuple(difficulties)
    for label in requested:
        if label not in DIFFICULTIES:
            raise XHardJobError(f"未知 xhard difficulty {label!r}，可选 {DIFFICULTIES}")
    if len(requested) != len(set(requested)):
        raise XHardJobError(f"difficulty 有重复项：{requested}")
    if not requested and not with_mother:
        raise XHardJobError("既没有请求 xhard 档也没有 --with-mother，没有可生成的卡片")
    if mother_rank is not None and (not _strict_int(mother_rank) or mother_rank not in VALID_RANKS):
        raise XHardJobError(f"mother_rank 必须是 {VALID_RANKS} 之一，收到 {mother_rank!r}")

    if tasks is None:
        selected = [task for task in TASK_ORDER if task in manifest]
    else:
        wanted = list(tasks)
        absent = [task for task in wanted if task not in manifest]
        if absent:
            raise XHardJobError(f"母 seed 清单里没有这些任务：{absent}")
        selected = [task for task in TASK_ORDER if task in wanted]

    cards: list[XHardCard] = []
    for task in selected:
        entries = list(manifest[task])
        if mother_rank is not None:
            entries = [entry for entry in entries if entry["rank"] == mother_rank]
            if not entries:
                raise XHardJobError(f"{task}: 母 seed 清单里没有 rank={mother_rank} 的条目")
        for entry in entries:
            source = str(entry["source_difficulty"])
            if with_mother:
                cards.append(
                    XHardCard(
                        task=task,
                        mother_episode=int(entry["episode"]),
                        seed=int(entry["seed"]),
                        difficulty=source,
                        source_difficulty=source,
                        role=ROLE_MOTHER,
                        rank=int(entry["rank"]),
                    )
                )
            for label in requested:
                if label not in TIER_CONFIGS.get(task, {}):
                    continue
                cards.append(
                    XHardCard(
                        task=task,
                        mother_episode=int(entry["episode"]),
                        seed=int(entry["seed"]),
                        difficulty=label,
                        source_difficulty=source,
                        role=ROLE_XHARD,
                        rank=int(entry["rank"]),
                    )
                )

    def order(card: XHardCard) -> tuple[int, int, int, int]:
        diff_index = -1 if card.role == ROLE_MOTHER else DIFFICULTIES.index(card.difficulty)
        return (TASK_ORDER.index(card.task), diff_index, card.rank, card.mother_episode)

    cards.sort(key=order)
    identities = [card.identity for card in cards]
    if len(identities) != len(set(identities)):
        raise XHardJobError("卡片身份 (task, mother_episode, seed, difficulty) 出现重复")
    return cards
