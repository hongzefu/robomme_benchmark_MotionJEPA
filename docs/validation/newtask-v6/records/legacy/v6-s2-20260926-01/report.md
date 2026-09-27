# S2 固定144次演示汇总

S2_ATTEMPT_COVERAGE=PASS expected=144 attempted=144 missing=0
S2_TASK_SUCCESS=119/144 failed=25 timeout=0
S2_SUCCESS_MEDIA=PASS successful=119 failed_checks=0

失败保留在固定144分母；成功率与尝试完成、媒体核验分别报告。视频只核验首帧真实解码，不证明全帧完整。
实际初始化／reset调用数未观测；不由逻辑尝试数推算。MoveCube只认本轮HDF5显式方法字段；缺失时不可核验，历史seed映射不代替实际覆盖。

|任务|档位|计划|已尝试|成功|失败|超时|缺失结果|成功媒体异常|
|---|---|---:|---:|---:|---:|---:|---:|---:|
|BinFill|xhard1|2|2|2|0|0|0|0|
|BinFill|xhard2|2|2|2|0|0|0|0|
|BinFill|xhard3|2|2|2|0|0|0|0|
|BinFill|xhard4|2|2|2|0|0|0|0|
|ButtonUnmask|xhard1|2|2|2|0|0|0|0|
|ButtonUnmask|xhard2|2|2|2|0|0|0|0|
|ButtonUnmask|xhard3|2|2|2|0|0|0|0|
|ButtonUnmask|xhard4|2|2|2|0|0|0|0|
|ButtonUnmaskSwap|xhard1|4|4|4|0|0|0|0|
|ButtonUnmaskSwap|xhard2|4|4|1|3|0|0|0|
|ButtonUnmaskSwap|xhard3|4|4|3|1|0|0|0|
|ButtonUnmaskSwap|xhard4|4|4|3|1|0|0|0|
|InsertPeg|xhard4|2|2|0|2|0|0|0|
|MoveCube|xhard4|12|12|9|3|0|0|0|
|PatternLock|xhard1|2|2|2|0|0|0|0|
|PatternLock|xhard2|2|2|2|0|0|0|0|
|PatternLock|xhard3|2|2|2|0|0|0|0|
|PatternLock|xhard4|2|2|2|0|0|0|0|
|PickHighlight|xhard1|2|2|2|0|0|0|0|
|PickHighlight|xhard2|2|2|2|0|0|0|0|
|PickHighlight|xhard3|2|2|2|0|0|0|0|
|PickHighlight|xhard4|2|2|2|0|0|0|0|
|PickXtimes|xhard1|2|2|2|0|0|0|0|
|PickXtimes|xhard2|2|2|2|0|0|0|0|
|PickXtimes|xhard3|2|2|2|0|0|0|0|
|PickXtimes|xhard4|2|2|2|0|0|0|0|
|RouteStick|xhard1|2|2|2|0|0|0|0|
|RouteStick|xhard2|2|2|2|0|0|0|0|
|RouteStick|xhard3|2|2|2|0|0|0|0|
|RouteStick|xhard4|2|2|2|0|0|0|0|
|StopCube|xhard4|2|2|2|0|0|0|0|
|SwingXtimes|xhard1|2|2|2|0|0|0|0|
|SwingXtimes|xhard2|2|2|2|0|0|0|0|
|SwingXtimes|xhard3|2|2|2|0|0|0|0|
|SwingXtimes|xhard4|2|2|2|0|0|0|0|
|VideoPlaceButton|xhard1|2|2|1|1|0|0|0|
|VideoPlaceButton|xhard2|2|2|2|0|0|0|0|
|VideoPlaceButton|xhard3|2|2|1|1|0|0|0|
|VideoPlaceButton|xhard4|2|2|2|0|0|0|0|
|VideoPlaceOrder|xhard1|2|2|0|2|0|0|0|
|VideoPlaceOrder|xhard2|2|2|0|2|0|0|0|
|VideoPlaceOrder|xhard3|2|2|1|1|0|0|0|
|VideoPlaceOrder|xhard4|2|2|1|1|0|0|0|
|VideoRepick|xhard1|4|4|3|1|0|0|0|
|VideoRepick|xhard2|4|4|3|1|0|0|0|
|VideoRepick|xhard3|4|4|1|3|0|0|0|
|VideoRepick|xhard4|4|4|3|1|0|0|0|
|VideoUnmask|xhard1|2|2|2|0|0|0|0|
|VideoUnmask|xhard2|2|2|2|0|0|0|0|
|VideoUnmask|xhard3|2|2|2|0|0|0|0|
|VideoUnmask|xhard4|2|2|2|0|0|0|0|
|VideoUnmaskSwap|xhard1|4|4|4|0|0|0|0|
|VideoUnmaskSwap|xhard2|4|4|4|0|0|0|0|
|VideoUnmaskSwap|xhard3|4|4|3|1|0|0|0|
|VideoUnmaskSwap|xhard4|4|4|4|0|0|0|0|

每个身份的错误、退出码、HDF5结构／终态核验及视频首帧结果见同目录 report.json。
