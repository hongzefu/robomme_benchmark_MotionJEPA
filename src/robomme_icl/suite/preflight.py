"""有限时间内诊断完整物体几何，不发布清单、不宣称物理 rollout 通过。"""

import argparse
import json
import time

from .compiler import candidate_for_slot, distribution_summary, load_configs, plan_slots
from .spec import TASKS, content_hash


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-config")
    parser.add_argument("--position-config")
    parser.add_argument("--tasks", nargs="+", choices=TASKS)
    parser.add_argument("--first-slot-only", action="store_true")
    parser.add_argument("--max-seconds", type=float, default=240.0)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if not 0 < args.max_seconds <= 240:
        parser.error("单次短诊断的 max-seconds 必须位于 (0,240]")
    from robomme_icl.geometry import validate_spec_geometry
    from robomme_icl.io.paths import output_path

    destination = output_path(args.output, create_parent=True)
    if destination.exists():
        raise FileExistsError(f"诊断报告已存在，拒绝覆盖：{destination}")
    started = time.monotonic()
    configs = load_configs(args.task_config, args.position_config)
    slots = plan_slots(*configs, tasks=args.tasks)
    if args.first_slot_only:
        first = {}
        for slot in slots:
            first.setdefault(slot["task_kind"], slot)
        slots = list(first.values())
    reports = []
    for slot in slots:
        if time.monotonic() - started > args.max_seconds:
            break
        task_start = time.monotonic()
        rejects, accepted = [], None
        for candidate in range(slot["max_candidates"]):
            if time.monotonic() - started > args.max_seconds:
                break
            spec = candidate_for_slot(slot, candidate)
            result = validate_spec_geometry(spec)
            if result["ok"]:
                accepted = {"candidate_index": candidate, "spec_hash": spec.spec_hash, "geometry": result}
                break
            rejects.append({"candidate_index": candidate, "reasons": result["reasons"]})
        row = {"task": slot["task_kind"], "slot_id": slot["slot_id"], "seed": slot["seed"],
               "parameters": slot["parameters"], "accepted": accepted, "rejects": rejects,
               "elapsed_seconds": time.monotonic() - task_start}
        reports.append(row)
        print(json.dumps({"slot": slot["slot_id"], "candidate": accepted["candidate_index"] if accepted else None,
                          "rejections": len(rejects), "seconds": round(row["elapsed_seconds"], 3)}, ensure_ascii=False), flush=True)
    report = {"coverage": "compound_geometry_only", "status": "diagnostic_only",
              "elapsed_seconds": time.monotonic() - started, "expected_slots": len(slots),
              "examined_slots": len(reports), "passed_slots": sum(row["accepted"] is not None for row in reports),
              "task_config_hash": content_hash(configs[0]), "position_config_hash": content_hash(configs[1]),
              "distribution": distribution_summary(slots), "slots": reports}
    with destination.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({key: value for key, value in report.items() if key not in ("distribution", "slots")}, ensure_ascii=False), flush=True)
    return 0 if report["passed_slots"] == report["expected_slots"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
