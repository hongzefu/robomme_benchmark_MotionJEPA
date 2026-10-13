# v3 全量一百八十卡：起跑档案

本轮执行已批准计划的阶段 D：现有三十个母 seed，母档加五档，共一百八十个身份；本机 GPU0、32 worker，一次生成并汇总、输出三十支六列视频、与 v2 逐身份及固定规划对账。起跑前代码与本档案随 2.103Beta 锁定，生成到包装结束冻结 HEAD；本文件当前记录的是起跑配置与判据，实际结论在 `full-result.md` 回写。

## 一、用户决定与已过闸门

关键用户原话按顺序保留：

1. “错流的视频你可以保存 你只需不记任务成功即可”。
2. “同意，改为核对首次建场的按钮位姿，保留9600和全部数值断言，先修订完整计划给我审查。”
3. 完整修订计划呈现后：“同意 继续执行”。
4. 主会话报告最小用例、十九项 GPU、两个 S2 和四卡冒烟通过，并报批“现有 30 seed、180 卡、GPU0、32 worker、预计 130 成功与 50 正常拒绝、约十五分钟生成及包装”；用户原话：“启动”。

第 4 条是计划 K9 的单独全量决定。最新既有结果锚点 `4231e656d45068b68d2d2aafb50b388d59544144`，本次独立开工审查：

```text
PLAN_CONSISTENCY_REVIEW=PASS base=4231e656d45068b68d2d2aafb50b388d59544144 findings=0 blocking=0
```

代码与恢复验证来源见 [首次建场结果](firstbuild-result.md)：最小三按钮位置误差 0、最大角误差 `4.4408920985e-16`，十九项与两个 S2 全过；四卡一成功三正常拒绝，保留卡规划结构与浮点零差异，infra=0。核心四个旧 FAILED 节点保持，无新增失败；官方源码、生产链路与依赖未改。旧 GPU FAIL 保留，不改写历史。

## 二、版本与干净工作区

本档案随 2.103Beta 提交并立即推送，然后核对 porcelain 为空；实际 Beta 完整 SHA 必须作为两个运行器的唯一参数，并与 `SOURCE_HEAD=` 日志逐字相同。源代码冻结于该 Beta，期间不再提交文档、规则或源码；无需制造新的代码改动来运行全量。结束后的 2.103 是独立结论提交，不能 squash、amend 或改写 Beta。

原功能合并 `e3979518`（2.102）以及首次场景单用例修补 `0bf3a27e`（2.102.3）均已推送并可解析；本次生产机制不改变。还原命令为 `git show <实际Beta完整SHA>:scripts/data-generation-newSeed/generate_dataset_newseed.py` 与对应 `src/robomme_xhard/` 文件；运行器本身仅在 artifacts，完整指纹与命令如下，不复制 bash/yaml 到 docs。

## 三、环境与资源

工作位置 `/data/hongzefu/robomme_benchmark_newtask-v3-MotionJepa1006`，分支 `newtask-v3-MotionJepa1006`，sled-vail 环境 B；SSH 四个别名、NFS、本机盘、两张 RTX 6000 Ada、uv 与 micromamba符合规则。全局并发配置32已存在，不将配置当作三十二个子代理并发实测。开工前 GPU0 为 1286 MiB / 46068 MiB、利用率 0%，本机盘可用约6.2T。

固定 GPU0，不换卡、不上集群。全量预算3600秒，包装预算1800秒，都是单次上限，不是自动重跑额度。v2 同样规模曾生成601.1秒、包装291秒，这仅供本次耗时参考。监控只持续读取日志，不新增高频 GPU 采样，不干预其他用户或任务进程。

## 四、输入与划分口径

母清单仅从 `artifacts/xhard/xhard-1012-swapv2/mother_seeds_all.json` 复制到新根，没有改字节。两份 SHA256 都为 `56a0381bb78485a7373f6446a4a0007679c0aff3e5a0c347ad3c16528200e278`，运行器起跑再核对该值；三任务各十个原条目，episode、seed、source_difficulty、rank均保持。

按官网顺序：2.3 VideoUnmaskSwap、2.4 ButtonUnmaskSwap、3.2 VideoRepick；每个母条目展开 mother、xhard12、xhard14、xhard16、xhard18、xhard20。没有新 seed，没有换 seed、补 seed，attempt固定0；本机没有官方 `data_0226`，不重建母清单，不声称核验了 HF revision。官方环境代码与本次输入来源都按仓库已有锚点只读引用。

## 五、参数与全部环境覆盖

|位置|本轮值|
|---|---|
|UV_CACHE_DIR|`/home/hongzefu/.cache/uv`|
|PYTHONUNBUFFERED|`1`|
|Python 环境|已有主 `.venv`，`uv run --no-sync`，不安装依赖|
|--env|`VideoUnmaskSwap,ButtonUnmaskSwap,VideoRepick`|
|--difficulty|`xhard12,xhard14,xhard16,xhard18,xhard20`|
|--mother-manifest|新根 `mother_seeds_all.json`|
|--with-mother|开启，增加三十张母卡|
|--gpus / --workers|`0` / `32`|
|--output-dir|新根 `full/`，起跑前不存在|
|恢复行为|既有基础设施同卡最多3次恢复；任务拒绝不重试，不改 seed/attempt；dup与infra会在验收暴露并判失败|

不加入精度、渲染、兼容或随机流覆盖；生成器按已有逻辑在 worker 导入前绑卡。剩余默认项由 Beta 锁定，不复制额外配置快照。

## 六、完整命令、顺序与会话清单

唯一全量启动命令：

```bash
tmux new-session -d -s xh-swapv3-full-1012 "bash /data/hongzefu/robomme_benchmark_newtask-v3-MotionJepa1006/artifacts/xhard/xhard-1012-swapv3/run_full.sh <实际Beta完整SHA>"
```

运行器内执行：

```bash
UV_CACHE_DIR=/home/hongzefu/.cache/uv PYTHONUNBUFFERED=1 timeout 3600s uv run --no-sync python scripts/data-generation-newSeed/generate_dataset_newseed.py --env VideoUnmaskSwap,ButtonUnmaskSwap,VideoRepick --difficulty xhard12,xhard14,xhard16,xhard18,xhard20 --mother-manifest artifacts/xhard/xhard-1012-swapv3/mother_seeds_all.json --with-mother --gpus 0 --workers 32 --output-dir artifacts/xhard/xhard-1012-swapv3/full
```

`run_full.sh` SHA256 为 `deab4308243dcf8b3da02bc453725065dc6052e0438bf214f2905fb1ef344156`；运行器核对 HEAD、干净工作区、母清单指纹、新日志和新目标。生成器预计 `EXIT_CODE=1`，因为五十张正常任务拒绝；这不等同于基础设施故障，也不能替代逐身份核对。主会话先核账本和预期数，再进入包装；若偏离即按失败流程留证、定位、一次独立对抗核查、交用户，不补跑。

包装唯一启动命令：

```bash
tmux new-session -d -s xh-swapv3-report-1012 "bash /data/hongzefu/robomme_benchmark_newtask-v3-MotionJepa1006/artifacts/xhard/xhard-1012-swapv3/run_report.sh <同一Beta完整SHA>"
```

包装运行器整体受 `timeout 1800s` 限制，按批准顺序执行：

```bash
UV_CACHE_DIR=/home/hongzefu/.cache/uv uv run --no-sync python -m robomme_xhard.tools.summarize --root artifacts/xhard/xhard-1012-swapv3/full --seeds artifacts/xhard/xhard-1012-swapv3/mother_seeds_all.json --out-md artifacts/xhard/xhard-1012-swapv3/report/summary.md --out-json artifacts/xhard/xhard-1012-swapv3/report/summary.json
UV_CACHE_DIR=/home/hongzefu/.cache/uv uv run --no-sync python -m robomme_xhard.tools.episode_strip_video --root artifacts/xhard/xhard-1012-swapv3/full --seeds artifacts/xhard/xhard-1012-swapv3/mother_seeds_all.json --out-dir artifacts/xhard/xhard-1012-swapv3/report/per_episode_strip
UV_CACHE_DIR=/home/hongzefu/.cache/uv uv run --no-sync python -m robomme_xhard.tools.swap_v2_report --v1 artifacts/xhard/xhard-1012-swapv2/full --v2 artifacts/xhard/xhard-1012-swapv3/full --seeds artifacts/xhard/xhard-1012-swapv3/mother_seeds_all.json --out-md artifacts/xhard/xhard-1012-swapv3/report/v2_vs_v3.md --out-json artifacts/xhard/xhard-1012-swapv3/report/v2_vs_v3.json
```

`run_report.sh` SHA256 为 `de9a81c7b08be65876dd0dc73989412edc6c2ab7d84a9df253c873444d3aaedb`，各阶段记录退出码，总退出码按实际记录；预期包装退出0。旧两根不作任何输出目标，新 report起跑前不存在。两个运行器均 `bash -n` 退出0，使用pipefail、无缓冲输出、tee和终止EXIT_CODE。

本轮唯一会话清单为 `xh-swapv3-full-1012`、`xh-swapv3-report-1012`，顺序启动；日志分别为 `artifacts/logs/xh-swapv3-full-1012.log`、`artifacts/logs/xh-swapv3-report-1012.log`。运行代理只按确定版本启动，60秒内核SOURCE_HEAD和精确tmux就绪后交回；主会话负责持续流式监听、预算与清理。巨大汇总JSON只输出简短监控摘要，完整原始日志仍保留，不靠反复 sleep 检查。

## 七、预期验收与失败处理

权威账目行只认 `swap_v2_report`：`XHARD_FULL_DERIVE=DONE expected=180 seen=180 missing=0 dup=0 unknown=0 ok=130 task_reject=50 infra=0`。逐卡身份要求 `V3_IDENTITY_MATCH=PASS cards=180 mismatches=0`；五类母seed要求 `SWAP_V3_KINDS_GATE=PASS seeds=30 pass=20 reject_kinds=6 reject_isolated=3 runtime_fail=1 mixed=0 expected_reject_kinds=6`；固定集合要求 `PLAN_UNCHANGED=PASS cards=105 expected=105 missing=0 diffs=0 float_tol=1e-9`，原结构逐位、浮点在批准容差内，新增边集单独核对。

汇总还须 `DIFFICULTY_LABEL=PASS files=130`、`XHARD_RECORD_NONEMPTY=PASS files=130`；视频须30支／180列／missing=0，逐文件非空、width3072、fps30且首帧版式目视检查；报告 `REPORT_V1V2=PASS seeds=30 rows=180`。全部数字逐个核对，不因工具打印PASS就放行。

原 `.v2_mark` 不重置，阶段末 v2文件数719/newer0；旧v1按既有sha清单复核426文件／mismatches0／extra0。任何身份或判据偏离都保留原FAIL，主会话找原因、独立代理一次对抗验证、交用户；不改代码、不换seed、不重试任务拒绝、不放宽。允许保存失败视频作证据，但不改变实际task_success或批次FAIL；不因有视频当任务成功。

## 八、结果回写与归档边界

成功完成全部验收后才写完整 `full-result.md` 的实测、用户决策、意外、结论和归档清单，并提交2.103立即push；失败则如实回写FAIL与根因，不把过程结束当作完整交付。records只存Git不能还原的清洗日志、账目/视频核验与判定数据；不归档bash/yaml/sbatch、权重或H5。数据与视频留artifacts；总索引随结果更新。Beta从第一阶段启动到包装验收结束始终冻结，不事后制造起跑版本。
