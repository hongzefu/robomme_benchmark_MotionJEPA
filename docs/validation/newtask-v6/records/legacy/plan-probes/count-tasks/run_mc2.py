"""第二批：Pick/Swing 往更大 N 扫到 50%/90% 边界；BinFill / PickHighlight 只放大 y 向（x 受可达性约束）的框。"""
import json, sys
import run_mc
from run_mc import sweep
env = sys.argv[1]
rows = []
if env == "PickXtimes":
    rows += sweep(env, [16, 18, 20, 22, 24, 26, 28, 30], "现值 0.25 d=0.08")
    rows += sweep(env, [18, 20, 22, 24, 26, 28, 30, 32], "y 半宽 0.30 d=0.08", region_half=(0.25, 0.30))
elif env == "SwingXtimes":
    rows += sweep(env, [18, 20, 22, 24, 26, 28, 30], "现值 0.25 d=0.08")
    rows += sweep(env, [18, 20, 22, 24, 26, 28, 30, 32], "y 半宽 0.30 d=0.08", region_half=(0.25, 0.30))
elif env == "BinFill":
    rows += sweep(env, [16, 18, 20, 22, 24, 26], "y 半宽 0.32", region_half=(0.2, 0.32))
    rows += sweep(env, [14, 16, 18, 20], "现值框 预算1024", trials=1024)
elif env == "PickHighlight":
    rows += sweep(env, [8, 10, 12, 14, 16], "y 半宽 0.25（x 不动）", region_half=(0.2, 0.25))
    rows += sweep(env, [10, 12, 14, 16, 18], "y 半宽 0.30（x 不动）", region_half=(0.2, 0.30))
    rows += sweep(env, [10, 12, 14, 16, 18], "y 半宽 0.30 预算1024", region_half=(0.2, 0.30), trials=1024)
    rows += sweep(env, [10, 12, 14, 16], "gap 0.03（现框）", gap=0.03)
json.dump(rows, open(f"mc2_{env}.json", "w"), ensure_ascii=False, indent=1)
