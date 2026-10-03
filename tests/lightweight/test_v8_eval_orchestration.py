"""V8 双模型评估 GL 编排（契约 C3）的零仿真测试：``run_seat.sh`` 的 V8 透传与 ``run_v8_gl.sh`` 席位编排。

零仿真、零 GPU、零真实 server、零 GL 作业：在临时目录搭一个假仓库（真脚本的副本 + 假 ``env_client.py``／
``smvla_server.py``／MME ``serve_policy.py``，三个解释器都是转交本机 python 的包装），PATH 前置假 ``git``
（让 MME 预检看到固定 commit）与假 ``nvidia-smi``。假 server 只起 TCP 监听；假客户端按计划文件写
results.jsonl 与录像目录、按指令退出 0／3／5／75 或挂住。

覆盖：正常成功、单局超时退出 75 被重启、server 死后重起、客户端退出 5／3 不重启、tokenizer 哈希不符
RUN_BLOCKED 且不启 server、哈希相符 TOKENIZER_SHA=PASS 且 OPENPI_DATA_HOME 进 server 环境、录像同步
（完成目录周期搬、进行中目录只在收尾搬、sha 不符不删源）、TERM 中断仍全量同步并写 V8_SEAT_DONE outcome=aborted、
监督进程（run_seat.sh）被 KILL 后回收残留子进程并照常收尾、旧调用方式（无 --v8）参数拼装不变；
NFS 原子发布（.incoming 后 mv、目标已存在落 .dupN 不覆盖）、SEAT_REC_SYNC 累计计数与 left=、
TERM 同时发给 tee 与全部子进程（模拟 slurmstepd 发给整个 step）仍在 60 s 内写出收尾三行、参数错误也写 V8_SEAT_DONE。
末尾判定行 ``V8_EVAL_ORCHESTRATION=PASS``。
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SRC_SEAT = REPO / "scripts" / "eval-official" / "run_seat.sh"
SRC_GL = REPO / "scripts" / "eval-official" / "run_v8_gl.sh"
MME_COMMIT = "ecf086c3be7c2223167d9bb2f6ef1f0a6e24353b"
MME_YAML = "perceptual-framesamp-modul.yaml"
RUN_TIMEOUT = 120  # 单个子进程（一次 run_seat／run_v8_gl）的硬超时

pytestmark = pytest.mark.skipif(shutil.which("bash") is None or shutil.which("rsync") is None
                                or shutil.which("setsid") is None, reason="需要 bash、rsync、setsid")

PASSED: list[str] = []
EXPECTED = ["old_mode", "v8_flags", "wall_restart", "server_died", "no_restart_5", "no_restart_3",
            "tokenizer_mismatch", "gl_bad_args", "gl_success", "gl_sha_mismatch", "gl_term", "gl_term_group",
            "gl_supervisor_dead"]

FAKE_CLIENT = r'''
import json, os, sys, time
from pathlib import Path
a = sys.argv[1:]
FAKE = Path(os.environ["V8_FAKE_DIR"])
def opt(name, default=None):
    return a[a.index(name) + 1] if name in a else default
pol = opt("--policy")
out = Path(opt("--out")); out.mkdir(parents=True, exist_ok=True)
with open(FAKE / "calls.jsonl", "a") as f:
    f.write(json.dumps({"who": "client", "policy": pol, "argv": a}) + "\n")
cnt = FAKE / f"client_{pol}_n"
n = int(cnt.read_text()) if cnt.exists() else 0
cnt.write_text(str(n + 1))
plan = json.loads((FAKE / "plan.json").read_text()).get(pol, [{}])
act = plan[n] if n < len(plan) else plan[-1]
rec_root = Path(opt("--rec-root") or (out / "rec"))
idents = json.load(open(opt("--identities"), encoding="utf-8"))
(out / "progress.json").write_text("{}")
def key_of(i):
    return i.get("key") or f"{i['task']}_{int(i['seed'])}"
if act.get("inprogress"):
    d = rec_root / (key_of(idents[0]) + ".a9"); d.mkdir(parents=True, exist_ok=True)
    (d / "front.mkv").write_bytes(os.urandom(2048))
if act.get("orphan"):
    d = rec_root / "Orphan_xhard1_1.a1"; d.mkdir(parents=True, exist_ok=True)
    (d / "front.mkv").write_bytes(os.urandom(1024)); (d / "summary.json").write_text("{}")
if act.get("write"):
    for i in idents:
        d = rec_root / (key_of(i) + ".a1"); d.mkdir(parents=True, exist_ok=True)
        (d / "front.mkv").write_bytes(os.urandom(4096)); (d / "wrist.mkv").write_bytes(os.urandom(3000))
        (d / "sub").mkdir(exist_ok=True); (d / "sub" / "meta.json").write_text("{}")
        if act.get("corrupt"):
            (d / "corrupt.bin").write_bytes(b"c")
        (d / "summary.json").write_text("{}")
        row = {"task": i["task"], "seed": int(i["seed"]), "status": "success", "task_success": True,
               "policy": pol, "rec_dir": str(d), "infra": False}
        if "--v8" in a:
            row.update({"v8": True, "key": key_of(i), "tier": i.get("tier"), "attempt_no": 1})
        with open(out / "results.jsonl", "a") as f:
            f.write(json.dumps(row) + "\n")
        print(f"EPISODE_DONE policy={pol} key={key_of(i)} status=success", flush=True)
(FAKE / f"client_{pol}_ready").write_text("1")
time.sleep(float(act.get("sleep", 0)))
sys.exit(int(act.get("exit", 0)))
'''

FAKE_SMVLA_SERVER = r'''
import json, os, socket, sys, time
from pathlib import Path
a = sys.argv[1:]
FAKE = Path(os.environ["V8_FAKE_DIR"])
port = int(a[a.index("--port") + 1])
cnt = FAKE / "smvla_server_n"
n = int(cnt.read_text()) if cnt.exists() else 0
cnt.write_text(str(n + 1))
with open(FAKE / "calls.jsonl", "a") as f:
    f.write(json.dumps({"who": "smvla_server", "argv": a, "n": n}) + "\n")
s = socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); s.bind(("127.0.0.1", port)); s.listen()
if os.environ.get("V8_FAKE_SERVER_DIE_FIRST") == "1" and n == 0:
    time.sleep(3); sys.exit(1)
time.sleep(10 ** 6)
'''

FAKE_MME_SERVER = r'''
import json, os, socket, sys, time
from pathlib import Path
a = sys.argv[1:]
FAKE = Path(os.environ["V8_FAKE_DIR"])
port = int([x for x in a if x.startswith("--port=")][0].split("=", 1)[1])
with open(FAKE / "calls.jsonl", "a") as f:
    f.write(json.dumps({"who": "mme_server", "argv": a, "openpi_data_home": os.environ.get("OPENPI_DATA_HOME")}) + "\n")
print("history_config='perceptual-framesamp-modul.yaml'", flush=True)
s = socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); s.bind(("127.0.0.1", port)); s.listen()
time.sleep(10 ** 6)
'''


def _write_exe(p: Path, text: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    p.chmod(0o755)
    return p


def _free_seat_idx() -> int:
    """挑一个两位席号：18000+100*idx 起的 smvla／mme 端口与其 +1 都空闲（避开真席位端口）。"""
    for idx in range(50, 99):
        base = 18000 + 100 * idx
        ok = True
        for p in (base, base + 1, base + 10, base + 11):
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


def _kill_leftovers(marker: str) -> None:
    """测试收尾：杀掉命令行含临时目录的残留进程（假 server／客户端），不碰其他进程。"""
    me = os.getpid()
    for d in Path("/proc").iterdir():
        if not d.name.isdigit() or int(d.name) == me:
            continue
        try:
            cmd = (d / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
        except OSError:
            continue
        if marker in cmd:
            try:
                os.kill(int(d.name), signal.SIGKILL)
            except OSError:
                pass


def _alive_with(marker: str, needle: str) -> list[int]:
    out = []
    for d in Path("/proc").iterdir():
        if not d.name.isdigit():
            continue
        try:
            cmd = (d / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
            state = (d / "stat").read_text().split(")")[-1].split()[0]
        except (OSError, IndexError):
            continue
        if marker in cmd and needle in cmd and state != "Z":
            out.append(int(d.name))
    return out


class Fake:
    """临时假仓库与运行环境。"""

    def __init__(self, tmp: Path):
        self.tmp = tmp
        self.repo = tmp / "repo"
        self.fake = tmp / "fake"
        self.fake.mkdir(parents=True)
        ev = self.repo / "scripts" / "eval-official"
        ev.mkdir(parents=True)
        shutil.copy2(SRC_SEAT, ev / "run_seat.sh")
        shutil.copy2(SRC_GL, ev / "run_v8_gl.sh")
        (ev / "env_client.py").write_text(FAKE_CLIENT)
        (ev / "smvla_server.py").write_text(FAKE_SMVLA_SERVER)
        mme = self.repo / "third_party" / "mme-vla"
        (mme / "scripts").mkdir(parents=True)
        (mme / "scripts" / "serve_policy.py").write_text(FAKE_MME_SERVER)
        cfg = mme / "src" / "mme_vla_suite" / "models" / "config" / "robomme"
        cfg.mkdir(parents=True)
        (cfg / MME_YAML).write_text("x: 1\n")
        wrapper = f"#!/bin/bash\nexec {sys.executable} \"$@\"\n"
        self.bench_py = _write_exe(self.repo / ".venv" / "bin" / "python", wrapper)
        self.mme_py = _write_exe(mme / ".venv" / "bin" / "python", wrapper)
        self.smvla_py = _write_exe(self.repo / "artifacts" / "v8-two" / "venvs" / "smvla-env" / "bin" / "python", wrapper)
        self.bin = tmp / "fakebin"
        _write_exe(self.bin / "git", f"#!/bin/bash\ncase \"$*\" in *rev-parse*) echo {MME_COMMIT};; *) exit 0;; esac\n")
        _write_exe(self.bin / "nvidia-smi", "#!/bin/bash\nexit 0\n")
        # 权重：MME 需父目录 history_config.txt 与 params/assets
        self.mme_ckpt = tmp / "ckpt" / "mme" / "run" / "79999"
        (self.mme_ckpt / "params").mkdir(parents=True)
        (self.mme_ckpt / "assets").mkdir()
        (self.mme_ckpt / "params" / "w.bin").write_bytes(b"w")
        (self.mme_ckpt.parent / "history_config.txt").write_text(MME_YAML)
        self.smvla_ckpt = tmp / "ckpt" / "smvla"
        self.smvla_ckpt.mkdir(parents=True)
        (self.smvla_ckpt / "w.bin").write_bytes(b"s")
        # tokenizer 缓存
        self.openpi = tmp / "openpi-data"
        tok = self.openpi / "big_vision" / "paligemma_tokenizer.model"
        tok.parent.mkdir(parents=True)
        tok.write_bytes(b"fake-tokenizer-bytes")
        self.tok_sha = hashlib.sha256(tok.read_bytes()).hexdigest()
        # 执行清单（C1 shard 行）
        self.shard = tmp / "shard-03.json"
        rows = []
        for task, tier, seed in [("VideoUnmask", "xhard1", 101), ("SwingXtimes", "xhard5", 202)]:
            rows.append({"task": task, "tier": tier, "seed": seed, "candidate": 1, "builder_episode": 0,
                         "source_episode": None, "spec_sha256": "ab" * 32, "effective_max_steps": 1600,
                         "key": f"{task}_{tier}_{seed}"})
        self.shard.write_text(json.dumps(rows))
        self.keys = [r["key"] for r in rows]
        self.old_idents = tmp / "ids-old.json"
        self.old_idents.write_text(json.dumps([{"task": "BinFill", "source_episode": 3, "seed": 7, "builder_episode": 0}]))

    def plan(self, **policies) -> None:
        (self.fake / "plan.json").write_text(json.dumps(policies))

    def env(self, **extra) -> dict:
        env = dict(os.environ)
        for k in ("OPENPI_DATA_HOME", "BENCH_PY", "MME_PY", "SMVLA_PY", "V8_FAKE_SERVER_DIE_FIRST"):
            env.pop(k, None)
        env.update(PATH=f"{self.bin}:{env.get('PATH', '/usr/bin:/bin')}", V8_FAKE_DIR=str(self.fake),
                   BENCH_PY=str(self.bench_py), MME_PY=str(self.mme_py), SMVLA_PY=str(self.smvla_py),
                   V75_DATA_ROOT=str(self.tmp))
        env.update(extra)
        return env

    def calls(self, who: str) -> list[dict]:
        p = self.fake / "calls.jsonl"
        if not p.exists():
            return []
        return [c for c in map(json.loads, p.read_text().splitlines()) if c["who"] == who]

    @property
    def seat_sh(self) -> Path:
        return self.repo / "scripts" / "eval-official" / "run_seat.sh"

    @property
    def gl_sh(self) -> Path:
        return self.repo / "scripts" / "eval-official" / "run_v8_gl.sh"

    def run_seat(self, args: list[str], **env) -> subprocess.CompletedProcess:
        return subprocess.run(["bash", str(self.seat_sh), *args], env=self.env(**env), capture_output=True,
                              text=True, timeout=RUN_TIMEOUT)

    def gl_args(self, idx: int, policies: str = "smvla") -> list[str]:
        return ["--run-name", "t-run", "--seat", f"{idx:02d}", "--repo", str(self.repo), "--stage", str(self.tmp / "stage"),
                "--shard", str(self.shard), "--policies", policies, "--mme-ckpt", str(self.mme_ckpt),
                "--smvla-ckpt", str(self.smvla_ckpt), "--openpi-data-home", str(self.openpi),
                "--tokenizer-sha256", self.tok_sha, "--reset-budget", "10", "--infra-retry-budget", "2",
                "--sync-interval", "1", "--local-root", str(self.tmp / "node-tmp")]


@pytest.fixture
def fk(tmp_path):
    f = Fake(tmp_path)
    yield f
    _kill_leftovers(str(tmp_path))


def _v8_seat_args(fk: Fake, idx: int, out: Path, policies: str = "smvla", **kw) -> list[str]:
    a = ["--seat", "t", "--seat-idx", str(idx), "--gpu", "0", "--cond", "V8", "--out", str(out),
         "--policies", policies, "--identities", str(fk.shard), "--v8", "--ledger-dir", str(out / "led"),
         "--reset-budget", "10", "--infra-retry-budget", "2", "--smvla-ckpt", str(fk.smvla_ckpt),
         "--mme-ckpt", str(fk.mme_ckpt)]
    for k, v in kw.items():
        a += [f"--{k.replace('_', '-')}", v]
    return a


def _opt(argv: list[str], name: str) -> str:
    return argv[argv.index(name) + 1]


# ---------------- run_seat.sh ----------------

def test_旧调用方式参数拼装不变(fk):
    idx = _free_seat_idx()
    out = fk.tmp / "out"
    fk.plan(smvla=[{"write": True}], mme=[{"write": True}])
    p = fk.run_seat(["--seat", "t", "--seat-idx", str(idx), "--gpu", "0", "--cond", "E1", "--out", str(out),
                     "--policies", "smvla,mme", "--identities", str(fk.old_idents), "--smvla-ckpt", str(fk.smvla_ckpt),
                     "--mme-ckpt", str(fk.mme_ckpt)])
    log = (out / "seat-t.log").read_text()
    assert p.returncode == 0, log
    base = 18000 + 100 * idx
    clients = fk.calls("client")
    assert [c["policy"] for c in clients] == ["smvla", "mme"]
    for c, pol, port, wall in [(clients[0], "smvla", base, "600"), (clients[1], "mme", base + 10, "900")]:
        assert c["argv"] == ["run", "--policy", pol, "--identities", str(fk.old_idents), "--order", "forward",
                             "--cond", "E1", "--seat", "t", "--port", str(port), "--out", str(out / pol),
                             "--episode-wall-s", wall, "--first-extra-s", "600", "--limit", "0"], c["argv"]
    mme = fk.calls("mme_server")
    assert len(mme) == 1 and mme[0]["openpi_data_home"] is None  # 旧版不注入 OPENPI_DATA_HOME
    assert "TOKENIZER_SHA" not in log and "V8_MODE" not in log and not (out / ".v8-pgids").exists()
    assert "MME_PREFLIGHT=PASS" in log and "EXIT_CODE=0" in log
    PASSED.append("old_mode")


def test_V8参数须配v8且v8拒绝norecord(fk):
    base = ["--seat", "t", "--seat-idx", "1", "--gpu", "0", "--cond", "E1", "--out", str(fk.tmp / "o"),
            "--identities", str(fk.shard)]
    p = fk.run_seat(base + ["--ledger-dir", str(fk.tmp / "l")])
    assert p.returncode == 2 and "--v8" in p.stderr
    p = fk.run_seat(base + ["--v8", "--ledger-dir", str(fk.tmp / "l"), "--reset-budget", "1",
                            "--infra-retry-budget", "1", "--no-record"])
    assert p.returncode == 2 and "no-record" in p.stderr
    p = fk.run_seat(base + ["--v8", "--ledger-dir", str(fk.tmp / "l"), "--infra-retry-budget", "1"])
    assert p.returncode == 2 and "reset-budget" in p.stderr
    PASSED.append("v8_flags")


def test_单局超时退出75被重启(fk):
    idx = _free_seat_idx()
    out = fk.tmp / "out"
    fk.plan(smvla=[{"exit": 75}, {"write": True}])
    p = fk.run_seat(_v8_seat_args(fk, idx, out, rec_root=str(fk.tmp / "rec")))
    log = (out / "seat-t.log").read_text()
    assert p.returncode == 0, log
    clients = fk.calls("client")
    assert len(clients) == 2 and "CLIENT_EXIT policy=smvla rc=75" in log
    a0, a1 = clients[0]["argv"], clients[1]["argv"]
    assert _opt(a0, "--first-extra-s") == "600" and _opt(a1, "--first-extra-s") == "0"
    for a in (a0, a1):
        assert "--v8" in a and _opt(a, "--episode-wall-s") == "900"
        assert _opt(a, "--ledger") == str(out / "led" / "smvla.ledger.jsonl")
        assert _opt(a, "--reset-budget") == "10" and _opt(a, "--infra-retry-budget") == "2"
        assert _opt(a, "--rec-root") == str(fk.tmp / "rec" / "smvla")
    assert len(fk.calls("smvla_server")) == 1
    rep = json.loads((out / "smvla" / "seat-report.json").read_text())
    assert rep["done"] == 2 and rep["success"] == 2
    PASSED.append("wall_restart")


def test_server死后重起(fk):
    idx = _free_seat_idx()
    out = fk.tmp / "out"
    fk.plan(smvla=[{"sleep": 1000}, {"write": True}])
    p = fk.run_seat(_v8_seat_args(fk, idx, out), V8_FAKE_SERVER_DIE_FIRST="1")
    log = (out / "seat-t.log").read_text()
    assert p.returncode == 0, log
    assert "SERVER_DIED policy=smvla" in log
    assert len(fk.calls("smvla_server")) == 2 and len(fk.calls("client")) == 2
    assert "EXIT_CODE=0" in log
    PASSED.append("server_died")


@pytest.mark.parametrize("code,needle,tag", [(5, "RESET_BUDGET_EXHAUSTED policy=smvla", "no_restart_5"),
                                             (3, "RUN_BLOCKED reason=client policy=smvla", "no_restart_3")])
def test_客户端退出5或3不重启(fk, code, needle, tag):
    idx = _free_seat_idx()
    out = fk.tmp / "out"
    fk.plan(smvla=[{"exit": code}, {"write": True}])
    p = fk.run_seat(_v8_seat_args(fk, idx, out))
    log = (out / "seat-t.log").read_text()
    assert p.returncode == code, log
    assert len(fk.calls("client")) == 1 and needle in log
    assert f"EXIT_CODE={code}" in log and "SERVER_STOPPED" in log
    PASSED.append(tag)


def test_tokenizer哈希不符不启server(fk):
    idx = _free_seat_idx()
    out = fk.tmp / "out"
    fk.plan(mme=[{"write": True}])
    p = fk.run_seat(_v8_seat_args(fk, idx, out, policies="mme", openpi_data_home=str(fk.openpi),
                                  tokenizer_sha256="0" * 64))
    log = (out / "seat-t.log").read_text()
    assert p.returncode == 3, log
    assert "RUN_BLOCKED reason=tokenizer_sha" in log and "TOKENIZER_SHA=PASS" not in log
    assert "SERVER_START" not in log and fk.calls("mme_server") == [] and fk.calls("client") == []
    # 缺参数同样阻塞
    out2 = fk.tmp / "out2"
    p = fk.run_seat(_v8_seat_args(fk, idx, out2, policies="mme"))
    log2 = (out2 / "seat-t.log").read_text()
    assert p.returncode == 3 and "RUN_BLOCKED reason=tokenizer_sha" in log2 and fk.calls("mme_server") == []
    PASSED.append("tokenizer_mismatch")


# ---------------- run_v8_gl.sh ----------------

def _sha_tree(root: Path) -> dict:
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


def test_gl_成功两策略_tokenizer通过_录像同步(fk):
    idx = _free_seat_idx()
    nn = f"{idx:02d}"
    fk.plan(smvla=[{"write": True, "inprogress": True, "orphan": True, "sleep": 4}], mme=[{"write": True}])
    pre = fk.tmp / "stage" / f"s{nn}" / "smvla" / "rec" / f"{fk.keys[1]}.a1"  # 已发布的同名目录：不得覆盖
    pre.mkdir(parents=True)
    (pre / "marker.txt").write_text("keep")
    p = subprocess.run(["bash", str(fk.gl_sh), *fk.gl_args(idx, "smvla,mme")], env=fk.env(),
                       capture_output=True, text=True, timeout=RUN_TIMEOUT)
    o = p.stdout
    assert p.returncode == 0, o + p.stderr
    lines = [l for l in o.splitlines() if l.strip()]
    assert lines[-1] == "EXIT_CODE=0"
    assert any(l.startswith(f"V8_SEAT_DONE seat={nn} outcome=pass rc=0") for l in lines)
    assert f"TOKENIZER_SHA=PASS sha256={fk.tok_sha}" in o
    mme = fk.calls("mme_server")
    assert len(mme) == 1 and mme[0]["openpi_data_home"] == str(fk.openpi)
    stage = fk.tmp / "stage" / f"s{nn}"
    local = fk.tmp / "node-tmp" / "rec"
    clients = {c["policy"]: c["argv"] for c in fk.calls("client")}
    for pol, wall in (("smvla", "900"), ("mme", "1200")):
        a = clients[pol]
        assert "--v8" in a and "--never-degrade" in a and "--no-record" not in a
        assert _opt(a, "--out") == str(stage / pol)
        assert _opt(a, "--ledger") == str(stage / pol / f"{pol}.ledger.jsonl")
        assert _opt(a, "--rec-root") == str(local / pol)
        assert _opt(a, "--episode-wall-s") == wall and _opt(a, "--identities") == str(fk.shard)
        assert (stage / pol / "results.jsonl").exists()
        for k in fk.keys:
            d = stage / pol / "rec" / f"{k}.a1"
            if pol == "smvla" and k == fk.keys[1]:
                assert sorted(x.name for x in d.iterdir()) == ["marker.txt"]  # 原目录未被覆盖
                d = d.with_name(d.name + ".dup1")
            assert (d / "summary.json").exists() and (d / "front.mkv").exists() and (d / "sub" / "meta.json").exists()
        assert list((local / pol).iterdir()) == []  # 节点副本已删
        assert list((stage / pol / "rec" / ".incoming").iterdir()) == []  # 暂存区已全部 mv 走
    # 完成目录在运行中被周期同步搬走；进行中目录（无结果行、无 summary）与无结果行的目录只在收尾全量同步时搬
    for k in fk.keys:
        assert f"REC_SYNCED policy=smvla dir={k}.a1 mode=periodic" in o
    assert f"REC_SYNCED policy=smvla dir={fk.keys[0]}.a9 mode=final" in o
    assert f"dir={fk.keys[0]}.a9 mode=periodic" not in o
    assert "REC_SYNCED policy=smvla dir=Orphan_xhard1_1.a1 mode=final" in o
    assert "dir=Orphan_xhard1_1.a1 mode=periodic" not in o
    assert f"REC_SYNC_DUP dir={fk.keys[1]}.a1 published_as={fk.keys[1]}.a1.dup1" in o
    # 累计：smvla 2 完成 + 1 进行中 + 1 无结果行，mme 2 完成 = 6
    assert any(l.startswith("SEAT_REC_SYNC=PASS n=6 ") and " left=0 " in l for l in lines), o
    assert (stage / f"run_v8_gl-s{nn}.log").exists() and (stage / "smvla" / f"seat-{nn}.log").exists()
    PASSED.append("gl_success")


def test_gl_sha不符不删源(fk):
    idx = _free_seat_idx()
    nn = f"{idx:02d}"
    # rsync 包装：同步后故意改坏目的端 corrupt.bin，模拟传输损坏
    _write_exe(fk.bin / "rsync", "#!/bin/bash\n/usr/bin/rsync \"$@\"; rc=$?\ndst=\"${@: -1}\"\n"
                                 "[[ -f \"$dst/corrupt.bin\" ]] && echo x >> \"$dst/corrupt.bin\"\nexit $rc\n")
    fk.plan(smvla=[{"write": True, "corrupt": True}])
    p = subprocess.run(["bash", str(fk.gl_sh), *fk.gl_args(idx)], env=fk.env(), capture_output=True, text=True,
                       timeout=RUN_TIMEOUT)
    o = p.stdout
    assert p.returncode == 7, o + p.stderr
    assert "REC_SYNC_SHA_MISMATCH file=corrupt.bin" in o
    assert any(l.startswith("SEAT_REC_SYNC=FAIL n=0 bytes=0 left=2 ") for l in o.splitlines()), o
    assert f"V8_SEAT_DONE seat={nn} outcome=fail rc=7" in o and o.strip().splitlines()[-1] == "EXIT_CODE=7"
    local = fk.tmp / "node-tmp" / "rec" / "smvla"
    pub = fk.tmp / "stage" / f"s{nn}" / "smvla" / "rec"
    for k in fk.keys:  # 源未删，也未发布（只留在 .incoming）
        assert (local / f"{k}.a1" / "front.mkv").exists()
        assert not (pub / f"{k}.a1").exists() and (pub / ".incoming" / f"{k}.a1").exists()
    PASSED.append("gl_sha_mismatch")


def _wait_for(path: Path, timeout: float = 60) -> None:
    t0 = time.time()
    while not path.exists():
        if time.time() - t0 > timeout:
            raise AssertionError(f"等待超时：{path}")
        time.sleep(0.2)


def test_gl_TERM中断仍全量同步(fk):
    idx = _free_seat_idx()
    nn = f"{idx:02d}"
    fk.plan(smvla=[{"inprogress": True, "sleep": 1000}])
    proc = subprocess.Popen(["bash", str(fk.gl_sh), *fk.gl_args(idx)], env=fk.env(), stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True)
    try:
        _wait_for(fk.fake / "client_smvla_ready")
        time.sleep(1.5)  # 让周期同步至少跑一轮（进行中目录不应被搬）
        proc.send_signal(signal.SIGTERM)
        o, _ = proc.communicate(timeout=RUN_TIMEOUT)
    finally:
        if proc.poll() is None:
            proc.kill()
    assert proc.returncode == 143, o
    assert "V8_SEAT_SIGNAL sig=TERM" in o
    assert f"dir={fk.keys[0]}.a9 mode=periodic" not in o
    assert f"REC_SYNCED policy=smvla dir={fk.keys[0]}.a9 mode=final" in o
    assert any(l.startswith("SEAT_REC_SYNC=PASS n=1 ") and " left=0 " in l for l in o.splitlines()), o
    assert f"V8_SEAT_DONE seat={nn} outcome=aborted rc=143" in o and o.strip().splitlines()[-1] == "EXIT_CODE=143"
    d = fk.tmp / "stage" / f"s{nn}" / "smvla" / "rec" / f"{fk.keys[0]}.a9" / "front.mkv"
    assert d.exists()
    time.sleep(0.5)
    assert _alive_with(str(fk.tmp), "env_client.py") == [] and _alive_with(str(fk.tmp), "smvla_server.py") == []
    PASSED.append("gl_term")


def test_gl_参数错误也写收尾行(fk):
    p = subprocess.run(["bash", str(fk.gl_sh), "--run-name", "r", "--seat", "3"], env=fk.env(), capture_output=True,
                       text=True, timeout=30)
    assert p.returncode == 2
    assert "V8_SEAT_DONE seat=3 outcome=fail rc=2" in p.stdout and p.stdout.strip().splitlines()[-1] == "EXIT_CODE=2"
    p = subprocess.run(["bash", str(fk.gl_sh), *fk.gl_args(1), "--no-record"], env=fk.env(), capture_output=True,
                       text=True, timeout=30)
    assert p.returncode == 2 and "outcome=fail rc=2" in p.stdout
    PASSED.append("gl_bad_args")


def test_gl_TERM发给全组仍写出收尾三行(fk):
    """模拟 slurmstepd：TERM 同时发给主进程、全部 tee、run_seat.sh、server、客户端。"""
    idx = _free_seat_idx()
    nn = f"{idx:02d}"
    fk.plan(smvla=[{"inprogress": True, "sleep": 1000}])
    proc = subprocess.Popen(["bash", str(fk.gl_sh), *fk.gl_args(idx)], env=fk.env(), stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True)
    try:
        _wait_for(fk.fake / "client_smvla_ready")
        time.sleep(1.0)
        tees = _alive_with(str(fk.tmp), "tee ")
        assert len(tees) >= 3, tees  # 主日志、每策略日志、run_seat 日志三个 tee
        targets = set(_alive_with(str(fk.tmp), "")) | {proc.pid}
        t0 = time.time()
        for pid in targets:
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
        o, _ = proc.communicate(timeout=RUN_TIMEOUT)
        took = time.time() - t0
    finally:
        if proc.poll() is None:
            proc.kill()
    assert proc.returncode == 143, o
    lines = [l for l in o.splitlines() if l.strip()]
    assert any(l.startswith("SEAT_REC_SYNC=PASS n=1 ") for l in lines), o
    assert any(l.startswith(f"V8_SEAT_DONE seat={nn} outcome=aborted rc=143") for l in lines), o
    assert lines[-1] == "EXIT_CODE=143"
    log = (fk.tmp / "stage" / f"s{nn}" / f"run_v8_gl-s{nn}.log").read_text()
    for needle in ("SEAT_REC_SYNC=PASS", f"V8_SEAT_DONE seat={nn} outcome=aborted rc=143", "EXIT_CODE=143"):
        assert needle in log
    assert took < 60, took
    PASSED.append("gl_term_group")


def test_gl_监督进程被杀_回收并收尾(fk):
    idx = _free_seat_idx()
    nn = f"{idx:02d}"
    fk.plan(smvla=[{"inprogress": True, "sleep": 1000}])
    proc = subprocess.Popen(["bash", str(fk.gl_sh), *fk.gl_args(idx)], env=fk.env(), stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True)
    try:
        _wait_for(fk.fake / "client_smvla_ready")
        for pid in _alive_with(str(fk.tmp), "run_seat.sh"):
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
        o, _ = proc.communicate(timeout=RUN_TIMEOUT)
    finally:
        if proc.poll() is None:
            proc.kill()
    assert proc.returncode == 137, o
    assert "V8_SUPERVISOR_DIED" in o and "REAP_ORPHAN role=client" in o and "REAP_ORPHAN role=server" in o
    assert "REAP_ORPHAN_GONE role=client" in o and "REAP_ORPHAN_GONE role=server" in o
    assert f"V8_SEAT_DONE seat={nn} outcome=fail rc=137" in o and o.strip().splitlines()[-1] == "EXIT_CODE=137"
    assert any(l.startswith("SEAT_REC_SYNC=PASS") for l in o.splitlines())
    time.sleep(0.5)
    assert _alive_with(str(fk.tmp), "env_client.py") == [] and _alive_with(str(fk.tmp), "smvla_server.py") == []
    PASSED.append("gl_supervisor_dead")


def test_zz_判定行():
    missing = [t for t in EXPECTED if t not in PASSED]
    if missing:
        print(f"V8_EVAL_ORCHESTRATION=FAIL missing={','.join(missing)}")
    assert not missing
    print(f"V8_EVAL_ORCHESTRATION=PASS cases={len(PASSED)}")
