"""G1 守卫：`src/robomme/**` 与官方 `src_commit` 逐字节相同，`robomme_hard` 的借用与导入落点正确。

子命令：
- ``build``：从 git 对象生成 ``src/robomme_hard/UPSTREAM.json``（双锚点、官方逐文件 sha256、shim 清单、vendor 清单、自校验哈希）。
- ``check``（默认）：输出判定行
  ``UPSTREAM_BYTES`` / ``ENTRY_SCRIPTS`` / ``VENDOR_SAME`` / ``SHIMS`` / ``ABS_IMPORT`` / ``BORROWED_DEPS``，
  末行 ``UPSTREAM_GUARD=PASS|FAIL``。
  ``UPSTREAM_BYTES`` 默认严格：``src/robomme`` 与官方 ``src_commit`` 有任何字节差即 FAIL。逃生阀 ``--allow-pending``
  把它降为 ``UPSTREAM_BYTES=PENDING``、不计作失败，并向 stderr 打醒目警告（只供临时排障，不得用于验收）。
  ``--require-upstream`` 保留为兼容旁路（现即默认行为，加不加结果相同），与 ``--allow-pending`` 互斥。
  ``ENTRY_SCRIPTS``：三个上游入口 ``scripts/{dataset_replay,evaluation,run_example}.py`` 与
  ``git show <src_commit>:scripts/<名>.py`` 逐字节相同，任一不同或缺失即 FAIL（不受 ``--allow-pending`` 影响）。
- ``manifest-md``：输出 README ③ 复制／借用／子类／新增逐文件表。

纯 CPU、秒级；只读 git 对象与工作区文件，不导入 robomme。
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HARD = REPO / "src" / "robomme_hard"
MANIFEST = HARD / "UPSTREAM.json"
VENDOR_DIR = REPO / "scripts" / "parity" / "official" / "scripts" / "data-generation"

SRC_COMMIT = "1fadc0ec50316b60ddcfd8e82ac62ef2b70c18f9"
SRC_TREE = "3006988fed0a708e7dcba906fb663f2475dc8d34"
ORCH_COMMIT = "d53f21a7947d2d8daf6e3e8bad9f59b4f89a77fa"
ORCH_TREE = "1d4c13697f0c5fbd7a8b05e01c196c984a07406c"
UPSTREAM_URL = "https://github.com/RoboMME/robomme_benchmark"
#: 与上游逐字节相同、不得改动的三个顶层入口（AGENTS.md P1）
ENTRY_SCRIPTS = ("dataset_replay.py", "evaluation.py", "run_example.py")
VENDOR_FILES = (
    "generate_dataset.py",
    "validate_generated_dataset_contract.py",
    "write_generation_report.py",
    "compare_joint_actions.py",
)

# 借用清单（阶段 0 导入扫描定稿：官方模块传递闭包不含任何被 robomme_hard 复制的模块）
SHIM_MODULES = (
    "robomme.logging_utils",
    "robomme.robomme_env.utils.adjacent",
    "robomme.robomme_env.utils.choice_action_mapping",
    "robomme.robomme_env.utils.constant",
    "robomme.robomme_env.utils.obschange",
    "robomme.robomme_env.utils.oracle_action_matcher",
    "robomme.robomme_env.utils.planner_denseStep",
    "robomme.robomme_env.utils.planner_fail_safe",
    "robomme.robomme_env.utils.reset_panda",
    "robomme.robomme_env.utils.rpy_util",
    "robomme.robomme_env.utils.save_reset_video",
    "robomme.robomme_env.utils.SceneGenerationError",
    "robomme.robomme_env.utils.statechange",
    "robomme.robomme_env.utils.generate_sample_action",
    "robomme.env_record_wrapper.EndeffectorDemonstrationWrapper",
    "robomme.env_record_wrapper.FailAwareWrapper",
    "robomme.env_record_wrapper.MultiStepDemonstrationWrapper",
    "robomme.env_record_wrapper.episode_dataset_resolver",
)
# 子类化的官方父类模块：robomme_hard 允许绝对导入它（hard_builder 继承官方 BenchmarkEnvBuilder）
PARENT_MODULES = ("robomme.env_record_wrapper.episode_config_resolver",)


def _git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(REPO), *args], check=True, capture_output=True, text=True).stdout


def _git_bytes(*args: str) -> bytes:
    return subprocess.run(["git", "-C", str(REPO), *args], check=True, capture_output=True).stdout


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def cheap_hash(data: bytes) -> str:
    """cheap 档：首尾各 1 MiB 的 blake2b（与 robomme_hard/__init__.py 的导入时校验同算法；挡不住等长改中间字节）。"""
    return hashlib.blake2b(data[: 1 << 20] + data[-(1 << 20):]).hexdigest()


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def official_files() -> dict[str, str]:
    """官方 src/robomme 逐文件 sha256（路径相对仓库根）。"""
    out = {}
    for line in _git("ls-tree", "-r", SRC_COMMIT, "--", "src/robomme").splitlines():
        meta, path = line.split("\t", 1)
        blob = meta.split()[2]
        out[path] = sha256_bytes(_git_bytes("cat-file", "blob", blob))
    return out


def module_to_path(mod: str, files) -> str:
    base = "src/" + mod.replace(".", "/")
    if base + ".py" in files:
        return base + ".py"
    if base + "/__init__.py" in files:
        return base + "/__init__.py"
    raise KeyError(mod)


def shim_path(mod: str) -> str:
    rel = mod.split(".", 1)[1].replace(".", "/") + ".py"
    return f"src/robomme_hard/{rel}"


def build() -> None:
    files = official_files()
    shims = []
    for mod in SHIM_MODULES:
        target = module_to_path(mod, files)
        blob = _git_bytes("show", f"{SRC_COMMIT}:{target}")
        shims.append({"shim": shim_path(mod), "target_module": mod, "target_file": target,
                      "target_sha256": files[target], "target_bytes": len(blob), "target_cheap": cheap_hash(blob)})
    vendor = {}
    for name in VENDOR_FILES:
        data = _git_bytes("show", f"{ORCH_COMMIT}:scripts/data-generation/{name}")
        vendor[f"scripts/parity/official/scripts/data-generation/{name}"] = sha256_bytes(data)
    manifest = {
        "schema": "robomme-hard-upstream/1",
        "upstream_url": UPSTREAM_URL,
        "src_commit": SRC_COMMIT,
        "src_tree": SRC_TREE,
        "orchestration_commit": ORCH_COMMIT,
        "orchestration_tree": ORCH_TREE,
        "robomme_files": files,
        "shims": shims,
        "parents": list(PARENT_MODULES),
        "vendor": vendor,
    }
    manifest["manifest_sha256"] = sha256_bytes(canonical(manifest).encode())
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, indent=1, ensure_ascii=False, sort_keys=True) + "\n")
    print(f"UPSTREAM_MANIFEST=WRITTEN files={len(files)} shims={len(shims)} vendor={len(vendor)} "
          f"manifest_sha256={manifest['manifest_sha256'][:12]}")


def load_manifest() -> dict:
    manifest = json.loads(MANIFEST.read_text())
    claimed = manifest.pop("manifest_sha256")
    actual = sha256_bytes(canonical(manifest).encode())
    if claimed != actual:
        raise SystemExit(f"UPSTREAM_GUARD=FAIL reason=manifest_tampered claimed={claimed[:12]} actual={actual[:12]}")
    for key in ("src_commit", "orchestration_commit"):
        if len(manifest[key]) != 40:
            raise SystemExit(f"UPSTREAM_GUARD=FAIL reason={key}_not_40_hex")
    return manifest


# ── 导入解析 ─────────────────────────────────────────────────────────────


def _modname(rel: str) -> str:
    parts = rel[len("src/"):-3].split("/")
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _resolve(cur: str, is_pkg: bool, level: int, module: str | None) -> str:
    if level == 0:
        return module or ""
    base = cur.split(".") if is_pkg else cur.split(".")[:-1]
    if level > 1:
        base = base[: len(base) - (level - 1)]
    return ".".join(base + ([module] if module else []))


def iter_imports(mod: str, source: str, is_pkg: bool, known: set[str]):
    """产出 (lineno, 解析后的目标模块, 是否相对导入)。from X import y 且 X.y 是模块时取 X.y。"""
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node.lineno, alias.name, False
        elif isinstance(node, ast.ImportFrom):
            target = _resolve(mod, is_pkg, node.level, node.module)
            for alias in node.names:
                sub = f"{target}.{alias.name}"
                yield node.lineno, (sub if sub in known else target), node.level > 0


def official_sources(manifest: dict) -> dict[str, tuple[str, bool]]:
    """官方模块名 → (源码, 是否包)；从 git 对象读，不依赖工作区状态。"""
    out = {}
    for rel in manifest["robomme_files"]:
        if not rel.endswith(".py"):
            continue
        name = rel.rsplit("/", 1)[-1]
        if " " in name or "-" in name:
            continue
        out[_modname(rel)] = (_git("show", f"{manifest['src_commit']}:{rel}"), rel.endswith("__init__.py"))
    return out


def hard_files() -> list[Path]:
    return sorted(p for p in HARD.rglob("*.py") if "__pycache__" not in p.parts)


def shim_set(manifest: dict) -> set[str]:
    return {s["shim"] for s in manifest["shims"]}


# ── 各道检查 ─────────────────────────────────────────────────────────────


def check_upstream_bytes(manifest: dict, allow_pending: bool = False) -> bool:
    """``src/robomme`` 逐文件 sha256 对官方清单。默认严格：任何差异即 FAIL；``allow_pending`` 时记 PENDING 放行并警告。"""
    want = manifest["robomme_files"]
    have = {}
    for p in (REPO / "src" / "robomme").rglob("*"):
        if p.is_file() and "__pycache__" not in p.parts and not p.name.endswith(".pyc"):
            have[str(p.relative_to(REPO))] = sha256_bytes(p.read_bytes())
    missing = sorted(set(want) - set(have))
    extra = sorted(set(have) - set(want))
    changed = sorted(k for k in set(want) & set(have) if want[k] != have[k])
    diff = len(missing) + len(extra) + len(changed)
    if diff == 0:
        print(f"UPSTREAM_BYTES=PASS src_commit={manifest['src_commit'][:8]} files={len(want)} diff=0 "
              f"shims={len(manifest['shims'])}")
        return True
    status = "PENDING" if allow_pending else "FAIL"
    if allow_pending:
        bar = "!" * 72
        print(f"{bar}\n!! 警告：--allow-pending 已开启，src/robomme 与官方 {manifest['src_commit'][:8]} 存在 {diff} 处"
              f"字节差异，本次按 PENDING 放行。\n!! 这只是临时排障逃生阀，结果不得作为验收证据。\n{bar}",
              file=sys.stderr, flush=True)
    print(f"UPSTREAM_BYTES={status} src_commit={manifest['src_commit'][:8]} files={len(want)} diff={diff} "
          f"changed={len(changed)} extra={len(extra)} missing={len(missing)}"
          + ("" if allow_pending else f" detail={(changed + extra + missing)[:10]}"), flush=True)
    return allow_pending


def check_entry_scripts(manifest: dict) -> bool:
    """三个上游入口与 ``git show <src_commit>:scripts/<名>`` 逐字节相同（缺文件或上游无此文件都算不同）。"""
    bad = []
    for name in ENTRY_SCRIPTS:
        path = REPO / "scripts" / name
        try:
            want = _git_bytes("show", f"{manifest['src_commit']}:scripts/{name}")
        except subprocess.CalledProcessError:
            bad.append(f"{name}:upstream_missing")
            continue
        if not path.is_file():
            bad.append(f"{name}:missing")
        elif path.read_bytes() != want:
            bad.append(f"{name}:changed")
    ok = not bad
    print(f"ENTRY_SCRIPTS={'PASS' if ok else 'FAIL'} src_commit={manifest['src_commit'][:8]} "
          f"files={len(ENTRY_SCRIPTS)} diff={len(bad)}" + (f" bad={bad}" if bad else ""))
    return ok


def check_vendor(manifest: dict) -> bool:
    bad = [rel for rel, sha in manifest["vendor"].items()
           if not (REPO / rel).is_file() or sha256_bytes((REPO / rel).read_bytes()) != sha]
    ok = not bad
    print(f"VENDOR_SAME={'PASS' if ok else 'FAIL'} files={len(manifest['vendor'])} "
          f"orchestration_commit={manifest['orchestration_commit'][:8]}" + (f" bad={bad}" if bad else ""))
    return ok


SHIM_IMPORT_LINE = "import importlib, sys"


def check_shims(manifest: dict) -> bool:
    bad = []
    for entry in manifest["shims"]:
        path = REPO / entry["shim"]
        if not path.is_file():
            bad.append(f"{entry['shim']}:missing")
            continue
        lines = [ln for ln in path.read_text().splitlines() if ln.strip() and not ln.strip().startswith("#")]
        expected = f'sys.modules[__name__] = importlib.import_module("{entry["target_module"]}")'
        # shim 非注释部分必须恰好是这两行；多一行任何代码都判 FAIL（原判据「> 3 行」会放过多 1 行）。
        if lines != [SHIM_IMPORT_LINE, expected]:
            bad.append(f"{entry['shim']}:body")
    ok = not bad
    print(f"SHIMS={'PASS' if ok else 'FAIL'} shims={len(manifest['shims'])}" + (f" bad={bad}" if bad else ""))
    return ok


def check_abs_import(manifest: dict) -> bool:
    """robomme_hard 自有文件：相对导入必须落在包内已有模块；绝对 robomme.* 只许指向 shim 目标或父类模块。"""
    shims = shim_set(manifest)
    allowed_abs = {s["target_module"] for s in manifest["shims"]} | set(manifest.get("parents", ()))
    own = [p for p in hard_files() if str(p.relative_to(REPO)) not in shims]
    known = {_modname(str(p.relative_to(REPO))) for p in hard_files()}
    known_official = {_modname(r) for r in manifest["robomme_files"] if r.endswith(".py")}
    unresolved, retargeted, kept = [], 0, 0
    for path in own:
        rel = str(path.relative_to(REPO))
        mod = _modname(rel)
        for lineno, target, relative in iter_imports(mod, path.read_text(), path.name == "__init__.py",
                                                     known | known_official):
            if relative:
                if target not in known:
                    unresolved.append(f"{rel}:{lineno}:{target}")
            elif target == "robomme_hard" or target.startswith("robomme_hard."):
                retargeted += 1
                if target not in known:
                    unresolved.append(f"{rel}:{lineno}:{target}")
            elif target == "robomme" or target.startswith("robomme."):
                if target in allowed_abs:
                    kept += 1
                else:
                    unresolved.append(f"{rel}:{lineno}:{target}")
    ok = not unresolved
    print(f"ABS_IMPORT={'PASS' if ok else 'FAIL'} files={len(own)} retargeted={retargeted} kept={kept} "
          f"unresolved={len(unresolved)}" + (f" detail={unresolved[:10]}" if unresolved else ""))
    return ok


def check_borrowed_deps(manifest: dict) -> bool:
    """shim 目标的传递闭包（在官方源码上求）不得含任何被 robomme_hard 复制的模块。"""
    sources = official_sources(manifest)
    known = set(sources)
    edges = {}
    for mod, (src, is_pkg) in sources.items():
        edges[mod] = {t for _, t, _ in iter_imports(mod, src, is_pkg, known) if t in known}
    shims = shim_set(manifest)
    copied = set()
    for p in hard_files():
        rel = str(p.relative_to(REPO))
        if rel in shims:
            continue
        official_mod = "robomme" + _modname(rel)[len("robomme_hard"):]
        if official_mod in known:
            copied.add(official_mod)
    hits = []
    for entry in manifest["shims"]:
        seen, stack = set(), [entry["target_module"]]
        while stack:
            for dep in edges.get(stack.pop(), ()):
                if dep not in seen:
                    seen.add(dep)
                    stack.append(dep)
        bad = sorted(seen & copied)
        if bad:
            hits.append(f"{entry['target_module']}->{bad}")
    ok = not hits
    print(f"BORROWED_DEPS={'PASS' if ok else 'FAIL'} shims={len(manifest['shims'])} copied={len(copied)} "
          f"changed_hits={len(hits)}" + (f" detail={hits}" if hits else ""))
    return ok


def check_net(manifest: dict) -> None:
    try:
        subprocess.run(["git", "-C", str(REPO), "fetch", "--quiet", manifest["upstream_url"], manifest["src_commit"]],
                       check=True, capture_output=True, timeout=60)
        tree = _git("rev-parse", f"{manifest['src_commit']}^{{tree}}").strip()
        print(f"UPSTREAM_NET={'PASS' if tree == manifest['src_tree'] else 'FAIL'} net=ok tree={tree[:8]}")
    except Exception as exc:  # noqa: BLE001 网络不可达只记 skipped
        print(f"UPSTREAM_NET=INFO net=skipped reason={type(exc).__name__}")


def manifest_md(manifest: dict) -> None:
    shims = {s["shim"]: s["target_module"] for s in manifest["shims"]}
    official = set(manifest["robomme_files"])
    print("| 文件 | 做法 | 官方对应 |")
    print("|---|---|---|")
    for p in hard_files():
        rel = str(p.relative_to(REPO))
        twin = "src/robomme/" + rel[len("src/robomme_hard/"):]
        if rel in shims:
            kind, ref = "借用 shim", shims[rel]
        elif rel.endswith("hard_builder.py"):
            kind, ref = "子类", "robomme.env_record_wrapper.episode_config_resolver.BenchmarkEnvBuilder"
        elif twin in official:
            kind, ref = "复制", twin
        else:
            kind, ref = "新增", "—"
        print(f"| `{rel}` | {kind} | `{ref}` |")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", nargs="?", default="check", choices=("check", "build", "manifest-md"))
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--require-upstream", action="store_true",
                      help="兼容旁路：UPSTREAM_BYTES 不等时按 FAIL 计（现为默认行为，加不加结果相同）")
    mode.add_argument("--allow-pending", action="store_true",
                      help="逃生阀：UPSTREAM_BYTES 不等时记 PENDING 放行并打醒目警告；只供临时排障，不得用于验收")
    parser.add_argument("--net", action="store_true", help="网络可达时 git fetch 官方锚点复核 tree")
    args = parser.parse_args()
    if args.command == "build":
        build()
        return 0
    manifest = load_manifest()
    manifest["manifest_sha256"] = "verified"
    if args.command == "manifest-md":
        manifest_md(manifest)
        return 0
    results = [
        check_upstream_bytes(manifest, allow_pending=args.allow_pending),
        check_entry_scripts(manifest),
        check_vendor(manifest),
        check_shims(manifest),
        check_abs_import(manifest),
        check_borrowed_deps(manifest),
    ]
    if args.net:
        check_net(manifest)
    ok = all(results)
    print(f"UPSTREAM_GUARD={'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
