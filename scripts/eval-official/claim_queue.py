#!/usr/bin/env python3
"""v7.5eval 正式跑法的 NFS 认领队列（0929-v7.5eval-restructure-plan.md §5「分发」）。

（原名 queue.py 会遮蔽标准库 ``queue``，已改名 claim_queue.py；作为脚本运行时仍把本目录挪到 ``sys.path`` 末尾。）

目录布局（``<root>`` = ``queue/<policy>``）：

* ``identities.json``：身份清单（``[{task, source_episode, seed, builder_episode, ...}]``）；
* ``order.json``：认领顺序 ``{"keys": [...], "sha256": ..., "shuffle_seed": ...}``；
* ``claims/<task>_<seed>.claim``：``O_CREAT|O_EXCL`` 原子创建，内容 ``{seat, host, pid, time, attempt, token}``；
  持有者定期 ``touch`` 刷新 mtime 作进展心跳；
* ``done/<task>_<seed>.json``：唯一终态。先写临时文件再 ``os.link`` 到目标名（目标已存在即 ``EEXIST``），
  NFS 上 ``link`` 是原子的，所以终态文件要么完整存在、要么不存在，一个身份只可能有一个终态；
* ``requeue/<task>_<seed>.<reason>.<attempt>.claim``：被回收的认领（原子 ``rename``），无进展回收每身份只一次；
* ``retries/<n>.tok``：重试额度令牌，``O_EXCL`` 逐个领取，领满即额度用完（跨进程、跨重启持续有效）；
  额度上限写在 ``budget.json``；
* ``late/``：旧进程迟到提交（认领已不属于它）被拒后的留档。

不用 ``flock``（跨节点 NFS 锁不可靠）。
"""
from __future__ import annotations

import sys
from pathlib import Path as _Path

_HERE = str(_Path(__file__).resolve().parent)
if __name__ == "__main__":
    sys.path[:] = [p for p in sys.path if p and str(_Path(p).resolve()) != _HERE] + [_HERE]

import argparse  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import random  # noqa: E402
import socket  # noqa: E402
import time  # noqa: E402
import uuid  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Any, Iterable  # noqa: E402

DEFAULT_SHUFFLE_SEED = 20260930
DEFAULT_RETRY_BUDGET = 8
INFRA_EXHAUSTED = "INFRA_EXHAUSTED"


def dumps(obj: Any) -> str:
    """全仓统一 jsonl 口径：sort_keys + 不转义中文。"""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False)


def key_of(row: dict) -> str:
    """身份键 ``<task>_<seed>``。"""
    return f"{row['task']}_{int(row['seed'])}"


def _token_of(path: Path) -> str | None:
    """读目标文件里的认领 token（claim 文件的 token，或 done 文件的 _claim.token）。"""
    doc = _read_json(path)
    if not isinstance(doc, dict):
        return None
    return doc.get("token") or (doc.get("_claim") or {}).get("token")


def _excl_write(path: Path, text: str, token: str | None = None) -> bool:
    """``O_CREAT|O_EXCL`` 创建并写入；已存在返回 False。
    NFS 重传幂等：给了 token 且已存在的文件正是自己写的（token 相同）→ 视为成功。"""
    try:
        fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError:
        return token is not None and _token_of(path) == token
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    return True


def _link_publish(tmp: Path, target: Path, token: str | None = None) -> bool:
    """临时文件经 ``os.link`` 原子发布为 target；target 已存在返回 False（NFS 重传幂等：已存在的正是
    自己这次发布的，token 相同 → 视为成功）。临时文件总会删掉。"""
    try:
        os.link(str(tmp), str(target))
        return True
    except FileExistsError:
        return token is not None and _token_of(target) == token
    finally:
        try:
            os.unlink(str(tmp))
        except FileNotFoundError:
            pass


def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def read_jsonl_tolerant(path: Path) -> tuple[list[dict], int]:
    """读 jsonl，跳过写到一半的坏行（崩溃留下的半行），返回 (记录, 坏行数)。"""
    rows, bad = [], 0
    if not path.exists():
        return rows, 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            bad += 1
    return rows, bad


def append_jsonl(path: Path, record: dict) -> None:
    """追加一行；若上一行是崩溃留下的半行（文件末尾没有换行），先补换行，保证新记录独占一行。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "ab+") as f:
        f.seek(0, os.SEEK_END)
        if f.tell() > 0:
            f.seek(-1, os.SEEK_END)
            if f.read(1) != b"\n":
                f.write(b"\n")
        f.write((dumps(record) + "\n").encode("utf-8"))
        f.flush()
        os.fsync(f.fileno())


def _stub(key: str, **fields: Any) -> dict:
    """只知道身份键时的最小终态记录（task、seed 从键里拆出）。"""
    task, seed = key.rsplit("_", 1)
    return dict(fields, task=task, seed=int(seed))


class Claim(dict):
    """一次认领（claim 文件内容）。"""

    @property
    def key(self) -> str:
        return self["key"]

    @property
    def token(self) -> str:
        return self["token"]


class ClaimQueue:
    """一个策略的认领队列。所有写操作都是 ``O_EXCL`` 创建、``link`` 发布或 ``rename``，不依赖锁。"""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.claims = self.root / "claims"
        self.done = self.root / "done"
        self.requeue = self.root / "requeue"
        self.retries = self.root / "retries"
        self.late = self.root / "late"
        self.tmp = self.root / "tmp"

    # ── 初始化 ──────────────────────────────────────────────────────────
    @staticmethod
    def shuffled_keys(identities: list[dict], shuffle_seed: int) -> list[str]:
        """按 (task, source_episode) 排序后用 ``random.Random(shuffle_seed)`` 打乱。"""
        base = sorted(identities, key=lambda r: (r["task"], int(r["source_episode"])))
        keys = [key_of(r) for r in base]
        random.Random(shuffle_seed).shuffle(keys)
        return keys

    def init(self, identities: list[dict], *, order: str = "shuffle", shuffle_seed: int = DEFAULT_SHUFFLE_SEED,
             order_keys: list[str] | None = None, retry_budget: int = DEFAULT_RETRY_BUDGET) -> dict:
        """建目录、写身份与顺序。已初始化且内容一致则幂等返回；内容不一致报错（不覆盖已有队列）。"""
        keys_all = [key_of(r) for r in identities]
        if len(keys_all) != len(set(keys_all)):
            raise ValueError("身份清单里 <task>_<seed> 有重复")
        if order_keys is not None:
            keys = list(order_keys)
            if sorted(keys) != sorted(keys_all):
                raise ValueError("顺序文件与身份清单的键集合不一致")
            shuffle_seed_rec: Any = "external"
        elif order == "shuffle":
            keys, shuffle_seed_rec = self.shuffled_keys(identities, shuffle_seed), shuffle_seed
        elif order in ("forward", "reverse"):
            keys = list(keys_all) if order == "forward" else list(reversed(keys_all))
            shuffle_seed_rec = None
        else:
            raise ValueError(f"未知 order={order}")
        order_doc = {"keys": keys, "order": order if order_keys is None else "file", "shuffle_seed": shuffle_seed_rec,
                     "sha256": hashlib.sha256(dumps(keys).encode()).hexdigest()}
        ident_text = dumps(identities)
        for d in (self.claims, self.done, self.requeue, self.retries, self.late, self.tmp):
            d.mkdir(parents=True, exist_ok=True)
        for name, text in (("identities.json", ident_text), ("order.json", dumps(order_doc)),
                           ("budget.json", dumps({"retry_budget": int(retry_budget)}))):
            path = self.root / name
            if not _excl_write(path, text):
                if path.read_text(encoding="utf-8") != text:
                    raise RuntimeError(f"队列已初始化且 {name} 内容不同：{path}（不覆盖已有队列）")
        return order_doc

    def identities(self) -> list[dict]:
        return json.loads((self.root / "identities.json").read_text(encoding="utf-8"))

    def order(self) -> list[str]:
        return json.loads((self.root / "order.json").read_text(encoding="utf-8"))["keys"]

    def identity(self, key: str) -> dict:
        for row in self.identities():
            if key_of(row) == key:
                return row
        raise KeyError(key)

    # ── 认领 ────────────────────────────────────────────────────────────
    def _claim_path(self, key: str) -> Path:
        return self.claims / f"{key}.claim"

    def _done_path(self, key: str) -> Path:
        return self.done / f"{key}.json"

    def attempts(self, key: str) -> int:
        """该身份已被回收过几次（requeue 目录里的条目数）。"""
        return sum(1 for p in self.requeue.glob(f"{key}.*.claim"))

    def claim_next(self, seat: str, *, skip: Iterable[str] = ()) -> Claim | None:
        """按顺序认领第一个无终态、无人认领的身份；全部完成或被占返回 None。"""
        skip = set(skip)
        for key in self.order():
            if key in skip or self._done_path(key).exists() or self._claim_path(key).exists():
                continue
            claim = Claim(key=key, seat=seat, host=socket.gethostname(), pid=os.getpid(), time=time.time(),
                          attempt=self.attempts(key) + 1, token=uuid.uuid4().hex)
            if _excl_write(self._claim_path(key), dumps(claim), token=claim.token):
                if self._done_path(key).exists():  # 认领与别人提交终态交错：终态为准，撤回认领
                    self._drop_claim(claim)
                    continue
                return claim
        return None

    def read_claim(self, key: str) -> Claim | None:
        doc = _read_json(self._claim_path(key))
        return Claim(doc) if doc else None

    def owns(self, claim: Claim) -> bool:
        cur = self.read_claim(claim.key)
        return cur is not None and cur.get("token") == claim.token

    def heartbeat(self, claim: Claim) -> None:
        """刷新认领文件 mtime（进展心跳）；认领已不属于自己则不动。"""
        if self.owns(claim):
            try:
                os.utime(self._claim_path(claim.key))
            except FileNotFoundError:
                pass

    def _drop_claim(self, claim: Claim) -> None:
        if self.owns(claim):
            try:
                os.unlink(self._claim_path(claim.key))
            except FileNotFoundError:
                pass

    def _move_to_requeue(self, key: str, reason: str, expect_token: str | None = None) -> bool:
        cur = self.read_claim(key)
        if cur is None or (expect_token is not None and cur.get("token") != expect_token):
            return False
        dst = self.requeue / f"{key}.{reason}.{cur.get('attempt', 0)}.{cur.get('token', 'x')[:8]}.claim"
        try:
            os.rename(str(self._claim_path(key)), str(dst))  # 原子；两个回收者同时 rename 只有一个成功
            return True
        except FileNotFoundError:
            return False

    # ── 提交终态 ────────────────────────────────────────────────────────
    def complete(self, claim: Claim, record: dict) -> bool:
        """写唯一终态。认领已不属于本进程（被回收／被他人重领）→ 拒收、写 late/ 留档、返回 False。"""
        if not self.owns(claim):
            self._late(claim, record, "not_owner")
            return False
        doc = dict(record, _claim=dict(claim), _committed_at=time.time())
        tmp = self.tmp / f"{claim.key}.{claim.token}.json"
        tmp.write_text(dumps(doc), encoding="utf-8")
        if not _link_publish(tmp, self._done_path(claim.key), token=claim.token):
            self._late(claim, record, "done_exists")
            return False
        self._drop_claim(claim)
        return True

    def _late(self, claim: Claim, record: dict, why: str) -> None:
        self.late.mkdir(parents=True, exist_ok=True)
        _excl_write(self.late / f"{claim.key}.{claim.token}.json", dumps({"why": why, "claim": dict(claim),
                                                                          "record": record, "time": time.time()}))

    # ── 失败与回收 ──────────────────────────────────────────────────────
    def budget(self) -> int:
        doc = _read_json(self.root / "budget.json") or {}
        return int(doc.get("retry_budget", DEFAULT_RETRY_BUDGET))

    def retries_used(self) -> int:
        return sum(1 for _ in self.retries.glob("*.tok"))

    def take_retry(self, key: str) -> bool:
        """领一枚重试令牌；额度用完返回 False。"""
        for n in range(self.budget()):
            if _excl_write(self.retries / f"{n}.tok", dumps({"key": key, "time": time.time(), "pid": os.getpid()})):
                return True
        return False

    def fail_infra(self, claim: Claim, record: dict) -> str:
        """基础设施失败：有额度 → 回收认领待重跑（返回 "requeued"）；额度用完 → 写 INFRA_EXHAUSTED 终态。"""
        if not self.owns(claim):
            self._late(claim, record, "not_owner_fail")
            return "late"
        if self.take_retry(claim.key):
            self._move_to_requeue(claim.key, "infra", claim.token)
            return "requeued"
        self.complete(claim, dict(record, status="error", queue_status=INFRA_EXHAUSTED))
        return "exhausted"

    def reap_stale(self, threshold_s: float, *, now: float | None = None) -> list[str]:
        """认领超过 threshold_s 无进展（mtime 不更新）且无终态 → 回收一次；同一身份第二次无进展写 INFRA_EXHAUSTED 终态。"""
        now = time.time() if now is None else now
        acted = []
        for path in sorted(self.claims.glob("*.claim")):
            key = path.name[: -len(".claim")]
            try:
                age = now - path.stat().st_mtime
            except FileNotFoundError:
                continue
            if age <= threshold_s:
                continue
            if self._done_path(key).exists():
                try:
                    os.unlink(str(path))  # 终态已在，残留认领直接清掉
                except FileNotFoundError:
                    pass
                continue
            stale_before = sum(1 for _ in self.requeue.glob(f"{key}.stale.*.claim"))
            if stale_before == 0:
                if self._move_to_requeue(key, "stale"):
                    acted.append(key)
            else:
                cur = self.read_claim(key)
                if cur is not None:
                    self.complete(Claim(cur), _stub(key, status="error", queue_status=INFRA_EXHAUSTED,
                                                    error="认领两次无进展", infra=True))
                    acted.append(key)
        return acted

    def recover_seat(self, seat: str, results_path: Path | None) -> dict:
        """席位进程重启后收拾自己名下的残留认领：结果已写进 results.jsonl 但未提交 → 补提交；
        认领后崩溃、没有结果 → 按基础设施失败处理（消耗重试额度）。"""
        acked, failed = [], []
        rows, _ = read_jsonl_tolerant(results_path) if results_path else ([], 0)
        by_token = {r.get("claim_token"): r for r in rows if r.get("claim_token")}
        for path in sorted(self.claims.glob("*.claim")):
            doc = _read_json(path)
            if not doc or doc.get("seat") != seat:
                continue
            claim = Claim(doc)
            if doc.get("host") == socket.gethostname() and doc.get("pid") == os.getpid():
                continue
            rec = by_token.get(claim.token)
            if rec is not None and not rec.get("infra"):
                if self.complete(claim, rec):
                    acked.append(claim.key)
            else:
                self.fail_infra(claim, rec or _stub(claim.key, status="error", error="认领后进程崩溃，无结果",
                                                    infra=True))
                failed.append(claim.key)
        return {"acked": acked, "failed": failed}

    def all_terminal(self) -> bool:
        """顺序里的每个身份都已有终态（含 INFRA_EXHAUSTED 终态）。"""
        return all(self._done_path(k).exists() for k in self.order())

    # ── 核对 ────────────────────────────────────────────────────────────
    def check(self) -> dict:
        """dup = 非法／重复终态数；missing = 无终态身份数；requeued = 回收条目数。"""
        want = set(self.order())
        done_keys: dict[str, int] = {}
        bad = 0
        for p in self.done.glob("*.json"):
            key = p.name[: -len(".json")]
            doc = _read_json(p)
            if doc is None or key_of(doc) != key:
                bad += 1
                continue
            done_keys[key] = done_keys.get(key, 0) + 1
        dup = bad + sum(n - 1 for n in done_keys.values()) + len(set(done_keys) - want)
        missing = len(want - set(done_keys))
        exhausted = sum(1 for k in done_keys if (_read_json(self._done_path(k)) or {}).get("queue_status") == INFRA_EXHAUSTED)
        return {"dup": dup, "missing": missing, "requeued": sum(1 for _ in self.requeue.glob("*.claim")),
                "done": len(done_keys), "total": len(want), "late": sum(1 for _ in self.late.glob("*.json")),
                "open_claims": sum(1 for _ in self.claims.glob("*.claim")), "retries_used": self.retries_used(),
                "infra_exhausted": exhausted}


def check_line(stats: dict) -> str:
    ok = stats["dup"] == 0 and stats["missing"] == 0
    return (f"QUEUE_CLAIM={'PASS' if ok else 'FAIL'} dup={stats['dup']} missing={stats['missing']} "
            f"requeued={stats['requeued']} done={stats['done']} total={stats['total']} late={stats['late']} "
            f"open_claims={stats['open_claims']} retries_used={stats['retries_used']} "
            f"infra_exhausted={stats['infra_exhausted']}")


def _load_order_file(path: str) -> list[str]:
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    items = doc.get("keys", doc.get("order", doc)) if isinstance(doc, dict) else doc
    return [x if isinstance(x, str) else key_of(x) for x in items]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="v7.5eval NFS 认领队列")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init", help="从身份清单建队列")
    p.add_argument("--queue", required=True, help="队列根目录（其下按策略分目录）")
    p.add_argument("--policy", required=True, choices=["mme", "smvla"])
    p.add_argument("--identities", required=True)
    p.add_argument("--order", default="shuffle", choices=["shuffle", "forward", "reverse"])
    p.add_argument("--shuffle-seed", type=int, default=DEFAULT_SHUFFLE_SEED)
    p.add_argument("--order-file", default=None, help="外部给定的顺序（如 compare.py identities 产出），优先于 --order")
    p.add_argument("--retry-budget", type=int, default=DEFAULT_RETRY_BUDGET)
    p = sub.add_parser("check", help="核对终态唯一、无遗漏")
    p.add_argument("--queue", required=True)
    p.add_argument("--policy", required=True, choices=["mme", "smvla"])
    p = sub.add_parser("reap", help="回收无进展认领")
    p.add_argument("--queue", required=True)
    p.add_argument("--policy", required=True, choices=["mme", "smvla"])
    p.add_argument("--threshold-s", type=float, default=1200.0)
    args = ap.parse_args(argv)
    q = ClaimQueue(Path(args.queue) / args.policy)
    if args.cmd == "init":
        idents = json.loads(Path(args.identities).read_text(encoding="utf-8"))
        order_keys = _load_order_file(args.order_file) if args.order_file else None
        doc = q.init(idents, order=args.order, shuffle_seed=args.shuffle_seed, order_keys=order_keys,
                     retry_budget=args.retry_budget)
        print(f"QUEUE_INIT=PASS policy={args.policy} n={len(doc['keys'])} order={doc['order']} "
              f"shuffle_seed={doc['shuffle_seed']} order_sha256={doc['sha256']}")
        return 0
    if args.cmd == "reap":
        acted = q.reap_stale(args.threshold_s)
        print(f"QUEUE_REAP=INFO policy={args.policy} acted={len(acted)} keys={','.join(acted)}")
        return 0
    stats = q.check()
    print(check_line(stats))
    return 0 if stats["dup"] == 0 and stats["missing"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
