#!/usr/bin/env python3
"""轻量测试：v8 P4 接续脚本与独立 watchdog 的六种夹具（v8 方案第二部分 §2.4.4、§2.12 S2-D；AGENTS.md P4）。

不触发仿真、不起真浏览器。合成目录取 S4-A ``test_v8_site_catalog.build_synthetic``（3 格 5 局 + 16×12 xhard0），
在其 ``delivery.json`` 上补全 S2-B 聚合契约（``specs_root``／``cells_table``／``exec_cap``／计数键显式写零／``line``）。
**真实调用**：``site/v8_site_catalog.py``、``site/v8_subgoal_lengths.py``、``site/v8_site.py``（真服务进程）与
``scripts/parity/hard_regression.py step-headroom``；``delivery-set``／``tier-values`` 与两个浏览器检查器用
``--cmd`` 换成假命令（假检查器会真的向服务发 HTTP 请求）。

六种情形：①成功（watchdog 收到 ``P4_WATCHDOG=DONE``）；②生成报告是 FAIL 行；③完成事件超时未到；④守卫 FAIL
（假 ``V8_STEP_CAP over=1`` 与真 step-headroom 的 ``filtered_mismatch``）；⑤检查器崩溃——(a) 只 SIGKILL 检查器，
接续脚本自报 FAIL；(b) SIGKILL 检查器并 SIGKILL 接续脚本本身，**由 watchdog 按心跳停更报出 ``P4_WATCHDOG=FAIL``**，
再续行只跑未完成步骤；⑥同一完成事件重复到达（复用报告、不重跑、不覆盖；身份不符拒绝）。另有零计数报告
「写 JSON → 读 JSON → 接续守卫」往返与缺键即 FAIL。全部通过时打印
``S2D_FIXTURES=PASS cases=6 watchdog_detected=1``。

    uv run --no-sync python -m pytest tests/lightweight/test_v8_continue_fixtures.py -q -s
"""
from __future__ import annotations

import importlib.util
import json
import os
import shlex
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CONTINUE = ROOT / "scripts/injection-dev/v8_continue_after_gen.py"
WATCHDOG = ROOT / "scripts/injection-dev/v8_watchdog.py"
PY = sys.executable
CASES: dict[str, bool] = {}
DETECTED: list[str] = []

FAKE = r'''
import argparse, os, sys, time, urllib.request
ap = argparse.ArgumentParser()
ap.add_argument("--line", action="append", default=[])
ap.add_argument("--exit", type=int, default=0)
ap.add_argument("--get", action="append", default=[])
ap.add_argument("--pidfile")
ap.add_argument("--hang-if")
ap.add_argument("--orphan-pidfile")
a = ap.parse_args()
if a.orphan_pidfile:  # 留一个继承 stdout 管道的孙进程，自己先退出
    import subprocess
    child = subprocess.Popen(["sleep", "60"])
    open(a.orphan_pidfile, "w").write(str(child.pid))
for url in a.get:
    body = urllib.request.urlopen(url, timeout=10).read()
    print(f"GET {url} bytes={len(body)}", flush=True)
if a.pidfile:
    open(a.pidfile + ".tmp", "w").write(str(os.getpid()))
    os.replace(a.pidfile + ".tmp", a.pidfile)
if a.hang_if and os.path.exists(a.hang_if):
    print("hanging", flush=True)
    time.sleep(120)
for line in a.line:
    print(line, flush=True)
sys.exit(a.exit)
'''


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


S4A = _load("test_v8_site_catalog_for_s2d", ROOT / "tests/lightweight/test_v8_site_catalog.py")
CONT = _load("v8_continue_after_gen_t", CONTINUE)


# ── 合成目录 ─────────────────────────────────────────────────────────


def write_delivery(src: dict, name: str, **edit) -> Path:
    """在 S4-A 合成 delivery.json 上补全 S2-B 聚合契约，写到 gen1 目录（行的 path 相对该目录）。"""
    base = json.loads(Path(src["delivery"]).read_text(encoding="utf-8"))
    cells = json.loads(Path(src["cells_json"]).read_text(encoding="utf-8"))
    n = len(base["rows"])
    counts = {key: 0 for key in CONT.DELIVERY_COUNT_KEYS}  # 显式写零
    counts.update(expected=n, candidates=n + len(cells), tried=n, delivered=n, spares_left=len(cells))
    tasks = len({k.split("/")[0] for k in cells})
    data = {**base, "specs_root": str(src["specs_root"]), "exec_cap": 1600, "cells_source": "custom",
            "cells_table": {k.replace("/", "@"): v for k, v in cells.items()}, "counts": counts,
            "line": (f"V8_DELIVERY_SET=PASS tasks={tasks} cells={len(cells)} total={n} expected={n} failed=0 "
                     f"exec_over_cap=0 backfills=0 infra_retries=0 exhausted_cells=0 pending_cells=0 bad_h5=0")}
    for key, value in edit.items():
        if key == "drop_count":
            del data["counts"][value]
        elif key == "counts":
            data["counts"].update(value)
        else:
            data[key] = value
    path = Path(src["delivery"]).parent / name
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


@pytest.fixture(scope="module")
def synth(tmp_path_factory):
    root = tmp_path_factory.mktemp("v8s2d")
    src = S4A.build_synthetic(root, S4A.SMALL)
    x0 = root / "xhard0-steps.jsonl"
    rows = [json.loads(t) for t in (src["xhard0_gen"] / "manifest-H.jsonl").read_text().splitlines() if t.strip()]
    x0.write_text("".join(json.dumps({"tier": "xhard0", "task": r["task"], "seed": r["seed"], "path": r["h5"],
                                      "success": not r.get("generation_failed")}) + "\n" for r in rows))
    fake = root / "fake_step.py"
    fake.write_text(FAKE)
    src.update(root=root, x0=x0, fake=fake, ok=write_delivery(src, "delivery.v8.json"))
    return src


def fake_cmd(src: dict, *lines: str, exit_code: int = 0, get: tuple[str, ...] = (), pidfile: Path | None = None,
             hang_if: Path | None = None, orphan_pidfile: Path | None = None) -> str:
    argv = ["{python}", str(src["fake"])]
    if orphan_pidfile:
        argv += ["--orphan-pidfile", str(orphan_pidfile)]
    for line in lines:
        argv += ["--line", line]
    for url in get:
        argv += ["--get", url]
    if pidfile:
        argv += ["--pidfile", str(pidfile)]
    if hang_if:
        argv += ["--hang-if", str(hang_if)]
    argv += ["--exit", str(exit_code)]
    return shlex.join(argv)


GUARD_OK = {
    "delivery_set": ("V8_DELIVERY_SET=PASS tasks=3 cells=3 total=5 expected_cells=3 expected_total=5 cell_mismatch=0",
                     "V8_SEED_DISJOINT=PASS tasks=3 tier_pairs=0 shared=0",
                     "V8_LAYOUT_INDEPENDENT=PASS files=3 delivered=5 parent_non_null=0 layout_equal_pairs=0"),
    "tier_values": ("V8_TIER_VALUES=PASS tasks=3 cells=3 mismatches=0",),
}


def cont_args(src: dict, work: Path, site: Path, *, delivery: Path | None = None, cmds: dict | None = None,
              extra: tuple[str, ...] = ()) -> list[str]:
    cmd = {name: fake_cmd(src, *lines) for name, lines in GUARD_OK.items()}
    cmd["site_check"] = fake_cmd(src, "V8_SITE=PASS sections=15 eval_placeholders=0 eval_filter_hits=0", get=("{base}/",))
    cmd["oracle_check"] = fake_cmd(src, "V8_ORACLE_BROWSER=PASS cells={expect_cells} missing=0",
                                   get=("{base}/api/catalog",))
    cmd.update(cmds or {})
    argv = ["--delivery", str(delivery or src["ok"]), "--specs-root", str(src["specs_root"]),
            "--cells", str(src["cells_json"]), "--work-dir", str(work), "--site-dir", str(site),
            "--xhard0-steps", str(src["x0"]), "--xhard0-manifest", str(src["xhard0_gen"] / "manifest-H.jsonl"),
            "--xhard0-gen", str(src["xhard0_gen"]), "--path-base", str(src["root"]), "--media-root", str(src["root"]),
            "--workers", "0", "--port", "0", "--beat-s", "0.5", "--poll-s", "0.1", *extra]
    for name, value in cmd.items():
        argv += ["--cmd", f"{name}={value}"]
    return argv


def run_continue(argv: list[str], timeout: float = 90) -> subprocess.CompletedProcess:
    return subprocess.run([PY, str(CONTINUE), *argv], capture_output=True, text=True, timeout=timeout, cwd=ROOT)


def start_continue(argv: list[str]) -> subprocess.Popen:
    return subprocess.Popen([PY, str(CONTINUE), *argv], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            cwd=ROOT, start_new_session=True)


def start_watchdog(work: Path, *extra: str) -> subprocess.Popen:
    work.mkdir(parents=True, exist_ok=True)
    return subprocess.Popen([PY, str(WATCHDOG), "--heartbeat", str(work / "heartbeat.json"),
                             "--report", str(work / "report.json"), "--event-log", str(work / "events.log"),
                             "--poll-s", "0.2", *extra], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)


def last(text: str, prefix: str) -> str:
    lines = [l for l in text.splitlines() if l.startswith(prefix)]
    assert lines, f"没有 {prefix} 行：\n{text[-3000:]}"
    return lines[-1]


def kv(line: str) -> dict[str, str]:
    return dict(part.split("=", 1) for part in line.split() if "=" in part)


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    try:
        with open(f"/proc/{pid}/stat") as handle:
            return handle.read().rsplit(")", 1)[1].split()[0] != "Z"
    except OSError:
        return False


def wait_file(path: Path, timeout: float = 60) -> None:
    deadline = time.time() + timeout
    while not path.exists():
        assert time.time() < deadline, f"{path} 未出现"
        time.sleep(0.05)


def snapshot(work: Path) -> dict[str, tuple[int, int]]:
    return {str(p.relative_to(work)): (p.stat().st_size, p.stat().st_mtime_ns)
            for p in sorted(work.rglob("*"))
            if p.is_file() and p.name not in ("events.log", "events2.log", ".lock", "heartbeat.json")}


# ── ① 成功 ────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def success(synth, tmp_path_factory):
    work = tmp_path_factory.mktemp("work_ok")
    site = synth["root"] / "site-ok"
    wd = start_watchdog(work, "--stale-s", "20")
    argv = cont_args(synth, work, site)
    proc = run_continue(argv)
    wd_out, _ = wd.communicate(timeout=20)
    return {"work": work, "site": site, "argv": argv, "proc": proc, "wd_rc": wd.returncode, "wd_out": wd_out}


def test_1_成功_真实建站入口与watchdog_DONE(success):
    proc, work = success["proc"], success["work"]
    assert proc.returncode == 0, proc.stdout[-4000:]
    final = last(proc.stdout, "V8_CONTINUE=")
    assert final.startswith("V8_CONTINUE=PASS step=done") and "site=built" in final and "reused=0" in final
    report = json.loads((work / "report.json").read_text())
    steps = {s["step"]: s for s in report["steps"]}
    assert list(steps) == ["wait_report", "report", "delivery_set", "tier_values", "step_headroom", "identities",
                           "catalog", "subgoals", "serve", "site_check", "oracle_check", "stop_serve"]
    assert all(s["status"] == "PASS" for s in steps.values()), steps
    # 真实入口的判定行原文、退出码、耗时都进报告
    assert steps["catalog"]["lines"][0].startswith("V8_SITE_CATALOG=PASS identities=197 expected=197")
    assert steps["subgoals"]["lines"][0].startswith("V8_SUBGOALS=PASS") and steps["subgoals"]["rc"] == 0
    assert steps["step_headroom"]["lines"][0].startswith("V8_STEP_CAP=PASS") and "filtered=0" in steps["step_headroom"]["lines"][0]
    assert steps["serve"]["lines"][0].startswith("V8_SITE_READY")
    assert all(isinstance(s["elapsed_s"], float) for s in steps.values())
    assert "source=synthesized rows=197 v8=5 xhard0=192" in steps["identities"]["lines"][0]
    assert (success["site"] / "catalog.json").is_file() and (success["site"] / "subgoals.json").is_file()
    # 假检查器真的打到了服务；服务进程组已收掉
    assert "GET http://127.0.0.1:" in (work / "logs/site_check.log").read_text()
    assert not alive(steps["serve"]["server_pid"])
    # watchdog 看到收尾：DONE，退出 0
    assert success["wd_rc"] == 0, success["wd_out"]
    assert last(success["wd_out"], "P4_WATCHDOG=").startswith("P4_WATCHDOG=DONE verdict=PASS step=done")
    events = (work / "events.log").read_text()
    assert final in events.splitlines() and "P4_WATCHDOG=DONE verdict=PASS" in events and "P4_NOTIFY" not in events
    hb = json.loads((work / "heartbeat.json").read_text())
    assert hb["status"] == "done" and set(CONT.COUNT_KEYS) <= set(hb["counts"])
    CASES["1_success"] = True


def test_零计数报告_写JSON读JSON接续守卫往返(synth, success, tmp_path):
    # 写出端：零值计数键逐个显式落盘
    disk = json.loads(Path(synth["ok"]).read_text())
    for key in ("exec_over_cap", "backfills", "infra_retries", "failed", "pending", "bad_h5", "failed_cells"):
        assert key in disk["counts"] and disk["counts"][key] == 0
    # 接续端：读回的报告与心跳里零值仍是显式键（不是缺省兜底）
    report = json.loads((success["work"] / "report.json").read_text())
    for key in ("exec_over_cap", "filtered", "backfills", "infra_retries", "failed", "steps_failed"):
        assert key in report["counts"] and report["counts"][key] == 0
    assert '"infra_retries":0' in report["steps"][1]["lines"][-1]
    # 缺一个计数键（哪怕本该是 0）→ report 步 FAIL，不跑守卫、不建站
    bad = write_delivery(synth, "delivery.nokey.json", drop_count="infra_retries")
    work, site = tmp_path / "work", synth["root"] / "site-nokey"
    proc = run_continue(cont_args(synth, work, site, delivery=bad))
    final = last(proc.stdout, "V8_CONTINUE=")
    assert proc.returncode == 1 and final.startswith("V8_CONTINUE=FAIL step=report")
    assert "count_keys_absent:infra_retries" in final
    assert not (work / "logs/delivery_set.log").exists() and not site.exists()


# ── ② 生成报告出现 FAIL 行 ─────────────────────────────────────────────


def test_2_生成报告FAIL行_停在报告且不建站(synth, tmp_path):
    bad = write_delivery(synth, "delivery.failline.json",
                         line="V8_DELIVERY_SET=FAIL tasks=3 cells=3 total=5 problems=StopCube/xhard1:exhausted")
    work, site = tmp_path / "work", synth["root"] / "site-failline"
    proc = run_continue(cont_args(synth, work, site, delivery=bad))
    assert proc.returncode == 1
    final = last(proc.stdout, "V8_CONTINUE=")
    assert final.startswith("V8_CONTINUE=FAIL step=report") and "line_not_pass" in final and "site=not_built" in final
    events = (work / "events.log").read_text()
    assert "P4_NOTIFY=FAIL step=report" in events and final in events
    report = json.loads((work / "report.json").read_text())
    assert [s["step"] for s in report["steps"]] == ["wait_report", "report"]
    assert report["steps"][1]["lines"][0].startswith("V8_DELIVERY_SET=FAIL")
    assert not site.exists() and not (work / "logs/delivery_set.log").exists()
    CASES["2_report_fail"] = True


# ── ③ 完成事件超时未到 ─────────────────────────────────────────────────


def test_3_完成行超时未到_FAIL并通知(synth, tmp_path):
    work, site = tmp_path / "work", synth["root"] / "site-timeout"
    wd = start_watchdog(work, "--stale-s", "20")
    never = Path(synth["ok"]).parent / "delivery.never.json"
    proc = run_continue(cont_args(synth, work, site, delivery=never, extra=("--wait-timeout", "1")))
    wd_out, _ = wd.communicate(timeout=20)
    final = last(proc.stdout, "V8_CONTINUE=")
    assert proc.returncode == 1 and final.startswith("V8_CONTINUE=FAIL step=wait_report")
    assert "reason=timeout_1s:delivery.json未出现" in final and not site.exists()
    assert "P4_NOTIFY=FAIL step=wait_report" in (work / "events.log").read_text()
    # 接续脚本自己收尾了（FAIL 报告），watchdog 报 DONE verdict=FAIL，不被误当成停更
    assert wd.returncode == 0 and last(wd_out, "P4_WATCHDOG=").startswith("P4_WATCHDOG=DONE verdict=FAIL step=wait_report")
    # 报告已在、但生成日志迟迟没有 EXIT_CODE 行 → 同样超时
    gen_log = tmp_path / "gen.log"
    gen_log.write_text("V8_DELIVERY_SET=PASS ...\n")
    proc = run_continue(cont_args(synth, tmp_path / "work2", synth["root"] / "site-timeout2",
                                  extra=("--wait-timeout", "0.5", "--gen-log", str(gen_log))))
    assert proc.returncode == 1 and "EXIT_CODE行未出现" in last(proc.stdout, "V8_CONTINUE=")
    CASES["3_timeout"] = True


# ── ④ 守卫 FAIL ─────────────────────────────────────────────────────


def test_4_守卫FAIL_停在守卫且不建站(synth, tmp_path):
    work, site = tmp_path / "work", synth["root"] / "site-guard"
    over = fake_cmd(synth, "V8_STEP_CAP=FAIL max=1700 cap=1600 over=1 filtered=0 xhard0_max=9 xhard0_cap=1300",
                    exit_code=1)
    proc = run_continue(cont_args(synth, work, site, cmds={"step_headroom": over}))
    final = last(proc.stdout, "V8_CONTINUE=")
    assert proc.returncode == 1 and final.startswith("V8_CONTINUE=FAIL step=step_headroom") and "reason=exit_1" in final
    report = json.loads((work / "report.json").read_text())
    assert report["steps"][-1]["lines"] == ["V8_STEP_CAP=FAIL max=1700 cap=1600 over=1 filtered=0 xhard0_max=9 "
                                            "xhard0_cap=1300"]
    assert not site.exists() and not (work / "logs/catalog.log").exists()
    # 真 step-headroom：delivery 报 exec_over_cap=1 而候选池里 0 个 → filtered_mismatch → FAIL
    bad = write_delivery(synth, "delivery.overcap.json", counts={"exec_over_cap": 1})
    work2 = tmp_path / "work2"
    proc = run_continue(cont_args(synth, work2, synth["root"] / "site-guard2", delivery=bad))
    final = last(proc.stdout, "V8_CONTINUE=")
    assert proc.returncode == 1 and final.startswith("V8_CONTINUE=FAIL step=step_headroom")
    line = json.loads((work2 / "report.json").read_text())["steps"][-1]["lines"][0]
    assert line.startswith("V8_STEP_CAP=FAIL") and "filtered_mismatch=1" in line
    # 不给 xhard0 来源：step-headroom 只出 INFO，不冒充 PASS，缺省不建站
    work3 = tmp_path / "work3"
    argv = cont_args(synth, work3, synth["root"] / "site-guard3")
    i = argv.index("--xhard0-steps")
    del argv[i:i + 2]
    proc = run_continue(argv)
    final = last(proc.stdout, "V8_CONTINUE=")
    assert proc.returncode == 3 and final.startswith("V8_CONTINUE=INFO step=step_headroom") and "site=not_built" in final
    assert json.loads((work3 / "report.json").read_text())["steps"][-1]["lines"][0].startswith("V8_STEP_CAP=INFO")
    CASES["4_guard_fail"] = True


# ── ⑤ 检查器崩溃 ────────────────────────────────────────────────────


def test_5a_只杀检查器_接续脚本自报FAIL且收掉服务(synth, tmp_path):
    work, site = tmp_path / "work", synth["root"] / "site-crash-a"
    pidfile, flag = tmp_path / "checker.pid", tmp_path / "hang"
    flag.write_text("1")
    hang = fake_cmd(synth, "V8_SITE=PASS sections=15", pidfile=pidfile, hang_if=flag)
    wd = start_watchdog(work, "--stale-s", "20")
    proc = start_continue(cont_args(synth, work, site, cmds={"site_check": hang}))
    try:
        wait_file(pidfile)
        os.kill(int(pidfile.read_text()), signal.SIGKILL)  # 真正 kill 被监督的检查器
        out, _ = proc.communicate(timeout=30)
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL)
    wd_out, _ = wd.communicate(timeout=20)
    final = last(out, "V8_CONTINUE=")
    assert proc.returncode == 1 and final.startswith("V8_CONTINUE=FAIL step=site_check") and "reason=exit_-9" in final
    report = json.loads((work / "report.json").read_text())
    serve = next(s for s in report["steps"] if s["step"] == "serve")
    assert report["steps"][-1]["step"] == "stop_serve" and not alive(serve["server_pid"])
    assert wd.returncode == 0 and last(wd_out, "P4_WATCHDOG=").startswith("P4_WATCHDOG=DONE verdict=FAIL step=site_check")


def test_5b_接续脚本与检查器一起崩溃_watchdog报FAIL_续行只跑未完成步骤(synth, tmp_path):
    work, site = tmp_path / "work", synth["root"] / "site-crash-b"
    pidfile, flag = tmp_path / "checker.pid", tmp_path / "hang"
    flag.write_text("1")
    hang = fake_cmd(synth, "V8_SITE=PASS sections=15", pidfile=pidfile, hang_if=flag)
    argv = cont_args(synth, work, site, cmds={"site_check": hang})
    proc = start_continue(argv)
    wd = start_watchdog(work, "--stale-s", "60", "--step-stale", "site_check=2", "--kill-pid", str(proc.pid),
                        "--kill-grace-s", "0.5", "--kill-heartbeat-groups")
    server_pid = None
    try:
        wait_file(pidfile)
        checker = int(pidfile.read_text())
        server_pid = json.loads((work / "heartbeat.json").read_text())["server_pid"]
        os.kill(proc.pid, signal.SIGKILL)  # 接续脚本自己崩溃：不会再写心跳、报告与收尾行
        os.kill(checker, signal.SIGKILL)   # 被监督的检查器同时被杀
        proc.wait(timeout=10)
        wd_out, _ = wd.communicate(timeout=30)
    finally:
        for pid in (proc.pid, server_pid):
            if pid and alive(pid):
                os.killpg(pid, signal.SIGKILL)
    line = last(wd_out, "P4_WATCHDOG=")
    assert wd.returncode == 1, wd_out
    assert line.startswith("P4_WATCHDOG=FAIL step=site_check") and "reason=stale" in line
    assert int(kv(line)["stale_s"]) >= 2 and f"pid{proc.pid}:gone" in line
    # 接续脚本被 SIGKILL 后服务进程组成了孤儿：watchdog 按心跳记录的 server_pid（核 pgid == pid）收掉
    assert f"pg{server_pid}:term" in line or f"pg{server_pid}:kill" in line
    assert not alive(server_pid)
    assert line in (work / "events.log").read_text().splitlines()
    assert not (work / "report.json").exists()
    DETECTED.append(line)
    # 续行：同一输入、同一 work-dir；已 PASS 的步骤核产物后复用（catalog／subgoals 不重跑），只跑服务与检查
    flag.unlink()
    catalog_before = (site / "catalog.json").stat().st_mtime_ns
    proc2 = run_continue(argv)
    assert proc2.returncode == 0, proc2.stdout[-3000:]
    assert last(proc2.stdout, "V8_CONTINUE=").startswith("V8_CONTINUE=PASS step=done")
    steps = {s["step"]: s for s in json.loads((work / "report.json").read_text())["steps"]}
    assert all(steps[s]["reused"] for s in ("delivery_set", "tier_values", "step_headroom", "identities", "catalog",
                                            "subgoals"))
    assert not steps["site_check"]["reused"] and not steps["serve"]["reused"]
    assert (site / "catalog.json").stat().st_mtime_ns == catalog_before
    assert (work / "logs/catalog.log").read_text().count("EXIT_CODE=") == 1
    CASES["5_crash"] = True


# ── ⑥ 同一完成事件重复到达 ─────────────────────────────────────────────


def test_6_重复到达_复用报告不重跑不覆盖_身份不符拒绝(synth, success):
    work = success["work"]
    before = snapshot(work)
    site_before = {p.name: p.stat().st_mtime_ns for p in success["site"].iterdir()}
    events2 = work / "events2.log"
    proc = run_continue(success["argv"] + ["--event-log", str(events2)])
    assert proc.returncode == 0, proc.stdout
    line = last(proc.stdout, "V8_CONTINUE=")
    assert line.startswith("V8_CONTINUE=PASS step=done") and "reused=1" in line
    assert "V8_CONTINUE_STEP" not in proc.stdout and "[catalog]" not in proc.stdout
    assert snapshot(work) == before
    # 新事件日志里只有 reused=1 的收尾行：watchdog 去掉 reused= 后与报告收尾行相等 → DONE
    wd = subprocess.run([PY, str(WATCHDOG), "--heartbeat", str(work / "heartbeat.json"), "--report",
                         str(work / "report.json"), "--event-log", str(events2), "--stale-s", "5", "--poll-s", "0.2"],
                        capture_output=True, text=True, timeout=20)
    assert wd.returncode == 0 and last(wd.stdout, "P4_WATCHDOG=").startswith("P4_WATCHDOG=DONE verdict=PASS")
    assert {p.name: p.stat().st_mtime_ns for p in success["site"].iterdir()} == site_before
    # 输入身份变了（换一份 delivery）→ 拒绝复用，也不覆盖
    other = write_delivery(synth, "delivery.other.json", cells_source="other")
    argv = list(success["argv"])
    argv[argv.index("--delivery") + 1] = str(other)
    proc = run_continue(argv)
    assert proc.returncode == 2 and "report_identity_mismatch:delivery" in last(proc.stdout, "V8_CONTINUE=")
    assert snapshot(work) == before
    CASES["6_duplicate"] = True


def test_B1_续行时旧心跳不被当本轮_watchdog报DONE(synth, tmp_path):
    """上一轮遗留 aborted 且早已过期的心跳：watchdog 先起、接续脚本后起，不得第一圈就判 FAIL。"""
    work, site = tmp_path / "work", synth["root"] / "site-oldbeat"
    work.mkdir()
    old = work / "heartbeat.json"
    old.write_text(json.dumps({"schema": "v8-continue-heartbeat/1", "step": "site_check", "status": "aborted",
                               "pid": 1, "counts": {}}))
    os.utime(old, (time.time() - 3600, time.time() - 3600))
    wd = start_watchdog(work, "--stale-s", "5")
    time.sleep(0.6)  # watchdog 已转过几圈，仍只把旧心跳当「尚无心跳」
    assert wd.poll() is None, wd.stdout.read()
    bad = write_delivery(synth, "delivery.oldbeat.json", line="V8_DELIVERY_SET=FAIL tasks=3 cells=3 total=5")
    proc = run_continue(cont_args(synth, work, site, delivery=bad))
    wd_out, _ = wd.communicate(timeout=20)
    assert proc.returncode == 1
    assert wd.returncode == 0, wd_out
    assert last(wd_out, "P4_WATCHDOG=").startswith("P4_WATCHDOG=DONE verdict=FAIL step=report")
    # --watch-pid：心跳 pid 不是被监督进程的，同样不算本轮
    old.write_text(json.dumps({"step": "x", "status": "aborted", "pid": 1}))
    wd = subprocess.run([PY, str(WATCHDOG), "--heartbeat", str(old), "--report", str(tmp_path / "none.json"),
                         "--event-log", str(tmp_path / "ev.log"), "--stale-s", "60", "--grace-s", "0.5",
                         "--poll-s", "0.1", "--watch-pid", str(os.getpid())], capture_output=True, text=True, timeout=20)
    line = last(wd.stdout, "P4_WATCHDOG=")
    assert wd.returncode == 1 and line.startswith("P4_WATCHDOG=FAIL step=absent") and "reason=no_heartbeat" in line


def test_B2_N5_孙进程占管道_判定行不丢且收尾无孤儿_failed与backfills非零仍通过(synth, tmp_path):
    work, site = tmp_path / "work", synth["root"] / "site-orphan"
    orphan = tmp_path / "orphan.pid"
    # N5：counts.failed=2、backfills=2（正常递补）而 V8_DELIVERY_SET=PASS → report 步应通过
    dl = write_delivery(synth, "delivery.backfill.json", counts={"failed": 2, "backfills": 2, "tried": 7})
    ds = fake_cmd(synth, *GUARD_OK["delivery_set"], orphan_pidfile=orphan)
    stop = fake_cmd(synth, "V8_TIER_VALUES=FAIL tasks=3 cells=3 mismatches=1", exit_code=1)
    started = time.time()
    proc = run_continue(cont_args(synth, work, site, delivery=dl, cmds={"delivery_set": ds, "tier_values": stop}))
    elapsed = time.time() - started
    steps = {s["step"]: s for s in json.loads((work / "report.json").read_text())["steps"]}
    assert steps["report"]["status"] == "PASS", steps["report"]
    assert '"failed":2' in steps["report"]["lines"][-1] and '"backfills":2' in steps["report"]["lines"][-1]
    assert steps["delivery_set"]["status"] == "PASS" and len(steps["delivery_set"]["lines"]) == 3
    assert steps["delivery_set"]["elapsed_s"] < 5 and elapsed < 30
    pid = int(orphan.read_text())
    assert not alive(pid), "孙进程 sleep 成了孤儿"
    assert proc.returncode == 1 and last(proc.stdout, "V8_CONTINUE=").startswith("V8_CONTINUE=FAIL step=tier_values")


def test_端口占用探测():
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        assert CONT.port_busy("127.0.0.1", sock.getsockname()[1])
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        free = sock.getsockname()[1]
    assert not CONT.port_busy("127.0.0.1", free)


def test_zz_判定行(capsys):
    if len(CASES) < 6:
        pytest.skip(f"只跑了部分情形：{sorted(CASES)}")
    assert all(CASES.values()) and len(DETECTED) == 1
    with capsys.disabled():
        print(f"\nS2D_FIXTURES=PASS cases={len(CASES)} watchdog_detected={len(DETECTED)}", flush=True)
