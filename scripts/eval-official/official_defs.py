#!/usr/bin/env python3
"""从官方源码按名摘取定义（1003-oracle-subgoal-groundsg-eval-plan.md 第二部分 1.3）。

官方 MME 客户端 ``third_party/mme-vla/examples/robomme/eval.py`` 经 ``subgoal_predictor.py`` 无条件导入 gemini
（``google.generativeai``）与 memer 模块，评估环境里都没装，所以 GroundSG 的新侧（``mmesg_client.py``）与原侧
（``official_hard_runner.py``）都**不整模块 import** 官方文件，而是用 ``extract_defs`` 从源文件里取出指定顶层
函数、类、单目标赋值的**原文**并执行；模块其余部分（import 行、模块级副作用）不执行，依赖由调用方经 ``extra``
注入。返回的命名空间就是这些定义的 globals，之后往里补名字（如延迟导入的 ``PtEngine``）对已取出的函数同样生效。

官方模块头部有三项环境设置（``eval.py`` 与 ``subgoal_prediction/qwenvl/api.py`` 顶部），摘取时不会被带走，由
``apply_official_env`` 负责；QwenVL 的离线运行约束由 ``apply_qwen_runtime_env`` 负责。

``load_groundsg`` 是两侧共用的装配：按变体只取需要的类（Oracle 不读 qwenvl/api.py、不导入 swift；QwenVL 只取
``QwenVLSubgoalPredictor`` 与 ``Qwen3VLModel``，不取 Gemini／MemER）。

官方源码位置：环境变量 ``SGEVAL_THIRD_PARTY``（指向某个检出的 ``third_party``；worktree 里子模块目录为空时测试
用它只读引用主检出），否则取本仓库 ``third_party``。
"""
from __future__ import annotations

import ast
import collections
import dataclasses
import hashlib
import json
import os
import pprint
import re
import shutil
import sys
import time
import types
from pathlib import Path
from typing import Any, List, Optional, Tuple

import numpy as np

REPO = Path(__file__).resolve().parents[2]
#: 两个变体（与 env_client.MME_VARIANTS 同值）
VARIANT_ORACLE = "ground-sg-oracle"
VARIANT_QWENVL = "ground-sg-qwenvl"
VARIANTS = (VARIANT_ORACLE, VARIANT_QWENVL)
_SEQ = 0
#: 官方模块头部的三项环境设置（eval.py 与 qwenvl/api.py 顶部原样）
OFFICIAL_ENV = {"IMAGE_MAX_TOKEN_NUM": "256", "VIDEO_MAX_TOKEN_NUM": "64", "FPS_MAX_FRAMES": "10"}
#: QwenVL 运行约束（ms-swift 默认走 ModelScope；本计划一律离线走 HF 缓存）
QWEN_RUNTIME_ENV = {"USE_HF": "1", "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"}


def third_party_root() -> Path:
    """官方第三方源码根：``SGEVAL_THIRD_PARTY`` 优先，否则本仓库 ``third_party``。"""
    env = os.environ.get("SGEVAL_THIRD_PARTY")
    return Path(env).resolve() if env else REPO / "third_party"


def official_robomme_dir() -> Path:
    """官方 ``examples/robomme`` 目录；缺 ``eval.py`` 即报错（不静默跳过）。"""
    d = third_party_root() / "mme-vla" / "examples" / "robomme"
    if not (d / "eval.py").is_file():
        raise FileNotFoundError(f"官方 MME 源码不在：{d}/eval.py（子模块未初始化？可设 SGEVAL_THIRD_PARTY）")
    return d


def file_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def extract_defs(path: str | Path, names: list[str], extra: dict | None = None) -> dict:
    """从源文件用 ast 取出指定顶层函数／类／单目标赋值的原文并执行，返回命名空间。

    * 只取 ``names`` 里列出的顶层 ``def``／``async def``／``class``（含装饰器）与单目标赋值 ``X = ...``；
      同名多次定义按源码顺序全部取出（与整模块执行时最后一个生效相同）；
    * 名字找不到抛 ``KeyError``；
    * 不执行模块其余部分（import 行、模块级副作用），依赖由 ``extra`` 注入（基础名 ``np``、``Any`` 等已预置）；
    * 命名空间记 ``__source_path__``、``__source_sha256__``（整文件字节的 sha256）。
    """
    path = Path(path)
    raw = path.read_bytes()
    src = raw.decode("utf-8")
    tree = ast.parse(src, filename=str(path))
    body = []
    found: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name in names:
            body.append(node)
            found.add(node.name)
        elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            if node.targets[0].id in names:
                body.append(node)
                found.add(node.targets[0].id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
            if node.target.id in names:
                body.append(node)
                found.add(node.target.id)
    missing = sorted(set(names) - found)
    if missing:
        raise KeyError(f"{path} 里找不到 {missing}")
    # 命名空间挂在一个独立的模块对象上并登记进 sys.modules（dataclass 等按 __module__ 回查模块）；
    # 模块名带 _official_ 前缀与序号，不与真实模块（eval、utils 等）同名
    global _SEQ
    _SEQ += 1
    mod = types.ModuleType(f"_official_{path.stem}_{_SEQ}")
    mod.__file__ = str(path)
    sys.modules[mod.__name__] = mod
    ns: dict[str, Any] = mod.__dict__
    ns.update({
        "__builtins__": __builtins__,
        "np": np, "Any": Any, "Optional": Optional, "Tuple": Tuple, "List": List, "Path": Path,
        "os": os, "re": re, "json": json, "time": time, "shutil": shutil, "collections": collections,
        "dataclasses": dataclasses, "pprint": pprint,
    })
    ns.update(extra or {})
    exec(compile(ast.Module(body=body, type_ignores=[]), str(path), "exec"), ns)  # noqa: S102 只执行官方定义原文
    ns["__source_path__"] = str(path)
    ns["__source_sha256__"] = hashlib.sha256(raw).hexdigest()
    return ns


def apply_official_env() -> dict:
    """官方 eval.py／qwenvl/api.py 头部的三项环境设置（原样覆盖写）。返回写入的键值。"""
    for k, v in OFFICIAL_ENV.items():
        os.environ[k] = v
    return dict(OFFICIAL_ENV)


def apply_qwen_runtime_env() -> dict:
    """QwenVL 运行约束：``USE_HF=1``、``HF_HUB_OFFLINE=1``、``TRANSFORMERS_OFFLINE=1``（导入 swift 之前调用）。"""
    for k, v in QWEN_RUNTIME_ENV.items():
        os.environ[k] = v
    return dict(QWEN_RUNTIME_ENV)


def import_swift_names() -> dict:
    """真实的 ``swift.llm`` 三个名字（只在 QwenVL 变体构造预测器时调用；先设运行约束再导入）。"""
    apply_qwen_runtime_env()
    apply_official_env()
    from swift.llm import InferRequest, PtEngine, RequestConfig

    return {"PtEngine": PtEngine, "InferRequest": InferRequest, "RequestConfig": RequestConfig}


#: 各官方文件要摘取的名字
UTILS_NAMES = ["TASK_WITH_VIDEO_DEMO", "TASK_NAME_LIST", "SUBGOAL_TYPES", "pack_buffer", "check_args", "EpisodeState",
               "RolloutRecorder"]
ENV_RUNNER_NAMES = ["pack_state", "EnvRunner"]
EVAL_NAMES = ["Args", "EpisodeEvaluator"]
PREDICTOR_NAMES = {
    VARIANT_ORACLE: ["SubgoalPredictorBase", "OracleSubgoalPredictor", "build_subgoal_predictor"],
    VARIANT_QWENVL: ["SubgoalPredictorBase", "QwenVLSubgoalPredictor", "build_subgoal_predictor"],
}


def load_groundsg(variant: str, *, env_runner_extra: dict | None = None, ws_module: Any = None,
                  qwen_extra: dict | None = None, with_env_runner: bool = True) -> dict:
    """两侧共用的官方定义装配，返回 ``{"utils","env_runner","predictor","qwen","eval","sha256","EnvRunner",...}``。

    * ``env_runner_extra``：给 ``env_runner.py`` 的依赖（原侧传真实 ``BenchmarkEnvBuilder``；测试传替身）。
      ``with_env_runner=False`` 时不取 ``EnvRunner``（新侧不用它，只取 ``pack_state``），子目标预测器与评估器
      里的 ``EnvRunner`` 注解以占位类代替（注解在定义时求值，不影响行为）。
    * ``ws_module``：注入为 ``eval.py`` 的 ``_websocket_client_policy``（须有 ``MMEVLAWebsocketClientPolicy``）；
      ``None`` 时用真实 ``openpi_client.websocket_client_policy``。
    * ``qwen_extra``：QwenVL 变体时注入 ``qwenvl/api.py`` 的 ``PtEngine``／``InferRequest``／``RequestConfig``；
      ``None`` 时不注入，构造预测器前须由调用方补（``import_swift_names``）。Oracle 变体不读 qwenvl/api.py。
    """
    if variant not in VARIANTS:
        raise ValueError(f"variant={variant!r} 不是 {VARIANTS} 之一")
    d = official_robomme_dir()
    apply_official_env()
    import cv2
    import imageio

    utils = extract_defs(d / "utils.py", UTILS_NAMES, {"cv2": cv2, "imageio": imageio})
    er_names = ENV_RUNNER_NAMES if with_env_runner else ["pack_state"]
    er_extra = {"TASK_NAME_LIST": utils["TASK_NAME_LIST"]}
    er_extra.update(env_runner_extra or {})
    env_runner = extract_defs(d / "env_runner.py", er_names, er_extra)
    runner_cls = env_runner.get("EnvRunner") or type("EnvRunner", (), {"__doc__": "注解占位（新侧不用官方 EnvRunner）"})
    qwen = None
    pred_extra: dict[str, Any] = {"EnvRunner": runner_cls, "EpisodeState": utils["EpisodeState"],
                                  "SUBGOAL_TYPES": utils["SUBGOAL_TYPES"],
                                  "TASK_WITH_VIDEO_DEMO": utils["TASK_WITH_VIDEO_DEMO"]}
    if variant == VARIANT_QWENVL:
        qwen = extract_defs(d / "subgoal_prediction" / "qwenvl" / "api.py", ["Qwen3VLModel"],
                            {"imageio": imageio, **(qwen_extra or {})})
        pred_extra["Qwen3VLModel"] = qwen["Qwen3VLModel"]
    predictor = extract_defs(d / "subgoal_predictor.py", PREDICTOR_NAMES[variant], pred_extra)
    if ws_module is None:
        from openpi_client import websocket_client_policy as ws_module  # noqa: N813 与官方同名
    ev = extract_defs(d / "eval.py", EVAL_NAMES, {
        "_websocket_client_policy": ws_module, "pack_buffer": utils["pack_buffer"], "check_args": utils["check_args"],
        "TASK_NAME_LIST": utils["TASK_NAME_LIST"], "TASK_WITH_VIDEO_DEMO": utils["TASK_WITH_VIDEO_DEMO"],
        "SUBGOAL_TYPES": utils["SUBGOAL_TYPES"], "EpisodeState": utils["EpisodeState"],
        "RolloutRecorder": utils["RolloutRecorder"], "EnvRunner": runner_cls,
        "build_subgoal_predictor": predictor["build_subgoal_predictor"],
        "SubgoalPredictorBase": predictor["SubgoalPredictorBase"],
    })
    sha = {"utils.py": utils["__source_sha256__"], "env_runner.py": env_runner["__source_sha256__"],
           "subgoal_predictor.py": predictor["__source_sha256__"], "eval.py": ev["__source_sha256__"]}
    if qwen is not None:
        sha["subgoal_prediction/qwenvl/api.py"] = qwen["__source_sha256__"]
    return {"variant": variant, "dir": str(d), "utils": utils, "env_runner": env_runner, "predictor": predictor,
            "qwen": qwen, "eval": ev, "sha256": sha, "EnvRunner": env_runner.get("EnvRunner"),
            "pack_state": env_runner["pack_state"], "Args": ev["Args"], "EpisodeEvaluator": ev["EpisodeEvaluator"]}


def make_args(defs: dict, *, variant: str, host: str, port: int, max_steps: int, adapter_path: str | None = None,
              save_dir: str = "runs/evaluation") -> Any:
    """按变体构造官方 ``Args``：``subgoal_type="grounded_subgoal"``，``use_oracle`` 与 ``use_qwenvl`` 恰一个为真
    （构造后断言；官方 ``build_subgoal_predictor`` 多开时静默取高优先级，这里不允许），再过官方 ``check_args``。"""
    kw: dict[str, Any] = dict(host=host, port=int(port), max_steps=int(max_steps), save_dir=save_dir,
                              subgoal_type="grounded_subgoal", use_oracle=variant == VARIANT_ORACLE,
                              use_qwenvl=variant == VARIANT_QWENVL)
    if variant == VARIANT_QWENVL:
        if not adapter_path:
            raise ValueError("ground-sg-qwenvl 必须给 qwenvl_groundSG_adapter_path")
        kw["qwenvl_groundSG_adapter_path"] = str(adapter_path)
    args = defs["Args"](**kw)
    assert_one_predictor(args)
    defs["utils"]["check_args"](args)
    return args


def assert_one_predictor(args: Any) -> None:
    """``use_oracle`` 与 ``use_qwenvl`` 恰有一个为真，且 gemini／memer 都不开。"""
    flags = (bool(args.use_oracle), bool(args.use_qwenvl))
    if sum(flags) != 1 or getattr(args, "use_gemini", False) or getattr(args, "use_memer", False):
        raise AssertionError(f"use_oracle={args.use_oracle} use_qwenvl={args.use_qwenvl} "
                             f"use_gemini={getattr(args, 'use_gemini', None)} use_memer={getattr(args, 'use_memer', None)}"
                             "：必须恰有 oracle／qwenvl 之一")


def build_predictor(defs: dict, args: Any, save_dir: str | Path) -> Any:
    """官方 ``build_subgoal_predictor``（构造前再断言一次互斥）。QwenVL 先设离线运行约束，未注入 swift 名字时
    此处导入真实 swift；``attn_impl='flash_attention_2'`` 等引擎参数一律取官方原文，不改。"""
    assert_one_predictor(args)
    if args.use_qwenvl:
        apply_qwen_runtime_env()
        if "PtEngine" not in defs["qwen"]:
            defs["qwen"].update(import_swift_names())
    return defs["predictor"]["build_subgoal_predictor"](args, Path(save_dir))


def canonical_bytes(obj: Any) -> bytes:
    """请求的规范化字节（两侧同一函数）：dict 按键排序；数组记 dtype、shape 与 C 连续字节；字符串 UTF-8。"""
    out = bytearray()

    def put(x: Any) -> None:
        if isinstance(x, dict):
            out.extend(b"{")
            for k in sorted(x, key=str):
                put(str(k))
                out.extend(b":")
                put(x[k])
                out.extend(b",")
            out.extend(b"}")
        elif isinstance(x, (list, tuple)):
            out.extend(b"[")
            for v in x:
                put(v)
                out.extend(b",")
            out.extend(b"]")
        elif isinstance(x, (bytes, bytearray)):
            out.extend(b"b%d:" % len(x) + bytes(x))
        elif isinstance(x, str):
            b = x.encode("utf-8")
            out.extend(b"s%d:" % len(b) + b)
        elif x is None or isinstance(x, (bool, int, float)):
            out.extend(("p:" + repr(x)).encode())
        else:
            a = np.ascontiguousarray(np.asarray(x))
            out.extend(f"a:{a.dtype.str}|{a.shape}|".encode() + a.tobytes())

    put(obj)
    return bytes(out)


def ws_shim(factory) -> Any:
    """``eval.py`` 里 ``_websocket_client_policy`` 的替身模块：``MMEVLAWebsocketClientPolicy(host, port)`` → ``factory``。"""
    return types.SimpleNamespace(MMEVLAWebsocketClientPolicy=factory)
