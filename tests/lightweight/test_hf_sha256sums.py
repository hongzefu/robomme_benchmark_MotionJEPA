# -*- coding: utf-8 -*-
"""轻量测试：scripts/hf-upload 的 sha256 清单生成与读回校验比对逻辑（不联网）。

运行（使用 uv）：
    uv run --no-sync python -m pytest tests/lightweight/test_hf_sha256sums.py -q
"""

from __future__ import annotations

import hashlib
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests._shared.repo_paths import find_repo_root

pytestmark = [pytest.mark.lightweight]

REPO_ROOT = find_repo_root(__file__)
HF_DIR = REPO_ROOT / "scripts" / "hf-upload"
MAKE = HF_DIR / "make_sha256sums.py"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"hfupload_{name}", HF_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


vb = _load("verify_bucket")
ms = _load("make_sha256sums")


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


@pytest.fixture()
def groups(tmp_path: Path):
    """造两组小产物：G1、G5，含 h5、视频子目录、清单 json。"""
    files = {
        "G5/hdf5_files/BinFill_ep50_seed1.h5": b"h5-binfill" * 1000,
        "G5/hdf5_files/AAA_ep51_seed2.h5": b"h5-aaa",
        "G5/run_summary.json": b'{"ok": true}\n',
        "G5/videos/BinFill_ep50.mp4": b"\x00\x01mp4",
        "G1/hdf5_files/VideoUnmask_ep50_seed3.h5": b"",
        "G1/episode_results.jsonl": b'{"a":1}\n{"a":2}\n',
    }
    root = tmp_path / "full"
    for rel, data in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    return root, files


def _run_make(root: Path, out: Path, *extra: str):
    return subprocess.run(
        [sys.executable, str(MAKE), "--out-dir", str(out), *extra, str(root / "G5"), str(root / "G1")],
        capture_output=True,
        text=True,
    )


def test_make_sha256sums_format_order_bytes(groups, tmp_path):
    root, files = groups
    out = tmp_path / "upload"
    r = _run_make(root, out, "--expect-h5", "3")
    assert r.returncode == 0, r.stdout + r.stderr
    last = r.stdout.strip().splitlines()[-1]
    total = sum(len(v) for v in files.values())
    assert last == f"SHA256SUMS=PASS h5=3 files={len(files)} bytes={total}"

    sums_text = (out / "SHA256SUMS").read_text()
    lines = sums_text.splitlines()
    paths = [ln.split("  ", 1)[1] for ln in lines]
    assert paths == sorted(files)  # 排序稳定、路径带组前缀
    for ln in lines:
        sha, rel = ln.split("  ", 1)
        assert sha == _sha(files[rel])

    man = (out / "MANIFEST.tsv").read_text().splitlines()
    assert man[0] == "path\tbytes\tsha256"
    rows = [m.split("\t") for m in man[1:]]
    assert [r_[0] for r_ in rows] == paths
    for rel, n, sha in rows:
        assert int(n) == len(files[rel]) and sha == _sha(files[rel])

    # 与 verify_bucket 的解析器互通
    parsed_sums = vb.parse_sha256sums(sums_text)
    parsed_man = vb.parse_manifest((out / "MANIFEST.tsv").read_text())
    assert vb.manifest_consistency(parsed_sums, parsed_man) == []

    # 同输入重跑字节级相同（顺序稳定）
    out2 = tmp_path / "upload2"
    assert _run_make(root, out2).returncode == 0
    assert (out2 / "SHA256SUMS").read_bytes() == (out / "SHA256SUMS").read_bytes()
    assert (out2 / "MANIFEST.tsv").read_bytes() == (out / "MANIFEST.tsv").read_bytes()


def test_make_sha256sums_expect_h5_mismatch_fails(groups, tmp_path):
    root, _ = groups
    r = _run_make(root, tmp_path / "upload", "--expect-h5", "624")
    assert r.returncode != 0
    assert r.stdout.strip().splitlines()[-1].startswith("SHA256SUMS=FAIL h5=3 ")


def test_make_sha256sums_rejects_duplicate_basename(tmp_path):
    a = tmp_path / "x" / "G1"
    b = tmp_path / "y" / "G1"
    for d in (a, b):
        d.mkdir(parents=True)
        (d / "f.h5").write_bytes(b"1")
    r = subprocess.run(
        [sys.executable, str(MAKE), "--out-dir", str(tmp_path / "o"), str(a), str(b)],
        capture_output=True,
        text=True,
    )
    assert r.returncode != 0
    assert "SHA256SUMS=FAIL" in r.stdout


def test_sha256_file_chunked_matches_hashlib(tmp_path):
    p = tmp_path / "big.bin"
    data = bytes(range(256)) * 5000
    p.write_bytes(data)
    sha, n = ms.sha256_file(p, chunk_bytes=1000)  # 小块强制多次读
    assert (sha, n) == (_sha(data), len(data))


def _expected():
    return {
        "G1/a.h5": (10, "a" * 64),
        "G1/b.h5": (20, "b" * 64),
        "G5/c.h5": (5, "c" * 64),
        "SHA256SUMS": (100, "d" * 64),
        "MANIFEST.tsv": (120, "e" * 64),
    }


def test_compare_listing_counts():
    exp = {p: v[0] for p, v in _expected().items()}
    remote = dict(exp)
    del remote["G1/b.h5"]  # 缺失
    remote["G9/zz.h5"] = 1  # 多出
    remote["G5/c.h5"] = 6  # 字节不符
    cmp = vb.compare_listing(exp, remote)
    assert cmp == {"missing": ["G1/b.h5"], "extra": ["G9/zz.h5"], "size_mismatch": ["G5/c.h5"]}


def test_tally_all_match_passes():
    exp = _expected()
    remote = {p: v[0] for p, v in exp.items()}
    digests = dict(exp)
    counts = vb.tally(exp, remote, digests)
    assert counts == {"objects": 5, "sha_match": 5, "size_equal": 5, "missing": 0, "extra": 0, "mismatch": 0, "checked": 5}
    ok, line = vb.verdict_line(counts, expect_checked=len(exp))
    assert ok and line.startswith("HF_VERIFY=PASS objects=5 ")
    assert " missing=0 extra=0 mismatch=0" in line


def test_tally_missing_extra_mismatch():
    exp = _expected()
    remote = {p: v[0] for p, v in exp.items()}
    del remote["G1/b.h5"]
    remote["G9/zz.h5"] = 1
    remote["G5/c.h5"] = 6
    digests = {
        "G1/a.h5": (10, "f" * 64),  # sha 不符
        "G5/c.h5": (6, "c" * 64),  # 字节不符
        "SHA256SUMS": exp["SHA256SUMS"],
        "MANIFEST.tsv": exp["MANIFEST.tsv"],
    }
    counts = vb.tally(exp, remote, digests)
    assert counts["objects"] == 5
    assert counts["missing"] == 1
    assert counts["extra"] == 1
    assert counts["mismatch"] == 2
    assert counts["sha_match"] == 3
    assert counts["size_equal"] == 3
    ok, line = vb.verdict_line(counts, expect_checked=len(exp))
    assert not ok and line.startswith("HF_VERIFY=FAIL ")
    assert "missing=1 extra=1 mismatch=2" in line


def test_limit_smoke_picks_smallest_and_counts():
    exp = _expected()
    picked = vb.pick_smallest({p: v for p, v in exp.items() if p not in ("SHA256SUMS", "MANIFEST.tsv")}, 1)
    assert picked == ["G5/c.h5"]
    remote = {p: v[0] for p, v in exp.items()}
    counts = vb.tally(exp, remote, {"G5/c.h5": exp["G5/c.h5"]})
    ok, line = vb.verdict_line(counts, expect_checked=1)
    assert ok and "checked=1" in line
    # 少读一个就不算通过
    ok2, _ = vb.verdict_line(vb.tally(exp, remote, {}), expect_checked=1)
    assert not ok2


def test_manifest_parsers_reject_bad_input():
    with pytest.raises(ValueError):
        vb.parse_sha256sums("nothex  G1/a.h5\n")
    with pytest.raises(ValueError):
        vb.parse_sha256sums(f"{'a' * 64}  x\n{'b' * 64}  x\n")
    with pytest.raises(ValueError):
        vb.parse_manifest("wrong\theader\n")
    sums = {"G1/a.h5": "a" * 64, "G1/b.h5": "b" * 64}
    man = {"G1/a.h5": (1, "a" * 64), "G1/c.h5": (1, "c" * 64)}
    probs = vb.manifest_consistency(sums, man)
    assert any("G1/b.h5" in p for p in probs) and any("G1/c.h5" in p for p in probs)


def test_redirect_strips_auth_on_cross_host():
    import urllib.request

    h = vb._StripAuthOnCrossHost()
    req = urllib.request.Request("https://huggingface.co/buckets/x/y/resolve/a", headers={"Authorization": "Bearer t"})
    same = h.redirect_request(req, None, 302, "Found", {}, "https://huggingface.co/other")
    cross = h.redirect_request(req, None, 302, "Found", {}, "https://cas-bridge.example.org/signed")
    assert same.get_header("Authorization") == "Bearer t"
    assert cross.get_header("Authorization") is None


def test_next_link_parsing():
    assert vb._next_link('<https://h/api/x?cursor=abc>; rel="next"') == "https://h/api/x?cursor=abc"
    assert vb._next_link(None) is None
    assert vb._next_link('<https://h/p>; rel="prev"') is None
