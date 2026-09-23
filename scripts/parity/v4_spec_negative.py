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

from scripts.parity.v4_reset_probe import _capture, _floats  # noqa: E402
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
    if isinstance(value, int) and value in (0, 1):
        return 1 - value  # 0/1 多为开关或二选一（如 obj_sample 只判是否为 0），+1 可能语义不变
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


def _extra_capture(env) -> dict:
    """在 reset 探针的抓取之外再加三类「规格会影响、但 actor 位姿看不到」的状态：
    关节体（按钮等）根位姿、每个 actor 的渲染颜色、环境上的小数值属性（如 reset 后被藏起来的目标的原位姿）。"""
    import numpy as np

    base = env.unwrapped
    out: dict = {"articulations": {}, "colors": {}, "attrs": {}}
    def _colors_of(entities):
        colors = []
        for obj in entities:
            entity = getattr(obj, "entity", obj)  # 关节体 link 的 _objs 是物理组件，经 .entity 拿到渲染组件
            for comp in getattr(entity, "components", []):
                for shape in getattr(comp, "render_shapes", None) or []:
                    for part in (getattr(shape, "parts", None) or [shape]):
                        color = getattr(getattr(part, "material", None), "base_color", None)
                        if color is not None:
                            colors.append(_floats(list(color)))
        return colors

    for name, art in sorted(getattr(base.scene, "articulations", {}).items()):
        try:
            out["articulations"][name] = {"p": _floats(art.pose.p), "q": _floats(art.pose.q)}
        except Exception:  # noqa: BLE001
            pass
        # 关节体的颜色挂在各 link 上（如 InsertPeg 的杆头/杆尾）
        link_colors = _colors_of([ent for link in getattr(art, "links", []) for ent in getattr(link, "_objs", [])])
        if link_colors:
            out["colors"][f"articulation:{name}"] = link_colors
    for name, actor in sorted(getattr(base.scene, "actors", {}).items()):
        colors = _colors_of(getattr(actor, "_objs", []))
        if colors:
            out["colors"][name] = colors
    # 任务指令文本（答案选哪一块、抓近端还是远端等只体现在这里）
    try:
        from robomme.robomme_env.utils import task_goal

        out["task_goal"] = task_goal.get_language_goal(env, base.spec.id)
    except Exception as exc:  # noqa: BLE001
        out["task_goal"] = f"<{type(exc).__name__}>"
    for key, value in sorted(vars(base).items()):
        if key.startswith("_spec") or "generator" in key:
            continue
        if isinstance(value, float):
            out["attrs"][key] = float.hex(value)
            continue
        if isinstance(value, (int, str)) and not isinstance(value, bool) and len(str(value)) <= 200:
            out["attrs"][key] = value  # 如 obj_flag、答案序号、目标颜色名
            continue
        poses = value if isinstance(value, (list, tuple)) else [value]
        if poses and all(hasattr(p, "p") and hasattr(p, "q") and not hasattr(p, "_objs") for p in poses):
            # sapien.Pose（或其列表）：如 reset 后才在执行段使用的初始位姿
            out["attrs"][key] = [{"p": _floats(p.p), "q": _floats(p.q)} for p in poses]
            continue
        array = value.detach().cpu().numpy() if hasattr(value, "detach") else value
        if isinstance(array, np.ndarray) and array.dtype.kind == "f" and 0 < array.size <= 64:
            out["attrs"][key] = _floats(array)
    return out


def _replay(task, row, spec, sampling):
    import gymnasium as gym

    env = None
    try:
        env = gym.make(task, sampling_config=sampling, native_episode_spec=spec,
                       **env_kwargs(row["seed"], row["episode"]))
        env.reset()
        capture = _capture(env)
        capture["extra"] = _extra_capture(env)
        recorder = env.unwrapped._spec
        record_paths = {item["path"] for item in recorder.trace if item["source"] == "record"}
        consumed = set(recorder.consumed_paths())
        unused = [p for p in recorder.leaf_paths()
                  if not any(p == c or p.startswith(c + ".") for c in consumed)]
        capture.pop("spec", None)
        capture.pop("trace", None)
        capture.pop("generator_states", None)  # 回注模式下原抽样照常发生，generator 终态不反映规格值
        return {"ok": True, "capture": capture, "mismatch": len(recorder.mismatches), "unused": len(unused),
                "record_paths": record_paths}
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
        # 只改真正的取值点：record() 记的是派生量／运行观测，回注时只做核对、不参与建场景，改它不该有效果
        records = base.get("record_paths", set())
        # ManiSkill 在 gym.make 构造期先初始化一次、reset 时再初始化一次：非最后一次 initializations.<k> 的取值
        # 会被随后那次覆盖，改它在最终场景里本来就看不到——只改最后一次
        inits = sorted(int(k) for k in row["spec"].get("initializations", {}) if str(k).isdigit())
        stale = {f"initializations.{k}" for k in inits[:-1]}
        records = set(records) | stale
        candidates = [(p, v) for p, v in _leaves({k: row["spec"][k] for k in SECTIONS if k in row["spec"]})
                      if _corrupt(v) is not None
                      and not any(p == r or p.startswith(r + ".") for r in records)]
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
