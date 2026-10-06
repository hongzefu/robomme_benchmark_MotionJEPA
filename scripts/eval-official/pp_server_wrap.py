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

启动（参数与原服务完全相同，cwd 在第三方 PonderPounce 目录，脚本用绝对路径）::

    python /abs/path/scripts/eval-official/pp_server_wrap.py --args.seed 0 --args.checkpoint_path ... --port 8000

``python -m`` 会把 cwd 放在 ``sys.path`` 首位，而按路径运行脚本放的是脚本目录；为了与原命令的导入环境一致，
入口先把本目录移出 ``sys.path``、把 cwd 放到首位，再导入 ``ponderpounce``。
"""
from __future__ import annotations

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


def latest_visible_subgoal(cognitions: Any, now: int, previous: str | None) -> str | None:
    """``cognitions`` 中 ``ready_at_ns <= now`` 且 ``subgoal`` 非空的最新一条的文本；没有则返回 ``previous``。"""
    for cog in reversed(list(cognitions)):
        if cog.ready_at_ns <= now and cog.subgoal:
            return str(cog.subgoal)
    return previous


class SubgoalReportingServer(PonderPounceRoboMMEServer):
    """原类 + ACTION 回包附 ``subgoal``；动作、随机数、游标与触发节拍与原类逐项相同。"""

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
        return out


def main() -> None:
    from vla_eval.model_servers.serve import run_server

    run_server(SubgoalReportingServer)


if __name__ == "__main__":  # pragma: no cover
    main()
