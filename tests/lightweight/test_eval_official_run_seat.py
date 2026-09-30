"""``scripts/eval-official/run_seat.sh`` 的无 GPU 测试：用假解释器（heredoc 交真 python、server 只起 TCP 监听、
客户端只记参数后退出），不起仿真、不起真模型。

覆盖：``--client-per-task`` 每任务起一个新客户端、``--only`` 列表按任务首次出现顺序与组内文件顺序、server 只起一次、
首次推理放宽只给第一个客户端、金丝雀只随第一个客户端；SEAT_DONE 判定行与 seat-report.json。
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SEAT = REPO / "scripts" / "eval-official" / "run_seat.sh"


def _free_seat_idx() -> int:
    """挑一个 18000+100*idx 与其 +1 都空闲的席号（避开真席位端口）。"""
    for idx in range(50, 99):
        ok = True
        for p in (18000 + 100 * idx, 18000 + 100 * idx + 1):
            s = socket.socket()
            try:
                s.bind(("127.0.0.1", p))
            except OSError:
                ok = False
            finally:
                s.close()
        if ok:
            return idx
    pytest.skip("找不到空闲端口")


@pytest.mark.skipif(shutil.which("bash") is None, reason="无 bash")
def test_client_per_task_每任务一个客户端_server只起一次(tmp_path):
    calls = tmp_path / "calls.log"
    fake = tmp_path / "fakepy"
    fake.write_text(f"""#!/bin/bash
if [[ "$1" == "-" ]]; then exec {sys.executable} "$@"; fi
case "$*" in
  *smvla_server.py*)
    echo "SERVER $*" >> {calls}
    p=$(echo "$*" | sed -E 's/.*--port ([0-9]+).*/\\1/')
    exec {sys.executable} -c "import socket,time;s=socket.socket();s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);s.bind(('127.0.0.1',$p));s.listen();time.sleep(10**6)";;
  *env_client.py*) echo "CLIENT $*" >> {calls}; exit 0;;
esac
exit 9
""")
    fake.chmod(0o755)
    ckpt = tmp_path / "ckpt"
    ckpt.mkdir()
    (ckpt / "w.bin").write_bytes(b"x")
    ids = [{"task": t, "source_episode": se, "seed": sd, "builder_episode": (se - 3) // 4}
           for t, se, sd in [("BinFill", 3, 1), ("PickXtimes", 3, 2), ("BinFill", 7, 3), ("StopCube", 3, 4),
                             ("PickXtimes", 7, 5)]]
    idf = tmp_path / "ids.json"
    idf.write_text(json.dumps(ids))
    out = tmp_path / "out"
    env = dict(os.environ, BENCH_PY=str(fake), SMVLA_PY=str(fake), SMVLA_CKPT=str(ckpt))
    proc = subprocess.run(["bash", str(SEAT), "--seat", "t", "--seat-idx", str(_free_seat_idx()), "--gpu", "0",
                           "--cond", "E1", "--policies", "smvla", "--identities", str(idf), "--out", str(out),
                           "--client-per-task", "--canary", "PickXtimes:3:510300"],
                          env=env, capture_output=True, text=True, timeout=180)
    log = (out / "seat-t.log").read_text()
    assert proc.returncode == 0, log
    lines = calls.read_text().splitlines()
    servers = [l for l in lines if l.startswith("SERVER")]
    clients = [l for l in lines if l.startswith("CLIENT")]
    assert len(servers) == 1
    onlys = [c.split("--only ")[1].split()[0] for c in clients]
    assert onlys == ["BinFill_1,BinFill_3", "PickXtimes_2,PickXtimes_5", "StopCube_4"]
    assert all("--order forward" in c for c in clients)
    assert "--first-extra-s 600" in clients[0] and all("--first-extra-s 0" in c for c in clients[1:])
    assert "--canary" in clients[0] and not any("--canary" in c for c in clients[1:])
    assert log.count("TASK_CLIENT policy=smvla") == 3
    assert "SEAT_DONE policy=smvla cond=E1 seat=t" in log and "EXIT_CODE=0" in log
    rep = json.loads((out / "smvla" / "seat-report.json").read_text())
    assert rep["queue_check"] == "NA" and rep["done"] == 0 and rep["infra"] == 0


def test_client_per_task_不接受队列模式(tmp_path):
    proc = subprocess.run(["bash", str(SEAT), "--seat", "t", "--seat-idx", "1", "--gpu", "0", "--cond", "N",
                           "--queue", str(tmp_path / "q"), "--out", str(tmp_path / "o"), "--client-per-task"],
                          capture_output=True, text=True, timeout=30)
    assert proc.returncode == 2 and "identities" in proc.stderr
