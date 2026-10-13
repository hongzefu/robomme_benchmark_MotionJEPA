# v3 全量完成：一百八十身份，一百三十成功、五十正常拒绝

## 一、一句话结论与指标

现有三十个母 seed、母档加五档的一百八十个身份全部交代清楚，没有缺项、重复、未知或基础设施失败。成功一百三十卡、正常任务拒绝五十卡，逐身份结果完全符合从 v2 推出的预期；一百零五张规划结构与浮点均无差异。三十支六列视频、180列及全部原定验收通过，没有换 seed、补卡或重试任务拒绝。

|官网编号|任务|母档成功|xhard 成功|正常拒绝|合计身份|
|---|---|---:|---:|---:|---:|
|2.3|VideoUnmaskSwap|10|40|10|60|
|2.4|ButtonUnmaskSwap|10|40|10|60|
|3.2|VideoRepick|10|20|30|60|
|合计|三个任务|30|100|50|180|

## 二、版本与代码状态

运行从干净 Beta `f6209f5d7cf83da85bae4141aad04e2e477666c3`（2.103Beta）开始，生成、包装和最终检查期间 HEAD 始终保持该 SHA，porcelain为空；两个运行器参数和 `SOURCE_HEAD=` 逐字一致。全部验收结束后才回写本结果并提交独立 2.103，Beta不改写、不合并。

本轮没有修改源码、配置、依赖或输入母清单。原 v3 实现与首次场景测试修补分别见 `e3979518`、`0bf3a27e`；十九项 GPU、S2 和四卡冒烟的实测见 [恢复结果](firstbuild-result.md)，旧失败记录也原样保留。正式全量开工前独立审查：

```text
PLAN_CONSISTENCY_REVIEW=PASS base=4231e656d45068b68d2d2aafb50b388d59544144 findings=0 blocking=0
```

## 三、启动与配置还原

完整命令、env覆盖、预算、指纹和参数见 [full-launch.md](full-launch.md)。还原源码入口可用：

```bash
git show f6209f5d7cf83da85bae4141aad04e2e477666c3:scripts/data-generation-newSeed/generate_dataset_newseed.py
git show f6209f5d7cf83da85bae4141aad04e2e477666c3:src/robomme_xhard/swap_plan.py
git show f6209f5d7cf83da85bae4141aad04e2e477666c3:src/robomme_xhard/tools/swap_v2_report.py
```

生成唯一尝试由运行代理在 `xh-swapv3-full-1012` 启动；完成账目核对后，包装唯一尝试在 `xh-swapv3-report-1012` 启动，按汇总 → 六列视频 → 权威对账顺序。主会话接管持续流式监听、预算与验收，不新增高频 GPU 查询、不修改运行参数或自动补跑。

## 四、数据集与划分口径

三任务各十个母条目只从 v2 复制，新旧母清单 SHA256 都为 `56a0381bb78485a7373f6446a4a0007679c0aff3e5a0c347ad3c16528200e278`；所有 episode、seed、rank、source_difficulty 和 attempt=0 保持。母档为两种 Swap 的 hard、VideoRepick 的 medium；派生档为 xhard12/14/16/18/20。本次没有下载或重新生成母清单，不声称核验了官方 HF revision。

全量数据在 `artifacts/xhard/xhard-1012-swapv3/full/`，共304个文件，磁盘占用约65GiB；报告及三十支视频在新 `report/`，约295MiB。以上体积来自 `du -sh`，不是成功样本数；失败证据也保留，不能用文件数替代180身份账目。

## 五、关键参数与不变项

本机 GPU0、32 worker，`--with-mother`、五档及原母清单，生成输出新 `full/`。环境只显式设置 `UV_CACHE_DIR=/home/hongzefu/.cache/uv`、`PYTHONUNBUFFERED=1`，使用已有主 `.venv` 与 `uv run --no-sync`。母 seed不换、不补，任务拒绝不重试；原基础设施有限恢复机制未实际触发，dup与infra均0。

新准入口径仍是 G 的可行无序边数至少3，不是每个实际交换序列必须用三种槽对；通过者的旧规划字段结构逐位、浮点容差 `1e-9` 米，新边证据单独核对。官方源码、两个引入文件、生成器、三个子类与依赖没有本轮改动。

## 六、硬件、耗时与预算

sled-vail 环境 B、本机 NVMe、RTX 6000 Ada GPU0。生成启动为2026-10-13 00:31:36（美国东部时间），程序报告465.7秒，约7.8分钟，退出1；包装00:43:15启动，日志起始时间到最后写入约227.9秒，约3.8分钟，退出0。主要生成和包装时间合计约11.6分钟；人工核对与阶段移交时间另计。

生成预算3600秒、包装整体1800秒，两者均未超预算。程序 `throughput_ep_per_min=16.75` 是成功卡吞吐，不是全部身份处理速度；`peak_rss_mb=7345.5` 是成功 worker 报告的进程峰值最大值，不是32个 worker的聚合内存。未采集稳态GPU利用率，不给GPU吃满结论。

## 七、构建过程行为与实际剔除

所有身份只有一次任务尝试，attempt=0。新三边闸门拒绝六个母 seed 的三十张 xhard 卡：按官网顺序为 VideoUnmaskSwap6500/9300、ButtonUnmaskSwap8500、VideoRepick10800/12400/13200。原孤立槽拒绝三 seed的十五张卡；VideoRepick12800五档继续在运行期拒绝，母档成功。阶段中记录的规划器内部 `screw plan failed` 搜索消息没有变成额外身份失败，最终账本与预期相同，没有据此换 seed 或重跑。

生成器终止 `EXIT_CODE=1` 是五十张正常任务拒绝的约定行为；独立成功字段仍为130张 `task_success=1`、50张 `task_success=0`，不因有报告或视频而把拒绝卡记成成功。

## 八、完整验收与视频复核

以下权威账目与比较行来自 `swap_v2_report`，不使用 `summarize` 的同名粗统计行替代身份对账：

```text
XHARD_FULL_DERIVE=DONE expected=180 seen=180 missing=0 dup=0 unknown=0 ok=130 task_reject=50 infra=0
REPORT_V1V2=PASS seeds=30 rows=180
V3_IDENTITY_MATCH=PASS cards=180 mismatches=0
SWAP_V3_KINDS_GATE=PASS seeds=30 pass=20 reject_kinds=6 reject_isolated=3 runtime_fail=1 mixed=0 expected_reject_kinds=6
PLAN_UNCHANGED=PASS cards=105 expected=105 missing=0 diffs=0 float_tol=1e-9
DIFFICULTY_LABEL=PASS files=130
XHARD_RECORD_NONEMPTY=PASS files=130
EPISODE_STRIP_VIDEO=PASS videos=30 columns=180 missing=0
FULL_VIDEO_METADATA=PASS videos=30 width=3072 fps=30
VIDEO_FIRST_FRAME_REVIEW=PASS videos=30 columns=180
OLD_RUN_INTACT=PASS files=426 mismatches=0 extra=0
V2_ROOT_UNTOUCHED=PASS files=719 newer=0
```

一百零五张比较包含12800五张失败卡，实际 `max_float_delta=0.0`。主会话另独立读取报告JSON逐项断言，确认180身份、五类母seed、105集合和H5/视频数全部符合；输出在 `records/full_validation.json`。两旧根复核中，v1完整哈希426条均OK、退出0，文件数仍426；v2仍719文件、原标记之后更新0，没有重置标记。

三十支视频逐文件 ffprobe 和首帧解码通过，文件非空、宽3072、fps30、时长和帧数正值。主会话已目视三任务各十支的首帧六列版式，六列对齐，头部、失败灰色占位、红色演示框及文字正常，未发现跨栏或重叠。复核图在新根 `video-previews/`，按五支视频的实际行高分片；未改原视频。可复现验收入口 `validate_full_videos.py` 由 uv执行，退出0；输出目录与结果排他创建，再读结果即可，不能覆盖运行证据重复起跑。

## 九、用户决策原话

完整开工消息链与已定参数见 `full-launch.md`。本轮关键授权原话是“启动”，对应主会话提出的现有30seed、180卡、GPU0/32worker、预计130成功/50拒绝及生成/包装范围。沿用用户此前“不做任何的换seed和上一版一样只对于现有SED做一次生成的检查。”及失败视频可以保存、不能记成功的决定。本轮没有范围或接口裁决变更。

## 十、意外与处置

正式生成与包装没有出现基础设施故障、身份偏离、规划差异或超预算。复核辅助拼图最初使用普通sans字体，附加标题的“母”字缺字，改用与视频相同的 NotoSansCJK 字体并重新目视；只改自制复核图，原视频未动。

缩小拼图曾让11602的英文指令段落看似为空，主会话重新读新旧 H5 `episode_26/setup/task_goal`、查看新旧原分辨率首帧，确认字段和显示都完整；这是复核误读，不是数据或视频缺失，未重编码视频或修改输入。图与文字按核实后的事实报告，不把误读扩大为生产故障。

## 十一、结论、限制与下一步

本次既定180卡检查与包装全部完成，通过所有原判据；数据约65GiB和三十支六列视频可用于本次批准的后续工作。只完成本计划的三个任务、三十个母 seed，不扩大为十六任务全库验收，也未启动训练或HF上传。

规划一致不等于 H5 或视频字节一致；首帧目视与视频元数据不替代全段逐帧对拍。口径甲仍允许少数低档实际只用两种槽对。当前没有待修复项，没有继续生成或补 seed 的自动动作，下一步由用户决定数据使用方式。

## 十二、归档与产物清单

`records/` 新增全量/包装/v1校验三份清洗日志、权威判定行文本及六个实测JSON：`full_raw_accounting.json`、`full_validation.json`、`full_video_validation.json`、`video_visual_review.json`、`v2_vs_v3.json`、`full_inventory.json`。全量日志约53.7MB，归档为 `xh-swapv3-full-1012.summary.log.gz`，gzip解压与清洗后字节完全相同；`gzip -dc` 即可读取，不删减汇总JSON或逐步证据。每份日志保留一个终止EXIT_CODE，合计三条；去除tqdm中间态与行尾空白，原始日志仍在artifacts。记录足以核查各具名闸门，不复制bash/yaml/sbatch、H5、视频或权重进Git。

永久本轮产物根为 `artifacts/xhard/xhard-1012-swapv3/`，重点目录为 `full/`、`report/`、`video-previews/`。两个本轮tmux均正常结束，精确会话检查返回1，无需强杀；其他会话不动。Beta锚点在全部验收结束前始终不变，结果提交2.103完成后立即push，工作区不得残留ahead。
