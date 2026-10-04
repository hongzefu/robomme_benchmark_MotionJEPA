"""席位脚本测试（``test_seat_scripts.py``）的假引擎：由假解释器按脚本名分派，充当策略 server 或常驻客户端。

- ``server``（代替 ``smvla_server.py serve``）：在 ``--port`` 上监听回环端口；``FAKE_SERVER_MODE``：
  ``ok``（正常，收 TERM 即退）／``die_before_ready``（立即退出 1）／``die_after``（监听 ``FAKE_SERVER_LIFE`` 秒后退出 1）／
  ``ignore_term``（忽略 TERM，只能被 KILL）。
- ``client``（代替 ``env_client.py run``）：第 n 次启动按 ``FAKE_CLIENT_CODES`` 的第 n 项（超出取最后一项）行事：
  非负整数 = 写进度后以该码退出（0 时为身份清单每行写一条结果行和录像目录）；``-1`` = 一直睡（收 TERM 即退）。
每次启动、收信号都往 ``FAKE_LOG`` 追加一行 JSON（含 pid），测试据此核对。
"""
from __future__ import annotations

import json
import os
import signal
import socket
import sys
import time
from pathlib import Path

ROLE, ARGS = sys.argv[1], sys.argv[2:]
LOG = os.environ["FAKE_LOG"]


def emit(**kw):
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"role": ROLE, "pid": os.getpid(), **kw}, ensure_ascii=False) + "\n")


def arg(name, default=None):
    return ARGS[ARGS.index(name) + 1] if name in ARGS else default


def on_term(*_):
    emit(event="term")
    sys.exit(0)


def server() -> None:
    mode = os.environ.get("FAKE_SERVER_MODE", "ok")
    port = int(arg("--port"))
    emit(event="start", port=port, mode=mode)
    if mode == "die_before_ready":
        sys.exit(1)
    signal.signal(signal.SIGTERM, signal.SIG_IGN if mode == "ignore_term" else on_term)
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("127.0.0.1", port))
    s.listen(64)
    s.settimeout(0.1)
    t_end = time.time() + float(os.environ.get("FAKE_SERVER_LIFE", "0")) if mode == "die_after" else None
    while True:
        if t_end is not None and time.time() > t_end:
            emit(event="died")
            os._exit(1)
        try:
            c, _ = s.accept()
            c.close()
        except (socket.timeout, OSError):
            pass


def client() -> None:
    state = Path(os.environ["FAKE_STATE"])
    n = int(state.read_text()) if state.exists() else 0
    state.write_text(str(n + 1))
    codes = [int(x) for x in os.environ.get("FAKE_CLIENT_CODES", "0").split(",")]
    code = codes[min(n, len(codes) - 1)]
    out = Path(arg("--out"))
    out.mkdir(parents=True, exist_ok=True)
    emit(event="start", n=n, code=code, first_extra_s=arg("--first-extra-s"), wall_s=arg("--episode-wall-s"),
         port=arg("--port"), v8="--v8" in ARGS, ledger=arg("--ledger"), rec_root=arg("--rec-root"))
    signal.signal(signal.SIGTERM, on_term)
    (out / "progress.json").write_text(json.dumps({"t": time.time()}), encoding="utf-8")
    if code == -1:
        while True:
            time.sleep(0.1)
    if code == 0:
        rec_root = Path(arg("--rec-root") or out / "rec")
        for row in json.loads(Path(arg("--identities")).read_text(encoding="utf-8")):
            key = row["key"]
            d = rec_root / f"{key}.a1"
            d.mkdir(parents=True, exist_ok=True)
            for name, data in (("front.mkv", b"front-" + key.encode()), ("wrist.mkv", b"wrist-" + key.encode()),
                               ("summary.json", b'{"RECORDER_VERIFY": "PASS"}')):
                (d / name).write_bytes(data)
            with open(out / "results.jsonl", "a", encoding="utf-8") as fh:
                fh.write(json.dumps({"v8": True, "key": key, "task": row["task"], "seed": row["seed"],
                                     "status": "success", "infra": False, "rec_dir": str(d)}) + "\n")
    sys.exit(code)


if __name__ == "__main__":
    server() if ROLE == "server" else client()
