#!/usr/bin/env python3
"""v7.5eval 通用编排器（0929-v7.5eval-restructure-plan.md 第一部分 §1.4 口径 14、§3.3；第二部分 R4、§3 runbook）。

与具体命令无关：输入一份计划 JSON（若干条「线」lane，每条线有顺序执行的若干步 step），
按依赖图推进；每步只有在「报告 JSON 存在且能解析」且「本次日志里有一行匹配判定正则」时才算完成
（AGENTS.md P4：完成 → 读真实报告 → 下一步；缺文件即停该分支，不用默认值填补）。

计划 JSON 形态::

    {"lanes": [
      {"name": "env-yi", "where": {"gl_jobid": 62608440},
       "steps": [
         {"name": "env-yi-first", "cmd": "bash run.sh ...", "needs": ["step0"],
          "report": "artifacts/v7.5eval/env/yi-first/report.json",
          "verdict_regex": "^ENV_DIGEST_DONE .*rows=48", "timeout_s": 7200,
          "retries": 1, "blocking": true, "notify": false}
       ]},
      {"name": "local-card0", "where": "local", "steps": [...]}
    ]}

- ``cmd`` / ``report`` 里的 ``{state}`` ``{step}`` ``{lane}`` ``{log}`` 会被替换成绝对路径 / 名字；
  相对路径的 ``report`` 以 ``--workdir``（默认当前目录）为基准，``cmd`` 也在 ``--workdir`` 下执行。
- 同一条线内的步骤隐式依赖上一步（线内顺序执行）。``blocking=true``（默认）的步骤失败，
  依赖它的步骤（含同线后续步骤）一律以 ``STEP_FAIL reason=upstream`` 跳过；``blocking=false``
  的步骤失败只记录，依赖方照跑（口径 6「只测差距、全部不阻塞」）。上游被跳过同样按阻塞传播。
- ``retries`` 只用于基础设施失败（非零退出、超时、启动失败）的重试；报告缺失、报告坏、判定不符不重试。

状态目录 ``--state``：``<step>.running`` / ``<step>.done`` / ``<step>.fail``（JSON），
``logs/<step>.log``（每次尝试追加 ``=== ATTEMPT`` 头，结束追加 ``EXIT_CODE=``），``events.log``，
``orch.heartbeat``（每 ``--heartbeat-s`` 秒重写一次的 JSON 状态摘要，计数键零值也显式写出），
``notify/*.json``（阶段完成 / 停线 / 需人工，供主会话转发 Slack；编排器自己不发 Slack）。

恢复（重启同一个 ``--state``）：``.done`` 直接跳过（绝不重放已完成预算）；``.fail`` 默认保留不重跑
（``--retry-failed`` 才清掉重跑，原日志保留）；``.running``：若记录的子进程仍存活（同主机、pid 与启动时刻一致）
就接管等待它结束；否则查远端存活证据（GL 作业步名 ``v75-<步名>``，经 ``squeue -h -s -j``；或步骤可选字段
``alive_file`` + ``alive_stale_s`` 指定、由步骤命令定期刷新的存活文件），在跑则 ``STEP_ADOPT_REMOTE`` 轮询等待；
换了主机又无法确认死活 → ``resume_unknown`` 需人工、绝不重跑；确认已死才按「报告缺失 → 重跑、报告存在 → 核对判定，
核对不过记 ``resume_unverified`` 需人工」处理。超时先 SIGTERM，宽限 ``--term-grace-s``（默认 120 s）后再 SIGKILL。

GL 线（``where={"gl_jobid": N}``）在编排席内派发：
``srun --jobid=N --overlap --exact --ntasks=1 --cpus-per-task=4 --gpu_cmode=shared --job-name=v75-<步名> bash -c <cmd>``，
子进程环境清空全部 ``SLURM_*``（否则报 ``CPU binding outside of job step allocation``）。
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

# 状态键全集：心跳 JSON 中每个计数都显式输出，零值也写（P4「报告契约必须验证序列化后形态」）。
STATUS_KEYS = ("pending", "running", "done", "fail", "skipped")
FAIL_REASONS = ("exit", "timeout", "spawn_error", "report_missing", "report_invalid",
                "verdict_mismatch", "upstream", "resume_unverified", "resume_unknown", "orch_error")
NEEDS_HUMAN_REASONS = ("resume_unverified", "resume_unknown", "orch_error")
INFRA_REASONS = ("exit", "timeout", "spawn_error")
SEAT_WARN_S = 6 * 3600


def step_job_name(step: str) -> str:
    """GL 作业步名：``v75-<步名>``，用于跨主机重启时经 ``squeue -s`` 找回仍在跑的步。"""
    return f"v75-{step}"


def srun_argv(jobid, cmd: str, srun: str = "srun", step=None) -> list:
    """按 R4 构造 GL 派发 argv（逐字固定，测试直接核对）；给了 step 时加 ``--job-name=v75-<step>``。"""
    argv = [srun, f"--jobid={jobid}", "--overlap", "--exact", "--ntasks=1",
            "--cpus-per-task=4", "--gpu_cmode=shared"]
    if step:
        argv.append(f"--job-name={step_job_name(step)}")
    return argv + ["bash", "-c", cmd]


def child_env(where, base=None) -> dict:
    """子进程环境：GL 线清空全部 SLURM_* 变量；本机线原样继承。"""
    env = dict(os.environ if base is None else base)
    if isinstance(where, dict):
        for k in list(env):
            if k.startswith("SLURM_"):
                del env[k]
    return env


def build_command(where, cmd: str, srun: str = "srun", step=None):
    """返回 (argv, env)。本机：bash -c cmd；GL：srun ... [--job-name=v75-<step>] bash -c cmd。"""
    if isinstance(where, dict):
        return srun_argv(where["gl_jobid"], cmd, srun, step), child_env(where)
    return ["bash", "-c", cmd], child_env(where)


def parse_time_left(s: str):
    """解析 squeue ``%L``：``D-HH:MM:SS`` / ``HH:MM:SS`` / ``MM:SS``；无法解析返回 None。"""
    s = s.strip()
    if not s or s.upper() in ("INVALID", "NOT_SET"):
        return None
    if s.upper() == "UNLIMITED":
        return float("inf")
    days = 0
    if "-" in s:
        d, s = s.split("-", 1)
        days = int(d)
    parts = [int(p) for p in s.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0)
    h, m, sec = parts[-3:]
    return days * 86400 + h * 3600 + m * 60 + sec


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def _clean(v) -> str:
    """事件行的值去掉空白，保证单行、空格分隔可解析。"""
    s = str(v).replace("\n", " ").strip()
    s = re.sub(r"\s+", "_", s)
    return s[:300] if s else "-"


def _write_json_atomic(path: Path, obj) -> None:
    tmp = path.with_name(path.name + f".tmp{os.getpid()}.{threading.get_ident()}")
    tmp.write_text(json.dumps(obj, sort_keys=True, ensure_ascii=False, indent=1) + "\n")
    os.replace(tmp, path)


def _proc_start(pid: int):
    """读 /proc/<pid>/stat 的启动时刻（防 pid 复用）；进程不存在返回 None。"""
    try:
        raw = Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return None
    # comm 字段可能含空格，从最后一个 ')' 之后切
    rest = raw[raw.rfind(")") + 2:].split()
    try:
        if rest[0] == "Z":
            return None
        return rest[19]
    except IndexError:
        return None


class PlanError(ValueError):
    pass


def load_plan(path) -> dict:
    """读计划并校验：步名全局唯一、needs 都存在、无环；返回规范化结构。"""
    plan = json.loads(Path(path).read_text())
    lanes = plan.get("lanes")
    if not isinstance(lanes, list) or not lanes:
        raise PlanError("plan.lanes 必须是非空列表")
    steps = {}
    lane_names = set()
    for lane in lanes:
        ln = lane.get("name")
        if not ln or ln in lane_names:
            raise PlanError(f"lane 名缺失或重复：{ln!r}")
        lane_names.add(ln)
        where = lane.get("where", "local")
        if where != "local" and not (isinstance(where, dict) and "gl_jobid" in where):
            raise PlanError(f"lane {ln} 的 where 只能是 'local' 或 {{'gl_jobid': N}}")
        lane["where"] = where
        prev = None
        for st in lane.get("steps", []):
            sn = st.get("name")
            if not sn or not re.fullmatch(r"[A-Za-z0-9_.\-]+", sn):
                raise PlanError(f"步名非法：{sn!r}（只允许字母数字 _ . -）")
            if sn in steps:
                raise PlanError(f"步名重复：{sn}")
            for k in ("cmd", "report", "verdict_regex"):
                if not st.get(k):
                    raise PlanError(f"步 {sn} 缺 {k}")
            re.compile(st["verdict_regex"])
            st = dict(st)
            st["lane"] = ln
            st["needs"] = list(st.get("needs", []))
            st["prev"] = prev
            st["retries"] = int(st.get("retries", 0))
            st["blocking"] = bool(st.get("blocking", True))
            st["timeout_s"] = st.get("timeout_s")
            steps[sn] = st
            prev = sn
        lane["step_names"] = [s["name"] for s in lane.get("steps", [])]
    for sn, st in steps.items():
        for n in st["needs"]:
            if n not in steps:
                raise PlanError(f"步 {sn} 的 needs 引用了不存在的步 {n}")
    # 环检测（needs + 线内顺序）
    color = {}

    def deps(s):
        d = list(steps[s]["needs"])
        if steps[s]["prev"]:
            d.append(steps[s]["prev"])
        return d

    def visit(s, stack):
        color[s] = 1
        for d in deps(s):
            if color.get(d) == 1:
                raise PlanError(f"依赖成环：{' -> '.join(stack + [s, d])}")
            if not color.get(d):
                visit(d, stack + [s])
        color[s] = 2

    for s in steps:
        if not color.get(s):
            visit(s, [])
    return {"lanes": lanes, "steps": steps}


class Orchestrator:
    def __init__(self, plan: dict, state: Path, workdir: Path, *, heartbeat_s=30.0, seat_check_s=600.0,
                 srun="srun", squeue="squeue", retry_failed=False, poll_s=1.0, term_grace_s=120.0,
                 remote_poll_s=30.0):
        self.plan = plan
        self.steps = plan["steps"]
        self.state = Path(state).resolve()
        self.workdir = Path(workdir).resolve()
        self.heartbeat_s = heartbeat_s
        self.seat_check_s = seat_check_s
        self.srun = srun
        self.squeue = squeue
        self.retry_failed = retry_failed
        self.poll_s = poll_s
        self.term_grace_s = term_grace_s    # SIGTERM → SIGKILL 宽限（留给 run_seat 等清理收尾）
        self.remote_poll_s = remote_poll_s  # 接管远端存活步骤时的轮询间隔
        self.host = socket.gethostname()
        self.cv = threading.Condition()
        self.status = {}      # 步名 -> pending/running/done/fail/skipped
        self.fail_info = {}   # 步名 -> {"reason", "blocking"}
        self.reasons = {r: 0 for r in FAIL_REASONS}
        self.seat_warned = set()
        self.seat_query_failed = set()
        self.stop_evt = threading.Event()
        self.ev_lock = threading.Lock()
        self.phase = "starting"
        self.started = time.time()
        for d in ("logs", "notify"):
            (self.state / d).mkdir(parents=True, exist_ok=True)

    # ---------- 路径与替换 ----------
    def _subst(self, s: str, st: dict) -> str:
        return (s.replace("{state}", str(self.state)).replace("{step}", st["name"])
                .replace("{lane}", st["lane"]).replace("{log}", str(self.log_path(st["name"]))))

    def report_path(self, st) -> Path:
        p = Path(self._subst(st["report"], st))
        return p if p.is_absolute() else self.workdir / p

    def log_path(self, name) -> Path:
        return self.state / "logs" / f"{name}.log"

    def marker(self, name, kind) -> Path:
        return self.state / f"{name}.{kind}"

    # ---------- 事件与通知 ----------
    def emit(self, kind: str, **kv) -> None:
        line = kind + " ts=" + _now() + "".join(f" {k}={_clean(v)}" for k, v in kv.items())
        with self.ev_lock:
            print(line, flush=True)
            with open(self.state / "events.log", "a") as f:
                f.write(line + "\n")

    def notify(self, kind: str, name: str, **payload) -> None:
        """写 notify/<时间>-<kind>-<name>.json；kind ∈ stage_done / lane_stop / needs_human。"""
        obj = {"kind": kind, "name": name, "ts": _now(), "host": self.host}
        obj.update(payload)
        fn = f"{time.strftime('%Y%m%dT%H%M%S')}-{int(time.time() * 1e6) % 1000000:06d}-{kind}-{name}.json"
        _write_json_atomic(self.state / "notify" / fn, obj)

    # ---------- 心跳 ----------
    def summary(self) -> dict:
        with self.cv:
            status = dict(self.status)
            reasons = dict(self.reasons)
        counts = {k: 0 for k in STATUS_KEYS}
        lanes = {}
        for lane in self.plan["lanes"]:
            lc = {k: 0 for k in STATUS_KEYS}
            for sn in lane["step_names"]:
                s = status.get(sn, "pending")
                lc[s] += 1
                counts[s] += 1
            lanes[lane["name"]] = lc
        return {"ts": _now(), "unix": time.time(), "pid": os.getpid(), "host": self.host,
                "phase": self.phase, "total": len(self.steps), "counts": counts,
                "fail_reasons": reasons, "lanes": lanes, "steps": status,
                "uptime_s": round(time.time() - self.started, 1)}

    def write_heartbeat(self) -> None:
        _write_json_atomic(self.state / "orch.heartbeat", self.summary())

    def _heartbeat_loop(self):
        while not self.stop_evt.wait(self.heartbeat_s):
            try:
                self.write_heartbeat()
            except OSError as e:  # 心跳写失败不应拖垮编排；看门狗会发现心跳过期
                print(f"HEARTBEAT_WRITE_FAIL err={_clean(e)}", file=sys.stderr, flush=True)

    # ---------- 席位剩余时间 ----------
    def _seat_loop(self):
        while True:
            self.check_seats()
            if self.stop_evt.wait(self.seat_check_s):
                return

    def check_seats(self):
        for lane in self.plan["lanes"]:
            w = lane["where"]
            if not isinstance(w, dict) or lane["name"] in self.seat_warned:
                continue
            with self.cv:
                pending = [s for s in lane["step_names"] if self.status.get(s) in ("pending", "running")]
            if not pending:
                continue
            jid = w["gl_jobid"]
            try:
                out = subprocess.run([self.squeue, "-h", "-j", str(jid), "-o", "%L"], capture_output=True,
                                     text=True, timeout=60, env=child_env(w))
                txt = out.stdout.strip().splitlines() if out.returncode == 0 else []
                # 作业已结束 / 已过期：squeue 返回非零或空输出 → 按 not_in_queue、剩余 0 处理
                left = parse_time_left(txt[0]) if txt else 0.0
            except Exception as e:  # noqa: BLE001  squeue 本身跑不起来（超时、找不到命令）
                if lane["name"] not in self.seat_query_failed:
                    self.seat_query_failed.add(lane["name"])
                    self.emit("SEAT_QUERY_FAIL", lane=lane["name"], jobid=jid, err=e)
                continue
            self.seat_query_failed.discard(lane["name"])
            if left is not None and left < SEAT_WARN_S:
                self.seat_warned.add(lane["name"])
                self.emit("SEAT_EXPIRING", lane=lane["name"], jobid=jid, left_s=int(left),
                          pending=len(pending), reason="not_in_queue" if not txt else "time_left")
                self.notify("needs_human", lane["name"], event="SEAT_EXPIRING", jobid=jid,
                            left_s=int(left), pending_steps=pending)

    # ---------- 状态机 ----------
    def _set(self, name, s, **info):
        with self.cv:
            self.status[name] = s
            if s == "fail" or s == "skipped":
                self.fail_info[name] = info
                r = info.get("reason")
                if r in self.reasons:
                    self.reasons[r] += 1
            self.cv.notify_all()

    def restore(self):
        """从状态目录恢复：.done 跳过；.fail 保留（或 --retry-failed 清掉）；.running 交给执行时处理。"""
        for sn, st in self.steps.items():
            done, fail = self.marker(sn, "done"), self.marker(sn, "fail")
            if done.exists():
                self.status[sn] = "done"
                continue
            if fail.exists():
                if self.retry_failed:
                    keep = self.state / "logs" / f"{sn}.fail.{int(time.time())}.json"
                    os.replace(fail, keep)  # 保留原失败报告
                else:
                    try:
                        info = json.loads(fail.read_text())
                    except (OSError, ValueError):
                        info = {"reason": "orch_error", "blocking": True}
                    kind = "skipped" if info.get("reason") == "upstream" else "fail"
                    self.status[sn] = kind
                    self.fail_info[sn] = info
                    if info.get("reason") in self.reasons:
                        self.reasons[info["reason"]] += 1
                    continue
            self.status[sn] = "pending"

    def _deps(self, st):
        d = list(st["needs"])
        if st["prev"]:
            d.append(st["prev"])
        return d

    def _wait_deps(self, st):
        """等所有依赖到终态；返回 None（可跑）或阻塞上游名（需跳过）。"""
        deps = self._deps(st)
        with self.cv:
            while True:
                blocked = None
                ready = True
                for d in deps:
                    s = self.status.get(d)
                    if s == "done":
                        continue
                    if s == "skipped" or (s == "fail" and self.fail_info.get(d, {}).get("blocking", True)):
                        blocked = d
                        break
                    if s == "fail":
                        continue
                    ready = False
                if blocked or ready:
                    return blocked
                self.cv.wait(timeout=self.poll_s)

    def _fail(self, st, reason, detail="", attempt=0):
        blocking = True if reason == "upstream" else st["blocking"]
        info = {"step": st["name"], "lane": st["lane"], "reason": reason, "detail": str(detail)[:2000],
                "blocking": blocking, "attempt": attempt, "ts": _now(), "report": str(self.report_path(st))}
        _write_json_atomic(self.marker(st["name"], "fail"), info)
        try:
            self.marker(st["name"], "running").unlink()
        except FileNotFoundError:
            pass
        self._set(st["name"], "skipped" if reason == "upstream" else "fail", **info)
        self.emit("STEP_FAIL", lane=st["lane"], step=st["name"], reason=reason, blocking=int(blocking),
                  attempt=attempt, detail=detail or "-")
        if reason in NEEDS_HUMAN_REASONS:
            self.notify("needs_human", st["name"], event="STEP_FAIL", **info)
        elif blocking and reason != "upstream":
            self.notify("lane_stop", st["lane"], event="STEP_FAIL", **info)

    def _verify(self, st, log_offset):
        """完成判定：报告存在且可解析 + 本次日志段有一行匹配判定正则。返回 (ok, reason, detail, extra)。"""
        rp = self.report_path(st)
        if not rp.is_file():
            return False, "report_missing", str(rp), {}
        try:
            raw = rp.read_bytes()
            json.loads(raw.decode("utf-8"))
        except (OSError, ValueError) as e:
            return False, "report_invalid", f"{rp}: {e}", {}
        try:
            with open(self.log_path(st["name"]), "rb") as f:
                f.seek(log_offset)
                text = f.read().decode("utf-8", "replace")
        except OSError:
            text = ""
        m = re.search(st["verdict_regex"], text, re.MULTILINE)
        if not m:
            return False, "verdict_mismatch", st["verdict_regex"], {}
        line_start = text.rfind("\n", 0, m.start()) + 1
        line_end = text.find("\n", m.end())
        line = text[line_start: line_end if line_end >= 0 else len(text)]
        return True, "", "", {"report_sha256": hashlib.sha256(raw).hexdigest(), "verdict_line": line[:1000]}

    def _mark_done(self, st, attempt, extra, t0):
        info = {"step": st["name"], "lane": st["lane"], "report": str(self.report_path(st)), "attempt": attempt,
                "ts": _now(), "elapsed_s": round(time.time() - t0, 2)}
        info.update(extra)
        _write_json_atomic(self.marker(st["name"], "done"), info)
        try:
            self.marker(st["name"], "running").unlink()
        except FileNotFoundError:
            pass
        self._set(st["name"], "done")
        self.emit("STEP_DONE", lane=st["lane"], step=st["name"], attempt=attempt, elapsed_s=info["elapsed_s"],
                  report=info["report"], verdict=info.get("verdict_line", "-"))
        if st.get("notify"):
            self.notify("stage_done", st["name"], **info)

    def _log_append(self, name, text):
        with open(self.log_path(name), "a") as f:
            f.write(text)

    def _killpg_graceful(self, pgid, wait_dead):
        """SIGTERM 进程组，宽限 term_grace_s 秒（给 run_seat 等清理收尾）后仍在则 SIGKILL。"""
        try:
            os.killpg(pgid, signal.SIGTERM)
        except OSError:
            return
        t_end = time.time() + self.term_grace_s
        while time.time() < t_end:
            if wait_dead():
                return
            time.sleep(min(self.poll_s, 1.0))
        try:
            os.killpg(pgid, signal.SIGKILL)
        except OSError:
            pass

    def _wait_pid(self, pid, pstart, deadline):
        while _proc_start(pid) == pstart:
            if deadline is not None and time.time() > deadline:
                return False
            time.sleep(self.poll_s)
        return True

    def _alive_file_state(self, st):
        """步骤自带的存活文件：返回 True（新鲜）/ False（过期或缺失）/ None（未配置）。"""
        af = st.get("alive_file")
        if not af:
            return None
        p = Path(self._subst(af, st))
        if not p.is_absolute():
            p = self.workdir / p
        try:
            age = time.time() - p.stat().st_mtime
        except OSError:
            return False
        return age < float(st.get("alive_stale_s", 600))

    def _squeue_step_state(self, st):
        """GL 步：``squeue -h -s -j <jobid> -o %i,%j`` 找作业步名 v75-<步名>。
        返回 True（在跑）/ False（查询成功但不在）/ None（非 GL 或查询失败）。"""
        w = st["lane_where"]
        if not isinstance(w, dict):
            return None
        try:
            out = subprocess.run([self.squeue, "-h", "-s", "-j", str(w["gl_jobid"]), "-o", "%i,%j"],
                                 capture_output=True, text=True, timeout=60, env=child_env(w))
        except (OSError, subprocess.SubprocessError):
            return None
        if out.returncode != 0:
            return None
        want = step_job_name(st["name"])
        return any(ln.strip().split(",", 1)[-1] == want for ln in out.stdout.splitlines())

    def _remote_alive(self, st):
        """综合存活证据：任一来源说在跑 → True；有来源且都说不在 → False；无任何可用来源 → None。"""
        vals = [v for v in (self._squeue_step_state(st), self._alive_file_state(st)) if v is not None]
        if any(vals):
            return True
        return False if vals else None

    def _finish_adopted(self, st, offset, attempt, t0, tag):
        self._log_append(st["name"], f"\nEXIT_CODE=unknown({tag})\n")
        ok, reason, detail, extra = self._verify(st, offset)
        if ok:
            self._mark_done(st, attempt, extra, t0)
        else:
            self._fail(st, reason, detail, attempt)

    def _try_adopt(self, st):
        """处理上次遗留的 .running。返回 'rerun' / 'handled'。

        顺序：①同主机、pid 与启动时刻一致的子进程仍活 → 本地接管；②远端存活证据（GL 作业步名、
        存活文件）说在跑 → STEP_ADOPT_REMOTE 轮询等它结束；③无法确认死活（换了主机或 pid 未知、
        又没有任何可用证据）→ 报告能核对通过就采纳，否则 resume_unknown 需人工、绝不重跑
        （防止同一张卡上重复派发）；④确认已死 → 报告缺失才重跑。"""
        rm = self.marker(st["name"], "running")
        if not rm.exists():
            return "rerun"
        try:
            info = json.loads(rm.read_text())
        except (OSError, ValueError):
            info = {}
        offset = int(info.get("log_offset", 0))
        attempt = int(info.get("attempt", 1))
        pid, pstart = info.get("pid"), info.get("pid_start")
        t0 = float(info.get("unix_start", time.time()))
        to = st["timeout_s"]
        deadline = (t0 + float(to)) if to else None
        same_host = bool(pid) and bool(pstart) and info.get("host") == self.host
        if same_host and _proc_start(int(pid)) == pstart:
            # 子进程仍在跑：接管等待，绝不重复派发（P4「续行前检查各分支是否已经启动」）
            self._set(st["name"], "running")
            self.emit("STEP_ADOPT", lane=st["lane"], step=st["name"], pid=pid, attempt=attempt)
            if not self._wait_pid(int(pid), pstart, deadline):
                self._killpg_graceful(int(pid), lambda: _proc_start(int(pid)) != pstart)
                self._log_append(st["name"], "\nEXIT_CODE=timeout(adopted)\n")
                self._fail(st, "timeout", f"adopted pid={pid}", attempt)
                return "handled"
            self._finish_adopted(st, offset, attempt, t0, "adopted")
            return "handled"
        alive = self._remote_alive(st)
        if alive:
            self._set(st["name"], "running")
            self.emit("STEP_ADOPT_REMOTE", lane=st["lane"], step=st["name"], host=info.get("host", "?"),
                      attempt=attempt)
            while self._remote_alive(st):
                if deadline is not None and time.time() > deadline:
                    # 远端进程不归本编排器管，不 scancel（R7），交人工
                    self._fail(st, "resume_unknown", "远端接管超时仍在跑，需人工处理", attempt)
                    return "handled"
                time.sleep(self.remote_poll_s)
            self._finish_adopted(st, offset, attempt, t0, "adopted_remote")
            return "handled"
        rp = self.report_path(st)
        if alive is None and not same_host:
            ok, reason, detail, extra = self._verify(st, offset) if rp.exists() else (False, "", "", {})
            if ok:
                self.emit("STEP_RESUME", lane=st["lane"], step=st["name"], action="adopt_report")
                self._mark_done(st, attempt, extra, t0)
            else:
                self._fail(st, "resume_unknown",
                           f"上次在 host={info.get('host', '?')} pid={pid} 运行，无法确认是否仍在跑，不重跑", attempt)
            return "handled"
        if not rp.exists():
            self.emit("STEP_RESUME", lane=st["lane"], step=st["name"], action="rerun", why="report_missing")
            return "rerun"
        ok, reason, detail, extra = self._verify(st, offset)
        if ok:
            self.emit("STEP_RESUME", lane=st["lane"], step=st["name"], action="adopt_report")
            self._mark_done(st, attempt, extra, t0)
        else:
            self._fail(st, "resume_unverified", f"报告已存在但核对不过（{reason}: {detail}），不覆盖、不重跑", attempt)
        return "handled"

    def run_step(self, st):
        name = st["name"]
        prior_attempt = 0
        rm = self.marker(name, "running")
        if rm.exists():
            try:
                prior_attempt = int(json.loads(rm.read_text()).get("attempt", 0))
            except (OSError, ValueError):
                prior_attempt = 0
            if self._try_adopt(st) == "handled":
                return
        cmd = self._subst(st["cmd"], st)
        argv, env = build_command(st["lane_where"], cmd, self.srun, name)
        max_attempts = 1 + st["retries"]
        t0 = time.time()
        for k in range(1, max_attempts + 1):
            attempt = prior_attempt + k
            lp = self.log_path(name)
            with open(lp, "a") as f:
                f.write(f"=== ATTEMPT {attempt} ts={_now()} host={self.host} ===\n")
                offset = f.tell()
            self._set(name, "running")
            self.emit("STEP_START", lane=st["lane"], step=name, attempt=attempt,
                      where="local" if st["lane_where"] == "local" else f"gl:{st['lane_where']['gl_jobid']}")
            try:
                logf = open(lp, "ab")
                proc = subprocess.Popen(argv, stdout=logf, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                        env=env, cwd=str(self.workdir), start_new_session=True)
                logf.close()
            except OSError as e:
                self._log_append(name, f"\nSPAWN_ERROR {e}\nEXIT_CODE=spawn_error\n")
                reason, detail = "spawn_error", str(e)
            else:
                _write_json_atomic(rm, {"step": name, "lane": st["lane"], "pid": proc.pid,
                                        "pid_start": _proc_start(proc.pid), "host": self.host,
                                        "attempt": attempt, "log_offset": offset, "argv": argv,
                                        "unix_start": time.time(), "ts": _now()})
                to = st["timeout_s"]
                try:
                    rc = proc.wait(timeout=float(to) if to else None)
                    self._log_append(name, f"\nEXIT_CODE={rc}\n")
                    reason, detail = ("exit", f"rc={rc}") if rc != 0 else ("", "")
                except subprocess.TimeoutExpired:
                    self._killpg_graceful(proc.pid, lambda: proc.poll() is not None)
                    proc.wait()
                    self._log_append(name, f"\nTIMEOUT after {to}s\nEXIT_CODE=timeout\n")
                    reason, detail = "timeout", f"timeout_s={to}"
            if not reason:
                ok, reason, detail, extra = self._verify(st, offset)
                if ok:
                    self._mark_done(st, attempt, extra, t0)
                    return
                self._fail(st, reason, detail, attempt)
                return
            if reason in INFRA_REASONS and k < max_attempts:
                self.emit("STEP_RETRY", lane=st["lane"], step=name, attempt=attempt, reason=reason, detail=detail)
                continue
            self._fail(st, reason, detail, attempt)
            return

    def run_lane(self, lane):
        try:
            for sn in lane["step_names"]:
                if self.stop_evt.is_set():
                    return
                st = self.steps[sn]
                st["lane_where"] = lane["where"]
                if self.status.get(sn) in ("done", "fail", "skipped"):
                    continue
                blocked = self._wait_deps(st)
                if blocked:
                    self._fail(st, "upstream", f"upstream={blocked}")
                    continue
                try:
                    self.run_step(st)
                except Exception as e:  # noqa: BLE001  编排器自身异常：记为需人工，不吞掉
                    self._fail(st, "orch_error", repr(e))
        finally:
            c = {k: 0 for k in STATUS_KEYS}
            for sn in lane["step_names"]:
                c[self.status.get(sn, "pending")] += 1
            if not self.stop_evt.is_set():
                self.emit("LANE_DONE", lane=lane["name"], **c)
                self.notify("stage_done", lane["name"], event="LANE_DONE", counts=c)

    def run(self) -> int:
        self.restore()
        self.phase = "running"
        self.write_heartbeat()
        hb = threading.Thread(target=self._heartbeat_loop, daemon=True)
        hb.start()
        seat = threading.Thread(target=self._seat_loop, daemon=True)
        seat.start()
        threads = [threading.Thread(target=self.run_lane, args=(ln,), name=f"lane-{ln['name']}", daemon=True)
                   for ln in self.plan["lanes"]]
        for t in threads:
            t.start()
        for t in threads:
            while t.is_alive():
                t.join(timeout=1.0)
        s = self.summary()
        blocking_fail = sum(1 for sn, i in self.fail_info.items()
                            if self.status.get(sn) == "fail" and i.get("blocking", True))
        verdict = "PASS" if s["counts"]["done"] == s["total"] else ("PARTIAL" if blocking_fail == 0 else "FAIL")
        self.phase = "done"
        self.stop_evt.set()
        self.write_heartbeat()
        self.emit("ORCH_DONE", verdict=verdict, total=s["total"], blocking_fail=blocking_fail, **s["counts"])
        self.notify("stage_done", "orch", event="ORCH_DONE", verdict=verdict, counts=s["counts"],
                    fail_reasons=s["fail_reasons"])
        return 0 if blocking_fail == 0 and s["counts"]["skipped"] == 0 else 1


def dry_run(plan, state: Path) -> None:
    for lane in plan["lanes"]:
        w = lane["where"]
        ws = "local" if w == "local" else f"gl:{w['gl_jobid']}"
        for sn in lane["step_names"]:
            st = plan["steps"][sn]
            stt = "pending"
            for k in ("done", "fail", "running"):
                if (state / f"{sn}.{k}").exists():
                    stt = k
                    break
            deps = st["needs"] + ([st["prev"]] if st["prev"] else [])
            print(f"DRYRUN lane={lane['name']} step={sn} where={ws} needs={','.join(deps) or '-'} "
                  f"blocking={int(st['blocking'])} retries={st['retries']} timeout_s={st['timeout_s']} state={stt}")
            print(f"  cmd: {st['cmd']}")
    print(f"DRYRUN_OK lanes={len(plan['lanes'])} steps={len(plan['steps'])}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="v7.5eval 通用编排器")
    ap.add_argument("--plan", required=True)
    ap.add_argument("--state", required=True)
    ap.add_argument("--workdir", default=".")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--retry-failed", action="store_true", help="清掉 .fail（原文件改名留档）后重跑")
    ap.add_argument("--heartbeat-s", type=float, default=30.0)
    ap.add_argument("--seat-check-s", type=float, default=600.0)
    ap.add_argument("--srun", default="srun")
    ap.add_argument("--squeue", default="squeue")
    ap.add_argument("--poll-s", type=float, default=1.0)
    ap.add_argument("--term-grace-s", type=float, default=120.0, help="超时 SIGTERM 后等多久再 SIGKILL（≥90 s）")
    ap.add_argument("--remote-poll-s", type=float, default=30.0, help="接管远端存活步骤时的轮询间隔")
    a = ap.parse_args(argv)
    try:
        plan = load_plan(a.plan)
    except (PlanError, ValueError, OSError, re.error) as e:
        print(f"PLAN_INVALID err={_clean(e)}", flush=True)
        return 2
    state = Path(a.state).resolve()
    if a.dry_run:
        dry_run(plan, state)
        return 0
    state.mkdir(parents=True, exist_ok=True)
    lock = open(state / "orch.lock", "a+")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print(f"ORCH_LOCKED state={state}（已有编排器在用此状态目录）", flush=True)
        return 3
    orch = Orchestrator(plan, state, Path(a.workdir), heartbeat_s=a.heartbeat_s, seat_check_s=a.seat_check_s,
                        srun=a.srun, squeue=a.squeue, retry_failed=a.retry_failed, poll_s=a.poll_s,
                        term_grace_s=a.term_grace_s, remote_poll_s=a.remote_poll_s)
    return orch.run()


if __name__ == "__main__":
    sys.exit(main())
