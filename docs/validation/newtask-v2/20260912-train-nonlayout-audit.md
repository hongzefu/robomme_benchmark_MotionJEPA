# 当前生成与原始训练种子的非布局差异审计

结论：**现行 07 生成不能描述为「原始训练任务只换了布局」**。物体数量、目标组合、动作序列分布、演示数据、难度覆盖及失败筛选均有非布局变化。已用代码反例和现存 HDF5 验证这一结论；没有重新运行仿真，也没有把历史原值对拍当成本轮全量一致性证明。

## 比较口径

- 用户原话：「对抗验证 这一版本的生成 除了环境的布局有所不同外」「其他和 https://github.com/hongzefu/robomme_benchmark_MotionJEPA/tree/dataset-gen-NewSeed 生成原始的train seed 有什么区别」。
- 工作副本：`/data/hongzefu/robomme_benchmark_MotionJEPANewTask`，当前代码锚点 `c0e7f04`，分支 `newtask-v2`。
- [目标分支](https://github.com/hongzefu/robomme_benchmark_MotionJEPA/tree/dataset-gen-NewSeed)：本轮 `git ls-remote --heads origin dataset-gen-NewSeed` 确认是 `3a5951a834ea014f63724647ab0bc091eb9f109d`，与本地远端引用一致。网页访问失败，比较依据为远端查询和该 SHA 的 Git 对象。
- 实际产物：`artifacts/injection/20260911-contract-v3-07/`。`feasibility/P01x20/run_parameters.json` 记录 `seed_layout=train`、`max_attempts=1`、`episode_timeout_s=600`、`binfill_demo=true`，两卡共 40 个 worker。
- 必须区分两个模式：当前生成器不传 `--episode-specs`、不传 `--binfill-demo` 的原生路径，以及 07 显式启用规格和演示转换的路径。下述主要结论针对 07；末节单列原生路径的适用边界。
- 原分支同时包含 `data-generation-newSeed/generate_dataset_newseed.py` 的公式种子生成和 `data-generation/generate_dataset.py` 的固定 train metadata 复现。公式中的 `train` 不等于逐条采用 metadata 已保存的成功种子。

## 一、逐环境的非布局差异

### BinFill：块数、目标色和整条演示都变了

旧版 `BinFill::config_easy/config_medium/config_hard` 的生成总数分别为 **4～6、8～10、10～12**。当前源码关闭注入时仍保留这些值，但 [契约 v3](../../../scripts/configs/newtask-v2/injection_contract_v3.json) 的 `overrides` 将 07 中、高档改为 **6～8、8～10**，每档比旧版少两块。不能仅检查 `native_sampling.json` 就下结论，因为该快照仍是原值，实际规格还有契约覆盖。

07 三份 BinFill 规格各 100 条，直接数 `layout.cubes` 得到：easy 的 4/5/6 块分别 34/33/33 条；medium 的 6/7/8 块分别 34/33/33 条；hard 的 8/9/10 块分别 34/33/33 条。

目标规则也改变：旧版允许选中的目标颜色分到 0 个投入量；当前 `target_count_rule_override.contract.rule=each_target_at_least_one`，每个选中的目标颜色至少投入一块。07 目标色池内零目标记录数为 0。这不意味着所有场上颜色都要投入；未选为目标的颜色仍可为 0。消费锚点是 [规格生成](../../../scripts/injection/specs.py) 的 `_binfill_group` 与 [环境](../../../src/robomme/robomme_env/BinFill.py) 的 `_load_scene`。

此外，`dynamic`、各色方块数、创建顺序、执行时颜色遍历顺序均由规格冻结，不能再用相同 seed 推断它们与旧版逐条相同。

**最直接的数据反例是模拟演示。** [生成入口](../../../scripts/generate_dataset_newseed.py) 的 `_worker` 在录像器 `close()` 后调用 `_binfill_demo_deliverable`：

```text
原生：实际轨迹 N 帧
07： 同一轨迹复制 N 帧 + 原轨迹 N 帧
      is_video_demo=True    原标志
      is_completed=False
```

`_binfill_duplicate_h5` 复制前半的动作、观察、状态及其余信息，只改上述两个标志；没有重新仿真一次演示。`_binfill_duplicate_video` 将前半视频加 10 像素红框，并对整条视频重新编码，后半视频像素也不再具有与原直出视频逐位一致的保证。HDF5 图像本身没有叠加这个视频红框。

07 成功 BinFill 共 **86 条**，全部转换为两倍长度。本轮对 `BinFill/easy/episode_0/seed4000` 的全部 678 对帧进行了实读：最终 **1356 帧**，除两种改写标志外的 **12882 个 dataset、444664566 字节，差异 0**。分类为 action 2712、info 3390、obs 6780 个 dataset；前半 678 帧全是演示且均未完成，后半均非演示、末帧完成。检查耗时 4.163 秒。

这会改变训练序列长度、演示标志和上下文内容；前半直接包含后半执行的同一套动作与画面。不能把该复制片段当成独立仿真的原生示范。

### RouteStick：动作序列分布也改了

普通档的段数范围仍为 easy **2～3**、medium **4～5**、hard **4～7**；新增 xhard 为 **8～10**，允许回退。但路径节点、段数、每段绕行方向、障碍柱颜色都来自外部规格。

关键反例：旧版 `RouteStick::task_generator` 每段独立用 `torch.rand(...).item() < 0.5` 决定绕行方向，任意给定的连续三段全同向的概率是 **1/4**。当前 `specs.py::_routestick_group` 把 `direction_usage` 放在整组 episode 循环之外，调用 [sampling.py](../../../scripts/injection/sampling.py) 的 `balanced_choice`，优先选择用得最少的方向。

从整组第 0 段起固定分对 `(0,1)、(2,3)…`，每对一定一顺一逆，因此连续三段同向不可能出现。不是任意相邻两段都相反，跨配对边界仍可出现两段同向。07 四档共 **400 条冻结规格**实查，连续三段同向数为 **0**。路线边也按跨 episode 使用次数优先补少。

因此这里不只是改变位置或有限样本比例，而是排除了原任务允许的一部分动作序列，并引入 episode 间的配额依赖。

### VideoUnmaskSwap：普通档次数范围保留，但具体任务重新取值

普通档仍为 easy **3 容器、1～2 次交换、1～2 次拾取**；medium **4 容器、1～2 次交换、1 次拾取**；hard **4 容器、2～3 次交换、2 次拾取**。新增 xhard 为 **4 容器、4～5 次交换、2 次拾取**。

[环境](../../../src/robomme/robomme_env/VideoUnmaskSwap.py) 的 `__init__`、`_load_scene`、`_refresh_swap_schedule` 在开启规格时读取冻结的次数、容器颜色、藏物／拾取映射和交换发起者。普通档的范围相同，不代表相同 seed 对应同一个目标或同一串事件。xhard 的发起者按前三个循环，4～5 次形如 `a,b,c,a,b`。

四容器档只在前三个容器藏物、`bin_3` 为空，是旧代码就有的行为，本轮不将其列为新增差异。

### VideoRepick：旧 hard 整组缺席，xhard 采用另一套机制

easy／medium 仍是 **3 个同色方块**，交换次数分别 **1～2、2～3**，重复抓放 **1～3** 次；具体颜色、目标方块、重复次数及交换发起者改为规格给定。

旧 hard 是 **5 轮、最多 15 个混色方块、0 次交换**的任务，**07 没有生成这组**。新增 xhard 是 **3 个同色方块、4～5 次交换、重复抓放 1～3 次**，沿 medium 的机制增加交换，不能看成旧 hard 的连续升级。[VideoRepick.py](../../../src/robomme/robomme_env/VideoRepick.py) 的 `config_xhard`、`_load_scene` 和 07 的 `manifest.json::groups` 共同确定这一差异。

## 二、种子、采样、失败与交付口径

### 相同 train 名称不能保证相同样本

[seed_layout.py](../../../scripts/seed_layout.py) 保留公式：`seed = env_code * 1000 + episode * 100 + attempt`。07 每条 `attempt=0`；任务规格则由 `generator_seed=20260909` 派生独立随机流，并经离散配额、连续分层、几何筛选后冻结。物体、目标和路线因此不再由这个环境 seed 单独决定。

明确的旧 metadata 反例是 BinFill ep3：目标提交的 `src/robomme/env_metadata/train/record_dataset_BinFill_metadata.json` 保存 **seed4301、hard**；07 则使用 **seed4300**，且 easy／medium／hard 都各有一条 ep3。旧 NewSeed 入口原本也会从 attempt0 开始，失败后加 attempt、换 seed；若要逐字复现旧 train 的成功 seed，须读取固定 metadata，而不是只用基础公式。

难度抽样从旧默认 `211`（easy、easy、medium、hard）循环改为按任务／难度单独成组。07 冻结 **14×100=1400** 条规格，实跑每组 episode0～29，共 **420** 条。`run_parameters.json` 虽仍显示默认 `episodes=100`、`difficulty_ratio=211`，清单模式实际由 `episode_spec_groups` 决定任务、难度和 episode；不能将这些未使用的默认字段当成有效运行口径。

目标分支中 BinFill、RouteStick、VideoRepick 的 train metadata 各 100 条，难度 50/25/25；VideoUnmaskSwap 已扩至 400 条，难度 200/100/100。07 也只生成四任务，不覆盖目标分支的全部 16 任务。

### 未冻结的随机失败抓取也没有同 seed 保证

有规格时，三个抓取任务跳过部分原 `torch` 随机抽样，随后仍用对应随机流调用 `task4recovery.py::inject_fail_grasp`，随机选一个抓取任务注入失败。因此代码没有保持这部分随机流位置对应关系。

当前 `EpisodeJob::recovery_mode` 与旧版相同：ep0～2 为 `z`，ep3～5 为 `xy`，后续不自动开启恢复。`_worker` 为前六条开启 `robomme_failure_recovery`；规格不会自动冻结被选中的失败抓取位置。**本轮没有实测新旧失败注入位置是否不同，只能判定不具备保持一致的保证。** 在 07 前六条的模式由入口明确给定，不能说它们会随机换成另一种模式。

### 新增拒绝条件与超时改变最终保留集合

两个视频环境在启用规格时增加 `_check_state_readonly`、`_verify_swap_binding`、`_check_swap_sweep_from_actual` 及交换期间的子步检查。碰撞／接触、无法证明连续路径安全或实际交换搭档与规格不符，均会拒绝该条。检查只读实际状态，不修改物理轨迹，但增加了旧生成器没有的失败条件。

进程池从 `ProcessPoolExecutor` 换为 `pebble`，新增默认 **600 秒**单条墙钟上限；07 设置 `max_attempts=1`，失败后不换 seed、不补样本。默认原生模式仍可按 `max_attempts` 重试，但同样受到新增墙钟上限约束。

07 实际 **420 条结果、410 个成功 HDF5、5 条规划失败、5 条超时**；视频 complete415、no_close5。`FEASIBILITY=PASS` 表示执行和分类达到该报告判据，不代表420条都成功，更不代表与旧训练数据一致。

数轴另排除 VideoUnmaskSwap/xhard ep5：1312 帧、最长子段828帧。本轮实读该 HDF5，文件仍在且末帧完成；排除只作用于采样窗口统计，**没有从原始生成数据删除**。当前窗口统计为409条，成功 HDF5 为410条，不能混用这两个分母。

## 三、哪些机制没有发现改变

本轮 Git 与 AST 核验得到：

- 生成入口 `_planner_classes`、`_execute_tasks`、`_write_metadata` 与目标 SHA 的对应函数 AST 完全相同。仍调用原 `gym.make`、`task_list`、求解器、`step`、`evaluate` 与录像器。
- 四环境的 `_default_sensor_configs`、`_default_human_render_camera_configs`、`_load_agent`、`_get_obs_extra`、`evaluate` 与奖励方法 AST 相同；BinFill、RouteStick 的 `step` 也相同。
- `RecordWrapper.py`、机器人、控制器、求解器、资产文件以及 `statechange.py::swap_flat_two_lane` 没有改动。原 `NO RECORD` 跳过规则和不补 reset 帧保留；BinFill 复制发生在生成入口的成品处理阶段。
- 环境构造参数仍为 `obs_mode=rgb+depth+segmentation`、`control_mode=pd_joint_pos`、`render_mode=rgb_array`、`reward_mode=dense`；只在显式启用时增加 `sampling_config`／`episode_spec`。
- 解析两份 `uv.lock` 的包名与版本后，仅新增 `pebble==5.2.2`，原锁定包版本没有变化。锁文件字面变化多来自上传时间元数据，不能据此声称物理库升级。

这些是不变机制的代码证据；参数和动作输入已经改变时，相同求解器不意味着会输出相同轨迹、长度或图像。

## 四、历史对拍能证明到哪里

[原值动作冻结对拍](20260909-actions-v3/README.md) 的基线是 `94449db`。本轮核查 `94449db..3a5951a` 的 `src`、旧 `data-generation-newSeed`、`pyproject.toml`、`uv.lock`，无差异，因此旧基线与目标分支在这部分代码上可连接。但15格原值结果证明的是当时的默认／原值配置／原值冻结路径，不能迁移到07的新值分布、xhard、BinFill复制及新调度。

[04报告](20260910-new-values-04/README.md) 的 `DEFAULT_PARITY` 只比较关闭注入的四任务easy／medium共8例，基线 `446455b` 到当时实现；其串并行内容比较也属于04。07报告没有 `DEFAULT_PARITY`、`SERIAL_REFERENCE`、`PARALLEL_CONTENT` 判定。

旧 `artifacts/` 的原始仿真与视频证据已在10.67清理；Git中的轻量报告仍可读，不能假称旧大文件仍可直接复核。当前07的HDF5和视频保留。

当前版本若不传 `--episode-specs`、不传 `--binfill-demo`，使用原 easy／medium／hard，源码保留原任务参数与原随机路径。本轮未发现上述非布局规格变化在该模式启用，但600秒上限和进程池已经改变，且**没有对当前 HEAD 重跑与旧版的仿真逐帧验证**，不能给整个默认模式标记逐位一致。

## 五、本轮验证与复现

以下命令均在工作副本根目录执行，读取本地盘数据；没有生产环境覆盖或修改。

### 代码与基线

```bash
git ls-remote --heads origin dataset-gen-NewSeed
git diff --name-status 3a5951a834ea014f63724647ab0bc091eb9f109d c0e7f04 -- src
git diff --exit-code 94449db0a068a6b454b55a13ebd48f0394d89cc8 3a5951a834ea014f63724647ab0bc091eb9f109d -- src scripts/data-generation-newSeed pyproject.toml uv.lock
git show 3a5951a834ea014f63724647ab0bc091eb9f109d:src/robomme/env_metadata/train/record_dataset_BinFill_metadata.json
```

远端与旧基线连接核验均退出0；`--name-status` 列出四环境、`difficulty.py`、`object_generation.py`、`route.py` 以及新增 `bin_collision.py`，共8文件。入口函数通过 `ast.parse`、`ast.dump(..., include_attributes=False)` 比较；锁文件通过 `tomllib.loads` 比较包名／版本集合。

### 方向反例与BinFill规格

```bash
jq -s '[.[].episodes[] | .actions.directions as $d | range(0; ($d|length)-2) | select($d[.] == $d[.+1] and $d[.] == $d[.+2])] | length' artifacts/injection/20260911-contract-v3-07/specs/RouteStick/{easy,medium,hard,xhard}.json
jq '[.episodes[] | .layout.cubes | length] | group_by(.) | map({blocks:.[0], episodes:length})' artifacts/injection/20260911-contract-v3-07/specs/BinFill/{easy,medium,hard}.json
```

第一条输出0；第二条得到正文中的三组34/33/33配额。

### BinFill整条重复实读

```bash
command -v uv
PYTHONDONTWRITEBYTECODE=1 uv run --no-sync python - <<'PY'
from pathlib import Path
import h5py
import numpy as np

path = Path('artifacts/injection/20260911-contract-v3-07/feasibility/P01x20/BinFill/easy/hdf5_files/BinFill_ep0_seed4000.h5')
compared = compared_bytes = 0
with h5py.File(path, 'r') as handle:
    episode = handle['episode_0']
    total = sum(name.startswith('timestep_') for name in episode)
    assert total % 2 == 0
    n = total // 2
    for index in range(n):
        left = episode[f'timestep_{index}']
        right = episode[f'timestep_{index+n}']
        assert bool(left['info/is_video_demo'][()])
        assert not bool(left['info/is_completed'][()])
        assert not bool(right['info/is_video_demo'][()])
        fields = []
        right_fields = []
        left.visititems(lambda name, value: fields.append(name) if isinstance(value, h5py.Dataset) else None)
        right.visititems(lambda name, value: right_fields.append(name) if isinstance(value, h5py.Dataset) else None)
        assert fields == right_fields
        for name in fields:
            if name in ('info/is_video_demo', 'info/is_completed'):
                continue
            a, b = np.asarray(left[name][()]), np.asarray(right[name][()])
            assert a.dtype == b.dtype and a.shape == b.shape
            # 原动作含NaN，数值相等会误报；数值数组比较原始字节。
            assert np.array_equal(a, b) if a.dtype.kind == 'O' else a.tobytes() == b.tobytes()
            compared += 1
            compared_bytes += a.nbytes
    assert bool(episode[f'timestep_{total-1}/info/is_completed'][()])
print(f'BINFILL_ALL_FIELDS=PASS N={n} timesteps={total} compared_datasets={compared} compared_bytes={compared_bytes} mismatches=0')
PY
```

实测退出0：`BINFILL_ALL_FIELDS=PASS N=678 timesteps=1356 compared_datasets=12882 compared_bytes=444664566 mismatches=0`。这是07自身复制的证明，不是新旧仿真对拍。

### 定向测试

```bash
command -v uv && timeout 240s uv run --no-sync python -m pytest tests/lightweight/test_seed_layout.py tests/lightweight/test_binfill_demo_duplicate.py tests/lightweight/test_episode_timeout.py tests/lightweight/test_native_sampling_config.py -q
```

实测退出0：`41 passed in 4.02s`。测试覆盖种子公式、复制转换、单条超时和原值配置；不宣称覆盖整条仿真或新旧全量同种子一致性。

最终判定：

```text
NON_LAYOUT_EQUIVALENCE=FAIL scope=07
BINFILL_ALL_FIELDS=PASS compared_datasets=12882 mismatches=0
ROUTE_THREE_SAME_DIRECTION=0 specs=400
SHORT_TESTS=PASS passed=41 failed=0
CURRENT_DEFAULT_PARITY=NOT_RUN
```

本轮只新增本报告并更新必要账本，不改变任何生成行为。若后续目标是「只改布局，其余逐条对应」，需要另行确定物体数量／目标／动作／恢复注入／演示／seed与失败策略的保留边界；本审计不把这些潜在修订当成当前实施授权。
