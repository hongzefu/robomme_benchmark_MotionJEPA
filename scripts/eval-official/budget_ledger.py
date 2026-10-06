#!/usr/bin/env python3
"""第二阶段跨原侧／新侧共享的预算账本（1005-eval-video-phase2-all-models-rerun-plan.md 第二部分一节「S8 预算与额度」、
六节预算、R6、R11）。

一个账本文件（JSONL，追加写 + fsync）由所有席位、两侧路线共同读写；每次领取都在 ``<账本>.lock`` 的独占
``fcntl.flock`` 下「读全量 → 判额度 → 追加一行」，所以并发争抢最后一个额度只有一方成功；全部计数从账本内容推出，
进程重启、换节点都不刷新额度。

行（``kind``）：

* ``reserve``：预约一局（一条轨迹）与 ``resets`` 次 reset 计量；字段 ``rid``／``route``／``key``／``astra``；
* ``commit``：该局收尾；可带实际 reset 次数 ``resets``（不带时按预约数与实领数取大）；
* ``release``：该局未进入执行（如开局前被拒），轨迹名额退回；已实领的 reset 仍计入；
* ``reset_claim``：新侧 ``EnvSession._claim`` 每次实际 build／reset 记一行（挂在某个 ``rid`` 下）；
* ``retry_claim``：基础设施重试名额；``interrupt`` ∈ {``infra``，``expired``}，分别计数——``infra`` 占共享 infra
  额度，``expired``（有 Slurm 到期证据）占到期续跑额度；同一 ``route``+``key`` 至多 ``V8_MAX_ATTEMPTS-1`` 次重试。

上限（六节）：轨迹 6366 硬上限；reset 计量 141430 为软上限（超过只打印 ``BUDGET_WARN``，不拦）；Astra 局数 2 硬上限；
共享 infra 重试 50、到期续跑 500（两者都在 6366 之内，按预约另计轨迹）。

CLI::

    budget_ledger.py [--ledger PATH] reserve --resets N [--route R] [--key K] [--astra]
    budget_ledger.py [--ledger PATH] commit --id RID [--resets N]
    budget_ledger.py [--ledger PATH] release --id RID
    budget_ledger.py [--ledger PATH] claim-retry --route R --key K --interrupt infra|expired
    budget_ledger.py [--ledger PATH] report

``--ledger`` 缺省取环境变量 ``SGEVAL_BUDGET_LEDGER``。``reserve`` 成功时末行打印 ``BUDGET_RESERVE rid=<rid> ...``
（标准输出最后一个字段即 rid，可被启动器取用）；额度不足打印 ``RUN_BLOCKED reason=budget ...`` 并以退出码 5 退出。
``report`` 末行固定为 ``BUDGET_ENFORCEMENT=PASS|FAIL trajectories=<used>/<cap> resets=<used>/<soft> astra=<used>/2
shared_infra=<used>/<cap>``。
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import socket
import sys
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any

#: 六节预算：轨迹硬上限、reset 计量软上限（十倍）、Astra 局数硬上限、共享 infra 重试、到期续跑
TRAJECTORY_CAP = 6366
RESET_SOFT_CAP = 141430
ASTRA_CAP = 2
SHARED_INFRA_CAP = 50
EXPIRED_CAP = 500
#: 与 env_client.V8_MAX_ATTEMPTS 相同口径：每身份至多 2 次尝试（首试 + 1 次重试，infra 与 expired 合计）
V8_MAX_ATTEMPTS = 2
INTERRUPTS = ("infra", "expired")
ENV_LEDGER = "SGEVAL_BUDGET_LEDGER"
EXIT_BUDGET = 5


class BudgetExhausted(RuntimeError):
    """硬上限（轨迹、Astra、共享 infra／到期续跑、每身份重试名额）不足：调用方在进入 attempt 前拒绝。"""

    budget_exhausted = True


def _dumps(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False)


def _canonical_row(row: Any) -> Any:
    """历史账本行的旧路线名映射成官方名（别名表在 ``official_defs.py``，已加载则复用同一模块）。"""
    mod = sys.modules.get("official_defs")
    if mod is None:
        import importlib.util

        spec = importlib.util.spec_from_file_location("official_defs", Path(__file__).resolve().parent / "official_defs.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules["official_defs"] = mod
        spec.loader.exec_module(mod)
    return mod.canonical_row(row)


class BudgetState:
    """从账本行推出的计数（只读快照）。"""

    def __init__(self, rows: list[dict]):
        self.reserves: dict[str, dict] = {}
        self.commits: dict[str, dict] = {}
        self.releases: set[str] = set()
        self.claimed: dict[str, int] = {}  # rid -> reset_claim 行数
        self.orphan_claims = 0  # 无 rid 的 reset_claim
        self.retries: list[dict] = []
        self.bad_rows = 0
        for row in rows:
            kind = row.get("kind")
            rid = row.get("rid")
            if kind == "reserve" and rid:
                self.reserves.setdefault(rid, row)
            elif kind == "commit" and rid:
                self.commits.setdefault(rid, row)
            elif kind == "release" and rid:
                self.releases.add(rid)
            elif kind == "reset_claim":
                if rid:
                    self.claimed[rid] = self.claimed.get(rid, 0) + 1
                else:
                    self.orphan_claims += 1
            elif kind == "retry_claim":
                self.retries.append(row)
            else:
                self.bad_rows += 1

    def live(self, rid: str) -> bool:
        return rid in self.reserves and rid not in self.releases

    @property
    def trajectories(self) -> int:
        """未退回的预约数（进行中 + 已收尾）。"""
        return sum(self.live(r) for r in self.reserves)

    @property
    def astra(self) -> int:
        return sum(self.live(r) and bool(row.get("astra")) for r, row in self.reserves.items())

    def resets_of(self, rid: str) -> int:
        """单局 reset 计量：退回的只计实领；收尾带实际数的取实际数与实领数之大；其余取预约数与实领数之大。"""
        claimed = self.claimed.get(rid, 0)
        if rid in self.releases:
            return claimed
        com = self.commits.get(rid)
        if com is not None and com.get("resets") is not None:
            return max(int(com["resets"]), claimed)
        return max(int(self.reserves[rid].get("resets") or 0), claimed)

    @property
    def resets(self) -> int:
        return sum(self.resets_of(r) for r in self.reserves) + self.orphan_claims

    def retries_of(self, interrupt: str) -> int:
        return sum(r.get("interrupt") == interrupt for r in self.retries)

    def retries_for(self, route: str, key: str) -> int:
        return sum(r.get("route") == route and r.get("key") == key for r in self.retries)


class BudgetLedger:
    """共享预算账本。``caps`` 可覆盖（单测用），缺省取六节常量。"""

    def __init__(self, path: Path | str, *, trajectory_cap: int = TRAJECTORY_CAP, reset_soft_cap: int = RESET_SOFT_CAP,
                 astra_cap: int = ASTRA_CAP, shared_infra_cap: int = SHARED_INFRA_CAP, expired_cap: int = EXPIRED_CAP,
                 warn_stream=None):
        self.path = Path(path)
        self.lock_path = self.path.with_name(self.path.name + ".lock")
        self.trajectory_cap = int(trajectory_cap)
        self.reset_soft_cap = int(reset_soft_cap)
        self.astra_cap = int(astra_cap)
        self.shared_infra_cap = int(shared_infra_cap)
        self.expired_cap = int(expired_cap)
        self.warn_stream = warn_stream

    # ── 底层：文件锁 + 读全量 + 追加 ─────────────────────────────────────
    @contextmanager
    def _locked(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.lock_path, os.O_RDWR | os.O_CREAT, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)

    def _read(self) -> list[dict]:
        if not self.path.exists():
            return []
        rows = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(_canonical_row(json.loads(line)))
            except json.JSONDecodeError:
                rows.append({"kind": "__bad__"})  # 半行（写入中被杀）：计 bad_rows，report 判 FAIL
        return rows

    def _append(self, row: dict) -> dict:
        row = {"t": time.time(), "host": socket.gethostname(), "pid": os.getpid(),
               "slurm_job_id": os.environ.get("SLURM_JOB_ID"), **row}
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(_dumps(row) + "\n")
            f.flush()
            os.fsync(f.fileno())
        return row

    def state(self) -> BudgetState:
        with self._locked():
            return BudgetState(self._read())

    def _warn_resets(self, st: BudgetState, extra: int = 0) -> None:
        total = st.resets + extra
        if total > self.reset_soft_cap:
            print(f"BUDGET_WARN resets={total} soft={self.reset_soft_cap}（软上限，只告警不拦）",
                  file=self.warn_stream or sys.stderr, flush=True)

    # ── 领取 ────────────────────────────────────────────────────────────
    def reserve(self, *, resets: int, route: str | None = None, key: str | None = None, astra: bool = False,
                **extra) -> str:
        """预约一局：轨迹与 Astra 是硬上限（不足抛 BudgetExhausted，不写行）；reset 只做软告警。返回 rid。"""
        resets = int(resets)
        if resets < 0:
            raise ValueError("resets 不能为负")
        with self._locked():
            st = BudgetState(self._read())
            if st.trajectories >= self.trajectory_cap:
                raise BudgetExhausted(f"trajectories={st.trajectories}/{self.trajectory_cap}")
            if astra and st.astra >= self.astra_cap:
                raise BudgetExhausted(f"astra={st.astra}/{self.astra_cap}")
            self._warn_resets(st, resets)
            rid = uuid.uuid4().hex
            self._append({"kind": "reserve", "rid": rid, "resets": resets, "route": route, "key": key,
                          "astra": bool(astra), **extra})
            return rid

    def _need_rid(self, st: BudgetState, rid: str) -> None:
        if rid not in st.reserves:
            raise KeyError(f"未知 rid={rid}")

    def commit(self, rid: str, *, resets: int | None = None, **extra) -> None:
        with self._locked():
            st = BudgetState(self._read())
            self._need_rid(st, rid)
            if rid in st.commits or rid in st.releases:
                return  # 重复收尾：幂等
            self._append({"kind": "commit", "rid": rid, "resets": None if resets is None else int(resets), **extra})

    def release(self, rid: str, **extra) -> None:
        with self._locked():
            st = BudgetState(self._read())
            self._need_rid(st, rid)
            if rid in st.commits or rid in st.releases:
                return
            self._append({"kind": "release", "rid": rid, **extra})

    def claim_reset(self, rid: str | None, what: str, **extra) -> None:
        """记一次实际 build／reset（软上限：超过只告警，从不抛）。"""
        with self._locked():
            st = BudgetState(self._read())
            self._warn_resets(st, 1)
            self._append({"kind": "reset_claim", "rid": rid, "what": what, **extra})

    def claim_retry(self, *, route: str, key: str, interrupt: str, **extra) -> bool:
        """原子领一次基础设施重试名额；``infra`` 占共享 infra 额度、``expired`` 占到期续跑额度，同一 route+key 至多
        ``V8_MAX_ATTEMPTS-1`` 次。成功返回 True，任一不足返回 False（不写行）。"""
        if interrupt not in INTERRUPTS:
            raise ValueError(f"interrupt={interrupt!r} 不是 {INTERRUPTS} 之一")
        cap = self.shared_infra_cap if interrupt == "infra" else self.expired_cap
        with self._locked():
            st = BudgetState(self._read())
            if st.retries_of(interrupt) >= cap:
                return False
            if st.retries_for(route, key) >= V8_MAX_ATTEMPTS - 1:
                return False
            self._append({"kind": "retry_claim", "route": route, "key": key, "interrupt": interrupt, **extra})
            return True

    # ── 汇总 ────────────────────────────────────────────────────────────
    def report_lines(self) -> tuple[bool, list[str]]:
        st = self.state()
        problems = []
        if st.trajectories > self.trajectory_cap:
            problems.append("trajectories_over_cap")
        if st.astra > self.astra_cap:
            problems.append("astra_over_cap")
        if st.retries_of("infra") > self.shared_infra_cap:
            problems.append("shared_infra_over_cap")
        if st.retries_of("expired") > self.expired_cap:
            problems.append("expired_over_cap")
        if st.bad_rows:
            problems.append(f"bad_rows={st.bad_rows}")
        open_n = sum(st.live(r) and r not in st.commits for r in st.reserves)
        lines = [f"BUDGET_DETAIL ledger={self.path} reserves={len(st.reserves)} committed={len(st.commits)} "
                 f"released={len(st.releases)} open={open_n} expired={st.retries_of('expired')}/{self.expired_cap} "
                 f"reset_soft_exceeded={int(st.resets > self.reset_soft_cap)}"]
        if problems:
            lines.append(f"BUDGET_PROBLEMS {' '.join(problems)}")
        ok = not problems
        lines.append(f"BUDGET_ENFORCEMENT={'PASS' if ok else 'FAIL'} trajectories={st.trajectories}/{self.trajectory_cap} "
                     f"resets={st.resets}/{self.reset_soft_cap} astra={st.astra}/{self.astra_cap} "
                     f"shared_infra={st.retries_of('infra')}/{self.shared_infra_cap}")
        return ok, lines


# ── CLI ─────────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="第二阶段共享预算账本（轨迹／reset／Astra／基础设施重试）")
    ap.add_argument("--ledger", default=None, help=f"账本 JSONL；缺省取环境变量 {ENV_LEDGER}")
    ap.add_argument("--trajectory-cap", type=int, default=TRAJECTORY_CAP)
    ap.add_argument("--reset-soft-cap", type=int, default=RESET_SOFT_CAP)
    ap.add_argument("--astra-cap", type=int, default=ASTRA_CAP)
    ap.add_argument("--shared-infra-cap", type=int, default=SHARED_INFRA_CAP)
    ap.add_argument("--expired-cap", type=int, default=EXPIRED_CAP)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("reserve")
    p.add_argument("--resets", type=int, required=True)
    p.add_argument("--route", default=None)
    p.add_argument("--key", default=None)
    p.add_argument("--astra", action="store_true")
    p = sub.add_parser("commit")
    p.add_argument("--id", required=True)
    p.add_argument("--resets", type=int, default=None)
    p = sub.add_parser("release")
    p.add_argument("--id", required=True)
    p = sub.add_parser("claim-retry")
    p.add_argument("--route", required=True)
    p.add_argument("--key", required=True)
    p.add_argument("--interrupt", required=True, choices=list(INTERRUPTS))
    sub.add_parser("report")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    path = args.ledger or os.environ.get(ENV_LEDGER)
    if not path:
        print(f"RUN_BLOCKED reason=budget detail=未给 --ledger 且 {ENV_LEDGER} 为空", flush=True)
        return 3
    led = BudgetLedger(path, trajectory_cap=args.trajectory_cap, reset_soft_cap=args.reset_soft_cap,
                       astra_cap=args.astra_cap, shared_infra_cap=args.shared_infra_cap, expired_cap=args.expired_cap)
    if args.cmd == "reserve":
        try:
            rid = led.reserve(resets=args.resets, route=args.route, key=args.key, astra=args.astra)
        except BudgetExhausted as e:
            print(f"RUN_BLOCKED reason=budget detail={e} route={args.route} key={args.key}", flush=True)
            return EXIT_BUDGET
        print(f"BUDGET_RESERVE resets={args.resets} route={args.route} key={args.key} astra={int(args.astra)} rid={rid}",
              flush=True)
        return 0
    if args.cmd == "commit":
        led.commit(args.id, resets=args.resets)
        print(f"BUDGET_COMMIT rid={args.id} resets={args.resets}", flush=True)
        return 0
    if args.cmd == "release":
        led.release(args.id)
        print(f"BUDGET_RELEASE rid={args.id}", flush=True)
        return 0
    if args.cmd == "claim-retry":
        ok = led.claim_retry(route=args.route, key=args.key, interrupt=args.interrupt)
        print(f"BUDGET_RETRY ok={int(ok)} route={args.route} key={args.key} interrupt={args.interrupt}", flush=True)
        return 0 if ok else EXIT_BUDGET
    ok, lines = led.report_lines()
    for line in lines:
        print(line, flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
