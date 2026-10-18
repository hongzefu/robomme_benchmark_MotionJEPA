# -*- coding: utf-8 -*-
"""HF Storage Bucket 读回校验：列全部对象，逐个流式下载算 sha256，与 SHA256SUMS／MANIFEST.tsv 对照。

在 Great Lakes 纯 CPU job（hfverify.sbatch）里跑，规约见 AgentMetaRules greatlakes.md「HF 上传校验 job」：
  - 逐对象 HTTP 分块读回、边下边算 sha256，不落盘（节点 /tmp 也不留文件）；
  - 同时核对对象数、逐对象字节数、清单外多出的对象；
  - 末行判定行 HF_VERIFY=PASS|FAIL objects=<n> sha_match=<n> size_equal=<n> missing=<n> extra=<n> mismatch=<n> checked=<n>
  - 正式校验前用 --limit 1 只校验 1 个最小对象做冒烟。

另有 --list-only：只列对象做「对象数／字节数／缺失／多出」比对、不下载，upload_bucket.sh 用它出 HF_UPLOAD 判定行，
末行 HF_LIST=PASS|FAIL objects=<n> bytes=<n> missing=<n> extra=<n> size_mismatch=<n>。

只用标准库（GL 上直接用 NFS 上 uv managed 的 python3.11，不需要 venv）。
token 只从环境变量 HF_TOKEN 读取；跨域跳转（如 Xet CAS 签名 URL）时去掉 Authorization 头。

期望对象集合 = MANIFEST.tsv 的全部条目 + bucket 根下的 SHA256SUMS 与 MANIFEST.tsv 两个清单文件本身。
清单来源：--manifest-dir 给了就以该目录（NFS 副本）为准，并要求 bucket 里的两份清单与之逐字节相同；
不给则读 bucket 里的两份清单。两份清单之间（路径、sha256）必须一致。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

DEFAULT_BUCKET = "HongzeFu/robomme-test-xhard5-12per-1017"
SUMS_NAME = "SHA256SUMS"
MANIFEST_NAME = "MANIFEST.tsv"
MANIFEST_HEADER = "path\tbytes\tsha256"
CHUNK_BYTES = 8 * 1024 * 1024
ATTEMPTS = 3  # 只对网络类基础设施故障重试，次数写进日志
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")


# ----------------------------------------------------------------- 纯函数（不依赖网络，单测覆盖）
def parse_sha256sums(text: str) -> dict[str, str]:
    """解析 "<sha256>  <path>" 行，返回 path -> sha256。格式不符或路径重复即抛 ValueError。"""
    out: dict[str, str] = {}
    for i, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        sha, sep, path = line.partition("  ")
        if not sep or not _SHA_RE.match(sha) or not path:
            raise ValueError(f"SHA256SUMS 第 {i} 行格式不符：{line!r}")
        if path in out:
            raise ValueError(f"SHA256SUMS 路径重复：{path}")
        out[path] = sha
    return out


def parse_manifest(text: str) -> dict[str, tuple[int, str]]:
    """解析 MANIFEST.tsv，返回 path -> (bytes, sha256)。"""
    lines = text.splitlines()
    if not lines or lines[0] != MANIFEST_HEADER:
        raise ValueError(f"MANIFEST.tsv 表头不符：{lines[:1]!r}")
    out: dict[str, tuple[int, str]] = {}
    for i, line in enumerate(lines[1:], 2):
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) != 3 or not parts[1].isdigit() or not _SHA_RE.match(parts[2]):
            raise ValueError(f"MANIFEST.tsv 第 {i} 行格式不符：{line!r}")
        if parts[0] in out:
            raise ValueError(f"MANIFEST.tsv 路径重复：{parts[0]}")
        out[parts[0]] = (int(parts[1]), parts[2])
    return out


def manifest_consistency(sums: dict[str, str], manifest: dict[str, tuple[int, str]]) -> list[str]:
    """两份清单的路径集合与 sha256 必须一致；返回问题描述列表（空表示一致）。"""
    problems = []
    for p in sorted(set(sums) - set(manifest)):
        problems.append(f"只在 SHA256SUMS：{p}")
    for p in sorted(set(manifest) - set(sums)):
        problems.append(f"只在 MANIFEST.tsv：{p}")
    for p in sorted(set(sums) & set(manifest)):
        if sums[p] != manifest[p][1]:
            problems.append(f"两份清单 sha256 不一致：{p}")
    return problems


def compare_listing(expected: dict[str, int], remote: dict[str, int]) -> dict[str, list[str]]:
    """对象集合与字节数比对。expected / remote 都是 path -> bytes。"""
    return {
        "missing": sorted(set(expected) - set(remote)),
        "extra": sorted(set(remote) - set(expected)),
        "size_mismatch": sorted(p for p in set(expected) & set(remote) if expected[p] != remote[p]),
    }


def tally(
    expected: dict[str, tuple[int, str]],
    remote: dict[str, int],
    digests: dict[str, tuple[int, str]],
) -> dict[str, int]:
    """汇总判定计数。digests 是实际读回的 path -> (读到字节数, sha256)，可以只含部分对象（--limit）。

    mismatch = 已读回对象里 sha256 或字节数与期望不符的个数（缺失／多出单独计）。
    """
    cmp = compare_listing({p: v[0] for p, v in expected.items()}, remote)
    sha_match = size_equal = mismatch = 0
    for p, (n, sha) in digests.items():
        exp = expected.get(p)
        if exp is None:
            mismatch += 1
            continue
        ok_size = n == exp[0] and remote.get(p) == exp[0]
        ok_sha = sha == exp[1]
        size_equal += ok_size
        sha_match += ok_sha
        mismatch += not (ok_size and ok_sha)
    return {
        "objects": len(remote),
        "sha_match": sha_match,
        "size_equal": size_equal,
        "missing": len(cmp["missing"]),
        "extra": len(cmp["extra"]),
        "mismatch": mismatch,
        "checked": len(digests),
    }


def verdict_line(counts: dict[str, int], expect_checked: int) -> tuple[bool, str]:
    ok = (
        counts["missing"] == 0
        and counts["extra"] == 0
        and counts["mismatch"] == 0
        and counts["checked"] == expect_checked
        and counts["sha_match"] == expect_checked
        and counts["size_equal"] == expect_checked
    )
    line = "HF_VERIFY={} objects={objects} sha_match={sha_match} size_equal={size_equal} missing={missing} extra={extra} mismatch={mismatch} checked={checked}".format(
        "PASS" if ok else "FAIL", **counts
    )
    return ok, line


def pick_smallest(expected: dict[str, tuple[int, str]], limit: int) -> list[str]:
    """--limit 冒烟：取字节数最小的 limit 个对象（同大小按路径）。"""
    return [p for p, _ in sorted(expected.items(), key=lambda kv: (kv[1][0], kv[0]))[:limit]]


# ----------------------------------------------------------------- 网络层（标准库 urllib）
class _StripAuthOnCrossHost(urllib.request.HTTPRedirectHandler):
    """跳转到别的主机时去掉 Authorization，避免把 token 发给签名 URL 所在的存储域名。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None:
            old_host = urllib.parse.urlsplit(req.full_url).hostname
            new_host = urllib.parse.urlsplit(new.full_url).hostname
            if old_host != new_host:
                for k in list(new.headers):
                    if k.lower() == "authorization":
                        del new.headers[k]
        return new


_OPENER = urllib.request.build_opener(_StripAuthOnCrossHost)


def _headers(token: str | None) -> dict[str, str]:
    h = {"User-Agent": "robomme-hfverify/1.0"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _next_link(link_header: str | None) -> str | None:
    if not link_header:
        return None
    for part in link_header.split(","):
        m = re.match(r'\s*<([^>]+)>\s*;\s*rel="?next"?', part)
        if m:
            return m.group(1)
    return None


def list_bucket(endpoint: str, bucket: str, token: str | None) -> dict[str, int]:
    """递归列出 bucket 全部文件，返回 path -> size（按 Link 头翻页）。"""
    url = f"{endpoint}/api/buckets/{bucket}/tree?recursive=true"
    out: dict[str, int] = {}
    while url:
        req = urllib.request.Request(url, headers=_headers(token))
        with _OPENER.open(req, timeout=120) as resp:
            items = json.load(resp)
            url = _next_link(resp.headers.get("Link"))
        for it in items:
            if it.get("type") == "file":
                out[it["path"]] = int(it["size"])
    return out


def resolve_url(endpoint: str, bucket: str, path: str) -> str:
    return f"{endpoint}/buckets/{bucket}/resolve/{urllib.parse.quote(path, safe='')}"


def stream_sha256(url: str, token: str | None, chunk_bytes: int = CHUNK_BYTES) -> tuple[int, str]:
    """流式 GET，边读边算 sha256，不落盘。返回 (字节数, sha256)。"""
    h = hashlib.sha256()
    n = 0
    req = urllib.request.Request(url, headers=_headers(token))
    with _OPENER.open(req, timeout=300) as resp:
        while True:
            buf = resp.read(chunk_bytes)
            if not buf:
                break
            h.update(buf)
            n += len(buf)
    return n, h.hexdigest()


def fetch_bytes(url: str, token: str | None) -> bytes:
    req = urllib.request.Request(url, headers=_headers(token))
    with _OPENER.open(req, timeout=120) as resp:
        return resp.read()


def stream_with_retry(url: str, token: str | None, label: str) -> tuple[int, str]:
    last: Exception | None = None
    for attempt in range(1, ATTEMPTS + 1):
        try:
            return stream_sha256(url, token)
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            if isinstance(e, urllib.error.HTTPError) and e.code in (401, 403, 404):
                raise
            last = e
            print(f"  读回 {label} 第 {attempt} 次网络失败：{type(e).__name__}: {e}", flush=True)
            if attempt < ATTEMPTS:
                time.sleep(30)
    assert last is not None
    raise last


# ----------------------------------------------------------------- 主流程
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bucket", default=DEFAULT_BUCKET)
    ap.add_argument("--endpoint", default=os.environ.get("HF_ENDPOINT", "https://huggingface.co").rstrip("/"))
    ap.add_argument("--manifest-dir", type=Path, default=None, help="SHA256SUMS 与 MANIFEST.tsv 的本地（NFS）副本目录")
    ap.add_argument("--limit", type=int, default=None, help="只读回字节数最小的 N 个清单对象（冒烟用 1）")
    ap.add_argument("--list-only", action="store_true", help="只列对象比对数量／字节，不下载内容")
    ap.add_argument("--workers", type=int, default=4, help="并行读回的线程数")
    args = ap.parse_args(argv)

    token = os.environ.get("HF_TOKEN") or None
    print(f"bucket={args.bucket} endpoint={args.endpoint} token={'有' if token else '无（匿名）'}", flush=True)

    # 1. 两份清单：bucket 里的副本必读；--manifest-dir 给了则以本地为准并要求逐字节相同
    remote_meta = {name: fetch_bytes(resolve_url(args.endpoint, args.bucket, name), token) for name in (SUMS_NAME, MANIFEST_NAME)}
    meta = remote_meta
    meta_problems: list[str] = []
    if args.manifest_dir is not None:
        meta = {name: (args.manifest_dir / name).read_bytes() for name in (SUMS_NAME, MANIFEST_NAME)}
        for name in (SUMS_NAME, MANIFEST_NAME):
            if meta[name] != remote_meta[name]:
                meta_problems.append(f"bucket 里的 {name} 与 {args.manifest_dir / name} 不是逐字节相同")
    sums = parse_sha256sums(meta[SUMS_NAME].decode("utf-8"))
    manifest = parse_manifest(meta[MANIFEST_NAME].decode("utf-8"))
    meta_problems += manifest_consistency(sums, manifest)
    for p in meta_problems:
        print(f"清单问题：{p}")

    expected: dict[str, tuple[int, str]] = dict(manifest)
    for name in (SUMS_NAME, MANIFEST_NAME):
        expected[name] = (len(meta[name]), hashlib.sha256(meta[name]).hexdigest())
    print(f"期望对象 {len(expected)} 个（清单条目 {len(manifest)} + 清单文件 2），"
          f"字节 {sum(v[0] for v in expected.values())}", flush=True)

    # 2. 列 bucket
    remote = list_bucket(args.endpoint, args.bucket, token)
    cmp = compare_listing({p: v[0] for p, v in expected.items()}, remote)
    for key in ("missing", "extra", "size_mismatch"):
        for p in cmp[key][:20]:
            print(f"{key}: {p}")
        if len(cmp[key]) > 20:
            print(f"{key}: ……另 {len(cmp[key]) - 20} 个")

    if args.list_only:
        ok = not meta_problems and not any(cmp.values())
        print(f"HF_LIST={'PASS' if ok else 'FAIL'} objects={len(remote)} bytes={sum(remote.values())} "
              f"missing={len(cmp['missing'])} extra={len(cmp['extra'])} size_mismatch={len(cmp['size_mismatch'])}")
        return 0 if ok else 1

    # 3. 逐对象流式读回（清单文件已在第 1 步读过，直接用其内容算）
    targets = sorted(p for p in expected if p in remote and p not in (SUMS_NAME, MANIFEST_NAME))
    if args.limit is not None:
        targets = pick_smallest({p: expected[p] for p in targets}, args.limit)
    digests: dict[str, tuple[int, str]] = {}
    if args.limit is None:
        for name in (SUMS_NAME, MANIFEST_NAME):
            if name in remote:
                digests[name] = (len(remote_meta[name]), hashlib.sha256(remote_meta[name]).hexdigest())

    def work(p: str) -> tuple[str, tuple[int, str]]:
        return p, stream_with_retry(resolve_url(args.endpoint, args.bucket, p), token, p)

    total = len(targets)
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        for i, (p, res) in enumerate(pool.map(work, targets), 1):
            digests[p] = res
            exp = expected[p]
            flag = "OK" if res == (exp[0], exp[1]) else "MISMATCH"
            if flag != "OK" or i % 25 == 0 or i == total:
                print(f"[{i}/{total}] {flag} {p} bytes={res[0]} 用时 {time.time() - t0:.0f}s", flush=True)

    counts = tally(expected, remote, digests)
    # 全量：每个期望对象都必须读回且一致；冒烟：恰好读回 limit 个且一致
    expect_checked = args.limit if args.limit is not None else len(expected)
    ok, line = verdict_line(counts, expect_checked)
    if meta_problems:
        ok = False
        line = line.replace("HF_VERIFY=PASS", "HF_VERIFY=FAIL")
    print(line)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
