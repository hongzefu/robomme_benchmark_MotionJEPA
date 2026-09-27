"""只读探针：导出 16 环境的 configs 与 decision 默认值（不建环境、不抽随机数）。"""
import importlib, json, sys
sys.path.insert(0, "src")
TASKS = ["PickXtimes","StopCube","SwingXtimes","BinFill","VideoUnmaskSwap","VideoUnmask","ButtonUnmaskSwap","ButtonUnmask","VideoRepick","VideoPlaceButton","VideoPlaceOrder","PickHighlight","InsertPeg","MoveCube","PatternLock","RouteStick"]
out = {}
def ser(o):
    try: json.dumps(o); return o
    except TypeError:
        if isinstance(o, dict): return {str(k): ser(v) for k, v in o.items()}
        if isinstance(o, (list, tuple)): return [ser(x) for x in o]
        return repr(o)
for t in TASKS:
    m = importlib.import_module(f"robomme.robomme_env.{t}")
    cls = getattr(m, t)
    rec = {"configs": ser(getattr(cls, "configs", None))}
    for name in ("_native_decision",):
        fn = getattr(m, name, None) or getattr(cls, name, None)
        if fn:
            try: rec["decision_default"] = ser(fn(cls))
            except TypeError:
                try: rec["decision_default"] = ser(fn())
                except Exception as e: rec["decision_default"] = f"ERR {e}"
    out[t] = rec
json.dump(out, open(sys.argv[1], "w"), indent=1, ensure_ascii=False)
print("ok")
