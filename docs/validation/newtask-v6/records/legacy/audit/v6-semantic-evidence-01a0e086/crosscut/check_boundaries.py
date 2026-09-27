"""只读检查既有交付HDF5的子目标边界，不导入或运行仿真源码。"""
import argparse
import json
from pathlib import Path

import h5py

AUDIT_BASE = "0a3f989b0dfcff12a3cbb34a8112cb56864c7ee8"


def decode(dataset):
    value = dataset[()]
    return value.decode() if isinstance(value, bytes) else str(value)


def inspect(row):
    path = next(item["path"] for item in row["files"] if item["path"].endswith(".h5"))
    result = {key: row[key] for key in ("task", "difficulty", "episode")}
    result.update(h5=path, boundaries=[], mismatches=[])
    with h5py.File(path, "r") as handle:
        group = handle[f'episode_{row["episode"]}']
        frames = sorted((key for key in group if key.startswith("timestep_")),
                        key=lambda key: int(key.split("_")[1]))
        for key in frames:
            info = group[key]["info"]
            if not bool(info["is_subgoal_boundary"][()]):
                continue
            entry = {"t": int(key.split("_")[1]), "demo": bool(info["is_video_demo"][()])}
            entry.update({field: decode(info[field]) for field in (
                "simple_subgoal", "simple_subgoal_online", "grounded_subgoal", "grounded_subgoal_online")})
            result["boundaries"].append(entry)
            if (entry["simple_subgoal"] == entry["simple_subgoal_online"]
                    and entry["grounded_subgoal"] != entry["grounded_subgoal_online"]
                    and "<" in entry["grounded_subgoal"]
                    and "<" in entry["grounded_subgoal_online"]):
                result["mismatches"].append(entry)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--compare", type=Path, help="与此前结果比较所选身份，不覆盖既有文件")
    args = parser.parse_args()
    rows = json.loads(args.manifest.read_text())["successes"]
    if len(rows) != 165:
        raise ValueError(f"交付范围应为165，实际{len(rows)}")
    if args.limit is not None:
        if args.limit < 1:
            parser.error("limit必须大于零")
        rows = rows[:args.limit]
    results = [inspect(row) for row in rows]
    if args.out:
        with args.out.open("x", encoding="utf-8") as stream:
            json.dump(results, stream, ensure_ascii=False, indent=2)
    if args.compare:
        previous = json.loads(args.compare.read_text())
        identity = lambda row: (row["task"], row["difficulty"], row["episode"])
        reference = {identity(row): row for row in previous}
        for row in results:
            if row != reference[identity(row)]:
                raise ValueError(f"与既有边界结果不一致：{identity(row)}")
    print(f"BOUNDARY_SCAN=PASS episodes={len(results)} mismatched_episodes={sum(bool(row['mismatches']) for row in results)} audit_base={AUDIT_BASE}")
    print("字段差异不等于题意错误；需结合当前图像、动作点和缓存产生时刻分别判读。")


if __name__ == "__main__":
    main()
