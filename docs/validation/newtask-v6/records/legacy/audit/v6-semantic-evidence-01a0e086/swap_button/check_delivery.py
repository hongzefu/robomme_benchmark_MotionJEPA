"""离线核验 ButtonUnmaskSwap 正式交付中的选择映射与首抓坐标。"""

import argparse
import ast
import hashlib
import json
import subprocess
from pathlib import Path

import h5py


AUDIT_BASE = "0a3f989b0dfcff12a3cbb34a8112cb56864c7ee8"
ANCESTOR = "903cfcc3f2b0a4d040f9bebedb64e0ffd35d3281"
TASK_PATH = "src/robomme/robomme_env/ButtonUnmaskSwap.py"
OPTION_PATH = "src/robomme/robomme_env/utils/vqa_options.py"


def digest(path):
    sha = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            sha.update(chunk)
    return sha.hexdigest()


def mappings(task_source, option_source):
    """只解析语法树，不导入或执行环境；分别提取演示与选项闭包的按钮。"""
    demo = {}
    for node in ast.walk(ast.parse(task_source)):
        if not isinstance(node, ast.Dict):
            continue
        fields = {k.value: v for k, v in zip(node.keys, node.values)
                  if isinstance(k, ast.Constant) and isinstance(k.value, str)}
        name = fields.get("name")
        if isinstance(name, ast.Constant) and name.value in ("press the first button", "press the second button"):
            buttons = [n.attr for n in ast.walk(fields["solve"])
                       if isinstance(n, ast.Attribute) and n.attr in ("button_left", "button_right")]
            assert len(buttons) == 1, buttons
            demo[name.value] = buttons[0]
    options = {}
    function = next(n for n in ast.walk(ast.parse(option_source))
                    if isinstance(n, ast.FunctionDef) and n.name == "_options_button_unmask_swap")
    for node in ast.walk(function):
        if not isinstance(node, ast.Dict):
            continue
        fields = {k.value: v for k, v in zip(node.keys, node.values)
                  if isinstance(k, ast.Constant) and isinstance(k.value, str)}
        action = fields.get("action")
        if isinstance(action, ast.Constant) and action.value in demo:
            defaults = fields["solve"].args.defaults
            assert len(defaults) == 1 and isinstance(defaults[0], ast.Name)
            variable = defaults[0].id
            assert variable in ("button_obj_left", "button_obj_right")
            options[action.value] = {
                "label": fields["label"].value.upper(),
                "button": "button_left" if variable == "button_obj_left" else "button_right",
            }
    assert len(demo) == len(options) == 2
    return {name: {"recorded_button": button, "option_button": options[name]["button"],
                   "label": options[name]["label"], "reversed": button != options[name]["button"]}
            for name, button in demo.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--frozen-root", type=Path, required=True)
    parser.add_argument("--git-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    entries = [x for x in manifest["successes"] if x["task"] == "ButtonUnmaskSwap"]
    assert len(entries) == 12, len(entries)
    assert {(x["difficulty"], x["episode"]) for x in entries} == {
        (f"xhard{i}", ep) for i in range(1, 5) for ep in (0, 3, 6)}
    rows = []
    for entry in entries:
        files = [x for x in entry["files"] if x["path"].endswith(".h5")]
        assert len(files) == 1
        source = files[0]
        path = Path(source["path"])
        sha = digest(path)
        size = path.stat().st_size
        assert size == source["bytes"] and sha == source["sha256"], str(path)
        row = {key: entry[key] for key in ("task", "difficulty", "episode", "seed")}
        row.update(source_hdf5=str(path), source_bytes=size, source_sha256=sha, boundaries=[])
        with h5py.File(path, "r") as handle:
            episode = handle[f"episode_{entry['episode']}"]
            names = sorted((k for k in episode if k.startswith("timestep_")), key=lambda k: int(k.split("_")[1]))
            seen = set()
            for name in names:
                timestep = episode[name]
                subgoal = timestep["info/simple_subgoal"][()].decode()
                relevant = subgoal.startswith("press the ") or subgoal.startswith("pick up the container")
                if not relevant or subgoal in seen:
                    continue
                seen.add(subgoal)
                row["boundaries"].append({
                    "timestep": int(name.split("_")[1]), "simple_subgoal": subgoal,
                    "choice_action": json.loads(timestep["action/choice_action"][()].decode()),
                    "grounded_subgoal": timestep["info/grounded_subgoal"][()].decode(),
                    "grounded_subgoal_online": timestep["info/grounded_subgoal_online"][()].decode(),
                })
            row["last_is_completed"] = bool(episode[names[-1]]["info/is_completed"][()])
        buttons = row["boundaries"][:2]
        assert [b["choice_action"]["choice"] for b in buttons] == ["A", "B"]
        assert [b["simple_subgoal"] for b in buttons] == ["press the first button", "press the second button"]
        pickup = next(x for x in row["boundaries"] if x["simple_subgoal"].startswith("pick up"))
        row["first_pick_grounding_difference"] = pickup["grounded_subgoal"] != pickup["grounded_subgoal_online"]
        rows.append(row)
        print("BUS_EPISODE", row["difficulty"], row["episode"], row["seed"],
              "首抓字段差异=" + str(row["first_pick_grounding_difference"]),
              "首抓步=" + str(pickup["timestep"]), "按钮标签=A/B")
    sources = {}
    for relative in (TASK_PATH, OPTION_PATH):
        path = args.frozen_root / relative
        sources[relative] = {"sha256": digest(path), "bytes": path.stat().st_size}
        anchored = subprocess.check_output(["git", "-C", str(args.git_root), "show", f"{AUDIT_BASE}:{relative}"])
        assert path.read_bytes() == anchored, relative
    current = mappings((args.frozen_root / TASK_PATH).read_text(), (args.frozen_root / OPTION_PATH).read_text())
    ancestor_sources = {
        relative: subprocess.check_output(["git", "-C", str(args.git_root), "show", f"{ANCESTOR}:{relative}"]).decode()
        for relative in (TASK_PATH, OPTION_PATH)}
    ancestor = mappings(ancestor_sources[TASK_PATH], ancestor_sources[OPTION_PATH])
    assert all(x["reversed"] for x in current.values())
    assert current == ancestor
    assert "config_hard" in ancestor_sources[TASK_PATH] and "config_xhard" not in ancestor_sources[TASK_PATH]
    result = {
        "audit_base": AUDIT_BASE,
        "manifest": {"path": str(args.manifest), "bytes": args.manifest.stat().st_size,
                     "sha256": digest(args.manifest)},
        "source_files": sources, "current_button_mapping": current,
        "ancestor": {"sha": ANCESTOR, "button_mapping": ancestor,
                     "sources": {p: {"bytes": len(s.encode()), "sha256": hashlib.sha256(s.encode()).hexdigest()}
                                 for p, s in ancestor_sources.items()}},
        "episodes": rows,
        "summary": {"files": len(rows), "first_pick_grounding_differences": sum(x["first_pick_grounding_difference"] for x in rows),
                    "button_label_pairs": len(rows), "last_is_completed_true": sum(x["last_is_completed"] for x in rows)},
        "limits": ["字段差异不等于全部帧像素错误；代表局截图支持目标位置变化，未逐帧重建全部分割。",
                   "选项反转由冻结源码语法树与交付选择标签共同证明；未执行策略、按钮或仿真。",
                   "祖先已有相同映射，只证明非V6新引入，不证明旧数据全部受到影响。"]}
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print("BUS_SOURCE_IDENTITY=PASS files=12")
    print("BUS_BUTTON_MAPPING=FAIL reversed_options=2 observed_label_pairs=12")
    print("BUS_FIRST_PICK_GROUNDING=FAIL differences=" + str(result["summary"]["first_pick_grounding_differences"]) + " compared=12")
    print("BUS_ANCESTOR_REPRODUCED=PASS original_difficulties_only=true")
    print("CHECKER_EXIT=0 仅读取既有产物，未仿真")


if __name__ == "__main__":
    main()
