"""重构收尾只读核验：导入闭包、Git 边界、活动文档链接及正式候选角色。"""
import importlib
import pkgutil
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
import scripts.injection as package
from scripts.injection.candidates.io import load_candidates
from scripts.injection.rollout.state import ROOT, RunStore, run_root


def main():
    modules = []
    for item in pkgutil.walk_packages(package.__path__, package.__name__ + "."):
        importlib.import_module(item.name)
        modules.append(item.name)
    print(f"IMPORT_CLOSURE=PASS modules={len(modules)} missing_old_imports=0")
    prefix = "artifacts/injection/ignore-rule-probe"
    visible = ["candidates/candidates.jsonl", "candidates/logs/a.log", "rollout/results.jsonl",
               "rollout/logs/smoke/s/logs/a.log", "rollout/logs/smoke/s/candidates.jsonl",
               "rollout/figures/windows_overview.png"]
    expected = {f"{prefix}/{path}": False for path in visible}
    for suffix in ("h5", "mp4", "png", "jpg", "svg"):
        for part in ("rollout/T/easy", "rollout/logs/smoke/s/T/easy", "rollout/logs/parity/x", "candidates/figures/T/easy"):
            expected[f"{prefix}/{part}/file.{suffix}"] = True
    for path, ignored in expected.items():
        actual = subprocess.run(["git", "check-ignore", "-q", "--no-index", path], cwd=ROOT).returncode == 0
        assert actual == ignored, (path, actual, ignored)
    print(f"IGNORE_RULES=PASS checked={len(expected)} candidates_visible=1 logs_visible=1 media_ignored=1")
    for path in ("src/robomme", "scripts/hf_release.py"):
        subprocess.run(["git", "diff", "--exit-code", "2bcd9cc", "--", path], cwd=ROOT, check=True)
    print("FROZEN_SOURCE=PASS src_unchanged=1 hf_release_unchanged=1")
    tracked = set(subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True).splitlines())
    inputs = list((ROOT / "artifacts/injection").glob("*/candidates/candidates.jsonl"))
    inputs += list((ROOT / "artifacts/injection").glob("*/rollout/logs/smoke/*/candidates.jsonl"))
    code = [ROOT / "scripts/injection/candidates/io.py", ROOT / "scripts/generate_dataset_newseed.py",
            ROOT / "scripts/injection/rollout/run.py", ROOT / "scripts/injection/rollout/reset_check.py"]
    assert inputs
    for path in inputs + code:
        assert str(path.relative_to(ROOT)) in tracked, f"唯一入口未跟踪：{path}"
    heavy = [path for path in tracked if path.startswith("artifacts/injection/")
             and Path(path).suffix.lower() in {".h5", ".hdf5", ".mp4", ".png", ".jpg", ".svg"}
             and not re.fullmatch(r"artifacts/injection/[^/]+/rollout/figures/windows_overview\.png", path)]
    assert not heavy, heavy
    print(f"GIT_INPUTS=PASS snapshots={len(inputs)} consumer_files={len(code)} heavy_tracked=0")
    root = run_root("20260912-contract-v3-10")
    store = RunStore(root)
    audit = store.audit()
    header, rows = load_candidates(store.candidates)
    expected_roles = {"train/primary": 1600, "train/spare": 196, "train/failed": 46,
                      "test/primary": 700, "test/spare": 858}
    assert header["roles"] == expected_roles and len(rows) == 3400
    assert audit["results"] == 3400 and audit["pending"] == audit["unused"] == 0
    print("ROLES_CONSISTENT=PASS rows=3400 primary_h5=1600 primary_reset=700 pending=0 unused=0")
    documents = [ROOT / "scripts/INJECTION.md", root / "candidates/DISTRIBUTION.md", root / "rollout/WINDOWS.md"]
    checked = 0
    for document in documents:
        for target in re.findall(r"!?\[[^\]]*\]\(([^)]+)\)", document.read_text()):
            if "://" in target or target.startswith("#"):
                continue
            path = (document.parent / target.split("#")[0]).resolve()
            assert path.exists(), (document, target)
            checked += 1
    print(f"DOC_LINKS=PASS checked={checked} missing=0")


if __name__ == "__main__":
    main()
