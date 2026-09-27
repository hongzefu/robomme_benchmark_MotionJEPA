# 抽查：各环境模块全局名 SceneGenerationError 是类还是被 from .utils import * 遮蔽成子模块
import importlib, inspect
envs = ["VideoRepick", "VideoPlaceOrder", "VideoUnmaskSwap", "ButtonUnmaskSwap", "VideoUnmask", "ButtonUnmask",
        "InsertPeg", "MoveCube", "BinFill", "PickXtimes", "SwingXtimes", "PatternLock", "RouteStick",
        "PickHighlight", "StopCube", "VideoPlaceButton"]
for e in envs:
    m = importlib.import_module(f"robomme.robomme_env.{e}")
    obj = getattr(m, "SceneGenerationError", None)
    kind = "class" if inspect.isclass(obj) else ("module" if inspect.ismodule(obj) else type(obj).__name__)
    extra = [n for n in dir(m) if "SceneGenerationError" in n and n != "SceneGenerationError"]
    print(f"{e:18s} SceneGenerationError -> {kind}  aliases={extra}")
