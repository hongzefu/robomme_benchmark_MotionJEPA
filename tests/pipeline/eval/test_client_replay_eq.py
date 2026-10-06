"""客户端回放等价核对 ``client_replay_eq.py`` 的自测：同一检出两侧比较必须 PASS，三类故意改动必须被抓到。

只跑 smvla、mme 两条路线（各三个场景、确定性假环境与假服务，纯 CPU、无网络、无真实仿真）；mmesg、pp 路线由主会话在
每批起跑前对真实 base／candidate 检出跑全量。
"""
from __future__ import annotations

import subprocess
import sys

from tests._support.loaders import REPO


def test_same_checkout_passes_and_tampers_are_caught():
    script = REPO / "scripts" / "eval-official" / "client_replay_eq.py"
    p = subprocess.run([sys.executable, str(script), "--base", str(REPO), "--candidate", str(REPO),
                        "--routes", "smvla,mme", "--self-test"], capture_output=True, text=True, timeout=600)
    lines = [ln for ln in p.stdout.splitlines() if ln.startswith("CLIENT_REPLAY_")]
    eq = [ln for ln in lines if ln.startswith("CLIENT_REPLAY_EQ=")]
    st = [ln for ln in lines if ln.startswith("CLIENT_REPLAY_SELFTEST=")]
    assert len(eq) == 2 and all(ln.startswith("CLIENT_REPLAY_EQ=PASS") for ln in eq), p.stdout + p.stderr
    assert all("request_diff=0 action_diff=0 control_diff=0 terminal_diff=0" in ln for ln in eq)
    assert len(st) == 2 and all("action=caught request=caught order=caught" in ln for ln in st), p.stdout
    assert p.returncode == 0
