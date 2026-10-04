#!/usr/bin/env python3
"""v8 单格补抽：给某格（``TASK@TIER``）追加候选，让 ``generate_h5.py --mode continue --resume`` 自动递补。

用途：gen1 某格备用候选耗尽（``V8_DELIVERY_SET=FAIL … problems=<task>/<tier>:exhausted``），经用户补充授权后
补抽 N 个新候选（S3-SUP，用户 2026-10-01「补抽到 40」，预算 reset ≤ 30、rollout ≤ 10）。

    # 先看计划（不起环境、不写盘）
    python scripts/injection-dev/append_candidates.py --frozen-root <specs-frozen> \\
        --shard-dir <gen1>/shard2 --cell BinFill@xhard2 --extra 10 --max-reset-attempts 30 --dry-run
    # 实抽 + 写回；之后续跑：generate_h5.py --mode continue --specs <shard>/specs --cells shard2 --output <shard> --resume
    python scripts/injection-dev/append_candidates.py --frozen-root <specs-frozen> \\
        --shard-dir <gen1>/shard2 --cell BinFill@xhard2 --extra 10 --max-reset-attempts 30 --gpus 0

步骤：

1. 读冻结根 ``<frozen>/<tier>/specs.jsonl`` 与片规格根 ``<shard>/specs/<tier>/specs.jsonl``（都走 ``load_specs`` 的
   /4 校验），核：片 ``shard.json`` 记录的来源 identity 等于冻结根当前 identity；冻结根未跑过；该任务在两边
   ``per_env`` 相同、行身份逐字相同、episode 恰为 ``0..per_env-1``；片里该任务无「selected 未跑」行、无未试备用
   （否则不需要追加）；两份文件都未被锁（``<specs>.lock``，有 continue 在跑即拒绝）。
2. 抽签：只 reset、不 step，复用 ``_draw._draw_one``（与 ``_draw.draw_task`` 同一推进规则：每个 episode 从
   attempt 0 起 reset，失败 attempt+1，成功进下一个 episode），seed 按冻结 header 的 ``seed_rule``（=
   ``seed_rule_for(tier, "v8")``）算，episode 从 ``per_env`` 起连续编号；``sampling_config`` 取冻结 header 里该任务
   那一份（实跑前另用 ``_extract.build_sampling`` 重建一次，必须与冻结值相等，保证同一决策规则）；reset 总次数
   受 ``--max-reset-attempts`` 限制，打印 ``APPEND_DRAW tried= ok=``。
3. 写回（只追加）：两份规格文件的旧行逐字保留（原文本行原样写回），文件末尾追加新行（与冻结未选行同形：
   ``selected=false tried=false initial_selected=false rollout=null layout_parent=null``）；header 只改
   ``per_env[task]``（+= 实抽成功数）与 ``draw_stats.appends``（审计记录，不进签），按 /4 重算
   ``identity_sha256``／``delivery_sha256``；``select_rule``／``delivery_per_cell`` 不动。
   **片规格里**另把缺额（配额 − 当前 selected 数）个编号最小的新候选标 ``selected=true``——这正是
   ``_rollout.apply_results`` 递补时做的事：片规格已回写过（行都 ``tried``），``--resume`` 不会重放账本，
   ``plan_pending`` 只挑「selected 且无 rollout」的行，新候选若全为 ``selected=false`` 续跑什么都不会做。
   冻结根的新行保持 ``selected=false``（合并时 ``selected``／``tried``／``rollout`` 一律取自片）。
   所有引用该档冻结 identity 的片（``<shard>`` 的同级目录 ``*/shard.json`` 里 ``sources[tier].identity_sha256``
   等于旧 identity 的全部片，含本片）把 ``sources[tier]`` 改为新的 identity／文件 sha，并追加 ``appends`` 记录——
   使各片 ``shard.json`` 记录的来源与冻结根保持一致（当初的 V8 四席合并依赖这一条，该合并已于维护计划 W2 删除，
   现只为来源记录自洽）。
   写前每份被改文件先复制为 ``<文件>.pre-append-<时间戳>``（``open("x")`` 排他新建）；写用同目录临时文件 +
   ``os.replace``；写后逐份 ``load_specs`` 重读校验、片根 ``load_v8_root``、各片来源 identity 与冻结根一致、
   新旧行身份逐字一致。任一步失败：全部按备份恢复，打印 ``APPEND_CANDIDATES=FAIL``，退出码 1。
   成功：``APPEND_CANDIDATES=PASS cell=… extra=N per_env=<旧>→<新> frozen_identity=<前 12 位> shard_identity=<…>``。

``--code-root``：从哪个仓库检出取抽签／校验代码（``<code-root>/scripts/injection-dev`` 与 ``<code-root>/src``），
缺省为本文件所在仓库。GL 上冻结克隆不含本脚本时，把本脚本放在克隆之外、``--code-root`` 指向冻结克隆，
抽签与校验就逐字用冻结克隆的 ``_draw``／``hard_specs``／``robomme_hard``（打印 ``APPEND_CODE`` 行核对）。
"""

from __future__ import annotations

import argparse
import copy
import datetime
import functools
import hashlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

DEFAULT_CODE_ROOT = Path(__file__).resolve().parents[2]
SHARD_META = "shard.json"

# bootstrap 之后才有值（代码来源由 --code-root 决定）
H = None  # robomme_hard.env_record_wrapper.hard_specs
_draw = None
_rollout = None
_extract = None
CODE_ROOT: Path | None = None


class AppendError(RuntimeError):
    """追加前置条件不满足或写回校验失败。"""


def bootstrap(code_root: str | Path = DEFAULT_CODE_ROOT) -> None:
    """把 ``<code_root>/scripts/injection-dev`` 放到 sys.path 最前并导入抽签／校验模块（``_common`` 再把
    ``<code_root>/src`` 放最前）。同一进程只允许一个代码来源。"""
    global H, _draw, _rollout, _extract, CODE_ROOT
    code_root = Path(code_root).resolve()
    if CODE_ROOT is not None:
        if CODE_ROOT != code_root:
            raise AppendError(f"同一进程已从 {CODE_ROOT} 取代码，不能再换 {code_root}")
        return
    inj = code_root / "scripts" / "injection-dev"
    if not (inj / "_common.py").is_file():
        raise AppendError(f"--code-root {code_root} 下没有 scripts/injection-dev/_common.py")
    if str(inj) in sys.path:
        sys.path.remove(str(inj))
    sys.path.insert(0, str(inj))
    import _common  # noqa: F401,PLC0415
    import _draw as draw_mod  # noqa: PLC0415
    import _extract as extract_mod  # noqa: PLC0415
    import _rollout as rollout_mod  # noqa: PLC0415
    from robomme_hard.env_record_wrapper import hard_specs  # noqa: PLC0415

    for name, mod in (("_common", _common), ("_draw", draw_mod), ("_rollout", rollout_mod)):
        if Path(mod.__file__).resolve().parent != inj:
            raise AppendError(f"{name} 取自 {mod.__file__}，不是 {inj}（同名模块已被别处先导入）")
    H, _draw, _rollout, _extract, CODE_ROOT = hard_specs, draw_mod, rollout_mod, extract_mod, code_root


# ── 读与前置核对 ─────────────────────────────────────────────────────────


def read_specs_raw(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    """``load_specs``（/4 校验）+ 原文本行（旧行写回时逐字保留）。"""
    header, rows = H.load_specs(path, check_fingerprint=False)
    lines = [line for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(lines) != len(rows) + 1:
        raise AppendError(f"{path} 行数与解析结果不符")
    for line, row in zip(lines[1:], rows):
        if json.loads(line) != row:
            raise AppendError(f"{path} 原文本行与解析行不符")
    return header, rows, lines[1:]


def parse_cell(text: str) -> tuple[str, str]:
    task, sep, tier = str(text).partition("@")
    if not sep or not task or not tier:
        raise AppendError(f"--cell 须为 TASK@TIER：{text!r}")
    return task, tier


def find_shards(shard_dir: Path, tier: str, identity: str) -> tuple[list[Path], list[str]]:
    """同级目录里来源 identity 等于 ``identity`` 的片（含本片）；返回 (片目录列表, 跳过说明)。"""
    found, skipped = [], []
    for meta_path in sorted(Path(shard_dir).resolve().parent.glob(f"*/{SHARD_META}")):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            skipped.append(f"{meta_path.parent.name}:unreadable:{type(exc).__name__}")
            continue
        if meta.get("schema") != _rollout.V8_SHARD_SCHEMA:
            skipped.append(f"{meta_path.parent.name}:schema")
            continue
        src = (meta.get("sources") or {}).get(tier)
        if src is None:
            skipped.append(f"{meta_path.parent.name}:no_{tier}")
        elif src.get("identity_sha256") != identity:
            skipped.append(f"{meta_path.parent.name}:other_identity:{str(src.get('identity_sha256'))[:12]}")
        else:
            found.append(meta_path.parent)
    return found, skipped


def plan_append(frozen_root: Path, shard_dir: Path, task: str, tier: str, extra: int) -> dict[str, Any]:
    """只读核对 + 计划（``--dry-run`` 与实跑共用）。"""
    # 格集合按 V9_CELLS 判（与已删除的 V8 1070 局表格集合相同，只有局数不同）
    if tier not in H.TIERS or (task, tier) not in H.V9_CELLS:
        raise AppendError(f"{task}@{tier} 不是 v8 交付格")
    if extra <= 0:
        raise AppendError(f"--extra 须为正整数：{extra}")
    frozen_path = Path(frozen_root) / tier / "specs.jsonl"
    shard_path = Path(shard_dir) / "specs" / tier / "specs.jsonl"
    meta_path = Path(shard_dir) / SHARD_META
    for path in (frozen_path, shard_path, meta_path):
        if not path.is_file():
            raise AppendError(f"缺少 {path}")
    for path in (frozen_path, shard_path):
        if Path(str(path) + ".lock").exists():
            raise AppendError(f"{path}.lock 存在（有 continue 在跑或上次异常退出），拒绝追加")
    f_header, f_rows, f_lines = read_specs_raw(frozen_path)
    s_header, s_rows, s_lines = read_specs_raw(shard_path)
    for name, header in (("冻结根", f_header), ("片规格", s_header)):
        if header["schema"] != H.SCHEMA or header["difficulty"] != tier:
            raise AppendError(f"{name} 须为 {H.SCHEMA} 且档位 {tier}")
        if task not in header["tasks"]:
            raise AppendError(f"{name} 的 {tier} 不含任务 {task}")
        if header["seed_rule"] != H.seed_rule_for(tier, "v8"):
            raise AppendError(f"{name} 的 seed_rule 不是 v8 规则")
    if any(r["tried"] for r in f_rows):
        raise AppendError(f"{frozen_path} 已跑过（有 tried 行），冻结根只能是未跑过的")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    cells = _rollout.resolve_cells_from_json(meta["cells"])
    if (task, tier) not in cells:
        raise AppendError(f"{shard_dir} 的格表不含 {task}@{tier}")
    if (meta.get("sources") or {}).get(tier, {}).get("identity_sha256") != f_header["identity_sha256"]:
        raise AppendError(f"{meta_path} 记录的 {tier} 来源 identity 与冻结根当前 identity 不符")
    if s_header["sampling_config"][task] != f_header["sampling_config"][task]:
        raise AppendError(f"片规格与冻结根的 {task} sampling_config 不符")
    if f_header["per_env"][task] != s_header["per_env"][task]:
        raise AppendError(f"per_env[{task}] 冻结根 {f_header['per_env'][task]} ≠ 片 {s_header['per_env'][task]}")
    if f_header["delivery_per_cell"][task] != s_header["delivery_per_cell"][task]:
        raise AppendError(f"delivery_per_cell[{task}] 冻结根与片不符")
    per_env = int(f_header["per_env"][task])
    _, row_keys, _, _ = H._schema_keys(H.SCHEMA)
    f_task = sorted((r for r in f_rows if r["task"] == task), key=lambda r: r["candidate"])
    s_task = sorted((r for r in s_rows if r["task"] == task), key=lambda r: r["candidate"])
    if [r["episode"] for r in f_task] != list(range(per_env)):
        raise AppendError(f"冻结根 {task} 的 episode 不是 0..{per_env - 1}")
    for a, b in zip(f_task, s_task, strict=True):
        if any(a[k] != b[k] for k in row_keys) or a["spec"] != b["spec"]:
            raise AppendError(f"{task}/{a['candidate']} 片行与冻结根行身份不符")
    quota = int(s_header["delivery_per_cell"][task])
    selected = sum(r["selected"] for r in s_task)
    pending = [r["candidate"] for r in s_task if r["selected"] and r["rollout"] is None]
    if pending:
        raise AppendError(f"片里 {task} 还有 selected 未跑的行 {pending[:5]}，先跑完再追加")
    spares = [r["candidate"] for r in s_task if not r["tried"] and not r["selected"]]
    if spares:
        raise AppendError(f"片里 {task} 还有未试备用 {spares[:5]}，用不着追加")
    delivered = sum(H.delivered(r) for r in s_task)
    deficit = quota - selected
    # 同任务别档的 seed（冻结根里有的档都读；只读 seed 不做全量校验）
    other_seeds: set[int] = set()
    for other in H.TIERS:
        path = Path(frozen_root) / other / "specs.jsonl"
        if other == tier or not path.is_file():
            continue
        other_seeds |= {int(r["seed"]) for r in H.read_jsonl(path)[1:] if r.get("task") == task}
    shards, skipped = find_shards(shard_dir, tier, f_header["identity_sha256"])
    if Path(shard_dir).resolve() not in shards:
        raise AppendError(f"本片 {shard_dir} 不在同级来源一致的片里（内部错误）")
    return {
        "task": task, "tier": tier, "extra": int(extra), "per_env": per_env, "quota": quota,
        "selected": selected, "delivered": delivered, "deficit": deficit,
        "frozen_path": frozen_path, "shard_path": shard_path, "shard_dir": Path(shard_dir).resolve(),
        "frozen": (f_header, f_rows, f_lines), "shard": (s_header, s_rows, s_lines),
        "shard_cells": cells, "shards": shards, "skipped_shards": skipped, "other_seeds": other_seeds,
        "seed_rule": f_header["seed_rule"], "sampling": f_header["sampling_config"][task],
    }


# ── 抽签 ─────────────────────────────────────────────────────────────────


def draw_candidates(task: str, tier: str, sampling: dict[str, Any], seed_rule: dict[str, Any], start: int,
                    extra: int, max_reset_attempts: int,
                    draw_one: Callable) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """与 ``_draw.draw_task`` 同一推进规则，只是 episode 从 ``start`` 起；返回 (抽签行, 统计)。"""
    drafts: list[dict[str, Any]] = []
    episode, attempt, total = start, 0, 0
    while episode < start + extra and total < max_reset_attempts:
        seed = H.seed_for(task, episode, attempt, seed_rule)
        started = time.time()
        ok, spec, fail_class, error = draw_one(task, seed, episode, sampling)
        drafts.append({"record": "draft", "task": task, "difficulty": tier, "episode": episode, "attempt": attempt,
                       "seed": seed, "reset_ok": bool(ok), "fail_class": fail_class, "error": error, "spec": spec,
                       "spec_sha256": H.spec_sha256(spec) if ok else None,
                       "wall_s": round(time.time() - started, 2)})
        total += 1
        print(f"DRAW {task} ep={episode} attempt={attempt} seed={seed} ok={bool(ok)} {fail_class or ''}", flush=True)
        if ok:
            episode, attempt = episode + 1, 0
        else:
            attempt += 1
    ok_n = episode - start
    fail_class: dict[str, int] = {}
    for d in drafts:
        if not d["reset_ok"]:
            key = d["fail_class"] or "unknown"
            fail_class[key] = fail_class.get(key, 0) + 1
    print(f"APPEND_DRAW tried={total} ok={ok_n} shortfall={extra - ok_n} max_reset_attempts={max_reset_attempts} "
          f"fail_class={json.dumps(fail_class, ensure_ascii=False, sort_keys=True)}", flush=True)
    return drafts, {"attempted": total, "ok": ok_n, "fail_class": fail_class}


def draw_extra(frozen_header: dict[str, Any], task: str, tier: str, start: int, count: int, *,
               allow_spares: bool = False, frozen_rows: list[dict[str, Any]] | None = None,
               shard_rows: list[dict[str, Any]] | None = None, max_reset_attempts: int,
               draw_one: Callable | None = None, sampling_check: Callable | None = None,
               pkg: str = "robomme_hard", release: str | None = None,
               gpus: str | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """抽签函数（CLI 与 S1-D ``v9_subset_specs.py extend`` 共用）：按冻结 header 给 ``task@tier`` 从候选号 ``start``
    起追加 ``count`` 个候选，返回 ``(新规格行, 抽签统计)``；只抽签、不写盘。

    核对（两种入口都做）：header 为 /4、档位与 seed 规则为 ``seed_rule_for(tier, "v8")``、任务在 header 内、
    ``start == per_env[task]``（新候选号紧接已有候选）；源码重建的 ``sampling_config`` 与冻结值相等
    （``sampling_check`` 注入或 ``check_sampling``）；新行 seed 按公式、规格散列自洽（``spec_rows_from_drafts``）。

    ``allow_spares=False``（CLI 口径）另做两道拒绝：``frozen_rows`` 里有 tried 行（冻结根必须未跑过）、
    ``shard_rows``（缺省用 ``frozen_rows``）里该任务还有未试备用。``allow_spares=True``（v9 InsertPeg 迁移：V8 片已跑过、
    候选号 29～39 仍是未试备用）跳过这两道，其余核对照旧。"""
    if H is None:
        bootstrap()
    if frozen_header.get("schema") != H.SCHEMA or frozen_header.get("difficulty") != tier:
        raise AppendError(f"冻结 header 须为 {H.SCHEMA} 且档位 {tier}")
    if task not in frozen_header["tasks"]:
        raise AppendError(f"冻结 header 的 {tier} 不含任务 {task}")
    if frozen_header["seed_rule"] != H.seed_rule_for(tier, "v8"):
        raise AppendError("冻结 header 的 seed_rule 不是 v8 规则")
    if count <= 0 or max_reset_attempts <= 0:
        raise AppendError(f"追加数与 reset 预算须为正整数：count={count} max_reset_attempts={max_reset_attempts}")
    if int(start) != int(frozen_header["per_env"][task]):
        raise AppendError(f"新候选须从 per_env={frozen_header['per_env'][task]} 起连续编号（收到 start={start}）")
    if not allow_spares:
        if frozen_rows is None:
            raise AppendError("allow_spares=False 时须给 frozen_rows（核对冻结根未跑过、无未试备用）")
        if any(r["tried"] for r in frozen_rows):
            raise AppendError("冻结根已跑过（有 tried 行），冻结根只能是未跑过的")
        check_rows = frozen_rows if shard_rows is None else shard_rows
        spares = [r["candidate"] for r in check_rows if r["task"] == task and not r["tried"] and not r["selected"]]
        if spares:
            raise AppendError(f"片里 {task} 还有未试备用 {spares[:5]}，用不着追加")
    sampling = frozen_header["sampling_config"][task]
    if sampling_check is not None:
        sampling_check(task, sampling)
    else:
        check_sampling(task, sampling, pkg, release or _extract.DEFAULT_RELEASE)
    if draw_one is None:
        gpu_list = _draw.parse_gpus(gpus)
        if gpu_list:
            os.environ["CUDA_VISIBLE_DEVICES"] = gpu_list[0]
        _draw.assert_registry_owner(pkg)
        draw_one = functools.partial(_draw._draw_one, difficulty=tier)
    drafts, info = draw_candidates(task, tier, sampling, frozen_header["seed_rule"], int(start), int(count),
                                   max_reset_attempts, draw_one)
    return spec_rows_from_drafts(drafts, tier, frozen_header["seed_rule"]), info


def spec_rows_from_drafts(drafts: list[dict[str, Any]], tier: str, seed_rule: dict[str, Any]) -> list[dict[str, Any]]:
    """成功抽签行 → 规格行（与 ``_freeze.freeze`` 写未选行同形）。"""
    rows = []
    for d in drafts:
        if not d["reset_ok"]:
            continue
        if not isinstance(d["spec"], dict) or d["spec_sha256"] != H.spec_sha256(d["spec"]):
            raise AppendError(f"抽签行规格散列不符：{d['task']}/{d['episode']}")
        if d["seed"] != H.seed_for(d["task"], d["episode"], d["attempt"], seed_rule) or d["difficulty"] != tier:
            raise AppendError(f"抽签行 seed／档位与公式不符：{d['task']}/{d['episode']}")
        rows.append({"record": "spec", "task": d["task"], "tier": tier, "candidate": d["episode"],
                     "episode": d["episode"], "seed": d["seed"], "attempt": d["attempt"], "spec": d["spec"],
                     "spec_sha256": d["spec_sha256"], "selected": False, "tried": False, "initial_selected": False,
                     "rollout": None, "layout_parent": None})
    return rows


# ── 组装与写回 ───────────────────────────────────────────────────────────


def build_file(header: dict[str, Any], rows: list[dict[str, Any]], old_lines: list[str], new_rows: list[dict[str, Any]],
               task: str, audit: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    """新 header（per_env += 新行数、draw_stats.appends 追加、重签）+ 全部行 + 文件文本（旧行逐字保留）。"""
    new_header = copy.deepcopy(header)
    new_header["per_env"][task] = int(header["per_env"][task]) + len(new_rows)
    stats = copy.deepcopy(new_header.get("draw_stats") or {})
    stats["appends"] = [*stats.get("appends", []), audit]
    new_header["draw_stats"] = stats
    all_rows = [*rows, *new_rows]
    new_header["identity_sha256"] = H.identity_sha256(new_header, all_rows)
    new_header["delivery_sha256"] = H.delivery_sha256(all_rows)
    H.validate_specs(new_header, all_rows)
    text = "\n".join([H.canonical_json(new_header), *old_lines, *(H.canonical_json(r) for r in new_rows)]) + "\n"
    return new_header, all_rows, text


def _atomic_write(path: Path, data: bytes) -> None:
    path = Path(path)
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o644
    fd, name = tempfile.mkstemp(prefix=".append-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(name, mode)
        os.replace(name, path)
    except BaseException:
        if os.path.exists(name):
            os.unlink(name)
        raise


def _backup(path: Path, stamp: str) -> Path:
    backup = Path(f"{path}.pre-append-{stamp}")
    with open(backup, "xb") as stream:  # 排他新建：同名备份已存在即失败
        stream.write(Path(path).read_bytes())
    return backup


def verify_written(plan: dict[str, Any], result: dict[str, Any]) -> None:
    """写后复核（失败抛异常，调用方恢复）：两份规格重读校验、片根按格表读、各片来源 identity、新行身份一致。"""
    task, tier = plan["task"], plan["tier"]
    f_header, f_rows = H.load_specs(plan["frozen_path"], check_fingerprint=False)
    s_header, s_rows = H.load_specs(plan["shard_path"], check_fingerprint=False)
    if f_header["identity_sha256"] != result["frozen_identity"] or s_header["identity_sha256"] != result["shard_identity"]:
        raise AppendError("重读后 identity 与写入值不符")
    if f_header["per_env"][task] != result["per_env_new"] or s_header["per_env"][task] != result["per_env_new"]:
        raise AppendError("重读后 per_env 不符")
    if any(r["tried"] for r in f_rows):
        raise AppendError("冻结根写后出现 tried 行")
    _rollout.load_v8_root(plan["shard_dir"] / "specs", plan["shard_cells"])
    file_sha = _rollout.file_sha256(plan["frozen_path"])
    for shard in plan["shards"]:
        src = json.loads((shard / SHARD_META).read_text(encoding="utf-8"))["sources"][tier]
        if src != {"identity_sha256": f_header["identity_sha256"], "file_sha256": file_sha}:
            raise AppendError(f"{shard / SHARD_META} 的 {tier} 来源未更新到新冻结根")
    _, row_keys, _, _ = H._schema_keys(H.SCHEMA)
    frozen_by = {(r["task"], r["candidate"]): r for r in f_rows}
    for r in s_rows:
        f = frozen_by.get((r["task"], r["candidate"]))
        if f is None or any(f[k] != r[k] for k in row_keys) or f["spec"] != r["spec"]:
            raise AppendError(f"片行 {(r['task'], r['candidate'])} 与冻结根身份不符")


def apply_append(plan: dict[str, Any], new_rows: list[dict[str, Any]], draw_info: dict[str, Any], *,
                 max_reset_attempts: int, pkg: str, stamp: str | None = None) -> dict[str, Any]:
    """组装、备份、原子写回、复核；失败全部按备份恢复后抛 ``AppendError``。返回结果摘要。"""
    task, tier = plan["task"], plan["tier"]
    if not new_rows:
        raise AppendError("没有抽到任何新候选，不写回")
    episodes = [r["episode"] for r in new_rows]
    if episodes != list(range(plan["per_env"], plan["per_env"] + len(new_rows))):
        raise AppendError(f"新候选 episode 须从 {plan['per_env']} 起连续：{episodes}")
    clash = sorted({int(r["seed"]) for r in new_rows} & plan["other_seeds"])
    if clash:
        raise AppendError(f"新候选 seed 与同任务别档相交：{clash[:5]}")
    f_header, f_rows, f_lines = plan["frozen"]
    s_header, s_rows, s_lines = plan["shard"]
    stamp = stamp or datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
    now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    chosen = episodes[:max(plan["deficit"], 0)]
    audit = {"at": now, "tool": "append_candidates.py", "task": task, "tier": tier,
             "start_episode": plan["per_env"], "extra_requested": plan["extra"], "appended": len(new_rows),
             "episodes": [episodes[0], episodes[-1]], "attempted": draw_info["attempted"],
             "fail_class": draw_info["fail_class"], "max_reset_attempts": int(max_reset_attempts), "env_package": pkg,
             "code_root": str(CODE_ROOT), "old_identity_sha256": f_header["identity_sha256"]}
    new_f_header, _, f_text = build_file(f_header, f_rows, f_lines, new_rows, task, audit)
    shard_new = [dict(copy.deepcopy(r), selected=r["episode"] in chosen) for r in new_rows]
    s_audit = {**audit, "old_identity_sha256": s_header["identity_sha256"],
               "source_identity_sha256": new_f_header["identity_sha256"], "backfill_selected": chosen}
    new_s_header, _, s_text = build_file(s_header, s_rows, s_lines, shard_new, task, s_audit)
    f_bytes = f_text.encode("utf-8")
    f_file_sha = hashlib.sha256(f_bytes).hexdigest()
    metas: dict[Path, bytes] = {}
    for shard in plan["shards"]:
        meta = json.loads((shard / SHARD_META).read_text(encoding="utf-8"))
        old_src = meta["sources"][tier]
        meta["sources"][tier] = {"identity_sha256": new_f_header["identity_sha256"], "file_sha256": f_file_sha}
        meta["appends"] = [*meta.get("appends", []), {
            "at": now, "cell": f"{task}@{tier}", "appended": len(new_rows), "frozen_root": str(plan["frozen_path"].parent.parent),
            "old_source": old_src, "new_source": meta["sources"][tier], "backup_suffix": f".pre-append-{stamp}"}]
        metas[shard / SHARD_META] = (json.dumps(meta, ensure_ascii=False, indent=1) + "\n").encode("utf-8")
    targets: dict[Path, bytes] = {plan["frozen_path"]: f_bytes, plan["shard_path"]: s_text.encode("utf-8"), **metas}
    result = {"frozen_identity": new_f_header["identity_sha256"], "shard_identity": new_s_header["identity_sha256"],
              "per_env_old": plan["per_env"], "per_env_new": plan["per_env"] + len(new_rows), "appended": len(new_rows),
              "backfill_selected": chosen, "backups": [], "updated_shards": [str(s) for s in plan["shards"]]}
    locks = [_rollout.SpecsLock(plan["frozen_path"]), _rollout.SpecsLock(plan["shard_path"])]
    held: list = []
    backups: dict[Path, Path] = {}
    written: list[Path] = []
    try:
        for lock in locks:
            lock.acquire()
            held.append(lock)
        for path in targets:
            backups[path] = _backup(path, stamp)
        result["backups"] = [str(p) for p in backups.values()]
        for path, data in targets.items():
            written.append(path)
            _atomic_write(path, data)
        verify_written(plan, result)
    except BaseException as exc:
        restored = []
        for path in written:
            try:
                _atomic_write(path, backups[path].read_bytes())
                restored.append(str(path))
            except BaseException as again:  # noqa: BLE001 恢复失败要显式报出
                print(f"# 恢复失败：{path} ← {backups[path]}：{again}", flush=True)
        raise AppendError(f"写回失败已恢复 {len(restored)}/{len(written)} 份（备份留证：{sorted(map(str, backups.values()))}）："
                          f"{type(exc).__name__}: {exc}") from exc
    finally:
        for lock in held:
            lock.release()
    return result


# ── CLI ─────────────────────────────────────────────────────────────────


def _print_plan(plan: dict[str, Any], args) -> None:
    task, tier = plan["task"], plan["tier"]
    first = [H.seed_for(task, plan["per_env"] + i, 0, plan["seed_rule"]) for i in range(plan["extra"])]
    print(f"APPEND_PLAN cell={task}@{tier} quota={plan['quota']} selected={plan['selected']} "
          f"delivered={plan['delivered']} deficit={plan['deficit']} per_env={plan['per_env']} "
          f"new_episodes={plan['per_env']}..{plan['per_env'] + plan['extra'] - 1} extra={plan['extra']} "
          f"max_reset_attempts={args.max_reset_attempts} first_seeds={first[0]}..{first[-1]} "
          f"frozen_identity={plan['frozen'][0]['identity_sha256'][:12]} "
          f"shard_identity={plan['shard'][0]['identity_sha256'][:12]} pkg={args.pkg} code_root={CODE_ROOT}", flush=True)
    print(f"APPEND_SHARDS update={','.join(s.name for s in plan['shards'])} "
          f"skip={','.join(plan['skipped_shards']) or '-'}", flush=True)
    print(f"APPEND_FILES frozen={plan['frozen_path']} shard={plan['shard_path']} "
          f"shard_meta={','.join(str(s / SHARD_META) for s in plan['shards'])}", flush=True)


def check_sampling(task: str, frozen_sampling: dict[str, Any], pkg: str, release: str) -> None:
    """重建该任务的 sampling_config，必须与冻结值相等（同一决策规则才能补抽）。"""
    rebuilt = _extract.build_sampling([task], pkg=pkg, release=release)["tasks"][task]
    if H.digest(rebuilt) != H.digest(frozen_sampling):
        raise AppendError(f"{task} 重建的 sampling_config 与冻结值不符（代码或 release 变了），拒绝补抽")


def main(argv: list[str] | None = None, *, draw_one: Callable | None = None,
         sampling_check: Callable | None = None) -> int:
    """``draw_one``／``sampling_check`` 只供单测注入（不起仿真）。"""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--frozen-root", required=True, help="冻结根（<root>/<tier>/specs.jsonl）")
    parser.add_argument("--shard-dir", required=True, help="片输出目录（含 specs/、shard.json、results.jsonl）")
    parser.add_argument("--cell", required=True, help="TASK@TIER，如 BinFill@xhard2")
    parser.add_argument("--extra", type=int, default=10, help="追加候选数（缺省 10）")
    parser.add_argument("--max-reset-attempts", type=int, default=30, help="reset 总预算（缺省 30）")
    parser.add_argument("--workers", type=int, default=1, help="单格抽签按 draw_task 规则串行推进；只记录，不并行")
    parser.add_argument("--gpus", default=None, help="抽签用的 GPU（取第一张）")
    parser.add_argument("--pkg", default="robomme_hard")
    parser.add_argument("--release", default=None, help="重建 sampling 的 release（缺省 _extract.DEFAULT_RELEASE）")
    parser.add_argument("--code-root", default=str(DEFAULT_CODE_ROOT),
                        help="抽签／校验代码所在仓库检出（缺省本文件所在仓库）")
    parser.add_argument("--dry-run", action="store_true", help="只打印计划，不起环境、不写盘")
    args = parser.parse_args(argv)
    try:
        bootstrap(args.code_root)
        print(f"APPEND_CODE code_root={CODE_ROOT} hard_specs={H.__file__} draw={_draw.__file__}", flush=True)
        task, tier = parse_cell(args.cell)
        if args.max_reset_attempts <= 0:
            raise AppendError("--max-reset-attempts 须为正整数")
        plan = plan_append(Path(args.frozen_root), Path(args.shard_dir), task, tier, args.extra)
        _print_plan(plan, args)
        if plan["deficit"] <= 0:
            print(f"# 注意：{task}@{tier} 已满额（deficit={plan['deficit']}），追加的候选只作备用", flush=True)
        if args.dry_run:
            print("APPEND_DRY_RUN=PASS（未起环境、未写盘）", flush=True)
            return 0
        new_rows, info = draw_extra(plan["frozen"][0], task, tier, plan["per_env"], args.extra, allow_spares=False,
                                    frozen_rows=plan["frozen"][1], shard_rows=plan["shard"][1],
                                    max_reset_attempts=args.max_reset_attempts, draw_one=draw_one,
                                    sampling_check=sampling_check, pkg=args.pkg, release=args.release, gpus=args.gpus)
        result = apply_append(plan, new_rows, info, max_reset_attempts=args.max_reset_attempts, pkg=args.pkg)
    except (AppendError, ValueError, RuntimeError) as exc:  # SpecsError 是 ValueError、RolloutError 是 RuntimeError
        print(f"APPEND_REASON {type(exc).__name__}: {exc}", flush=True)
        print(f"APPEND_CANDIDATES=FAIL cell={args.cell} reason={type(exc).__name__}", flush=True)
        return 1
    print(f"APPEND_BACKUPS {' '.join(result['backups'])}", flush=True)
    print(f"APPEND_CANDIDATES=PASS cell={task}@{tier} extra={result['appended']} "
          f"per_env={result['per_env_old']}→{result['per_env_new']} frozen_identity={result['frozen_identity'][:12]} "
          f"shard_identity={result['shard_identity'][:12]} backfill_selected={len(result['backfill_selected'])} "
          f"shards_updated={len(result['updated_shards'])}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
