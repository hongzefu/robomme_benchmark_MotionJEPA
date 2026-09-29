# 单 GPU 评估 CPU 与常驻开销实测

## 目的与授权

用户原话依次为：「现在的simplememvla和framesample是怎么eval的 每次都分法是最快的形式吗 1cpu是否会造成等待 实测并且告诉我 可以用gl提交job 以现在的newtaskrelease v5为锚点」「如果我一次性分配 然后在单gpu串行跑是否更快」「再测一个带demo的」。用户选择 test-hard 和运行名 `eval-cpu-20260928`，明确批准整批 16 次。

预算为 2 任务（PickXtimes、VideoPlaceButton）×1 档（xhard1）×1 局（episode 0）×2 策略×3 CPU 档（1/2/4）=12 次，加 2 任务×1 档×1 局×2 策略的独立冷启动对照=4 次；reset 与轨迹尝试上限各 16 次，单 worker 串行，无自动重试、无递补。首次单任务单局作为最小冒烟，计入独立冷启动对照。基础设施失败停止受影响组，不为任务成功重跑。

用户另要求：「测完只保留小文件log 写入 大文件都删除 这个是一次性任务 把小文件和中介的经验写在 doc 注意写入的时候branch切回newtaskv5」。只清理本轮创建的快照、缓存、视频等，不删除已有模型、其他任务产物或共享环境。

后续用户要求：「你要给我完整的几轮 做作对比 现在的分发 和 一次性分配完 启动延迟有多少」。新增三轮比较及一次基础设施补跑已合并提出总41次预算，尚未获确认；未启动扩展。实际执行与未覆盖项见结果文档。

## 版本与运行环境

环境为 sled-vail 发起、GreatLakes `chaijy2/spgpu` 执行。冻结 benchmark 为请求开始时 `newtaskRelease-v5` 的 `ce3843b4fbe981307655570425ec39a3cdaad4a7`，用 `git archive` 导出至本轮 NFS 产物根的 `benchmark-ce3843`。后续分支移动不进入实验。开始时当前分支是同提交的 `codex/eval`；文档写入前重新核对，工作区已由其他操作切回 `newtaskRelease-v5`，已有删除 `0928-xhard0-native-hard-plan.md` 不属于本轮，不提交、不恢复。

SimpleMemVLA 来源为 `c359d3237bd7b2c468642ae4d102845dccc39fe4`，工作区干净，现成 uv 环境 `.venv-robomme`。ManiSkill editable 指向其 `third_party/ManiSkill`，提交 `07be6fbc66350ddca200abfb0a11b692f078f7fd`，工作区干净。权重使用已有 `checkpoints/simplememvla_robomme`，不拷贝、不下载。

framesample 来源为远端 `official-testhard-eval-0928-0137` 固定提交 `b22fc9c1ec73584870342c6335676a63dc417f9e`；权重为已有 `eval-out/mmevla-ckpt/perceptual-framesamp-modul/79999`。运行器兼容性在准备阶段单独核验，不将旧环境默认为相同。

本轮作业清单：`62268872` 为 1 GPU/4 CPU/24 GB/48 h，未跑仿真即取消；已知 SimpleMemVLA 历史 RSS 约 25.4 GiB，改提 `62268960`，1 GPU/4 CPU/32 GB/48 h，运行节点 `gl1527`。只释放本清单内作业。

## 执行与测量口径

产物根为 `/nfs/turbo/coe-chaijy-unreplicated/hongzefu/robomme_benchmark-newtask-gl/artifacts/eval-cpu-20260928`。共享盘 NFS，GPU A40；各 CPU 档在同一占位作业串行运行，`srun --overlap --exact --ntasks=1 --cpus-per-task=<1|2|4> --cpu-bind=cores --gpu_cmode=shared`。CPU affinity 必须记录，线程设置保持现成入口口径，不把增加算子线程混入 CPU 配额对照。

SimpleMemVLA 临时观察器只包装策略 `build_policy`/`generate_batch`、缓冲输入准备和客户端 `InProcSimPool.reset/step`，记录墙钟、进程 CPU 时间及调用次数，不修改或覆盖 benchmark 源码。正常终态独立报告 `task_success`；不同步数的整局耗时不能直接归因于速度，应对照每次调用和每步耗时。首次加载、预热与后续推理分开统计。无高频 GPU 查询。

任务在 detached tmux 中执行，使用 `pipefail`、`PYTHONUNBUFFERED=1`、`tee` 与 `EXIT_CODE`。会话清单：`ev-cpu0928-smoke`（SimpleMemVLA 冷启动 PickXtimes），其余会话启动时由结果文档记录。独立观察器每次写一条小 JSON，尚未单独测量观察器自身开销，属于比较的共同测量条件与限制。

实际会话完整清单为`ev-cpu0928-smoke`、`ev-cpu0928-framesmoke`、`ev-cpu0928-framecpu`，均在GreatLakes登录节点启动。首次SimpleMemVLA观察器逐次写小JSON；此后版本改为进程内缓存、退出统一落盘，避免每次RPC同步写NFS。同目录的`reproduce.md`保留一次性脚本正文。

历史占位与执行命令如下。JobID仅作证据，新跑必须申请新席位，不应照抄旧ID：

```bash
sbatch --parsable --account=chaijy2 --partition=spgpu --nodes=1 --ntasks-per-node=1 \
  --gres=gpu:1 --gpu_cmode=shared --cpus-per-task=4 --mem=32G --time=48:00:00 \
  --job-name=eval-cpu-0928-hold32 \
  --output=/nfs/turbo/coe-chaijy-unreplicated/hongzefu/robomme_benchmark-newtask-gl/artifacts/eval-cpu-20260928/%x-%j.log \
  --wrap='sleep infinity'

srun --jobid=62268960 --overlap --exact --ntasks=1 --cpus-per-task=4 --cpu-bind=cores --gpu_cmode=shared \
  /usr/bin/bash /nfs/turbo/coe-chaijy-unreplicated/hongzefu/robomme_benchmark-newtask-gl/artifacts/eval-cpu-20260928/run_simplemem.sh cold-pick PickXtimes/0

srun --jobid=62268960 --overlap --exact --ntasks=1 --cpus-per-task=4 --cpu-bind=cores --gpu_cmode=shared \
  /usr/bin/env PORT=19281 OUTPUT=/nfs/turbo/coe-chaijy-unreplicated/hongzefu/robomme_benchmark-newtask-gl/artifacts/eval-cpu-20260928/framesample-cold-pick \
  TASKS=PickXtimes ROUNDS=1 /usr/bin/bash \
  /nfs/turbo/coe-chaijy-unreplicated/hongzefu/robomme_benchmark-newtask-gl/artifacts/eval-cpu-20260928/framesample-prep/run_pair.sh

bash /nfs/turbo/coe-chaijy-unreplicated/hongzefu/robomme_benchmark-newtask-gl/artifacts/eval-cpu-20260928/framesample_remaining.sh
```

最后一个脚本在登录节点tmux中按cold-demo、1CPU双任务、2CPU双任务、4CPU双任务顺序执行；其内每个`srun`均完整退出后才进下一项，完整命令、timeout与守卫在`reproduce.md`。本轮未生成训练数据集，不写HDF5；framesample临时视频将在小记录归档后删除。

## 收尾

完整结果与小日志归入同目录 `records/`，正文写入 `result.md`。保留复现所需命令、版本、身份、耗时、错误与清理边界；临时脚本内容通过文档代码块留存，避免长期依赖本轮缓存。实验不是全任务性能证明，不宣称单 GPU 最优或所有任务 1 CPU 足够。
