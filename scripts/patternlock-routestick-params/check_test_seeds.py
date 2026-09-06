"""核对本轮实跑的 test 数据：seed 是否与 test metadata 逐条相等。

generate_dataset_newseed.py 是生成型入口，seed 由公式自算、失败会 attempt+1 换 seed。
test metadata 里 50 条全部是 attempt=0 的尾号，所以只要首次 attempt 成功，seed 就与原版逐条相同。
不一致的条目不改数，原样列出交人判断，并在报告里标注该 episode 的时长来自不同 seed。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
METADATA_ROOT = HERE.parents[1] / "src" / "robomme" / "env_metadata"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="核对实跑 test 的 seed 与 metadata 是否逐条一致")
    parser.add_argument("--results", default=str(HERE / "outputs" / "test-h5" / "episode_results.jsonl"))
    parser.add_argument("--split", default="test")
    parser.add_argument("--out", default=str(HERE / "outputs" / "test_seed_check.json"))
    args = parser.parse_args(argv)

    rows = []
    with Path(args.results).open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))

    # 任务列表从结果里取，不写死——同一个脚本要同时服务 Imitation 与 Counting 两批
    expected: dict[tuple[str, int], int] = {}
    for task in sorted({row["task"] for row in rows}):
        path = METADATA_ROOT / args.split / f"record_dataset_{task}_metadata.json"
        for record in json.loads(path.read_text(encoding="utf-8"))["records"]:
            expected[(task, int(record["episode"]))] = int(record["seed"])

    succeeded = [r for r in rows if r.get("ok")]
    mismatched = []
    matched = 0
    for row in succeeded:
        key = (row["task"], int(row["episode"]))
        want = expected.get(key)
        if want is None:
            continue
        if int(row["seed"]) == want:
            matched += 1
        else:
            mismatched.append(
                {
                    "task": row["task"],
                    "episode": int(row["episode"]),
                    "metadata_seed": want,
                    "generated_seed": int(row["seed"]),
                    "attempt": row.get("attempt"),
                }
            )

    failed = [
        {"task": r["task"], "episode": r["episode"], "failure_class": r.get("failure_class")}
        for r in rows
        if not r.get("ok")
    ]
    report = {
        "total_records": len(rows),
        "succeeded": len(succeeded),
        "seed_matched": matched,
        "seed_mismatched": mismatched,
        "failed_attempts": len(failed),
    }
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"成功 {len(succeeded)} 条，seed 与 metadata 一致 {matched} 条，"
        f"不一致 {len(mismatched)} 条，失败 attempt {len(failed)} 次"
    )
    for item in mismatched:
        print(f"  {item['task']} ep{item['episode']}: metadata {item['metadata_seed']} -> 实跑 {item['generated_seed']}（attempt {item['attempt']}）")
    print(f"已写出 {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
