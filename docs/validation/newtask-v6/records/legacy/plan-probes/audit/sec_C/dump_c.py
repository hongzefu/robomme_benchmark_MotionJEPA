"""只读审计：重新导出 16 环境的 config_easy/medium/hard/xhard、XHARD_DECISION、_native_decision，
以及 scripts/configs/newtask-v5/sampling_config.json 对应任务条目。不建环境、不抽随机数。"""
import importlib, json, sys
sys.path.insert(0, "src")
TASKS = ["BinFill","PickXtimes","SwingXtimes","PickHighlight","VideoUnmask","ButtonUnmask","VideoUnmaskSwap","ButtonUnmaskSwap","VideoRepick","PatternLock","RouteStick","VideoPlaceButton","VideoPlaceOrder","MoveCube","InsertPeg","StopCube"]
def ser(o):
    try: json.dumps(o); return o
    except TypeError:
        if isinstance(o, dict): return {str(k): ser(v) for k, v in o.items()}
        if isinstance(o, (list, tuple)): return [ser(x) for x in o]
        return repr(o)
out = {}
for t in TASKS:
    m = importlib.import_module(f"robomme.robomme_env.{t}")
    cls = getattr(m, t)
    rec = {}
    for k in ("config_easy","config_medium","config_hard","config_xhard","configs"):
        rec[k] = ser(getattr(cls, k, None))
    rec["XHARD_DECISION"] = ser(getattr(m, "XHARD_DECISION", None))
    fn = getattr(m, "_native_decision", None)
    if fn:
        try: rec["_native_decision"] = ser(fn(cls))
        except TypeError:
            try: rec["_native_decision"] = ser(fn())
            except Exception as e: rec["_native_decision"] = f"ERR {e}"
    out[t] = rec
sc = json.load(open("scripts/configs/newtask-v5/sampling_config.json"))
out["__sampling_config_top_keys__"] = list(sc.keys()) if isinstance(sc, dict) else str(type(sc))
out["__sampling_config__"] = sc
json.dump(out, open(sys.argv[1], "w"), indent=1, ensure_ascii=False)
print("ok")
