"""只读两轮结果，逐身份对账并比较交换覆盖、均衡和净置换。"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path

from ..configs import DIFFICULTIES, TASK_ORDER, SOURCE_DIFFICULTY

TASKS = ("VideoUnmaskSwap", "ButtonUnmaskSwap", "VideoRepick")
LEVELS = ("mother",) + DIFFICULTIES
NORMAL_ERRORS = {"SwapCollisionError", "SwapBindingError", "SceneGenerationError",
                 "FailsafeTimeout", "PlannerExhausted", "ScrewPlanFailure", "DatasetGenerationError"}
OLD_ROOT = Path(__file__).resolve().parents[3] / "artifacts/xhard/xhard-1012-coll"


def expected_identities(manifest):
    """每个母条目展开母档与五档，拒绝清单本身的重复或未知任务。"""
    tasks = manifest["tasks"]
    if set(tasks) != set(TASKS):
        raise ValueError("母清单必须恰含三个交换任务")
    expected = []
    for task in TASKS:
        for item in sorted(tasks[task], key=lambda r: int(r["episode"])):
            episode, seed = int(item["episode"]), int(item["seed"])
            if item["source_difficulty"] != SOURCE_DIFFICULTY[task]:
                raise ValueError(f"{task} 母来源难度不符")
            expected.extend((task, episode, seed, level) for level in LEVELS)
    if len(expected) != len(set(expected)):
        raise ValueError("母清单身份重复")
    return expected


def identity_of(record, directory_level=None):
    """档位来自角色及难度，母来源也必须与官方配置一致。"""
    task = str(record["task"]).removesuffix("XHard")
    episode = int(record["mother_episode"] if "mother_episode" in record else record["episode"])
    seed = int(record["seed"])
    difficulty, role = record.get("difficulty"), record.get("card_role")
    if role == "mother":
        if difficulty != SOURCE_DIFFICULTY.get(task):
            raise ValueError("母档难度不符")
        level = "mother"
    elif role == "xhard":
        level = difficulty
    elif role is None:
        level = difficulty if difficulty in DIFFICULTIES else "mother"
        if level == "mother" and difficulty != SOURCE_DIFFICULTY.get(task):
            raise ValueError("无角色记录的母档难度不符")
    else:
        raise ValueError("未知卡片角色")
    if directory_level is not None and directory_level != level:
        raise ValueError("目录档位与记录身份不符")
    if level not in LEVELS or task not in TASKS:
        raise ValueError("未知任务或档位")
    return task, episode, seed, level


def classify(record):
    """独立成功字段；任务正常拒绝与读取/进程/接口故障明确分离。"""
    ok, success = record.get("ok"), record.get("task_success")
    if not isinstance(ok, bool) or not isinstance(success, (bool, int)) or success not in (0, 1):
        return "unknown"
    if ok:
        return "ok" if success else "task_reject"
    if success:
        return "unknown"
    failure = record.get("failure_class")
    if failure in ("infra", "code") or record.get("quarantined"):
        return "infra"
    if failure != "task" or record.get("error_type") not in NORMAL_ERRORS:
        return "unknown"
    rejection = record.get("rejection") or {}
    detail = record.get("detail") or {}
    if (rejection.get("reason") == "uncertified" or
            isinstance(detail, dict) and detail.get("check") == "uncertified" or
            "按钮包络读取失败" in str(record.get("error", ""))):
        return "infra"
    return "task_reject"


def read_records(root):
    """优先单一根账本，否则读取各档账本；保留重复，禁止静默取最后一条。"""
    root = Path(root)
    direct = root / "episode_results.jsonl"
    paths = [(direct, None)] if direct.is_file() else [
        (p, level) for level in LEVELS for p in sorted((root / level).rglob("episode_results.jsonl"))]
    rows = []
    for path, level in paths:
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                if not isinstance(record, dict):
                    raise ValueError("结果必须是对象")
                key = identity_of(record, level)
                state = classify(record)
            except (ValueError, KeyError, TypeError):
                record, key, state = {"raw": line}, None, "unknown"
            rows.append((key, record, state, str(path), line_no))
    return rows


def reconcile(root, expected):
    """缺项、重复、非预期身份与未知状态分别留证。"""
    expected_set, groups = set(expected), defaultdict(list)
    unknown, extra = [], []
    rows = read_records(root)
    for key, record, state, path, line in rows:
        evidence = dict(identity=key, state=state, path=path, line=line)
        if key is None or state == "unknown":
            unknown.append(evidence)
        if key is not None and key not in expected_set:
            extra.append(evidence)
        if key is not None:
            groups[key].append((record, state))
    missing = [key for key in expected if key not in groups]
    duplicates = [dict(identity=key, count=len(records)) for key, records in groups.items() if len(records) > 1]
    counts = Counter(state for key in expected for _, state in groups.get(key, []))
    summary = dict(expected=len(expected), seen=len(rows), missing=len(missing),
                   dup=sum(row["count"]-1 for row in duplicates), unknown=len(unknown)+len(extra),
                   ok=counts["ok"], task_reject=counts["task_reject"], infra=counts["infra"])
    summary["complete"] = not (missing or duplicates or unknown or extra or summary["infra"])
    unique = {key: records[0] for key, records in groups.items() if len(records) == 1 and key in expected_set}
    return {"summary": summary, "missing": missing, "duplicates": duplicates,
            "unknown_states": unknown, "unexpected_identities": extra}, unique


def plan_metrics(record):
    """有规划证据才计算置换；母档没有规划时不凭空宣称恒等。"""
    plan = record.get("swap_plan")
    result = dict(task_success=record.get("task_success"), ok=record.get("ok"),
                  error_type=record.get("error_type"), stage=record.get("stage"),
                  timestep=record.get("timestep_count", record.get("timesteps")),
                  slot_pair_kinds=None, usage=None, spread_full=None, spread_prefix=None,
                  net_identity=None)
    if not isinstance(plan, dict):
        return result
    pairs, usage = plan.get("pairs", []), plan.get("usage")
    slot_pairs = plan.get("slot_pairs")
    result.update(usage=usage, spread_full=plan.get("spread_full"),
                  spread_prefix=plan.get("spread_prefix", max(usage)-min(usage) if usage else None))
    if slot_pairs is not None:
        result["slot_pair_kinds"] = len({tuple(sorted(pair)) for pair in slot_pairs})
    elif usage is not None:
        # v1 没有槽对，按对象交换推演槽对再计种类。
        slot_of = list(range(len(usage)))
        keys = []
        for a, b, *_ in pairs:
            keys.append(tuple(sorted((slot_of[a], slot_of[b]))))
            slot_of[a], slot_of[b] = slot_of[b], slot_of[a]
        result["slot_pair_kinds"] = len(set(keys))
    if usage is not None:
        slot_of = list(range(len(usage)))
        for a, b, *_ in pairs:
            slot_of[a], slot_of[b] = slot_of[b], slot_of[a]
        result["net_identity"] = slot_of == list(range(len(usage)))
    return result


def build_report(v1, v2, manifest):
    expected = expected_identities(manifest)
    audits, data = {}, {}
    for label, root in (("v1", v1), ("v2", v2)):
        audits[label], data[label] = reconcile(root, expected)
    rows, distributions = [], {}
    for key in expected:
        row = dict(task=key[0], mother_episode=key[1], seed=key[2], level=key[3])
        for label in ("v1", "v2"):
            record_state = data[label].get(key)
            row[label] = None if record_state is None else dict(
                state=record_state[1], **plan_metrics(record_state[0]))
        rows.append(row)
    for label in ("v1", "v2"):
        groups = {}
        for task in TASKS:
            for level in LEVELS:
                metrics = [r[label] for r in rows if r["task"] == task and r["level"] == level and r[label]]
                prefix = Counter(str(m["spread_prefix"]) for m in metrics if m["spread_prefix"] is not None)
                full = Counter(str(m["spread_full"]) for m in metrics if m["spread_full"] is not None)
                known = [m["net_identity"] for m in metrics if m["net_identity"] is not None]
                groups[f"{task}/{level}"] = dict(spread_prefix=dict(prefix), spread_full=dict(full),
                    net_identity_count=sum(known), net_identity_denominator=len(known),
                    net_identity_ratio=sum(known)/len(known) if known else None)
        distributions[label] = groups
    return dict(audits=audits, rows=rows, distributions=distributions,
                seeds=len(expected)//len(LEVELS), rows_count=len(rows))


def validate_outputs(v1, out_md, out_json):
    """解析路径和符号链接后拒绝旧根，所有目标必须未存在且互不相同。"""
    paths = [Path(out_md), Path(out_json)]
    roots = [Path(v1).resolve(), OLD_ROOT.resolve()]
    for path in paths:
        resolved = path.resolve()
        if any(resolved == root or resolved.is_relative_to(root) for root in roots):
            raise ValueError(f"禁止写入旧目录：{path}")
        if path.exists() or path.is_symlink():
            raise ValueError(f"目标已存在：{path}")
    if paths[0].resolve() == paths[1].resolve():
        raise ValueError("两个报告目标必须不同")


def markdown_report(report):
    """逐母 seed 对照正文，失败状态及独立成功字段都展示。"""
    lines = ["# 交换配对两轮对比", "", "任务执行成功字段独立报告；基础设施身份不计作正常剔除。", "",
             "|任务|母 episode|seed|档位|v1 状态／成功|v2 状态／成功|v1／v2 槽对种类|v1／v2 参与|v1／v2 极差（整条／前缀）|v1／v2 帧数|",
             "|---|---:|---:|---|---|---|---|---|---|---|"]
    for row in report["rows"]:
        metrics = [row[label] or {} for label in ("v1", "v2")]
        def value(m, key):
            return str(m.get(key, "缺失"))
        cells = [row["task"], str(row["mother_episode"]), str(row["seed"]), row["level"]]
        cells += [f"{value(m, 'state')}／{value(m, 'task_success')}（{value(m, 'error_type')}／{value(m, 'stage')}）" for m in metrics]
        for key in ("slot_pair_kinds", "usage"):
            cells.append("／".join(value(m, key) for m in metrics))
        cells.append("／".join(f"{value(m, 'spread_full')}／{value(m, 'spread_prefix')}" for m in metrics))
        cells.append("／".join(value(m, "timestep") for m in metrics))
        lines.append("|"+"|".join(cells)+"|")
    lines.extend(["", "## 对账与按任务档位分布", "", "```json",
                  json.dumps({"audits": report["audits"], "distributions": report["distributions"]},
                             ensure_ascii=False, indent=2), "```", ""])
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ("v1", "v2", "seeds", "out-md", "out-json"):
        parser.add_argument("--"+flag, required=True, type=Path)
    args = parser.parse_args(argv)
    validate_outputs(args.v1, args.out_md, args.out_json)
    report = build_report(args.v1, args.v2, json.loads(args.seeds.read_text(encoding="utf-8")))
    # 所有只读对账完成之后才创建报告目录；排他创建再次防止覆盖竞争。
    for path, payload in ((args.out_md, markdown_report(report)),
                          (args.out_json, json.dumps(report, ensure_ascii=False, indent=2)+"\n")):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8") as handle:
            handle.write(payload)
    s = report["audits"]["v2"]["summary"]
    verdict = "DONE" if s["complete"] else "INCOMPLETE"
    print(f"XHARD_FULL_DERIVE={verdict} " + " ".join(f"{key}={s[key]}" for key in
          ("expected", "seen", "missing", "dup", "unknown", "ok", "task_reject", "infra")))
    passed = all(audit["summary"]["complete"] for audit in report["audits"].values())
    print(f"REPORT_V1V2={'PASS' if passed else 'FAIL'} seeds={report['seeds']} rows={report['rows_count']}")
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())

