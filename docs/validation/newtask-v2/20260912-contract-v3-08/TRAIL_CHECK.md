# 白球尾迹减半核验（08 对 07，RouteStick 四档 ep0）

方法见 [trail_check.py](trail_check.py) 文首说明：同规格同 seed 下 07 与 08 机械臂轨迹逐帧相同，每像素「最长连续白帧游程」之差在尾迹像素上应恰为 20（40 − 20），机械臂像素为 0。逐档明细在 `trail_check_<难度>.json`（含差值直方图）。

```
TRAIL_HALVED=PASS median_diff=20.0 share_18_22=0.609 n=458 left_frames=300 right_frames=300 difficulty=easy episode=0 left=20260911-contract-v3-07 right=20260912-contract-v3-08
TRAIL_HALVED=PASS median_diff=20.0 share_18_22=0.737 n=1207 left_frames=500 right_frames=500 difficulty=medium episode=0 left=20260911-contract-v3-07 right=20260912-contract-v3-08
TRAIL_HALVED=PASS median_diff=20.0 share_18_22=0.609 n=617 left_frames=400 right_frames=400 difficulty=hard episode=0 left=20260911-contract-v3-07 right=20260912-contract-v3-08
TRAIL_HALVED=PASS median_diff=20.0 share_18_22=0.606 n=2061 left_frames=1000 right_frames=1000 difficulty=xhard episode=0 left=20260911-contract-v3-07 right=20260912-contract-v3-08
```

⚠ 像素面积比值法不可用：Panda 机械臂本身是白色，07 对 08 的近白像素面积比实测 0.733 而非 0.5。
