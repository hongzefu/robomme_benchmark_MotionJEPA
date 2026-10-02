#!/usr/bin/env python3
"""v8 P4 独立 watchdog：按心跳文件 mtime 判「停止更新」（v8 方案第二部分 §2.4.4、§2.12 S2-D）。

``v8_continue_after_gen.py`` 每步、子进程每行输出与每 ``--beat-s`` 秒原子替换心跳文件。接续脚本自身崩溃、被杀或卡死
时它无法自报，本进程独立监督：

* 心跳 mtime 距今超过阈值（``--stale-s`` 缺省 900 秒＝15 分钟；``--step-stale STEP=秒`` 按心跳里的 ``step`` 单独给，
  取「该步 2b 实测用时 × 3」）→ 向事件日志追加 ``P4_WATCHDOG=FAIL step=<名> stale_s=<n> reason=stale``，退出 1；
* 心跳 ``status == "aborted"``（接续脚本收到信号中断）→ 立即 ``P4_WATCHDOG=FAIL … reason=aborted``，退出 1；
* 心跳文件在 ``--grace-s``（缺省 = ``--stale-s``）内一直没出现 → ``P4_WATCHDOG=FAIL step=absent … reason=no_heartbeat``；
  **本轮心跳**才算数：mtime 早于本 watchdog 启动时刻、或给了 ``--watch-pid`` 而心跳 ``pid`` 不等于它的，都是上一轮
  遗留（续行场景），一律按「尚无心跳」处理；
* ``--watch-pid`` 给定且该进程已不在、又没有收尾报告 → ``P4_WATCHDOG=FAIL … reason=pid_gone``（比 mtime 更快，
  不替代 mtime 判据）；
* 被监督进程正常完成：``--report`` 写出、含 ``final_line``（``V8_CONTINUE=…``）且该行已出现在事件日志 →
  ``P4_WATCHDOG=DONE verdict=<PASS|FAIL|INFO> step=<名>``，退出 0（接续本身的成败由 ``V8_CONTINUE`` 行与
  ``P4_NOTIFY`` 行表达，watchdog 只管「是否还活着、有没有收尾」）。

「停止受影响部分」：FAIL 时只对参数显式给出的精确目标动手——``--kill-pid <pid>``（SIGTERM，``--kill-grace-s``
后仍在再 SIGKILL）与 ``--kill-tmux <会话名>``（``tmux kill-session -t '=<会话名>'``，精确匹配）；
``--kill-heartbeat-groups`` 再收掉心跳里记录的 ``child_pid``／``server_pid`` 进程组（接续脚本以独立会话起它们，
组号 == pid；``/proc/<pid>/stat`` 核得 pgid == pid 才 killpg，防 pid 复用）——接续脚本被 SIGKILL 时它们会成孤儿，
tmux kill-session 也收不到。不做任何 pkill／模式匹配，不 kill-server。除事件日志外不写任何文件（只读监督）。

事件日志与接续脚本共用（只追加、整行一次写入），主会话对它挂一个 Monitor::

    tail -n +1 -F <事件日志> | stdbuf -oL tr '\\r' '\\n' | grep --line-buffered -E \\
      "P4_WATCHDOG=|P4_NOTIFY=|V8_CONTINUE=|V8_CONTINUE_ABORT|V8_CONTINUE_STEP .*status=FAIL|Traceback"

    uv run --no-sync python scripts/injection-dev/v8_watchdog.py --heartbeat <work>/heartbeat.json \\
      --report <work>/report.json --event-log <work>/events.log --stale-s 900 --poll-s 15 --kill-tmux v8-continue
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


def append_line(path: Path, line: str) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(fd, (line.rstrip("\n") + "\n").encode("utf-8"))
    finally:
        os.close(fd)


def read_json(path: Path) -> dict | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    # 僵尸进程（父进程尚未回收）也算已退出
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8") as handle:
            return handle.read().rsplit(")", 1)[1].split()[0] != "Z"
    except OSError:
        return True


def kill_pid(pid: int, grace: float) -> str:
    if not pid_alive(pid):
        return f"pid{pid}:gone"
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return f"pid{pid}:gone"
    deadline = time.time() + grace
    while time.time() < deadline:
        if not pid_alive(pid):
            return f"pid{pid}:term"
        time.sleep(0.1)
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        return f"pid{pid}:term"
    return f"pid{pid}:kill"


def kill_tmux(name: str) -> str:
    target = f"={name}"
    if subprocess.run(["tmux", "has-session", "-t", target], capture_output=True).returncode != 0:
        return f"tmux:{name}:absent"
    rc = subprocess.run(["tmux", "kill-session", "-t", target], capture_output=True).returncode
    return f"tmux:{name}:{'killed' if rc == 0 else f'rc{rc}'}"


def _strip_reused(line: str) -> str:
    return " ".join(part for part in line.split() if not part.startswith("reused="))


def done_line(report: Path, event_log: Path) -> str | None:
    """收尾报告与事件日志里的 ``V8_CONTINUE`` 行都在才算正常完成；返回报告里的收尾行。
    比较时去掉 ``reused=`` 字段（复用报告时重打的收尾行与原行只差这一项）。"""
    data = read_json(report) if report.is_file() else None
    if not data:
        return None
    final = data.get("final_line")
    if not isinstance(final, str) or not final.startswith("V8_CONTINUE="):
        return None
    try:
        text = event_log.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    want = _strip_reused(final)
    return final if any(_strip_reused(l) == want for l in text.splitlines() if l.startswith("V8_CONTINUE=")) else None


def proc_pgid(pid: int) -> int | None:
    """/proc/<pid>/stat 的进程组号（第 5 字段；comm 可含空格，按最后一个 ')' 切）。"""
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8") as handle:
            return int(handle.read().rsplit(")", 1)[1].split()[2])
    except (OSError, ValueError, IndexError):
        return None


def kill_heartbeat_group(pid: int, grace: float) -> str:
    """心跳里记录的 child_pid／server_pid：接续脚本以 start_new_session 起它们，组号 == pid。
    只有 /proc 核得 pgid == pid 才 killpg 这个精确组号（防 pid 复用误杀）；否则不动。"""
    if proc_pgid(pid) != pid:
        return f"pg{pid}:skip"
    try:
        os.killpg(pid, signal.SIGTERM)
    except ProcessLookupError:
        return f"pg{pid}:gone"
    deadline = time.time() + grace
    while time.time() < deadline:
        try:
            os.killpg(pid, 0)
        except ProcessLookupError:
            return f"pg{pid}:term"
        time.sleep(0.1)
    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        return f"pg{pid}:term"
    return f"pg{pid}:kill"


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--heartbeat", required=True, help="接续脚本的心跳文件")
    ap.add_argument("--report", required=True, help="接续脚本的收尾报告 report.json")
    ap.add_argument("--event-log", required=True, help="事件日志（只追加；Monitor 挂这里）")
    ap.add_argument("--stale-s", type=float, default=900.0, help="缺省停更阈值秒（15 分钟）")
    ap.add_argument("--step-stale", action="append", default=[], metavar="STEP=SECONDS", help="按步阈值")
    ap.add_argument("--grace-s", type=float, default=None, help="等首个心跳出现的秒数（缺省 = --stale-s）")
    ap.add_argument("--poll-s", type=float, default=10.0, help="检查间隔秒")
    ap.add_argument("--watch-pid", type=int, default=None, help="可选：被监督进程 pid（消失且无报告即 FAIL）")
    ap.add_argument("--kill-pid", type=int, action="append", default=[], help="FAIL 时终止的精确 pid（可多次）")
    ap.add_argument("--kill-tmux", action="append", default=[], help="FAIL 时 kill-session 的精确 tmux 会话名（可多次）")
    ap.add_argument("--kill-heartbeat-groups", action="store_true",
                    help="FAIL 时再收掉心跳里记录的 child_pid／server_pid 进程组（/proc 核 pgid == pid 才动）")
    ap.add_argument("--kill-grace-s", type=float, default=10.0, help="SIGTERM 后等多少秒再 SIGKILL")
    ap.add_argument("--max-runtime-s", type=float, default=None, help="可选：总时长上限，超过即 FAIL reason=max_runtime")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    heartbeat, report, event_log = Path(args.heartbeat), Path(args.report), Path(args.event_log)
    step_stale: dict[str, float] = {}
    for item in args.step_stale:
        step, sep, sec = item.partition("=")
        if not sep:
            raise SystemExit(f"--step-stale 须为 STEP=SECONDS：{item!r}")
        step_stale[step] = float(sec)
    grace = args.stale_s if args.grace_s is None else args.grace_s
    started = time.time()
    event_log.parent.mkdir(parents=True, exist_ok=True)

    def emit(line: str) -> None:
        print(line, flush=True)
        append_line(event_log, line)

    def fail(step: str, stale: float, reason: str) -> int:
        actions = []
        if args.kill_heartbeat_groups:
            beat = read_json(heartbeat) or {}
            for key in ("child_pid", "server_pid"):
                if isinstance(beat.get(key), int):
                    actions.append(kill_heartbeat_group(beat[key], args.kill_grace_s))
        actions += [kill_pid(pid, args.kill_grace_s) for pid in args.kill_pid]
        actions += [kill_tmux(name) for name in args.kill_tmux]
        emit(f"P4_WATCHDOG=FAIL step={step} stale_s={int(stale)} reason={reason} heartbeat={heartbeat} "
             f"killed={','.join(actions) if actions else 'none'}")
        return 1

    emit(f"P4_WATCHDOG=START pid={os.getpid()} heartbeat={heartbeat} stale_s={int(args.stale_s)} "
         f"step_stale={json.dumps(step_stale, separators=(',', ':'))} poll_s={args.poll_s}")
    while True:
        final = done_line(report, event_log)
        if final is not None:
            kv = dict(part.split("=", 1) for part in final.split() if "=" in part)
            emit(f"P4_WATCHDOG=DONE verdict={kv.get('V8_CONTINUE')} step={kv.get('step')} report={report}")
            return 0
        now = time.time()
        mtime, beat = None, {}
        if heartbeat.is_file():
            try:
                mtime = heartbeat.stat().st_mtime
            except FileNotFoundError:  # 原子替换的瞬间
                time.sleep(0.05)
                continue
            beat = read_json(heartbeat) or {}
            # 续行场景：上一轮遗留的心跳（mtime 早于本 watchdog 启动，或不是 --watch-pid 那个进程写的）
            # 一律当「本轮尚无心跳」，走 --grace-s，不据此判 FAIL
            if mtime < started or (args.watch_pid is not None and beat.get("pid") != args.watch_pid):
                mtime, beat = None, {}
        if mtime is not None:
            step = str(beat.get("step") or "unknown")
            stale = now - mtime
            if beat.get("status") == "aborted":
                return fail(step, stale, "aborted")
            limit = step_stale.get(step, args.stale_s)
            if stale > limit:
                return fail(step, stale, "stale")
        else:
            step, stale = "absent", now - started
            if stale > grace:
                return fail(step, stale, "no_heartbeat")
        if args.watch_pid is not None and not pid_alive(args.watch_pid):
            time.sleep(min(1.0, args.poll_s))  # 给收尾报告与事件行落盘留一点时间
            if done_line(report, event_log) is None:
                return fail(step, stale, "pid_gone")
            continue
        if args.max_runtime_s is not None and now - started > args.max_runtime_s:
            return fail(step, stale, "max_runtime")
        time.sleep(args.poll_s)


if __name__ == "__main__":
    sys.exit(main())
