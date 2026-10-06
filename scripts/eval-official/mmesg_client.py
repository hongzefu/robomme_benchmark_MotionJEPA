#!/usr/bin/env python3
"""GroundSG（MME-VLA symbolic-grounded-subgoal）新侧客户端（1003-oracle-subgoal-groundsg-eval-plan.md 第二部分 1.3）。

``env_client.py run --policy mmesg --mme-variant {ground-sg-oracle,ground-sg-qwenvl}`` 按
``load_sibling("mmesg_client")`` 加载本模块，调用 ``run_episode(session, identity, conn_info, recorder)``。

循环本身**不重写**：从官方 ``eval.py`` 用 ``official_defs.extract_defs`` 摘取 ``EpisodeEvaluator``、``Args`` 原文，
直接调官方 ``EpisodeEvaluator.eval_each_episode``；本模块只提供一个 runner 适配对象（``SessionRunner``），把官方
``EnvRunner`` 的接口（``env_id``、``episode_id``、``task_goal``、``difficulty``、``info``、``get_init_obs()``、
``step()``、``simple_subgoal_oracle``、``grounded_subgoal_oracle``）委托到本仓库 ``EnvSession`` 的
``reset()``／``step()``，每步同步 ``info``。``get_init_obs``／``step`` 的函数体与官方 ``EnvRunner`` 逐行同式，只把
``self.env`` 换成 ``EnvSession``；以下三类异常不当作环境错误吞掉、原样上抛：``StepCapReached``（``--strict-cap``，
本模块收住后返回，由 ``run_one`` 按 ``cap_hit`` 记 timeout）、``RecorderError``（基础设施）、``ResetBudgetExhausted``。

子目标预测器只取所选变体需要的类：Oracle 取 ``OracleSubgoalPredictor``（不读 qwenvl/api.py、不导入 swift）；
QwenVL 取 ``QwenVLSubgoalPredictor`` 与 ``Qwen3VLModel``（不取 Gemini／MemER）。构造前断言 ``use_oracle`` 与
``use_qwenvl`` 恰一个为真。预测器与评估器放在 ``policy_context`` 里整席只建一次（``make_policy_context``），
与官方「一次评估只建一个预测器、跨局复用」相同。

每局外围记录（两侧同一套代码，原侧 ``official_hard_runner.py`` 也用这里的 ``EpisodeTap``／``TracingClient``）：

* ``trace.jsonl``（``trace_writer.TraceWriter``）：位置优先 ``conn_info["trace_path"]``，否则
  ``<trace_dir>/trace.jsonl``，否则 ``<recorder.out_dir>/trace.jsonl``，都没有则不写；
* 发给模型的每个请求（``reset``／``add_buffer``／``infer``）以 ``official_defs.canonical_bytes`` 规范化后记 sha256，
  ``infer`` 回复记完整动作块；
* Qwen 临时目录 ``<trace_dir>/qwen-tmp/<dataset>/<episode_tag>/``（无 ``trace_dir`` 时落在临时目录），局末把
  ``ep<id>_QwenVL_log.jsonl`` 归档到轨迹所在目录，临时目录整个删除（``unknown``／异常早退同样清理）；
* 官方循环自己写的叠字 mp4 局末删除（交付视频走本仓库录像器）——原侧（不传 ``keep_official``）保持如此。

终态：官方返回 ``success``／``fail``／``timeout`` 原样；``unknown``（及其他非终态值）记 ``status="error"``、
``error="success_flag=<值>"``，不中止整席；官方循环抛出的异常记 ``status="error"`` + ``<异常类>: <消息>``，
``infra`` 按 ``mme_client.INFRA_MARKERS`` 判。

第二阶段 S1（1005-eval-video-phase2-all-models-rerun-plan.md 第二部分一节「S1」与八节 3.5）只增不改：

* ``run_official_episode(..., keep_official=UNSET)``：不传时与此前逐字节相同（原侧 ``official_hard_runner`` 不传，
  R1／R2）。传真值时：调用前给 evaluator 实例包一层 ``init_episode`` 抓住官方 ``(task_goal, recorder)``（``finally``
  还原）；正常局官方自己 ``save_video``；``StepCapReached``／其他异常／``unknown`` 而 ``video_dir`` 无 mp4 时，按官方
  文件名格式（``official_safe_filename`` 截断）调用**官方 recorder 自己的** ``save_video`` 补存；``init_episode`` 返回前
  失败：一帧未录为 ``none``，已取到 reset 帧但录像器没交出来为 ``partial``（只记原因，不冒充完整视频）。``finally``
  在删 ``video_dir`` 之前经 ``keep_official_videos`` 完整解码、核帧数、核恰一个文件后搬入
  ``<archive_dir>/official/`` 并写 ``provenance.json``；核验或补存失败只记 ``official_save_error``，原始帧照留。
  返回另加 ``official_videos``、``official_source``（``official``／``official-salvaged``／``partial``／``none``）、
  ``official_save_error`` 与 C8 三分计数。
* 新侧 ``run_episode`` 传 ``keep_official=True``；轨迹按共享契约收尾：C6 identity 补 ``attempt``，缺观测步用
  ``log_missing_step``（C8），``end`` 写 ``steps_attempted``／``steps_observed``／``frames_recorded``／
  ``omitted_timeout_frames``，``terminal_reason`` 取终态（C3，官方原值另记 ``success_flag``），无帧局 ``no_frame=true``。
"""
from __future__ import annotations

import sys
from pathlib import Path as _Path

_HERE = str(_Path(__file__).resolve().parent)
# 不改 sys.path：同目录模块一律按文件路径加载（原侧 official_hard_runner 要求 sys.path 只加两项）

import hashlib  # noqa: E402
import importlib.util  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
import time  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Any, Callable  # noqa: E402

import numpy as np  # noqa: E402

NORMAL = ("success", "fail", "timeout")
#: 不当作环境错误吞掉的异常（按类名判，避免导入 env_client）
PASS_THROUGH = ("StepCapReached", "RecorderError", "ResetBudgetExhausted")
INFRA_MARKERS = ("RecorderError", "svulkan2", "EXCLUSIVE", "Vulkan", "vk::", "out of memory", "RESOURCE_EXHAUSTED",
                 "CUDA_ERROR", "ConnectionClosed", "ConnectionRefused", "InvalidStatus", "Connection reset")


def load_sibling(name: str):
    """按文件路径加载本目录下的模块（别名与 env_client.load_sibling 相同，已加载则复用）。"""
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, _Path(_HERE) / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


official_defs = load_sibling("official_defs")
trace_writer = load_sibling("trace_writer")
_UNSET = trace_writer.UNSET  # R2：新增可选参数的「未提供」哨兵

#: 官方叠字视频与身份清单所在子目录（R4：官方版式文件一律放 official/）
OFFICIAL_VIDEO_SUBDIR = "official"
OFFICIAL_SOURCES = ("official", "official-salvaged", "partial", "none")
PROVENANCE_SCHEMA = "official-video-provenance/1"
FRAMES_BASIS = "demo_frames + 1 + steps_observed - omitted_timeout_frames"


def classify_infra(*texts: str | None) -> str | None:
    for text in texts:
        for marker in INFRA_MARKERS:
            if marker in (text or ""):
                return marker
    return None


# ── 外围记录：轨迹、原始帧、请求 ─────────────────────────────────────────────


class RawFrameWriter:
    """原侧每局一个原始帧目录（格式与 ``pp_official_runner.RawFrameWriter`` 相同，S6 启动器同一套转码）：

    ``front.rgb24``／``wrist.rgb24`` 逐帧拼接 H×W×3 uint8 原始字节（ffmpeg rawvideo rgb24）；``frames.json`` 为
    ``{"pix_fmt":"rgb24","streams":{"front":{"width","height","count"},"wrist":{…}},"demo_frames","init_frames",
    "exec_steps","missing_steps","order"}``。帧顺序：reset 返回的全部帧（演示 + 初始），之后每执行一步追加该步观测；
    某步没有观测（环境 step 抛异常）时不追加、步号记入 ``missing_steps``。
    ``count = demo_frames + init_frames + exec_steps - len(missing_steps)``。"""

    STREAMS = ("front", "wrist")

    def __init__(self, frames_dir: str | Path):
        self.dir = Path(frames_dir)
        self.dir.mkdir(parents=True, exist_ok=False)
        self._fh = {s: (self.dir / f"{s}.rgb24").open("wb") for s in self.STREAMS}
        self.shape: dict[str, tuple | None] = {s: None for s in self.STREAMS}
        self.count = {s: 0 for s in self.STREAMS}
        self.meta: dict[str, Any] = {"demo_frames": None, "init_frames": 0, "exec_steps": 0, "missing_steps": []}
        self._closed = False

    def write(self, stream: str, frame: Any) -> None:
        a = np.ascontiguousarray(np.asarray(frame))
        if a.dtype != np.uint8 or a.ndim != 3 or a.shape[2] != 3:
            raise ValueError(f"{stream} 帧应为 H×W×3 uint8，实际 {a.dtype} {a.shape}")
        if self.shape[stream] is None:
            self.shape[stream] = a.shape
        elif self.shape[stream] != a.shape:
            raise ValueError(f"{stream} 帧尺寸变化：{self.shape[stream]} → {a.shape}")
        self._fh[stream].write(a.tobytes())
        self.count[stream] += 1

    def close(self) -> dict:
        if self._closed:
            return self.summary()
        for fh in self._fh.values():
            fh.close()
        self._closed = True
        summ = self.summary()
        (self.dir / "frames.json").write_text(json.dumps(summ, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                                              encoding="utf-8")
        return summ

    def summary(self) -> dict:
        streams = {}
        for s in self.STREAMS:
            shp = self.shape[s]
            streams[s] = {"width": None if shp is None else int(shp[1]), "height": None if shp is None else int(shp[0]),
                          "count": self.count[s]}
        return {"pix_fmt": "rgb24", "streams": streams, "order": "reset_all_then_per_step_last", **self.meta}


class EpisodeTap:
    """一局的外围记录器（新侧与原侧共用）。所有回调都在环境／模型调用之外，只读不改数据。

    * ``on_reset(pre_traj)``：``get_init_obs`` 返回后，记演示（全部 reset 帧、状态、目标文本）；
    * ``on_request``／``on_response``：客户端请求与回复；
    * ``on_step(action, obs3, stop, flag, terminated, truncated)``：每执行一步（含异常步，``obs3`` 为 None 三元组）。

    ``missing_step_contract``（S1，默认 ``UNSET`` = 旧行为逐字节不变）：真值时缺观测步按 C8 用
    ``TraceWriter.log_missing_step`` 记（``observed=false``、``missing_reason``），只有新侧打开。
    ``missing_steps`` 只在内存里记缺观测步号（供 C8 计数），不影响任何输出。
    """

    def __init__(self, trace: Any | None, frames: RawFrameWriter | None = None, *,
                 missing_step_contract: Any = _UNSET):
        self.trace = trace
        self.frames = frames
        self.missing_step_contract = missing_step_contract is not _UNSET and bool(missing_step_contract)
        self.missing_steps: list[int] = []
        self.steps = 0
        self.decisions = 0
        self.last_subgoal: str | None = None
        self.history_from = 0
        self.demo_frames: int | None = None
        self.task_goal: str | None = None
        self.requests: list[str] = []  # 请求规范化字节 sha256（测试与摘要用）

    def on_reset(self, pre: dict) -> None:
        imgs, wrists, states = list(pre["images"]), list(pre["wrist_images"]), list(pre["states"])
        self.demo_frames = len(imgs) - 1
        self.task_goal = pre.get("task_goal")
        if self.trace is not None:
            self.trace.log_demo(imgs, wrists, states, [self.task_goal])
        if self.frames is not None:
            for f in imgs:
                self.frames.write("front", f)
            for w in wrists:
                self.frames.write("wrist", w)
            self.frames.meta.update(demo_frames=len(imgs) - 1, init_frames=1 if imgs else 0)

    def on_request(self, name: str, obj: Any) -> None:
        payload = official_defs.canonical_bytes(obj)
        self.requests.append(trace_writer.bytes_record(payload)["sha256"])
        if self.trace is not None:
            self.trace.log_request(name, payload, step=self.steps)
        if name == "add_buffer" and self.trace is not None:
            n = len(obj["images"]) if isinstance(obj, dict) and "images" in obj else 0
            self.trace.log_history(self.history_from, self.steps,
                                   note=f"add_buffer frames={n} exec_start_idx={obj.get('exec_start_idx')}")
            self.history_from = self.steps
        if name == "infer":
            self.decisions += 1
            self.last_subgoal = obj.get("grounded_subgoal") if isinstance(obj, dict) else None

    def on_response(self, actions: Any) -> None:
        if self.trace is not None:
            self.trace.log_response(actions, step=self.steps)

    def on_step(self, action: Any, obs3: tuple, stop: bool, flag: str, terminated: Any, truncated: Any,
                reason: str | None = None) -> None:
        self.steps += 1
        img, wrist, state = obs3
        if img is None:
            self.missing_steps.append(self.steps)
        if self.frames is not None:
            self.frames.meta["exec_steps"] = self.steps
            if img is not None:
                self.frames.write("front", img)
                if wrist is not None:
                    self.frames.write("wrist", wrist)
            else:
                self.frames.meta["missing_steps"].append(self.steps)
        if self.trace is not None and img is None and self.missing_step_contract:
            self.trace.log_missing_step(step=self.steps, action=action, subgoal=self.last_subgoal,
                                        reason=reason or f"no_observation status={flag}")
        elif self.trace is not None:
            self.trace.log_step(step=self.steps, front=img, wrist=wrist, state=state, action=action,
                                subgoal=self.last_subgoal, terminated=bool(terminated), truncated=bool(truncated),
                                status=flag)


class TracingClient:
    """包住 ``MMEVLAWebsocketClientPolicy``（或替身）的 ``reset``／``add_buffer``／``infer``：先记请求再原样转发。"""

    def __init__(self, inner: Any, tap: EpisodeTap):
        self._inner = inner
        self._tap = tap

    def reset(self):
        self._tap.on_request("reset", {"reset": True})
        return self._inner.reset()

    def add_buffer(self, buffer):
        self._tap.on_request("add_buffer", buffer)
        return self._inner.add_buffer(buffer)

    def infer(self, obs):
        self._tap.on_request("infer", obs)
        out = self._inner.infer(obs)
        self._tap.on_response(out["actions"])
        return out

    def close(self) -> None:
        ws = getattr(self._inner, "_ws", None)
        if ws is not None:
            try:
                ws.close()
            except Exception:  # noqa: BLE001
                pass

    def __getattr__(self, name):
        return getattr(self._inner, name)


def episode_scratch(trace_dir: str | None) -> tuple[Path, bool]:
    """本局临时区：有 ``trace_dir`` 用它（返回 False：不整删），否则新建临时目录（返回 True：局末整删）。"""
    if trace_dir:
        p = Path(trace_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p, False
    return Path(tempfile.mkdtemp(prefix="mmesg-")), True


def qwen_begin(predictor: Any, scratch: Path, dataset: str, episode_tag: str) -> Path | None:
    """QwenVL 预测器：把官方 ``save_dir`` 指到 ``<scratch>/qwen-tmp/<dataset>/<episode_tag>/``（官方再拼
    ``<env_name>/ep<episode_id>``）。Oracle 预测器返回 None。"""
    if type(predictor).__name__ != "QwenVLSubgoalPredictor":
        return None
    base = scratch / "qwen-tmp" / str(dataset) / str(episode_tag)
    base.mkdir(parents=True, exist_ok=True)
    predictor.save_dir = base
    predictor.episode_dir = None
    return base


def qwen_end(predictor: Any, base: Path | None, archive_dir: Path | None) -> str | None:
    """局末（正常、``unknown``、异常都调）：``ep<id>_QwenVL_log.jsonl`` 归档到 ``archive_dir``，再整删临时目录，
    并逐级删掉空的 ``qwen-tmp`` 父目录。返回归档路径。"""
    if base is None:
        return None
    archived = None
    logs = sorted(base.glob("*/ep*_QwenVL_log.jsonl"))
    if archive_dir is not None:
        archive_dir.mkdir(parents=True, exist_ok=True)
        for log in logs:
            dst = archive_dir / log.name
            shutil.move(str(log), dst)
            archived = str(dst)
    shutil.rmtree(base, ignore_errors=True)
    predictor.episode_dir = None
    p = base.parent
    for _ in range(2):  # <dataset>、qwen-tmp 两层，空了才删
        try:
            p.rmdir()
        except OSError:
            break
        p = p.parent
    return archived


def trace_location(conn_info: dict, recorder: Any) -> Path | None:
    """轨迹位置：``trace_path`` → ``<trace_dir>/trace.jsonl`` → ``<recorder.out_dir>/trace.jsonl`` → 不写。"""
    if conn_info.get("trace_path"):
        return Path(conn_info["trace_path"])
    if conn_info.get("trace_dir"):
        return Path(conn_info["trace_dir"]) / "trace.jsonl"
    out = getattr(recorder, "out_dir", None)
    return Path(out) / "trace.jsonl" if out else None


def map_flag(flag: str) -> tuple[str, str | None]:
    """官方返回值 → (status, error)。"""
    if flag in NORMAL:
        return flag, None
    return "error", f"success_flag={flag}"


# ── 新侧 runner 适配 ────────────────────────────────────────────────────────


def official_episode_id(identity: dict, episode_tag: str) -> str:
    """交给官方循环的短局号：``<source_episode>a<attempt>``（V9 无源局号时取 builder_episode），如 ``3a1``。

    与原侧官方 ``EnvRunner.episode_id``（源局号整数）同量级，避免叠字视频文件名超过 255 字节。"""
    src = identity.get("source_episode")
    if src is None:
        src = identity.get("builder_episode")
    att = episode_tag.rsplit(".a", 1)[1] if ".a" in episode_tag else "1"
    return f"{src}a{att}"


class SessionRunner:
    """官方 ``EnvRunner`` 的接口，委托到 ``EnvSession``。``get_init_obs``／``step`` 与官方逐行同式。"""

    def __init__(self, session: Any, episode_tag: str, pack_state: Callable, tap: EpisodeTap,
                 official_episode_id: str | None = None):
        self._session = session
        self._pack_state = pack_state
        self._tap = tap
        self.env_id = session.task
        # 交给官方循环的 episode_id：官方 eval.py 用它拼叠字视频文件名
        # ``{env_id}_ep{episode_id}_{flag}_{task_goal}_{difficulty}.mp4``，任务目标文本很长（如 SwingXtimes）时
        # 用 episode_tag（``<key>.a<n>``）会超过文件名 255 字节上限、ffmpeg 打不开输出而 Broken pipe；
        # 故改用短编号 ``official_episode_id``，本仓库自己的目录、Qwen 临时目录、轨迹仍按 episode_tag。
        self.episode_id = official_episode_id or episode_tag
        self.task_goal: str = ""
        self.info: dict | None = None
        self.last_exception: BaseException | None = None
        env = getattr(session, "env", None)
        self.difficulty = getattr(getattr(env, "unwrapped", None), "difficulty", None)

    def get_init_obs(self) -> dict:
        obs, self.info = self._session.reset()
        if isinstance(self.info["task_goal"], list):
            self.task_goal = self.info["task_goal"][0]
        else:
            self.task_goal = self.info["task_goal"]
        images = obs["front_rgb_list"]
        wrist_images = obs["wrist_rgb_list"]
        states = [self._pack_state(joint_state, gripper_state) for joint_state, gripper_state in
                  zip(obs["joint_state_list"], obs["gripper_state_list"])]
        pre = {"images": images, "wrist_images": wrist_images, "states": states, "task_goal": self.task_goal}
        self._tap.on_reset(pre)
        return pre

    def step(self, action: np.ndarray):
        try:
            obs, _, terminated, truncated, self.info = self._session.step(action)
        except Exception as e:
            if type(e).__name__ in PASS_THROUGH:
                raise
            print(f"Error: {e}")
            self.last_exception = e
            self._tap.on_step(action, (None, None, None), True, "error", None, None,
                              reason=f"{type(e).__name__}: {e}"[:400])
            return (None, None, None), True, "error"

        img = obs["front_rgb_list"][-1]
        wrist_img = obs["wrist_rgb_list"][-1]
        joint_state = obs["joint_state_list"][-1]
        gripper_state = obs["gripper_state_list"][-1]
        state = self._pack_state(joint_state, gripper_state)

        outcome = self.info.get("status", "unknown")
        stop = terminated or truncated

        self._tap.on_step(action, (img, wrist_img, state), stop, outcome, terminated, truncated)
        return (img, wrist_img, state), stop, outcome

    @property
    def simple_subgoal_oracle(self) -> str:
        return self.info["simple_subgoal_online"]

    @property
    def grounded_subgoal_oracle(self) -> str:
        return self.info["grounded_subgoal_online"]


# ── 席位上下文 ──────────────────────────────────────────────────────────────


def default_client_factory(host: str, port: int, episode: dict) -> Any:
    """新侧默认：``mme_client.make_recording_client``（``MMEVLAWebsocketClientPolicy`` 子类，收发与父类逐行相同，
    另把逐消息 sha256 记进录制器事件）。"""
    mme = load_sibling("mme_client")
    return mme.make_recording_client(host, int(port), episode.get("recorder"), episode.setdefault("timing", {}))


def make_policy_context(seat_info: dict, *, client_factory: Callable | None = None, qwen_extra: dict | None = None,
                        save_dir: str | Path | None = None) -> dict:
    """整席只建一次：官方定义、``Args``、子目标预测器（QwenVL 在此加载模型）、``EpisodeEvaluator``。

    ``client_factory(host, port, episode) -> client`` 与 ``qwen_extra``（swift 三个名字的替身）只供测试注入。"""
    variant = seat_info.get("mme_variant")
    if variant not in official_defs.VARIANTS:
        raise ValueError(f"mme_variant={variant!r} 不是 {official_defs.VARIANTS} 之一")
    ctx: dict[str, Any] = {"variant": variant, "seat_info": dict(seat_info), "episode": None,
                           "client_factory": client_factory or default_client_factory}

    def ws_factory(host, port):
        ep = ctx["episode"]
        client = TracingClient(ctx["client_factory"](host, port, ep), ep["tap"])
        ep["clients"].append(client)
        return client

    defs = official_defs.load_groundsg(variant, with_env_runner=False, ws_module=official_defs.ws_shim(ws_factory),
                                       qwen_extra=qwen_extra)
    base = Path(save_dir) if save_dir else Path(seat_info.get("trace_root") or seat_info.get("out") or
                                                 tempfile.gettempdir()) / "qwen-tmp"
    args = official_defs.make_args(defs, variant=variant, host=seat_info.get("host", "127.0.0.1"),
                                   port=int(seat_info["port"]), max_steps=int(seat_info["max_steps"]),
                                   adapter_path=seat_info.get("qwenvl_groundSG_adapter_path"), save_dir=str(base))
    t0 = time.perf_counter()
    predictor = official_defs.build_predictor(defs, args, base)
    ctx.update(defs=defs, args=args, predictor=predictor, evaluator=defs["EpisodeEvaluator"](args, base),
               predictor_init_s=time.perf_counter() - t0, official_sha256=dict(defs["sha256"]))
    print(f"MMESG_CONTEXT variant={variant} max_steps={args.max_steps} predictor={type(predictor).__name__} "
          f"init_s={ctx['predictor_init_s']:.1f}", flush=True)
    return ctx


def close_policy_context(ctx: Any) -> None:
    """席位收尾：释放预测器（QwenVL 引擎）与评估器。"""
    if not isinstance(ctx, dict):
        return
    for k in ("predictor", "evaluator"):
        ctx.pop(k, None)
    try:
        import gc

        gc.collect()
        if "torch" in sys.modules:
            torch = sys.modules["torch"]
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
    except Exception:  # noqa: BLE001
        pass


# ── S1：官方叠字视频保留（只新侧打开） ──────────────────────────────────────


class OfficialVideoRejected(ValueError):
    """官方叠字视频核验不过（个数、可解码、帧数、目标目录），不搬入 ``official/``。"""


def official_safe_filename(full_name: str) -> str:
    """与 ``render_official_video.safe_filename`` 同款：去掉 ``/``、``\\``、NUL；超过 255 字节时截断并附整名摘要。

    这里照写一份（6 行）而不跨文件导入，避免依赖并行重构中的重绘工具；两份规则须保持一致。"""
    sanitized = re.sub(r"[/\\\x00]", "_", full_name)
    if sanitized == full_name and len(sanitized.encode()) <= 255:
        return sanitized
    suffix = "__" + hashlib.sha256(full_name.encode()).hexdigest()[:16] + ".mp4"
    stem = sanitized.removesuffix(".mp4").encode()[:255 - len(suffix.encode())].decode(errors="ignore")
    return stem + suffix


def official_video_name(runner: Any, flag: str, task_goal: str) -> str:
    """官方 ``eval_each_episode`` 的文件名格式 ``{env_id}_ep{episode_id}_{flag}_{task_goal}_{difficulty}.mp4``（截断后）。"""
    return official_safe_filename(
        f"{runner.env_id}_ep{runner.episode_id}_{flag}_{task_goal}_{runner.difficulty}.mp4")


def ffmpeg_exe() -> str:
    """与官方 ``imageio.mimsave`` 同源的 ffmpeg：``IMAGEIO_FFMPEG_EXE`` 优先，否则 imageio-ffmpeg 自带二进制。"""
    exe = os.environ.get("IMAGEIO_FFMPEG_EXE")
    if exe:
        return exe
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


def decode_video_frames(path: str | Path, ffmpeg: str | None = None) -> int:
    """完整解码第一路视频流并返回帧数；ffmpeg 退出码非 0 或报任何 error 级消息即 ``OfficialVideoRejected``。"""
    cmd = [ffmpeg or ffmpeg_exe(), "-nostdin", "-hide_banner", "-v", "error", "-i", str(path),
           "-map", "0:v:0", "-f", "framemd5", "-"]
    proc = subprocess.run(cmd, capture_output=True, timeout=600)
    err = proc.stderr.decode(errors="replace").strip()
    if proc.returncode != 0 or err:
        raise OfficialVideoRejected(f"解码失败 rc={proc.returncode}：{err[:300]}")
    return sum(1 for ln in proc.stdout.decode(errors="replace").splitlines() if ln.strip() and not ln.startswith("#"))


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def keep_official_videos(video_dir: str | Path, dst: str | Path, *, expected_frames: int,
                         provenance: dict | None = None, ffmpeg: str | None = None) -> list[str]:
    """把 ``video_dir`` 里官方写出的叠字视频搬进 ``dst``（即 ``<局目录>/official/``）并写 ``provenance.json``。

    搬入前核：恰一个 ``*.mp4``（非符号链接）、完整解码无错、帧数等于 ``expected_frames``（= ``frames_recorded``）、
    ``dst`` 不存在或为空。任一不过抛 ``OfficialVideoRejected``、不搬、不写。通过打印
    ``OFFICIAL_VIDEO=KEPT``，返回搬入后的路径列表（恰 1 个）。``provenance`` 为调用方给的身份、路线、终态等，本函数
    补 ``video``（文件名、sha256、字节数）与 ``frames``（解码帧数、期望帧数、依据）。"""
    video_dir, dst = Path(video_dir), Path(dst)
    mp4s = sorted(video_dir.glob("*.mp4")) if video_dir.is_dir() else []
    if len(mp4s) != 1:
        raise OfficialVideoRejected(f"官方视频应恰 1 个，实际 {len(mp4s)} 个：{[p.name for p in mp4s]}")
    src = mp4s[0]
    if src.is_symlink() or not src.is_file():
        raise OfficialVideoRejected(f"官方视频不是普通文件：{src.name}")
    frames = decode_video_frames(src, ffmpeg)
    if frames != int(expected_frames):
        raise OfficialVideoRejected(f"帧数不符：解码 {frames} != frames_recorded {int(expected_frames)}")
    if dst.is_symlink() or (dst.exists() and (not dst.is_dir() or any(dst.iterdir()))):
        raise OfficialVideoRejected(f"目标目录已存在且非空：{dst}")
    sha, nbytes = _file_sha256(src), src.stat().st_size
    dst.mkdir(parents=True, exist_ok=True)
    target = dst / src.name
    shutil.move(str(src), str(target))
    prov = dict(provenance or {})
    prov["schema"] = PROVENANCE_SCHEMA
    prov["video"] = {"name": target.name, "sha256": sha, "bytes": nbytes}
    frame_info = dict(prov.get("frames") or {})
    frame_info.update(decoded=frames, expected=int(expected_frames), basis=FRAMES_BASIS)
    prov["frames"] = frame_info
    tmp = dst / ".provenance.json.tmp"
    tmp.write_text(json.dumps(prov, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, dst / "provenance.json")
    print(f"OFFICIAL_VIDEO=KEPT source={prov.get('official_source')} frames={frames} sha256={sha[:16]} "
          f"name={target.name}", flush=True)
    return [str(target)]


def episode_counts(tap: EpisodeTap, flag: Any, exc_name: str | None, max_steps: int | None) -> dict:
    """C8 三分计数（按 ``EpisodeTap`` 的记录与官方循环语义推出）。

    官方 ``count > max_steps`` 时先 ``break`` 后不 ``record``：自然超时局最后一步有观测却不进官方视频，记
    ``omitted_timeout_frames=1``（该步若本就缺观测则为 0）。``get_init_obs`` 没返回的局 ``no_frame``。"""
    attempted = int(tap.steps)
    observed = attempted - len(tap.missing_steps)
    no_frame = tap.demo_frames is None
    omitted = int(flag == "timeout" and exc_name is None and max_steps is not None and attempted > int(max_steps)
                  and attempted not in tap.missing_steps)
    frames = 0 if no_frame else int(tap.demo_frames) + 1 + observed - omitted
    return {"steps_attempted": attempted, "steps_observed": observed, "frames_recorded": frames,
            "omitted_timeout_frames": omitted, "no_frame": no_frame}


def _status_of(flag: Any, error: str | None, exc_name: str | None) -> tuple[str, str | None]:
    if exc_name == "StepCapReached":
        return "timeout", error
    if error is None:
        return map_flag(flag)
    return "error", error


def _finish_official(captured: dict, runner: Any, tap: EpisodeTap, video_dir: Path, archive_dir: Path | None, *,
                     flag: Any, error: str | None, exc_name: str | None, counts: dict, provenance: dict) -> dict:
    """``keep_official`` 打开时的收尾（在删 ``video_dir`` 之前调用）；本函数不抛异常，失败一律记进返回值。"""
    out: dict[str, Any] = {"official_videos": [], "official_source": "none", "official_save_error": None}
    rec = captured.get("recorder")
    if rec is None:
        if captured.get("init_started") and tap.demo_frames is not None:
            # 已取到 reset 帧但官方 init_episode 没交出录像器：部分帧不成片，只记原因（不冒充完整视频）
            out["official_source"] = "partial"
            out["official_save_error"] = (f"init_episode 中途失败：已取 {tap.demo_frames + 1} 帧 reset 画面，"
                                          f"官方录像器未交出，不成片；{error or ''}")[:800]
        else:
            out["official_save_error"] = f"init_episode 之前或其中取初始观测失败，一帧未录；{error or ''}"[:800]
        return out
    try:
        status, _ = _status_of(flag, error, exc_name)
        has_mp4 = video_dir.is_dir() and any(video_dir.glob("*.mp4"))
        source = "official"
        if not has_mp4:
            if exc_name is None and flag != "unknown":
                raise OfficialVideoRejected(f"官方正常收尾（flag={flag}）却没有写出 mp4")
            label = "timeout" if exc_name == "StepCapReached" else ("unknown" if flag == "unknown" else "error")
            name = official_video_name(runner, label, captured.get("task_goal"))
            try:
                rec.save_video(name)  # 官方实例自己的 save_video（R3：不复制、不改写）
            except Exception as e:  # noqa: BLE001
                raise OfficialVideoRejected(f"补存 save_video 失败：{type(e).__name__}: {e}") from e
            source = "official-salvaged"
        if archive_dir is None:
            raise OfficialVideoRejected("没有局目录（archive_dir=None），无处保留")
        prov = dict(provenance)
        prov.update(official_source=source,
                    terminal={"status": status, "success_flag": flag, "error": error, "exception": exc_name},
                    frames={k: counts[k] for k in ("steps_attempted", "steps_observed", "frames_recorded",
                                                   "omitted_timeout_frames")} | {"demo_frames": tap.demo_frames})
        out["official_videos"] = keep_official_videos(video_dir, Path(archive_dir) / OFFICIAL_VIDEO_SUBDIR,
                                                      expected_frames=counts["frames_recorded"], provenance=prov)
        out["official_source"] = source
    except Exception as e:  # noqa: BLE001 只记原因，原始帧照留
        out["official_save_error"] = f"{type(e).__name__}: {e}"[:800]
        print(f"OFFICIAL_VIDEO=REJECTED reason={out['official_save_error'][:200]!r}", flush=True)
    return out


def run_official_episode(ctx: dict, runner: Any, tap: EpisodeTap, *, dataset: str, episode_tag: str,
                         scratch: Path, archive_dir: Path | None, recorder: Any = None,
                         keep_official: Any = _UNSET, official_provenance: Any = _UNSET) -> dict:
    """两侧共用：在 ``ctx`` 的官方评估器上跑一局 ``eval_each_episode``，收住异常、清理临时目录，返回终态字典。

    ``keep_official`` 不传（原侧）时行为与返回值与此前逐字节相同；传真值时保留官方叠字视频（见模块文档串 S1），
    ``official_provenance`` 为写进 ``provenance.json`` 的身份、路线等（dict）。"""
    keep = keep_official is not _UNSET and bool(keep_official)
    predictor, evaluator = ctx["predictor"], ctx["evaluator"]
    ctx["episode"] = {"tap": tap, "clients": [], "recorder": recorder, "timing": {}}
    video_dir = scratch / "official-video"
    qbase = qwen_begin(predictor, scratch, dataset, episode_tag)
    error = None
    exc_name = None
    flag = None
    captured: dict[str, Any] = {}
    official: dict[str, Any] = {}
    counts: dict[str, Any] = {}
    had_attr = "init_episode" in vars(evaluator)
    saved_attr = vars(evaluator).get("init_episode")
    if keep:
        orig_init = evaluator.init_episode

        def init_episode_capture(env_runner, epstate, video_save_dir):
            captured["init_started"] = True
            out = orig_init(env_runner, epstate, video_save_dir)
            captured["task_goal"], captured["recorder"] = out
            return out

        evaluator.init_episode = init_episode_capture
    t0 = time.perf_counter()
    try:
        flag = evaluator.eval_each_episode(runner, predictor, video_dir)
    except Exception as e:  # noqa: BLE001 与官方 evaluate 的整局兜底同样记 error
        exc_name = type(e).__name__
        print(f"Error evaluating episode {episode_tag}: {e}")
        flag, error = "error", f"{exc_name}: {e}"[:800]
    finally:
        if keep:
            if had_attr:
                evaluator.init_episode = saved_attr
            else:
                vars(evaluator).pop("init_episode", None)
        for c in ctx["episode"]["clients"]:
            c.close()
        qlog = qwen_end(predictor, qbase, archive_dir)
        if keep:
            counts = episode_counts(tap, flag, exc_name, getattr(ctx.get("args"), "max_steps", None))
            prov = dict(official_provenance) if isinstance(official_provenance, dict) else {}
            prov.setdefault("official_sha256", dict(ctx.get("official_sha256") or {}))
            official = _finish_official(captured, runner, tap, video_dir, archive_dir, flag=flag, error=error,
                                        exc_name=exc_name, counts=counts, provenance=prov)
        shutil.rmtree(video_dir, ignore_errors=True)  # 官方叠字 mp4 不交付（keep 时已先搬入 official/）
    wall = time.perf_counter() - t0
    status, error = _status_of(flag, error, exc_name)
    env_exc = getattr(runner, "last_exception", None)
    env_exc_s = None if env_exc is None else f"{type(env_exc).__name__}: {env_exc}"[:800]
    infra = classify_infra(error, env_exc_s) if status == "error" else None
    timing = dict(ctx["episode"].get("timing") or {})
    if "per_msg" in timing:  # 新侧录制客户端的逐消息计时：与 mme_client 同口径汇总
        timing = load_sibling("mme_client").summarize_timing(timing)
    timing["episode_s"] = wall
    ctx["episode"] = None
    res = {"status": status, "task_success": status == "success", "steps": tap.steps, "error": error,
           "success_flag": flag, "decisions": tap.decisions, "infra": infra is not None, "infra_reason": infra,
           "env_exception": env_exc_s, "exception": exc_name, "qwen_log": qlog, "timing": timing,
           "official_sha256": dict(ctx.get("official_sha256") or {})}
    if keep:
        res.update(counts)
        res.update(official)
    return res


def run_episode(session, identity: dict, conn_info: dict, recorder) -> dict:
    """env_client 调用入口：一局 GroundSG（新侧）。``session`` 为已 build 的 EnvSession。"""
    ctx = conn_info.get("policy_context")
    if not isinstance(ctx, dict) or "evaluator" not in ctx:
        raise RuntimeError("mmesg 需要 SeatRunner 先以 make_policy_context 建好 policy_context")
    variant = conn_info.get("mme_variant")
    if variant != ctx["variant"]:
        raise ValueError(f"conn_info mme_variant={variant!r} 与 policy_context {ctx['variant']!r} 不一致")
    max_steps = int(conn_info["max_steps"])
    if int(ctx["args"].max_steps) != max_steps:
        raise ValueError(f"conn_info max_steps={max_steps} 与 policy_context {ctx['args'].max_steps} 不一致")
    dataset = conn_info.get("dataset")
    tag = conn_info.get("episode_tag") or f"{identity.get('key')}.a1"
    attempt = attempt_of(tag)
    tpath = trace_location(conn_info, recorder)
    route = f"mmesg/{variant}/new"
    ident = {k: identity.get(k) for k in ("task", "tier", "seed", "source_episode", "builder_episode", "key")}
    ident["dataset"] = dataset
    ident["attempt"] = attempt  # C6：= 局目录名 <key>.a<N> 的 N（账本 accepted_attempt_id 对应的尝试号）
    trace = (trace_writer.TraceWriter(tpath, route=route, identity=ident, max_steps=max_steps)
             if tpath is not None else None)
    tap = EpisodeTap(trace, missing_step_contract=True)
    runner = SessionRunner(session, tag, ctx["defs"]["pack_state"], tap,
                           official_episode_id=official_episode_id(identity, tag))
    scratch, own_scratch = episode_scratch(conn_info.get("trace_dir"))
    archive_dir = tpath.parent if tpath is not None else None
    prov = {"identity": dict(ident), "route": route, "dataset": dataset, "attempt": attempt, "episode_tag": tag,
            "official_episode_id": runner.episode_id, "official_sha256": dict(ctx.get("official_sha256") or {})}
    try:
        res = run_official_episode(ctx, runner, tap, dataset=dataset, episode_tag=tag, scratch=scratch,
                                   archive_dir=archive_dir, recorder=recorder, keep_official=True,
                                   official_provenance=prov)
    finally:
        if own_scratch:
            shutil.rmtree(scratch, ignore_errors=True)
    demo = (getattr(session, "timing", None) or {}).get("demo_frames", tap.demo_frames)
    if res.get("no_frame"):
        demo = 0  # C3：无帧 error 局 demo_frames 记 0
    if trace is not None:
        extra = {k: res[k] for k in ("steps_attempted", "steps_observed", "frames_recorded", "omitted_timeout_frames")}
        if res.get("no_frame"):
            extra["no_frame"] = True
        # C3：terminal_reason 取终态（strict-cap 为 timeout、unknown 为 error），官方原返回值另记 success_flag
        trace.close(status=res["status"], terminal_reason=res["status"], side="new", demo_frames=demo,
                    decisions=res["decisions"], success_flag=res["success_flag"],
                    official_source=res["official_source"],
                    official_videos=[Path(p).name for p in res["official_videos"]], **extra)
    res.update(side="new", demo_frames=demo, max_steps=max_steps, policy_variant=variant,
               trace_path=str(tpath) if tpath is not None else None)
    return res


def attempt_of(episode_tag: str) -> int:
    """局目录名 ``<key>.a<N>`` 的尝试号 N；不含 ``.a<N>`` 时为 1（与 ``official_episode_id`` 同口径）。"""
    m = re.search(r"\.a(\d+)$", str(episode_tag))
    return int(m.group(1)) if m else 1
