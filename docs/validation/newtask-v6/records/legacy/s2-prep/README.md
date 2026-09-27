# V6 S2 演示探针预备资料

本目录只保存 S2 的执行清单、配置投影和确定性种子；本轮未运行 reset、演示、渲染或仿真，也未修改源码、测试、计划和账本。

## 一、覆盖口径

[NEWTASK_RELEASE_V6_PLAN.md](../../../NEWTASK_RELEASE_V6_PLAN.md) 定稿范围是 13 个梯度环境的 xhard1、xhard2、xhard3，加 16 个环境的 xhard4，共 55 格。S2 的“每格”按这 55 个 V6 新值格解释，不把原 easy、medium、hard 的 V1 对拍格混入本次演示探针。

- 常规 42 格各跑 2 次：84 次。
- VideoUnmaskSwap（VUS）、ButtonUnmaskSwap（BUS）、VideoRepick（VR）四个新值档共 12 格，各跑 4 次：48 次。
- MoveCube xhard4 跑 12 次：12 次，三种方法各 4 次。
- 合计 55 格、144 次固定尝试。每格尝试数和 seed 在 [manifest.json](manifest.json)；失败保留在尝试分母，并另报成功局数，不静默补抽。
- 可按环境、档位、次数和 seed 快速浏览 [cells.tsv](cells.tsv)。

计划只写“每格至少 2 局”，没有说明“局”指尝试数还是成功演示数，也没有给 reset 失败后的补抽规则。预备清单按确定的 seed 列表各尝试一次；如果结果少于目标成功数，单独报告短缺，不将 144 次尝试写成 144 个成功演示。

## 二、单任务 sampling_config

`v4_demo_probe --sampling-config` 读取一个任务的 `{decision,native}` 对象，不能直接接收含 16 个任务的 V6 snapshot。本目录 `sampling/` 已从 `scripts/configs/newtask-v6/sampling_config.json` 的 `.tasks[任务名]` 投影出 16 个单任务文件。重建投影的例子：

```bash
jq -c --arg task VideoUnmaskSwap '.tasks[$task]' \
  scripts/configs/newtask-v6/sampling_config.json \
  > artifacts/newtask-v6/s2-prep/sampling/VideoUnmaskSwap.json
```

启动 S2 前先通过计划 S1 的 V0，确认当前环境源码与该快照一致。`v4_reset_probe` 没有 `--sampling-config` 参数，VR reset 率备用测量只在 V0 通过后使用代码默认配置。

## 三、确定性种子与演示探针

常规格使用 V6 seed 公式：`offset + env_code*100000 + episode*100 + attempt`，四档 offset 为 xhard4=6,000,000、xhard1=8,000,000、xhard2=10,000,000、xhard3=12,000,000；环境编号沿用 `scripts/seed_layout.py::ALL_TASKS` 的一基编号。除 MoveCube 分支分层外，episode 从 0 起、attempt 固定为 0，完整列表已写在 manifest。

例如 VideoUnmaskSwap/xhard1 的四个 seed 是 `8500000,8500100,8500200,8500300`。执行命令：

```bash
uv run --no-sync python -m scripts.parity.v4_demo_probe \
  --task VideoUnmaskSwap --difficulty xhard1 \
  --seeds 8500000,8500100,8500200,8500300 --episode 9 \
  --sampling-config artifacts/newtask-v6/s2-prep/sampling/VideoUnmaskSwap.json \
  --out artifacts/newtask-v6/plan-probes/s2/VideoUnmaskSwap-xhard1
```

每格使用独立且此前不存在的 `--out` 目录，因为 `summary.jsonl` 以追加方式写入。必须显式传 `--difficulty`；当前 CLI 默认仍是旧名 `xhard`。`--episode 9` 令该探针关闭 z/xy failure recovery。seed 公式中的 episode 是种子编号，不是 `EpisodeJob.episode`；`v4_demo_probe` 把所给 seed 作为独立参数，并固定 `EpisodeJob.episode=9`。因此这些是可复现的 S2 探针身份，不应冒称为 S1 冻结 spec 身份。

`v4_demo_probe` 即使有局失败也可能以退出码 0 结束；必须读取每个 `summary.jsonl` 的 `ok`、`failure_class`、`error_type`，以目标尝试数为分母报告。HDF5/视频由 worker 写入独立输出目录，但 summary 不记录它们的路径，也不包含 MoveCube `way_idx`；报告应另核对产物清单，并对 MoveCube 附 seed 到分支的映射。

## 四、MoveCube 三分支 4/4/4

S1 的 `v4_specs draw` 在 reset 时把 MoveCube 分支写入 `spec.initializations.0.way_idx`。源码分支顺序是 0=`peg_push`、1=`gripper_push`、2=`grasp_putdown`。候选 episode 预设为 0–199，attempt=0 的基础 seed 为 7,400,000–7,419,900；发生 reset 重试时以 drafts 行中的实际 seed（含 attempt）为准。等 `artifacts/newtask-v6/s1-reset/xhard4/drafts.jsonl` 完成后：

1. 只取 `task=MoveCube`、`difficulty=xhard4`、`reset_ok=true` 的 drafts 行。
2. 按 `(episode, attempt, seed)` 升序，在每个 `way_idx` 内取前 4 行。
3. 用这 12 行的实际 `seed` 显式调用 MoveCube xhard4 的 `v4_demo_probe`；保留 `{seed,episode,attempt,way_idx,方法名}` 映射及每次成功/失败结果。
4. 若任一分支不足 4 条，按同一 V6 seed 规则扩充 MoveCube xhard4 reset 候选，再按相同排序选取；不以别的分支替代。

必须等 S1 的 xhard4 全环境 drafts 完成后再选择。该选择方案把三种分支实际覆盖写成可核对的 4/4/4，同时复用 S1 reset 规格，不用随机挑 12 局后猜测分支比例。

从完成的 S1 drafts 生成确定的分层 seed 文件并检查每支恰好 4 条：

```bash
jq -s '
  . as $all
  | if ($all[0].record != "header" or $all[0].difficulty != "xhard4" or
        ($all[0].tasks | index("MoveCube")) == null)
    then error("S1 header不是包含MoveCube的xhard4") else $all[1:] end
  | map(select(.record == "draft" and .task == "MoveCube" and
               .difficulty == "xhard4" and .reset_ok == true))
  | sort_by(.spec.initializations["0"].way_idx, .episode, .attempt, .seed)
  | group_by(.spec.initializations["0"].way_idx)
  | map({way_idx: .[0].spec.initializations["0"].way_idx,
         method: (["peg_push", "gripper_push", "grasp_putdown"][.[0].spec.initializations["0"].way_idx]),
         rows: (.[0:4] | map({episode, attempt, seed}))})
  | if length != 3 or any(.[]; (.rows | length) != 4)
    then error("MoveCube三分支reset成功样本不足4/4/4") else . end
' artifacts/newtask-v6/s1-reset/xhard4/drafts.jsonl \
  > artifacts/newtask-v6/s2-prep/movecube_seed_selection.json

jq -r '[.[].rows[].seed] | join(",")' \
  artifacts/newtask-v6/s2-prep/movecube_seed_selection.json
```

将上一步输出的 seed 列表传给 `v4_demo_probe --task MoveCube --difficulty xhard4 --episode 9`；用 `movecube_seed_selection.json` 保留分支映射。该命令依赖 S1 的 `drafts.jsonl` 已完整写入。

## 五、VideoRepick 七块 reset 率

主口径优先复用 S1 xhard4 `drafts.jsonl`：筛出所有 `VideoRepick/xhard4` 行，以 `reset_ok=true` 行数除以该环境全部尝试行数；将拒绝也计入分母，并列出 `fail_class`。这与 S1 同一份七块 reset 抽签数据一致，不额外消耗仿真。

可用以下命令从 S1 drafts 计算尝试数、成功数、失败数、接受率和失败类别：

```bash
jq -s '
  [.[] | select(.record == "draft" and .task == "VideoRepick" and .difficulty == "xhard4")] as $r
  | {attempts: ($r | length),
     reset_ok: ([$r[] | select(.reset_ok == true)] | length),
     reset_failed: ([$r[] | select(.reset_ok != true)] | length),
     acceptance_rate: (if ($r | length) == 0 then null
                       else ([$r[] | select(.reset_ok == true)] | length) / ($r | length) end),
     fail_class: ([$r[] | select(.reset_ok != true) | .fail_class]
                  | group_by(.) | map({class: .[0], count: length}))}
' artifacts/newtask-v6/s1-reset/xhard4/drafts.jsonl
```

计划未指定该 reset 率的样本数。若需要独立固定样本口径，备用文件 [videorepick_xhard4_reset_manifest.json](videorepick_xhard4_reset_manifest.json) 提供 200 次 xhard4、7 块 reset 尝试（episode 0–199，attempt 0，seed 显式固定），可在 V0 通过后运行：

```bash
uv run --no-sync python -m scripts.parity.v4_reset_probe probe \
  --manifest artifacts/newtask-v6/s2-prep/videorepick_xhard4_reset_manifest.json \
  --tasks VideoRepick \
  --out artifacts/newtask-v6/plan-probes/s2/videorepick-xhard4-reset-200.json
```

该备用结果报告 `ok/200`，逐条保留失败和错误类型；不重抽，不应用 recovery。若采用 S1 drafts 主口径和固定 200 次备用口径，两者要分别标明，不能拼成一个比例。

## 六、当前边界

本清单依据生成时的 V6 snapshot 和计划 SHA-256 制作，来源指纹记录在 `manifest.json`。本轮没有执行 S2，也没有形成 reset 率、演示成功率、视频验收或最终 S2 PASS 证据。S1 drafts 未完成前，MoveCube 的 12 个实际 seed 尚不能落定；这是按分支均衡选样必需的运行依赖。
