"""母 seed 清单：每任务选 2 个母 episode/seed（计划 R11、四.7 表与逐任务续审）。

选法（确定性）：
1. 候选来自官方 train metadata（``src/robomme/env_metadata/train/record_dataset_<Task>_metadata.json``
   的 ``records[*].episode/seed/difficulty``），difficulty 须等于 ``SOURCE_DIFFICULTY[task]``
   （VideoRepick 为 medium，其余 hard）。
2. 只取计划“固定配置参照子集”里的 episode（原本就符合 1.0 倍固定母配置的样本，见
   ``REFERENCE_SUBSETS``）；MoveCube、InsertPeg 无旋钮，取该来源难度全体。
3. 只取 episode >= ``MIN_EPISODE``（R11：生成器对 episode 0–5 加 robomme_failure_recovery，先避开）。
4. 按 episode 升序取前两个：rank 0 为较小者（锁定给最终版），rank 1 为另一个。

不足 2 个时响亮失败，不自行放宽口径。

可选只读核验：若 ``/data/hongzefu/data_0226/record_dataset_<Task>.h5`` 可读，只读打开
``episode_<n>/setup/seed`` 与 ``setup/difficulty`` 与 metadata 比对（不读图像）；读不到记 ``unverified``。

用法::

    python -m robomme_xhard.tools.mother_seeds --out <json>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ..configs import SOURCE_DIFFICULTY, TASK_ORDER

# R11：生成器 EpisodeJob.recovery_mode 对 episode <= 5 加 FailRecover，母 seed 从 6 起选
MIN_EPISODE = 6
PER_TASK = 2

# 计划（1006-xhard12-env-plan.html）第二部分“逐任务续审”各任务末尾
# “固定配置参照子集 n=…，episode=…”逐字抄录；None 表示该任务无旋钮、取来源难度全体。
REFERENCE_SUBSETS: dict[str, tuple[int, ...] | None] = {
    "BinFill": (3, 7, 15, 19, 23, 31, 47, 51, 83, 87),
    "PickXtimes": (7, 11, 19, 23, 27, 39, 43, 55, 67, 87, 91, 95, 99),
    "SwingXtimes": (3, 7, 11, 15, 19, 23, 27, 31, 35, 39, 43, 47, 51, 55, 59, 63, 67, 71, 75, 79, 83, 87, 91, 95, 99),
    "StopCube": (59, 83, 87),
    "VideoUnmask": (3, 7, 11, 15, 19, 23, 27, 31, 35, 39, 43, 47, 51, 55, 59, 63, 67, 71, 75, 79, 83, 87, 91, 95, 99),
    "ButtonUnmask": (3, 7, 11, 15, 19, 23, 27, 31, 35, 39, 43, 47, 51, 55, 59, 63, 67, 71, 75, 79, 83, 87, 91, 95, 99),
    "VideoUnmaskSwap": (7, 11, 19, 23, 31, 35, 39, 43, 67, 75, 91, 95, 99),
    "ButtonUnmaskSwap": (7, 27, 31, 35, 39, 43, 51, 59, 63, 67, 83, 91, 99),
    "PickHighlight": (3, 7, 11, 15, 19, 23, 27, 31, 35, 39, 43, 47, 51, 55, 59, 63, 67, 71, 75, 79, 83, 87, 91, 95, 99),
    "VideoRepick": (2, 46, 86, 90),
    "VideoPlaceButton": (3, 7, 11, 15, 19, 23, 27, 31, 35, 39, 43, 47, 51, 55, 59, 63, 67, 71, 75, 79, 83, 87, 91, 95, 99),
    "VideoPlaceOrder": (7, 15, 19, 31, 47, 67, 95),
    "MoveCube": None,
    "InsertPeg": None,
    "PatternLock": (7, 15, 27, 31, 43),
    "RouteStick": (3, 7, 39, 47, 51, 63, 95),
}

# 计划逐任务续审写明的 n，用来防抄录错
REFERENCE_SUBSET_SIZES: dict[str, int] = {
    "BinFill": 10,
    "PickXtimes": 13,
    "SwingXtimes": 25,
    "StopCube": 3,
    "VideoUnmask": 25,
    "ButtonUnmask": 25,
    "VideoUnmaskSwap": 13,
    "ButtonUnmaskSwap": 13,
    "PickHighlight": 25,
    "VideoRepick": 4,
    "VideoPlaceButton": 25,
    "VideoPlaceOrder": 7,
    "PatternLock": 5,
    "RouteStick": 7,
}

DEFAULT_METADATA_DIR = Path(__file__).resolve().parents[2] / "robomme" / "env_metadata" / "train"
DEFAULT_OFFICIAL_DIR = Path("/data/hongzefu/data_0226")


class MotherSeedError(RuntimeError):
    """候选不足或 metadata 与计划口径矛盾。"""


def load_records(metadata_dir: Path, task: str) -> list[dict]:
    path = Path(metadata_dir) / f"record_dataset_{task}_metadata.json"
    with open(path, encoding="utf-8") as handle:
        payload = json.load(handle)
    records = payload["records"]
    for rec in records:
        for key in ("episode", "seed", "difficulty"):
            if key not in rec:
                raise MotherSeedError(f"{path}: 记录缺字段 {key}: {rec}")
    return records


def select_task(task: str, records: list[dict]) -> list[dict]:
    """对单个任务按确定性规则选 PER_TASK 个母 episode。"""
    source = SOURCE_DIFFICULTY[task]
    by_episode = {int(r["episode"]): r for r in records}
    subset = REFERENCE_SUBSETS[task]
    if subset is None:
        candidates = sorted(int(r["episode"]) for r in records if r["difficulty"] == source)
    else:
        candidates = []
        for ep in sorted(subset):
            rec = by_episode.get(ep)
            if rec is None:
                raise MotherSeedError(f"{task}: 参照子集 episode {ep} 不在 metadata 里")
            if rec["difficulty"] != source:
                raise MotherSeedError(
                    f"{task}: 参照子集 episode {ep} 的 difficulty={rec['difficulty']!r}，应为 {source!r}"
                )
            candidates.append(ep)
    eligible = [ep for ep in candidates if ep >= MIN_EPISODE]
    if len(eligible) < PER_TASK:
        raise MotherSeedError(
            f"{task}: 参照子集内 episode>={MIN_EPISODE} 的只有 {eligible}，不足 {PER_TASK} 个（不自行放宽口径）"
        )
    chosen = []
    for rank, ep in enumerate(eligible[:PER_TASK]):
        rec = by_episode[ep]
        chosen.append(
            {
                "episode": ep,
                "seed": int(rec["seed"]),
                "source_difficulty": source,
                "rank": rank,
            }
        )
    return chosen


def _decode(value):
    if isinstance(value, bytes):
        return value.decode("utf-8")
    if hasattr(value, "item"):
        value = value.item()
        if isinstance(value, bytes):
            return value.decode("utf-8")
    return value


def verify_against_official(official_dir: Path, task: str, entries: list[dict]) -> None:
    """只读核对官方 H5 的 setup/seed 与 setup/difficulty；结果写进每条的 verify 字段。"""
    path = Path(official_dir) / f"record_dataset_{task}.h5"
    try:
        import h5py

        handle = h5py.File(path, "r")
    except Exception as exc:  # 读不到不失败
        for entry in entries:
            entry["verify"] = f"unverified: {type(exc).__name__}"
        return
    with handle:
        for entry in entries:
            group_name = f"episode_{entry['episode']}"
            try:
                setup = handle[group_name]["setup"]
                seed = int(_decode(setup["seed"][()]))
                difficulty = _decode(setup["difficulty"][()])
            except Exception as exc:
                entry["verify"] = f"unverified: {type(exc).__name__}"
                continue
            problems = []
            if seed != entry["seed"]:
                problems.append(f"seed {seed}!={entry['seed']}")
            if difficulty != entry["source_difficulty"]:
                problems.append(f"difficulty {difficulty}!={entry['source_difficulty']}")
            entry["verify"] = "match" if not problems else "mismatch: " + "; ".join(problems)


def build_manifest(
    metadata_dir: Path = DEFAULT_METADATA_DIR,
    official_dir: Path | None = DEFAULT_OFFICIAL_DIR,
) -> dict:
    tasks: dict[str, list[dict]] = {}
    for task in TASK_ORDER:
        entries = select_task(task, load_records(metadata_dir, task))
        if official_dir is not None:
            verify_against_official(official_dir, task, entries)
        else:
            for entry in entries:
                entry["verify"] = "unverified"
        tasks[task] = entries
    return {
        "version": 1,
        "rule": (
            f"计划固定配置参照子集（MoveCube/InsertPeg 取全体）∩ difficulty=SOURCE_DIFFICULTY ∩ "
            f"episode>={MIN_EPISODE}（R11），episode 升序前 {PER_TASK} 个；rank 0 锁定给最终版"
        ),
        "metadata_dir": str(metadata_dir),
        "verify_source": str(official_dir) if official_dir is not None else None,
        "tasks": tasks,
    }


def check_manifest(manifest: dict) -> tuple[bool, int, int]:
    """返回 (是否通过, seed 数, 最小 episode)。"""
    entries = [e for task in TASK_ORDER for e in manifest["tasks"].get(task, [])]
    ok = (
        list(manifest["tasks"]) == list(TASK_ORDER)
        and len(entries) == PER_TASK * len(TASK_ORDER)
        and all(e["episode"] >= MIN_EPISODE for e in entries)
        and sum(e["rank"] == 0 for e in entries) == len(TASK_ORDER)
        and sum(e["rank"] == 1 for e in entries) == len(TASK_ORDER)
    )
    min_episode = min((e["episode"] for e in entries), default=-1)
    return ok, len(entries), min_episode


def load_manifest(path: Path) -> dict:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成 xhard 母 seed 清单（只读 metadata 与官方 H5）")
    parser.add_argument("--out", required=True, help="输出 JSON 路径")
    parser.add_argument("--metadata-dir", default=str(DEFAULT_METADATA_DIR))
    parser.add_argument("--official-dir", default=str(DEFAULT_OFFICIAL_DIR), help="只读核验用官方 H5 目录")
    parser.add_argument("--no-verify", action="store_true", help="跳过官方 H5 只读核验")
    args = parser.parse_args(argv)

    manifest = build_manifest(
        Path(args.metadata_dir),
        None if args.no_verify else Path(args.official_dir),
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    for task in TASK_ORDER:
        for e in manifest["tasks"][task]:
            print(f"{task}\tep={e['episode']}\tseed={e['seed']}\trank={e['rank']}\t{e['source_difficulty']}\t{e['verify']}")
    ok, n, min_ep = check_manifest(manifest)
    verified = sum(e["verify"] == "match" for t in TASK_ORDER for e in manifest["tasks"][t])
    print(f"MOTHER_SEED_VERIFY=INFO match={verified} total={n}")
    print(f"XHARD_MOTHER_NO_FAILRECOVER={'PASS' if ok else 'FAIL'} seeds={n} min_episode={min_ep}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
