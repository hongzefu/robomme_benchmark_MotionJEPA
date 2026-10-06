#!/usr/bin/env python3
"""从已有视频与轨迹离线调用官方录像器；不启动仿真，不修改源视频。

逐帧一致的对象是同一组解码画面与经 trace 指纹核对的原数组。
float64 动作从 arrays.npz 恢复，禁止用有舍入损失的 f32hex 替代。
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from fractions import Fraction
import hashlib
import importlib.util
import json
import multiprocessing
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import uuid

import numpy as np

REPO = Path(__file__).resolve().parents[2]
SCHEMA = "official-rerender/1"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"不能加载模块：{path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def load_official(repo_root: Path):
    """直接执行锁定官方 utils 原文件；返回原类与原任务清单。"""
    path = Path(repo_root) / "third_party/mme-vla/examples/robomme/utils.py"
    mod = _load(path, "official_robomme_utils")
    return mod.RolloutRecorder, mod.TASK_WITH_VIDEO_DEMO


def f32_from_record(rec: dict) -> np.ndarray:
    """只有完整、有限的 8 维数值记录才能进入官方文字区。"""
    if not isinstance(rec, dict) or rec.get("shape") != [8]:
        raise ValueError("数组 shape 必须为 [8]")
    if np.dtype(rec.get("dtype", "O")).kind not in "fiub":
        raise ValueError("数组 dtype 必须为数值类型")
    raw = bytes.fromhex(rec["f32hex"])
    if len(raw) != 32:
        raise ValueError("f32hex 必须完整记录 8 个 float32")
    a = np.frombuffer(raw, dtype="<f4").copy()
    if not np.isfinite(a).all():
        raise ValueError("数组包含非有限值")
    if np.dtype(rec["dtype"]) == np.dtype("<f4") and hashlib.sha256(raw).hexdigest() != rec.get("sha256"):
        raise ValueError("float32 数组字节与 trace.sha256 不符")
    return a


@dataclass
class TraceData:
    identity: dict
    route: str
    task_goal: str
    demo_frames: int
    init_states: list[np.ndarray]
    init_subgoal: str | None
    steps: list[dict]
    terminal_reason: str
    end_status: str
    max_steps: int
    omitted_timeout_frames: int

    @property
    def source_frames(self) -> int:
        return len(self.init_states) + len(self.steps)

    @property
    def output_frames(self) -> int:
        return self.source_frames - self.omitted_timeout_frames


def load_trace(path: Path, arrays_path: Path | None = None) -> TraceData:
    """先核对序列与必需字段，再解码；demo.frames 包括初始帧。"""
    rows = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows or any(not isinstance(r, dict) for r in rows):
        raise ValueError("轨迹为空或行不是对象")
    if any(r.get("kind") not in ("header", "demo", "step", "request", "response", "history", "end") for r in rows):
        raise ValueError("轨迹包含未知行类型")
    writer = _load(REPO / "scripts/eval-official/trace_writer.py", "rerender_trace_writer")
    problems = writer.validate_trace(rows)
    if problems:
        raise ValueError("；".join(problems))
    header, end = rows[0], rows[-1]
    demo = next(r for r in rows if r["kind"] == "demo")
    identity = header["identity"]
    if not isinstance(identity, dict) or not all(identity.get(k) is not None for k in ("task", "tier", "seed", "dataset")):
        raise ValueError("轨迹身份缺少 task/tier/seed/dataset")
    route = header["route"]
    if not isinstance(route, str) or route.rsplit("/", 1)[-1] not in ("new", "orig"):
        raise ValueError("route 必须明确 new 或 orig")
    terminal = end["terminal_reason"]
    end_status = end.get("status")
    if (end_status not in ("success", "fail", "timeout") or
            terminal not in ("success", "fail", "timeout", "error") or
            (terminal != end_status and (terminal, end_status) != ("error", "timeout"))):
        raise ValueError("不支持非正常终态或终态冲突")
    frames, demo_frames = demo["frames"], end["demo_frames"]
    if type(frames) is not int or type(demo_frames) is not int or demo_frames < 0 or frames != demo_frames + 1:
        raise ValueError("demo.frames 必须等于 end.demo_frames + 1")
    if any(not isinstance(demo.get(k), list) or len(demo[k]) != frames for k in ("states", "front_sha256", "wrist_sha256")):
        raise ValueError("初始状态与画面哈希数量不完整")
    texts = demo.get("texts")
    if not isinstance(texts, list) or len(texts) != 1 or not isinstance(texts[0], str) or not texts[0].strip():
        raise ValueError("demo.texts 必须包含唯一非空任务目标")
    init = [f32_from_record(s) for s in demo["states"]]
    if any(np.dtype(s["dtype"]) != np.dtype("<f4") for s in demo["states"]):
        raise ValueError("初始状态非 float32，f32hex 不能证明完整原数组")
    steps = []
    arrays_path = arrays_path or Path(path).with_name("arrays.npz")
    arrays = np.load(arrays_path, allow_pickle=False) if arrays_path.exists() else None
    try:
        for st in (r for r in rows if r["kind"] == "step"):
            if type(st["step"]) is not int:
                raise ValueError("step 必须为整数")
            if not isinstance(st.get("subgoal"), (str, type(None))):
                raise ValueError("subgoal 必须为文本或 None")
            if not st.get("front_sha256") or not st.get("wrist_sha256"):
                raise ValueError("执行步没有完整画面，不能与视频配对")
            action_rec = st["action"]
            if np.dtype(st["state"]["dtype"]) != np.dtype("<f4"):
                raise ValueError("执行状态非 float32，f32hex 不能证明完整原数组")
            action = f32_from_record(action_rec)
            key = f"exec_action__{st['step'] - 1:05d}"
            if arrays is not None:
                action = arrays[key]
                if (list(action.shape) != action_rec["shape"] or action.dtype.str != action_rec["dtype"] or
                        hashlib.sha256(action.tobytes()).hexdigest() != action_rec["sha256"] or not np.isfinite(action).all()):
                    raise ValueError(f"原动作 {key} 与 trace dtype/shape/sha256 不符")
            elif np.dtype(action_rec["dtype"]) != np.dtype("<f4"):
                raise ValueError("缺少原动作 arrays.npz，拒绝以 f32hex 丢失原数组精度")
            steps.append({**st, "state": f32_from_record(st["state"]), "action": action})
    finally:
        if arrays is not None:
            arrays.close()
    max_steps = header["max_steps"]
    if type(max_steps) is not int or max_steps < 1:
        raise ValueError("max_steps 必须为正整数")
    if len(steps) > max_steps + 1 or (len(steps) > max_steps and end_status != "timeout"):
        raise ValueError("执行步超出官方上限且不是唯一超时末步")
    omitted = int(terminal == "timeout" and end_status == "timeout" and len(steps) == max_steps + 1)
    # 官方 eval_each_episode 在超过 max_steps 时先 break，最后一步不调用 record。
    subgoal = "[initializing...]" if any(st["subgoal"] is not None for st in steps) or "ground-sg" in route else None
    return TraceData(identity, route, texts[0], demo_frames, init, subgoal, steps, terminal, end_status, max_steps, omitted)


def feed_official_recorder(rec, front, wrist, trace: TraceData, task: str, video_demo_tasks=None,
                           max_output_bytes: int | None = None) -> None:
    """顺序与官方 init_episode / eval_each_episode 相同，所有绘图归原类。"""
    if len(front) != trace.source_frames or len(wrist) != trace.source_frames:
        raise ValueError(f"frame_count：输入 {len(front)}/{len(wrist)}，轨迹 {trace.source_frames}")
    front, wrist = np.asarray(front), np.asarray(wrist)
    if front.dtype != np.uint8 or wrist.dtype != np.uint8 or front.ndim != 4 or front.shape != wrist.shape or front.shape[-1] != 3:
        raise ValueError("front/wrist 必须为同尺寸的 N×H×W×3 uint8 数组")
    if video_demo_tasks is None:
        _, video_demo_tasks = load_official(REPO)
    n_init = len(trace.init_states)
    recorded_bytes = 0

    def record(**kwargs):
        nonlocal recorded_bytes
        rec.record(**kwargs)
        recorded_bytes += rec.total_images[-1].nbytes
        if max_output_bytes is not None and recorded_bytes > max_output_bytes:
            raise ValueError("官方文字区的实际帧内存超过本局预算")

    for i, state in enumerate(trace.init_states):
        record(image=front[i].copy(), wrist_image=wrist[i].copy(), state=state,
               is_video_demo=task in video_demo_tasks and i < n_init - 1, subgoal=trace.init_subgoal)
    for k, st in enumerate(trace.steps[:len(trace.steps) - trace.omitted_timeout_frames]):
        record(image=front[n_init + k].copy(), wrist_image=wrist[n_init + k].copy(),
               state=st["state"], action=st["action"], subgoal=st["subgoal"])


def fingerprint(path: Path) -> dict:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return {"sha256": h.hexdigest(), "size": Path(path).stat().st_size}


def probe_video(ffprobe: str, path: Path) -> dict:
    proc = subprocess.run([ffprobe, "-v", "error", "-select_streams", "v:0", "-count_frames",
                           "-show_entries", "stream=width,height,avg_frame_rate,nb_read_frames", "-of", "json", str(path)],
                          capture_output=True, text=True, check=True)
    streams = json.loads(proc.stdout)["streams"]
    if len(streams) != 1:
        raise ValueError("视频必须有唯一画面流")
    s = streams[0]
    return {"width": int(s["width"]), "height": int(s["height"]), "frames": int(s["nb_read_frames"]),
            "fps": str(Fraction(s["avg_frame_rate"]))}


def decode_mp4(ffmpeg: str, mp4: Path, info: dict | None = None):
    """流式读入预分配数组，避免整段 stdout 再复制一份数 GB 缓冲。"""
    info = info or probe_video(str(Path(ffmpeg).with_name("ffprobe")), mp4)
    if (info["width"], info["height"]) != (512, 256):
        raise ValueError("源视频必须为 512×256")
    images = np.empty((info["frames"], 256, 512, 3), dtype=np.uint8)
    with tempfile.TemporaryFile() as err:
        proc = subprocess.Popen([ffmpeg, "-v", "error", "-threads", "1", "-i", str(mp4), "-f", "rawvideo",
                                 "-pix_fmt", "rgb24", "-threads", "1", "pipe:1"], stdout=subprocess.PIPE, stderr=err)
        try:
            for arr in images:
                view = memoryview(arr).cast("B")
                offset = 0
                while offset < len(view):
                    n = proc.stdout.readinto(view[offset:])
                    if not n:
                        raise ValueError("解码帧提前结束")
                    offset += n
            if proc.stdout.read(1):
                raise ValueError("解码帧数超过 ffprobe")
            code = proc.wait()
            if code:
                err.seek(0)
                raise ValueError(f"ffmpeg 退出 {code}：{err.read().decode(errors='replace')}")
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
            proc.stdout.close()
    return images[:, :, :256], images[:, :, 256:]


def safe_filename(full_name: str) -> str:
    """完整官方语义写入 sidecar；文件系统不合法或超长时附固定摘要。"""
    sanitized = re.sub(r"[/\\\x00]", "_", full_name)
    if sanitized == full_name and len(sanitized.encode()) <= 255:
        return sanitized
    suffix = "__" + hashlib.sha256(full_name.encode()).hexdigest()[:16] + ".mp4"
    stem = sanitized.removesuffix(".mp4").encode()[:255 - len(suffix.encode())].decode(errors="ignore")
    return stem + suffix


def _episode_id(trace: TraceData, ep_dir: Path) -> str:
    identity = trace.identity
    if identity.get("key") and not re.fullmatch(re.escape(identity["key"]) + r"\.a[1-9]\d*", ep_dir.name):
        raise ValueError("局目录与 trace.identity.key 不符")
    if trace.route.endswith("/new"):
        if identity.get("source_episode") is None and identity.get("builder_episode") is None:
            raise ValueError("新侧身份没有 source_episode 或 builder_episode")
        mc = _load(REPO / "scripts/eval-official/mmesg_client.py", "rerender_mmesg_client")
        return mc.official_episode_id(identity, ep_dir.name)
    if identity.get("source_episode") is None:
        raise ValueError("原侧缺少 source_episode")
    return str(identity["source_episode"])


def _configure_threads(threads: int, cpus: list[int], worker_index: int) -> None:
    for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        os.environ[key] = str(threads)
    import cv2
    cv2.setNumThreads(threads)
    # imageio 的官方 save_video 不接受额外 ffmpeg 参数；子进程继承 CPU 亲和性限制编码线程。
    if hasattr(os, "sched_setaffinity"):
        start = worker_index * threads
        os.sched_setaffinity(0, set(cpus[start:start + threads]))


def _init_worker(threads: int, cpus: list[int], counter) -> None:
    """共享计数器分配唯一工作进程编号；每个进程只配置一次，不按 PID 碰撞。"""
    with counter.get_lock():
        index = counter.value
        counter.value += 1
    _configure_threads(threads, cpus, index)


def render_episode(ep_dir: Path, *, official_root: Path = REPO, ffmpeg: str = "/usr/bin/ffmpeg",
                   out_subdir: str = "official", prefix: str = "official-rerender__", overwrite: bool = False,
                   max_memory_mib: int = 6144) -> dict:
    """每局原子产出视频与身份清单；旧结果只有全链路指纹一致才复用。"""
    ep_dir, official_root = Path(ep_dir).resolve(), Path(official_root).resolve()
    if Path(out_subdir).name != out_subdir or out_subdir in ("", ".", "..") or any(c in prefix for c in "/\\\x00"):
        raise ValueError("输出子目录或前缀不安全")
    src, trace_path = ep_dir / "episode.mp4", ep_dir / "trace.jsonl"
    arrays_path = ep_dir / "arrays.npz"
    source_mp4, source_trace = fingerprint(src), fingerprint(trace_path)
    source_arrays = fingerprint(arrays_path) if arrays_path.exists() else None
    trace = load_trace(trace_path)
    episode_id = _episode_id(trace, ep_dir)
    out_dir = ep_dir / out_subdir
    if out_dir.is_symlink():
        raise ValueError("输出目录不能为符号链接")
    full_name = f"{prefix}{trace.identity['task']}_ep{episode_id}_{trace.terminal_reason}_{trace.task_goal}_{trace.identity['tier']}.mp4"
    safe_name = safe_filename(full_name)
    output, sidecar = out_dir / safe_name, out_dir / "render.json"
    if output.is_symlink() or sidecar.is_symlink():
        raise ValueError("输出视频与清单不能为符号链接")
    ffmpeg = str(Path(ffmpeg).resolve())
    ffprobe = str(Path(ffmpeg).with_name("ffprobe"))
    os.environ["IMAGEIO_FFMPEG_EXE"] = ffmpeg
    import cv2
    import imageio
    context = {"schema": SCHEMA, "identity": trace.identity, "episode_id": episode_id, "route": trace.route,
               "task_goal": trace.task_goal, "terminal_reason": trace.terminal_reason, "status": trace.end_status,
               "source_frames": trace.source_frames, "frames": trace.output_frames, "demo_frames": trace.demo_frames,
               "exec_steps": len(trace.steps), "recorded_exec_steps": len(trace.steps) - trace.omitted_timeout_frames,
               "omitted_timeout_frames": trace.omitted_timeout_frames, "full_name": full_name, "safe_name": safe_name,
               "out": str(output), "source_mp4": source_mp4, "source_trace": source_trace,
               "source_arrays": source_arrays,
               "tool": fingerprint(Path(__file__)),
               "official": fingerprint(official_root / "third_party/mme-vla/examples/robomme/utils.py"),
               "official_eval": fingerprint(official_root / "third_party/mme-vla/examples/robomme/eval.py"),
               "episode_id_helper": fingerprint(REPO / "scripts/eval-official/mmesg_client.py"),
               "trace_reader": fingerprint(REPO / "scripts/eval-official/trace_writer.py"), "ffmpeg": fingerprint(Path(ffmpeg)),
               "runtime": {"numpy": np.__version__, "opencv": cv2.__version__, "imageio": imageio.__version__}}
    if output.exists() or sidecar.exists():
        try:
            old = json.loads(sidecar.read_text()) if sidecar.is_file() else {}
        except (ValueError, OSError):
            old = {}
        if output.is_file() and all(old.get(k) == v for k, v in context.items()):
            actual = probe_video(ffprobe, output)
            if (actual["frames"] == trace.output_frames and actual["fps"] == "30" and
                    all(old.get(k) == v for k, v in actual.items()) and old.get("output_fingerprint") == fingerprint(output)):
                return {**old, "render_status": "reused", "dir": ep_dir.name}
        if not overwrite:
            raise ValueError("已有输出未通过 provenance 与完整视频验证；拒绝覆盖，请显式使用 --overwrite")
    info = probe_video(ffprobe, src)
    if info != {"width": 512, "height": 256, "frames": trace.source_frames, "fps": "30"}:
        raise ValueError(f"源视频帧数/帧率/尺寸不符：{info}；期望 frames={trace.source_frames} fps=30 size=512x256")
    Recorder, demo_tasks = load_official(official_root)
    out_dir.mkdir(exist_ok=True)
    rec = Recorder(out_dir, trace.task_goal, fps=30)
    # 先绘单帧估计官方版式高度，源解码 + 全部官方帧 + 编码余量一起计入预算。
    dummy = np.zeros((256, 256, 3), np.uint8)
    rec.record(dummy, dummy, trace.init_states[0], subgoal=trace.init_subgoal)
    frame_bytes = rec.total_images[0].nbytes
    estimated = int((trace.source_frames * 512 * 256 * 3 + trace.output_frames * frame_bytes) * 1.35 + 64 * 1024**2)
    rec.total_images.clear()
    if estimated > max_memory_mib * 1024**2:
        raise ValueError(f"预计内存 {estimated / 1024**2:.0f} MiB 超过上限 {max_memory_mib} MiB")
    front, wrist = decode_mp4(ffmpeg, src, info)
    output_budget = int((max_memory_mib * 1024**2 - 64 * 1024**2) / 1.35 - trace.source_frames * 512 * 256 * 3)
    feed_official_recorder(rec, front, wrist, trace, trace.identity["task"], demo_tasks, output_budget)
    del front, wrist
    if len(rec.total_images) != trace.output_frames or len({a.shape for a in rec.total_images}) != 1:
        raise ValueError("官方录像器帧数或逐帧尺寸不一致")
    temp = out_dir / f".render-{uuid.uuid4().hex}.mp4"
    try:
        rec.save_video(temp.name)
        actual = probe_video(ffprobe, temp)
        shape = rec.total_images[0].shape
        expected_size = ((shape[1] + 15) // 16 * 16, (shape[0] + 15) // 16 * 16)
        if actual["frames"] != trace.output_frames or actual["fps"] != "30" or (actual["width"], actual["height"]) != expected_size:
            raise ValueError(f"输出完整性不符：{actual}")
        if (fingerprint(src) != context["source_mp4"] or fingerprint(trace_path) != context["source_trace"] or
                (fingerprint(arrays_path) if arrays_path.exists() else None) != context["source_arrays"]):
            raise ValueError("源文件在重绘期间发生变化")
        result = {**context, **actual, "dir": ep_dir.name, "render_status": "rendered", "estimated_memory_mib": round(estimated / 1024**2),
                  "output_fingerprint": fingerprint(temp), "input_array_precision": "verified-original"}
        os.replace(temp, output)
        side_temp = out_dir / f".render-{uuid.uuid4().hex}.json"
        side_temp.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(side_temp, sidecar)
        return result
    finally:
        temp.unlink(missing_ok=True)


def _worker(ep_dir: str, opts: dict) -> dict:
    try:
        return {"ok": True, **render_episode(Path(ep_dir), **opts)}
    except Exception as exc:
        return {"ok": False, "dir": Path(ep_dir).name, "reason": f"{type(exc).__name__}: {exc}"}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("episodes", nargs="*", type=Path)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--label", default="mmesg-ground-sg-oracle")
    parser.add_argument("--official-root", type=Path, default=REPO)
    parser.add_argument("--ffmpeg", default=shutil.which("ffmpeg") or "/usr/bin/ffmpeg")
    parser.add_argument("--out-subdir", default="official")
    parser.add_argument("--prefix", default="official-rerender__")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--max-memory-mib", type=int, default=6144)
    args = parser.parse_args(argv)
    if args.jobs < 1 or args.threads < 1 or args.max_memory_mib < 128 or bool(args.root) == bool(args.episodes):
        parser.error("必须选择局目录或 --root，且资源参数必须为正数")
    if args.root:
        root = args.root.resolve()
        dirs = sorted(p.parent for p in root.rglob("trace.jsonl")
                      if args.label in p.parts and not any(part.startswith(".") for part in p.relative_to(root).parts))
    else:
        dirs = [p.resolve() for p in args.episodes]
    if not dirs or len(set(dirs)) != len(dirs):
        parser.error("没有局目录或包含重复目录")
    opts = {k: getattr(args, k) for k in ("official_root", "ffmpeg", "out_subdir", "prefix", "overwrite", "max_memory_mib")}
    available = next((int(line.split()[1]) * 1024 for line in Path("/proc/meminfo").read_text().splitlines()
                      if line.startswith("MemAvailable:")), args.max_memory_mib * 1024**2)
    cpus = sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else list(range(os.cpu_count() or 1))
    if args.threads > len(cpus):
        parser.error("--threads 超过可用 CPU 数")
    jobs = min(args.jobs, len(dirs), max(1, int(available * 0.6) // (args.max_memory_mib * 1024**2)), len(cpus) // args.threads)
    print(f"OFFICIAL_RENDER_RESOURCES jobs={jobs} requested_jobs={args.jobs} threads={args.threads} max_memory_mib={args.max_memory_mib}", flush=True)
    ok = fail = reused = 0
    counter = multiprocessing.Value("i", 0)
    with ProcessPoolExecutor(max_workers=jobs, initializer=_init_worker, initargs=(args.threads, cpus, counter)) as pool:
        futures = {pool.submit(_worker, str(p), dict(opts)): p for p in dirs}
        for f in as_completed(futures):
            try:
                result = f.result()
            except Exception as exc:
                result = {"ok": False, "dir": futures[f].name, "reason": f"{type(exc).__name__}: {exc}"}
            if result["ok"]:
                ok += 1
                reused += result["render_status"] == "reused"
                print(f"OFFICIAL_RENDER=PASS dir={result['dir']} frames={result['frames']} demo={result['demo_frames']} steps={result['exec_steps']} omitted={result['omitted_timeout_frames']} size={result['width']}x{result['height']} status={result['render_status']} terminal_reason={result['terminal_reason']} end_status={result['status']} out={json.dumps(result['out'])}", flush=True)
            else:
                fail += 1
                print(f"OFFICIAL_RENDER=FAIL dir={result['dir']} reason={json.dumps(result['reason'], ensure_ascii=False)}", flush=True)
    print(f"OFFICIAL_RENDER_SUMMARY={'PASS' if fail == 0 else 'FAIL'} total={len(dirs)} ok={ok} fail={fail} reused={reused}", flush=True)
    return int(fail > 0)


if __name__ == "__main__":
    raise SystemExit(main())
