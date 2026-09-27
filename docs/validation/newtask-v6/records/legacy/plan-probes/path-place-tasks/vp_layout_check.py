"""复刻核验：复刻布局在 seed 5000000..5000299 上的 xhard 成功率应等于 S3i 真 reset 的 81.7%（VPB）/ 48.3%（VPO）。"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vp_layout_mc import layout
for env in ("VideoPlaceButton", "VideoPlaceOrder"):
    rs = [layout(env, 5000000 + k) for k in range(300)]
    from collections import Counter
    print(env, "ok", sum(r == "ok" for r in rs), "/300", Counter(rs))
