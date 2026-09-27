"""从已验证交付媒体与原 hard 基准生成仅展示难度梯度的网站目录。"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "artifacts"
NAMES = {
    "BinFill": "分类投放", "PickXtimes": "重复抓取", "SwingXtimes": "重复摆动",
    "PickHighlight": "高亮目标抓取", "VideoUnmask": "视频遮挡记忆", "ButtonUnmask": "按钮遮挡记忆",
    "VideoUnmaskSwap": "视频遮挡交换", "ButtonUnmaskSwap": "按钮遮挡交换", "VideoRepick": "视频重复抓取",
    "PatternLock": "图案解锁", "RouteStick": "路线引导", "VideoPlaceButton": "视频放置与按钮",
    "VideoPlaceOrder": "视频放置顺序", "MoveCube": "移动方块", "InsertPeg": "插入插销", "StopCube": "停止方块",
}
TIERS = ("hard", "xhard1", "xhard2", "xhard3", "xhard4")
EXTRA = {"MoveCube", "InsertPeg", "StopCube"}
NOTES = {
    "BinFill": "原版 hard 总块数为10–12；新四档固定12块，逐档增加需要投入的块数。",
    "PickXtimes": "逐档增加抓取次数，并增加干扰块；最高两档干扰块均为3。",
    "SwingXtimes": "逐档增加摆动轮数，并增加干扰块；最高两档干扰块均为3。",
    "PickHighlight": "逐档增加需抓取的高亮块和总块数，干扰块始终为3。",
    "VideoUnmask": "抓取数量最多为3，主要通过增加干扰容器区分更高档位。",
    "ButtonUnmask": "抓取数量最多为3，主要通过增加干扰容器区分更高档位。",
    "VideoUnmaskSwap": "通过交换次数、抓取数量和外环干扰数量共同增加难度。",
    "ButtonUnmaskSwap": "通过交换次数、抓取数量和外环干扰数量共同增加难度。",
    "VideoRepick": "原版 hard 是静态布局的另一种任务，不能与新档直接比较；新四档增加块数、交换与重复抓取次数。",
    "PatternLock": "在5×5网格中逐档增加不重复访问的路径节点数。",
    "RouteStick": "逐档增加路线段数，需要连续完成更长的路线。",
    "VideoPlaceButton": "新四档均放回原位，按演示中放到台上的总次数区分难度。",
    "VideoPlaceOrder": "新四档均放回原位，两个物体的总放台次数从5增加到8。",
    "MoveCube": "不增加中间档位；xhard4 将方块中心、目标中心和杆抓取点统一放在圆环区域，并扩大杆的朝向范围。",
    "InsertPeg": "不增加中间档位；xhard4 增加1根干扰杆并扩大杆朝向范围，不是要求插入4根杆。",
    "StopCube": "不增加中间档位；xhard4 固定采用原版范围中最快的单程60步，并将停止序号延后至6–15。",
}


def gradients(plan):
    """读取批准的第三节；只取梯度维度与各档数值，不公开运行说明。"""
    section = plan.read_text(encoding="utf-8").split("## 三、", 1)[1].split("## 四、", 1)[0]
    result = {}
    for line in section.splitlines():
        if not line.startswith("| "):
            continue
        fields = [field.strip() for field in line.strip("|").split("|")]
        if fields[0] in NAMES and fields[0] not in EXTRA:
            result[fields[0]] = {tier: f"{fields[1]}：{fields[index + 2]}" for index, tier in enumerate(TIERS)}
    if set(result) != set(NAMES) - EXTRA:
        raise ValueError("批准表未覆盖全部梯度任务")
    result.update({
        "MoveCube": {"hard": "原版位置布局；杆朝向 −45°～45°", "xhard4": "圆环圆心 (−0.06, 0) 米、半径0.12–0.20米；杆朝向 −180°～180°"},
        "InsertPeg": {"hard": "3根杆；杆朝向 −45°～45°", "xhard4": "4根杆（增加1根干扰杆）；杆朝向 −180°～180°"},
        "StopCube": {"hard": "单程60、80或120步；停止序号2–5", "xhard4": "单程固定60步；停止序号6–15"},
    })
    result["BinFill"]["hard"] = "总块数10–12；投入块数3–5"
    result["VideoPlaceButton"]["hard"] = "1块，放台2次；演示后放到桌面"
    result["VideoPlaceOrder"]["hard"] = "1块，访问2–4台；演示后放到桌面"
    for tier in TIERS[1:]:
        result["BinFill"][tier] = f"总块数12；{result['BinFill'][tier].replace('（总块 12）', '')}"
    return result


# ---- VPB/VPO 子目标人读标签（2026-09-26）----
# HDF5 每步 info 只有 simple_subgoal / grounded_subgoal 等 7 个字段，没有方块 id、颜色和台 id；
# 演示计划只存在环境运行时对象、未落盘。这里用「位置链」从坐标反推：每个方块的位置 = 上一次
# 放下的点，抓取点就近归属；方块颜色只在 timestep_0（机械臂未动）的原点取像素。
CUBE_COUNT = {  # 各档演示中出现的方块数，来自源码 V6_DEMO_DECISIONS.demo_object_count 与原三档定义
    ("VideoPlaceButton", "hard"): 1, ("VideoPlaceButton", "xhard1"): 1, ("VideoPlaceButton", "xhard2"): 1,
    ("VideoPlaceButton", "xhard3"): 2, ("VideoPlaceButton", "xhard4"): 2,
    ("VideoPlaceOrder", "hard"): 1, ("VideoPlaceOrder", "xhard1"): 2, ("VideoPlaceOrder", "xhard2"): 2,
    ("VideoPlaceOrder", "xhard3"): 2, ("VideoPlaceOrder", "xhard4"): 2,
}
PLACEMENTS = {  # 各 xhard 档演示放台次数期望值（源码 expected_placements / visit_counts 之和）；hard 档只要求 ≥2
    ("VideoPlaceButton", "xhard1"): 3, ("VideoPlaceButton", "xhard2"): 4, ("VideoPlaceButton", "xhard3"): 5,
    ("VideoPlaceButton", "xhard4"): 6, ("VideoPlaceOrder", "xhard1"): 5, ("VideoPlaceOrder", "xhard2"): 6,
    ("VideoPlaceOrder", "xhard3"): 7, ("VideoPlaceOrder", "xhard4"): 8,
}
COLOR_ZH = {"red": "红", "green": "绿", "blue": "蓝"}
ORDINAL_EN = {"first": 1, "second": 2, "third": 3, "fourth": 4}
MATCH_PX = 16  # 抓取点（方块中心）与放台点（台中心）实测偏差 9–12 px，两块最小间隔 15 px
# 已披露的「程序答案台与题意不一致」样例（VideoPlaceButton xhard3 episode 3、6）；生成时反向校验程序答案规则
KNOWN_ISSUE_SAMPLES = {("VideoPlaceButton", "xhard3", 3), ("VideoPlaceButton", "xhard3", 6)}
KNOWN_ISSUE_NOTE = "程序判定的答案台与题意不同，见上方已知问题"


def parse_goal(text):
    """解析 setup/task_goal 首句：正确方块颜色与提问方式。"""
    import re
    color = re.search(r"the (\w+) cube", text)
    if not color or color.group(1) not in COLOR_ZH:
        raise ValueError(f"题目颜色无法解析：{text}")
    side = re.search(r"right (before|after) the button", text)
    order = re.search(r"the (first|second|third|fourth) target", text)
    if side:
        return {"color": color.group(1), "mode": side.group(1), "n": None}
    if order:
        return {"color": color.group(1), "mode": "order", "n": ORDINAL_EN[order.group(1)]}
    raise ValueError(f"题目提问方式无法解析：{text}")


def question_zh(goal):
    color = COLOR_ZH[goal["color"]]
    if goal["mode"] == "before":
        return f"题目：把{color}色方块放到它在按按钮前最后一次放置的台"
    if goal["mode"] == "after":
        return f"题目：把{color}色方块放到它在按按钮后第一次放置的台"
    return f"题目：把{color}色方块放到它先前第 {goal['n']} 次放置的台"


def classify_color(rgb):
    """把 5×5 像素均值归到红 / 绿 / 蓝，其它（台面、桌面）视为无法判定。"""
    r, g, b = (float(x) for x in rgb)
    top = max(r, g, b)
    if r == top and r > g + 40 and r > b + 40:
        return "red"
    if g == top and g > r + 40 and g > b + 40:
        return "green"
    if b == top and b > r + 40 and b > g + 40:
        return "blue"
    raise ValueError(f"原点像素无法判定为红/绿/蓝：({r:.0f},{g:.0f},{b:.0f})")


def _dist(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def read_boundaries(path, episode):
    """严格按记录边界读取原子子目标；坐标取 grounded_subgoal 的 <行, 列>，缺失时用同帧 choice_action.point。"""
    import h5py
    import re

    def decode(value):
        return value.decode() if isinstance(value, bytes) else str(value)
    boundaries = []
    terminal = ""
    with h5py.File(path, "r") as handle:
        group = handle[f"episode_{episode}"]
        goal = parse_goal(decode(group["setup/task_goal"][()][0]))
        image0 = group["timestep_0/obs/front_rgb"][()]
        frames = sorted((name for name in group if name.startswith("timestep_")),
                        key=lambda name: int(name.split("_")[1]))
        for index, name in enumerate(frames):
            frame = group[name]
            simple = decode(frame["info/simple_subgoal"][()])
            if simple == "All tasks completed":
                terminal = "全部任务完成"
                continue
            if index != 0 and not bool(frame["info/is_subgoal_boundary"][()]):
                continue
            grounded = decode(frame["info/grounded_subgoal"][()])
            location = re.search(r"<\s*(-?[0-9]+)\s*,\s*(-?[0-9]+)\s*>", grounded)
            choice = json.loads(decode(frame["action/choice_action"][()]))
            if location:
                point, source = (int(location.group(1)), int(location.group(2))), "grounded"
            elif choice.get("point"):
                point, source = (int(choice["point"][0]), int(choice["point"][1])), "choice_action"
            else:
                point, source = None, "none"
            boundaries.append({
                "timestep": int(name.split("_")[1]),
                "phase": "demo_steps" if bool(frame["info/is_video_demo"][()]) else "execution_steps",
                "simple": simple, "grounded": grounded, "point": point, "point_source": source,
            })

    def color_at(point):
        r, c = point
        patch = image0[max(r - 2, 0):r + 3, max(c - 2, 0):c + 3].reshape(-1, 3).mean(0)
        return classify_color(patch)
    return boundaries, goal, color_at, terminal


def label_flow(task, boundaries, n_cubes, goal, color_at, expected_placements=None):
    """位置链归属方块身份并生成人读标签；任一校验不成立即抛错，不放宽。"""
    cubes = []          # {"origin", "pos"(None=位置未知), "color"}
    targets = []        # 演示中放台点聚类，按首次出现顺序编 A/B/C/D
    steps = []          # 与 boundaries 等长的中间记录
    held = None
    button_seen = False
    correct = None

    def target_letter(point):
        for index, known in enumerate(targets):
            if _dist(point, known) <= MATCH_PX:
                return chr(65 + index)
        targets.append(point)
        return chr(65 + len(targets) - 1)

    for item in boundaries:
        simple, point, demo = item["simple"], item["point"], item["phase"] == "demo_steps"
        record = {"kind": None, "cube": None, "letter": None, "side": None}
        if simple == "static":
            record["kind"] = "static"
        elif simple == "press the button":
            record["kind"] = "button"
            if demo:
                button_seen = True
        elif simple == "pick up the cube":
            if point is None:
                raise ValueError(f"抓取边界无坐标 @{item['timestep']}")
            known = sorted((_dist(point, cube["pos"]), index) for index, cube in enumerate(cubes) if cube["pos"] is not None)
            unknown = [index for index, cube in enumerate(cubes) if cube["pos"] is None]
            if known and known[0][0] <= MATCH_PX:
                held = known[0][1]
            elif unknown:
                held = unknown[0]
            elif len(cubes) < n_cubes:
                cubes.append({"origin": point, "pos": point, "color": color_at(point)})
                held = len(cubes) - 1
            else:
                raise ValueError(f"抓取点 {point} 无法归属任何方块 @{item['timestep']}（已知 {known}）")
            record.update(kind="pick", cube=held)
            if not demo and correct is None:
                correct = held
        elif simple in ("drop the cube onto target", "place the cube onto the correct target"):
            if held is None:
                raise ValueError(f"放置前未持有方块 @{item['timestep']}")
            if demo:
                if point is None:
                    raise ValueError(f"演示放台边界无坐标 @{item['timestep']}")
                cubes[held]["pos"] = point
                record.update(kind="drop", cube=held, letter=target_letter(point),
                              side="after" if button_seen else "before")
            else:
                record.update(kind="place", cube=held)
            held = None
        elif simple == "drop the cube onto table":
            if held is None:
                raise ValueError(f"放到桌面前未持有方块 @{item['timestep']}")
            cubes[held]["pos"] = None
            record.update(kind="table", cube=held)
            held = None
        elif simple == "put the cube back to its original position":
            if held is None:
                raise ValueError(f"放回原位前未持有方块 @{item['timestep']}")
            if point is not None and _dist(point, cubes[held]["origin"]) > MATCH_PX:
                raise ValueError(f"放回原位点 {point} 与原点 {cubes[held]['origin']} 不符 @{item['timestep']}")
            cubes[held]["pos"] = cubes[held]["origin"]
            record.update(kind="home", cube=held)
            held = None
        else:
            raise ValueError(f"未登记的真实子目标：{simple}")
        steps.append(record)

    # ---- 校验 ----
    if len(cubes) != n_cubes:
        raise ValueError(f"识别出 {len(cubes)} 个方块，档定义为 {n_cubes}")
    colors = [cube["color"] for cube in cubes]
    if len(set(colors)) != len(colors):
        raise ValueError(f"方块颜色重复：{colors}")
    if correct is None:
        raise ValueError("执行阶段没有抓取边界，无法确定正确方块")
    if colors[correct] != goal["color"]:
        raise ValueError(f"执行阶段抓取的方块颜色 {colors[correct]} 与题目 {goal['color']} 不符")
    demo_drops = [index for index, record in enumerate(steps) if record["kind"] == "drop"]
    if expected_placements is not None and len(demo_drops) != expected_placements:
        raise ValueError(f"演示放台 {len(demo_drops)} 次，档期望 {expected_placements}")
    if expected_placements is None and len(demo_drops) < 2:
        raise ValueError(f"演示放台仅 {len(demo_drops)} 次")

    # ---- 放置计数、题目所问与程序答案 ----
    counters = {}
    for index in demo_drops:
        record = steps[index]
        key = (record["cube"], record["side"]) if task == "VideoPlaceButton" else (record["cube"],)
        counters[key] = counters.get(key, 0) + 1
        record["ordinal"] = counters[key]
    correct_drops = [index for index in demo_drops if steps[index]["cube"] == correct]
    if goal["mode"] == "before":
        side = [index for index in correct_drops if steps[index]["side"] == "before"]
        asked, program = (side[-1], side[0]) if side else (None, None)
    elif goal["mode"] == "after":
        side = [index for index in correct_drops if steps[index]["side"] == "after"]
        asked, program = (side[0], side[0]) if side else (None, None)
    else:
        asked = correct_drops[goal["n"] - 1] if len(correct_drops) >= goal["n"] else None
        program = asked
    if asked is None:
        raise ValueError("题目所问的放置在演示中不存在")

    # ---- 文案 ----
    def identity(cube):
        return "正确方块" if cube == correct else "干扰方块"
    flow = {"question": question_zh(goal), "cubes": [
        {"color": COLOR_ZH[color], "role": "correct" if index == correct else "distractor"} for index, color in enumerate(colors)],
        "demo_steps": [], "execution_steps": []}
    for index, (item, record) in enumerate(zip(boundaries, steps)):
        cube = record["cube"]
        role = "correct" if cube == correct else "distractor" if cube is not None else record["kind"]
        if record["kind"] == "static":
            text = "静止"
        elif record["kind"] == "button":
            text = "按按钮"
        elif record["kind"] == "pick":
            text = f"抓起{identity(cube)}（{COLOR_ZH[colors[cube]]}）"
        elif record["kind"] == "drop":
            side = ("按钮前" if record["side"] == "before" else "按钮后") if task == "VideoPlaceButton" else ""
            text = f"{identity(cube)} → 台 {record['letter']}（{side}第 {record['ordinal']} 次放置）"
        elif record["kind"] == "place":
            text = "放到答案台"
        elif record["kind"] == "table":
            text = f"{identity(cube)}放到桌面（演示结束）"
        else:
            text = f"{identity(cube)}放回原位"
        step = {"text": text, "role": role, "asked": index == asked}
        if index == asked and asked != program:
            step["note"] = KNOWN_ISSUE_NOTE
        flow[item["phase"]].append(step)
        item.update(cube=cube, target_letter=record.get("letter"), side=record.get("side"),
                    ordinal=record.get("ordinal"), translated=text)
    audit = {"goal": goal, "cubes": [{"origin": list(cube["origin"]), "color": cube["color"],
                                      "role": "correct" if index == correct else "distractor"} for index, cube in enumerate(cubes)],
             "targets": [list(point) for point in targets], "asked_index": asked, "program_answer_index": program,
             "boundaries": boundaries}
    return flow, audit


def sample_flow(task, tier, path, episode):
    """读取一个样例并生成人读标签；返回 flow、完成状态与审计记录。"""
    boundaries, goal, color_at, terminal = read_boundaries(path, episode)
    flow, audit = label_flow(task, boundaries, CUBE_COUNT[task, tier], goal, color_at,
                             PLACEMENTS.get((task, tier)))
    if not flow["demo_steps"] or not flow["execution_steps"] or not terminal:
        raise ValueError(f"演示、执行或完成状态缺失：{path}")
    digest = hashlib.sha256(json.dumps(audit, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    audit.update(h5=str(path), episode=episode, flow_sha256=digest)
    return flow, terminal, audit


def build_catalog(delivery, baseline, plan):
    values = gradients(plan)
    public = {"schema": "v6-site-catalog/1", "tasks": []}
    private = {}
    excluded = []
    flow_audit = []
    mismatched = set()
    cards = {}
    for task, name in NAMES.items():
        item = {"id": task, "name": name, "note": NOTES[task], "tiers": []}
        if task == "VideoPlaceButton":
            item["known_issue"] = {
                "title": "已知问题：部分视频的程序答案与题目含义不一致",
                "steps": [
                    "已确认受影响的是 xhard3 示例4和示例7（episode 3、6）。",
                    "以示例4为例：蓝色方块（正确方块）先放到台B，再被拿起放到台C，然后按按钮。",
                    "题目问蓝色方块在按钮前最后一次放到的台，因此按演示应回答台C，并追踪该台交换后的所在位置。",
                    "当前程序仍将更早的台B绑定为正确答案；视频中的执行按这个答案完成，所以内部记录显示成功。",
                ],
                "note": "台代号与下方演示子目标列表一致（按首次放置顺序编 A、B、C、D），不是视频中的标签；列表里带「题目所问」标记的是按题意应答的那次放置。视频显示的成功只代表通过当前程序判定，不能证明符合题目含义。此处保留原视频并说明问题，没有修复源码或重生成数据；其他所列样例不因此被判定为错误。",
            }
        for tier in (("hard", "xhard4") if task in EXTRA else TIERS):
            card = {"id": tier, "label": tier, "gradient": values[task][tier], "videos": []}
            cards[task, tier] = card
            item["tiers"].append(card)
        public["tasks"].append(item)

    def add(task, tier, episode, paths, h5):
        if (task, tier) not in cards:
            raise ValueError(f"未知任务档位：{task}/{tier}")
        if not paths:
            raise ValueError(f"成功轨迹无视频：{task}/{tier}/{episode}")
        playable = []
        for path in paths:
            if path.name.startswith("success_NO_OBJECT_"):
                excluded.append({"task": task, "difficulty": tier, "episode": episode,
                                 "path": str(path.resolve()), "reason": "NO_OBJECT状态尾片，不作为轨迹示例"})
                continue
            probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                    "stream=nb_frames,duration:format=duration", "-of", "json", str(path)],
                                   check=True, capture_output=True, text=True, timeout=30)
            data = json.loads(probe.stdout)
            stream = data.get("streams", [{}])[0]
            frames = int(stream.get("nb_frames", 0))
            duration = float(stream.get("duration", data.get("format", {}).get("duration", 0)))
            if frames <= 4 or duration < 1:
                raise ValueError(f"主视频帧数或时长不足：{path} frames={frames} duration={duration}")
            playable.append(path)
        paths = playable
        if not paths:
            raise ValueError(f"轨迹缺少可播放主视频：{task}/{tier}/{episode}")
        for index, path in enumerate(sorted(paths)):
            resolved = path.resolve(strict=True)
            if not resolved.is_relative_to(ARTIFACTS.resolve()) or not resolved.is_file() or resolved.suffix.lower() != ".mp4":
                raise ValueError(f"媒体不在产物白名单：{path}")
            identity = f"{task}/{tier}/{episode}/{index}"
            media_id = hashlib.sha256(identity.encode()).hexdigest()[:24]
            if media_id in private:
                raise ValueError(f"媒体身份重复：{identity}")
            private[media_id] = str(resolved)
            label = f"示例 {episode + 1}"
            if len(paths) > 1:
                label += f" · 片段 {index + 1}/{len(paths)}"
            video = {"id": media_id, "label": label, "url": f"/media/{media_id}"}
            if task in {"VideoPlaceButton", "VideoPlaceOrder"}:
                flow, terminal, audit = sample_flow(task, tier, h5, episode)
                video.update(subgoal_flow=flow, flow_terminal=terminal, flow_sha256=audit["flow_sha256"])
                flow_audit.append({"task": task, "tier": tier, "media_id": media_id, **audit})
                if audit["asked_index"] != audit["program_answer_index"]:
                    mismatched.add((task, tier, episode))
            cards[task, tier]["videos"].append(video)

    rows = json.loads(delivery.read_text(encoding="utf-8"))["successes"]
    if len(rows) != 165:
        raise ValueError(f"正式成功轨迹应为165条，实际{len(rows)}")
    for row in rows:
        if row.get("state") != "success":
            raise ValueError("交付successes中包含非成功轨迹")
        media = [Path(entry["path"]) for entry in row["files"] if Path(entry["path"]).suffix.lower() == ".mp4"]
        h5 = [Path(entry["path"]) for entry in row["files"] if Path(entry["path"]).suffix.lower() == ".h5"]
        if len(h5) != 1:
            raise ValueError("成功轨迹H5必须唯一")
        add(row["task"], row["difficulty"], row["episode"], media, h5[0])
    hard_rows = [row for row in json.loads(baseline.read_text(encoding="utf-8"))["results"]
                 if row.get("difficulty") == "hard" and row.get("ok") is True]
    for row in hard_rows:
        folder = Path(row["raw_h5_path"]).parent.parent / "videos"
        add(row["task"], "hard", row["episode"], list(folder.glob("*.mp4")), Path(row["raw_h5_path"]))
    for (task, tier), card in cards.items():
        if not card["videos"]:
            raise ValueError(f"缺少成功视频：{task}/{tier}")
    listed = ",".join(f"{tier}:{episode}" for _, tier, episode in sorted(mismatched))
    if mismatched != KNOWN_ISSUE_SAMPLES:
        print(f"KNOWN_ISSUE_MATCH=FAIL mismatched={listed}")
        raise ValueError("题意与程序答案不一致的样例集合与已披露集合不同")
    print(f"KNOWN_ISSUE_MATCH=PASS mismatched={listed}")
    print(f"FLOW_LABELS=PASS samples={len(flow_audit)} cubes={sum(len(a['cubes']) for a in flow_audit)} "
          f"asked={sum(1 for a in flow_audit if a['asked_index'] is not None)}")
    return public, private, excluded, flow_audit


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--delivery", type=Path, default=ARTIFACTS / "newtask-v6/s4-launch/verification/merged-provisional-delivery.json")
    parser.add_argument("--baseline", type=Path, default=ARTIFACTS / "newtask-v6/v1/base/results/B.json")
    parser.add_argument("--plan", type=Path, default=ROOT / "0925-newtask-release-v6-plan.md")
    parser.add_argument("--out", type=Path, default=ARTIFACTS / "newtask-v6/site")
    parser.add_argument("--poster-source", type=Path, help="按媒体绝对路径匹配已有预览，不依赖旧媒体编号")
    args = parser.parse_args(argv)
    if not args.out.resolve().is_relative_to(ARTIFACTS.resolve()):
        parser.error("输出必须位于本仓库artifacts")
    public, private, excluded, flow_audit = build_catalog(args.delivery, args.baseline, args.plan)
    args.out.mkdir(parents=True, exist_ok=True)
    for name in ("catalog.json", "media-private.json", "excluded-tail-clips.json", "subgoal-audit.json"):
        if (args.out / name).exists():
            raise FileExistsError(f"拒绝覆盖已有目录文件：{name}")
    for name, data in (("catalog.json", public), ("media-private.json", private),
                       ("excluded-tail-clips.json", {"count": len(excluded), "clips": excluded}),
                       ("subgoal-audit.json", {"schema": 2, "samples": flow_audit, "sha_scope": "真实边界、位置链归属、题目解析与标签文字的散列，非H5全文件散列"})):
        with (args.out / name).open("x", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    if args.poster_source:
        source_media = json.loads((args.poster_source / "media-private.json").read_text())
        source_by_path = {str(Path(path).resolve()): media_id for media_id, path in source_media.items()}
        posters = args.out / "posters"
        posters.mkdir()
        for media_id, path in private.items():
            old_id = source_by_path[path]
            source = args.poster_source / "posters" / f"{old_id}.jpg"
            if not source.is_file():
                raise FileNotFoundError(f"缺少匹配预览：{source}")
            shutil.copyfile(source, posters / f"{media_id}.jpg")
    print(f"SITE_CATALOG=PASS tasks={len(public['tasks'])} cards={sum(len(t['tiers']) for t in public['tasks'])} videos={len(private)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
