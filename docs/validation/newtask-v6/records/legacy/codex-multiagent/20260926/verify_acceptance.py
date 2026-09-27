"""只读复核本次 App 并发快照、模型和探针停止记录。"""

import json
from pathlib import Path


evidence_dir = Path(__file__).parent
evidence = json.loads((evidence_dir / "acceptance.json").read_text())
cleanup = json.loads((evidence_dir / "cleanup.json").read_text())
expected = {f"/root/probe{i:02d}" for i in range(1, 17)}
assert len(evidence["models"]) == 16
assert {item["agent_path"] for item in evidence["models"]} == expected

calls = {}
snapshot_found = False
rejection_found = False
interruptions = set()
root_models = set()
for line in Path(evidence["parent_rollout"]).read_text().splitlines():
    entry = json.loads(line)
    payload = entry.get("payload", {})
    if entry["type"] == "turn_context":
        root_models.add(payload["model"])
    if entry["type"] != "response_item":
        continue
    if payload.get("type") == "function_call":
        args = json.loads(payload.get("arguments", "{}"))
        calls[payload["call_id"]] = (payload.get("name"), args)
    elif payload.get("type") == "function_call_output":
        name, args = calls.get(payload.get("call_id"), (None, {}))
        if name == "list_agents" and entry["timestamp"] == evidence["snapshot"]["timestamp"]:
            actual = json.loads(payload["output"])["agents"]
            running = {a["agent_name"] for a in actual if a["agent_status"] == "running"}
            assert running == expected | {"/root"}
            snapshot_found = True
        if name == "spawn_agent" and args.get("task_name") == "probe17":
            assert payload["output"] == evidence["rejected_17"]["output"]
            rejection_found = "agent thread limit reached" in payload["output"]
        if name == "interrupt_agent":
            assert json.loads(payload["output"])["previous_status"] == "running"
            interruptions.add(args["target"].rsplit("/", 1)[-1])

assert root_models == {"gpt-6-astra"}
assert snapshot_found and rejection_found
assert interruptions == {f"probe{i:02d}" for i in range(1, 17)}
for item in evidence["models"]:
    entries = [json.loads(line) for line in Path(item["rollout"]).read_text().splitlines()]
    meta = next(e["payload"] for e in entries if e["type"] == "session_meta")
    spawn = meta["source"]["subagent"]["thread_spawn"]
    assert meta["id"] == item["thread_id"]
    assert spawn["parent_thread_id"] == evidence["thread_id"]
    assert spawn["agent_path"] == item["agent_path"]
    contexts = [e["payload"] for e in entries if e["type"] == "turn_context"]
    assert contexts and all(c["model"] == "gpt-6-luna" and c["effort"] == "low" for c in contexts)

assert cleanup["cleanup"] == "PASS" and cleanup["interrupted_count"] == 16
assert all(a["agent_status"] == "interrupted" for a in cleanup["last_agent_list"]["agents"] if a["agent_name"] != "/root")
print("CONCURRENT_16=PASS running=16 root_excluded=1")
print("MODELS_16=PASS model=gpt-6-luna effort=low checked=16")
print("LIMIT_17=PASS rejected=1")
print("CLEANUP=PASS interrupted=16 running_children=0")
