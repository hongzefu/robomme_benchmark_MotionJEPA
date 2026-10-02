#!/usr/bin/env python3
"""v8 gen1 之后的接续脚本：核验最终报告 → 守卫 → 建站 → 浏览器检查 → 通知（v8 方案第二部分 §2.4.4、§2.12 S2-D）。

AGENTS.md P4 的落地：不只听「完成行」，而是读取并核验 gen1 聚合产物 ``delivery.json``（``v8-delivery/1``）；
守卫判定行全部 PASS 才建站；任一 FAIL 停在报告、写通知事件、不建站。每步写心跳文件，供独立的
``v8_watchdog.py`` 按 mtime 判停更（本脚本自身崩溃或卡死时由 watchdog 报出，不靠本脚本自报）。

步骤（按序；``--cmd STEP=…`` 可替换任一步的命令，测试用假命令替换浏览器检查器等）：

1. ``wait_report``：等 ``--delivery`` 出现（``--wait-timeout`` 秒内；给了 ``--gen-log`` 时还要等到 ``EXIT_CODE=`` 行
   且为 0）。超时 → FAIL（「完成行超时未到」）。
2. ``report``：核 ``delivery.json``——``schema == v8-delivery/1``、``exec_cap == 1600``、``specs_root`` 与 ``--specs-root``
   为同一路径、``cells_table`` 与 ``--cells`` 格表相等、``counts`` 的计数键**显式存在**且为非负整数（零值也必须写出，
   不用 ``.get(k, 0)`` 兜底）、``line`` 以 ``V8_DELIVERY_SET=PASS`` 开头且 ``total=`` 等于 ``counts.delivered`` 与
   ``len(rows)``、``failed_cells == 0``。
3. ``delivery_set``：``hard_regression.py delivery-set`` → ``V8_DELIVERY_SET``／``V8_SEED_DISJOINT``／
   ``V8_LAYOUT_INDEPENDENT`` 三行 PASS，且 ``total=`` 与报告一致。
4. ``tier_values``：``hard_regression.py tier-values`` → ``V8_TIER_VALUES=PASS``。
5. ``step_headroom``：``hard_regression.py step-headroom --delivery … --pool … --xhard0 …`` → ``V8_STEP_CAP=PASS``。
   未给 ``--xhard0-steps`` 时改带 ``--skip-xhard0``，该步记 **INFO**（不冒充 PASS）：默认就此停下不建站，
   ``--allow-xhard0-info`` 时继续建站但最终判定也只能是 ``V8_CONTINUE=INFO``。
6. ``identities``：给了 ``--identities`` 就用它；否则在 ``--work-dir`` 下合成身份清单（见下）。
7. ``catalog``：``site/v8_site_catalog.py`` → ``V8_SITE_CATALOG=PASS``。
8. ``subgoals``：``site/v8_subgoal_lengths.py`` → ``V8_SUBGOALS=PASS``。
9. ``serve``：起服务前探端口占用（``--port 0`` 由系统分配）；``site/v8_site.py`` 打出 ``V8_SITE_READY`` 视为就绪。
10. ``site_check``／``oracle_check``：两个浏览器检查器 → ``V8_SITE=PASS``、``V8_ORACLE_BROWSER=PASS``。
11. ``stop_serve``：finally 中收掉服务进程组（SIGTERM → 5 秒 → SIGKILL）；SIGTERM／SIGHUP／SIGINT 同样走 finally。

**身份清单（3b 前可用的做法）**：``export_eval_identities.py`` 须在 3b 换包后跑，而 gen1 验收后即建站（不等 3b）。
未给 ``--identities`` 时，本脚本合成 ``<work-dir>/eval-identities-<n>.jsonl``：v8 新值局取 ``delivery.json`` 的
``rows``（task／tier／seed／candidate），xhard0 取 ``--xhard0-manifest``（缺省 ``scripts/configs/newtask-v7/
xhard0_manifest.json`` 的 192 行；也接受 ``manifest-H.jsonl`` 形态）的 task／seed／episode（记为 ``source_episode``）；
``round``／``shard`` 置空，``episode`` 按 (tier, task, seed) 排序编号。站点 catalog 只按 (tier, task, seed) 对账，
不依赖 builder 的 episode 编号；总数仍由 catalog 按表 2 核 1262。合成文件已存在时只在内容逐字节相同时复用。

**产物**（全部在 ``--work-dir``）：``heartbeat.json``（加锁成功后立即写一次本轮心跳，覆盖上一轮遗留；之后每步、
每 ``--beat-s`` 秒与子进程每行输出时原子替换；拒绝执行（退出码 2）时记 ``status=aborted``；
``step``／``status``／``ts``／``epoch``／``pid``／``child_pid``／``server_pid``／``counts``，计数键显式写零）、
``progress.json``（已完成步骤，供崩溃后续行）、``logs/<step>.log``、``report.json``（schema
``v8-continue-report/1``：每步判定行原文、退出码、耗时；以 ``os.link`` 独占写入，从不覆盖）。
事件日志（``--event-log``，缺省 ``<work-dir>/events.log``，与 watchdog 共用、只追加）逐步写
``V8_CONTINUE_STEP step=<名> status=<PASS|FAIL|INFO|SKIP> …``，失败写 ``P4_NOTIFY=FAIL step=<名> reason=…``，
收尾写 ``V8_CONTINUE=PASS|FAIL|INFO step=<名> …``（stdout 同样打印）。

**重复调用（同一完成事件重复到达）**：``report.json`` 已存在 → 先核 schema、输入指纹（delivery.json 的 sha256、
各输入路径、格表）与完整性（每步都有记录、有收尾行），全部相符才复用：不重跑任何步骤、不覆盖任何文件，
重打一行带 ``reused=1`` 的 ``V8_CONTINUE``，退出码与原报告一致；指纹不符 → 拒绝（退出码 2），换新 ``--work-dir``。
没有报告但有 ``progress.json``（上次中途崩溃）→ 只跑未完成步骤（已 PASS 的步骤核其产物 sha256 后复用）。
同一 ``--work-dir`` 用 ``flock`` 互斥，第二个并发实例直接退出（防重复派发）。

退出码：0 = PASS，1 = FAIL，3 = INFO，2 = 参数／报告身份冲突，130 = 被信号中断（不写 report.json，可续行）。

主检出仓库根执行（gen1 rsync 回 /data 并 ``aggregate --rebase`` 之后；完整命令见 S2-D 交回的运行手册）::

    uv run --no-sync python scripts/injection-dev/v8_continue_after_gen.py \\
      --delivery artifacts/newtask-v8/gen1/delivery.local.json --specs-root artifacts/newtask-v8/specs-root \\
      --xhard0-steps artifacts/newtask-v7/parity/h5/H-xhard0 --work-dir artifacts/newtask-v8/continue \\
      --site-dir artifacts/newtask-v8/site --port 8090
"""
from __future__ import annotations

import argparse
import datetime as _dt
import fcntl
import hashlib
import importlib.util
import json
import os
import re
import selectors
import shlex
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
SITE = REPO_ROOT / "scripts/injection-dev/site"
HARD_REGRESSION = REPO_ROOT / "scripts/parity/hard_regression.py"
DEFAULT_XHARD0_GEN = REPO_ROOT / "artifacts/newtask-v7/site-media/xhard0-gen"
DEFAULT_XHARD0_MANIFEST = REPO_ROOT / "scripts/configs/newtask-v7/xhard0_manifest.json"

REPORT_SCHEMA = "v8-continue-report/1"
HEARTBEAT_SCHEMA = "v8-continue-heartbeat/1"
PROGRESS_SCHEMA = "v8-continue-progress/1"
DELIVERY_SCHEMA = "v8-delivery/1"
EXEC_CAP = 1600
#: delivery.json ``counts`` 必须显式写出的键（与 S2-B ``_rollout.V8_TOTAL_COUNT_KEYS`` 同一清单，零值也写）
DELIVERY_COUNT_KEYS = ("expected", "candidates", "tried", "delivered", "failed", "exec_over_cap", "backfills",
                       "infra_retries", "spares_left", "pending", "bad_h5", "exhausted_cells", "pending_cells",
                       "failed_cells")
#: 心跳与报告的计数键（全部显式写零）
COUNT_KEYS = ("steps_done", "steps_failed", "steps_info", "steps_reused", "delivered", "failed", "exec_over_cap",
              "filtered", "backfills", "infra_retries")
STEPS = ("wait_report", "report", "delivery_set", "tier_values", "step_headroom", "identities", "catalog", "subgoals",
         "serve", "site_check", "oracle_check", "stop_serve")
GUARD_STEPS = ("delivery_set", "tier_values", "step_headroom")
#: 每步必须出现的判定行名（取最后一次出现）
EXPECT = {
    "delivery_set": ("V8_DELIVERY_SET", "V8_SEED_DISJOINT", "V8_LAYOUT_INDEPENDENT"),
    "tier_values": ("V8_TIER_VALUES",),
    "step_headroom": ("V8_STEP_CAP",),
    "catalog": ("V8_SITE_CATALOG",),
    "subgoals": ("V8_SUBGOALS",),
    "site_check": ("V8_SITE",),
    "oracle_check": ("V8_ORACLE_BROWSER",),
}
READY_RE = re.compile(r"^V8_SITE_READY\b.*\bport=(\d+)")
#: 缺省命令模板：``{名}`` 逐 token 替换；``@pool``／``@xhard0_args``／``@cells_json_args`` 展开为多个 token
DEFAULT_CMDS = {
    "delivery_set": ["{python}", "{hard_regression}", "delivery-set", "--specs-root", "{specs_root}", "--cells", "{cells}"],
    "tier_values": ["{python}", "{hard_regression}", "tier-values", "--specs-root", "{specs_root}", "--cells", "{cells}"],
    "step_headroom": ["{python}", "{hard_regression}", "step-headroom", "--delivery", "{delivery}", "--pool", "@pool",
                      "@xhard0_args"],
    "catalog": ["{python}", "{site}/v8_site_catalog.py", "--specs-root", "{specs_root}", "--delivery", "{delivery}",
                "--identities", "{identities}", "--xhard0-gen", "{xhard0_gen}", "--path-base", "{path_base}",
                "@cells_json_args", "--out", "{site_dir}"],
    "subgoals": ["{python}", "{site}/v8_subgoal_lengths.py", "--site-dir", "{site_dir}", "--specs-root", "{specs_root}",
                 "--delivery", "{delivery}", "--xhard0-gen", "{xhard0_gen}", "--path-base", "{path_base}",
                 "--workers", "{workers}"],
    "serve": ["{python}", "-u", "{site}/v8_site.py", "--host", "{host}", "--port", "{port}", "--site-dir", "{site_dir}",
              "--media-root", "{media_root}"],
    "site_check": ["uv", "run", "--no-project", "--with", "playwright", "python", "{site}/v8_site_browser_check.py",
                   "--base", "{base}", "--shots", "{shots}/site"],
    "oracle_check": ["uv", "run", "--no-project", "--with", "playwright", "python", "{site}/v8_oracle_browser_check.py",
                     "--base", "{base}", "--shots", "{shots}/oracle", "--delivery", "{delivery}",
                     "--expect-cells", "{expect_cells}"],
}
DEFAULT_TIMEOUTS = {"delivery_set": 1800, "tier_values": 1800, "step_headroom": 3600, "catalog": 1800,
                    "subgoals": 3600, "serve": 120, "site_check": 1800, "oracle_check": 1800}


class Interrupted(Exception):
    def __init__(self, signum: int):
        super().__init__(f"signal {signum}")
        self.signum = signum


def now_iso() -> str:
    return _dt.datetime.now().astimezone().isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def real(path: str | Path | None) -> str | None:
    return None if path is None else os.path.realpath(os.path.abspath(str(path)))


def write_json_atomic(path: Path, payload: Any) -> None:
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def write_json_exclusive(path: Path, payload: Any) -> None:
    """独占写入：目标已存在即抛 FileExistsError（从不覆盖）。"""
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    try:
        os.link(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def append_line(path: Path, line: str) -> None:
    """事件日志只追加；一次 ``os.write``（O_APPEND）写整行，与 watchdog 并发追加不交错。"""
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(fd, (line.rstrip("\n") + "\n").encode("utf-8"))
    finally:
        os.close(fd)


def parse_kv(line: str) -> dict[str, str]:
    return dict(m.groups() for m in re.finditer(r"(\w+)=(\S+)", line))


def verdict_lines(lines: list[str], names: tuple[str, ...]) -> dict[str, str | None]:
    """每个判定行名取最后一次出现的原文（``NAME=PASS|FAIL|INFO`` 开头，``V8_SITE`` 不会误配 ``V8_SITE_READY``）。"""
    out: dict[str, str | None] = {name: None for name in names}
    for raw in lines:
        line = raw.strip()
        for name in names:
            if re.match(rf"^{re.escape(name)}=(PASS|FAIL|INFO)\b", line):
                out[name] = line
    return out


def load_catalog_module():
    spec = importlib.util.spec_from_file_location("v8_site_catalog_c", SITE / "v8_site_catalog.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["v8_site_catalog_c"] = module
    spec.loader.exec_module(module)
    return module


def parse_cells_arg(spec: str, full: dict[tuple[str, str], int]) -> dict[tuple[str, str], int]:
    """``full``（表 2 的 43 格）或 JSON 文件（``{"Task/tier": n}``，与 catalog ``--cells-json`` 同形态）。"""
    if spec == "full":
        return dict(full)
    raw = json.loads(Path(spec).read_text(encoding="utf-8"))
    cells: dict[tuple[str, str], int] = {}
    for key, n in raw.items():
        task, sep, tier = str(key).partition("/")
        if not sep:
            raise SystemExit(f"--cells JSON 键应为 Task/tier：{key!r}")
        cells[(task, tier)] = int(n)
    return cells


def delivery_cells_table(delivery: dict) -> dict[tuple[str, str], int] | None:
    table = delivery.get("cells_table")
    if not isinstance(table, dict):
        return None
    out = {}
    for key, n in table.items():
        task, sep, tier = str(key).partition("@")
        if not sep:
            return None
        out[(task, tier)] = n
    return out


def load_xhard0_rows(path: Path) -> list[dict]:
    """xhard0 192 局：``xhard0_manifest.json``（``rows``）或 ``manifest-H.jsonl`` 形态（每行 task／seed／episode）。"""
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".jsonl":
        rows = [json.loads(t) for t in text.splitlines() if t.strip()]
    else:
        payload = json.loads(text)
        rows = payload["rows"] if isinstance(payload, dict) else payload
    return [{"task": r["task"], "seed": int(r["seed"]), "source_episode": r.get("episode")} for r in rows]


def synth_identities(delivery: dict, xhard0_rows: list[dict]) -> list[dict]:
    """3b 前的身份清单：v8 行取 delivery.rows，xhard0 行取 xhard0 清单；``episode`` 按 (tier, task, seed) 编号。"""
    rows = [{"candidate": int(r["candidate"]), "episode": None, "round": None, "seed": int(r["seed"]), "shard": None,
             "source_episode": None, "task": r["task"], "tier": r["tier"]} for r in delivery["rows"]]
    rows += [{"candidate": None, "episode": None, "round": None, "seed": r["seed"], "shard": None,
              "source_episode": r["source_episode"], "task": r["task"], "tier": "xhard0"} for r in xhard0_rows]
    rows.sort(key=lambda r: (r["tier"], r["task"], r["seed"]))
    for i, row in enumerate(rows):
        row["episode"] = i
    return rows


class Runner:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.work = Path(args.work_dir)
        self.heartbeat = Path(args.heartbeat) if args.heartbeat else self.work / "heartbeat.json"
        self.event_log = Path(args.event_log) if args.event_log else self.work / "events.log"
        self.report_path = self.work / "report.json"
        self.progress_path = self.work / "progress.json"
        self.logs = self.work / "logs"
        self.counts = {key: 0 for key in COUNT_KEYS}
        self.steps: dict[str, dict] = {}
        self.step = "init"
        self.status = "running"
        self.child: subprocess.Popen | None = None
        self.server: subprocess.Popen | None = None
        self.last_beat = 0.0
        self.seq = 0
        self.base: str | None = None
        self.prev_steps: dict[str, dict] = {}
        self.vars: dict[str, Any] = {}

    # ── 心跳、事件、进度 ───────────────────────────────────────────

    def beat(self, *, force: bool = False) -> None:
        now = time.time()
        if not force and now - self.last_beat < 1.0:
            return
        self.last_beat = now
        self.seq += 1
        write_json_atomic(self.heartbeat, {
            "schema": HEARTBEAT_SCHEMA, "step": self.step, "status": self.status, "ts": now_iso(), "epoch": now,
            "seq": self.seq, "pid": os.getpid(),
            "child_pid": self.child.pid if self.child and self.child.poll() is None else None,
            "server_pid": self.server.pid if self.server and self.server.poll() is None else None,
            "report": str(self.report_path), "counts": dict(self.counts),
        })

    def event(self, line: str) -> None:
        print(line, flush=True)
        append_line(self.event_log, line)

    def save_progress(self) -> None:
        write_json_atomic(self.progress_path, {"schema": PROGRESS_SCHEMA, "fingerprint": self.fingerprint,
                                               "steps": self.steps, "counts": self.counts, "ts": now_iso()})

    def record(self, step: str, status: str, *, rc: int | None = None, lines: list[str] | None = None,
               elapsed: float = 0.0, reason: str | None = None, log: Path | None = None, reused: bool = False,
               extra: dict | None = None) -> dict:
        entry = {"step": step, "status": status, "rc": rc, "lines": lines or [], "elapsed_s": round(elapsed, 3),
                 "reason": reason, "log": str(log) if log else None, "reused": reused, "ended": now_iso(),
                 **(extra or {})}
        self.steps[step] = entry
        if reused:
            self.counts["steps_reused"] += 1
        if status == "PASS":
            self.counts["steps_done"] += 1
        elif status == "FAIL":
            self.counts["steps_failed"] += 1
        elif status == "INFO":
            self.counts["steps_info"] += 1
        self.status = status.lower()
        self.beat(force=True)
        self.save_progress()
        self.event(f"V8_CONTINUE_STEP step={step} status={status} rc={rc} elapsed_s={entry['elapsed_s']:.1f}"
                   + (f" reused=1" if reused else "") + (f" reason={reason}" if reason else ""))
        return entry

    # ── 子进程 ────────────────────────────────────────────────────

    def command(self, step: str) -> list[str]:
        template = self.vars["cmd_overrides"].get(step, DEFAULT_CMDS[step])
        out: list[str] = []
        for token in template:
            if token == "@pool":
                out += self.vars["pool"]
            elif token == "@xhard0_args":
                out += (["--xhard0", self.vars["xhard0_steps"]] if self.vars["xhard0_steps"] else ["--skip-xhard0"])
            elif token == "@cells_json_args":
                out += (["--cells-json", self.vars["cells_json"]] if self.vars["cells_json"] else [])
            else:
                out.append(token.format(**{k: v for k, v in self.vars.items() if isinstance(v, (str, int))}))
        return out

    def run_child(self, step: str, argv: list[str], timeout: float) -> tuple[int | None, list[str], str | None, Path]:
        """跑一步子进程（独立进程组），逐行落 ``logs/<step>.log`` 并回显；子进程活着时每 ``--beat-s`` 秒心跳。"""
        log = self.logs / f"{step}.log"
        lines: list[str] = []
        env = dict(os.environ, PYTHONUNBUFFERED="1")
        with open(log, "a", encoding="utf-8") as handle:
            handle.write(f"# {now_iso()} argv={shlex.join(argv)}\n")
            handle.flush()
            self.child = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=REPO_ROOT,
                                          env=env, start_new_session=True)
            self.beat(force=True)
            fd = self.child.stdout.fileno()
            sel = selectors.DefaultSelector()
            sel.register(fd, selectors.EVENT_READ)
            buf, deadline, reason = b"", time.time() + timeout, None

            def take(chunk: bytes) -> None:
                nonlocal buf
                buf += chunk
                while b"\n" in buf:
                    raw, buf = buf.split(b"\n", 1)
                    text = raw.decode("utf-8", "replace")
                    lines.append(text)
                    handle.write(text + "\n")
                    handle.flush()
                    print(f"[{step}] {text}", flush=True)

            try:
                while True:
                    # 至多 1 秒醒一次查子进程是否已退出；心跳按 --beat-s 节奏写
                    events = sel.select(timeout=min(1.0, self.args.beat_s, max(0.05, deadline - time.time())))
                    if events:
                        chunk = os.read(fd, 65536)
                        if not chunk:
                            break
                        take(chunk)
                        self.beat()
                    else:
                        if time.time() - self.last_beat >= self.args.beat_s:
                            self.beat(force=True)
                        if self.child.poll() is not None:
                            # 子进程已退出、管道却被遗留的孙进程占着：先非阻塞读尽管道里剩下的数据再退出，不丢判定行
                            os.set_blocking(fd, False)
                            while True:
                                try:
                                    chunk = os.read(fd, 65536)
                                except BlockingIOError:
                                    break
                                if not chunk:
                                    break
                                take(chunk)
                            break
                    if time.time() > deadline:
                        reason = f"timeout_{int(timeout)}s"
                        break
            finally:
                sel.close()
            if buf:
                text = buf.decode("utf-8", "replace")
                lines.append(text)
                handle.write(text + "\n")
            # 无论组长怎么结束（正常退出、超时、遗留孙进程），都对整组收尾：孙进程不成孤儿
            rc = kill_group(self.child) if reason else self.child.wait()
            if reason is None:
                kill_group(self.child)
            self.child.stdout.close()
            handle.write(f"# {now_iso()} EXIT_CODE={rc}\n")
        self.child = None
        return rc, lines, reason, log

    def run_step(self, step: str) -> dict:
        self.step, self.status = step, "running"
        self.beat(force=True)
        started = time.time()
        rc, lines, reason, log = self.run_child(step, self.command(step), self.vars["timeouts"][step])
        found = verdict_lines(lines, EXPECT[step])
        kept = [line for line in found.values() if line]
        status = "PASS"
        if reason:
            status = "FAIL"
        elif rc != 0:
            status, reason = "FAIL", f"exit_{rc}"
        missing = [name for name, line in found.items() if line is None]
        if status == "PASS" and missing:
            status, reason = "FAIL", "line_missing:" + ",".join(missing)
        not_pass = [name for name, line in found.items() if line and not line.startswith(f"{name}=PASS")]
        if status == "PASS" and not_pass:
            info_ok = (step == "step_headroom" and not self.vars["xhard0_steps"] and not_pass == ["V8_STEP_CAP"]
                       and found["V8_STEP_CAP"].startswith("V8_STEP_CAP=INFO"))
            status, reason = ("INFO", "xhard0_skipped") if info_ok else ("FAIL", "verdict:" + ",".join(not_pass))
        if status in ("PASS", "INFO") and step == "delivery_set":
            total = parse_kv(found["V8_DELIVERY_SET"]).get("total")
            if total is None or int(total) != self.counts["delivered"]:
                status, reason = "FAIL", f"total_mismatch:guard={total},report={self.counts['delivered']}"
        if step == "step_headroom" and found["V8_STEP_CAP"]:
            filtered = parse_kv(found["V8_STEP_CAP"]).get("filtered")
            if filtered is not None and filtered.isdigit():
                self.counts["filtered"] = int(filtered)
        return self.record(step, status, rc=rc, lines=kept, elapsed=time.time() - started, reason=reason, log=log)

    # ── 各步 ──────────────────────────────────────────────────────

    def wait_report(self) -> dict:
        self.step, self.status = "wait_report", "running"
        started = time.time()
        delivery, gen_log = Path(self.args.delivery), self.args.gen_log
        deadline = started + self.args.wait_timeout
        while True:
            self.beat()
            exit_line = None
            if gen_log and Path(gen_log).is_file():
                exit_line = next((l for l in reversed(Path(gen_log).read_text(errors="replace").splitlines())
                                  if l.startswith("EXIT_CODE=")), None)
            parsed = False
            if delivery.is_file():
                try:  # 写到一半／不完整的 JSON 视为未就绪，继续等
                    json.loads(delivery.read_text(encoding="utf-8"))
                    parsed = True
                except (OSError, ValueError):
                    parsed = False
            if parsed and (not gen_log or exit_line):
                lines = [f"delivery={delivery}"] + ([exit_line] if exit_line else [])
                if exit_line and exit_line.strip() != "EXIT_CODE=0":
                    return self.record("wait_report", "FAIL", lines=lines, elapsed=time.time() - started,
                                       reason=f"gen_{exit_line.strip()}")
                return self.record("wait_report", "PASS", lines=lines, elapsed=time.time() - started)
            if time.time() >= deadline:
                what = ("delivery.json" if not delivery.is_file() else
                        "delivery.json可解析内容" if not parsed else "EXIT_CODE行")
                return self.record("wait_report", "FAIL", elapsed=time.time() - started,
                                   reason=f"timeout_{int(self.args.wait_timeout)}s:{what}未出现",
                                   lines=[f"delivery={delivery} exists={int(delivery.is_file())}"])
            time.sleep(min(self.args.poll_s, max(0.05, deadline - time.time())))

    def check_report(self) -> dict:
        self.step, self.status = "report", "running"
        self.beat(force=True)
        started = time.time()
        problems: list[str] = []
        try:
            delivery = json.loads(Path(self.args.delivery).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            return self.record("report", "FAIL", elapsed=time.time() - started, reason=f"unreadable:{type(exc).__name__}")
        if not isinstance(delivery, dict):
            return self.record("report", "FAIL", elapsed=time.time() - started, reason="not_object")
        if delivery.get("schema") != DELIVERY_SCHEMA:
            problems.append(f"schema={delivery.get('schema')!r}")
        if delivery.get("exec_cap") != EXEC_CAP:
            problems.append(f"exec_cap={delivery.get('exec_cap')!r}")
        if real(delivery.get("specs_root")) != real(self.args.specs_root):
            problems.append(f"specs_root_mismatch:{delivery.get('specs_root')}")
        table = delivery_cells_table(delivery)
        if table != self.vars["cells_table"]:
            problems.append("cells_table_mismatch" if table is not None else "cells_table_absent")
        counts = delivery.get("counts")
        if not isinstance(counts, dict):
            counts = {}
            problems.append("counts_absent")
        absent = [k for k in DELIVERY_COUNT_KEYS if k not in counts]
        bad = [k for k in DELIVERY_COUNT_KEYS if k in counts and not (isinstance(counts[k], int) and counts[k] >= 0)]
        if absent:
            problems.append("count_keys_absent:" + ",".join(absent))
        if bad:
            problems.append("count_keys_bad:" + ",".join(bad))
        rows = delivery.get("rows") if isinstance(delivery.get("rows"), list) else None
        if rows is None:
            problems.append("rows_absent")
        line = delivery.get("line") if isinstance(delivery.get("line"), str) else ""
        if not line.startswith("V8_DELIVERY_SET=PASS"):
            problems.append("line_not_pass" if line else "line_absent")
        total = parse_kv(line).get("total")
        if line and (total is None or not total.isdigit() or int(total) != counts.get("delivered")
                     or rows is None or int(total) != len(rows)):
            problems.append(f"total_mismatch:line={total},counts={counts.get('delivered')},"
                            f"rows={None if rows is None else len(rows)}")
        if "failed_cells" in counts and counts["failed_cells"] != 0:  # 缺键已计入 count_keys_absent，不兜底为 0
            problems.append(f"failed_cells={counts['failed_cells']}")
        for key in ("delivered", "failed", "exec_over_cap", "backfills", "infra_retries"):
            if isinstance(counts.get(key), int):
                self.counts[key] = counts[key]
        self.vars["delivery_obj"] = delivery
        lines = [line] if line else []
        lines.append("counts=" + json.dumps({k: counts.get(k, "ABSENT") for k in DELIVERY_COUNT_KEYS},
                                            ensure_ascii=False, separators=(",", ":")))
        status = "FAIL" if problems else "PASS"
        return self.record("report", status, lines=lines, elapsed=time.time() - started,
                           reason=";".join(problems)[:600] if problems else None)

    def identities(self) -> dict:
        self.step, self.status = "identities", "running"
        self.beat(force=True)
        started = time.time()
        if self.args.identities:
            path = Path(self.args.identities)
            if not path.is_file():
                return self.record("identities", "FAIL", elapsed=time.time() - started, reason=f"missing:{path}")
            self.vars["identities"] = str(path)
            n = sum(1 for t in path.read_text(encoding="utf-8").splitlines() if t.strip())
            return self.record("identities", "PASS", elapsed=time.time() - started,
                               lines=[f"IDENTITIES source=given rows={n} path={path}"],
                               extra={"sha256": sha256_file(path), "source": "given"})
        try:
            x0 = load_xhard0_rows(Path(self.args.xhard0_manifest))
            rows = synth_identities(self.vars["delivery_obj"], x0)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            return self.record("identities", "FAIL", elapsed=time.time() - started,
                               reason=f"synth_error:{type(exc).__name__}:{exc}"[:300])
        text = "".join(json.dumps(r, sort_keys=True) + "\n" for r in rows)
        path = self.work / f"eval-identities-{len(rows)}.jsonl"
        if path.exists():
            if path.read_text(encoding="utf-8") != text:
                return self.record("identities", "FAIL", elapsed=time.time() - started,
                                   reason=f"exists_differs:{path}")
            reused = True
        else:
            with open(path, "x", encoding="utf-8") as handle:
                handle.write(text)
            reused = False
        self.vars["identities"] = str(path)
        n_x0 = sum(r["tier"] == "xhard0" for r in rows)
        return self.record("identities", "PASS", elapsed=time.time() - started,
                           lines=[f"IDENTITIES source=synthesized rows={len(rows)} v8={len(rows) - n_x0} xhard0={n_x0} "
                                  f"existing_reused={int(reused)} path={path}"],
                           extra={"sha256": sha256_file(path), "source": "synthesized",
                                  "xhard0_manifest": real(self.args.xhard0_manifest)})

    def serve(self) -> dict:
        self.step, self.status = "serve", "running"
        self.beat(force=True)
        started = time.time()
        host, port = self.args.host, int(self.args.port)
        if port and port_busy(host, port):
            return self.record("serve", "FAIL", elapsed=time.time() - started, reason=f"port_busy:{host}:{port}")
        log = self.logs / "serve.log"
        handle = open(log, "a", encoding="utf-8")
        argv = self.command("serve")
        handle.write(f"# {now_iso()} argv={shlex.join(argv)}\n")
        handle.flush()
        offset = handle.tell()  # 续行时日志里还有上一次服务的就绪行，只认本次启动之后写入的内容
        # 服务输出直接落文件（不走管道），请求日志再多也不会因管道写满而卡住服务
        self.server = subprocess.Popen(argv, stdout=handle, stderr=subprocess.STDOUT, cwd=REPO_ROOT,
                                       env=dict(os.environ, PYTHONUNBUFFERED="1"), start_new_session=True)
        handle.close()
        deadline = started + self.vars["timeouts"]["serve"]
        while True:
            self.beat()
            with open(log, "rb") as reader:
                reader.seek(offset)
                text = reader.read().decode("utf-8", "replace")
            ready =next((l for l in text.splitlines() if READY_RE.match(l)), None)
            if ready:
                actual = int(READY_RE.match(ready).group(1))
                self.base = f"http://{'127.0.0.1' if host in ('0.0.0.0', '') else host}:{actual}"
                self.vars["base"], self.vars["port_actual"] = self.base, actual
                return self.record("serve", "PASS", rc=None, lines=[ready], elapsed=time.time() - started, log=log,
                                   extra={"server_pid": self.server.pid, "base": self.base})
            if self.server.poll() is not None:
                return self.record("serve", "FAIL", rc=self.server.returncode, elapsed=time.time() - started, log=log,
                                   reason="server_exited", lines=text.splitlines()[-3:])
            if time.time() > deadline:
                return self.record("serve", "FAIL", elapsed=time.time() - started, log=log, reason="ready_timeout")
            time.sleep(0.1)

    def stop_serve(self) -> None:
        if self.server is None:
            return
        started = time.time()
        rc = kill_group(self.server)
        self.server = None
        if "serve" in self.steps and self.steps["serve"].get("status") == "PASS":
            prev = self.step
            self.step = "stop_serve"
            self.record("stop_serve", "PASS", rc=rc, elapsed=time.time() - started)
            self.step = prev

    # ── 续行与复用 ────────────────────────────────────────────────

    def reusable(self, step: str) -> bool:
        prev = self.prev_steps.get(step)
        if not prev or prev.get("status") != "PASS":
            return False
        if step == "catalog":
            paths = [Path(self.args.site_dir) / "catalog.json", Path(self.args.site_dir) / "media-private.json"]
        elif step == "subgoals":
            paths = [Path(self.args.site_dir) / "subgoals.json"]
        elif step == "identities":
            if prev.get("path_used") is None or not Path(prev["path_used"]).is_file():
                return False
            return sha256_file(Path(prev["path_used"])) == prev.get("sha256")
        else:
            return True
        return all(p.is_file() for p in paths) and prev.get("sha256s") == [sha256_file(p) for p in paths]

    def reuse(self, step: str) -> dict:
        prev = dict(self.prev_steps[step])
        self.step = step
        if step == "identities":
            self.vars["identities"] = prev["path_used"]
        if step == "step_headroom":
            for line in prev.get("lines", []):
                kv = parse_kv(line)
                if line.startswith("V8_STEP_CAP=") and kv.get("filtered", "").isdigit():
                    self.counts["filtered"] = int(kv["filtered"])
        extra = {k: v for k, v in prev.items() if k not in ("step", "status", "rc", "lines", "elapsed_s", "reason",
                                                             "log", "reused", "ended")}
        return self.record(step, prev["status"], rc=prev.get("rc"), lines=prev.get("lines"), elapsed=0.0,
                           reason=prev.get("reason"), reused=True,
                           log=Path(prev["log"]) if prev.get("log") else None, extra=extra)

    # ── 主流程 ────────────────────────────────────────────────────

    def finish(self, verdict: str, step: str, reason: str | None, site_built: bool, reused: bool = False) -> int:
        final = (f"V8_CONTINUE={verdict} step={step} steps={len(self.steps)} site={'built' if site_built else 'not_built'} "
                 f"delivered={self.counts['delivered']} filtered={self.counts['filtered']} "
                 f"exec_over_cap={self.counts['exec_over_cap']} backfills={self.counts['backfills']} "
                 f"infra_retries={self.counts['infra_retries']} reused={int(reused)}"
                 + (f" reason={reason}" if reason else "") + f" report={self.report_path}")
        report = {"schema": REPORT_SCHEMA, "fingerprint": self.fingerprint, "verdict": verdict, "final_step": step,
                  "reason": reason, "site_built": site_built, "site_dir": real(self.args.site_dir),
                  "counts": dict(self.counts), "steps": [self.steps[s] for s in STEPS if s in self.steps],
                  "final_line": final, "ended": now_iso(), "exit_code": EXIT_CODES[verdict]}
        self.step, self.status = step, "done"
        write_json_exclusive(self.report_path, report)
        self.beat(force=True)
        if verdict != "PASS":
            self.event(f"P4_NOTIFY={verdict} step={step} reason={reason} report={self.report_path}")
        self.event(final)
        return EXIT_CODES[verdict]

    def run(self) -> int:
        steps_order = [("wait_report", self.wait_report), ("report", self.check_report)]
        steps_order += [(s, lambda s=s: self.run_step(s)) for s in GUARD_STEPS]
        for name, fn in steps_order:
            if name in ("wait_report", "report") or not self.reusable(name):
                entry = fn()
            else:
                entry = self.reuse(name)
            if entry["status"] == "FAIL":
                return self.finish("FAIL", name, entry["reason"], False)
        info = self.steps["step_headroom"]["status"] == "INFO"
        if info and not self.args.allow_xhard0_info:
            return self.finish("INFO", "step_headroom", "xhard0_skipped_site_not_built", False)
        site = Path(self.args.site_dir)
        if not self.reusable("catalog") and site.exists() and any(site.iterdir()):
            self.step = "catalog"
            entry = self.record("catalog", "FAIL", reason=f"site_dir_not_empty:{site}")
            return self.finish("FAIL", "catalog", entry["reason"], False)
        for name in ("identities", "catalog", "subgoals"):
            if self.reusable(name):
                entry = self.reuse(name)
            elif name == "identities":
                entry = self.identities()
                entry["path_used"] = self.vars.get("identities")
                self.save_progress()
            else:
                entry = self.run_step(name)
                if entry["status"] == "PASS":
                    paths = ([site / "catalog.json", site / "media-private.json"] if name == "catalog"
                             else [site / "subgoals.json"])
                    entry["sha256s"] = [sha256_file(p) for p in paths]
                    self.save_progress()
            if entry["status"] == "FAIL":
                return self.finish("FAIL", name, entry["reason"], False)
        if self.reusable("site_check") and self.reusable("oracle_check"):
            for name in ("serve", "site_check", "oracle_check", "stop_serve"):
                if name in self.prev_steps:
                    self.reuse(name)
        else:
            Path(self.vars["shots"]).mkdir(parents=True, exist_ok=True)
            try:
                entry = self.serve()
                if entry["status"] == "FAIL":
                    return self.finish("FAIL", "serve", entry["reason"], False)
                for name in ("site_check", "oracle_check"):
                    entry = self.run_step(name)
                    if entry["status"] == "FAIL":
                        self.stop_serve()
                        return self.finish("FAIL", name, entry["reason"], False)
            finally:
                self.stop_serve()
        verdict = "INFO" if info else "PASS"
        return self.finish(verdict, "done", "xhard0_skipped" if info else None, True)


EXIT_CODES = {"PASS": 0, "FAIL": 1, "INFO": 3}


def _group_alive(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def kill_group(proc: subprocess.Popen, grace: float = 5.0) -> int | None:
    """收掉子进程所在进程组（子进程以 ``start_new_session`` 启动，组号 = 其 pid；只按这个精确组号发信号）。

    组长已退出也照样对整组发信号：``uv run`` 下的 playwright 驱动／chromium 等孙进程留在同一组里，组长退出后
    不收就成孤儿。SIGTERM → 等组空（``killpg(pgid, 0)``）至 ``grace`` 秒 → SIGKILL → 再等至 5 秒。"""
    pgid = proc.pid
    for sig, wait in ((signal.SIGTERM, grace), (signal.SIGKILL, 5.0)):
        if proc.poll() is not None and not _group_alive(pgid):
            break
        try:
            os.killpg(pgid, sig)
        except ProcessLookupError:
            break
        deadline = time.time() + wait
        while time.time() < deadline:
            proc.poll()  # 回收组长，免得僵尸让组看起来还活着
            if proc.returncode is not None and not _group_alive(pgid):
                break
            time.sleep(0.05)
    try:
        return proc.wait(timeout=5.0)
    except subprocess.TimeoutExpired:
        return proc.poll()


def port_busy(host: str, port: int) -> bool:
    target = "127.0.0.1" if host in ("0.0.0.0", "") else host
    try:
        with socket.create_connection((target, port), timeout=1.0):
            return True
    except OSError:
        return False


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--delivery", required=True, help="gen1 聚合产物 delivery.json（v8-delivery/1）")
    ap.add_argument("--specs-root", required=True, help="v8 /4 规格根（须与 delivery.json 的 specs_root 为同一路径）")
    ap.add_argument("--cells", default="full", help="full（表 2 的 43 格）或 {\"Task/tier\": n} JSON 文件")
    ap.add_argument("--work-dir", required=True, help="心跳、进度、日志、报告目录（同一完成事件复用同一目录）")
    ap.add_argument("--site-dir", required=True, help="站点输出目录（首次须不存在或为空）")
    ap.add_argument("--event-log", default=None, help="事件日志（缺省 <work-dir>/events.log；与 watchdog 共用）")
    ap.add_argument("--heartbeat", default=None, help="心跳文件（缺省 <work-dir>/heartbeat.json）")
    ap.add_argument("--gen-log", default=None, help="可选：生成日志，须出现 EXIT_CODE=0 才算完成")
    ap.add_argument("--wait-timeout", type=float, default=0.0, help="等报告出现的秒数（缺省 0 = 必须已存在）")
    ap.add_argument("--poll-s", type=float, default=5.0, help="等报告时的轮询间隔秒")
    ap.add_argument("--beat-s", type=float, default=30.0, help="子进程运行期间的心跳间隔秒（须小于 watchdog 阈值）")
    ap.add_argument("--pool", nargs="+", default=None, help="step-headroom 的 --pool（缺省 = --specs-root）")
    ap.add_argument("--xhard0-steps", default=None,
                    help="step-headroom 的 --xhard0 来源（如 artifacts/newtask-v7/parity/h5/H-xhard0）；不给则该步 INFO")
    ap.add_argument("--allow-xhard0-info", action="store_true",
                    help="step-headroom 为 INFO 时仍建站（最终判定 V8_CONTINUE=INFO，不出 PASS）")
    ap.add_argument("--identities", default=None, help="现成身份清单；不给则在 work-dir 合成（3b 前）")
    ap.add_argument("--xhard0-manifest", default=str(DEFAULT_XHARD0_MANIFEST),
                    help="合成身份清单的 xhard0 来源（xhard0_manifest.json 或 manifest-H.jsonl）")
    ap.add_argument("--xhard0-gen", default=str(DEFAULT_XHARD0_GEN), help="v7 已渲染的 xhard0 生成视频目录")
    ap.add_argument("--path-base", default=str(REPO_ROOT), help="catalog／subgoals 的 --path-base")
    ap.add_argument("--media-root", default=str(REPO_ROOT / "artifacts"), help="站点服务媒体白名单根")
    ap.add_argument("--workers", type=int, default=16, help="subgoals 的 --workers")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8090, help="站点服务端口（0 = 系统分配）；占用即 FAIL")
    ap.add_argument("--shots", default=None, help="浏览器截图目录（缺省 <work-dir>/shots）")
    ap.add_argument("--step-timeout", action="append", default=[], metavar="STEP=SECONDS",
                    help=f"覆盖单步超时（缺省 {DEFAULT_TIMEOUTS}）")
    ap.add_argument("--cmd", action="append", default=[], metavar="STEP=COMMAND",
                    help="替换某步命令（shlex 切分；可用 {python} {delivery} {base} {shots} 等占位与 @pool 等展开）")
    return ap


def fingerprint_of(args: argparse.Namespace, cells: dict, overrides: dict) -> dict:
    delivery = Path(args.delivery)
    return {
        "delivery": real(delivery), "delivery_sha256": sha256_file(delivery) if delivery.is_file() else None,
        "specs_root": real(args.specs_root), "cells": {f"{t}/{tier}": n for (t, tier), n in sorted(cells.items())},
        "site_dir": real(args.site_dir), "xhard0_steps": real(args.xhard0_steps), "xhard0_gen": real(args.xhard0_gen),
        "identities": real(args.identities), "xhard0_manifest": real(args.xhard0_manifest),
        "allow_xhard0_info": bool(args.allow_xhard0_info), "cmd_overrides": {k: v for k, v in sorted(overrides.items())},
        "pool": [real(p) for p in (args.pool or [args.specs_root])], "path_base": real(args.path_base),
        "media_root": real(args.media_root), "workers": int(args.workers), "host": args.host, "port": int(args.port),
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    work = Path(args.work_dir)
    work.mkdir(parents=True, exist_ok=True)
    (work / "logs").mkdir(exist_ok=True)
    lock_handle = open(work / ".lock", "a")
    try:
        fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print(f"V8_CONTINUE_BUSY work_dir={work} reason=another_instance_running", flush=True)
        return 2
    # 加锁成功后立即写本轮心跳：覆盖上一轮遗留的 aborted／过期心跳，watchdog 据 mtime 与 pid 认本轮
    hb_path = Path(args.heartbeat) if args.heartbeat else work / "heartbeat.json"
    write_json_atomic(hb_path, {"schema": HEARTBEAT_SCHEMA, "step": "init", "status": "starting", "ts": now_iso(),
                                "epoch": time.time(), "seq": 0, "pid": os.getpid(), "child_pid": None,
                                "server_pid": None, "report": str(work / "report.json"),
                                "counts": {key: 0 for key in COUNT_KEYS}})
    C = load_catalog_module()
    H = C.load_hard_specs()
    cells = parse_cells_arg(args.cells, dict(H.V8_CELLS))
    overrides: dict[str, list[str]] = {}
    for item in args.cmd:
        step, sep, cmd = item.partition("=")
        if not sep or step not in DEFAULT_CMDS:
            raise SystemExit(f"--cmd 须为 STEP=COMMAND，STEP ∈ {sorted(DEFAULT_CMDS)}：{item!r}")
        overrides[step] = shlex.split(cmd)
    timeouts = dict(DEFAULT_TIMEOUTS)
    for item in args.step_timeout:
        step, sep, sec = item.partition("=")
        if not sep or step not in timeouts:
            raise SystemExit(f"--step-timeout 须为 STEP=SECONDS，STEP ∈ {sorted(timeouts)}：{item!r}")
        timeouts[step] = float(sec)
    runner = Runner(args)
    full = cells == dict(H.V8_CELLS)
    def refuse(step: str) -> int:
        """拒绝执行（参数／报告身份冲突）：心跳记 aborted，watchdog 立即报出而不是等停更。"""
        runner.step, runner.status = step, "aborted"
        runner.beat(force=True)
        return 2

    cells_json = None
    if not full:
        cells_json = work / "cells.json"
        text = json.dumps({f"{t}/{tier}": n for (t, tier), n in sorted(cells.items())}, ensure_ascii=False)
        if not cells_json.exists():
            cells_json.write_text(text, encoding="utf-8")
        elif cells_json.read_text(encoding="utf-8") != text:
            print(f"V8_CONTINUE=FAIL step=preflight reason=cells_json_differs:{cells_json}", flush=True)
            return refuse("preflight")
    runner.fingerprint = fingerprint_of(args, cells, {k: shlex.join(v) for k, v in overrides.items()})
    runner.vars = {
        "python": sys.executable, "hard_regression": str(HARD_REGRESSION), "site": str(SITE), "repo": str(REPO_ROOT),
        "delivery": str(args.delivery), "specs_root": str(args.specs_root),
        "cells": "full" if full else str(cells_json), "cells_json": None if full else str(cells_json),
        "cells_table": cells, "pool": list(args.pool or [str(args.specs_root)]), "xhard0_steps": args.xhard0_steps,
        "xhard0_gen": str(args.xhard0_gen), "path_base": str(args.path_base), "site_dir": str(args.site_dir),
        "media_root": str(args.media_root), "workers": str(args.workers), "host": args.host, "port": str(args.port),
        "shots": str(args.shots or work / "shots"), "work_dir": str(work), "base": "",
        "expect_cells": str(len(cells) + len(H.ALL_TASKS)), "identities": str(args.identities or ""),
        "cmd_overrides": overrides, "timeouts": timeouts,
    }

    # 同一完成事件重复到达：报告已在 → 核身份、来源、完整性后复用，不重跑、不覆盖
    if runner.report_path.exists():
        try:
            old = json.loads(runner.report_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            runner.event(f"V8_CONTINUE=FAIL step=resume reason=report_unreadable:{type(exc).__name__} "
                         f"reused=0 report={runner.report_path}")
            return refuse("resume")
        steps_ok = (isinstance(old, dict) and isinstance(old.get("steps"), list) and bool(old["steps"])
                    and all(isinstance(s, dict) and s.get("step") in STEPS and s.get("status") for s in old["steps"]))
        complete = (steps_ok and old.get("schema") == REPORT_SCHEMA
                    and str(old.get("final_line", "")).startswith(f"V8_CONTINUE={old.get('verdict')} ")
                    and old.get("verdict") in EXIT_CODES and old.get("exit_code") == EXIT_CODES[old["verdict"]]
                    and (old.get("final_step") == "done"
                         or old.get("final_step") in {s["step"] for s in old["steps"]})
                    and isinstance(old.get("counts"), dict)
                    and all(isinstance(old["counts"].get(k), int) for k in COUNT_KEYS))
        if not complete:
            runner.event(f"V8_CONTINUE=FAIL step=resume reason=report_incomplete reused=0 report={runner.report_path}")
            return refuse("resume")
        if old.get("fingerprint") != runner.fingerprint:
            diff = sorted(k for k in set(old.get("fingerprint", {})) | set(runner.fingerprint)
                          if old.get("fingerprint", {}).get(k) != runner.fingerprint.get(k))
            runner.event(f"V8_CONTINUE=FAIL step=resume reason=report_identity_mismatch:{','.join(diff)} reused=0 "
                         f"report={runner.report_path}")
            return refuse("resume")
        runner.step, runner.status = str(old.get("final_step")), "done"
        runner.counts = {key: old["counts"][key] for key in COUNT_KEYS}
        runner.beat(force=True)
        runner.event(old["final_line"].replace(" reused=0", " reused=1"))
        return int(old["exit_code"])

    if runner.progress_path.exists():
        try:
            prog = json.loads(runner.progress_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            prog = {}
        if prog.get("schema") == PROGRESS_SCHEMA and prog.get("fingerprint") == runner.fingerprint:
            runner.prev_steps = dict(prog.get("steps") or {})
            print(f"# 续行：上次已完成 {sorted(k for k, v in runner.prev_steps.items() if v.get('status') == 'PASS')}",
                  flush=True)
        else:
            runner.event(f"V8_CONTINUE=FAIL step=resume reason=progress_identity_mismatch reused=0 "
                         f"report={runner.report_path}")
            return refuse("resume")

    def on_signal(signum, _frame):
        raise Interrupted(signum)

    for sig in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
        signal.signal(sig, on_signal)
    runner.event(f"V8_CONTINUE_START pid={os.getpid()} work_dir={work} delivery={args.delivery} "
                 f"heartbeat={runner.heartbeat} resume={int(bool(runner.prev_steps))}")
    runner.beat(force=True)
    try:
        return runner.run()
    except Interrupted as exc:
        runner.status = "aborted"
        runner.beat(force=True)
        runner.save_progress()
        runner.event(f"V8_CONTINUE_ABORT step={runner.step} signal={exc.signum} report=absent（可续行）")
        return 130
    finally:
        for sig in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
            signal.signal(sig, signal.SIG_IGN)
        if runner.child is not None:
            kill_group(runner.child)
        if runner.server is not None:
            kill_group(runner.server)
        lock_handle.close()


if __name__ == "__main__":
    sys.exit(main())
