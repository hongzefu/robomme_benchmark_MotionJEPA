"""v3.1 候选变体包：每个变体是本目录下一个独立模块，互不 import、互不修改。

## 变体模块契约（强制）

每个变体模块（如 ``variants/foo.py``）必须定义：

- ``NAME: str``——与文件名（去 ``.py``）一致；
- ``DESCRIPTION: str``——一句话中文描述（机制要点）；
- ``compute_masks(frames, phase_flags) -> (remove_masks, tip_masks, stats)``：
  - 入参 ``frames``: ``(N,H,W,3) uint8`` RGB；``phase_flags``: ``(N,) bool``
    （``is_video_demo`` 相位标志，相位切段用）；
  - ``remove_masks``: ``(N,H,W) bool``——**最终要涂红删除**的像素（黑指尖已从中
    扣除）；
  - ``tip_masks``: ``(N,H,W) bool``——判定为「夹爪黑色指尖、予以保留」的像素，
    只用于可视化（渲染器画成绿色）；必须与 ``remove_masks`` 逐帧不相交；
    没有指尖保留机制或该帧无指尖时给全 False；
  - ``stats``: 可 JSON 序列化的字典（自由结构，进 ``summary.json``）。

## 口径（v3.1，与 v3 的关键差异）

1. **任务物体零误删（硬约束）**：桌面上与被操作的任务物体一个像素都不得进
   ``remove_masks``——包括与臂接触/被夹持/被拖动的帧。「多删背景可接受、误删
   物体不可接受」，与 v3 的「多删可接受」优先级相反。
2. **夹爪黑色指尖保留（硬约束）**：14 个夹爪任务里手指末端的黑色接触面
   （参考定义：三通道均值 ≤ 100 的手指端部像素）不得删除，进 ``tip_masks``；
   手掌与腕部相机支架上的其他黑色块不属于指尖，照删。
3. **panda_stick 任务（PatternLock / RouteStick）机器人全删**：含 stick 工具，
   无任何保留（这两个任务 ``tip_masks`` 应为全 False）；但被操作物（白色缆线、
   按钮等）仍受口径 1 保护。
4. **软目标**：满足 1–3 前提下机器人删得尽可能干净。

## 依赖纪律（与 v3 相同，测试会用 AST 钉死）

只准 import numpy / cv2 / 标准库 / 本目录基座 ``cv_base``；禁止 h5py、scipy、
torch、仓库内其他模块；源码不得出现任何仿真分割相关标识符（纯 CV 口径）。
"""
