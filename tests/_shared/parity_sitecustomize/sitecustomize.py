"""解释器启动钩子：把三路对拍的观察器装进每个进程（含 spawn 出来的 worker）。

用法是把本目录放进 ``PYTHONPATH``，并设 ``PARITY_EVIDENCE_DIR``；不设时本文件什么也不做。
必须先于 torch / sapien / robomme 的导入生效，因此只能走 sitecustomize，
不能在测试进程里事后打桩 —— 真正跑生成的是 spawn 出来的子进程。
"""

import os
import sys

_OBSERVER_DIR = os.environ.get("PARITY_OBSERVER_DIR")
if os.environ.get("PARITY_EVIDENCE_DIR") and _OBSERVER_DIR:
    if _OBSERVER_DIR not in sys.path:
        sys.path.insert(0, _OBSERVER_DIR)
    try:
        import parity_observer

        parity_observer.install()
    except Exception as exc:  # 观察器绝不能让被观察的进程起不来
        sys.stderr.write(f"[parity-sitecustomize] 安装观察器失败：{exc!r}\n")
