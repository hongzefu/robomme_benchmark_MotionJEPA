"""Astra 费用守卫：常驻汇总两侧全部规划请求的 ``usage`` × 单价，到线即在 ``group_*/`` 下写 ``STOP.json``。

计划：``1003-oracle-subgoal-groundsg-eval-plan.md`` 第二部分 1.5「费用上限」与红线 R4。

- 扫描对象：每个 ``--root`` 下（递归）凡是与 ``request.json`` 同目录的 ``response.json``——这正是 Astra
  ``Planner`` 的 spool 布局 ``<spool>/<uuid>/{request.json,response.json}``；监视器的
  ``monitor_inputs/tNNNN/response.json`` 旁边没有 ``request.json``，不计。``ResponsesClient`` 写的
  ``response.json`` 里 ``usage`` 是 OpenAI Responses API 原样的 usage 对象。
- 计价：``(input_tokens - cached_tokens) × input + cached_tokens × cached_input + output_tokens × output``，
  单价单位「美元 / 百万 token」，由 ``--prices`` 配置文件给（不写死）。``reasoning_tokens`` 已含在
  ``output_tokens`` 里，只统计不另计价（配置 ``"reasoning_billed_separately": true`` 时另按 output 单价加计）。
  缺字段按 0 计，并计入 ``missing_fields`` 告警计数；``status=error`` 且无 ``usage`` 的响应计入 ``no_usage``。
- 累计账本：``--ledger`` 指向的 JSON 先读入（本机预检的账本拷到 GL 后接着累计），按请求 uuid 去重，
  每轮扫描后原子写回。
- 到线判定：``累计 + max(1, 在途数) × 一次请求最坏花费 > --cap``（在途＝有 ``api_started.json`` 而无
  ``response.json``；最坏花费＝已见最大输入 token × input 单价 + ``--max-output-tokens``(2048) × output 单价）。
  到线时在每个 ``group_*`` 目录（``--root`` 的祖先或子孙中名为 ``group_<数字>`` 的目录）写 ``STOP.json``，
  打印 ``ASTRA_COST=STOP usd=… cap=…``。Astra 自带两个停机口都读它：``ResponsesClient._send`` 每次发送前、
  驱动每局开跑前。
- 输出：累计变化时（及首轮）打印 ``ASTRA_COST usd=<累计> calls=<n> …``。

单价配置示例（``--prices``）::

    {"model": "gpt-6-astra", "unit": "usd_per_1m_tokens",
     "input": 1.25, "cached_input": 0.125, "output": 10.0,
     "source": "<OpenAI 价目页 URL>", "checked_at": "2026-10-05"}

（数值仅为格式示意，开工后查官方价目填写并记入 launch.md。）
"""
from __future__ import annotations

import argparse
import json
import os
import re
import signal
import sys
import time
from pathlib import Path

LEDGER_SCHEMA = "astra-cost-ledger/1"
GROUP_RE = re.compile(r"^group_\d+$")
#: 有效单价单位
PRICE_UNIT = "usd_per_1m_tokens"


def load_prices(path: Path) -> dict:
    prices = json.loads(Path(path).read_text())
    if prices.get("unit", PRICE_UNIT) != PRICE_UNIT:
        raise ValueError(f"单价单位须为 {PRICE_UNIT}，实为 {prices.get('unit')!r}")
    for key in ("input", "output"):
        if not isinstance(prices.get(key), (int, float)) or prices[key] < 0:
            raise ValueError(f"单价配置缺少非负数值 {key!r}")
    prices.setdefault("cached_input", prices["input"])
    prices.setdefault("reasoning_billed_separately", False)
    return prices


def _get(usage: dict, *keys, warn: list) -> int:
    value = usage
    for key in keys:
        if not isinstance(value, dict) or key not in value or value[key] is None:
            warn.append(".".join(keys))
            return 0
        value = value[key]
    try:
        return int(value)
    except (TypeError, ValueError):
        warn.append(".".join(keys))
        return 0


def price_usage(usage: dict, prices: dict) -> tuple[float, dict, list]:
    """一次请求的花费；返回 ``(usd, tokens, 缺失字段列表)``。"""
    warn: list = []
    tokens = {
        "input_tokens": _get(usage, "input_tokens", warn=warn),
        "output_tokens": _get(usage, "output_tokens", warn=warn),
        "cached_tokens": _get(usage, "input_tokens_details", "cached_tokens", warn=warn),
        "reasoning_tokens": _get(usage, "output_tokens_details", "reasoning_tokens", warn=warn),
    }
    cached = min(tokens["cached_tokens"], tokens["input_tokens"])
    usd = ((tokens["input_tokens"] - cached) * prices["input"] + cached * prices["cached_input"]
           + tokens["output_tokens"] * prices["output"]) / 1e6
    if prices.get("reasoning_billed_separately"):
        usd += tokens["reasoning_tokens"] * prices["output"] / 1e6
    return usd, tokens, warn


def new_ledger() -> dict:
    return {"schema": LEDGER_SCHEMA, "calls": {}}


def load_ledger(path: Path | None) -> dict:
    if path is None or not Path(path).is_file():
        return new_ledger()
    ledger = json.loads(Path(path).read_text())
    if ledger.get("schema") != LEDGER_SCHEMA:
        raise ValueError(f"账本 schema 应为 {LEDGER_SCHEMA}：{path}")
    return ledger


def save_ledger(path: Path, ledger: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n")
    os.replace(tmp, path)


def scan(roots: list[Path], ledger: dict, prices: dict) -> dict:
    """扫描全部根，把新出现的规划响应计入账本；返回本轮统计（在途数、本轮新增等）。"""
    pending = 0
    added = 0
    for root in roots:
        root = Path(root)
        if not root.exists():
            continue
        for request in root.rglob("request.json"):
            call_dir = request.parent
            response = call_dir / "response.json"
            if not response.is_file():
                if (call_dir / "api_started.json").is_file():
                    pending += 1
                continue
            rid = call_dir.name
            if rid in ledger["calls"]:
                continue
            try:
                body = json.loads(response.read_text())
            except (OSError, ValueError):
                continue  # 正在写（Astra 用原子替换，理论上不会出现）；下一轮再读
            usage = body.get("usage")
            if isinstance(usage, dict):
                usd, tokens, warn = price_usage(usage, prices)
            else:
                usd, tokens, warn = 0.0, {}, ["usage"]
            ledger["calls"][rid] = {"usd": usd, **tokens, "missing": warn, "status": body.get("status"),
                                    "path": str(response), "counted_at": time.time()}
            added += 1
    return {"pending": pending, "added": added}


def totals(ledger: dict) -> dict:
    calls = ledger["calls"].values()
    return {
        "usd": sum(c["usd"] for c in calls),
        "calls": len(ledger["calls"]),
        "max_input": max((c.get("input_tokens", 0) for c in calls), default=0),
        "missing_fields": sum(1 for c in calls if c.get("missing") and c["missing"] != ["usage"]),
        "no_usage": sum(1 for c in calls if c.get("missing") == ["usage"]),
    }


def worst_request_usd(max_input: int, prices: dict, max_output_tokens: int) -> float:
    return (max_input * prices["input"] + max_output_tokens * prices["output"]) / 1e6


def group_dirs(roots: list[Path]) -> list[Path]:
    """当前全部 ``group_*`` 目录：各根自身及其祖先中名为 group_<n> 的，加上根下（≤3 层）的。"""
    found: set[Path] = set()
    for root in roots:
        root = Path(root).resolve()
        for candidate in (root, *root.parents):
            if GROUP_RE.match(candidate.name):
                found.add(candidate)
        if root.is_dir():
            for depth in ("*", "*/*", "*/*/*"):
                for path in root.glob(depth):
                    if path.is_dir() and GROUP_RE.match(path.name):
                        found.add(path)
    return sorted(found)


def write_stops(roots: list[Path], summary: dict) -> list[Path]:
    written = []
    for group in group_dirs(roots):
        stop = group / "STOP.json"
        if stop.exists():
            continue
        tmp = group / "STOP.json.tmp"
        tmp.write_text(json.dumps({"reason": "astra_cost_cap", **summary, "time": time.time()}, indent=2) + "\n")
        os.replace(tmp, stop)
        written.append(stop)
    return written


def cycle(roots: list[Path], ledger: dict, prices: dict, cap: float, max_output_tokens: int) -> dict:
    """一轮：扫描、算累计与投影、到线写 STOP。返回本轮摘要。"""
    stats = scan(roots, ledger, prices)
    tot = totals(ledger)
    worst = worst_request_usd(tot["max_input"], prices, max_output_tokens)
    projected = tot["usd"] + max(1, stats["pending"]) * worst
    summary = {"usd": round(tot["usd"], 6), "calls": tot["calls"], "pending": stats["pending"],
               "worst_request_usd": round(worst, 6), "projected_usd": round(projected, 6), "cap": cap,
               "missing_fields": tot["missing_fields"], "no_usage": tot["no_usage"], "added": stats["added"]}
    summary["stop"] = projected > cap
    summary["stops_written"] = [str(p) for p in write_stops(roots, summary)] if summary["stop"] else []
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Astra 费用守卫（每 --interval 秒汇总一次）")
    parser.add_argument("--root", action="append", required=True,
                        help="spool 根（可多个，本机预检与 GL 各一个）；也可直接给 group_*/ 或其上层目录")
    parser.add_argument("--prices", required=True, help="单价配置 JSON（美元/百万 token）")
    parser.add_argument("--ledger", required=True, help="累计账本 JSON：存在则先读入，每轮写回")
    parser.add_argument("--cap", type=float, default=30.0)
    parser.add_argument("--interval", type=float, default=10.0)
    parser.add_argument("--max-output-tokens", type=int, default=2048, help="Astra 每次请求的 max_output_tokens")
    parser.add_argument("--once", action="store_true", help="只跑一轮（测试与手动核账用）")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    prices = load_prices(Path(args.prices))
    ledger_path = Path(args.ledger)
    ledger = load_ledger(ledger_path)
    ledger["prices"] = prices
    roots = [Path(r) for r in args.root]
    running = {"go": True}

    def _stop(signum, frame):  # noqa: ARG001
        running["go"] = False

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    last = None
    stop_seen = False
    while running["go"]:
        summary = cycle(roots, ledger, prices, args.cap, args.max_output_tokens)
        save_ledger(ledger_path, ledger)
        key = (summary["calls"], summary["pending"], summary["usd"])
        if key != last:
            print(f"ASTRA_COST usd={summary['usd']:.4f} calls={summary['calls']} pending={summary['pending']} "
                  f"projected={summary['projected_usd']:.4f} cap={args.cap:g}", flush=True)
            if summary["missing_fields"] or summary["no_usage"]:
                print(f"ASTRA_COST_WARN missing_fields={summary['missing_fields']} no_usage={summary['no_usage']}",
                      flush=True)
            last = key
        if summary["stop"] and (summary["stops_written"] or not stop_seen):
            print(f"ASTRA_COST=STOP usd={summary['usd']:.4f} cap={args.cap:g} projected={summary['projected_usd']:.4f} "
                  f"stop_files={len(summary['stops_written'])}", flush=True)
            stop_seen = True
        if args.once:
            break
        deadline = time.monotonic() + args.interval
        while running["go"] and time.monotonic() < deadline:
            time.sleep(min(1.0, max(0.0, deadline - time.monotonic())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
