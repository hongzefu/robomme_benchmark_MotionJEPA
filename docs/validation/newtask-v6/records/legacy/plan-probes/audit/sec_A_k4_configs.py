# 只读探针：导入三个环境类，比对 config_easy/medium/hard 是否逐字同值，并列出 difficulty 相关读取点
import importlib, json, re, pathlib
for e in ["StopCube", "MoveCube", "InsertPeg"]:
    m = importlib.import_module(f"robomme.robomme_env.{e}")
    cls = getattr(m, e)
    cfgs = {k: getattr(cls, f"config_{k}", None) for k in ["easy", "medium", "hard", "xhard"]}
    print(e, {k: (v is not None) for k, v in cfgs.items()})
    if cfgs["easy"] is not None:
        print("  easy==medium==hard:", cfgs["easy"] == cfgs["medium"] == cfgs["hard"])
        print("  easy:", json.dumps(cfgs["easy"], default=str)[:300])
    src = pathlib.Path(m.__file__).read_text()
    for i, line in enumerate(src.splitlines(), 1):
        if re.search(r"difficulty", line) and not line.strip().startswith("#"):
            if re.search(r'"(easy|medium|hard)"', line) or "configs[" in line or "_config" in line.lower():
                print("  L%d: %s" % (i, line.strip()[:140]))
