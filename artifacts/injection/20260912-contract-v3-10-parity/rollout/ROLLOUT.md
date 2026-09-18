# 实跑结果

运行：`20260912-contract-v3-10-parity`；用途：`parity`。

结果按唯一键保存；reset 通过只表示能建环境，不表示可以完成任务。

| 组 | HDF5 正式 | HDF5 备用 | HDF5 失败 | reset 正式 | reset 备用 | reset 失败 |
|---|---:|---:|---:|---:|---:|---:|
| BinFill/easy | 14 | 0 | 1 | 50 | 1 | 0 |
| BinFill/medium | 15 | 0 | 0 | 50 | 1 | 0 |
| BinFill/hard | 14 | 0 | 1 | 50 | 1 | 0 |
| RouteStick/easy | 15 | 0 | 0 | 50 | 1 | 0 |
| RouteStick/medium | 15 | 0 | 0 | 50 | 1 | 0 |
| RouteStick/hard | 15 | 0 | 0 | 50 | 1 | 0 |
| VideoUnmaskSwap/easy | 15 | 0 | 0 | 50 | 1 | 0 |
| VideoUnmaskSwap/medium | 15 | 0 | 0 | 50 | 1 | 0 |
| VideoUnmaskSwap/hard | 15 | 0 | 0 | 50 | 1 | 0 |
| VideoRepick/easy | 14 | 0 | 1 | 50 | 1 | 0 |
| VideoRepick/medium | 15 | 0 | 0 | 50 | 1 | 0 |
| RouteStick/xhard | 15 | 0 | 0 | 50 | 1 | 0 |
| VideoUnmaskSwap/xhard | 14 | 0 | 1 | 50 | 4 | 0 |
| VideoRepick/xhard | 14 | 0 | 1 | 50 | 4 | 0 |

## 视频状态

{'complete': 208, 'no_close': 2}

## 失败记录

| 类型 | 组 | episode | seed | 异常 |
|---|---|---:|---:|---|
| h5 | BinFill/easy | 10 | 5000 | DatasetGenerationError |
| h5 | BinFill/hard | 4 | 4400 | DatasetGenerationError |
| h5 | VideoRepick/easy | 0 | 9000 | EpisodeWallClockTimeout |
| h5 | VideoRepick/xhard | 5 | 9500 | DatasetGenerationError |
| h5 | VideoUnmaskSwap/xhard | 7 | 5700 | EpisodeWallClockTimeout |

候选角色：`{'test/primary': 700, 'test/spare': 20, 'test/unused': 838, 'train/failed': 5, 'train/pending': 1632, 'train/primary': 205}`。

完整交付缺口组：`['BinFill/easy', 'BinFill/medium', 'BinFill/hard', 'RouteStick/easy', 'RouteStick/medium', 'RouteStick/hard', 'VideoUnmaskSwap/easy', 'VideoUnmaskSwap/medium', 'VideoUnmaskSwap/hard', 'VideoRepick/easy', 'VideoRepick/medium', 'RouteStick/xhard', 'VideoUnmaskSwap/xhard', 'VideoRepick/xhard']`。局部运行不冒充完整交付。
