# robomme-ICL v3 全量结果

基线 `e34474a6304b917b44cedae129ac621ddd52a430` 下的96条规格已完成双进程严格认证、32/16 worker 两套新生成、断点复用、动作回放和同环境连续 reset 验收。所有正式阶段退出码均为0。

本工具核对已签名验收证据、套件及 HDF5 记录头，没有重新执行仿真或再次解码全部 RGB；逐帧字节一致的结论来自已通过的严格验收链。

每遍共 63689 帧；两轮生成均覆盖相同96个 spec，使用相同逆序与原 GPU 绑定，所有生成记录均为 `resumed=false`。

## 阶段结果

| 阶段 | 条数 | 墙钟秒数 | episode/秒 |
| --- | ---: | ---: | ---: |
| certification96 | 96 | 1207.524616 | 0.079501 |
| generate-reverse-w32 | 96 | 277.080352 | 0.346470 |
| generate-reverse-w16 | 96 | 302.238754 | 0.317630 |
| resume-forward-w4 | 96 | 282.981079 | 0.339245 |
| replay-forward-w32 | 96 | 304.062712 | 0.315724 |
| reset-reverse-w32 | 96 | 354.317877 | 0.270943 |
| plots | 4 | 1.794050 | 2.229593 |

## 32 与16 worker 匹配批次对照

32 worker：277.080352 秒，229.857511 帧/秒；16 worker：302.238754 秒，210.724135 帧/秒。

本批次的16/32吞吐比为 **0.916760**。这是先32、后16的一次顺序实验，没有独立预热或稳态分段，可能受缓存和主机负载影响，不能据此宣称全局最优并发。

## 实际规格与帧数

| 任务/难度/GPU | 条数 | 每遍帧数 |
| --- | ---: | ---: |
| BinFill/easy/gpu0 | 4 | 2048 |
| BinFill/easy/gpu1 | 4 | 2709 |
| BinFill/hard/gpu0 | 4 | 4103 |
| BinFill/hard/gpu1 | 4 | 4658 |
| BinFill/medium/gpu0 | 4 | 3868 |
| BinFill/medium/gpu1 | 4 | 3232 |
| RouteStick/easy/gpu0 | 4 | 1714 |
| RouteStick/easy/gpu1 | 4 | 1498 |
| RouteStick/hard/gpu0 | 4 | 2818 |
| RouteStick/hard/gpu1 | 4 | 2806 |
| RouteStick/medium/gpu0 | 4 | 2418 |
| RouteStick/medium/gpu1 | 4 | 2412 |
| VideoRepick/easy/gpu0 | 4 | 3524 |
| VideoRepick/easy/gpu1 | 4 | 3283 |
| VideoRepick/hard/gpu0 | 4 | 3699 |
| VideoRepick/hard/gpu1 | 4 | 3010 |
| VideoRepick/medium/gpu0 | 4 | 3463 |
| VideoRepick/medium/gpu1 | 4 | 3910 |
| VideoUnmaskSwap/easy/gpu0 | 4 | 1193 |
| VideoUnmaskSwap/easy/gpu1 | 4 | 1503 |
| VideoUnmaskSwap/hard/gpu0 | 4 | 1977 |
| VideoUnmaskSwap/hard/gpu1 | 4 | 2004 |
| VideoUnmaskSwap/medium/gpu0 | 4 | 860 |
| VideoUnmaskSwap/medium/gpu1 | 4 | 979 |

## 按阶段对齐的 GPU 采样

| 阶段 | GPU | 采样数 | 利用率均值 | 0%占比 | 峰值显存 MiB |
| --- | ---: | ---: | ---: | ---: | ---: |
| certification96 | 0 | 2092 | 5.264% | 41.683% | 13553 |
| certification96 | 1 | 2092 | 6.197% | 33.222% | 12056 |
| generate-reverse-w32 | 0 | 519 | 10.744% | 29.287% | 13553 |
| generate-reverse-w32 | 1 | 519 | 11.222% | 28.324% | 12056 |
| generate-reverse-w16 | 0 | 574 | 8.922% | 27.875% | 7285 |
| generate-reverse-w16 | 1 | 574 | 9.517% | 21.951% | 6031 |
| resume-forward-w4 | 0 | 566 | 0.000% | 100.000% | 1017 |
| resume-forward-w4 | 1 | 566 | 0.000% | 100.000% | 9 |
| replay-forward-w32 | 0 | 579 | 9.074% | 26.252% | 13553 |
| replay-forward-w32 | 1 | 579 | 9.489% | 24.698% | 12056 |
| reset-reverse-w32 | 0 | 668 | 15.699% | 12.725% | 13553 |
| reset-reverse-w32 | 1 | 668 | 16.430% | 8.982% | 12056 |
| plots | 0 | 4 | 0.000% | 100.000% | 1017 |
| plots | 1 | 4 | 0.000% | 100.000% | 9 |

采样窗口按 UTC 阶段时间与 GPU 日志的主机时区对齐。利用率为样本均值；原始间隔统计保存在 VERIFIED_ROOT.json，不把名义500ms当作硬件计数器分辨率。

没有逐控制步起止时间戳，不能进行慢步/非慢步 GPU 利用率分层。逐条 build/run/write 及按任务、难度、GPU 的耗时统计保存在 VERIFIED_ROOT.json；并行进程耗时之和不是阶段墙钟时间。reset/resume没有逐条 ICL_TIMING，不能为它们补造任务级耗时。

## 原版边界与图表来源

原版 Git tree `1d0154117e58c783cd3466dbad910aeaaff573a8` 与2.23基线及当前 HEAD 相同；当前源码、依赖、GPU/PCI指纹与运行记录一致。

图表规格集合、样例seed和真实actor散点数均已核对：[figure_sources.json](figures/figure_sources.json)。

![BinFill 实际配额与位置](figures/binfill.png)

![RouteStick 实际配额与位置](figures/routestick.png)

![VideoUnmaskSwap 实际配额与位置](figures/videounmaskswap.png)

![VideoRepick 实际配额与位置](figures/videorepick.png)

原始证据：[run_context.json](run_context.json)、[phase_timings.tsv](phase_timings.tsv)、[main.log](main.log)、[gpu_samples.csv](gpu_samples.csv)。VERIFIED_ROOT.json保留原始纳秒时间、ICL_TIMING原文、所有控制文件摘要与本汇总工具全文。
