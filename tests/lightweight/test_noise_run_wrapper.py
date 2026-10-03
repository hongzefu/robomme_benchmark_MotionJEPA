"""噪声基线 GL 单遍运行包装（``scripts/parity/noise_run.py`` 与 ``noise_run_gl.sh``）的纯 CPU 测试。

全部用临时目录与假入口：不依赖 ``artifacts/``、GPU 与集群；nvidia-smi 用 ``NOISE_RUN_NVIDIA_SMI`` 指向假脚本。
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
NOISE_RUN = REPO / "scripts" / "parity" / "noise_run.py"
WRAPPER = REPO / "scripts" / "parity" / "noise_run_gl.sh"


def _load():
    spec = importlib.util.spec_from_file_location("_noise_run_under_test", NOISE_RUN)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


nr = _load()

CAPS = {"gen": {"attempts": 10, "resets": 30, "retries": 2},
        "eval": {"attempts": 8, "resets": 16, "retries": 2},
        "digest": {"attempts": 4, "resets": 8, "retries": 0},
        "total": {"attempts": 15, "resets": 40, "retries": 3}}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@pytest.fixture()
def env(tmp_path, monkeypatch):
    fake = tmp_path / "fake-nvidia-smi"
    fake.write_text("#!/bin/sh\necho 'NVIDIA A40, 550.54.15, GPU-aaaa-bbbb'\n")
    fake.chmod(0o755)
    monkeypatch.setenv("NOISE_RUN_NVIDIA_SMI", str(fake))
    caps = tmp_path / "caps.json"
    caps.write_text(json.dumps(CAPS))
    return {"tmp": tmp_path, "caps": caps, "ledger": tmp_path / "ledger" / "budget.jsonl", "smi": fake}


def preflight(env, name, *, kind="gen", attempts=2, resets=6, retries=0, out_root=None, extra=()):
    out_root = out_root or env["tmp"] / "runs" / name
    prov = env["tmp"] / "prov" / f"{name}.json"
    argv = ["preflight", "--pass", name, "--kind", kind, "--out-root", str(out_root),
            "--budget-ledger", str(env["ledger"]), "--budget-caps", str(env["caps"]),
            "--attempts", str(attempts), "--resets", str(resets), "--retries", str(retries),
            "--max-steps", "1300", "--server-args", "--port 8000", "--provenance-out", str(prov), *extra]
    return nr.main(argv), prov


def ledger_rows(env):
    return [json.loads(t) for t in env["ledger"].read_text().splitlines()]


# ── 输出根 ────────────────────────────────────────────────────────────────────


def test_输出根不存在或为空目录可跑(env):
    rc, _ = preflight(env, "p1")
    assert rc == 0
    empty = env["tmp"] / "empty"
    empty.mkdir()
    rc, prov = preflight(env, "p2", out_root=empty)
    assert rc == 0
    assert json.loads(prov.read_text())["out_root_state"] == "empty_dir"


def test_输出根非空即拒_且不占预算(env, capsys):
    root = env["tmp"] / "used"
    root.mkdir()
    (root / "results.jsonl").write_text("{}\n")
    rc, prov = preflight(env, "p1", out_root=root)
    out = capsys.readouterr().out
    assert rc == nr.EXIT_FRESH
    assert "RUN_FRESH=FAIL reason=out_root_not_empty" in out
    assert not prov.exists()
    assert not env["ledger"].exists()


def test_输出根是文件也拒(env, capsys):
    root = env["tmp"] / "afile"
    root.write_text("x")
    rc, _ = preflight(env, "p1", out_root=root)
    assert rc == nr.EXIT_FRESH
    assert "RUN_FRESH=FAIL" in capsys.readouterr().out


# ── 预算账本 ──────────────────────────────────────────────────────────────────


def test_预算按kind与total累加_触线即拒(env, capsys):
    assert preflight(env, "g1", attempts=5, resets=15)[0] == 0
    assert preflight(env, "g2", attempts=5, resets=15)[0] == 0  # gen 恰好 10／30，不超
    rc, prov = preflight(env, "g3", attempts=1, resets=0)
    out = capsys.readouterr().out
    assert rc == nr.EXIT_BUDGET and "BUDGET=FAIL reason=over_cap" in out and "gen.attempts=11>10" in out
    assert not prov.exists()
    # gen 已用 10，eval 再要 6 次会让 total 16>15
    rc, _ = preflight(env, "e1", kind="eval", attempts=6, resets=0)
    out = capsys.readouterr().out
    assert rc == nr.EXIT_BUDGET and "total.attempts=16>15" in out
    assert preflight(env, "e2", kind="eval", attempts=5, resets=0)[0] == 0
    rows = ledger_rows(env)
    assert [r["pass"] for r in rows] == ["g1", "g2", "e2"]
    for r in rows:
        assert set(r) == {"t", "pass", "kind", "attempts", "resets", "retries", "event"}
        assert r["event"] == "reserve"


def test_同名pass拒(env, capsys):
    rc, prov = preflight(env, "dup")
    assert rc == 0
    prov.unlink()  # 绕过「来源报告已存在」那道检查，专测账本的同名拒绝
    rc, _ = preflight(env, "dup", out_root=env["tmp"] / "other")
    assert rc == nr.EXIT_BUDGET
    assert "reason=duplicate_pass" in capsys.readouterr().out


def test_finish实际数大于登记时按实际计费(env, capsys):
    rc, prov = preflight(env, "g1", attempts=2, resets=6)
    assert rc == 0
    assert nr.main(["finish", "--pass", "g1", "--provenance", str(prov), "--exit-code", "0",
                    "--actual-attempts", "9", "--actual-resets", "unknown"]) == nr.EXIT_OVERRUN
    assert "actual_exceeds_reserved" in capsys.readouterr().out
    # 已计费 9 次，再要 2 次超 gen 上限 10
    rc, _ = preflight(env, "g2", attempts=2, resets=0)
    assert rc == nr.EXIT_BUDGET


def test_账本行完整且fsync(env, monkeypatch):
    calls = []
    real = os.fsync
    monkeypatch.setattr(nr.os, "fsync", lambda fd: (calls.append(fd), real(fd)))
    assert preflight(env, "g1")[0] == 0
    assert calls  # 写账本时 fsync 过
    text = env["ledger"].read_text()
    assert text.endswith("\n") and len(text.splitlines()) == 1
    json.loads(text)


def test_账本损坏即拒(env, capsys):
    env["ledger"].parent.mkdir(parents=True)
    env["ledger"].write_text('{"pass": "x", "event": "reserve"\n')
    rc, _ = preflight(env, "g1")
    assert rc == nr.EXIT_BUDGET and "ledger_corrupt" in capsys.readouterr().out


def test_缺上限即拒(env, capsys):
    env["caps"].write_text(json.dumps({"gen": CAPS["gen"]}))
    rc, _ = preflight(env, "g1")
    assert rc == nr.EXIT_BUDGET and "cap_missing scope=total" in capsys.readouterr().out


# ── 资产核对 ──────────────────────────────────────────────────────────────────


def make_asset(root: Path) -> dict[str, str]:
    (root / "sub").mkdir(parents=True)
    (root / "config.json").write_bytes(b'{"a": 1}')
    (root / "sub" / "w.bin").write_bytes(b"\x00\x01weights")
    (root / ".gitattributes").write_bytes(b"* binary")
    return {"./config.json": sha(b'{"a": 1}'), "./sub/w.bin": sha(b"\x00\x01weights"),
            "./.gitattributes": sha(b"* binary")}


def write_lock(path: Path, name: str, files: dict[str, str]) -> Path:
    path.write_text(json.dumps({"schema": "x", "assets": {name: {"files": files, "n_files": len(files)}}}))
    return path


def asset_args(env, root, lock):
    return ("--assets-lock", str(lock), "--asset-dir", f"smvla={root}")


def test_资产相同_PASS且排除cache与DS_Store(env, capsys):
    root = env["tmp"] / "ckpt"
    files = make_asset(root)
    (root / ".cache" / "huggingface").mkdir(parents=True)
    (root / ".cache" / "huggingface" / "x.metadata").write_text("m")
    (root / ".DS_Store").write_text("d")
    (root / "sub" / ".DS_Store").write_text("d")
    (root / "sub" / ".cache").mkdir()  # 非顶层 .cache 不排除（与 find -path './.cache/*' 一致）
    (root / "sub" / ".cache" / "keep").write_bytes(b"k")
    files["./sub/.cache/keep"] = sha(b"k")
    lock = write_lock(env["tmp"] / "lock.json", "smvla", files)
    rc, prov = preflight(env, "g1", extra=asset_args(env, root, lock))
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "ASSET name=smvla files=4 locked=4 missing=0 extra=0 mismatch=0" in out
    assert "assets=PASS" in out
    rep = json.loads(prov.read_text())
    a = rep["assets_sha"]["smvla"]
    assert a["verdict"] == "PASS" and a["files_sha256"] == a["locked_files_sha256"]


@pytest.mark.parametrize("change,field", [("missing", "missing=1"), ("extra", "extra=1"), ("byte", "mismatch=1")])
def test_资产缺文件_多文件_改一个字节均FAIL(env, capsys, change, field):
    root = env["tmp"] / "ckpt"
    files = make_asset(root)
    lock = write_lock(env["tmp"] / "lock.json", "smvla", files)
    if change == "missing":
        (root / "sub" / "w.bin").unlink()
    elif change == "extra":
        (root / "new.bin").write_bytes(b"x")
    else:
        (root / "sub" / "w.bin").write_bytes(b"\x00\x02weights")
    rc, prov = preflight(env, "g1", extra=asset_args(env, root, lock))
    out = capsys.readouterr().out
    assert rc == nr.EXIT_ASSETS
    assert field in out and "NOISE_PREFLIGHT=FAIL" in out and "reason=assets" in out
    assert not prov.exists() and not env["ledger"].exists()  # 资产不过不占预算


def test_资产跟随符号链接(env, capsys):
    real = env["tmp"] / "blobs"
    real.mkdir()
    (real / "big").write_bytes(b"BIG")
    root = env["tmp"] / "ckpt"
    root.mkdir()
    (root / "model.safetensors").symlink_to(real / "big")
    (root / "linked_dir").symlink_to(real, target_is_directory=True)
    (root / "dangling").symlink_to(env["tmp"] / "nope")  # 断链：find -L -type f 不列
    files = {"./model.safetensors": sha(b"BIG"), "./linked_dir/big": sha(b"BIG")}
    lock = write_lock(env["tmp"] / "lock.json", "smvla", files)
    rc, _ = preflight(env, "g1", extra=asset_args(env, root, lock))
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "ASSET name=smvla files=2 locked=2 missing=0 extra=0 mismatch=0" in out


def test_资产名不在锁里即FAIL(env, capsys):
    root = env["tmp"] / "ckpt"
    make_asset(root)
    lock = write_lock(env["tmp"] / "lock.json", "other", {})
    rc, _ = preflight(env, "g1", extra=asset_args(env, root, lock))
    assert rc == nr.EXIT_ASSETS and "error=not_in_lock" in capsys.readouterr().out


def test_tokenizer单独核sha(env, capsys):
    tok = env["tmp"] / "tokenizer.model"
    tok.write_bytes(b"tok")
    rc, prov = preflight(env, "g1", extra=("--tokenizer", str(tok), "--tokenizer-sha256", sha(b"tok")))
    out = capsys.readouterr().out
    assert rc == 0 and "match=1" in out and "assets=PASS" in out
    assert json.loads(prov.read_text())["tokenizer_sha256"] == sha(b"tok")
    rc, _ = preflight(env, "g2", extra=("--tokenizer", str(tok), "--tokenizer-sha256", sha(b"other")))
    assert rc == nr.EXIT_ASSETS


def test_find过滤规则与真实find一致(env):
    root = env["tmp"] / "ckpt"
    make_asset(root)
    (root / ".cache" / "a").mkdir(parents=True)
    (root / ".cache" / "a" / "b").write_text("x")
    (root / "sub" / ".DS_Store").write_text("d")
    (root / "lnk").symlink_to(root / "config.json")
    out = subprocess.run(["find", "-L", ".", "-type", "f", "!", "-path", "./.cache/*", "!", "-name", ".DS_Store"],
                         cwd=root, capture_output=True, text=True, check=True).stdout.split()
    assert sorted(out) == sorted(nr.list_asset_files(root))


# ── 来源报告 ──────────────────────────────────────────────────────────────────


REQUIRED = ("pass", "kind", "started_at", "started_at_iso", "commit", "git_dirty", "policy_commits", "assets_sha",
            "tokenizer_sha256", "driver", "gpu_model", "gpu_uuid", "host", "slurm_job_id", "max_steps", "server_args",
            "out_root", "budget", "python", "fingerprint", "env_fingerprint")


def test_来源报告字段齐全且fingerprint可重算(env, capsys, monkeypatch):
    monkeypatch.setenv("SLURM_JOB_ID", "12345")
    rc, prov = preflight(env, "g1", extra=("--policy-repo", f"self={REPO}"))
    out = capsys.readouterr().out
    assert rc == 0
    rep = json.loads(prov.read_text())
    assert all(k in rep for k in REQUIRED), [k for k in REQUIRED if k not in rep]
    assert isinstance(rep["started_at"], float)
    assert rep["gpu_model"] == "NVIDIA A40" and rep["driver"] == "550.54.15" and rep["gpu_uuid"] == "GPU-aaaa-bbbb"
    assert rep["slurm_job_id"] == "12345" and rep["max_steps"] == 1300 and rep["server_args"] == "--port 8000"
    assert len(rep["commit"]) == 40 and rep["policy_commits"]["self"] == rep["commit"]
    body = {k: v for k, v in rep.items() if k != "fingerprint"}
    want = hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                          .encode("utf-8")).hexdigest()
    assert rep["fingerprint"] == want
    assert out.strip().splitlines()[-1] == (f"NOISE_PREFLIGHT=PASS pass=g1 kind=gen assets=SKIP "
                                            f"fingerprint={want[:12]}")
    assert rep["budget"]["reserved"] == {"attempts": 2, "resets": 6, "retries": 0}


def test_nvidia_smi不可用时为null(env, monkeypatch):
    monkeypatch.setenv("NOISE_RUN_NVIDIA_SMI", str(env["tmp"] / "no-such-smi"))
    rc, prov = preflight(env, "g1")
    assert rc == 0
    rep = json.loads(prov.read_text())
    assert rep["driver"] is None and rep["gpu_model"] is None and rep["gpu_uuid"] is None


def test_finish追加字段_fingerprint不变_重复finish拒(env, capsys):
    rc, prov = preflight(env, "g1")
    fp = json.loads(prov.read_text())["fingerprint"]
    assert nr.main(["finish", "--pass", "g1", "--provenance", str(prov), "--exit-code", "1",
                    "--actual-attempts", "2", "--actual-resets", "unknown"]) == 0
    rep = json.loads(prov.read_text())
    assert rep["exit_code"] == 1 and rep["actual_attempts"] == 2 and rep["actual_resets"] is None
    assert isinstance(rep["finished_at"], float) and rep["finished_at"] >= rep["started_at"]
    assert rep["fingerprint"] == fp == nr.fingerprint_of(rep)
    fin = [r for r in ledger_rows(env) if r["event"] == "finish"]
    assert len(fin) == 1 and fin[0]["attempts"] == 2 and fin[0]["resets"] is None and fin[0]["kind"] == "gen"
    assert nr.main(["finish", "--pass", "g1", "--provenance", str(prov), "--exit-code", "0",
                    "--actual-attempts", "2", "--actual-resets", "0"]) != 0


def test_来源报告已存在即拒(env):
    rc, prov = preflight(env, "g1")
    assert rc == 0
    rc, _ = preflight(env, "g1", out_root=env["tmp"] / "x")
    assert rc == nr.EXIT_FRESH


# ── eval-shard ────────────────────────────────────────────────────────────────


def shard_row(task, tier, seed, ep, cand=None):
    return {"task": task, "tier": tier, "seed": seed, "candidate": cand, "builder_episode": ep,
            "source_episode": None, "spec_sha256": sha(f"{task}{tier}{seed}".encode()),
            "effective_max_steps": 1300, "key": f"{task}_{tier}_{seed}"}


def write_shard(path: Path, rows: list[dict]) -> Path:
    # 与 v8_manifest.write_outputs 同序列化
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
    return path


def test_eval_shard筛选正确且格式与v8一致(env, capsys):
    vm = nr.load_v8_manifest()
    a = write_shard(env["tmp"] / "shard-00.json", [shard_row("MoveCube", "xhard4", 7, 3, 1),
                                                   shard_row("BinFill", "xhard1", 5, 0, 0)])
    b = write_shard(env["tmp"] / "shard-01.json", [shard_row("StopCube", "xhard2", 9, 2, 4)])
    keys = env["tmp"] / "keys.json"
    keys.write_text(json.dumps(["StopCube_xhard2_9", "MoveCube_xhard4_7"]))
    out = env["tmp"] / "out" / "shard-nb.json"
    assert nr.main(["eval-shard", "--source-shard", str(a), str(b), "--keys", str(keys), "--out", str(out)]) == 0
    text = capsys.readouterr().out
    assert "EVAL_SHARD=PASS rows=2 missing=0" in text
    rows = json.loads(out.read_text())
    assert [r["key"] for r in rows] == ["MoveCube_xhard4_7", "StopCube_xhard2_9"]
    assert all(set(r) == set(vm.SHARD_ROW_KEYS) for r in rows)
    assert out.read_text() == json.dumps(rows, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    # 客户端 V8 模式的结构核对（只用标准库的同口径实现）对新分片全部通过
    assert all(nr.shard_row_problem(r, vm) is None for r in rows)


def test_eval_shard键缺失报错(env, capsys):
    a = write_shard(env["tmp"] / "shard-00.json", [shard_row("MoveCube", "xhard4", 7, 3, 1)])
    keys = env["tmp"] / "keys.json"
    keys.write_text(json.dumps({"keys": ["MoveCube_xhard4_7", "PatternLock_xhard3_1"]}))
    out = env["tmp"] / "shard-nb.json"
    rc = nr.main(["eval-shard", "--source-shard", str(a), "--keys", str(keys), "--out", str(out)])
    assert rc != 0 and "EVAL_SHARD=FAIL rows=0 missing=1" in capsys.readouterr().out
    assert not out.exists()


def test_eval_shard源分片坏行或重复键报错(env, capsys):
    bad = shard_row("MoveCube", "xhard4", 7, 3, 1)
    bad["key"] = "wrong"
    a = write_shard(env["tmp"] / "a.json", [bad])
    keys = env["tmp"] / "keys.json"
    keys.write_text(json.dumps(["wrong"]))
    assert nr.main(["eval-shard", "--source-shard", str(a), "--keys", str(keys),
                    "--out", str(env["tmp"] / "o1.json")]) != 0
    r = shard_row("MoveCube", "xhard4", 7, 3, 1)
    b = write_shard(env["tmp"] / "b.json", [r])
    c = write_shard(env["tmp"] / "c.json", [r])
    keys.write_text(json.dumps([r["key"]]))
    assert nr.main(["eval-shard", "--source-shard", str(b), str(c), "--keys", str(keys),
                    "--out", str(env["tmp"] / "o2.json")]) != 0
    assert "duplicate=1" in capsys.readouterr().out


# ── ship ──────────────────────────────────────────────────────────────────────


def make_shipped(tmp: Path, *, pulled=False, corrupt=False, leftover=False):
    src, stage = tmp / "node", tmp / "stage"
    rel = Path("episodes") / "xhard4" / "MoveCube_episode_3"
    h5 = b"h5bytes"
    (src / rel).mkdir(parents=True)
    (src / rel / "meta.json").write_text("{}")
    line = {"task": "MoveCube", "episode": 3, "path": str(rel / "hdf5_files" / "a.h5"), "sha256": sha(h5)}
    (src / "identities.jsonl").write_text(json.dumps(line) + "\n" + json.dumps({"task": "X", "path": None}) + "\n")
    (stage / rel / "hdf5_files").mkdir(parents=True)
    (stage / rel / "SHIPPED").write_text(json.dumps({"hdf5_files/a.h5": sha(h5)}))
    if pulled:
        (stage / rel / "PULLED").write_text("t\n")
    else:
        (stage / rel / "hdf5_files" / "a.h5").write_bytes(b"bad" if corrupt else h5)
    if leftover:
        (src / rel / "hdf5_files").mkdir(parents=True)
        (src / rel / "hdf5_files" / "a.h5").write_bytes(h5)
    return src, stage


@pytest.mark.parametrize("kw,ok", [({}, True), ({"pulled": True}, True), ({"corrupt": True}, False),
                                   ({"leftover": True}, False)])
def test_ship核对暂存完整性(tmp_path, capsys, kw, ok):
    src, stage = make_shipped(tmp_path, **kw)
    rc = nr.main(["ship", "--src", str(src), "--stage", str(stage), "--finalize"])
    out = capsys.readouterr().out
    assert (rc == 0) is ok, out
    assert out.strip().splitlines()[-1].startswith(f"NOISE_SHIP={'PASS' if ok else 'FAIL'} episodes=1")
    assert (stage / "SEGMENT_DONE").exists() is ok
    if ok:
        assert (stage / "identities.jsonl").exists()
        assert not list(stage.rglob("*.mp4"))


# ── 壳脚本端到端 ──────────────────────────────────────────────────────────────


def run_wrapper(env, name, real_cmd, out_root=None, extra=()):
    log = env["tmp"] / "logs" / f"{name}.log"
    prov = env["tmp"] / "prov" / f"{name}.json"
    out_root = out_root or env["tmp"] / "runs" / name
    e = dict(os.environ, PY=sys.executable, NOISE_RUN_NVIDIA_SMI=str(env["smi"]))
    cmd = ["bash", str(WRAPPER), "--pass", name, "--kind", "gen", "--out-root", str(out_root), "--log", str(log),
           "--provenance-out", str(prov), "--budget-ledger", str(env["ledger"]), "--budget-caps", str(env["caps"]),
           "--attempts", "1", "--resets", "3", "--retries", "0", *extra, "--", *real_cmd]
    proc = subprocess.run(cmd, capture_output=True, text=True, env=e, timeout=120)
    return proc, log, prov


@pytest.mark.parametrize("real,code", [(["true"], 0), (["false"], 1)])
def test_壳脚本端到端写EXIT_CODE与finish行(env, real, code):
    proc, log, prov = run_wrapper(env, f"w{code}", real, extra=("--actual-attempts", "1"))
    assert proc.returncode == code, proc.stdout + proc.stderr
    lines = log.read_text().splitlines()
    assert lines[-1] == f"EXIT_CODE={code}"
    assert any(ln.startswith("NOISE_PREFLIGHT=PASS") for ln in lines)
    assert any(ln.startswith(f"NOISE_FINISH=PASS pass=w{code} exit_code={code}") for ln in lines)
    fin = [r for r in ledger_rows(env) if r["event"] == "finish"]
    assert len(fin) == 1 and fin[0]["exit_code"] == code and fin[0]["attempts"] == 1
    rep = json.loads(prov.read_text())
    assert rep["exit_code"] == code and rep["real_command"].strip() == " ".join(real)


def test_壳脚本真实命令输出进日志_环境变量已导出(env):
    proc, log, _ = run_wrapper(env, "wenv", ["bash", "-c", 'echo "HELLO omp=$OMP_NUM_THREADS mkl=$MKL_NUM_THREADS"'])
    assert proc.returncode == 0
    assert "HELLO omp=1 mkl=1" in log.read_text()


def test_壳脚本preflight不过不执行真实命令且不写finish(env):
    root = env["tmp"] / "used"
    root.mkdir()
    (root / "x").write_text("1")
    marker = env["tmp"] / "ran"
    proc, log, prov = run_wrapper(env, "wbad", ["touch", str(marker)], out_root=root)
    assert proc.returncode == nr.EXIT_FRESH
    text = log.read_text()
    assert "RUN_FRESH=FAIL reason=out_root_not_empty" in text
    assert text.splitlines()[-1] == f"EXIT_CODE={nr.EXIT_FRESH}"
    assert not marker.exists() and not prov.exists() and not env["ledger"].exists()


def test_壳脚本被TERM中断时收掉真实命令并照写finish与EXIT_CODE(env):
    import signal
    import time

    log = env["tmp"] / "logs" / "wsig.log"
    prov = env["tmp"] / "prov" / "wsig.json"
    pidfile = env["tmp"] / "child.pid"
    e = dict(os.environ, PY=sys.executable, NOISE_RUN_NVIDIA_SMI=str(env["smi"]))
    cmd = ["bash", str(WRAPPER), "--pass", "wsig", "--kind", "gen", "--out-root", str(env["tmp"] / "runs" / "wsig"),
           "--log", str(log), "--provenance-out", str(prov), "--budget-ledger", str(env["ledger"]),
           "--budget-caps", str(env["caps"]), "--attempts", "1", "--resets", "1", "--retries", "0", "--",
           sys.executable, "-c",
           f"import os,time;open({str(pidfile)!r},'w').write(str(os.getpid()));print('begin',flush=True);time.sleep(60)"]
    proc = subprocess.Popen(cmd, env=e, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    deadline = time.time() + 30
    while not (log.exists() and "begin" in log.read_text()):
        assert time.time() < deadline and proc.poll() is None
        time.sleep(0.1)
    proc.send_signal(signal.SIGTERM)
    proc.communicate(timeout=30)
    assert proc.returncode == 143
    lines = log.read_text().splitlines()
    assert lines[-1] == "EXIT_CODE=143"
    assert any(ln.startswith("NOISE_FINISH=PASS pass=wsig exit_code=143") for ln in lines)
    child = int(pidfile.read_text())
    time.sleep(0.2)
    assert not Path(f"/proc/{child}").exists() or "zombie" in Path(f"/proc/{child}/status").read_text().lower()


def test_壳脚本语法检查():
    assert subprocess.run(["bash", "-n", str(WRAPPER)]).returncode == 0
