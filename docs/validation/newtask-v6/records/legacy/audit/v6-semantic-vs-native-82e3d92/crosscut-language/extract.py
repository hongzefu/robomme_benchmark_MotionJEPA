"""只读抽取 165 条新档与 144 条原三档 HDF5 的语言目标、选项与子目标边界序列（不导入仿真代码）。"""
import glob, json, os, sys
from concurrent.futures import ProcessPoolExecutor
import h5py

ROOT = "/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts"
OUT = os.path.join(ROOT, "audit/v6-semantic-vs-native-82e3d92/crosscut-language/records.json")

def dec(v):
    v = v[()] if hasattr(v, "shape") else v
    if isinstance(v, bytes):
        return v.decode()
    if hasattr(v, "tolist"):
        v = v.tolist()
    if isinstance(v, list):
        return [x.decode() if isinstance(x, bytes) else x for x in v]
    return v

def one(job):
    task, tier_hint, ep, h5, mp4s, kind = job
    rec = dict(task=task, kind=kind, episode=ep, h5=h5, mp4=[os.path.basename(m) for m in mp4s])
    with h5py.File(h5, "r") as f:
        (gk,) = [k for k in f.keys() if k.startswith("episode_")]
        g = f[gk]
        s = g["setup"]
        rec["setup"] = {k: dec(s[k]) for k in s.keys() if k not in ("front_camera_intrinsic", "wrist_camera_intrinsic")}
        ts = sorted((int(k.split("_")[1]) for k in g if k.startswith("timestep_")))
        rec["n_steps"] = len(ts)
        bnds = []
        ndemo = 0
        for t in ts:
            info = g[f"timestep_{t}"]["info"]
            demo = bool(info["is_video_demo"][()])
            ndemo += demo
            if bool(info["is_subgoal_boundary"][()]):
                e = {"t": t, "demo": demo, "simple": dec(info["simple_subgoal"]), "grounded": dec(info["grounded_subgoal"])}
                a = g[f"timestep_{t}"]["action"]
                if "choice_action" in a:
                    e["choice"] = dec(a["choice_action"])
                bnds.append(e)
        last = g[f"timestep_{ts[-1]}"]["info"]
        rec["last_completed"] = bool(last["is_completed"][()])
        rec["n_demo_steps"] = ndemo
        rec["boundaries"] = bnds
    rec["difficulty"] = rec["setup"].get("difficulty", tier_hint)
    return rec

def main():
    jobs = []
    idx = json.load(open(os.path.join(ROOT, "audit/v6-semantic-vs-native-82e3d92/new-tier-index.json")))
    for task, rows in idx.items():
        for r in rows:
            jobs.append((task, r["difficulty"], r["episode"], r["h5"], r["mp4"], "new"))
    for d in sorted(glob.glob(os.path.join(ROOT, "newtask-v6/v1/base/B/*_episode_*"))):
        name = os.path.basename(d)
        task, ep = name.rsplit("_episode_", 1)
        h5s = glob.glob(os.path.join(d, "hdf5_files/*.h5"))
        mp4s = glob.glob(os.path.join(d, "videos/*.mp4"))
        tier = None
        for m in mp4s:
            for t in ("easy", "medium", "hard"):
                if f"_{t}_" in os.path.basename(m):
                    tier = t
        for h in h5s:
            jobs.append((task, tier, int(ep), h, mp4s, "native"))
    print("jobs", len(jobs), file=sys.stderr)
    with ProcessPoolExecutor(12) as ex:
        recs = list(ex.map(one, jobs))
    json.dump(recs, open(OUT, "w"), indent=1, ensure_ascii=False)
    print("EXTRACT=PASS records=%d new=%d native=%d" % (len(recs), sum(r["kind"] == "new" for r in recs), sum(r["kind"] == "native" for r in recs)))

main()
