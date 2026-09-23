#!/usr/bin/env python3
"""V4 新值规格的抽签／冻结／读取（NEWTASK_RELEASE_V4_PLAN 第三节 3.2～3.4，步 4）。

三件事、两个文件：

* ``draw``（占 GPU）：拿 xhard 的范围开环境，**只 reset、不 step、不录像**，把 ``SpecRecorder`` 导出的
  每局规格写进 ``drafts.jsonl``（含失败尝试）。每环境攒够 ``--candidates-per-env`` 条 reset 成功
  或尝试满 ``--max-reset-attempts`` 次为止。**来源在抽签时就封存**进 header（Codex 审计 #7）：
  ``sampling_config`` 全文、源码指纹、runtime 四项、seed 规则。
* ``freeze``（纯 CPU）：先核验 drafts header 封存的来源与当前磁盘**逐项一致**（不一致拒绝），
  只留 reset 成功的行，每环境按 index ``--select`` 标 ``selected=true``，算每行 ``spec_sha256`` 与
  整文件 ``identity_sha256``，写出 ``specs.jsonl``；已存在拒绝覆盖。
* ``load_specs()``：实跑段与推理侧唯一的读取入口，校验全部封套后返回
  ``(header, sampling_by_task, specs_by_identity)``（后者只含 ``selected=true``）。

封套沿用链路甲的纯函数（``scripts/injection/candidates/io.py`` 的 ``canonical_json`` / ``digest``），
**不复用甲的 identity_sha256**：甲的 ``_MUTABLE`` 不含 ``selected``，直接用会让「改选择就改身份」
（Codex 审计 #6）。本模块先剔除管理字段再调 ``digest``。

    uv run --no-sync python -m scripts.parity.v4_specs draw --run-id <id> --out artifacts/newtask-v4/<id>/draft/drafts.jsonl
    uv run --no-sync python -m scripts.parity.v4_specs freeze --drafts <drafts.jsonl> --out scripts/configs/newtask-v4/<id>/specs.jsonl
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import sys
import tempfile
import time
import traceback
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
for extra in (REPO_ROOT / "scripts", REPO_ROOT):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from scripts.injection.candidates.io import canonical_json, digest  # noqa: E402  甲的纯函数，只读复用
from seed_layout import ALL_TASKS, SeedLayout, env_code  # noqa: E402

DEFAULT_SAMPLING = REPO_ROOT / "scripts" / "configs" / "newtask-v4" / "sampling_config.json"
SOURCE_ROOT = REPO_ROOT / "src" / "robomme" / "robomme_env"
DRAFT_SCHEMA = "v4-drafts/1"
SPECS_SCHEMA = "v4-specs/1"
DIFFICULTY = "xhard"
# runtime 四项与主入口 / parity worker 的 gym.make 参数逐字相同（推理侧起环境时逐字比对）
RUNTIME = {
    "obs_mode": "rgb+depth+segmentation",
    "control_mode": "pd_joint_pos",
    "render_mode": "rgb_array",
    "reward_mode": "dense",
}
# V4 专用 seed 布局：与 train/test/val/heldout 四代都不重叠（heldout 最大约 1.5e6+16e5）。
# seed = offset + env_code × env_block + episode × 100 + attempt
SEED_RULE = {"offset": 4_000_000, "env_block": 100_000, "episode_stride": 100, "formula": "offset + env_code*env_block + episode*100 + attempt"}
# fail recover：用户 2026-09-22 定「V4 全部不开 recover」——抽签、实跑、推理三处一律不开。
# ⚠ recover 会改变 reset 期的抽样（inject_fail_grasp），三处必须同口径，否则回注对不上；
# 规则写进 header 封存，实跑侧（runner --no-recovery）与推理侧（from_v4_specs）按它执行。
RECOVERY_RULE = {"rule": "V4 全部不开 fail recover（用户 2026-09-22）"}
DEFAULT_SELECT = (0, 3, 6)
# 管理字段：可变、不进身份散列（改 selected 不改身份；改任一规格值必改身份）
MANAGEMENT_KEYS = {"selected", "identity_sha256", "run_id", "notes"}
DRAFT_ROW_KEYS = {"record", "task", "difficulty", "episode", "attempt", "seed", "reset_ok",
                  "fail_class", "error", "spec", "spec_sha256", "wall_s"}
SPEC_ROW_KEYS = {"record", "task", "difficulty", "episode", "attempt", "seed", "spec", "spec_sha256", "selected"}
HEADER_KEYS = {"record", "schema", "run_id", "difficulty", "sampling_config", "sampling_config_sha256",
               "source_fingerprint", "runtime", "seed_rule", "recovery_rule", "identity_source", "tasks"}
SPECS_HEADER_EXTRA = {"drafts_sha256", "select_indices", "per_env", "identity_sha256"}


class SpecsError(ValueError):
    """规格文件缺失、被篡改、来源不符或字段集合不符。"""


# ── 基础函数 ─────────────────────────────────────────────────────────────


def seed_for(task: str, episode: int, attempt: int) -> int:
    layout = SeedLayout(offset=SEED_RULE["offset"], env_block=SEED_RULE["env_block"])
    return layout.seed(task, episode, attempt)


def source_fingerprint(root: Path = SOURCE_ROOT) -> dict[str, Any]:
    """环境源码指纹：``src/robomme/robomme_env`` 下全部 .py 的相对路径与 sha256，外加总散列。"""
    files = {}
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        files[str(path.relative_to(REPO_ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"files": len(files), "sha256": digest(files)}


def recovery_mode(episode: int) -> str | None:
    """V4 一律不开 recover（RECOVERY_RULE）；保留函数形态供实跑/推理侧统一调用。"""
    return None


def env_kwargs(seed: int, episode: int) -> dict[str, Any]:
    """抽签与实跑共用的 gym.make 参数（不含 sampling_config / native_episode_spec）。"""
    kwargs = {**RUNTIME, "seed": seed, "difficulty": DIFFICULTY}
    mode = recovery_mode(episode)
    if mode is not None:
        kwargs["robomme_failure_recovery"] = True
        kwargs["robomme_failure_recovery_mode"] = mode
    return kwargs


def spec_sha256(spec: dict[str, Any]) -> str:
    return digest(spec)


def task_sampling(sampling_document: dict[str, Any], task: str) -> dict[str, Any]:
    """从 ``train_split_config extract`` 的快照里取单任务 ``{decision, native}``。"""
    block = sampling_document["tasks"][task]
    return {"decision": copy.deepcopy(block["decision"]), "native": copy.deepcopy(block["native"])}


def identity_sha256(header: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    """V4 层投影：剔除管理字段后再 digest（不改冻结的甲代码）。"""
    key = lambda row: (row["task"], row["episode"])  # noqa: E731
    return digest({
        "header": {k: v for k, v in header.items() if k not in MANAGEMENT_KEYS},
        "rows": [{k: v for k, v in row.items() if k not in MANAGEMENT_KEYS} for row in sorted(rows, key=key)],
    })


def _exact_keys(value: dict[str, Any], required: set[str], label: str) -> None:
    missing, extra = required - value.keys(), value.keys() - required
    if missing or extra:
        raise SpecsError(f"{label} 字段集合不符：缺少 {sorted(missing)}，多出 {sorted(extra)}")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise SpecsError(f"JSON 存在重复字段：{key}")
        result[key] = value
    return result


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with Path(path).open(encoding="utf-8") as stream:
        records = [json.loads(line, object_pairs_hook=_unique_object) for line in stream if line.strip()]
    if not records:
        raise SpecsError(f"{path} 为空")
    return records


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    """已存在拒绝覆盖；临时文件 + 原子改名。"""
    path = Path(path)
    if path.exists():
        raise SpecsError(f"{path} 已存在，禁止覆盖")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".v4specs-", dir=path.parent)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        for record in records:
            stream.write(canonical_json(record) + "\n")
    os.chmod(name, 0o644)  # mkstemp 默认 0600；冻结文件要进 Git、供他人读取
    os.link(name, path)  # link 在目标已存在时失败，比 rename 更能防并发覆盖
    os.unlink(name)


def _check_sources(header: dict[str, Any], sampling_document: dict[str, Any], label: str) -> None:
    """封存的来源与当前磁盘逐项比对：配置全文、源码指纹、runtime、seed 规则。"""
    problems = []
    for task in header["tasks"]:
        if header["sampling_config"].get(task) != task_sampling(sampling_document, task):
            problems.append(f"sampling_config[{task}]")
    if header["sampling_config_sha256"] != digest(header["sampling_config"]):
        problems.append("sampling_config_sha256 与内嵌配置不自洽")
    if header["source_fingerprint"] != source_fingerprint():
        problems.append("source_fingerprint")
    if header["runtime"] != RUNTIME:
        problems.append("runtime")
    if header["seed_rule"] != SEED_RULE:
        problems.append("seed_rule")
    if header["recovery_rule"] != RECOVERY_RULE:
        problems.append("recovery_rule")
    if problems:
        raise SpecsError(f"{label}：封存的来源与当前磁盘不一致：{problems}")


# ── 抽签 ───────────────────────────────────────────────────────────────


def _draw_one(task: str, seed: int, episode: int, sampling: dict[str, Any]) -> tuple[bool, dict | None, str | None, str | None]:
    import gymnasium as gym

    env = None
    try:
        env = gym.make(task, sampling_config=sampling, **env_kwargs(seed, episode))
        env.reset()
        recorder = env.unwrapped._spec
        recorder.identity.update({"task": task, "seed": seed, "difficulty": DIFFICULTY,
                                  "episode": episode, "recovery_mode": recovery_mode(episode)})
        return True, recorder.to_dict(), None, None
    except Exception as exc:  # noqa: BLE001 失败本身要归类记录
        return False, None, type(exc).__name__, f"{exc}\n{traceback.format_exc(limit=4)}"[:2000]
    finally:
        if env is not None:
            env.close()


def cmd_draw(args: argparse.Namespace) -> int:
    sys.path.insert(0, str(REPO_ROOT / "src"))
    import robomme.robomme_env  # noqa: F401 注册环境

    sampling_document = json.loads(Path(args.sampling_config).read_text(encoding="utf-8"))
    tasks = list(ALL_TASKS) if args.tasks == "all" else args.tasks.split(",")
    header = {
        "record": "header",
        "schema": DRAFT_SCHEMA,
        "run_id": args.run_id,
        "difficulty": DIFFICULTY,
        "sampling_config": {task: task_sampling(sampling_document, task) for task in tasks},
        "source_fingerprint": source_fingerprint(),
        "runtime": dict(RUNTIME),
        "seed_rule": dict(SEED_RULE),
        "recovery_rule": copy.deepcopy(RECOVERY_RULE),
        "identity_source": "formula",
        "tasks": tasks,
    }
    header["sampling_config_sha256"] = digest(header["sampling_config"])
    out = Path(args.out)
    if out.exists():
        raise SpecsError(f"{out} 已存在，禁止覆盖")
    rows: list[dict[str, Any]] = []
    for task in tasks:
        episode = attempt = total = 0
        while episode < args.candidates_per_env and total < args.max_reset_attempts:
            seed = seed_for(task, episode, attempt)
            started = time.time()
            ok, spec, fail_class, error = _draw_one(task, seed, episode, header["sampling_config"][task])
            row = {
                "record": "draft", "task": task, "difficulty": DIFFICULTY, "episode": episode,
                "attempt": attempt, "seed": seed, "reset_ok": ok, "fail_class": fail_class,
                "error": error, "spec": spec, "spec_sha256": spec_sha256(spec) if spec else None,
                "wall_s": round(time.time() - started, 2),
            }
            rows.append(row)
            total += 1
            print(f"DRAW {task} ep={episode} attempt={attempt} seed={seed} ok={ok} {fail_class or ''}", flush=True)
            if ok:
                episode, attempt = episode + 1, 0
            else:
                attempt += 1
        print(f"DRAW_TASK {task} ok={episode} attempted={total} shortfall={args.candidates_per_env - episode}", flush=True)
    _write_jsonl(out, [header, *rows])
    print(f"DRAW_DONE rows={len(rows)} ok={sum(r['reset_ok'] for r in rows)} out={out}")
    return 0


# ── 冻结 ───────────────────────────────────────────────────────────────


def freeze(drafts_path: Path, sampling_path: Path, out: Path, select=DEFAULT_SELECT,
           candidates_per_env: int = 10) -> dict[str, Any]:
    records = _read_jsonl(drafts_path)
    header, drafts = records[0], records[1:]
    _exact_keys(header, HEADER_KEYS, "drafts header")
    if header["schema"] != DRAFT_SCHEMA or header["difficulty"] != DIFFICULTY:
        raise SpecsError("drafts 版本或难度不符")
    sampling_document = json.loads(Path(sampling_path).read_text(encoding="utf-8"))
    _check_sources(header, sampling_document, "冻结")
    rows, per_env = [], {}
    for task in header["tasks"]:
        ok_rows = []
        for row in drafts:
            _exact_keys(row, DRAFT_ROW_KEYS, "drafts 行")
            if row["task"] != task or not row["reset_ok"]:
                continue
            if row["spec_sha256"] != spec_sha256(row["spec"]):
                raise SpecsError(f"drafts 行规格散列不符：{task}/{row['episode']}")
            if row["seed"] != seed_for(task, row["episode"], row["attempt"]):
                raise SpecsError(f"drafts 行 seed 与公式不符：{task}/{row['episode']}")
            ok_rows.append(row)
        ok_rows.sort(key=lambda r: r["episode"])
        if [r["episode"] for r in ok_rows] != list(range(len(ok_rows))):
            raise SpecsError(f"{task} 的成功候选编号不连续")
        attempted = sum(1 for r in drafts if r["task"] == task)
        selected = [r["episode"] for r in ok_rows if r["episode"] in select]
        per_env[task] = {"candidates": len(ok_rows), "attempted": attempted,
                         "candidate_shortfall": max(0, candidates_per_env - len(ok_rows)),
                         "selected": selected}
        for row in ok_rows:
            rows.append({
                "record": "spec", "task": task, "difficulty": DIFFICULTY, "episode": row["episode"],
                "attempt": row["attempt"], "seed": row["seed"], "spec": row["spec"],
                "spec_sha256": row["spec_sha256"], "selected": row["episode"] in select,
            })
    specs_header = {key: copy.deepcopy(header[key]) for key in HEADER_KEYS}
    specs_header.update({
        "schema": SPECS_SCHEMA,
        "drafts_sha256": hashlib.sha256(Path(drafts_path).read_bytes()).hexdigest(),
        "select_indices": list(select),
        "per_env": per_env,
    })
    specs_header["identity_sha256"] = identity_sha256(specs_header, rows)
    validate_specs(specs_header, rows)
    _write_jsonl(out, [specs_header, *rows])
    return {"rows": len(rows), "selected": sum(r["selected"] for r in rows), "per_env": per_env}


def validate_specs(header: dict[str, Any], rows: list[dict[str, Any]], *, check_disk: bool = False) -> None:
    _exact_keys(header, HEADER_KEYS | SPECS_HEADER_EXTRA, "specs header")
    if header["schema"] != SPECS_SCHEMA or header["difficulty"] != DIFFICULTY or header["runtime"] != RUNTIME:
        raise SpecsError("specs 版本、难度或 runtime 不符")
    if header["sampling_config_sha256"] != digest(header["sampling_config"]):
        raise SpecsError("内嵌 sampling_config 散列不自洽")
    seen = set()
    for row in rows:
        _exact_keys(row, SPEC_ROW_KEYS, "specs 行")
        key = (row["task"], row["episode"])
        if key in seen or row["task"] not in header["tasks"]:
            raise SpecsError(f"重复或额外的规格行：{key}")
        seen.add(key)
        if row["spec_sha256"] != spec_sha256(row["spec"]):
            raise SpecsError(f"规格散列不符：{key}")
        if row["seed"] != seed_for(row["task"], row["episode"], row["attempt"]):
            raise SpecsError(f"seed 与公式不符：{key}")
        if type(row["selected"]) is not bool:
            raise SpecsError(f"selected 必须是布尔：{key}")
    if identity_sha256(header, rows) != header["identity_sha256"]:
        raise SpecsError("identity_sha256 不符（规格值或来源被改过）")
    if check_disk:
        if header["source_fingerprint"] != source_fingerprint():
            raise SpecsError("源码指纹与当前工作树不符")


def load_specs(path: str | Path, *, check_disk: bool = True):
    """实跑段／推理侧的唯一读取入口。返回 ``(header, sampling_by_task, specs_by_identity)``。

    ``specs_by_identity["<task>/<episode>"]`` 只含 ``selected=true`` 的行（值是整行，含 seed 与 spec）。
    """
    records = _read_jsonl(Path(path))
    header, rows = records[0], records[1:]
    validate_specs(header, rows, check_disk=check_disk)
    sampling_by_task = copy.deepcopy(header["sampling_config"])
    specs_by_identity = {f"{r['task']}/{r['episode']}": r for r in rows if r["selected"]}
    return header, sampling_by_task, specs_by_identity


def reselect(specs_path: Path, results_path: Path, out: Path) -> dict[str, Any]:
    """H4 递补后按实跑结果重标 ``selected``：只把演示成功的局标为正式局，写出新快照。

    规格值与来源一字不动 ⇒ ``identity_sha256`` 必须不变（``selected`` 是管理字段）；原冻结文件不改。
    推理侧应评这份快照：演示本身失败的局（如规划器找不到路径）在推理路径上可能卡在示范重放里。
    """
    records = _read_jsonl(Path(specs_path))
    header, rows = records[0], records[1:]
    validate_specs(header, rows, check_disk=True)
    ok = {(r["task"], int(r["episode"]))
          for r in (json.loads(line) for line in Path(results_path).read_text(encoding="utf-8").splitlines() if line.strip())
          if r["ok"]}
    new_rows = [{**row, "selected": (row["task"], row["episode"]) in ok} for row in rows]
    # header 一字不动（per_env 在冻结时已进身份散列，其中的 selected 记的是冻结时 0/3/6 的初选）；
    # 以数据行上的 selected 为准
    new_header = copy.deepcopy(header)
    if identity_sha256(new_header, new_rows) != header["identity_sha256"]:
        raise SpecsError("重标 selected 后身份散列变了——只允许改管理字段")
    validate_specs(new_header, new_rows)
    _write_jsonl(Path(out), [new_header, *new_rows])
    per_env = {task: sorted(r["episode"] for r in new_rows if r["task"] == task and r["selected"])
               for task in header["tasks"]}
    return {"selected": sum(r["selected"] for r in new_rows), "per_env": per_env}


def cmd_reselect(args: argparse.Namespace) -> int:
    result = reselect(Path(args.specs), Path(args.results), Path(args.out))
    print(f"RESELECT_DONE selected={result['selected']} out={args.out}")
    return 0


def cmd_freeze(args: argparse.Namespace) -> int:
    select = tuple(int(x) for x in args.select.split(","))
    result = freeze(Path(args.drafts), Path(args.sampling_config), Path(args.out), select, args.candidates_per_env)
    shortfall = sum(v["candidate_shortfall"] for v in result["per_env"].values())
    print(f"FREEZE_DONE rows={result['rows']} selected={result['selected']} "
          f"envs={len(result['per_env'])} candidate_shortfall={shortfall} out={args.out}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    draw = sub.add_parser("draw", help="抽签：xhard 只 reset，导出规格到 drafts.jsonl")
    draw.add_argument("--run-id", required=True)
    draw.add_argument("--tasks", default="all")
    draw.add_argument("--sampling-config", default=str(DEFAULT_SAMPLING))
    draw.add_argument("--candidates-per-env", type=int, default=10)
    draw.add_argument("--max-reset-attempts", type=int, default=30)
    draw.add_argument("--out", required=True)
    draw.set_defaults(func=cmd_draw)
    fr = sub.add_parser("freeze", help="冻结：核验来源后写出 specs.jsonl（纯 CPU）")
    fr.add_argument("--drafts", required=True)
    fr.add_argument("--sampling-config", default=str(DEFAULT_SAMPLING))
    fr.add_argument("--select", default=",".join(map(str, DEFAULT_SELECT)))
    fr.add_argument("--candidates-per-env", type=int, default=10)
    fr.add_argument("--out", required=True)
    fr.set_defaults(func=cmd_freeze)
    rs = sub.add_parser("reselect", help="H4 递补后按实跑结果重标 selected（身份散列不变，另写新文件）")
    rs.add_argument("--specs", required=True)
    rs.add_argument("--results", required=True, help="v4_rollout 的 results.jsonl")
    rs.add_argument("--out", required=True)
    rs.set_defaults(func=cmd_reselect)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
