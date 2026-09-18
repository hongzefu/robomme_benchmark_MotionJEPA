"""测试专用的固定 Git 基线；生产代码禁止导入，不保留旧生产入口。"""
from functools import lru_cache
from pathlib import Path
import subprocess
import sys
import types

ROOT = Path(__file__).resolve().parents[2]
REVISION = "e53173d"
PACKAGE = "_injection_frozen_baseline"


@lru_cache(None)
def load(name):
    if PACKAGE not in sys.modules:
        package = types.ModuleType(PACKAGE)
        package.__path__ = []
        sys.modules[PACKAGE] = package
    dependencies = {"categories": ["contract"], "specs": ["contract", "sampling"],
                    "delivery": ["contract", "sampling", "run"], "env_check": ["run"],
                    "campaign": ["categories", "contract", "delivery", "sampling", "specs"]}
    for dependency in dependencies.get(name, []):
        load(dependency)
    path = f"scripts/injection/{name}.py"
    source = subprocess.check_output(["git", "show", f"{REVISION}:{path}"], cwd=ROOT, text=True)
    if name == "env_check":
        source = source.replace("from scripts.injection.run import", "from .run import")
    module = types.ModuleType(f"{PACKAGE}.{name}")
    module.__file__ = str(ROOT / path)
    module.__package__ = PACKAGE
    sys.modules[module.__name__] = module
    setattr(sys.modules[PACKAGE], name, module)
    exec(compile(source, str(ROOT / path), "exec"), module.__dict__)
    return module


def legacy_path(relative):
    """历史轻量输入迁移后按冻结映射定位，不能因为原路径消失增加跳过。"""
    run = ROOT / "artifacts/injection/20260912-contract-v3-10"
    path = run / relative
    if path.exists():
        return path
    import json
    mapping = json.loads((run / "rollout/logs/migration/path_map.json").read_text())
    for entry in mapping["entries"]:
        if entry["source"] == str(relative):
            return run / entry["target"]
    raise FileNotFoundError(relative)
