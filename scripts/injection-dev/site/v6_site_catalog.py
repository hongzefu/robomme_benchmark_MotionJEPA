"""从已验证交付媒体与原 hard 基准生成仅展示难度梯度的网站目录。"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
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


# ---- site-v11：V6 语义审查修复（0926-v6-audit-fix-plan.md §8.5 / §8.3 / §九）----
# 只涉及 xhard1～4；用户裁决 D1/D4/D5「不要管」，不在此列出。
TIERS_ALL_NEW = "xhard1～xhard4"
CHANGELOG = [
    # 一、题面（task_goal）文字改动
    {"group": "一、题面文字改动", "env": "PickHighlight", "refs": ["F1"], "tiers": TIERS_ALL_NEW,
     "change": "两句题面改为与新任务链一致：先按按钮，再逐个抓起全部高亮方块，最后再按按钮结束（第二句为同义变体），并修正拼写 highlighteted。",
     "reason": "原题面要求末尾再按按钮，任务链却没有这一步（F1）。"},
    {"group": "一、题面文字改动", "env": "VideoPlaceButton", "refs": ["N3", "N4"], "tiers": TIERS_ALL_NEW,
     "change": "每局只保留一句：按钮前题问「按按钮前最后一次放置的台」，按钮后题问「按按钮后第一次放置的台」；删去 right / immediately / previously placed 三种说法。",
     "reason": "双块档里另一块会在中间放置，「紧挨按钮前/后」时序不成立（N3）；有额外放置时「previously placed」不唯一（N4）。"},
    # 二、子目标文字与链条改动
    {"group": "二、子目标文字与链条改动", "env": "PickHighlight", "refs": ["F1"], "tiers": TIERS_ALL_NEW,
     "change": "末块抓起后新增子目标 place the cube onto the table（把方块放到桌面），链尾新增 press the button at <坐标>（按末按钮）；成功时点后移到末按钮。",
     "reason": "与改后的题面保持一致（F1）。"},
    {"group": "二、子目标文字与链条改动", "env": "ButtonUnmaskSwap", "refs": ["N1"], "tiers": TIERS_ALL_NEW,
     "change": "第二个按钮之后新增子目标 wait for the containers to finish swapping（等待容器交换完成）；等待段不再标为「按第二个按钮」，选项不再是 B。",
     "reason": "按下第二个按钮后机器人要静止等待交换 18～124 步，原先整段仍标为按按钮（N1）。"},
    {"group": "二、子目标文字与链条改动", "env": "VideoPlaceButton / VideoPlaceOrder", "refs": ["N5"], "tiers": TIERS_ALL_NEW,
     "change": "put the cube back to its original position（放回原位）去掉 at <>；该子目标无坐标是设计如此。",
     "reason": "原位标记在画面中被隐藏，坐标永远缺失（N5）。"},
    {"group": "二、子目标文字与链条改动", "env": "SwingXtimes", "refs": ["N10"], "tiers": "xhard4",
     "change": "第 11 轮由 for the 11th time 改为 for the eleventh time。",
     "reason": "其余轮次都用英文单词，只有第 11 轮用了数字序数（N10）。"},
    {"group": "二、子目标文字与链条改动", "env": "VideoRepick", "refs": ["N11", "M1"], "tiers": "xhard4",
     "change": "每次交换对应一个 static 边界，边界数 = 交换数 + 1（以定位到根因为前提）；同环境新四档的提前按钮失败窗口改为随轮次滚动（M1，判定逻辑，不改文字）。",
     "reason": "xhard4 曾出现 12 次交换只有 11 个边界（N11）；失败窗口只覆盖首抓后 50～500 步（M1）。"},
    {"group": "二、子目标文字与链条改动", "env": "InsertPeg", "refs": ["D6"], "tiers": "xhard4",
     "change": "Pick up the peg by grasping the near/far end 的 near/far 改按真实距离判定，个别候选标签翻转。",
     "reason": "原先按 x 轴而非实际距离判定远近（D6）。"},
    # 三、文字不变但含义或坐标变
    {"group": "三、文字不变但含义或坐标变化", "env": "VideoPlaceButton", "refs": ["Q-C"], "tiers": "xhard2、xhard3、xhard4（含按钮前额外放置的局）",
     "change": "按钮前题的答案改为「按钮前最后一次放置的台」；含按钮前额外放置的局答案台会变。台可交换，答案按台实体判定。",
     "reason": "原程序取按钮前第一次放置的台，与题意不符（Q-C）。"},
    {"group": "三、文字不变但含义或坐标变化", "env": "VideoPlaceButton", "refs": ["N2", "F6"], "tiers": "xhard3、xhard4",
     "change": "台数 4→5；额外放台落到第 5 台，演示中不再出现原地空转或两块同台。",
     "reason": "4 台下额外放台的候选恒等于按钮后要用的台（N2），且缺少跨按钮时刻的占用检查（F6）。"},
    {"group": "三、文字不变但含义或坐标变化", "env": "ButtonUnmaskSwap", "refs": ["F4"], "tiers": TIERS_ALL_NEW,
     "change": "交换后 grounded_subgoal 的 <坐标> 随目标移动刷新；不做遮挡回填。",
     "reason": "交换后坐标仍指向旧位置（F4）。"},
    {"group": "三、文字不变但含义或坐标变化", "env": "ButtonUnmaskSwap", "refs": ["F3"], "tiers": TIERS_ALL_NEW,
     "change": "button_left / button_right 改为机器人坐标系命名，press the first button 与选项 a 指向同一按钮；子目标文字不变。",
     "reason": "原先「第一/第二按钮」的选项标签与执行对象相反（F3）。"},
    # 四、只披露、不改动
    {"group": "四、只披露、不改动", "env": "多个环境", "refs": ["F2", "F5", "D3", "D7", "N6～N8", "S1～S13", "M3"], "tiers": "原三档与新四档",
     "change": "原三档同样存在的问题逐环境列在下方「已知问题」，本轮不修。",
     "reason": "与原三档同源，按裁决只记录（§8.3）。"},
    {"group": "四、只披露、不改动", "env": "PickHighlight", "refs": ["N9"], "tiers": TIERS_ALL_NEW,
     "change": "新档题面无「, which is <颜色>」后缀，按钮失败判定改为每步重算。",
     "reason": "来源为 V4 决策，本轮不改（N9）。"},
    {"group": "四、只披露、不改动", "env": "全部环境", "refs": ["D2"], "tiers": "全部档位",
     "change": "所有 left / right 均为机器人坐标系，与前相机画面左右相反。",
     "reason": "如 SwingXtimes「右盘→左盘」按机器人视角描述（D2）。"},
]
KNOWN_ISSUES = [  # §8.5 第 13～15 条，按环境列出；原三档同样存在，本轮不修
    {"env": "VideoRepick", "items": ["F2：题面把「执行 N 次」写成「previously picked up N times」（演示里抓过 N 次）。",
                                     "S3：交换可能被延迟撤销、回到原槽。",
                                     "S4：模板 1「for N times, finally put it down」存在歧义读法。"]},
    {"env": "BinFill", "items": ["F5：在孔板上方约 0.2 米处悬空「删除」方块并计数。",
                                 "S6：静态布局下的序数没有可见的对应物。",
                                 "S7：抓取判据不区分颜色。"]},
    {"env": "ButtonUnmask", "items": ["D3：揭示按绝对步数触发，按键不会触发再次揭示。",
                                      "M3：原三档容器请求数被静默截断（hard 15→6）。"]},
    {"env": "VideoUnmask / ButtonUnmask / VideoUnmaskSwap / ButtonUnmaskSwap", "items": ["D7：VQA 只允许选内环容器，外环容器可见但不可选。"]},
    {"env": "ButtonUnmaskSwap", "items": ["S2：交换的净置换可能恰为恒等。"]},
    {"env": "PickHighlight / VideoUnmask / ButtonUnmask / VideoUnmaskSwap / VideoPlaceOrder / BinFill / PickXtimes / MoveCube",
     "items": ["N6～N8 与 S1：子目标切换帧目标被机械臂遮住，整段坐标缺失（可能留下 1 帧 NO_OBJECT 片段，网站已剔除）。"]},
    {"env": "PickHighlight", "items": ["S8：「第 k 个」高亮顺序在画面中不可见。",
                                       "N9：新档无「, which is <颜色>」后缀、按钮失败判定每步重算，来源为 V4 决策。"]},
    {"env": "SwingXtimes", "items": ["S5：主模板漏写「放下」一步。"]},
    {"env": "RouteStick", "items": ["S9：末 6 帧在线字段为 NO RECORD。"]},
    {"env": "MoveCube", "items": ["S10：长推时前相机看不到方块。", "S11：成功判据不检查运动方式。"]},
    {"env": "InsertPeg", "items": ["S12：演示段与执行段措辞不一致。"]},
    {"env": "StopCube", "items": ["S13：成功容差大于靶盘。"]},
    {"env": "全部环境", "items": ["D2：所有 left / right 均为机器人坐标系。"]},
]
KNOWN_ISSUES_NOTE = "原三档同样存在，本轮不修。所有 left / right 均为机器人坐标系。"
SUBGOAL_ZH = {  # 本轮新增或改动的子目标原文 → 网页人读标签
    "wait for the containers to finish swapping": "等待容器交换完成",
    "press the button": "按按钮",
    "place the cube onto the table": "把方块放到桌面",
    "put the cube back to its original position": "放回原位（无坐标，设计如此）",
}


def translate_subgoal(text):
    """把子目标原文（去掉 at <坐标> 后）翻译为人读标签；未登记返回原文。"""
    import re
    base = re.sub(r"\s*at\s*<[^>]*>\s*$", "", str(text).strip())
    return SUBGOAL_ZH.get(base, base)


def task_notices(fixed):
    """各任务顶部说明框；fixed=False（旧 delivery，修复前数据）时只返回不依赖新数据的说明。"""
    notices = {
        "ButtonUnmaskSwap": {
            "kind": "emphasis",
            "title": f"重点：新四档在第二个按钮之后新增子目标「{translate_subgoal('wait for the containers to finish swapping')}」",
            "steps": [
                "原文 wait for the containers to finish swapping。按下第二个按钮后，机器人要静止等待容器交换 18～124 步；原先这一整段仍标为「按第二个按钮」（N1）。",
                "修复后等待段单独成为一个子目标，选项不再是 B；交换后子目标坐标随容器移动刷新（F4）。",
                "button_left / button_right 按机器人坐标系命名，「按第一个按钮」与选项 a 指向同一按钮（F3），子目标文字不变。",
            ],
            "note": "只涉及 xhard1～xhard4。" + ("" if fixed else "当前目录仍为修复前数据，视频中还没有等待子目标。"),
        },
        "PickHighlight": {
            "kind": "emphasis",
            "title": "本轮改动：任务链末尾补上「放下末块」和「按末按钮」",
            "steps": [
                "题面：先按按钮，再逐个抓起全部高亮方块，最后再按按钮结束（F1）。",
                f"子目标：末块抓起后新增 place the cube onto the table（{translate_subgoal('place the cube onto the table')}），链尾新增 press the button at <坐标>（按末按钮）；成功时点后移到末按钮。",
                "新档题面无「, which is <颜色>」后缀，来源为 V4 决策（N9，不改）。",
            ],
            "note": "只涉及 xhard1～xhard4。" + ("" if fixed else "当前目录仍为修复前数据。"),
        },
        "VideoPlaceOrder": {
            "kind": "emphasis",
            "title": "说明：「放回原位」子目标没有坐标，是设计如此",
            "steps": ["put the cube back to its original position 在新四档去掉了 at <>（N5）：原位标记在画面中被隐藏，坐标本来就无法给出。"],
            "note": "只涉及 xhard1～xhard4。",
        },
    }
    if fixed:
        notices["VideoPlaceButton"] = {
            "kind": "emphasis",
            "title": "已按 Q-C 修复：按钮前题的答案 = 按钮前最后一次放置的台",
            "steps": [
                "题面每局只剩一句：按钮前题问「where it was last placed before the button was pressed」，按钮后题问「where it was first placed after the button was pressed」。",
                "删去的说法：right / immediately before/after 在双块档被另一块的放置打断，时序不成立（N3）；previously placed 在有额外放置时不唯一（N4）。",
                "台可交换：演示结束后两张台互换位置，答案按台实体判定，需要追踪答案台交换后的位置。",
                "xhard3 / xhard4 台数由 4 增为 5（N2），额外放台落到空闲的第 5 台，不再出现原地空转或两块同台（F6）。",
                "「放回原位」子目标没有坐标，是设计如此（N5）。",
            ],
            "note": "台代号与下方演示子目标列表一致（按首次放置顺序编 A、B、C…），不是视频中的标签；带「题目所问」标记的是答案那次放置。",
        }
    else:
        notices["VideoPlaceButton"] = {
            "kind": "issue",
            "title": "已知问题：部分视频的程序答案与题目含义不一致（修复前数据）",
            "steps": [
                "已确认受影响的是 xhard3 示例4和示例7（episode 3、6）。",
                "以示例4为例：蓝色方块（正确方块）先放到台B，再被拿起放到台C，然后按按钮。",
                "题目问蓝色方块在按钮前最后一次放到的台，因此按演示应回答台C，并追踪该台交换后的所在位置。",
                "当前程序仍将更早的台B绑定为正确答案；视频中的执行按这个答案完成，所以内部记录显示成功。",
                "本轮已按 Q-C 改为「按钮前最后一次放置的台」，新数据回传后此说明将替换。",
            ],
            "note": "台代号与下方演示子目标列表一致（按首次放置顺序编 A、B、C、D），不是视频中的标签；列表里带「题目所问」标记的是按题意应答的那次放置。视频显示的成功只代表通过当前程序判定，不能证明符合题目含义。",
        }
    return notices


TIER_NOTES_FIXED = {  # 新数据才有的档位说明
    ("VideoPlaceButton", "xhard3"): "台数 5（原 4，N2）；额外放台落在空闲台。",
    ("VideoPlaceButton", "xhard4"): "台数 5（原 4，N2）；额外放台落在空闲台。",
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
    # site-v11：新四档修复后（§九）VPB 每局只剩一句 last placed before / first placed after
    fixed = re.search(r"where it was (last placed before|first placed after) the button", text)
    # 2026-09-27 用户要求题目用英文原文展示：保留原句，中文含义作注释
    if side:
        return {"color": color.group(1), "mode": side.group(1), "n": None, "text": text.strip()}
    if fixed:
        return {"color": color.group(1), "mode": fixed.group(1).split()[-1], "n": None, "text": text.strip()}
    if order:
        return {"color": color.group(1), "mode": "order", "n": ORDINAL_EN[order.group(1)], "text": text.strip()}
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
        goals = [decode(value) for value in group["setup/task_goal"][()]]
        goal = parse_goal(goals[0])
        # 修复后数据判据：只有一句且为新句式（旧数据首句恒为 right before/after 或 the N-th target）
        goal["fixed"] = len(goals) == 1 and any(
            phrase in goals[0] for phrase in ("where it was last placed before", "where it was first placed after"))
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
        # 旧数据程序答案取按钮前第一次放置（已披露问题）；修复后（Q-C）取最后一次
        asked, program = (side[-1], side[-1] if goal.get("fixed") else side[0]) if side else (None, None)
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
    # question = 英文原句（用户 2026-09-27「题目用英文」），question_zh = 中文含义注释（保持不变）
    flow = {"question": f"题目：{goal.get('text', '')}".strip("：") if goal.get("text") else question_zh(goal),
            "question_zh": question_zh(goal), "cubes": [
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
            if item["point"] is None and item["grounded"].strip() == "put the cube back to its original position":
                text += "（该子目标无坐标，设计如此）"
        # en = 子目标英文原文（grounded_subgoal 原句），text = 中文含义注释（保持不变）
        step = {"en": item["grounded"].strip(), "text": text, "role": role, "asked": index == asked}
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
    public = {"schema": "v6-site-catalog/2", "tasks": []}
    private = {}
    excluded = []
    flow_audit = []
    mismatched = set()
    cards = {}
    for task, name in NAMES.items():
        item = {"id": task, "name": name, "note": NOTES[task], "tiers": []}
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
    # 判定目录数据是否为修复后（v6-02）：VPB 新四档样例题面全为新句式；混合即报错
    vpb_fixed = {bool(a["goal"].get("fixed")) for a in flow_audit if a["task"] == "VideoPlaceButton" and a["tier"] != "hard"}
    if len(vpb_fixed) > 1:
        raise ValueError("VPB 新四档样例混有修复前与修复后题面")
    fixed = vpb_fixed == {True}
    expected_mismatch = set() if fixed else KNOWN_ISSUE_SAMPLES
    notices = task_notices(fixed)
    for item in public["tasks"]:
        notice = notices.get(item["id"])
        if notice:
            item["known_issue"] = notice
        for card in item["tiers"]:
            if fixed and (item["id"], card["id"]) in TIER_NOTES_FIXED:
                card["note"] = TIER_NOTES_FIXED[item["id"], card["id"]]
    public["data_fixed"] = fixed
    public["changelog"] = {
        "title": "本轮改动（V6 语义审查修复，只涉及 xhard1～xhard4）",
        "status": "当前视频已按本轮修复重新生成。" if fixed else "当前目录仍为修复前数据（v6-01），下列改动尚未体现在视频中。",
        "items": CHANGELOG,
    }
    public["known_issues"] = {"title": "已知问题（原三档同样存在，本轮不修）", "note": KNOWN_ISSUES_NOTE, "groups": KNOWN_ISSUES}
    listed = ",".join(f"{tier}:{episode}" for _, tier, episode in sorted(mismatched))
    if mismatched != expected_mismatch:
        print(f"KNOWN_ISSUE_MATCH=FAIL mismatched={listed}")
        raise ValueError("题意与程序答案不一致的样例集合与已披露集合不同")
    print(f"KNOWN_ISSUE_MATCH=PASS mismatched={listed or 'none'} data_fixed={fixed}")
    print(f"SITE_V11_CHANGELOG={'PASS' if len(CHANGELOG) == 15 else 'FAIL'} items={len(CHANGELOG)} known_issue_groups={len(KNOWN_ISSUES)}")
    print(f"FLOW_LABELS=PASS samples={len(flow_audit)} cubes={sum(len(a['cubes']) for a in flow_audit)} "
          f"asked={sum(1 for a in flow_audit if a['asked_index'] is not None)}")
    return public, private, excluded, flow_audit


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--delivery", type=Path, default=ARTIFACTS / "newtask-v6/s4-relaunch-02/verification/final-delivery.json")
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
