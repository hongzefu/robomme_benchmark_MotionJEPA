# 白球尾迹再减半核验（09 对 07 与 09 对 08，RouteStick 四档 ep0）

方法同 [08 的 trail_check.py](../20260912-contract-v3-08/trail_check.py)：每像素「最长连续白帧游程」之差在尾迹像素上应恰为两侧存活步数之差——09 对 07 为 30（40 − 10），09 对 08 为 10（20 − 10；参考侧游程下限用 `--min-run-left 15`）。逐档明细在 `trail_check_vs07_<难度>.json`／`trail_check_vs08_<难度>.json`。

```
TRAIL_HALVED=PASS expected=30 median_diff=30.0 share_pm2=0.570 n=479 left_frames=300 right_frames=300 difficulty=easy episode=0 left=20260911-contract-v3-07 right=20260912-contract-v3-09
TRAIL_HALVED=PASS expected=30 median_diff=30.0 share_pm2=0.685 n=1233 left_frames=500 right_frames=500 difficulty=medium episode=0 left=20260911-contract-v3-07 right=20260912-contract-v3-09
TRAIL_HALVED=PASS expected=30 median_diff=30.0 share_pm2=0.620 n=623 left_frames=400 right_frames=400 difficulty=hard episode=0 left=20260911-contract-v3-07 right=20260912-contract-v3-09
TRAIL_HALVED=PASS expected=30 median_diff=30.0 share_pm2=0.514 n=2088 left_frames=1000 right_frames=1000 difficulty=xhard episode=0 left=20260911-contract-v3-07 right=20260912-contract-v3-09
TRAIL_HALVED=PASS expected=10 median_diff=10.0 share_pm2=0.542 n=936 left_frames=300 right_frames=300 difficulty=easy episode=0 left=20260912-contract-v3-08 right=20260912-contract-v3-09
TRAIL_HALVED=PASS expected=10 median_diff=10.0 share_pm2=0.585 n=2302 left_frames=500 right_frames=500 difficulty=medium episode=0 left=20260912-contract-v3-08 right=20260912-contract-v3-09
TRAIL_HALVED=PASS expected=10 median_diff=10.0 share_pm2=0.645 n=1149 left_frames=400 right_frames=400 difficulty=hard episode=0 left=20260912-contract-v3-08 right=20260912-contract-v3-09
TRAIL_HALVED=PASS expected=10 median_diff=10.0 share_pm2=0.496 n=3626 left_frames=1000 right_frames=1000 difficulty=xhard episode=0 left=20260912-contract-v3-08 right=20260912-contract-v3-09
```
