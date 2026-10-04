"""Astra 新侧驱动：把 Astra-on-RoboMME 的单局循环 ``runner.episode`` 接到本仓库的 ``BenchmarkEnvBuilder`` 上。

计划：``1003-oracle-subgoal-groundsg-eval-plan.md`` 第二部分 1.5（S5）。原侧是原样运行 Astra 的
``examples/champ/run.sh``；本文件是新侧，不改 Astra 任何源码，只做三件事：

1. ``sys.path`` 加 Astra 的 ``examples/champ`` 与本仓库 ``src``，``import robomme_hard.robomme_env``，
   以 ``BenchmarkEnvBuilder(task, dataset=<test-hard0|test-hard>, action_space="joint_angle",
   gui_render=False, max_steps=<启动命令给的值>)`` 建环境；
2. 构造 Astra 的 ``Monitor``、``Planner``、``ResponsesClient`` 与 websocket 客户端后，直接调用
   ``runner.episode(...)``（不经它的 ``main()``：其中按 ``metadata_index`` 取 50 局的断言对本仓库 builder 不成立）；
3. 逐项复刻 ``main()`` 的六项行为（见 ``run_cases`` 文档串），并在环境、VLA、规划、监视四处以委托方式
   调用 ``trace_writer`` 记每局 ``trace.jsonl``。

输出目录与原侧相同：``<根>/group_<0|1>/<RUN>/{results,planner_calls}``；``results/<task>/ep<NNN>/`` 下是
Astra 自己写的 ``identity.json``、``decisions.jsonl``、``actions.npy``、``result.json``、``rollout.mp4``、
``monitor_inputs/``，本驱动只在同一目录多写一份 ``trace.jsonl``。``group_*`` 这一层必须保留：
``main()`` 每局前查 ``<output>/../../STOP.json``，``ResponsesClient._send`` 每次发送前查路径上名为
``group_0``／``group_1`` 的目录里的 ``STOP.json``——费用守卫 ``astra_cost_guard.py`` 就往那里写。

子命令：

- ``prepare``：生成新侧的局清单（``{"dataset", "cases": [{task, episode, tier, seed[, source_episode]}]}``），
  ``episode`` 是本仓库 builder 的本地局号；身份字段取自 builder，供 ``run`` 起跑前逐局核对。
- ``check``：不加载模型、不联网：核对局清单与身份、数据集与步数的配对、``validate_checkpoints``、端口可绑定，
  并打印 ``robomme_hard.__file__``、``robomme.__file__``。``run_astra.sh`` 在起 VLA 前调用。
- ``run``：正式运行（``run_astra.sh`` 调用）。
- ``summarize``：汇总 ``results`` 为 ``summary.json``（Astra 自带的 ``summarize.py`` 只认 test／val）。

密钥只从环境变量 ``OPENAI_API_KEY`` 读，交给 ``ResponsesClient``；本文件不读密钥文件、不打印密钥。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
REPO_SRC = REPO_ROOT / "src"

#: 新侧只接受这两个数据集；与启动命令的 ``--max-steps`` 做配对一致性检查（不是按档查表，数值由启动命令给）
DATASET_STEP_PAIRING = {"test-hard0": 1300, "test-hard": 1600}
#: ``main()`` 第⑤项：错误信息以这三个前缀开头的局，单次即停整个分片
PLANNER_STOP_PREFIXES = ("Planner API", "Pilot planner-call", "Planner bridge failed")
#: ``main()`` 第④项：非规划类 error 连续累计到此数即停
INFRA_ERROR_LIMIT = 3
#: ``ResponsesClient._send`` 只认这两个目录名下的 STOP.json
GROUP_DIR_NAMES = ("group_0", "group_1")
#: 启动时打印 sha256 的 Astra 源文件（留档用）
ASTRA_SOURCE_FILES = ("runner.py", "core.py", "api_client.py", "input_contract.py", "release_utils.py",
                      "train_entry.py", "weights.json")


class AstraStop(RuntimeError):
    """``main()`` 里那几处 ``raise RuntimeError`` 的同义异常；``reason`` 供测试与日志判读。"""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


# ── 路径与上游模块 ─────────────────────────────────────────────────────────

def astra_root(explicit: str | None = None) -> Path:
    """Astra 子模块根：命令行 > ``SGEVAL_THIRD_PARTY``（worktree 测试只读引用主检出）> 本仓库 ``third_party``。"""
    if explicit:
        return Path(explicit).resolve()
    third = os.environ.get("SGEVAL_THIRD_PARTY")
    base = Path(third) if third else REPO_ROOT / "third_party"
    return (base / "Astra-on-RoboMME").resolve()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def bootstrap(root: Path) -> SimpleNamespace:
    """``sys.path`` 加 Astra ``examples/champ`` 与本仓库 ``src``，导入 Astra 的四个模块并返回。"""
    champ = root / "examples" / "champ"
    if not (champ / "runner.py").is_file():
        raise FileNotFoundError(f"找不到 Astra 源码 {champ}/runner.py（子模块未初始化？）")
    for entry in (str(REPO_SRC), str(champ), str(HERE)):
        if entry in sys.path:
            sys.path.remove(entry)
        sys.path.insert(0, entry)
    import api_client  # noqa: PLC0415  Astra 的直连 Responses API 客户端
    import core  # noqa: PLC0415
    import release_utils  # noqa: PLC0415
    import runner as astra_runner  # noqa: PLC0415  Astra 的单局循环（模块级 episode 函数）
    return SimpleNamespace(root=root, champ=champ, runner=astra_runner, core=core,
                           release_utils=release_utils, api_client=api_client)


def source_digests(champ: Path) -> dict[str, str]:
    return {name: file_sha256(champ / name) for name in ASTRA_SOURCE_FILES if (champ / name).is_file()}


def assert_env_sources() -> dict[str, str]:
    """环境源必须是本仓库 ``src``：``robomme`` 与 ``robomme_hard`` 都不得来自 Astra 嵌套的官方副本。"""
    import robomme  # noqa: PLC0415
    import robomme_hard  # noqa: PLC0415
    files = {"robomme_hard": str(Path(robomme_hard.__file__).resolve()),
             "robomme": str(Path(robomme.__file__).resolve())}
    for name, path in files.items():
        if not path.startswith(str(REPO_SRC.resolve()) + os.sep):
            raise RuntimeError(f"{name} 不是来自本仓库 src：{path}")
    print(f"ASTRA_ENV_SOURCE robomme_hard={files['robomme_hard']} robomme={files['robomme']}", flush=True)
    return files


def default_builder_cls():
    import robomme_hard.robomme_env  # noqa: F401,PLC0415  注册环境（与官方 main() 的 import robomme.robomme_env 对应）
    from robomme_hard.env_record_wrapper import BenchmarkEnvBuilder  # noqa: PLC0415
    return BenchmarkEnvBuilder


def make_builder(builder_cls, task: str, dataset: str, max_steps: int):
    return builder_cls(task, dataset=dataset, action_space="joint_angle", gui_render=False, max_steps=max_steps)


# ── 局清单 ────────────────────────────────────────────────────────────────

def check_pairing(dataset: str, max_steps: int) -> None:
    expected = DATASET_STEP_PAIRING.get(dataset)
    if expected is None:
        raise ValueError(f"RUN_BLOCKED reason=dataset dataset={dataset!r}（只接受 {sorted(DATASET_STEP_PAIRING)}）")
    if int(max_steps) != expected:
        raise ValueError(f"RUN_BLOCKED reason=step_cap_pairing dataset={dataset} max_steps={max_steps}（应为 {expected}）")


def validate_cases(document: dict, tasks: list[str]) -> list[dict]:
    """新侧局清单：``dataset`` 为 test-hard0／test-hard；``episode`` 为本地局号；身份字段必备以供逐局核对。"""
    dataset = document.get("dataset")
    if dataset not in DATASET_STEP_PAIRING:
        raise ValueError(f"局清单 dataset 应为 {sorted(DATASET_STEP_PAIRING)}，实为 {dataset!r}")
    cases = document.get("cases") or []
    if not cases:
        raise ValueError("局清单为空")
    seen = set()
    for case in cases:
        task, episode = case.get("task"), case.get("episode")
        if task not in tasks or type(episode) is not int or episode < 0:
            raise ValueError(f"未知任务或本地局号非法：{case}")
        if (task, episode) in seen:
            raise ValueError(f"重复身份：{case}")
        seen.add((task, episode))
        need = ("tier", "seed", "source_episode") if dataset == "test-hard0" else ("tier", "seed")
        missing = [key for key in need if key not in case]
        if missing:
            raise ValueError(f"局清单缺身份字段 {missing}：{case}")
    return cases


def verify_identity(builder, case: dict) -> dict:
    """起跑前逐局核对：builder 解析出的身份与局清单一致（test-hard0 局号 0 ↔ 官方 test episode 3 即由此保证）。"""
    episode = int(case["episode"])
    if not 0 <= episode < builder.get_episode_num():
        raise ValueError(f"{case['task']} 本地局号 {episode} 超出 {builder.dataset} 的 {builder.get_episode_num()} 局")
    identity = builder.resolve_identity(episode)
    for key in ("tier", "seed", "source_episode"):
        if key in case and identity.get(key) != case[key]:
            raise ValueError(f"身份不符 {case['task']} ep{episode} {key}: builder={identity.get(key)!r} 清单={case[key]!r}")
    return identity


def prepare_cases(builder_cls, dataset: str, tasks: list[str], *, source_episodes: list[int] | None = None,
                  tier: str | None = None, index: int = 0) -> dict:
    """test-hard0：按官方 test 局号（与原侧 ``prepare_cases.py --episodes`` 同义）找本地局号；
    test-hard：取每任务 ``tier`` 档的第 ``index`` 局（V9 连通局为 VideoUnmask xhard1 第 0 局）。"""
    cases = []
    for task in tasks:
        builder = make_builder(builder_cls, task, dataset, DATASET_STEP_PAIRING[dataset])
        identities = [builder.resolve_identity(ep) for ep in range(builder.get_episode_num())]
        if dataset == "test-hard0":
            for source in source_episodes or []:
                hits = [i for i in identities if i.get("source_episode") == source]
                if len(hits) != 1:
                    raise ValueError(f"{task} 在 test-hard0 里找不到官方 test episode {source}")
                hit = hits[0]
                cases.append({"task": task, "episode": hit["episode"], "tier": hit["tier"], "seed": hit["seed"],
                              "source_episode": hit["source_episode"]})
        else:
            in_tier = [i for i in identities if i["tier"] == tier]
            if index >= len(in_tier):
                raise ValueError(f"{task} 在 test-hard 的 {tier} 档只有 {len(in_tier)} 局")
            hit = in_tier[index]
            cases.append({"task": task, "episode": hit["episode"], "tier": hit["tier"], "seed": hit["seed"],
                          "candidate": hit.get("candidate"), "spec_sha256": hit.get("spec_sha256")})
    return {"dataset": dataset, "cases": cases}


# ── 轨迹委托（trace_writer） ───────────────────────────────────────────────

def _canonical(obj: Any) -> bytes:
    """规范化字节：数组一律换成 ``array_record``（dtype、shape、sha256），其余按 JSON 排序键序列化。"""
    import numpy as np  # noqa: PLC0415
    import trace_writer as tw  # noqa: PLC0415

    def conv(value):
        if isinstance(value, np.ndarray) or (hasattr(value, "shape") and hasattr(value, "dtype")):
            rec = tw.array_record(value)
            return {"dtype": rec["dtype"], "shape": rec["shape"], "sha256": rec["sha256"]}
        if isinstance(value, dict):
            return {str(k): conv(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [conv(v) for v in value]
        if isinstance(value, (np.integer, np.floating, np.bool_)):
            return value.item()
        return value

    return json.dumps(conv(obj), sort_keys=True, ensure_ascii=False).encode()


class TraceContext:
    """一局的共享状态：当前步号与当前子目标（VLA 请求里的 ``grounded_subgoal``）。"""

    def __init__(self, writer) -> None:
        self.writer = writer
        self.t = 0
        self.subgoal: str | None = None


def _pack_state(obs, i: int = -1):
    import numpy as np  # noqa: PLC0415
    return np.concatenate([np.asarray(obs["joint_state_list"][i]),
                           np.asarray(obs["gripper_state_list"][i])[:1]]).astype(np.float32)


class TracedEnv:
    """包住 builder 给的环境：reset 记演示段，step 记执行后的画面哈希、状态、动作与终止标志。"""

    def __init__(self, inner, ctx: TraceContext) -> None:
        self._inner = inner
        self._ctx = ctx

    def reset(self, *a, **k):
        obs, info = self._inner.reset(*a, **k)
        fronts = list(obs.get("front_rgb_list", []))[:-1]
        wrists = list(obs.get("wrist_rgb_list", []))[:-1]
        n = min(len(obs.get("joint_state_list", [])), len(obs.get("gripper_state_list", []))) - 1
        states = [_pack_state(obs, i) for i in range(max(n, 0))]
        goal = info.get("task_goal")
        texts = list(goal) if isinstance(goal, list) else ([goal] if goal is not None else [])
        self._ctx.writer.log_demo(fronts, wrists, states, texts)
        return obs, info

    def step(self, action):
        obs, reward, terminated, truncated, info = self._inner.step(action)
        self._ctx.t += 1
        self._ctx.writer.log_step(step=self._ctx.t, front=obs["front_rgb_list"][-1], wrist=obs["wrist_rgb_list"][-1],
                                  state=_pack_state(obs), action=action, subgoal=self._ctx.subgoal,
                                  terminated=terminated, truncated=truncated, status=info.get("status"))
        return obs, reward, terminated, truncated, info

    def close(self):
        return self._inner.close()

    def __getattr__(self, name):
        return getattr(self._inner, name)


class TracedBuilder:
    """只暴露 ``runner.episode`` 用到的两个方法；``make_env_for_episode`` 不传步数，取构造时的 ``max_steps``。"""

    def __init__(self, inner, ctx: TraceContext) -> None:
        self._inner = inner
        self._ctx = ctx

    def make_env_for_episode(self, episode):
        return TracedEnv(self._inner.make_env_for_episode(episode), self._ctx)

    def resolve_episode(self, episode):
        return self._inner.resolve_episode(episode)


class TracedClient:
    """包住 VLA websocket 客户端：记每次 ``infer`` 的规范化请求与完整动作块。"""

    def __init__(self, inner, ctx: TraceContext) -> None:
        self._inner = inner
        self._ctx = ctx

    def reset(self):
        self._ctx.writer.log_request("vla_reset", b"", step=self._ctx.t)
        return self._inner.reset()

    def infer(self, element):
        self._ctx.subgoal = element.get("grounded_subgoal")
        self._ctx.writer.log_request("vla_infer", _canonical(element), step=self._ctx.t)
        out = self._inner.infer(element)
        self._ctx.writer.log_response(out.get("actions"), step=self._ctx.t)
        return out


def _spool_payload(out: Path) -> bytes:
    """规划请求的规范化字节：``request.json``（去掉 id／created）+ ``prompt.txt`` + 各附图字节的 sha256。"""
    request = json.loads((out / "request.json").read_text())
    images = {name: file_sha256(out / name) for name in request.get("images", []) if (out / name).is_file()}
    request = {k: v for k, v in request.items() if k not in ("id", "created")}
    prompt = (out / "prompt.txt").read_text() if (out / "prompt.txt").is_file() else ""
    return json.dumps({"request": request, "prompt": prompt, "images": images}, sort_keys=True,
                      ensure_ascii=False).encode()


class TracedPlanner:
    """包住 Astra ``Planner``：每次规划／复审请求按 spool 目录内容记一行 request。"""

    def __init__(self, inner, ctx: TraceContext) -> None:
        self._inner = inner
        self._ctx = ctx

    def _log(self, name: str, rid: str) -> None:
        out = Path(self._inner.spool) / rid
        if (out / "request.json").is_file():
            self._ctx.writer.log_request(name, _spool_payload(out), step=self._ctx.t)

    def predict(self, *a, **k):
        result = self._inner.predict(*a, **k)
        self._log("planner", result[1])
        return result

    def review_second_button(self, *a, **k):
        result = self._inner.review_second_button(*a, **k)
        self._log("planner_review", result[1])
        return result

    def __getattr__(self, name):
        return getattr(self._inner, name)


class TracedMonitor:
    """包住监视器：记 ``input.json``（去掉图片路径，换成各图 sha256）。"""

    def __init__(self, inner, ctx: TraceContext) -> None:
        self._inner = inner
        self._ctx = ctx

    def predict(self, task, goal, subgoal, frames, command_start, wrist, out):
        result = self._inner.predict(task, goal, subgoal, frames, command_start, wrist, out)
        sample_path = Path(out) / "input.json"
        if sample_path.is_file():
            sample = json.loads(sample_path.read_text())
            sample["images"] = [file_sha256(Path(p)) if Path(p).is_file() else None for p in sample.get("images", [])]
            payload = json.dumps(sample, sort_keys=True, ensure_ascii=False).encode()
        else:
            payload = _canonical({"task": task, "goal": goal, "subgoal": subgoal, "command_start": command_start})
        self._ctx.writer.log_request("monitor", payload, step=self._ctx.t)
        return result


# ── 运行（复刻 main() 六项） ───────────────────────────────────────────────

def _terminal_reason(result: dict, max_steps: int) -> str:
    status = result.get("status")
    if status == "error":
        return "exception"
    if status == "timeout" and int(result.get("steps", 0)) >= int(max_steps):
        return "loop_exit"
    return "env_terminated"


def stop_file(output: Path) -> Path:
    """``main()`` 第③项查的位置：``<output>/../../STOP.json``（即 ``group_*/STOP.json``）。"""
    return Path(output).parent.parent / "STOP.json"


def check_layout(output: Path, spool: Path) -> None:
    """``results`` 与 ``planner_calls`` 同属一个 RUN 目录，RUN 的上一层必须叫 group_0／group_1。"""
    output, spool = Path(output).resolve(), Path(spool).resolve()
    if output.parent != spool.parent:
        raise ValueError(f"RUN_BLOCKED reason=layout --output 与 --spool 须在同一 RUN 目录下：{output} {spool}")
    if output.parent.parent.name not in GROUP_DIR_NAMES:
        raise ValueError(f"RUN_BLOCKED reason=layout RUN 目录的上一层须为 {GROUP_DIR_NAMES} 之一（STOP.json 停机口），"
                         f"实为 {output.parent.parent}")


def run_cases(args, deps: SimpleNamespace) -> dict:
    """复刻 Astra ``main()``（2026-10-04 按上游源码核实的六项）：

    ① ``validate_checkpoints``：VLA 与监视器文件齐全、监视器哈希与 ``weights.json`` 相同；
    ② ``--output`` 与 ``--spool`` 都必须不存在，``mkdir(exist_ok=False)``；
    ③ 每局开跑前查 ``<output>/../../STOP.json``，存在即停；
    ④ ``status=="error"`` 且不是规划输出不合模板（``core.is_planner_failure``）的局计入错误数，
       其余结局清零（与上游同为「连续」口径），累计 3 次停整个分片；
    ⑤ 错误信息以 ``Planner API``／``Pilot planner-call``／``Planner bridge failed`` 开头的局，单次即停；
    ⑥ 全部局正常走完写 ``PILOT_FINISHED.json``。

    ``deps``：``astra``（bootstrap 结果）、``builder_cls``、``make_client()``、``make_monitor(base, adapter)``、
    ``make_responder()``；测试注入替身，正式运行用 ``default_deps``。
    """
    astra = deps.astra
    output, spool = Path(args.output), Path(args.spool)
    check_layout(output, spool)
    document = json.loads(Path(args.cases).read_text())
    cases = validate_cases(document, astra.core.TASKS)
    args.dataset = document["dataset"]
    check_pairing(args.dataset, args.max_steps)
    astra.release_utils.validate_checkpoints(args.vla_checkpoint, args.monitor_adapter)  # ①
    responder = deps.make_responder()
    for directory in (output, spool):  # ②
        if directory.exists():
            raise ValueError("Use new output and spool directories; existing evidence is preserved")
    output.mkdir(parents=True, exist_ok=False)
    spool.mkdir(parents=True, exist_ok=False)

    tasks = list(dict.fromkeys(c["task"] for c in cases))
    builders, identities = {}, {}
    for task in tasks:  # 付费请求之前先把全部身份核完
        builders[task] = make_builder(deps.builder_cls, task, args.dataset, args.max_steps)
        for case in (c for c in cases if c["task"] == task):
            identities[(task, case["episode"])] = verify_identity(builders[task], case)

    client = deps.make_client()
    monitor = deps.make_monitor(args.monitor_base, args.monitor_adapter)
    planner = astra.core.Planner(str(spool), responder=responder)
    results, errors = [], 0
    for task in tasks:
        episodes = sorted(c["episode"] for c in cases if c["task"] == task)
        for ep in episodes:
            if stop_file(output).exists():  # ③
                print(f"ASTRA_STOP reason=host_stop task={task} episode={ep}", flush=True)
                raise AstraStop("host_stop", "Host requested stop before next episode")
            rp = output / task / f"ep{ep:03d}" / "result.json"
            if rp.exists():
                continue
            if rp.parent.exists():
                raise RuntimeError("Incomplete prior episode; use a new output directory to preserve its evidence")
            result = run_one(args, task, ep, identities[(task, ep)], builders[task], monitor, planner, client, astra)
            results.append(result)
            failed = result["status"] == "error" and not astra.core.is_planner_failure(result)
            errors = errors + 1 if failed else 0  # ④
            if result["status"] == "error" and result.get("error", "").startswith(PLANNER_STOP_PREFIXES):  # ⑤
                print(f"ASTRA_STOP reason=planner_error task={task} episode={ep}", flush=True)
                raise AstraStop("planner_error", "Stopping pilot after planner service or budget error")
            if errors >= INFRA_ERROR_LIMIT:
                print(f"ASTRA_STOP reason=infra_errors task={task} episode={ep} errors={errors}", flush=True)
                raise AstraStop("infra_errors", "Three consecutive infrastructure/protocol errors; stopping shard")
    from core import atomic_json  # noqa: PLC0415
    finished = {"dataset": args.dataset, "tasks": tasks, "finished_at": time.time()}
    atomic_json(output / "PILOT_FINISHED.json", finished)  # ⑥
    print(f"ASTRA_PILOT_FINISHED dataset={args.dataset} episodes={len(results)}", flush=True)
    return {"results": results, "finished": finished}


def run_one(args, task, ep, identity, builder, monitor, planner, client, astra) -> dict:
    """一局：建 trace，经委托包装调 Astra 的 ``runner.episode``，按结果收尾 trace。"""
    import trace_writer as tw  # noqa: PLC0415
    ep_dir = Path(args.output) / task / f"ep{ep:03d}"
    trace_path = (Path(args.trace_root) / task / f"ep{ep:03d}" / "trace.jsonl") if args.trace_root else ep_dir / "trace.jsonl"
    trace_identity = {"task": task, "dataset": args.dataset, **identity}
    writer = tw.TraceWriter(trace_path, route="astra-new", identity=trace_identity, max_steps=args.max_steps)
    ctx = TraceContext(writer)
    try:
        result = astra.runner.episode(args, task, ep, TracedBuilder(builder, ctx), TracedMonitor(monitor, ctx),
                                      TracedPlanner(planner, ctx), TracedClient(client, ctx))
    except BaseException:
        writer.close(status="error", terminal_reason="driver_exception")
        raise
    writer.close(status=result.get("status"), terminal_reason=_terminal_reason(result, args.max_steps),
                 planner_calls=result.get("planner_calls"), monitor_calls=result.get("monitor_calls"),
                 review_calls=result.get("review_calls"), error=result.get("error"))
    return result


def default_deps(astra: SimpleNamespace, port: int) -> SimpleNamespace:
    def make_client():
        from openpi_client.websocket_client_policy import MMEVLAWebsocketClientPolicy  # noqa: PLC0415
        import openpi_client  # noqa: PLC0415
        print(f"ASTRA_VLA_CLIENT openpi_client={openpi_client.__file__} port={port}", flush=True)
        return MMEVLAWebsocketClientPolicy("127.0.0.1", port)

    def make_responder():
        # 与 main() 的 ResponsesClient(os.environ.get('OPENAI_API_KEY','')) 相同；不支持 --key-file（R5）
        return astra.api_client.ResponsesClient(os.environ.get("OPENAI_API_KEY", ""))

    return SimpleNamespace(astra=astra, builder_cls=default_builder_cls(), make_client=make_client,
                           make_monitor=lambda base, adapter: astra.runner.Monitor(base, adapter),
                           make_responder=make_responder)


# ── 汇总 ──────────────────────────────────────────────────────────────────

def summarize(cases_path: Path, results_root: Path) -> dict:
    document = json.loads(Path(cases_path).read_text())
    counts = dict(success=0, fail=0, timeout=0, error=0, pending=0)
    rows = []
    for case in document["cases"]:
        path = Path(results_root) / case["task"] / f"ep{case['episode']:03d}" / "result.json"
        result = json.loads(path.read_text()) if path.is_file() else {**case, "dataset": document["dataset"], "status": "pending"}
        if result.get("dataset") != document["dataset"]:
            raise ValueError(f"结果 dataset 与局清单不符：{path}")
        counts[result["status"] if result["status"] in counts else "error"] += 1
        rows.append(result)
    n = len(document["cases"])
    return dict(dataset=document["dataset"], expected=n, counts=counts,
                complete=counts["error"] == counts["pending"] == 0,
                success_rate=counts["success"] / n if n else 0.0, cases=rows)


# ── 命令行 ────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("prepare", help="生成新侧局清单")
    p.add_argument("--dataset", required=True, choices=sorted(DATASET_STEP_PAIRING))
    p.add_argument("--tasks", nargs="+", default=None, help="默认 Astra core.TASKS 全部 16 个")
    p.add_argument("--source-episodes", nargs="+", type=int, default=None, help="test-hard0：官方 test 局号（如 3）")
    p.add_argument("--tier", default=None, help="test-hard：档名（如 xhard1）")
    p.add_argument("--index", type=int, default=0, help="test-hard：该档内第几局（从 0 计）")
    p.add_argument("--output", required=True)
    p.add_argument("--astra-root", default=None)

    def common(q):
        q.add_argument("--cases", required=True)
        q.add_argument("--vla-checkpoint", required=True)
        q.add_argument("--monitor-adapter", required=True)
        q.add_argument("--max-steps", type=int, required=True, help="步数只来自启动命令：test-hard0 1300，test-hard 1600")
        q.add_argument("--port", type=int, default=18762)
        q.add_argument("--astra-root", default=None)

    c = sub.add_parser("check", help="起跑前核对（不加载模型、不联网）")
    common(c)

    r = sub.add_parser("run", help="正式运行")
    common(r)
    r.add_argument("--max-planner-calls", type=int, default=24)
    r.add_argument("--monitor-base", default=None, help="默认 Astra runner.BASE")
    r.add_argument("--output", required=True)
    r.add_argument("--spool", required=True)
    r.add_argument("--trace-root", default=None, help="默认写在 results/<task>/ep<NNN>/trace.jsonl")

    s = sub.add_parser("summarize")
    s.add_argument("--cases", required=True)
    s.add_argument("--results", required=True)
    s.add_argument("--output", required=True)
    return parser


def _print_sources(astra: SimpleNamespace) -> None:
    digests = source_digests(astra.champ)
    print("ASTRA_SOURCE root=" + str(astra.root) + " " + " ".join(f"{k}={v}" for k, v in digests.items()), flush=True)


def cmd_check(args) -> int:
    astra = bootstrap(astra_root(args.astra_root))
    _print_sources(astra)
    assert_env_sources()
    document = json.loads(Path(args.cases).read_text())
    cases = validate_cases(document, astra.core.TASKS)
    check_pairing(document["dataset"], args.max_steps)
    astra.release_utils.validate_checkpoints(args.vla_checkpoint, args.monitor_adapter)
    builder_cls = default_builder_cls()
    for task in dict.fromkeys(c["task"] for c in cases):
        builder = make_builder(builder_cls, task, document["dataset"], args.max_steps)
        for case in (c for c in cases if c["task"] == task):
            verify_identity(builder, case)
    with socket.socket() as sock:  # 端口探测：与 run.sh 相同的 bind 检查
        sock.bind(("0.0.0.0", int(args.port)))
    print(f"ASTRA_CHECK=PASS dataset={document['dataset']} max_steps={args.max_steps} cases={len(cases)} port={args.port}",
          flush=True)
    return 0


def main(argv: list[str] | None = None, deps_factory: Callable | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "summarize":
        summary = summarize(Path(args.cases), Path(args.results))
        Path(args.output).write_text(json.dumps(summary, indent=2) + "\n")
        print(f"ASTRA_SUMMARY dataset={summary['dataset']} expected={summary['expected']} "
              + " ".join(f"{k}={v}" for k, v in summary["counts"].items()), flush=True)
        return 0
    if args.cmd == "check":
        return cmd_check(args)
    astra = bootstrap(astra_root(args.astra_root))
    if args.cmd == "prepare":
        out = Path(args.output)
        if out.exists():
            raise SystemExit(f"{out} 已存在；局清单不覆盖")
        document = prepare_cases(default_builder_cls(), args.dataset, args.tasks or list(astra.core.TASKS),
                                 source_episodes=args.source_episodes, tier=args.tier, index=args.index)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(document, indent=2) + "\n")
        print(f"ASTRA_CASES dataset={document['dataset']} cases={len(document['cases'])} output={out}", flush=True)
        return 0
    _print_sources(astra)
    assert_env_sources()
    if args.monitor_base is None:
        args.monitor_base = astra.runner.BASE
    deps = (deps_factory or default_deps)(astra, args.port)
    run_cases(args, deps)
    return 0


if __name__ == "__main__":
    sys.exit(main())
