"""从已验证交付媒体与原 hard 基准生成仅展示难度梯度的网站目录。"""
from __future__ import annotations

import argparse
import hashlib
import json
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
    for tier in TIERS[1:]:
        result["BinFill"][tier] = f"总块数12；{result['BinFill'][tier].replace('（总块 12）', '')}"
    return result


def build_catalog(delivery, baseline, plan):
    values = gradients(plan)
    public = {"schema": "v6-site-catalog/1", "tasks": []}
    private = {}
    cards = {}
    for task, name in NAMES.items():
        item = {"id": task, "name": name, "note": NOTES[task], "tiers": []}
        for tier in (("hard", "xhard4") if task in EXTRA else TIERS):
            card = {"id": tier, "label": tier, "gradient": values[task][tier], "videos": []}
            cards[task, tier] = card
            item["tiers"].append(card)
        public["tasks"].append(item)

    def add(task, tier, episode, paths):
        if (task, tier) not in cards:
            raise ValueError(f"未知任务档位：{task}/{tier}")
        if not paths:
            raise ValueError(f"成功轨迹无视频：{task}/{tier}/{episode}")
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
    return public, private


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--delivery", type=Path, default=ARTIFACTS / "newtask-v6/s4-launch/verification/merged-provisional-delivery.json")
    parser.add_argument("--baseline", type=Path, default=ARTIFACTS / "newtask-v6/v1/base/results/B.json")
    parser.add_argument("--plan", type=Path, default=ROOT / "0925-newtask-release-v6-plan.md")
    parser.add_argument("--out", type=Path, default=ARTIFACTS / "newtask-v6/site")
    args = parser.parse_args(argv)
    if not args.out.resolve().is_relative_to(ARTIFACTS.resolve()):
        parser.error("输出必须位于本仓库artifacts")
    public, private = build_catalog(args.delivery, args.baseline, args.plan)
    args.out.mkdir(parents=True, exist_ok=True)
    for name in ("catalog.json", "media-private.json"):
        if (args.out / name).exists():
            raise FileExistsError(f"拒绝覆盖已有目录文件：{name}")
    for name, data in (("catalog.json", public), ("media-private.json", private)):
        with (args.out / name).open("x", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    print(f"SITE_CATALOG=PASS tasks={len(public['tasks'])} cards={sum(len(t['tiers']) for t in public['tasks'])} videos={len(private)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
