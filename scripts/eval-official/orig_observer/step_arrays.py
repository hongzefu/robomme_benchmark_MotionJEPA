"""逐步原数组 ``arrays.npz``（计划第二部分一节 S7、审计第 12 条；契约 C4、C5）。

在 ``InProcSimPool.step``（SimpleMemVLA）／``EnvRunner.step``（MME）钩子里，把每步**实际交给环境**的动作行按原 dtype、
shape 复制一份（只复制主机端 numpy，不调随机函数、不做 GPU 运算、不改参数与返回值），局末 ``np.savez`` 到局目录
``arrays.npz``，键 ``exec_action__%05d``（0 起的步序号 = ``trace`` 的 ``step - 1``）。

SimpleMemVLA 一次派发一个动作块，``SimEnvService.step`` 逐行执行到 ``consumed`` 行为止；实际交给环境的第 j 行是
``np.asarray(np.asarray(chunk, float64)[j], float64).reshape(-1)[:8]``（``SimEnvService.step`` 先整体转 float64，
``RoboMMESimEnv.step_one`` 再 ``reshape(-1)`` 后取前 8 维交给 ``env.step``），见 ``smvla_exec_rows``。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

KEY_FMT = "exec_action__{:05d}"


def smvla_exec_rows(chunk: Any, consumed: int) -> list[np.ndarray]:
    """SimpleMemVLA 动作块里实际执行的前 ``consumed`` 行（float64、8 维），换算与原版 ``SimEnvService.step`` →
    ``RoboMMESimEnv.step_one`` 逐字相同；返回新数组，不与入参共享内存。"""
    n = int(consumed or 0)
    if n <= 0:
        return []
    rows = np.asarray(chunk, dtype=np.float64)
    out = []
    for a in rows[:n]:
        act = np.asarray(a, dtype=np.float64).reshape(-1)
        out.append(np.array(act[:8], copy=True))
    return out


class StepArrays:
    """一局的逐步动作原数组；``add`` 复制一份，``save`` 写 ``arrays.npz``（非压缩 ``np.savez``）。"""

    def __init__(self) -> None:
        self._arrays: dict[str, np.ndarray] = {}

    def add(self, index: int, action: Any) -> str:
        key = KEY_FMT.format(int(index))
        if key in self._arrays:
            raise ValueError(f"重复的步键 {key}")
        self._arrays[key] = np.array(np.asarray(action), copy=True)
        return key

    def __len__(self) -> int:
        return len(self._arrays)

    def keys(self) -> list[str]:
        return sorted(self._arrays)

    def save(self, path: str | Path) -> Path | None:
        """写 ``arrays.npz``；没有任何步时不写文件，返回 None。"""
        if not self._arrays:
            return None
        path = Path(path)
        tmp = path.with_name(path.name + ".tmp.npz")
        np.savez(tmp, **self._arrays)
        tmp.replace(path)
        return path
