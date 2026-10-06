#!/usr/bin/env python3
"""PonderPounce 服务外壳：在每个 ACTION 回包里附上模型自己的子目标（1005-eval-video-phase2-all-models-rerun-plan.md
第二部分一节「S5 PonderPounce 新侧」、八节 2.2）。

上游 ``ponderpounce.eval.robomme_server.PonderPounceRoboMMEServer``（子模块锁定 ``723df357``）把 System 2 产出的
子目标文本只写进服务端日志，协议里不回传。本外壳子类化原类（原文件一行不改），只覆写两个方法：

- ``_fire_s1``：调父类之前，从本局 ``ep.cognitions`` 里取「到 ``now`` 为止已可见（``ready_at_ns <= now``）且子目标
  非空」的最新一条，更新本局「最近一个已可见且非空的子目标」（没有新的就沿用旧值，本局开头为 ``None``）；
  父类生成 ``ep.chunk`` 之后把这个值挂到 chunk 上。默认节拍（Ponder／Pounce 各 1000 ms）下每次 Pounce 触发之间恰
  有一条 cognition 变为可见，与只看 ``_visible_cognition(ep, now)`` 等价；节拍不等时也不会漏掉夹在两次触发之间
  变为可见的子目标。
- ``_dispense``：父类结果原样保留，另加 ``"subgoal": <当前 chunk 上的子目标>``；没有 chunk（手臂 hold）时为
  ``None``。chunk 用尽后父类重复最后一行动作，子目标同样不变。

外壳不读写随机数发生器、不改 ``cursor``／触发计数／动作，只在 ``Episode``、``Chunk`` 实例上各加一个私有属性
（``_sgeval_subgoal``）。等价性由 ``tests/pipeline/evalx/pp/test_pp_server_wrap.py``（``PP_SERVER_ACTION_EQ``）钉死。

第三阶段（1006 计划八.11／八.12 第 5、7 条；接口冻结说明 2.2、五节「服务外壳回包审计键」）：

- 每个 ACTION 回包另加 ``_sgeval_audit``：``channels`` 为 System 1 本局实际用的 prompt（``Task: …;\nAction: ``
  原文、父类算出的 token id 与 mask、tokenizer 名、是否填满／截断；``text_reconstructed=true``：原文是按同一
  task_text 重新拼出的），``server_final_text`` 同该原文，``pp_generation`` 为自上次回包以来 System 2 每次 ``fire``
  一块的列表（reasoning、子目标原文与 token、kind、gate 分数、是否提交、是否回滚、上下文长度增量；键名对齐客户端
  语言账本，见 ``generation_blocks``；没有 fire 为 None）。System 2 的观察挂在本局上下文实例的 ``fire``／``_restore`` 上（调用原方法、原样
  返回）；第一次 Ponder 时父类才新建上下文，外壳在父类 ``_fire_s2`` 期间把模块里的上下文类临时换成「建好即挂观察」
  的工厂，返回后立即还原。外壳只观察真实结果：不多推理、不多抽随机数、不改动作。环境变量 ``SGEVAL_AUDIT=0`` 时
  不挂观察、不加审计键（``OBS_EQ`` 对照）。
- 外壳自用参数 ``--sgeval-metadata-out <path>``：启动时从 argv 摘掉（其余原样交给 vla_eval），写服务元数据
  ``server-metadata-<port>.json``（``policy_seed`` 即 ``--args.seed``、``argv``、``pid``、``port``）。

启动（参数与原服务完全相同，cwd 在第三方 PonderPounce 目录，脚本用绝对路径）::

    python /abs/path/scripts/eval-official/pp_server_wrap.py --args.seed 0 --args.checkpoint_path ... --port 8000

``python -m`` 会把 cwd 放在 ``sys.path`` 首位，而按路径运行脚本放的是脚本目录；为了与原命令的导入环境一致，
入口先把本目录移出 ``sys.path``、把 cwd 放到首位，再导入 ``ponderpounce``。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

#: 回包里新增的键（客户端 ``pp_client.TracedConnection.act`` 按此读取）
SUBGOAL_KEY = "subgoal"
#: 挂在 Episode／Chunk 实例上的私有属性名
_ATTR = "_sgeval_subgoal"


def _prepare_sys_path() -> None:
    """与 ``python -m ponderpounce.eval.robomme_server`` 的 ``sys.path`` 对齐：cwd 在首位，本目录不在路径里。"""
    here = str(Path(__file__).resolve().parent)
    sys.path[:] = [p for p in sys.path if p and str(Path(p).resolve()) != here]
    cwd = os.getcwd()
    if cwd not in sys.path:
        sys.path.insert(0, cwd)


if __name__ == "__main__":  # pragma: no cover - 只在作为脚本启动时调整
    _prepare_sys_path()

from ponderpounce.eval.robomme_server import PonderPounceRoboMMEServer  # noqa: E402

#: 服务回包审计键（接口冻结说明五节）；SGEVAL_AUDIT=0 时不加
AUDIT_KEY = "_sgeval_audit"
ENV_AUDIT = "SGEVAL_AUDIT"
#: 外壳自用参数（启动时从 argv 里摘掉，其余原样交给 vla_eval 的 run_server）
METADATA_FLAG = "--sgeval-metadata-out"
#: 挂在 Episode 实例上的私有属性：本次回包之前累积的 System 2 生成块（每次回包后清空）
_GEN_ATTR = "_sgeval_generations"


def audit_enabled() -> bool:
    """``SGEVAL_AUDIT`` 缺省开；为 ``0`` 时外壳不挂观察、不加审计键（``OBS_EQ`` 对照）。"""
    return os.environ.get(ENV_AUDIT, "1") != "0"


def latest_visible_subgoal(cognitions: Any, now: int, previous: str | None) -> str | None:
    """``cognitions`` 中 ``ready_at_ns <= now`` 且 ``subgoal`` 非空的最新一条的文本；没有则返回 ``previous``。"""
    for cog in reversed(list(cognitions)):
        if cog.ready_at_ns <= now and cog.subgoal:
            return str(cog.subgoal)
    return previous


def _tolist(x: Any) -> list | None:
    if x is None:
        return None
    try:
        return [int(v) for v in (x.tolist() if hasattr(x, "tolist") else list(x))]
    except Exception:  # noqa: BLE001 观察失败不影响服务
        return None


class _S2Watch:
    """System 2 上下文（``SoftS2SessionContext``）的只读观察：包住实例的 ``fire`` 与 ``_restore``，原样调用、原样返回，
    记下本次真实生成结果（reasoning、子目标、token、gate 分数）、上下文长度增量与回滚次数。"""

    def __init__(self, ctx: Any, sink: list):
        self.ctx, self.sink = ctx, sink
        self.restores = 0
        self.fire_index = 0
        orig_fire, orig_restore = ctx.fire, getattr(ctx, "_restore", None)

        def fire(*a, **k):
            before = getattr(ctx, "_context_len", None)
            prefix_restore = getattr(ctx, "_prefix_snapshot", None) is not None
            self.restores = 0
            result = orig_fire(*a, **k)
            after = getattr(ctx, "_context_len", None)
            rollbacks = max(0, self.restores - (1 if prefix_restore else 0))
            sg_tokens = getattr(result, "subgoal_tokens", None)
            self.sink.append({
                "fire_index": self.fire_index,
                "subgoal_text": getattr(result, "subgoal_text", None),
                "reasoning_text": getattr(result, "reasoning_text", None),
                "subgoal_tokens": _tolist(sg_tokens),
                "kind": getattr(result, "kind", None),
                "gate_score": None if getattr(result, "gate_score", None) is None else float(result.gate_score),
                "n_input_frames": getattr(result, "n_input_frames", None),
                "committed": sg_tokens is not None,
                "rolled_back": rollbacks > 0,
                "context_len_before": before,
                "context_len_after": after,
                "context_delta": (after - before) if isinstance(before, int) and isinstance(after, int) else None,
            })
            self.fire_index += 1
            return result

        ctx.fire = fire
        if callable(orig_restore):
            def restore(*a, **k):
                self.restores += 1
                return orig_restore(*a, **k)
            ctx._restore = restore


class SubgoalReportingServer(PonderPounceRoboMMEServer):
    """原类 + ACTION 回包附 ``subgoal``（与审计键）；动作、随机数、游标与触发节拍与原类逐项相同。"""

    def _fire_s2(self, ep, obs, now: int) -> None:
        if not audit_enabled():
            return super()._fire_s2(ep, obs, now)
        sink = getattr(ep, _GEN_ATTR, None)
        if sink is None:
            sink = []
            setattr(ep, _GEN_ATTR, sink)
        if ep.s2_context is not None:
            return super()._fire_s2(ep, obs, now)
        # 本局第一次 Ponder：父类在 _fire_s2 里新建上下文后立即 fire。临时把模块里的上下文类换成「建好即挂观察」的
        # 工厂（构造参数原样转交，返回原类实例），父类返回后立即还原；不多建、不多调。
        import ponderpounce.eval.robomme_server as rs

        orig_cls = rs.SoftS2SessionContext

        def factory(*a, **k):
            ctx = orig_cls(*a, **k)
            _S2Watch(ctx, sink)
            return ctx

        rs.SoftS2SessionContext = factory
        try:
            return super()._fire_s2(ep, obs, now)
        finally:
            rs.SoftS2SessionContext = orig_cls

    def _fire_s1(self, ep, obs, now: int) -> None:
        current = latest_visible_subgoal(ep.cognitions, now, getattr(ep, _ATTR, None))
        setattr(ep, _ATTR, current)
        super()._fire_s1(ep, obs, now)
        if ep.chunk is not None:
            setattr(ep.chunk, _ATTR, current)

    def _dispense(self, ep, obs):
        action = super()._dispense(ep, obs)
        subgoal = getattr(ep.chunk, _ATTR, None) if ep.chunk is not None else None
        out = dict(action)
        out[SUBGOAL_KEY] = subgoal
        if audit_enabled():
            out[AUDIT_KEY] = self._audit_block(ep)
        return out

    def _audit_block(self, ep) -> dict:
        """S1 prompt（本局 session 上父类真实算出的 token id／mask）+ 自上次回包以来的 S2 完整生成块。"""
        s = ep.session
        ids, mask = getattr(s, "s1_prompt_ids", None), getattr(s, "s1_prompt_mask", None)
        text = None
        if ids is not None:
            try:
                from ponderpounce.pi05.prompt import build_pi0_prompt

                text = build_pi0_prompt(getattr(s, "task_text", None) or "", None)
            except Exception:  # noqa: BLE001 观察失败不影响服务
                text = None
        mask_l = _tolist(mask)
        tok = getattr(self, "_s1_tokenizer", None)
        channels = [] if ids is None else [{
            "channel": "task", "text": text, "token_ids": _tolist(ids), "mask": mask_l,
            "tokenizer": getattr(tok, "name_or_path", None) or (type(tok).__name__ if tok is not None else None),
            # 右侧补齐到 max_token_len 且 truncation=True：mask 全为 1 表示填满（可能被截断）
            "truncated": None if mask_l is None else bool(mask_l) and all(mask_l),
            # text 是用 build_pi0_prompt 按同一 task_text 重新拼出的（token_ids／mask 才是真实截获）
            "text_reconstructed": True}]
        gens = getattr(ep, _GEN_ATTR, None)
        fires = list(gens) if gens else []
        if gens:
            gens.clear()
        return {"channels": channels, "server_final_text": text,
                "pp_generation": generation_blocks(fires, task_text=getattr(s, "task_text", None),
                                                   active_subgoal=getattr(ep, "active_subgoal", None),
                                                   n_s2_fires=getattr(ep, "n_s2_fires", None),
                                                   n_s1_fires=getattr(ep, "n_s1_fires", None))}


def generation_blocks(fires: list, *, task_text: Any = None, active_subgoal: Any = None, n_s2_fires: Any = None,
                      n_s1_fires: Any = None) -> list | None:
    """``pp_generation``：自上次回包以来每次 System 2 ``fire`` 一块（列表；没有 fire 为 ``None``，客户端不开调用）。

    每块保留 ``_S2Watch`` 记下的原字段，另按客户端 ``pp_client.TracedConnection._log_generation`` 读的键补齐：
    ``subgoal_raw``（= ``subgoal_text``，``at [x, y]`` 原文）、``reasoning``（= ``reasoning_text``）、``kind``／``committed``
    （原字段）、``params``（fire 序号、gate 分数、输入帧数、上下文长度增量、是否回滚）。``text`` 不给（上游只保留拆开后的
    reasoning 与子目标，不保留整块解码原文；客户端缺 ``text`` 时取 ``subgoal_raw``）；``context``／``prompt``／``images``
    不给（S2 输入是上下文里累积的 token，上游不保留文字形式，外壳不多解码），客户端记 None。``s2_task_text`` 与
    回包时刻的 ``active_subgoal``／``n_s2_fires``／``n_s1_fires`` 随每块附上。"""
    if not fires:
        return None
    out = []
    for f in fires:
        b = dict(f)
        b.update(subgoal_raw=f.get("subgoal_text"), reasoning=f.get("reasoning_text"),
                 params={k: f.get(k) for k in ("fire_index", "gate_score", "n_input_frames", "context_len_before",
                                               "context_len_after", "context_delta", "rolled_back")},
                 s2_task_text=task_text, active_subgoal=active_subgoal, n_s2_fires=n_s2_fires, n_s1_fires=n_s1_fires)
        out.append(b)
    return out


def split_wrapper_args(argv: list[str]) -> tuple[str | None, list[str]]:
    """从 argv 摘掉外壳自用的 ``--sgeval-metadata-out[=]<path>``，返回 (路径, 其余参数)。"""
    meta, rest, i = None, [], 0
    while i < len(argv):
        a = argv[i]
        if a.startswith(METADATA_FLAG + "="):
            meta = a.split("=", 1)[1]
        elif a == METADATA_FLAG and i + 1 < len(argv):
            meta = argv[i + 1]
            i += 1
        else:
            rest.append(a)
        i += 1
    return meta, rest


def _flag_value(argv: list[str], name: str) -> str | None:
    for i, a in enumerate(argv):
        if a == name and i + 1 < len(argv):
            return argv[i + 1]
        if a.startswith(name + "="):
            return a.split("=", 1)[1]
    return None


def write_metadata(path: str, argv_full: list[str], argv_rest: list[str]) -> dict:
    """服务元数据 ``server-metadata-<port>.json``：policy_seed（即 --args.seed）、argv、pid、port、audit。"""
    seed = _flag_value(argv_rest, "--args.seed")
    port = _flag_value(argv_rest, "--port")
    doc = {"policy": "pp", "policy_seed": int(seed) if seed is not None and seed.lstrip("-").isdigit() else None,
           "argv": list(argv_full), "pid": os.getpid(), "port": int(port) if port and port.isdigit() else port,
           "audit": audit_enabled(), "wrapper": "pp_server_wrap.py"}
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(doc, sort_keys=True, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, p)
    return doc


def main() -> None:
    from vla_eval.model_servers.serve import run_server

    full = list(sys.argv)
    meta, rest = split_wrapper_args(full[1:])
    if meta:
        write_metadata(meta, full, rest)
    sys.argv = [full[0], *rest]
    run_server(SubgoalReportingServer)


if __name__ == "__main__":  # pragma: no cover
    main()
