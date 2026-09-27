"""放慢方案的两种形态（逐段末尾停顿 H 帧 / 整段时间拉伸 ts）在 5x5 [20,24] 300 个种子上的演示时长分布（基于离线模型逐路径帧数）。
注：ts 形态这里用 demo×ts 近似（逐段 ceil 的误差 ≤ 段数帧）。"""
import json, numpy as np, os
d = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "pl_study_5x5_0.1_dfs_20_24_ts1.0.json")))["rows"]
demo = np.array([r["demo"] for r in d]); segs = np.array([r["segs"] for r in d])
for H in (8, 9, 10, 11, 12):
    x = demo + H * segs
    print(f"hold H={H:2d}: sec min={x.min()/30:.2f} mean={x.mean()/30:.2f} max={x.max()/30:.2f} in[750,1050]={np.mean((x>=750)&(x<=1050)):.3f}")
for ts in (1.25, 1.3, 1.35, 1.4):
    x = np.ceil(demo * ts)
    print(f"stretch ts={ts}: sec min={x.min()/30:.2f} mean={x.mean()/30:.2f} max={x.max()/30:.2f} in[750,1050]={np.mean((x>=750)&(x<=1050)):.3f}")
