"""V6 三档实测 worker：进程内调用 generate_dataset_newseed._worker（与正式生成同一 gym.make/录像器/规划器/失败分类），
只做只读观测补丁：RecordWrapper.close 前取 elapsed_steps 与 SpecRecorder 内容；逐局读完 h5 后立即删产物。
可选补丁（仅本进程内，不改仓库文件）：
  vpo_visit_max3：VideoPlaceOrder 模块内 torch.randint(2, 5, ...) 改为 randint(2, 4, ...)，模拟 v∈[2,3]。"""
import json
import os
import shutil
import sys
import time
from pathlib import Path

REPO = Path(os.environ["PROBE_REPO"])
CAPTURE = {}
_PATCHED = set()


def _plain(x, depth=0):
    if isinstance(x, dict):
        return {k: _plain(v, depth + 1) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_plain(v, depth + 1) for v in x]
    try:
        json.dumps(x)
        return x
    except TypeError:
        return repr(x)


def init(gpu):
    sys.path.insert(0, str(REPO / "scripts"))
    sys.path.insert(0, str(REPO / "src"))
    import generate_dataset_newseed as gen
    gen._pool_init(gpu, None, str(REPO / "src"))
    from robomme.env_record_wrapper import RobommeRecordWrapper
    orig_close = RobommeRecordWrapper.close

    def close(self):
        try:
            env = self.unwrapped
            es = env.elapsed_steps
            CAPTURE["elapsed_steps"] = int(es[0]) if hasattr(es, "__len__") else int(es)
            CAPTURE["n_tasks"] = len(getattr(env, "task_list", []) or [])
            CAPTURE["task_index"] = getattr(env, "current_task_index", None)
            spec = getattr(env, "_spec", None)
            if spec is not None:
                CAPTURE["spec"] = _plain(spec.to_dict())
        except Exception as exc:  # noqa: BLE001
            CAPTURE["capture_error"] = repr(exc)
        return orig_close(self)

    RobommeRecordWrapper.close = close


def apply_patch(name):
    if name in _PATCHED:
        return
    if name == "vpo_visit_max3":
        import importlib
        vpo = importlib.import_module("robomme.robomme_env.VideoPlaceOrder")
        vpo = sys.modules["robomme.robomme_env.VideoPlaceOrder"]
        real = vpo.torch

        class _TorchProxy:
            def __getattr__(self, attr):
                return getattr(real, attr)

            def randint(self, *args, **kwargs):
                if len(args) >= 2 and args[0] == 2 and args[1] == 5:
                    args = (2, 4) + tuple(args[2:])
                return real.randint(*args, **kwargs)

        vpo.torch = _TorchProxy()
    else:
        raise ValueError(name)
    _PATCHED.add(name)


def run(item):
    import generate_dataset_newseed as gen
    import h5py
    for p in item["patches"]:
        apply_patch(p)
    cfg = json.loads((Path(item["dir"]) / item["config"]).read_text())["sampling_config"]
    out = Path(item["tmp_root"]) / f"{item['task']}_{item['tier']}_{item['seed']}"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    CAPTURE.clear()
    job = gen.EpisodeJob(task=item["task"], episode=9, attempt=0, seed=item["seed"], difficulty="xhard",
                         output_root=str(out), repo_root=str(REPO), sampling_config=cfg)
    t0 = time.time()
    res = gen._worker(job)
    row = {k: item[k] for k in ("task", "tier", "tier_idx", "i", "seed", "patches")}
    row.update(ok=bool(res.get("ok")), failure_class=res.get("failure_class"), error_type=res.get("error_type"),
               error=(res.get("error") or "")[:400], wall_s=round(time.time() - t0, 1), phases=res.get("phases"),
               timestep_count=res.get("timestep_count"))
    if not row["ok"] and res.get("traceback"):
        row["traceback_tail"] = res["traceback"][-1200:]
    row["elapsed_steps"] = CAPTURE.get("elapsed_steps")
    row["n_tasks"] = CAPTURE.get("n_tasks")
    row["task_index"] = CAPTURE.get("task_index")
    spec = CAPTURE.get("spec") or {}
    row["spec_objects"] = spec.get("objects")
    acts = spec.get("actions") or {}
    row["spec_actions_small"] = {k: v for k, v in acts.items() if len(json.dumps(v)) < 300} if isinstance(acts, dict) else None
    if "capture_error" in CAPTURE:
        row["capture_error"] = CAPTURE["capture_error"]
    h5 = gen._h5_path(out, job)
    if row["ok"] and h5.exists():
        try:
            with h5py.File(h5, "r") as f:
                g = f[list(f.keys())[0]]
                steps = [k for k in g.keys() if k.startswith("timestep_")]
                demo = sum(bool(g[k]["info"]["is_video_demo"][()]) for k in steps)
            row["h5_steps"] = len(steps)
            row["h5_demo"] = demo
            row["h5_nondemo"] = len(steps) - demo
        except Exception as exc:  # noqa: BLE001
            row["h5_error"] = repr(exc)
    shutil.rmtree(out, ignore_errors=True)
    return row
