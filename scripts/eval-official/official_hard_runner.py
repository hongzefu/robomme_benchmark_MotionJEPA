#!/usr/bin/env python3
"""GroundSG 原侧（官方循环 + 官方 builder）驱动（1003-oracle-subgoal-groundsg-eval-plan.md 第二部分 1.3、1.7；子任务 S3）。

独立进程，解释器用客户端扩展环境（client-env）。官方 ``eval.py`` 经 ``subgoal_predictor.py`` 无条件导入 gemini
（``google.generativeai``）与 memer，所以**不整模块 import** 官方文件：与新侧一样用
``official_defs.extract_defs`` 摘取 ``EpisodeEvaluator``、``Args``、``EnvRunner`` 与所选变体的预测器原文。
``sys.path`` 只加官方 ``examples/robomme`` 与本仓库 ``src``（本目录模块按文件路径加载、不进 ``sys.path``）；启动时
断言 ``robomme.__file__`` 在本仓库 ``src/robomme/`` 下、``"robomme_hard" not in sys.modules``，每局结束再查一次。

流程：对 hard0 分片（``eval_manifest.py --mode hard0`` 产出的 ``shard-NN.json``）的每一行，官方
``EnvRunner(task, video_dir, max_steps=--max-steps)``（每任务一个，与官方 ``evaluate`` 相同）→
``make_env(source_episode)`` → ``EpisodeEvaluator.eval_each_episode`` → ``close_env``。预测器与评估器整个进程只建
一次（与官方相同，QwenVL 模型只加载一次）。

外围记录全部是委托包装，不改 ``src/robomme`` 的任何方法、不 monkeypatch：

* ``TapRunner`` 包住官方 ``EnvRunner`` 实例的 ``get_init_obs``／``step``（其余属性原样转发）；
* ``EnvTap`` 包住 ``EnvRunner.env`` 这个对象：``step`` 原样转发并记下 ``terminated``／``truncated``，其余属性转发；
* 客户端经 ``eval.py`` 的 ``_websocket_client_policy`` 名字注入 ``mmesg_client.TracingClient``（包住真实
  ``MMEVLAWebsocketClientPolicy``）。

每局目录 ``<out>/<key>.a<attempt>/``（已存在即报错，分片开跑前统一检查）::

    trace.jsonl                 # trace_writer，route mmesg/<variant>/orig；字段与新侧同一套代码写出
    frames/front.rgb24          # 逐帧 H×W×3 uint8 原始字节顺序拼接（ffmpeg rawvideo rgb24）
    frames/wrist.rgb24
    frames/frames.json          # {"pix_fmt":"rgb24","streams":{"front":{"width","height","count"},"wrist":{…}},
                                #  "demo_frames","init_frames","exec_steps","missing_steps","order"}
    ep<source_episode>_QwenVL_log.jsonl   # 仅 QwenVL 变体：官方 Qwen 请求日志（局末从临时目录归档）

帧顺序：``get_init_obs`` 返回的全部帧（``demo_frames`` 个演示帧 + 1 个初始帧），之后每执行一步追加该步观测；某步
环境抛异常（官方 ``EnvRunner.step`` 返回 None 三元组）时不追加、步号记入 ``missing_steps``。
``count = demo_frames + 1 + exec_steps - len(missing_steps)``。官方循环 ``count > max_steps`` 才判超时，所以超时局
执行第 ``max_steps+1`` 步，外围帧含这一步（xhard0：1300 → 执行 1301 步、``count = demo_frames + 1302``）；官方
循环自己写的叠字 mp4 只录到第 ``max_steps`` 步，局末删除、不交付。Qwen 临时目录在每局目录下的
``qwen-tmp/test-hard0/<key>.a<attempt>/``，局末删除。

结果行（``<out>/results.jsonl``，每局一行，追加并 fsync）：分片行的身份字段 + ``side="orig"``、``policy="mmesg"``、
``policy_variant``、``dataset="test-hard0"``、``attempt``、``status``、``task_success``、``exec_steps``、``steps``、
``demo_frames``、``max_steps``、``effective_max_steps``、``success_flag``、``decisions``、``error``、``infra``、
``infra_reason``、``ep_dir``、``trace_path``、``frames_dir``、``video_frames``（``{"front":n,"wrist":n}``）、
``wall_s``、``official_sha256``。官方 ``unknown`` 记 ``status="error"``、``error="success_flag=unknown"``，**不中止**
（官方 ``evaluate`` 在此中止整个评估；这里只记该局，属记录在案的偏离）。

用法::

    python official_hard_runner.py --shard <shard-NN.json> --out <目录> --port <端口> \\
        --variant {ground-sg-oracle,ground-sg-qwenvl} [--qwenvl-groundsg-adapter <路径>] \\
        [--host 127.0.0.1] [--max-steps 1300] [--attempt 1] [--only <key,…>] [--no-frames]
    python official_hard_runner.py --check-imports [--variant …]   # 只做导入断言，打印 OFFICIAL_IMPORTS=PASS …

退出码：0 分片跑完（含 error 局）；2 服务不可达中止；3 参数、分片或导入断言不合格。
"""
from __future__ import annotations

import sys
from pathlib import Path as _Path

_HERE = str(_Path(__file__).resolve().parent)
# 本目录不进 sys.path（同目录模块一律按文件路径加载）
sys.path[:] = [p for p in sys.path if p and str(_Path(p).resolve()) != _HERE]

import argparse  # noqa: E402
import importlib.util  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import socket  # noqa: E402
import time  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Any, Callable  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
SIDE = "orig"
POLICY = "mmesg"
DATASET = "test-hard0"
XHARD0 = "xhard0"
MAX_STEPS = 1300
EXIT_UNREACHABLE = 2
EXIT_BAD_INPUT = 3
#: 服务可达探测：每局建客户端前 TCP 探测，累计等这么久仍连不上即判「服务不可达」（官方客户端自己会无限重试）
PROBE_TIMEOUT_S = 300.0


def _load(name: str):
    """按文件路径加载本目录模块（别名与 env_client.load_sibling 相同）。"""
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, Path(_HERE) / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


official_defs = _load("official_defs")
mmesg = _load("mmesg_client")
trace_writer = _load("trace_writer")


class ServerUnreachable(ConnectionError):
    """模型服务在 ``PROBE_TIMEOUT_S`` 内连不上：本局记 error 并停止整个分片（退出码 2）。"""


def dumps(obj: Any) -> str:
    def default(o):
        try:
            import numpy as np

            if isinstance(o, np.generic):
                return o.item()
        except ImportError:
            pass
        return str(o)

    return json.dumps(obj, sort_keys=True, ensure_ascii=False, default=default)


# ── 启动：路径与导入断言 ────────────────────────────────────────────────────


def setup_paths() -> list[str]:
    """``sys.path`` 只加官方 ``examples/robomme`` 与本仓库 ``src``（放最前）。返回加入的两项。"""
    added = [str(official_defs.official_robomme_dir()), str(REPO / "src")]
    for p in reversed(added):
        while p in sys.path:
            sys.path.remove(p)
        sys.path.insert(0, p)
    return added


def assert_no_robomme_hard() -> None:
    bad = sorted(m for m in sys.modules if m == "robomme_hard" or m.startswith("robomme_hard."))
    if bad:
        raise AssertionError(f"原侧进程导入了 robomme_hard：{bad[:5]}")


def import_official_env() -> dict:
    """照官方 ``env_runner.py`` 头部导入环境注册与 builder，并断言来源：``robomme`` 在本仓库 ``src/robomme/``，
    ``robomme_hard`` 未被导入。返回 ``{"BenchmarkEnvBuilder", "robomme_file"}``。"""
    import robomme

    want = (REPO / "src" / "robomme").resolve()
    got = Path(robomme.__file__).resolve()
    if want not in got.parents:
        raise AssertionError(f"robomme 不在仓库 src/robomme 下：{got}")
    import robomme.robomme_env  # noqa: F401 环境注册（官方 from robomme.robomme_env import *）
    from robomme.env_record_wrapper import BenchmarkEnvBuilder

    assert_no_robomme_hard()
    return {"BenchmarkEnvBuilder": BenchmarkEnvBuilder, "robomme_file": str(got)}


# ── 分片 ───────────────────────────────────────────────────────────────────


def load_shard(path: Path, only: str | None = None) -> list[dict]:
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"分片应为非空 JSON 数组：{path}")
    keys = set()
    for i, r in enumerate(rows):
        for k in ("task", "tier", "seed", "source_episode", "key"):
            if k not in r:
                raise ValueError(f"分片第 {i} 行缺 {k}")
        if r["tier"] != XHARD0:
            raise ValueError(f"分片第 {i} 行 tier={r['tier']!r}，原侧只跑 {XHARD0}")
        if not isinstance(r["source_episode"], int) or isinstance(r["source_episode"], bool):
            raise ValueError(f"分片第 {i} 行 source_episode={r['source_episode']!r} 须为整数")
        if r["key"] in keys:
            raise ValueError(f"分片 key 重复：{r['key']}")
        keys.add(r["key"])
    if only:
        want = set(only.split(","))
        rows = [r for r in rows if r["key"] in want]
    return rows


# ── 委托包装 ────────────────────────────────────────────────────────────────


class EnvTap:
    """包住 ``EnvRunner.env`` 对象：``step`` 原样转发并记下 ``terminated``／``truncated``；其余属性转发。"""

    def __init__(self, env: Any):
        object.__setattr__(self, "_env", env)
        object.__setattr__(self, "last", None)

    def step(self, action):
        object.__setattr__(self, "last", None)
        out = self._env.step(action)
        object.__setattr__(self, "last", (out[2], out[3]))
        return out

    def __getattr__(self, name):
        return getattr(self._env, name)


class TapRunner:
    """包住官方 ``EnvRunner`` 实例：``get_init_obs``／``step`` 先调官方原方法再把结果交给 ``EpisodeTap``；其余属性
    （``env_id``、``episode_id``、``task_goal``、``difficulty``、``info``、两个 oracle 属性）原样转发。"""

    def __init__(self, inner: Any, tap: Any):
        object.__setattr__(self, "_inner", inner)
        object.__setattr__(self, "_tap", tap)

    def get_init_obs(self):
        pre = self._inner.get_init_obs()
        self._tap.on_reset(pre)
        return pre

    def step(self, action):
        env = self._inner.env
        out = self._inner.step(action)
        obs3, stop, flag = out
        tt = env.last if isinstance(env, EnvTap) else None
        term, trunc = tt if tt is not None else (None, None)
        self._tap.on_step(action, obs3, stop, flag, term, trunc)
        return out

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def __setattr__(self, name, value):
        setattr(self._inner, name, value)


# ── 驱动 ────────────────────────────────────────────────────────────────────


def probe_server(host: str, port: int, timeout_s: float | None = None) -> None:
    """TCP 探测模型服务；``timeout_s``（默认取模块常量 ``PROBE_TIMEOUT_S``）内连不上抛 ``ServerUnreachable``。"""
    timeout_s = PROBE_TIMEOUT_S if timeout_s is None else float(timeout_s)
    t_end = time.monotonic() + timeout_s
    while True:
        try:
            with socket.create_connection((host, int(port)), timeout=5):
                return
        except OSError as e:
            if time.monotonic() >= t_end:
                raise ServerUnreachable(f"{host}:{port} 在 {timeout_s:.0f}s 内连不上：{e}") from e
            time.sleep(min(2.0, max(0.05, t_end - time.monotonic())))


def default_client_factory(host: str, port: int, episode: dict) -> Any:
    """原侧默认：先探测可达，再建真实 ``openpi_client`` 的 ``MMEVLAWebsocketClientPolicy``（与官方相同，不加记录）。"""
    probe_server(host, port)
    from openpi_client import websocket_client_policy

    return websocket_client_policy.MMEVLAWebsocketClientPolicy(host, port)


def make_context(variant: str, *, host: str, port: int, max_steps: int, adapter: str | None,
                 builder_cls: Any, scratch_root: Path, client_factory: Callable | None = None,
                 qwen_extra: dict | None = None) -> dict:
    """进程内只建一次：官方定义（含 ``EnvRunner``）、``Args``、预测器（QwenVL 在此加载模型）、评估器。"""
    ctx: dict[str, Any] = {"variant": variant, "episode": None,
                           "client_factory": client_factory or default_client_factory}

    def ws_factory(h, p):
        ep = ctx["episode"]
        client = mmesg.TracingClient(ctx["client_factory"](h, p, ep), ep["tap"])
        ep["clients"].append(client)
        return client

    defs = official_defs.load_groundsg(variant, with_env_runner=True,
                                       env_runner_extra={"BenchmarkEnvBuilder": builder_cls},
                                       ws_module=official_defs.ws_shim(ws_factory), qwen_extra=qwen_extra)
    base = Path(scratch_root) / "qwen-tmp"
    args = official_defs.make_args(defs, variant=variant, host=host, port=port, max_steps=max_steps,
                                   adapter_path=adapter, save_dir=str(base))
    predictor = official_defs.build_predictor(defs, args, base)
    ctx.update(defs=defs, args=args, predictor=predictor, evaluator=defs["EpisodeEvaluator"](args, base),
               official_sha256=dict(defs["sha256"]), runners={})
    return ctx


def runner_for(ctx: dict, task: str, video_dir: Path) -> Any:
    """每任务一个官方 ``EnvRunner``（与官方 ``evaluate`` 相同，builder 建一次跨局复用）。"""
    if task not in ctx["runners"]:
        ctx["runners"][task] = ctx["defs"]["EnvRunner"](task, video_dir, max_steps=ctx["args"].max_steps)
    return ctx["runners"][task]


def ep_dir_of(out: Path, row: dict, attempt: int) -> Path:
    return Path(out) / f"{row['key']}.a{int(attempt)}"


def run_identity(ctx: dict, row: dict, *, out: Path, attempt: int = 1, write_frames: bool = True) -> dict:
    """跑一个 hard0 身份，返回结果行（不写 results.jsonl）。每局目录已存在即抛 ``FileExistsError``。"""
    variant = ctx["variant"]
    max_steps = int(ctx["args"].max_steps)
    tag = f"{row['key']}.a{int(attempt)}"
    ep_dir = ep_dir_of(out, row, attempt)
    ep_dir.mkdir(parents=True, exist_ok=False)
    tpath = ep_dir / "trace.jsonl"
    tid = {k: row.get(k) for k in ("task", "tier", "seed", "source_episode", "builder_episode", "key")}
    tid["dataset"] = DATASET
    trace = trace_writer.TraceWriter(tpath, route=f"mmesg/{variant}/orig", identity=tid, max_steps=max_steps)
    frames = mmesg.RawFrameWriter(ep_dir / "frames") if write_frames else None
    tap = mmesg.EpisodeTap(trace, frames)
    video_dir = ep_dir / "official-video"
    t0 = time.perf_counter()
    runner = None
    difficulty = None
    try:
        runner = runner_for(ctx, row["task"], video_dir)
        runner.video_save_dir = video_dir
        runner.make_env(int(row["source_episode"]))
        difficulty = getattr(runner, "difficulty", None)
        runner.env = EnvTap(runner.env)
        res = mmesg.run_official_episode(ctx, TapRunner(runner, tap), tap, dataset=DATASET, episode_tag=tag,
                                         scratch=ep_dir, archive_dir=ep_dir)
    except Exception as e:  # noqa: BLE001 官方 EnvRunner 构建／make_env 失败（官方 evaluate 同样整局记 error）
        err = f"{type(e).__name__}: {e}"[:800]
        infra = mmesg.classify_infra(err)
        res = {"status": "error", "task_success": False, "steps": tap.steps, "error": err, "success_flag": "error",
               "decisions": tap.decisions, "infra": True, "infra_reason": infra or "env_build",
               "env_exception": None, "exception": type(e).__name__, "qwen_log": None, "timing": {}}
    finally:
        if runner is not None and getattr(runner, "env", None) is not None:
            try:
                runner.close_env()
            except Exception as e:  # noqa: BLE001
                print(f"close_env error: {e!r}", flush=True)
    if res.get("exception") == "ServerUnreachable":
        res.update(infra=True, infra_reason="mmesg_unreachable")
    shutil.rmtree(video_dir, ignore_errors=True)
    wall = time.perf_counter() - t0
    trace.close(status=res["status"], terminal_reason=res.get("success_flag"), side=SIDE, demo_frames=tap.demo_frames,
                decisions=res.get("decisions"))
    fsum = frames.close() if frames is not None else None
    out_row = dict(row)
    out_row.update(res)
    out_row.update(side=SIDE, policy=POLICY, policy_variant=variant, dataset=DATASET, attempt=int(attempt),
                   attempt_no=int(attempt), task_success=res["status"] == "success", exec_steps=tap.steps,
                   steps=tap.steps, demo_frames=tap.demo_frames, max_steps=max_steps, effective_max_steps=max_steps,
                   difficulty=difficulty, ep_dir=str(ep_dir), trace_path=str(tpath),
                   frames_dir=None if frames is None else str(frames.dir),
                   video_frames=None if fsum is None else {s: v["count"] for s, v in fsum["streams"].items()},
                   wall_s=round(wall, 3), host=socket.gethostname())
    return out_row


def append_result(path: Path, row: dict) -> None:
    with Path(path).open("a", encoding="utf-8") as fh:
        fh.write(dumps(row) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def run_shard(ctx: dict, rows: list[dict], *, out: Path, attempt: int = 1, write_frames: bool = True,
              import_check: Callable[[], Any] | None = None) -> dict:
    """逐身份跑；返回 ``{"episodes","errors","aborted",<各终态计数>}``。服务不可达即停止（aborted）。"""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    results = out / "results.jsonl"
    summary = {"episodes": 0, "errors": 0, "aborted": False, "success": 0, "fail": 0, "timeout": 0}
    for row in rows:
        rec = run_identity(ctx, row, out=out, attempt=attempt, write_frames=write_frames)
        append_result(results, rec)
        summary["episodes"] += 1
        summary["errors"] += int(rec["status"] == "error")
        if rec["status"] in ("success", "fail", "timeout"):
            summary[rec["status"]] += 1
        print(f"EPISODE_DONE side={SIDE} policy={POLICY} variant={ctx['variant']} dataset={DATASET} key={rec['key']} "
              f"status={rec['status']} exec_steps={rec['exec_steps']} demo_frames={rec['demo_frames']} "
              f"video_frames={(rec['video_frames'] or {}).get('front')} infra={rec['infra']} wall_s={rec['wall_s']:.1f}",
              flush=True)
        if import_check is not None:
            import_check()
        if rec.get("exception") == "ServerUnreachable":
            summary["aborted"] = True
            break
    return summary


def cmd_check_imports(args) -> int:
    """只做导入断言：路径、``robomme`` 来源、所选（默认两个）变体的官方定义可摘取；不建环境、不连服务、不加载模型。"""
    added = setup_paths()
    info = import_official_env()
    variants = [args.variant] if args.variant else list(official_defs.VARIANTS)
    for v in variants:
        defs = official_defs.load_groundsg(v, with_env_runner=True,
                                           env_runner_extra={"BenchmarkEnvBuilder": info["BenchmarkEnvBuilder"]},
                                           ws_module=official_defs.ws_shim(lambda h, p: None))
        names = sorted(k for k in defs["predictor"] if k.endswith("Predictor"))
        print(f"OFFICIAL_DEFS variant={v} predictors={','.join(names)} "
              + " ".join(f"{k}={s}" for k, s in sorted(defs["sha256"].items())), flush=True)
    assert_no_robomme_hard()
    leaked = sorted(m for m in ("subgoal_predictor", "eval", "env_runner", "utils", "google.generativeai", "swift",
                                "subgoal_prediction") if m in sys.modules)
    if leaked:
        raise AssertionError(f"官方模块被整模块导入：{leaked}")
    print(f"OFFICIAL_IMPORTS=PASS robomme={info['robomme_file']} robomme_hard_imported=0 "
          f"official_modules_imported=0 variants={len(variants)} sys_path_added={','.join(added)}", flush=True)
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="GroundSG 原侧驱动（官方循环 + 官方 builder 跑 hard0 分片）")
    ap.add_argument("--check-imports", action="store_true", help="只做导入断言")
    ap.add_argument("--shard", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int)
    ap.add_argument("--max-steps", type=int, default=MAX_STEPS)
    ap.add_argument("--attempt", type=int, default=1)
    ap.add_argument("--only", default=None, help="逗号分隔的 key，只跑这些")
    ap.add_argument("--no-frames", action="store_true", help="不写原始帧")
    ap.add_argument("--variant", choices=list(official_defs.VARIANTS))
    ap.add_argument("--qwenvl-groundsg-adapter", default=None, help="ground-sg-qwenvl 必填")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.check_imports:
            return cmd_check_imports(args)
        added = setup_paths()
        info = import_official_env()
    except (AssertionError, FileNotFoundError, KeyError) as e:
        print(f"OFFICIAL_IMPORTS=FAIL reason={e}", flush=True)
        return EXIT_BAD_INPUT
    miss = [n for n, v in (("--shard", args.shard), ("--out", args.out), ("--port", args.port),
                           ("--variant", args.variant)) if v is None]
    if miss:
        print(f"MMESG_ORIG_BLOCKED reason=args missing={' '.join(miss)}", flush=True)
        return EXIT_BAD_INPUT
    if (args.variant == official_defs.VARIANT_QWENVL) != bool(args.qwenvl_groundsg_adapter):
        print("MMESG_ORIG_BLOCKED reason=args --qwenvl-groundsg-adapter 仅且必须与 ground-sg-qwenvl 同用", flush=True)
        return EXIT_BAD_INPUT
    try:
        rows = load_shard(args.shard, args.only)
    except (ValueError, OSError) as e:
        print(f"MMESG_ORIG_BLOCKED reason=shard detail={e}", flush=True)
        return EXIT_BAD_INPUT
    exists = [str(ep_dir_of(args.out, r, args.attempt)) for r in rows if ep_dir_of(args.out, r, args.attempt).exists()]
    if exists:
        print(f"MMESG_ORIG_BLOCKED reason=ep_dir_exists n={len(exists)} first={exists[0]}", flush=True)
        return EXIT_BAD_INPUT
    args.out.mkdir(parents=True, exist_ok=True)
    ctx = make_context(args.variant, host=args.host, port=args.port, max_steps=args.max_steps,
                       adapter=args.qwenvl_groundsg_adapter, builder_cls=info["BenchmarkEnvBuilder"],
                       scratch_root=args.out)
    url = f"ws://{args.host}:{args.port}"
    print(f"MMESG_ORIG_START shard={args.shard} variant={args.variant} episodes={len(rows)} url={url} "
          f"max_steps={args.max_steps} robomme={info['robomme_file']} sys_path_added={','.join(added)} "
          + " ".join(f"{k}={s}" for k, s in sorted(ctx["official_sha256"].items())), flush=True)
    summary = run_shard(ctx, rows, out=args.out, attempt=args.attempt, write_frames=not args.no_frames,
                        import_check=assert_no_robomme_hard)
    print(f"MMESG_ORIG_DONE shard={args.shard} variant={args.variant} episodes={summary['episodes']} "
          f"errors={summary['errors']} success={summary['success']} fail={summary['fail']} "
          f"timeout={summary['timeout']} aborted={int(summary['aborted'])}", flush=True)
    return EXIT_UNREACHABLE if summary["aborted"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
