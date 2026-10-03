"""G9 固定检查集：从 V9 交付集每任务取 12 局，16 任务 × 12 局 = 192（1003 噪声基线计划第一部分「固定检查集」、
第二部分 §一、§二 S1 行）。噪声基线与以后每次回归都用这同一批局。

选局规则（确定、可重算，只读包内规格，不读 ``artifacts/``）：

1. 数据源：包内 V9 规格 ``src/robomme_hard/env_metadata/test-hard/xhard{1..5}/specs.jsonl``；交付行＝
   ``hard_specs.delivered(row)`` 为真的行（``selected`` 且 ``rollout.status == "ok"``）。交付行与 builder episode 号
   直接复用 ``hard_regression.delivery_index``（与 ``hard_builder._test_hard_entries`` 同一排序：档序主序、档内
   ``candidate`` 升序、xhard0 前置局数在前），本模块不另造一套。
2. 每任务 12 局，在该任务出现的各档之间按交付局数比例分配，最大余数法；余数相同按档位升序（xhard1 优先）。
3. 每格取交付行里 ``candidate`` 升序最小的 N 个。
4. ``builder_episode`` 是开关 ``ROBOMME_HARD_XHARD0_IN_TEST_HARD`` 为 0（默认，V9 每任务 50 局）时该身份在
   ``BenchmarkEnvBuilder(env_id=task, dataset="test-hard")`` 里的 episode 号（0～49）。开关为 1 时直接报错拒绝。

行内排序：(16 任务规范序, tier, candidate)。规范序取 ``hard_specs.ALL_TASKS``——它与
``scripts/injection-dev/seed_layout.py::ALL_TASKS`` 逐字相同（hard_specs 注释约定、测试另行断言）；后者所在目录名
带连字符、不能按包导入，所以这里不直接导入它。

冻结文件 ``scripts/configs/gate-set-v9-192.json``：``{"schema", "source", "rule", "rows", "sha256"}``，
``sha256`` 是剔掉该键后 canonical JSON（``sort_keys=True, ensure_ascii=False, separators=(",", ":")``）的 sha256。

用法（仓库根）::

    uv run --no-sync python scripts/parity/gate_set.py build --out scripts/configs/gate-set-v9-192.json
    uv run --no-sync python scripts/parity/gate_set.py check --path scripts/configs/gate-set-v9-192.json
    uv run --no-sync python scripts/parity/gate_set.py export --kind generate --out <dir>/g9.identities.jsonl
    uv run --no-sync python scripts/parity/gate_set.py export --kind env-digest --out <dir>/g9.env-digest.json

``check`` 末行判定 ``GATE_SET=PASS tasks=16 per_task=12 total=192 in_delivery=192 sha=<前12位>``（不符为 FAIL）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from fractions import Fraction
from pathlib import Path
from typing import Any, Iterable

REPO = Path(__file__).resolve().parents[2]
for _extra in (REPO / "src", REPO):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

SCHEMA = "gate-set-v9/1"
PER_TASK = 12
N_TASKS = 16
DEFAULT_PATH = REPO / "scripts" / "configs" / "gate-set-v9-192.json"
ROW_KEYS = ("task", "tier", "candidate", "seed", "spec_sha256", "builder_episode")
XHARD0_ENV = "ROBOMME_HARD_XHARD0_IN_TEST_HARD"
RULE = ("V9 包内规格交付行（hard_specs.delivered），每任务 12 局按各档交付局数比例最大余数法分配（余数相同档位升序优先），"
        "每格取 candidate 升序最小的 N 个；builder_episode 按 XHARD0_IN_TEST_HARD=0 的 test-hard 编号")


class GateSetError(RuntimeError):
    """检查集构建、读取或核对失败。"""


# ── 依赖（复用 hard_parity／hard_regression 的轻量入口，不导入仿真）─────────────────


def _hs():
    from scripts.parity import hard_parity

    return hard_parity.hard_specs_light()


def _delivery_index(specs_root: str) -> dict[tuple[str, str, int], dict[str, Any]]:
    from scripts.parity import hard_regression

    return hard_regression.delivery_index(specs_root)


def _require_xhard0_off(hs) -> None:
    """builder_episode 只对开关为 0 的编号定义；开关为 1（环境变量或已加载模块）一律拒绝。"""
    if os.environ.get(XHARD0_ENV, "0") == "1" or bool(getattr(hs, "XHARD0_IN_TEST_HARD", False)):
        raise GateSetError(f"{XHARD0_ENV}=1：G9 的 builder_episode 只按开关为 0（xhard0 不前置）定义，拒绝构建")
    if hs.xhard0_prefix() != 0:
        raise GateSetError(f"xhard0 前置局数应为 0，实为 {hs.xhard0_prefix()}")


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def payload_sha256(obj: dict[str, Any]) -> str:
    """剔掉顶层 ``sha256`` 键后 canonical JSON 的 sha256。"""
    body = {k: v for k, v in obj.items() if k != "sha256"}
    return hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()


# ── 分配与选局 ──────────────────────────────────────────────────────────────


def allocate(counts: dict[str, int], total: int = PER_TASK) -> dict[str, int]:
    """最大余数法：``counts`` 为 {tier: 交付局数}，按比例把 ``total`` 局分给各档；余数相同按档位升序优先。
    结果每档不超过该档交付局数（比例份额 ≤ 交付局数时自然成立，另作断言）。"""
    tiers = sorted(t for t, n in counts.items() if n > 0)
    whole = sum(counts[t] for t in tiers)
    if whole < total:
        raise GateSetError(f"交付局数合计 {whole} < {total}：{counts}")
    shares = {t: Fraction(total * counts[t], whole) for t in tiers}
    alloc = {t: int(shares[t]) for t in tiers}  # Fraction 非负，int() 即向下取整
    left = total - sum(alloc.values())
    order = sorted(tiers, key=lambda t: (-(shares[t] - alloc[t]), t))
    for tier in order[:left]:
        alloc[tier] += 1
    for tier in tiers:
        if alloc[tier] > counts[tier]:
            raise GateSetError(f"{tier} 分到 {alloc[tier]} 局，超过交付局数 {counts[tier]}")
    return alloc


def _specs_root(hs, specs_root: str | Path | None) -> str:
    """缺省固定为包内规格根（不读 ``ROBOMME_HARD_SPECS_ROOT``，冻结清单只认包内 V9 规格）。"""
    return str(Path(specs_root).resolve() if specs_root is not None else hs.PACKAGED_SPECS_ROOT)


def build_gate_set(specs_root: str | Path | None = None) -> list[dict[str, Any]]:
    """按模块文档的规则算出 192 行 ``{task, tier, candidate, seed, spec_sha256, builder_episode}``，
    按 (任务规范序, tier, candidate) 排序。"""
    hs = _hs()
    _require_xhard0_off(hs)
    index = _delivery_index(_specs_root(hs, specs_root))
    rows: list[dict[str, Any]] = []
    for task in hs.ALL_TASKS:
        by_tier: dict[str, list[dict[str, Any]]] = {}
        for (t, tier, _seed), hit in index.items():
            if t == task:
                if not hs.delivered(hit["row"]):
                    raise GateSetError(f"delivery_index 返回了非交付行：{task}@{tier} seed={_seed}")
                by_tier.setdefault(tier, []).append(hit)
        alloc = allocate({tier: len(hits) for tier, hits in by_tier.items()})
        for tier in sorted(alloc):
            chosen = sorted(by_tier[tier], key=lambda h: int(h["row"]["candidate"]))[: alloc[tier]]
            for hit in chosen:
                row = hit["row"]
                rows.append({
                    "task": task,
                    "tier": tier,
                    "candidate": int(row["candidate"]),
                    "seed": int(row["seed"]),
                    "spec_sha256": row["spec_sha256"],
                    "builder_episode": int(hit["builder_episode"]),
                })
    order = {task: i for i, task in enumerate(hs.ALL_TASKS)}
    rows.sort(key=lambda r: (order[r["task"]], r["tier"], r["candidate"]))
    return rows


def allocation_table(rows: Iterable[dict[str, Any]]) -> dict[str, dict[str, int]]:
    """{task: {tier: 局数}}，报告与测试用。"""
    table: dict[str, dict[str, int]] = {}
    for row in rows:
        cell = table.setdefault(row["task"], {})
        cell[row["tier"]] = cell.get(row["tier"], 0) + 1
    return table


def source_headers(specs_root: str | Path | None = None) -> dict[str, dict[str, Any]]:
    """各档 specs header 的 ``delivery_sha256`` 与 ``identity_sha256``（有则记），写进冻结文件的 ``source``。"""
    hs = _hs()
    root = Path(_specs_root(hs, specs_root))
    out: dict[str, dict[str, Any]] = {}
    for tier in hs.TIERS:
        path = root / tier / "specs.jsonl"
        if not path.is_file():
            continue
        with path.open(encoding="utf-8") as stream:
            header = json.loads(stream.readline())
        out[tier] = {key: header[key] for key in ("delivery_sha256", "identity_sha256") if key in header}
    return out


def build_payload(specs_root: str | Path | None = None) -> dict[str, Any]:
    obj: dict[str, Any] = {
        "schema": SCHEMA,
        "source": source_headers(specs_root),
        "rule": RULE,
        "rows": build_gate_set(specs_root),
    }
    obj["sha256"] = payload_sha256(obj)
    return obj


def dumps_payload(obj: dict[str, Any]) -> str:
    """冻结文件的确定字节：sort_keys、缩进 1、末尾换行（``check`` 逐字节比它）。"""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, indent=1) + "\n"


def load_gate_set(path: str | Path = DEFAULT_PATH) -> list[dict[str, Any]]:
    """读冻结 json，校验 schema、行键与顶层 ``sha256``；不一致抛 ``GateSetError``。返回行列表。"""
    obj = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(obj, dict) or obj.get("schema") != SCHEMA:
        raise GateSetError(f"{path}：schema 应为 {SCHEMA}")
    want = obj.get("sha256")
    got = payload_sha256(obj)
    if want != got:
        raise GateSetError(f"{path}：sha256 不符（文件 {want}，重算 {got}）")
    rows = obj.get("rows")
    if not isinstance(rows, list) or any(not isinstance(r, dict) or set(r) != set(ROW_KEYS) for r in rows):
        raise GateSetError(f"{path}：rows 须为键恰为 {ROW_KEYS} 的对象列表")
    return rows


# ── 导出给下游入口 ──────────────────────────────────────────────────────────


def to_generate_identities(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """``hard_parity.py generate／compare／import-delivery --identities`` 的身份：``[{task, tier, seed}]``。

    ``hard_parity.read_identity_subset`` 按文件后缀读：``.jsonl`` 每行一个 ``{task, tier|difficulty, seed}``；
    ``.json`` 为列表或带 ``rows``／``delivered`` 的对象（行带 ``source`` 时只取 ``v9-new``，本函数不写 ``source``）。
    写文件用 ``write_generate_identities``（jsonl）。"""
    return [{"task": r["task"], "tier": r["tier"], "seed": int(r["seed"])} for r in rows]


def to_env_digest_identities(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """``hard_regression.py env-digest --identities`` 的身份：json 列表 ``[{task, source_episode, seed, builder_episode}]``。

    ``_env_digest_one`` 用 ``builder.resolve_identity(builder_episode)`` 核对 seed 与 ``source_episode``；新值档的
    resolve_identity 不带 ``source_episode``，按 -1 比较，所以这里固定写 -1。写文件用 ``write_env_digest_identities``。"""
    return [{"task": r["task"], "source_episode": -1, "seed": int(r["seed"]),
             "builder_episode": int(r["builder_episode"])} for r in rows]


def to_eval_keys(rows: Iterable[dict[str, Any]]) -> set[str]:
    """V8 评估链路身份键 ``<task>_<tier>_<seed>``（与 ``scripts/eval-official/env_client.py::v8_key`` 同式）。"""
    return {f"{r['task']}_{r['tier']}_{int(r['seed'])}" for r in rows}


def write_generate_identities(rows: Iterable[dict[str, Any]], path: str | Path) -> Path:
    """写 jsonl（每行一个身份），供 ``hard_parity.py --identities``；后缀必须是 ``.jsonl``。"""
    path = Path(path)
    if path.suffix != ".jsonl":
        raise GateSetError(f"generate 身份文件须以 .jsonl 结尾（read_identity_subset 按后缀判格式）：{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(item, ensure_ascii=False) + "\n" for item in to_generate_identities(rows)),
                    encoding="utf-8")
    return path


def write_env_digest_identities(rows: Iterable[dict[str, Any]], path: str | Path) -> Path:
    """写 json 列表，供 ``hard_regression.py env-digest --identities``（它用 ``json.loads`` 读整个文件）。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(to_env_digest_identities(rows), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return path


# ── 核对 ────────────────────────────────────────────────────────────────────


def check(path: str | Path, specs_root: str | Path | None = None) -> tuple[bool, str]:
    """重算清单，与冻结文件逐字节比；另核 16 任务 × 12 局、每行属交付集。返回 (是否通过, 判定行)。"""
    reasons: list[str] = []
    path = Path(path)
    fresh = build_payload(specs_root)
    rows = fresh["rows"]
    try:
        frozen_bytes = path.read_bytes()
    except OSError as exc:
        frozen_bytes = b""
        reasons.append(f"读不到冻结文件：{exc}")
    if frozen_bytes and frozen_bytes != dumps_payload(fresh).encode("utf-8"):
        reasons.append("冻结文件与重算结果字节不同")
    if frozen_bytes:
        try:
            load_gate_set(path)
        except (GateSetError, ValueError) as exc:
            reasons.append(str(exc))
    table = allocation_table(rows)
    per_task = sorted({sum(cell.values()) for cell in table.values()})
    hs = _hs()
    index = _delivery_index(_specs_root(hs, specs_root))
    in_delivery = sum(
        1 for r in rows
        if (hit := index.get((r["task"], r["tier"], r["seed"]))) is not None
        and hs.delivered(hit["row"]) and int(hit["row"]["candidate"]) == r["candidate"]
        and hit["row"]["spec_sha256"] == r["spec_sha256"] and hit["builder_episode"] == r["builder_episode"])
    if len(table) != N_TASKS or per_task != [PER_TASK] or len(rows) != N_TASKS * PER_TASK:
        reasons.append(f"规模不符：tasks={len(table)} per_task={per_task} total={len(rows)}")
    if in_delivery != len(rows):
        reasons.append(f"有 {len(rows) - in_delivery} 行不在交付集")
    ok = not reasons
    per = per_task[0] if len(per_task) == 1 else "/".join(map(str, per_task))
    line = (f"GATE_SET={'PASS' if ok else 'FAIL'} tasks={len(table)} per_task={per} total={len(rows)} "
            f"in_delivery={in_delivery} sha={fresh['sha256'][:12]}")
    for reason in reasons:
        print(f"GATE_SET_REASON {reason}", flush=True)
    return ok, line


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="G9 固定检查集（V9 交付集 16 任务 × 12 局 = 192）")
    parser.add_argument("--specs-root", default=None, help="规格根（缺省为包内 V9 规格；冻结清单只认包内）")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_build = sub.add_parser("build", help="写冻结 json")
    p_build.add_argument("--out", type=Path, default=DEFAULT_PATH)
    p_check = sub.add_parser("check", help="重算并与冻结文件逐字节比较")
    p_check.add_argument("--path", type=Path, default=DEFAULT_PATH)
    p_export = sub.add_parser("export", help="从冻结文件导出下游身份清单")
    p_export.add_argument("--kind", choices=("generate", "env-digest"), required=True)
    p_export.add_argument("--path", type=Path, default=DEFAULT_PATH, help="冻结清单（读前校验 sha256）")
    p_export.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    if args.cmd == "build":
        obj = build_payload(args.specs_root)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(dumps_payload(obj), encoding="utf-8")
        table = allocation_table(obj["rows"])
        for task, cell in table.items():
            print(f"GATE_SET_ALLOC {task} " + " ".join(f"{t}={n}" for t, n in sorted(cell.items())), flush=True)
        print(f"GATE_SET_BUILT path={args.out} total={len(obj['rows'])} sha={obj['sha256'][:12]}", flush=True)
        return 0
    if args.cmd == "check":
        ok, line = check(args.path, args.specs_root)
        print(line, flush=True)
        return 0 if ok else 1
    rows = load_gate_set(args.path)
    if args.kind == "generate":
        out = write_generate_identities(rows, args.out)
    else:
        out = write_env_digest_identities(rows, args.out)
    print(f"GATE_SET_EXPORT kind={args.kind} out={out} n={len(rows)}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
