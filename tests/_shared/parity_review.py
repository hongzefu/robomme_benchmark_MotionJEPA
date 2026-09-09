"""逐图目视辅助：原尺寸排列三路双相机原图区，绑定原图版散列。

差分两列仍保留在原始图版及机检统计中；此处仅裁出三路原图区便于逐张查看，
不缩放、不插值。prepare 只准备画板，mark 只在实际查看指定画板后由检查者调用。
"""

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare(index_path, output):
    payload = json.loads(Path(index_path).read_text())
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    items = []
    for cell, detail in payload["cells"].items():
        if detail.get("not_rendered"):
            raise ValueError(f"{cell} 有未出图的关键帧")
        for frame, record in detail.get("montages", {}).items():
            if sha(record["montage"]) != record["montage_sha256"]:
                raise ValueError(f"图版散列不匹配：{record['montage']}")
            items.append({"cell": cell, "frame": frame, "path": record["montage"], "sha256": record["montage_sha256"],
                "pixel_differences": record["difference"]})
    manifest = {"source_index": str(index_path), "source_sha256": sha(index_path), "boards": []}
    for offset in range(0, len(items), 4):
        group = items[offset:offset + 4]
        images = []
        for item in group:
            with Image.open(item["path"]) as image:
                # 原图版共五列：A1/B/C 与两列差分；前三列逐像素原样裁出。
                width = (image.width - 4) // 5 * 3 + 4
                images.append(image.crop((0, 0, width, image.height)))
        width, height = max(i.width for i in images), max(i.height for i in images)
        board = Image.new("RGB", (2 * width, 2 * height), (45, 45, 45))
        for index, image in enumerate(images):
            board.paste(image, ((index % 2) * width, (index // 2) * height))
        target = output / f"board_{offset // 4:03d}.png"
        board.save(target)
        manifest["boards"].append({"number": offset // 4, "path": str(target.resolve()), "sha256": sha(target),
                                   "items": group, "reviewed": False})
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(f"准备 {len(items)} 张原图版，共 {len(manifest['boards'])} 个原尺寸画板；尚未目视。")


def mark(manifest_path, numbers, note):
    path = Path(manifest_path)
    manifest = json.loads(path.read_text())
    found = set()
    for board in manifest["boards"]:
        if board["number"] not in numbers:
            continue
        if sha(board["path"]) != board["sha256"] or any(sha(item["path"]) != item["sha256"] for item in board["items"]):
            raise ValueError("画板或原图版已经改变，旧目视结论不能沿用")
        board.update(reviewed=True, reviewer="Codex 主 agent", note=note)
        found.add(board["number"])
    if found != set(numbers):
        raise ValueError("指定画板编号不存在")
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(f"登记已实际查看的 {len(found)} 个画板。")


def collect(run_id, cell):
    """已完成四路的单格先比较再出图，使目视可与后续格生成同时推进。"""
    from tests._shared import native_sampling_parity as parity
    from tests._shared.parity_keyframes import export_cell
    from tests._shared.parity_runner import REPO_ROOT
    root = REPO_ROOT
    if any(Path(value).name != value or value in (".", "..") for value in (run_id, cell)):
        raise ValueError("运行编号与格名必须为单个目录名")
    cases = json.loads((root / "docs/validation/newtask-v2/cases.json").read_text())["cases"]
    case = next(item for item in cases if item["cell"] == cell)
    run = root / "artifacts/parity" / run_id
    evidence_root = root / "artifacts/parity-evidence" / run_id
    target = root / "artifacts/parity-incremental" / run_id / cell
    result = parity.pack_run(run, evidence_root, [case], target)
    if not result["passed"]:
        raise ValueError("该格未通过完整比较，不能开始目视")
    frames = {label: parity._single_h5(parity._episode_dir(run, cell, label)) for label in ("A1", "B", "C")}
    evidence = {label: parity.load_evidence(evidence_root / label / f"{case['task']}_seed{case['seed']}", case["difficulty"]) for label in frames}
    detail = export_cell(cell, case, frames, root / "artifacts/keyframes" / run_id, evidence_paths=evidence)
    index = target / "keyframe_index.json"
    index.write_text(json.dumps({"run": run_id, "cells": {cell: detail}}, ensure_ascii=False, indent=2) + "\n")
    prepare(index, root / "artifacts/review" / run_id / cell)


def finalize(index_path, review_root, output):
    """将实际目视逐项与最终出图索引重新对齐，拒绝未查看、缺帧及任何图片变化。"""
    index_path = Path(index_path)
    payload = json.loads(index_path.read_text())
    report = {"run": payload["run"], "cells": {}, "passed": True, "image_count": 0}
    for cell, detail in payload["cells"].items():
        if detail.get("not_rendered") or not detail.get("montages"):
            raise ValueError(f"{cell}: 缺少完整图版")
        manifest_path = Path(review_root) / cell / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        reviewed = {}
        for board in manifest["boards"]:
            if not board.get("reviewed"):
                raise ValueError(f"{cell}: 画板 {board['number']} 未目视")
            if sha(board["path"]) != board["sha256"]:
                raise ValueError(f"{cell}: 画板散列已改变")
            for item in board["items"]:
                frame = item["frame"]
                if item["cell"] != cell or frame in reviewed:
                    raise ValueError(f"{cell}: 目视身份重复或错位")
                if frame not in detail["montages"]:
                    raise ValueError(f"{cell}: 目视记录包含未规定的帧 {frame}")
                expected = detail["montages"][frame]
                if item["sha256"] != expected["montage_sha256"] or sha(expected["montage"]) != item["sha256"]:
                    raise ValueError(f"{cell}/{frame}: 原图版散列已改变")
                if any(value["max_abs"] != 0 or value["nonzero_pixels"] != 0 for value in expected["difference"].values()):
                    raise ValueError(f"{cell}/{frame}: 像素比较存在差异")
                reviewed[frame] = {"montage_sha256": item["sha256"], "board_sha256": board["sha256"],
                    "reviewer": board["reviewer"], "note": board["note"], "passed": True}
        if set(reviewed) != set(detail["montages"]):
            raise ValueError(f"{cell}: 规定关键帧未全部目视")
        report["cells"][cell] = {"image_count": len(reviewed), "passed": True, "images": reviewed,
                                  "review_manifest_sha256": sha(manifest_path)}
        report["image_count"] += len(reviewed)
        detail["status"] = "通过"
    report["cell_count"] = len(report["cells"])
    index_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    report["keyframe_index_sha256"] = sha(index_path)
    Path(output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(f"最终目视复核通过：{report['cell_count']} 格，{report['image_count']} 张图版。")
    return report


def main():
    parser = argparse.ArgumentParser(description="原尺寸关键帧目视与散列绑定")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--index", required=True)
    p.add_argument("--output", required=True)
    m = sub.add_parser("mark")
    m.add_argument("--manifest", required=True)
    m.add_argument("--boards", required=True)
    m.add_argument("--note", required=True)
    c = sub.add_parser("collect")
    c.add_argument("--run-id", required=True)
    c.add_argument("--cell", required=True)
    f = sub.add_parser("finalize")
    f.add_argument("--index", required=True)
    f.add_argument("--review-root", required=True)
    f.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args.index, args.output)
    elif args.command == "mark":
        mark(args.manifest, [int(n) for n in args.boards.split(",")], args.note)
    elif args.command == "collect":
        collect(args.run_id, args.cell)
    else:
        finalize(args.index, args.review_root, args.output)


if __name__ == "__main__":
    main()
