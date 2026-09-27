"""只读探针：以运行时覆盖 sampling_config 的方式，把 xhard 的数值换成 V6 新档值，只做 reset 统计布局失败率。
不改任何仓库文件；sampling 快照取 scripts/configs/newtask-v5/sampling_config.json，gym.make 参数与 v4_specs 抽签逐字相同。
用法：python reset_probe.py <task> <variant> <n> <out.jsonl> [seed_base]
"""
import copy, json, sys, time, traceback, os
from pathlib import Path
REPO = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / "scripts"))
import gymnasium as gym
import robomme.robomme_env  # noqa: F401  注册环境
from scripts.parity import v4_specs

VARIANTS = {
    "PickHighlight": {
        "xhard":  dict(spawn=[8, 10], pick=[5, 7]),
        "xhard1": dict(spawn=[7, 7], pick=[4, 4]),
        "xhard2": dict(spawn=[8, 8], pick=[4, 5]),
        "xhard3": dict(spawn=[8, 9], pick=[5, 6]),
        "n8": dict(spawn=[8, 8], pick=[5, 7]),
        "n9": dict(spawn=[9, 9], pick=[5, 7]),
        "n10": dict(spawn=[10, 10], pick=[5, 7]),
    },
    "BinFill": {
        "xhard": dict(put=[5, 7]), "xhard1": dict(put=[4, 5]),
        "xhard2": dict(put=[4, 6]), "xhard3": dict(put=[5, 6]),
    },
    "PickXtimes": {"xhard": dict(k=3), "xhard1": dict(k=1), "xhard2": dict(k=2), "xhard3": dict(k=3)},
    "SwingXtimes": {"xhard": dict(k=3), "xhard1": dict(k=1), "xhard2": dict(k=2), "xhard3": dict(k=3)},
}


def patched_sampling(task, variant):
    doc = json.load(open(REPO / "scripts/configs/newtask-v5/sampling_config.json"))
    s = v4_specs.task_sampling(doc, task)
    v = VARIANTS[task][variant]
    d = s["decision"]
    if task == "PickHighlight":
        d["spawn_count"]["xhard"] = list(v["spawn"]); d["highlight_count"]["xhard"] = list(v["pick"])
    elif task == "BinFill":
        d["configs"]["xhard"]["put_in_numbers"] = list(v["put"])
    else:
        d["xhard"]["distractor"]["colors"] = d["xhard"]["distractor"]["colors"][: v["k"]]
    return s


def main():
    task, variant, n, out = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]
    seed_base = int(sys.argv[5]) if len(sys.argv) > 5 else 9_100_000
    sampling = patched_sampling(task, variant)
    fo = open(out, "w")
    ok_n = 0; t0 = time.time()
    for i in range(n):
        seed = seed_base + i
        env = None; t1 = time.time()
        rec = {"task": task, "variant": variant, "i": i, "seed": seed}
        try:
            env = gym.make(task, sampling_config=copy.deepcopy(sampling), **v4_specs.env_kwargs(seed, 0))
            env.reset()
            u = env.unwrapped
            rec["ok"] = True
            if task == "PickHighlight":
                rec["n_cubes"] = len(getattr(u, "all_cubes", []))
                for attr in ("target_cubes", "highlight_cubes", "pickup_cubes", "cubes_to_pick"):
                    if hasattr(u, attr):
                        try: rec["n_pick"] = len(getattr(u, attr)); rec["pick_attr"] = attr; break
                        except Exception: pass
            if task in ("PickXtimes", "SwingXtimes"):
                rec["n_cubes"] = len(getattr(u, "all_cubes", []))
            if i < 3:
                try:
                    objs = u._spec.to_dict().get("objects", {})
                    rec["spec_objects"] = {k: v for k, v in objs.items() if len(json.dumps(v)) < 200}
                except Exception as e:  # noqa: BLE001
                    rec["spec_objects_err"] = str(e)[:100]
            ok_n += 1
        except Exception as exc:  # noqa: BLE001
            rec["ok"] = False; rec["err"] = type(exc).__name__; rec["msg"] = str(exc)[:300]
        finally:
            if env is not None:
                env.close()
        rec["wall_s"] = round(time.time() - t1, 2)
        fo.write(json.dumps(rec, ensure_ascii=False) + "\n"); fo.flush()
        if (i + 1) % 20 == 0:
            print(f"PROGRESS {task} {variant} {i+1}/{n} ok={ok_n} t={time.time()-t0:.0f}s", flush=True)
    print(f"DONE {task} {variant} n={n} ok={ok_n} fail={n-ok_n} t={time.time()-t0:.0f}s", flush=True)

if __name__ == "__main__":
    main()
