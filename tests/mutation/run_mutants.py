"""植入（变异）执行器：读取全部 ``tests/**/mutants.json``，逐项植入语义错误，核对指定用例因之失败。

三类（详见同目录 README.md）：
- A 文本替换／数据改写：在 tmp 隔离副本里落盘改源码（每个 old 恰好命中 1 次），受保护的 ``src/robomme`` 与
  三个上游入口一律拒绝落盘（红线 R9）；
- B 进程内插件：``tests/unit/hard/mutants_plugin.py``（T4_MUTANT）或 ``plugins/mut_inproc.py``（MUT_INPROC），
  不落盘，在仓库本身运行（只读，``PYTHONDONTWRITEBYTECODE=1``、关 cacheprovider）；
- C 仅描述、无法机检：只报告，计入 not_executable，不计入 seeded。

每项先确认原版在同环境下 expect_fail 用例全过（基线），再植入重跑：至少一个 expect_fail 用例（参数化按前缀匹配实例）
在 setup／call 阶段失败、且异常类型不是导入／语法错误、所在文件无收集错误，才算抓到。

判定行：``TEST_MUTATION=PASS|FAIL seeded=<n> caught=<n> survived=<n> not_executable=<n> baseline_fail=<n>``；
通过条件 survived=0 且 baseline_fail=0（且 seeded>0）。逐项记录写 ``artifacts/maint-regress/mutation/last_run*.jsonl``。

用法：
  UV_PROJECT_ENVIRONMENT=<主检出>/.venv uv run --no-sync python tests/mutation/run_mutants.py [--jobs 4]
      [--only <块或块:编号>...] [--tag <批次名>] [--list]
  … run_mutants.py --merge     # 合并各批次 last_run.<tag>.jsonl，写 last_run.jsonl 并打印总判定行
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import hashlib
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tests.mutation.plugins import mut_inproc  # noqa: E402
from tests.mutation.recipes import RECIPES  # noqa: E402

OUT_DIR = REPO / "artifacts" / "maint-regress" / "mutation"
#: 隔离副本只复制这些（与各块作者自检时的副本口径一致）。
COPY_ITEMS = ("src", "scripts", "tests", "challenge_interface", "pyproject.toml")
#: 受保护：只许进程内植入，不得落盘（AGENTS.md P2／计划红线 R9）。
PROTECTED_PREFIX = "src/robomme/"
UPSTREAM_ENTRIES = {"scripts/dataset_replay.py", "scripts/evaluation.py", "scripts/run_example.py"}
#: 这些异常类型导致的失败不算抓到。
NOT_SEMANTIC = {"ImportError", "ModuleNotFoundError", "SyntaxError", "IndentationError"}
PYTEST_TIMEOUT = 280
T4_PLUGIN_DIR = "tests/unit/hard"


# ───────────────────────────── 读取与归一 ─────────────────────────────


def load_items() -> list[dict]:
    items = []
    for path in sorted((REPO / "tests").rglob("mutants.json")):
        rel = path.relative_to(REPO).as_posix()
        block = path.parent.relative_to(REPO / "tests").as_posix()
        data = json.loads(path.read_text(encoding="utf-8"))
        entries = data["mutants"] if isinstance(data, dict) else data
        for e in entries:
            items.append(normalize(rel, block, e))
    return items


def _is_protected(rel: str) -> bool:
    return rel.startswith(PROTECTED_PREFIX) or rel in UPSTREAM_ENTRIES


def normalize(source: str, block: str, e: dict) -> dict:
    mid = e.get("id")
    key = f"{block}:{mid}"
    expect = list(e.get("expect_fail", e.get("expected_failing")) or [])
    it = {"source": source, "block": block, "id": mid, "key": key, "target": e.get("target"), "expect_fail": expect,
          "category": "C", "reason": None, "recipe": None}
    if not expect:
        it["reason"] = "无 expect_fail 用例" + (f"（{e['decision']}）" if e.get("decision") else "")
        return it
    method = e.get("method") or e.get("inject") or ""
    if e.get("patch"):
        recipe = {"kind": "text", "patch": e["patch"]}
    elif key in RECIPES:
        recipe = RECIPES[key]
    elif "T4_MUTANT=" in method and "mutants_plugin" in method:
        name = re.search(r"T4_MUTANT=([A-Za-z0-9_]+)", method).group(1)
        recipe = {"kind": "plugin", "plugin": "mutants_plugin", "pythonpath": T4_PLUGIN_DIR, "env": {"T4_MUTANT": name}}
    elif key in mut_inproc.SUPPORTED:
        recipe = {"kind": "plugin", "plugin": "tests.mutation.plugins.mut_inproc", "pythonpath": None,
                  "env": {"MUT_INPROC": key}}
    else:
        it["reason"] = "只有文字描述，执行器无对应配方"
        return it
    if recipe["kind"] in ("text", "transform"):
        files = [p["file"] for p in recipe.get("patch", [])] + list(recipe.get("files", []))
        bad = [f for f in files if _is_protected(f)]
        if bad:
            it["reason"] = f"R9：受保护文件不得落盘改 {bad}"
            return it
        it["category"] = "A"
    else:
        it["category"] = "B"
    it["recipe"] = recipe
    return it


# ───────────────────────────── 运行 pytest ─────────────────────────────


def _venv() -> str:
    v = os.environ.get("UV_PROJECT_ENVIRONMENT")
    if v:
        return v
    if (REPO / ".venv").is_dir():
        return str(REPO / ".venv")
    raise SystemExit("缺 UV_PROJECT_ENVIRONMENT（worktree 里没有 .venv，须指向主检出 .venv）")


def run_pytest(root: Path, nodeids: list[str], plugins: list[str], extra_path: list[str], env_extra: dict,
               scratch: Path) -> dict:
    """在 root 下跑指定用例，返回结果记录插件写出的 JSON（另附 rc 与输出尾部）。"""
    fd, out_file = tempfile.mkstemp(suffix=".json", dir=scratch)
    os.close(fd)
    pp = [str(root / "src"), str(root)] + [str(root / p) for p in extra_path]
    env = dict(os.environ, UV_PROJECT_ENVIRONMENT=_venv(), PYTHONPATH=":".join(pp), PYTHONDONTWRITEBYTECODE="1",
               MUT_OUTCOME_FILE=out_file, **env_extra)
    for k in ("MUT_INPROC", "T4_MUTANT"):
        if k not in env_extra:
            env.pop(k, None)
    cmd = ["uv", "run", "--no-sync", "python", "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "no:warnings",
           "--tb=line", "-p", "tests.mutation.plugins.outcome_recorder"]
    for p in plugins:
        cmd += ["-p", p]
    t0 = time.monotonic()
    try:
        proc = subprocess.run(cmd + nodeids, cwd=root, env=env, capture_output=True, text=True, timeout=PYTEST_TIMEOUT)
        rc, tail = proc.returncode, (proc.stdout + proc.stderr)[-3000:]
    except subprocess.TimeoutExpired as exc:
        rc, tail = "timeout", str(exc.stdout or "")[-3000:]
    try:
        data = json.loads(Path(out_file).read_text(encoding="utf-8") or "{}")
    except (OSError, json.JSONDecodeError):
        data = {}
    Path(out_file).unlink(missing_ok=True)
    data.update(rc=rc, tail=tail, seconds=round(time.monotonic() - t0, 1))
    return data


def _final(rec: dict) -> tuple[str, str | None]:
    """把一个用例各阶段合成最终结局：(passed|failed|skipped, 失败阶段的异常类型)。"""
    ph = rec.get("phases", {})
    for when in ("setup", "call", "teardown"):
        p = ph.get(when)
        if p and p["outcome"] == "failed":
            return "failed", p.get("exc")
    if any(p["outcome"] == "skipped" for p in ph.values()):
        return "skipped", None
    if ph.get("call", {}).get("outcome") == "passed":
        return "passed", None
    return "unknown", None


def _matches(nodeid: str, want: str) -> bool:
    return nodeid == want or nodeid.startswith(want + "[")


def judge(data: dict, expect: list[str]) -> dict:
    """逐个 expect_fail 汇总：每个期望 → 实例结局列表。"""
    tests = data.get("tests", {})
    per = {}
    for want in expect:
        inst = [(nid, *_final(r)) for nid, r in tests.items() if _matches(nid, want)]
        per[want] = inst
    files = {w.split("::")[0] for w in expect}
    cerr = [c for c in data.get("collect_errors", []) if c["nodeid"].split("::")[0] in files or not c["nodeid"]]
    return {"per": per, "collect_errors": cerr}


def baseline_ok(j: dict) -> tuple[bool, list[str]]:
    bad = []
    if j["collect_errors"]:
        bad.append(f"收集错误 {[c['nodeid'] for c in j['collect_errors']]}")
    for want, inst in j["per"].items():
        if not inst:
            bad.append(f"{want} 未收集到")
        bad += [f"{nid} {out}" for nid, out, _ in inst if out != "passed"]
    return not bad, bad


def caught_by(j: dict) -> tuple[list[str], list[str]]:
    """返回 (语义失败的用例实例, 被排除的失败说明)。"""
    if j["collect_errors"]:
        return [], [f"收集错误 {[c['nodeid'] for c in j['collect_errors']]}"]
    hit, excluded = [], []
    for inst in j["per"].values():
        for nid, out, exc in inst:
            if out != "failed":
                continue
            if exc in NOT_SEMANTIC:
                excluded.append(f"{nid} {exc}")
            else:
                hit.append(nid)
    return hit, excluded


# ───────────────────────────── 隔离副本 ─────────────────────────────


def make_copy(dest: Path) -> Path:
    ign = shutil.ignore_patterns("__pycache__", ".pytest_cache")
    for name in COPY_ITEMS:
        src = REPO / name
        if src.is_dir():
            shutil.copytree(src, dest / name, ignore=ign, symlinks=True)
        elif src.exists():
            shutil.copy2(src, dest / name)
    env = dict(os.environ, UV_PROJECT_ENVIRONMENT=_venv(), PYTHONPATH=f"{dest}/src:{dest}", PYTHONDONTWRITEBYTECODE="1")
    out = subprocess.run(["uv", "run", "--no-sync", "python", "-c", "import robomme_hard, robomme; "
                          "print(robomme_hard.__file__); print(robomme.__file__)"],
                         cwd=dest, env=env, capture_output=True, text=True, check=True).stdout.split()
    if not all(p.startswith(f"{dest}/src/") for p in out):
        raise SystemExit(f"隔离副本导入指向不对：{out}")
    return dest


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def apply_a(root: Path, recipe: dict) -> dict[str, bytes]:
    """在副本里植入，返回 {相对路径: 原字节} 供还原；old 未恰好命中 1 次时抛 ValueError（不留半改状态）。"""
    backup: dict[str, bytes] = {}
    if recipe["kind"] == "text":
        new_text: dict[str, str] = {}
        for p in recipe["patch"]:
            f = p["file"]
            if f not in backup:
                backup[f] = (root / f).read_bytes()
                new_text[f] = backup[f].decode("utf-8")
            n = new_text[f].count(p["old"])
            if n != 1:
                raise ValueError(f"{f} 植入点命中 {n} 次：{p['old'][:80]!r}")
            new_text[f] = new_text[f].replace(p["old"], p["new"])
        for f, t in new_text.items():
            (root / f).write_text(t, encoding="utf-8")
    else:
        for f in recipe["files"]:
            backup[f] = (root / f).read_bytes()
        try:
            recipe["func"](root)
        except Exception:
            restore(root, backup)
            raise
    return backup


def restore(root: Path, backup: dict[str, bytes]) -> None:
    for f, b in backup.items():
        (root / f).write_bytes(b)


# ───────────────────────────── 主流程 ─────────────────────────────


def _plugins_for(recipe: dict | None) -> tuple[list[str], list[str]]:
    if recipe is None or recipe["kind"] != "plugin":
        return [], []
    return [recipe["plugin"]], [recipe["pythonpath"]] if recipe.get("pythonpath") else []


def _group_sig(it: dict) -> tuple:
    if it["category"] == "A":
        return ("A",)
    p, x = _plugins_for(it["recipe"])
    return ("B", tuple(p), tuple(x))


def run_baselines(items: list[dict], copy0: Path, scratch: Path, log) -> None:
    """按运行环境分组跑一次并集基线；并集里有用例不过时，对涉及条目逐项单跑复核（排除用例间互扰）。"""
    groups: dict[tuple, list[dict]] = {}
    for it in items:
        groups.setdefault(_group_sig(it), []).append(it)

    def one(sig, its):
        root = copy0 if sig[0] == "A" else REPO
        plugins, extra = (list(sig[1]), list(sig[2])) if sig[0] == "B" else ([], [])
        union = sorted({n for it in its for n in it["expect_fail"]})
        data = run_pytest(root, union, plugins, extra, {}, scratch)
        log(f"基线 组={sig[0]}{'/' + ','.join(sig[1]) if sig[0] == 'B' else ''} 用例={len(union)} "
            f"rc={data['rc']} 用时={data['seconds']}s")
        for it in its:
            ok, bad = baseline_ok(judge(data, it["expect_fail"]))
            if not ok:  # 单跑复核
                single = run_pytest(root, it["expect_fail"], plugins, extra, {}, scratch)
                ok, bad = baseline_ok(judge(single, it["expect_fail"]))
                if not ok:
                    it["baseline_tail"] = single["tail"][-1500:]
            it["baseline"] = "pass" if ok else "fail"
            it["baseline_problems"] = bad

    # A 组用 copy0，B 组在仓库本身；彼此独立可并发
    with cf.ThreadPoolExecutor(max_workers=max(1, len(groups))) as ex:
        list(ex.map(lambda kv: one(*kv), groups.items()))


def run_one(it: dict, copies: "queue.Queue[Path]", scratch: Path, log) -> None:
    recipe = it["recipe"]
    if it["category"] == "A":
        root = copies.get()
        try:
            before = {f: _sha(root / f) for f in _files_of(recipe)}
            try:
                backup = apply_a(root, recipe)
            except ValueError as exc:
                it.update(mutant="not_applied", caught=False, reason=str(exc))
                log(f"{it['key']} 植入点不唯一：{exc}")
                return
            try:
                data = run_pytest(root, it["expect_fail"], [], [], {}, scratch)
            finally:
                restore(root, backup)
            after = {f: _sha(root / f) for f in before}
            assert after == before, f"{it['key']} 副本还原失败"
        finally:
            copies.put(root)
    else:
        plugins, extra = _plugins_for(recipe)
        data = run_pytest(REPO, it["expect_fail"], plugins, extra, dict(recipe["env"]), scratch)
    j = judge(data, it["expect_fail"])
    hit, excluded = caught_by(j)
    it.update(mutant="applied", caught=bool(hit), failed_tests=hit, excluded_failures=excluded,
              mutant_rc=data["rc"], mutant_seconds=data["seconds"],
              mutant_outcomes={w: [[n, o, e] for n, o, e in inst] for w, inst in j["per"].items()})
    if not hit:
        it["mutant_tail"] = data["tail"][-1500:]
    log(f"{it['key']} {'CAUGHT' if hit else 'SURVIVED'} 失败={len(hit)} 用时={data['seconds']}s rc={data['rc']}")


def _files_of(recipe: dict) -> list[str]:
    return sorted({p["file"] for p in recipe.get("patch", [])} | set(recipe.get("files", [])))


def summarize(rows: list[dict]) -> str:
    seeded = [r for r in rows if r["category"] in ("A", "B") and r.get("baseline") == "pass"
              and r.get("mutant") == "applied"]
    caught = sum(1 for r in seeded if r["caught"])
    survived = len(seeded) - caught
    not_exec = sum(1 for r in rows if r["category"] == "C" or r.get("mutant") == "not_applied")
    base_fail = sum(1 for r in rows if r["category"] in ("A", "B") and r.get("baseline") == "fail")
    ok = survived == 0 and base_fail == 0 and len(seeded) > 0
    return (f"TEST_MUTATION={'PASS' if ok else 'FAIL'} seeded={len(seeded)} caught={caught} survived={survived} "
            f"not_executable={not_exec} baseline_fail={base_fail}")


def _row_for_file(it: dict) -> dict:
    r = {k: v for k, v in it.items() if k != "recipe"}
    rc = it.get("recipe")
    if rc is not None:
        r["recipe"] = ({"kind": "transform", "func": rc["func"].__name__, "files": rc["files"]}
                       if rc["kind"] == "transform" else rc)
    return r


def table(rows: list[dict]) -> str:
    by: dict[str, dict] = {}
    for r in rows:
        b = by.setdefault(r["block"], {"seeded": 0, "caught": 0, "survived": 0, "not_executable": 0, "baseline_fail": 0})
        if r["category"] == "C" or r.get("mutant") == "not_applied":
            b["not_executable"] += 1
        elif r.get("baseline") == "fail":
            b["baseline_fail"] += 1
        elif r.get("mutant") == "applied":
            b["seeded"] += 1
            b["caught" if r["caught"] else "survived"] += 1
    lines = ["块 | seeded | caught | survived | not_executable | baseline_fail"]
    for k in sorted(by):
        v = by[k]
        lines.append(f"{k} | {v['seeded']} | {v['caught']} | {v['survived']} | {v['not_executable']} | {v['baseline_fail']}")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--only", nargs="*", default=None,
                    help="只跑这些块（可写前缀，如 pipeline/ 或 unit/）或键（如 pipeline/site:M20a）")
    ap.add_argument("--jobs", type=int, default=4, help="并发 pytest 进程数（A 类每个并发一份隔离副本）")
    ap.add_argument("--tag", default=None, help="批次名；给出时写 last_run.<tag>.jsonl，否则写 last_run.jsonl")
    ap.add_argument("--list", action="store_true", help="只打印归一结果，不运行")
    ap.add_argument("--merge", action="store_true", help="合并 last_run.*.jsonl 为 last_run.jsonl 并打印总判定行")
    args = ap.parse_args(argv)

    if args.merge:
        rows = []
        for p in sorted(OUT_DIR.glob("last_run.*.jsonl")):
            rows += [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
        keys = [r["key"] for r in rows]
        dup = sorted({k for k in keys if keys.count(k) > 1})
        if dup:
            raise SystemExit(f"批次之间条目重复：{dup}")
        total = {it["key"] for it in load_items()}
        missing = sorted(total - set(keys))
        (OUT_DIR / "last_run.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                                                encoding="utf-8")
        print(table(rows))
        if missing:
            print(f"批次未覆盖的条目：{missing}")
            print(summarize(rows).replace("TEST_MUTATION=PASS", "TEST_MUTATION=FAIL") + f" uncovered={len(missing)}")
            return 1
        line = summarize(rows)
        print(line)
        return 0 if "=PASS" in line else 1

    items = load_items()
    keys = [it["key"] for it in items]
    dup = sorted({k for k in keys if keys.count(k) > 1})
    if dup:
        raise SystemExit(f"同一块内编号重复：{dup}")
    if args.only:
        # 块名可写前缀（如 pipeline/ 选全部流水线块）
        items = [it for it in items if it["key"] in args.only or any(it["block"].startswith(o) for o in args.only)]
    if args.list:
        for it in items:
            print(f"{it['category']} {it['key']} {it['reason'] or (it['recipe'] or {}).get('kind')}")
        return 0

    t_start = time.monotonic()
    log = lambda s: print(f"[{time.monotonic() - t_start:6.1f}s] {s}", flush=True)  # noqa: E731
    runnable = [it for it in items if it["category"] in ("A", "B")]
    work = Path(tempfile.mkdtemp(prefix="t14-mutation-"))
    scratch = work / "outcomes"
    scratch.mkdir()
    git_before = _git_status()
    try:
        n_copies = max(1, min(args.jobs, sum(1 for it in runnable if it["category"] == "A") or 1))
        copies: "queue.Queue[Path]" = queue.Queue()
        with cf.ThreadPoolExecutor(max_workers=n_copies) as ex:
            for c in ex.map(lambda i: make_copy(work / f"copy{i}"), range(n_copies)):
                copies.put(c)
        copy0 = copies.queue[0]
        log(f"隔离副本 {n_copies} 份就绪（{work}），可执行 {len(runnable)} 项、仅描述 {len(items) - len(runnable)} 项")
        run_baselines(runnable, copy0, scratch, log)
        todo = [it for it in runnable if it["baseline"] == "pass"]
        for it in runnable:
            if it["baseline"] != "pass":
                log(f"{it['key']} 基线未过：{it['baseline_problems'][:3]}")
        with cf.ThreadPoolExecutor(max_workers=args.jobs) as ex:
            list(ex.map(lambda it: run_one(it, copies, scratch, log), todo))
    finally:
        shutil.rmtree(work, ignore_errors=True)
    git_after = _git_status()
    if git_after != git_before:
        print(f"警告：运行前后仓库 git status 不同\n前：{git_before}\n后：{git_after}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    name = f"last_run.{args.tag}.jsonl" if args.tag else "last_run.jsonl"
    (OUT_DIR / name).write_text("".join(json.dumps(_row_for_file(it), ensure_ascii=False) + "\n" for it in items),
                                encoding="utf-8")
    print(table(items))
    for it in items:
        if it["category"] == "C" or it.get("mutant") == "not_applied":
            print(f"NOT_EXECUTABLE {it['key']}：{it.get('reason')}")
        elif it.get("baseline") == "fail":
            print(f"BASELINE_FAIL {it['key']}：{it['baseline_problems'][:3]}")
        elif not it.get("caught"):
            print(f"SURVIVED {it['key']}：{it.get('excluded_failures')}")
    line = summarize(items)
    print(f"记录：{OUT_DIR / name}")
    print(line)
    return 0 if "=PASS" in line else 1


def _git_status() -> str:
    try:
        return subprocess.run(["git", "status", "--porcelain", "--ignore-submodules=dirty"], cwd=REPO,
                              capture_output=True, text=True).stdout
    except OSError:
        return ""


if __name__ == "__main__":
    sys.exit(main())
