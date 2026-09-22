# 步 5c 报告：多 worker 等价性（2026-09-21）

对应 [NEWTASK_RELEASE_V3_PLAN.md](../../../NEWTASK_RELEASE_V3_PLAN.md) 第五节步 5c，闸门 P4／P6（`WORKER_ISOLATION`）。运行目录 `artifacts/train-parity/gl-5c`。

## 一、为什么先做 5c 再做 5d

原本打算用单 worker 直接跑 5d，理由是「多 worker 等价性还没验，不让未验证变量混进判据数据」。用户指出这是舍近求远：方案本来就把 5c 排在 5d 之前，**先花十分钟验多 worker，再用 4 worker 跑 5d**，比绕开它慢跑两小时划算。采纳。

## 二、第一版 5c 是无效的（自查纠正）

第一版让每个环境只跑 `episode 0` 一条身份、`--workers 4`。但运行器里是
`max_workers=min(args.workers, len(jobs))`——**一次运行只有一条身份时，4 worker 会退化成 1 worker**，等于拿单 worker 比单 worker，什么也没验到。已作废重跑。

结论：要压出多 worker 并行，一次运行里必须有多条身份。

## 三、重做后的做法

每个 job 负责一个环境，跑该环境**全部 9 条子集身份**（`episode 0,1,2,3,4,6,7,10,11`），
先 `--workers 1` 跑一遍、再 `--workers 4` 跑一遍，然后逐位比 A1／B／C／D 四路。

选这四个环境是按代码路径差异挑的：`BinFill`（两种 dynamic）、`VideoUnmaskSwap`（交换与延迟搭档）、`VideoPlaceOrder`（最长 episode）、`InsertPeg`（杆的拒绝采样）。9 条身份本身横跨 easy／medium／hard 三档与 z／xy／关闭三种恢复模式，因此这一轮同时是「多 worker 下恢复分支不串味」的证据，也是 **xy 与关闭两种恢复模式第一次上集群**。

## 四、结果

| 环境 | 比较对数 | 整文件散列相同 | 字段／伴生差异 | 单 worker | 4 worker | 加速 |
|---|---|---|---|---|---|---|
| BinFill | 36 | 36 | 0 | 345.9 s | 159.0 s | 2.18× |
| VideoUnmaskSwap | 36 | 36 | 0 | 164.1 s | 77.6 s | 2.11× |
| VideoPlaceOrder | 36 | 36 | 0 | 546.8 s | 258.3 s | 2.12× |
| InsertPeg | 36 | 36 | 0 | 269.0 s | 124.7 s | 2.16× |

（耗时列为 A1 路 9 条身份的整段耗时。）

```text
WORKER_ISOLATION=PASS tasks=1 mismatch=0 input_mutation=0   ×4（四个环境各一行）
```

合计 **144 对比较全部 `sha_equal`、零差异**；`input_mutation=0` 表示两侧消费的 `sampling_config`／`episode_spec` 输入散列没有被改动。

加速比稳定在 2.1～2.2 倍，与步骤「十」里 8 worker 只得 2.5 倍的探针结论一致——瓶颈在进程启动与场景编译，不在并行度。

## 五、对 5d 的影响

5d 改用 `--workers 4`：每片 36 条身份 × 5 路 = 180 次生成，按实测约 1 小时（单 worker 需约 2.5 小时）。

## 六、覆盖边界

- 只覆盖 4 个环境（16 选 4），其余十二个环境的多 worker 等价性由 5d 的产物间接受益但未单独比对。
- P6 里「甲→乙→甲 在同一 PID」这一形态：本轮是「同一运行内多条身份复用 worker 进程」，与之等价的顺序复用已覆盖；跨环境交替的形态留到 5d 的分片运行（每片 4 个环境混跑）后再核。
