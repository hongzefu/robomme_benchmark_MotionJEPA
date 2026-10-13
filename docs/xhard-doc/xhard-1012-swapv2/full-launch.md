# 交换配对第二版：全量启动档案

用户在获知四卡 smoke 全部符合判据后，两次原话：「你还在等什么，为什么还不开始。」本轮据此接续当前完整计划的阶段 E，开始单独的全量：三任务、三十个母 seed、每 seed 一母档与五 xhard 档，共一百八十个身份。GPU0、三十二 worker，不换 seed、不补 seed；旧目录只读不动。

## 版本与代码冻结

此前 D1b 十八项通过；三按钮位姿位置差零、角差 `4.4408920985e-16`；四卡 smoke 三条成功、一条预期 graph 正常拒绝，infra 零；三个 H5 内容契约与旧根四百二十六文件完整性通过。源代码自 W3 合并后没有改变。

本次正式全量先打 2.98Beta，实际完整提交由起跑日志 `SOURCE_HEAD=` 固定。运行器要求 `HEAD` 与传入 Beta SHA 相同、工作区干净才起跑；其源码字节与通过 smoke 的 2.97.1 相同，新增内容仅为结果和启动档案。从生成开始到汇总、对比报告和六列视频打包结束，主会话冻结 HEAD，不改源码、依赖、配置、启动参数，也不提交文档；完成后再以 2.98 回写结论，Beta 永久保留，不 amend 或 squash。

## 环境、输入与规模

本机 sled-vail，工作副本 `/data/hongzefu/robomme_benchmark_newtask-v3-MotionJepa1006`，GPU0 为 RTX 6000 Ada，起跑前使用 1286 MiB / 46068 MiB、利用率零；本机总内存 377 GiB、可用 331 GiB。使用现有 uv 环境，不装依赖，不提交集群作业。

母清单 `artifacts/xhard/xhard-1012-swapv2/mother_seeds_all.json`，固定三任务各十 seed；VideoUnmaskSwap 与 ButtonUnmaskSwap 来源 hard，VideoRepick 来源 medium，母元数据的未核官方 HF revision 状态保留。档案名固定 `xhard-1012-swapv2`，全量输出新目录 `artifacts/xhard/xhard-1012-swapv2/full/`，要求启动时不存在。每卡 attempt=0，母卡三十张、xhard 卡一百五十张；静态预扫剔除缺口不补，正常拒绝与基础设施失败分开报告。

## 完整运行命令

```bash
UV_CACHE_DIR=/home/hongzefu/.cache/uv PYTHONUNBUFFERED=1 timeout 3600s uv run --no-sync python scripts/data-generation-newSeed/generate_dataset_newseed.py --env VideoUnmaskSwap,ButtonUnmaskSwap,VideoRepick --difficulty xhard12,xhard14,xhard16,xhard18,xhard20 --mother-manifest artifacts/xhard/xhard-1012-swapv2/mother_seeds_all.json --with-mother --gpus 0 --workers 32 --output-dir artifacts/xhard/xhard-1012-swapv2/full
```

运行器只落 `artifacts/xhard/xhard-1012-swapv2/run_full.sh`，不复制 bash 到 docs。日志 `artifacts/logs/xh-swapv2-full-1012.log`，detached tmux 会话仅 `xh-swapv2-full-1012`，使用 pipefail、tee、PYTHONUNBUFFERED 与 EXIT_CODE。运行型代理只按确定版本和该命令启动，禁止修代码、改参数、重试、清理或取消会话；监听、预算与清理归主会话。

上轮同机同 GPU0／三十二 worker 的 v1 一百八十身份实测生成墙钟 612.9 秒。本轮生成预估十至二十分钟，正式吞吐尚未实测；生成墙钟上限一小时。汇总、三十支六列视频及 v1/v2 对比随后执行，全部输出新 `report/`。

## 失败与收尾

进程池损坏、基础设施异常、无进展或一小时超限均保留证据并停止；任一任务 SwapBindingError 超过该任务五十张 xhard 的 10%，即超过五张，按计划停止。发现必须修代码或重大口径调整，先停止受影响本轮任务，交用户审查，不让旧方案后台继续；不动用户其他任务、会话或资产。

正常碰撞、绑定或静态前提拒绝按任务拒绝计数，不换 seed。生成器因正常拒绝返回非零不改写退出码；交付按 `XHARD_FULL_DERIVE` 的 expected=180、seen=180、missing=0、dup=0、unknown=0、infra=0 判定，再核对独立任务成功字段。汇总、六列视频、两轮对比报告与旧根完整性必须分别给出具名判定行，不能用单条笼统成功代替。
