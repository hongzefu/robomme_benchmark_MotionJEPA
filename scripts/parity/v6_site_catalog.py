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


def subgoal_flow(task, tier):
    """只描述已由源码及已有轨迹核对的放置任务子目标。"""
    if task == "VideoPlaceOrder":
        if tier == "hard":
            demo = ["拿起一个方块，依次放到2–4个不同的平台上。",
                    "在其中一次放台后按按钮；继续完成这块的访问序列。",
                    "将方块放到桌面位置，结束演示；末尾两个平台交换位置。"]
        else:
            counts = {"xhard1": "2次与3次（合计5次）", "xhard2": "各3次（合计6次）",
                      "xhard3": "3次与4次（合计7次）", "xhard4": "各4次（合计8次）"}[tier]
            demo = [f"两个方块分别访问平台{counts}；次数不同的两种分配会随机对应到方块。",
                    "先完成第一个方块的全部访问并放回原位，再完成第二个方块并归位。",
                    "按按钮插在某一次目标台放置之后；演示末尾两个平台交换位置。"]
        return {"demo_steps": demo,
                "remember": "分别记住每个颜色方块按先后顺序访问的平台，并追踪平台交换后的新位置。",
                "execution_steps": ["读取题目指定的方块颜色和第几次访问。", "只拾取该方块，放到那一次访问的平台当前所在位置。"],
                "note": "每次访问均包含抓起方块再放下，不是持物滑过平台。执行阶段不重演完整访问序列。每块内部不重复访问同一台，两块可以共享台；归位不计入放台次数。按按钮是演示中的插入动作，不是平台交换的触发动作。"}
    if task == "VideoPlaceButton":
        demo = {
            "hard": ["将一个方块放到按钮前的目标台。", "按按钮，再将方块放到按钮后的目标台。", "将方块放到桌面位置。"],
            "xhard1": ["将一个方块放到按钮前的目标台。", "按按钮，再依次放到按钮后的目标台和一个额外台。", "将方块放回原位。"],
            "xhard2": ["将一个方块依次放到按钮前的目标台和一个额外台。", "按按钮，再依次放到按钮后的目标台和一个额外台。", "将方块放回原位。"],
            "xhard3": ["将两个方块依次放到各自按钮前的目标台，再将其中一个放到额外台。", "按按钮，再将两个方块依次放到各自按钮后的目标台。", "将两个方块分别放回原位。"],
            "xhard4": ["将两个方块依次放到各自按钮前的目标台，再将其中一个放到额外台。", "按按钮，将两个方块依次放到各自按钮后的目标台，再将另一个放到额外台。", "将两个方块分别放回原位。"],
        }[tier]
        extra_before = tier in {"xhard2", "xhard3", "xhard4"}
        execution = "只拾取指定方块并放到答案平台，不重演演示动作。"
        note = "每次放台都包含重新抓起再放下；归位不计入放台次数。"
        if extra_before:
            execution = "只拾取指定方块并放到程序绑定的答案台；答案与题目措辞的已知差异见说明。"
            if tier == "xhard3":
                note += "当前所列示例4和示例7（episode 3、6）存在演示与答案不一致：按钮前最后放到额外台，程序却将更早的基础台判为正确；本档其余所列样例未触发。这里保留实际旧视频及其执行结果，不将这两个样例视为记忆问题已正确实现。"
            else:
                note += "按钮前额外放台的候选存在答案仍绑定更早基础台的机制风险，但本档当前所列三个样例未触发该问题；已确认的交付冲突出现在xhard3示例4和示例7。"
        return {"demo_steps": [*demo, "演示结束后两个平台交换位置，再进入执行阶段。"],
                "remember": "题目问按钮前时，记住该颜色方块在按按钮前最后一次放到的平台；问按钮后时，记住按钮后第一次放到的平台，并追踪平台交换后的所在位置。",
                "execution_steps": ["读取题目指定的方块颜色与按钮前／后的关系。", execution],
                "note": note}
    return None


def build_catalog(delivery, baseline, plan):
    values = gradients(plan)
    public = {"schema": "v6-site-catalog/1", "tasks": []}
    private = {}
    excluded = []
    cards = {}
    for task, name in NAMES.items():
        item = {"id": task, "name": name, "note": NOTES[task], "tiers": []}
        if task == "VideoPlaceButton":
            item["known_issue"] = {
                "title": "已知问题：部分视频的程序答案与题目含义不一致",
                "steps": [
                    "已确认受影响的是 xhard3 示例4和示例7（episode 3、6）。",
                    "以示例4为例：蓝色方块先放到平台A，再被拿起放到平台B，然后按按钮。",
                    "题目问蓝色方块在按钮前最后一次放到的平台，因此按演示应回答平台B，并追踪该平台交换后的所在位置。",
                    "当前程序仍将更早的平台A绑定为正确答案；视频中的执行按这个答案完成，所以内部记录显示成功。",
                ],
                "note": "A、B仅为这里解释先后访问的平台所用的代号，不是视频中的标签。视频显示的成功只代表通过当前程序判定，不能证明符合题目含义。此处保留原视频并说明问题，没有修复源码或重生成数据；其他所列样例不因此被判定为错误。",
            }
        for tier in (("hard", "xhard4") if task in EXTRA else TIERS):
            card = {"id": tier, "label": tier, "gradient": values[task][tier], "videos": []}
            flow = subgoal_flow(task, tier)
            if flow is not None:
                card["subgoal_flow"] = flow
            cards[task, tier] = card
            item["tiers"].append(card)
        public["tasks"].append(item)

    def add(task, tier, episode, paths):
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
            cards[task, tier]["videos"].append({"id": media_id, "label": label,
                                                 "url": f"/media/{media_id}"})

    rows = json.loads(delivery.read_text(encoding="utf-8"))["successes"]
    if len(rows) != 165:
        raise ValueError(f"正式成功轨迹应为165条，实际{len(rows)}")
    for row in rows:
        if row.get("state") != "success":
            raise ValueError("交付successes中包含非成功轨迹")
        media = [Path(entry["path"]) for entry in row["files"] if Path(entry["path"]).suffix.lower() == ".mp4"]
        add(row["task"], row["difficulty"], row["episode"], media)
    hard_rows = [row for row in json.loads(baseline.read_text(encoding="utf-8"))["results"]
                 if row.get("difficulty") == "hard" and row.get("ok") is True]
    for row in hard_rows:
        folder = Path(row["raw_h5_path"]).parent.parent / "videos"
        add(row["task"], "hard", row["episode"], list(folder.glob("*.mp4")))
    for (task, tier), card in cards.items():
        if not card["videos"]:
            raise ValueError(f"缺少成功视频：{task}/{tier}")
    return public, private, excluded


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
    public, private, excluded = build_catalog(args.delivery, args.baseline, args.plan)
    args.out.mkdir(parents=True, exist_ok=True)
    for name in ("catalog.json", "media-private.json", "excluded-tail-clips.json"):
        if (args.out / name).exists():
            raise FileExistsError(f"拒绝覆盖已有目录文件：{name}")
    for name, data in (("catalog.json", public), ("media-private.json", private),
                       ("excluded-tail-clips.json", {"count": len(excluded), "clips": excluded})):
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
