#!/usr/bin/env python3
"""V3g 反例检验（``SPEC_NEGATIVE``）：改坏冻结规格里的一个叶子值再回注，场景必须随之改变。

对快照里每个环境的每条 selected 规格，先原样回注 reset 一次抓取可比状态（actor 位姿、任务表、规格绑定），
再逐个改坏若干叶子（数值 +扰动 / 列表倒序 / 布尔取反），每改一处重新 reset 抓取；
要求：原样回注 ``mismatch=0, unused=0``（``SPEC_BINDING``），每个改坏样本的可比状态与原样不同（``diff_zero=0``）。

只做 reset 级（不跑演示），属 V3g 的离线部分；与负载无关，结果可重复。

    uv run --no-sync python -m scripts.parity.v4_spec_negative --specs scripts/configs/newtask-v4/v4-01/specs.jsonl \
        --per-spec 2 --out artifacts/newtask-v4/v4-01/v3g.json
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
for extra in (REPO_ROOT, REPO_ROOT / "scripts", REPO_ROOT / "src"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from scripts.parity.v4_reset_probe import _capture  # noqa: E402
from scripts.parity.v4_specs import env_kwargs, load_specs  # noqa: E402

SECTIONS = ("layout", "objects", "actions", "initializations")


def _leaves(node, path=""):
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _leaves(value, f"{path}.{key}" if path else key)
    else:
        yield path, node


def _corrupt(value):
    """给出一个「明显不同」的替身值；返回 None 表示这个叶子不适合改。"""
    if isinstance(value, bool):
        return not value
    if isinstance(value, (int, float)):
        return value + (0.037 if isinstance(value, float) else 1)
    if isinstance(value, list) and len(value) > 1:
        if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value):
            if any(isinstance(v, float) for v in value):
                return [v + 0.037 if isinstance(v, float) else v for v in value]
            reversed_ = list(reversed(value))
            return reversed_ if reversed_ != value else None
    return None


def _set(tree, dotted, value):
    node = tree
    parts = dotted.split(".")
    for part in parts[:-1]:
        node = node[part]
    node[parts[-1]] = value


def _replay(task, row, spec, sampling):
    import gymnasium as gym

    env = None
    try:
        env = gym.make(task, sampling_config=sampling, native_episode_spec=spec,
                       **env_kwargs(row["seed"], row["episode"]))
        env.reset()
        capture = _capture(env)
        recorder = env.unwrapped._spec
        consumed = set(recorder.consumed_paths())
        unused = [p for p in recorder.leaf_paths()
                  if not any(p == c or p.startswith(c + ".") for c in consumed)]
        capture.pop("spec", None)
        capture.pop("trace", None)
        capture.pop("generator_states", None)  # 回注模式下原抽样照常发生，generator 终态不反映规格值
        return {"ok": True, "capture": capture, "mismatch": len(recorder.mismatches), "unused": len(unused)}
    except Exception as exc:  # noqa: BLE001 改坏的规格可能直接让场景起不来——那也是「产生了差异」
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:300]}
    finally:
        if env is not None:
            env.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--specs", required=True)
    parser.add_argument("--per-spec", type=int, default=2, help="每条规格改坏几个叶子（按路径排序等距取）")
    parser.add_argument("--tasks", default="all")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    import robomme.robomme_env  # noqa: F401 注册环境

    header, sampling_by_task, specs = load_specs(args.specs)
    tasks = header["tasks"] if args.tasks == "all" else args.tasks.split(",")
    report, cases, diff_zero, binding_bad = [], 0, 0, 0
    for key, row in sorted(specs.items()):
        task = row["task"]
        if task not in tasks:
            continue
        base = _replay(task, row, row["spec"], sampling_by_task[task])
        if not base["ok"] or base["mismatch"] or base["unused"]:
            binding_bad += 1
        candidates = [(p, v) for p, v in _leaves({k: row["spec"][k] for k in SECTIONS if k in row["spec"]})
                      if _corrupt(v) is not None]
        step = max(1, len(candidates) // max(1, args.per_spec))
        picked = candidates[::step][: args.per_spec]
        for path, value in picked:
            spec = copy.deepcopy(row["spec"])
            _set(spec, path, _corrupt(value))
            bad = _replay(task, row, spec, sampling_by_task[task])
            changed = (not bad["ok"]) or bad["capture"] != base.get("capture")
            cases += 1
            diff_zero += not changed
            report.append({"identity": key, "path": path, "changed": changed,
                           "replay_ok": bad["ok"], "error": bad.get("error")})
            print(f"NEG {key} {path} changed={changed} {'' if bad['ok'] else bad['error'][:80]}", flush=True)
        print(f"BIND {key} ok={base['ok']} mismatch={base.get('mismatch')} unused={base.get('unused')}", flush=True)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"SPEC_BINDING={'PASS' if binding_bad == 0 else 'FAIL'} specs={len([k for k in specs if specs[k]['task'] in tasks])} bad={binding_bad}")
    print(f"SPEC_NEGATIVE={'PASS' if diff_zero == 0 and cases else 'FAIL'} cases={cases} diff_zero={diff_zero}")
    return 0 if diff_zero == 0 and binding_bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
