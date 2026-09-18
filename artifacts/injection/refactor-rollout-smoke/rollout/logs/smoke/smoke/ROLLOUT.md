# 实跑结果

运行：`refactor-rollout-smoke-smoke`；用途：`smoke`。

结果按唯一键保存；reset 通过只表示能建环境，不表示可以完成任务。

| 组 | HDF5 正式 | HDF5 备用 | HDF5 失败 | reset 正式 | reset 备用 | reset 失败 |
|---|---:|---:|---:|---:|---:|---:|
| BinFill/easy | 0 | 0 | 0 | 0 | 0 | 0 |
| BinFill/medium | 0 | 0 | 0 | 0 | 0 | 0 |
| BinFill/hard | 0 | 0 | 0 | 0 | 0 | 0 |
| RouteStick/easy | 1 | 0 | 0 | 1 | 0 | 0 |
| RouteStick/medium | 0 | 0 | 0 | 0 | 0 | 0 |
| RouteStick/hard | 0 | 0 | 0 | 0 | 0 | 0 |
| VideoUnmaskSwap/easy | 0 | 0 | 0 | 0 | 0 | 0 |
| VideoUnmaskSwap/medium | 0 | 0 | 0 | 0 | 0 | 0 |
| VideoUnmaskSwap/hard | 0 | 0 | 0 | 0 | 0 | 0 |
| VideoRepick/easy | 0 | 0 | 0 | 0 | 0 | 0 |
| VideoRepick/medium | 0 | 0 | 0 | 0 | 0 | 0 |
| RouteStick/xhard | 0 | 0 | 0 | 0 | 0 | 0 |
| VideoUnmaskSwap/xhard | 0 | 0 | 0 | 0 | 0 | 0 |
| VideoRepick/xhard | 0 | 0 | 0 | 0 | 0 | 0 |

## 视频状态

{'complete': 1}

## 失败记录

| 类型 | 组 | episode | seed | 异常 |
|---|---|---:|---:|---|

候选角色：`{'test/pending': 1557, 'test/primary': 1, 'train/pending': 1841, 'train/primary': 1}`。

完整交付缺口组：`['BinFill/easy', 'BinFill/medium', 'BinFill/hard', 'RouteStick/easy', 'RouteStick/medium', 'RouteStick/hard', 'VideoUnmaskSwap/easy', 'VideoUnmaskSwap/medium', 'VideoUnmaskSwap/hard', 'VideoRepick/easy', 'VideoRepick/medium', 'RouteStick/xhard', 'VideoUnmaskSwap/xhard', 'VideoRepick/xhard']`。局部运行不冒充完整交付。
