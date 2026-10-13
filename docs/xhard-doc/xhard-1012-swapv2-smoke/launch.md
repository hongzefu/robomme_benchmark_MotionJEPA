# 交换配对第二版：阶段 D 启动档案

用户最新原话：「根据最新的计划修正后的内容 继续」。本批按已批准计划执行 GPU 契约、失败送达和四卡单 worker smoke，完成后才对全量一百八十卡另行报批。重大口径调整立即停工。

## 版本与已经通过的闸门

W2 合并为 `abed3ba9f48a702ecbb33c10c746e72bfd99b3a5`（2.96），保留 W2-a/b/c 及审查修补 W2-d 四个子提交。独立审查 `PRE_MERGE_REVIEW=PASS`；主检出核心实测 427 通过、四项原基线失败、二跳过，8.69 秒，pytest 退出 1，逐节点闸门 `CORE_SHORT=PASS new_failures=0 baseline_failures=4 passed=427`。官方源码零差异，两份引入源码完整哈希命中固定值。

实施途中主线回流新增了开工前计划全文一致性审查规则；在进一步 GPU 实跑前补做独立只读全文核对：`PLAN_CONSISTENCY_REVIEW=PASS base=0dfb2aead0c48ad545909fa9280e64dfc3a1c404 findings=7 blocking=0`，审查仓库锚点为上述 2.96。七项只作文字与图示维护：补完整证据摘要和已有 slots 字段说明、纠正配置访问与伪码变量名、图三顺序与已实现认证顺序统一、旧授权状态标明历史、四个实际子提交记全。没有待裁决的机制、接口、失败处理、预算或验收变更。

本启动档案与文档维护先提交，实际 GPU 起跑版本为该提交；启动时把完整 HEAD 作为参数传入运行器，由运行器检查版本和工作区干净。阶段 D 期间主会话冻结 HEAD，不改源码、依赖或配置，不提交其他内容。日志同时记录 `SOURCE_HEAD=`，结果留档另记录实际 SHA，不能把 2.96 当作后来诊断启动的精确提交。

## 环境、范围与输入

主机 sled-vail，工作副本 `/data/hongzefu/robomme_benchmark_newtask-v3-MotionJepa1006`，本机 GPU0；起跑前核对为 RTX 6000 Ada、1286 MiB / 46068 MiB、利用率零，未被占满。Python 与依赖仍使用本仓库 uv 环境，`UV_CACHE_DIR=/home/hongzefu/.cache/uv`。不提交集群作业，不切换 GPU，不安装依赖，不改默认后端。

先单任务、单 seed 最小复位测试通过后再跑 D1。D1 收集为十七项 GPU 用例（含五档槽、图、配对前缀及三任务故障送达）；首项失败停止，单次墙钟上限一小时，不重试。四卡 smoke 只含原批准身份：VideoUnmaskSwap episode 7/seed 5700 与 episode 43/seed 9300，ButtonUnmaskSwap episode 35/seed 10500，VideoRepick episode 22/seed 11200；来源难度与母清单不变，全部 xhard20、单 worker。母档与其他 seed 不生成。

输入清单 `artifacts/xhard/xhard-1012-swapv2/smoke_seeds.json`，输出根 `artifacts/xhard/xhard-1012-swapv2/smoke/` 必须不存在。旧根 `artifacts/xhard/xhard-1012-coll/` 全部四百二十六文件继续只读保留，结束后按冻结哈希和字节数复核。

## 完整命令与运行器

最小 GPU 短测（前置固定 HEAD 与干净工作区检查，输出日志不存在；带 pipefail、tee 与退出记录）：

```bash
CUDA_VISIBLE_DEVICES=0 UV_CACHE_DIR=/home/hongzefu/.cache/uv PYTHONUNBUFFERED=1 timeout 280s uv run --no-sync python -m pytest src/robomme_xhard/tests/test_swap_collision_gpu.py -m gpu -k 'test_reset_certifies_all_pairs and VideoUnmaskSwap' -q -rf -x
```

D1 的实际 uv 命令：

```bash
CUDA_VISIBLE_DEVICES=0 UV_CACHE_DIR=/home/hongzefu/.cache/uv PYTHONUNBUFFERED=1 XHARD_TIMING_EVIDENCE_ROOT=/data/hongzefu/robomme_benchmark_newtask-v3-MotionJepa1006/artifacts/xhard/xhard-1012-swapv2/gpu-contract timeout 3600s uv run --no-sync python -m pytest src/robomme_xhard/tests/test_swap_collision_gpu.py src/robomme_xhard/tests/test_fatal_catch.py -m gpu -q -rf -x
```

四卡 smoke 的实际 uv 命令：

```bash
UV_CACHE_DIR=/home/hongzefu/.cache/uv PYTHONUNBUFFERED=1 timeout 3600s uv run --no-sync python scripts/data-generation-newSeed/generate_dataset_newseed.py --env VideoUnmaskSwap,ButtonUnmaskSwap,VideoRepick --difficulty xhard20 --mother-manifest artifacts/xhard/xhard-1012-swapv2/smoke_seeds.json --gpus 0 --workers 1 --output-dir artifacts/xhard/xhard-1012-swapv2/smoke
```

多变量长命令先落本轮运行器再进入 detached tmux；运行器只在 `artifacts/`，不把 bash 拷贝放入档案。D1 运行器 `run_d1.sh` 的 SHA256 为 `a2aee665e7cca976caa7473baed5042ab04d30069c68ea9a0430177a28f2de2f`，smoke 运行器 `run_smoke.sh` 为 `7f4f87e64f6cdb6f646ff81d6feada735533e4d80c8630ce985762b49ea79bb4`，两者在 `artifacts/xhard/xhard-1012-swapv2/`；执行前核对其字节与日志／目标新鲜性。它们分别包上述完整命令，使用 `set -o pipefail`、`PYTHONUNBUFFERED=1`、`tee` 和 `EXIT_CODE=`。

```bash
tmux new-session -d -s xh-swapv2-d1-1012 "bash /data/hongzefu/robomme_benchmark_newtask-v3-MotionJepa1006/artifacts/xhard/xhard-1012-swapv2/run_d1.sh <实际启动HEAD>"
tmux new-session -d -s xh-swapv2-smoke-1012 "bash /data/hongzefu/robomme_benchmark_newtask-v3-MotionJepa1006/artifacts/xhard/xhard-1012-swapv2/run_smoke.sh <同一启动HEAD>"
```

## 会话、日志、监听与停止

本批预定会话清单只有 `xh-swapv2-d1-1012`、`xh-swapv2-smoke-1012`，顺序运行；实际启动后分别记录。日志为 `artifacts/logs/xh-swapv2-d1-min-1012.log`、`xh-swapv2-d1-1012.log`、`xh-swapv2-smoke-1012.log`；D1 时间步证据在新根 `gpu-contract/`。读取日志使用持久 tail 与逐级行缓冲过滤，核对实际 tmux/PID 存活及 `EXIT_CODE=`。不新增高频 GPU 查询。

失败保留日志、版本、参数和已写产物，停止后续阶段，不改判据、不降级、不换 seed、不自行重试。基础设施／接口故障均阻断。四卡判据沿用批准计划：5700、9300 必须成功；10500 必须在 reset 的 graph 阶段正常拒绝；11200 的有证据碰撞或槽位绑定正常拒绝不阻断，接口或基础设施错误阻断。阶段结果独立报告任务成功字段，不能把批次验收通过写成四条任务全部成功。
