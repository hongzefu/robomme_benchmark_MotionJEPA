# BinFill 既有正式数据离线取证

源码审查锚点：`0a3f989b0dfcff12a3cbb34a8112cb56864c7ee8`。输入为 `artifacts/newtask-v6/s4-launch/verification/final-delivery.json` 的 `successes` 中全部 12 条 BinFill 正式 HDF5。未重置环境、未生成轨迹、未改数据。

## 结论与边界

四档各 3 条正式轨迹共 90 次投放，90 次都在孔板上方仍有彩色块时发生相邻帧突消。消失前可见表面高度中位值为 0.177487～0.211496 米，而孔板顶面为 0.05 米。`all12-first-drop.png` 展示每条轨迹首投的前／后帧和两个相机；已逐行目视确认。高度是深度反投影的可见表面统计，不是物体中心位姿，不拿它冒充完整碰撞检测。

`subgoal_evaluate_func.py::is_obj_dropped` 在非演示包装路径允许物体中心 z≤0.2 米；`is_obj_dropped_onto` 仅要求距孔中心的水平距离≤0.05 米；`is_obj_dropped_onto_delete` 再直接将物体传送到 `[10,10,0]` 并计数。这是原生沿用的主动删除设计。问题在于视觉中的物体尚悬空，未展示落入孔洞便被删除；不能将设计删除等同于已展示入孔，也不能声称是 V6 新引入的问题。

前相机颜色掩码：目标色通道>45且为其余最大通道的1.6倍以上；反投影后保留孔心半径0.07米内、z在0.07～0.35米的像素。逐投放边界前12帧查相邻帧，至少8像素且下一帧降至20%以下记一次突消。输出逐帧像素数、高度范围与中位数见 `drop-analysis.json`。颜色掩码只是自动定位手段，不能替代目视检查；联系图提供独立视觉核查。

## 相机与单位校准

深度为毫米，除以1000得到米。使用 HDF5 的 `setup/front_camera_intrinsic` 为 K，逐帧 `obs/front_camera_extrinsic=[R|t]`：

`camera = inv(K) @ [u,v,1] * depth_m`

`world = R.T @ (camera - t)`

在 xhard1／ep0／seed8400000 的 t165，桌面像素(128,170)、(130,150)分别反投影到 z=0.001232、0.000799米；孔板顶面像素(179,98)为0.050992米；孔内黑色视觉底面(185,114)为0.026283米（构建器黑块顶面名义0.025米）。同帧蓝块像素(222,70)为0.209760米。数据及 K/E 原文见 `calibration.json`。独立代理另复核蓝块区域共483像素，世界z=0.169825～0.210808米，下一帧该区域蓝像素为0。

## 复核命令

在主仓根目录运行，只读既有数据、不导入仓库模块：

```bash
UV_CACHE_DIR=/home/hongzefu/.cache/uv uv run --no-sync python artifacts/audit/v6-semantic-evidence-01a0e086/binfill/recheck.py
```

完整逐帧证据为 `drop-analysis.json`；首例时间窗为 `first_drop.png`；12条双相机联系图为 `all12-first-drop.png`。零新增 reset，零新增 rollout。
