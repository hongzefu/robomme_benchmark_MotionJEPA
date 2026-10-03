待办清单与代码测试维护方案（2026-10-03）

> 本轮只细化本文件，不实施维护、不启动生成或评估。保留并行会话在 12.349 补入的已完成项、资源清理与暂不处理项；资源清理仍由 [资源清理方案](1003-resource-cleanup-plan.md) 单独管理。
>
> 用户本轮原话：「细化该方案，我还需要做对拍，就是说改之前改之后，生成和test evaluation需要是一致的。」下文将原维护清单细化为可执行、可审查的前后对拍合同。已有维护事项授权保留；新增对拍工具及实跑规模须在实施前一次定清，本文不是生成、reset、评估或集群启动授权。
>
> 规划代码锚点 `PLAN_BASE=e1be125cde7350223ba6b5c6f13a814e82b81a51`，工作副本 `/data/hongzefu/robomme_benchmark_MotionJEPANewTask`，当前分支 `newtaskRelease-taskV9`。编写期间其他会话提交了 12.349 等文档更新，本文保留其内容，不纳入其他方案的实施。后续另冻结完整 `BEFORE_SHA/AFTER_SHA/HARNESS_SHA`，不拿移动的 HEAD 作基线；提交编号沿用 `<大>.<小>[.<修订>] 中文描述`。
>
> 外部锚点：官方环境 `1fadc0ec50316b60ddcfd8e82ac62ef2b70c18f9`，官方生成编排 `d53f21a7947d2d8daf6e3e8bad9f59b4f89a77fa`，ManiSkill 声明锁定 `07be6fbc66350ddca200abfb0a11b692f078f7fd`。第三方 gitlink：SimpleMemVLA `c564c17d276d7294200122b286c21901a3bfb99f`、MME-VLA `ecf086c3be7c2223167d9bb2f6ef1f0a6e24353b`；不读取或带入其在途修改，运行前另核安装实物及资产指纹。

事项背景见 [未定事项清单](docs/1002-pending-decisions.md)。交付数据集已冻结：下文 V9 逐格乘式合计 16 任务各 50 局，正式 HDF5 与五份规格全部字节均不得修改。

# 第一部分（给人看）

## 已完成

- [x] 生成对拍的事实与结论成文：[`docs/1003-generation-parity-reproducibility.md`](docs/1003-generation-parity-reproducibility.md)（12.346）
- [x] `.gitignore` 忽略 `runs/` 与 mp4、mkv、h5 等媒体文件（12.348）
- [x] 资源清理方案成文：[`1003-resource-cleanup-plan.md`](1003-resource-cleanup-plan.md)（12.348）

## 一、资源清理（等用户说「执行」）

- [ ] 算 V9 交付集 sha 基线
- [ ] 搬出四样小件（官方 xhard0 h5、V7／V8 对拍逐局记录、权重锁、V8 站点目录）
- [ ] 停 4 个旧站点（8060、8070、8080、8081）
- [ ] 删本机 9 个历史目录
- [ ] 删 NFS 19 个历史目录
- [ ] 验收（sha 不变、无断链、8082 可用）并写留档
- [ ] 待定清单 F1、F3、F4、B4 写结案

## 二、核心短测（用户已批准可改）

- [ ] 修掉 6 个长期失败（C1）
- [ ] 拆出 5 分钟内能跑完的核心集，其余标为慢测（C2-1）
- [ ] 清理 V7、V8 的旧用例与只服务它们的夹具（C2-3、C2-4）
- [ ] 改正名不副实的文件名与函数名（C2-5）
- [ ] 合并重复断言（C2-6）
- [ ] 收窄 pytest 收集范围，不扫 `third_party/`（C2-7）
- [ ] 补 xhard0 开关关闭时的两条路径测试（C2-9）

## 三、步数上限表 `TIER_MAX_STEPS`（用户已批准可改）

- [ ] 定去留：保留、拉平成全 1600，或删表改单常量（B5）
- [ ] 按结论改代码、测试与 README

## 四、小修（用户已批准可改）

- [ ] 冻结脚本 `_freeze.py` 的档位预检（G1）
- [ ] V8 评估脚本的收尾逻辑与重启计数（D3）
- [ ] xhard0 退出 test-hard 后，站点常量 `XHARD0_PER_TASK` 与身份文件导出跟进（B6）
- [ ] `export_eval_identities.py` 的过时说明文字（C2-9）

## 五、收尾

- [ ] 更新 `AGENTS.md` 里核心短测的命令与口径
- [ ] 待定清单 A1、A5（生成对拍）等用户说结案
- [ ] 待定清单其余已办条目写结案

## 暂不处理（用户 2026-10-03 指示）

- 站点相关（B1、F2）
- MME 评估对拍（A3、A4）
- 未开工的 Oracle 子目标评估
- HuggingFace 上传、分支与 worktree 清理

## 六、维护方案总览与已定口径

一句话方案：先冻结维护前代码、身份和输入，采集完整基线，再维护测试与外围工具，最后以同一输入对拍维护后生成与评估，分别报告文件字节、内容、数值和行为是否一致。

1. **资产不变和运行一致分别验收。** 冻结交付 HDF5 不动，并不证明新代码重新生成的结果相同。新生成只写独立对拍目录（第八节）。
2. **生成与评估分别验收。** 生成 HDF5 相同、reset 相同、成功率相同，都不能代替完整 evaluation 的逐步比较（第九节）。
3. **覆盖官方 `test`、默认 `test-hard` 与开启 xhard0 的兼容配置。** 三套身份、局号与上限分开记录（第七、九节）。
4. **确定性字段严格零差异；不替用户放宽噪声判据。** 默认完整 A/B 比较输出严格结论。另一个 [噪声基线方案](1003-noise-baseline-plan.md) 管理重复运行、阈值标定及真实模型噪声；其尚未实施/批准的阈值不是本维护的现成放行依据。未来若采用经确认的冻结噪声合同，单列“噪声范围内”，不能改称“逐字节一致”（第八节）。
5. **评估默认采用固定动作与完整客户端协议对拍。** 不加载真实模型重新推理；真实模型闭环扩展与噪声方案衔接，另定模型及预算。此默认只证明同输入环境/客户端行为，不证明独立模型重推逐位一致（第九节）。
6. **B5 推荐保留现表，尚不代用户结案。** 将 xhard0 的流水线上限从 1300 改成 1600 是行为变更，不能混在本次维护等价提交里（第十节）。
7. **所有结果都有作用范围。** 全量才可写全集一致；抽样只能写样本一致。缺证据写未验证，任何新差异先定位，不自行调整阈值、换候选或挑成功回合。

## 七、维护前后基线与身份全集

### 7.1 固定版本和环境

A 为维护前 `BEFORE_SHA`，B 为最终整合后的 `AFTER_SHA`。原则上 A 承接 `PLAN_BASE`；实施时若基线已变化，先审清新增差异并记录，不能悄悄混入其他功能。两侧使用独立 worktree、各自 uv 环境和输出目录；验证实际导入路径，防止 editable 安装把 A、B 都指回主副本。

公共观察器/比较器单独冻结为 `HARNESS_SHA`，两侧用同一版。输入、身份、动作带、依赖/解释器、GPU设备、驱动、渲染器、CPU/线程配置、worker数和顺序相同。正式生成受现有 A40 守卫约束，同一身份 A/B 在同一席位串行；本机 Ada 的 `--dev-smoke` 只算开发证据，不与历史 A40 混比。

官方 `robomme` 与 `robomme_hard` 会覆盖同名 Gym 注册，两条链必须独立进程。观察器组合持有公开 builder/env，在调用边界读写自己的证据，不替换官方方法、不注入官方替身。现有 `hard_regression.py::_env_install_timers` 会替换方法，不能直接当作只读观察器使用。

### 7.2 生成与新值评估的共同集合

以下乘式记为 `N_V9`，真源是 `src/robomme_hard/env_record_wrapper/hard_specs.py::_v9_cells/V9_CELLS`：

| 任务 | 档位与每格局数 | 小计 |
|---|---|---|
| PickXtimes、RouteStick、PatternLock | 3 任务 ×（xhard1 17 + xhard2 17 + xhard3 16） | 150 |
| SwingXtimes、StopCube | 2 任务 × 5 档 × 10 局 | 100 |
| VideoUnmask、ButtonUnmask | 2 任务 ×（xhard1 13 + xhard2 13 + xhard3 12 + xhard4 12） | 100 |
| BinFill、VideoUnmaskSwap、ButtonUnmaskSwap、VideoPlaceButton、VideoPlaceOrder、PickHighlight、VideoRepick | 7 任务 × 2 档 × 25 局 | 350 |
| MoveCube、InsertPeg | 2 任务 × xhard4 × 50 局 | 100 |

合计 `N_V9=800`、43 格，逐档 `272/272/92/144/20`。五份包内规格的未选候选也冻结，不能只保护选中行。

| 评估配置 | 完整集合乘式 | 路由 |
|---|---|---|
| 官方 test | `N_TEST=16任务 ×（easy 26 + medium 12 + hard 12）=800` | 官方包和 test 元数据 |
| 默认 test-hard | `N_V9`，按上表乘式合计 800 | xhard0 开关关闭 |
| 兼容 test-hard | `N_COMPAT=N_V9 + 16任务 × xhard0 × 12局=992` | `ROBOMME_HARD_XHARD0_IN_TEST_HARD=1` |

官方 hard 原 episode 是 `3,7,11,15,19,23,27,31,35,39,43,47`，不是 hard builder 中的 `0…11`；兼容模式下新值 builder episode 相对默认整体加 12。不能把官方 test 全集误算为 xhard0 的子集。

连接键至少包含 `(配置,dataset,task,tier/difficulty,seed,candidate,source_episode,spec_sha256)`，不适用字段显式 null，另存两侧实际 builder episode。不能只凭 `(task,seed)`、文件排序或局号连接。冻结输入清单逐项记录规格/官方元数据/交付清单/动作与协议证据的哈希，正式 HDF5 记录路径、真实目标、字节数与全量 SHA256；不只相信规格里写的旧摘要。

## 八、生成对拍：从准备输入到完整 HDF5

### 8.1 现有能力与缺口

可复用链路为 `generate_h5.py --mode replay` → `_rollout.py::load_identities/run_replay/run_batch` → `train_split_runner.py` → `train_split_worker.py::run_one` → 任务/规划器 → `RobommeRecordWrapper`。每侧从自己的入口启动，同一冻结身份，不递补、不回写规格，输出分到 `before/gen` 与 `after/gen`。

现有 `hard_parity.py::classify_terminal/cmd_compare` 把 H:H2 的左侧 HDF5 绑定到交付 manifest，不能直接把维护前新采集 A 冒充交付 H。拟新增维护比较器，只复用经核对的只读读取函数；旧容差、5%线和历史 H:H2 结果不变。

另有两个不能误用的通过信号：

- `run_replay` 的 `REPLAY_SET=PASS` 只证明身份调度齐，`summary.failed>0` 时入口仍可能退出 0；验收必须读取逐局结果和完整产物。
- `pair_metrics` 只比较部分 setup、动作/状态/RGB，并按共同帧计算；不能证明全部属性、语言、子目标、waypoint 和尾部记录一致。新比较器必须遍历所有 group/dataset/attribute。

### 8.2 分层判据

| 层 | 必须检查 | 通过说明什么 |
|---|---|---|
| 冻结资产 | 前后五份规格全部字节、交付清单与正式HDF5哈希相同；缺失/重复/额外身份均0 | 没动交付数据 |
| 生成准备 | seed/attempt/spec、sampling配置、候选、任务顺序、配额、worker kwargs相同；合法schema冻结输出相同 | 维护未改生成输入或选择 |
| 回注与完整内容 | 规格绑定覆盖且无未消费/未归因差异；setup、全字段dtype/shape/值、完整帧序、事件/子目标、成功字段与终态相同 | 生成语义和记录内容一致 |
| 容器字节 | 整文件SHA256相同 | HDF5逐字节一致，与内容一致单列 |

数组默认 `atol=0,rtol=0`，同时报告字节差、数值差、NaN/Inf位置；不同dtype、正负零字节差不可隐藏。图像同时记录存储值与解码像素；MP4编码字节不作为物理行为等价判据。帧数先比较，不截成共同前缀；失败产物也保留。

允许规范化的仅为事先列出的运行路径、时间、PID、版本provenance等确切输出键。不能忽略整个 header/setup/info；冻结规格中原有provenance仍是输入，不随意剔除。内容全等而容器字节不同，只能写“内容一致、容器字节不同”。

### 8.3 已知分叉与噪声方案的衔接

现行留档记载 `N_V9` 的历史 H:H2 中 782 局字节一致、17 局轨迹分叉、1 局二次生成失败；这是已有记录，本轮未复跑。根因未完整诊断，不能把这18个身份当豁免名单。

本轮 A/B 有差异，严格等价就保持 FAIL，报告首个字段/步、原值、最大差与终态。噪声方案将来若完成，只有身份集合、参考对象、环境指纹、统计分母、模型/worker条件均匹配且阈值已冻结，才能另给 `MAINT_NOISE_GATE` 结论；样本G9上的阈值不能直接套全量 `N_V9`，相对交付H的阈值也不能不经转换套A:B。缺合同就标未验证，不能改旧容差来取得PASS。

A:A/B:B诊断默认额度0；需要时纳入一次预算，不覆盖最初A/B结果。即使同版也分叉，也不等于当前改动已经证明等价。

## 九、test evaluation：完整运行与客户端协议分别对拍

### 9.1 E1：固定同一动作的真实环境

官方 test、默认 test-hard、兼容 test-hard 各走两侧真实公开 builder 的 `make_env_for_episode→reset→step→close`。每身份使用预先冻结的同一动作带，跑至各自真实终态或该入口原有上限，不能只测前30/50步。

动作带可来自已有完整、身份绑定的动作证据，或预先用独立随机源生成；清单记录来源、动作空间、dtype、维度、每行内容及最大可消费长度。不能在运行中重置环境全局随机流。动作带耗尽但环境未终止属于证据不完整，不伪装成timeout。固定动作只验证该动作序列下的行为，不声称覆盖所有可能策略。

reset保存全部演示帧、状态、初始观测、task_goal及顺序，不只留最后一帧。逐步比较实际动作、完整观测、reward、terminated、truncated、info.status、执行步和终止原因。A先终止时B继续到自己的终态并保留尾部；不能截齐长度掩盖差异。

### 9.2 E2：固定观测和服务返回的完整客户端逻辑

用两侧真实 `mme_client.py/smvla_client.py` 执行循环，回放同一份观测和策略原始动作块；比较预处理、reset/add_buffer/infer请求、消息顺序、动作块、dtype转换、逐行执行、消费数及终止截断。模拟对象只提供外部输入，不手写一份“正确客户端”来测试自己。本层不加载模型、不触发真实环境reset。

完整E2证据清单为 `2种客户端 × (N_TEST + N_V9 + N_COMPAT)=5184` 份身份绑定trace，每份分别在A/B重放，合计10368次离线重放，真实环境reset为0。每份trace必须有来源、输入/动作块哈希、完整时序及终态；缺任一必选trace即 `MAINT_EVAL_CLIENT=NOT_VERIFIED`，不能只跑几个分支夹具后汇总全量PASS。S0先查已有录制能否覆盖；缺真实记录时不能在此零预算下偷偷启动模型或额外评估。若用户只选客户端分支合同验证，则E2及最终汇总必须改写为该有限范围，不能保留完整协议对拍的称谓。

覆盖非空demo、无demo、块中途终止、块跨上限、obs=None、异常返回、timeout、连续身份与重启接续。真实记录缺分支时用明确标注的合成夹具补合同测试，不冒充真实闭环记录。

现有 `policy_replay.py::cmd_build_inputs` 计算 `exec_equal` 却未将其纳入 `ok`；不能直接拿 `BUILD_INPUTS=PASS` 充当执行动作一致。新门禁检查维度、顺序、数量、终态、完整证据。缺线上wire证据只能给离线协议结论；`payload_equal` 也不能推出真实模型动作相同。

### 9.3 上限按各入口原语义保留

| 入口 | 当前语义 | 维护对拍 |
|---|---|---|
| `scripts/evaluation.py` | builder构造1300、逐局不传 | 官方test的A/B保持相同 |
| `scripts/evaluation_hard.py` | builder构造1600、逐局不传 | 默认/兼容两模式分别A/B比较 |
| `env_client.py::SeatRunner.run_one/EnvSession.step` | 清单effective_max_steps与表核对，新值1600；现有官方路径按原配置 | E2检查块边界与严格cap，cap+1不能进入受该守卫管理的环境 |

builder/wrapper还存在 `max_steps+2`、演示和初始化步，客户端有各自动作块计数。分别记录 requested_max_steps、wrapper上限、demo/init步、客户端调用数和实际执行步，不把它们强行统一。不同入口本来存在的上限差另列，不算维护A/B差异。

`hard_regression.py::cmd_eval_smoke` 当前仍逐局查表，不等于公开 `evaluation_hard.py`；`reset-replay` 只验回注；旧 `env-digest` 短前缀也不能证明完整评估。

### 9.4 E3：真实模型闭环扩展

默认本轮不启动，模型选择与预算另定并与噪声基线方案衔接。若执行，两侧真实模型独立推理，锁定权重/tokenizer/配置/seed/缓存及重启方式，逐身份比较成功→失败、失败→成功、error、timeout与步数差，并记录首次观测→payload→模型输入→原始动作→执行动作分叉。总成功率相同不够。

所有结果含attempt_id/accepted_attempt_id。普通task_success=0是有效结果，不重试挑成功。E3未执行时明确 `MAINT_EVAL_MODEL=NOT_VERIFIED`，不能因E1/E2通过宣称模型闭环一致。

## 十、逐项维护怎样保证不改正常行为

| 事项与锚点 | 具体修改 | 正常保证／允许改变 |
|---|---|---|
| C1：`test_TaskGoal.py` | 未知环境断言改为真实的[]；文本改为back-and-forth，保留次数/颜色等检查 | 不改官方源码 |
| C1：`test_step_error_handling.py` | 调用真实DemonstrationWrapper.step测试异常传播；纠正脚本子串断言；修复mock依赖泄漏 | 不用手写FakeDemoWrapper自证，不广泛xfail掩盖失败 |
| C1连带：两个`test_zz_summary_line` | 移除“整个pytest会话失败数=0”耦合，测试各自业务报告；会话退出码由外部汇总 | 不靠执行顺序隐藏前面失败 |
| C2：测试/夹具/命名/重复断言 | 建旧nodeid→契约→新nodeid/处置表，先迁移活跃正反例再删冗余 | 名字带v7/v8不是删除依据；条件测试仍显式可跑 |
| C2：`pyproject.toml` | testpaths限定tests；增加core标记，实测拆核心和扩展集 | 核心目标≤120秒、硬上限280秒；不能全标slow来凑通过 |
| G1：`_freeze.py::freeze` | /2、/3用自身合法tiers，/4保持五档 | 合法输入输出/签名不变；非法xhard5更早明确拒绝，旧代码最终也拒绝 |
| B6：导出→manifest→站点 | 显式身份模式与偏移；默认800、历史992分别校验 | 修复新导出800被固定要求992的消费者拒绝；旧文件不原地改写 |
| D3：运行器/manifest | 持久重启计数、总收尾期限、半写文件发布、cleanup判定与说明 | 正常观测/动作/结果不变；恢复/错误路径改变逐项列夹具 |
| B5 | 推荐保留TIER_MAX_STEPS原值和调用 | 拉平或删表另立行为变更，不混入零语义差异验收 |

原清单部分信息已过时：`test_hard_builder_xhard0.py::test_逐任务局数常量_开关两档合计` 已完成改名及两模式覆盖；`test_v7_*.py` 当前9个文件；`tests/fixtures/v7_specs_sample/` 仍被活跃 `test_v8_regression_cmds.py` 当反例使用。不得按“8个、只服务旧用例”批量删除。

G1非法输入提前拒绝、B6模式兼容和D3故障恢复是预先声明的纠错，不要求错误路径与旧bug相同；合法输入上的生成和评估仍严格比较。缺少解释的新差异不能归进“小修”。

## 十一、链路、验收和阶段顺序

```text
维护前 A
冻结规格/元数据 [JSON；全文件SHA/字节数固定，不改数]
 ├─ A生成准备 → A任务/规划器 → A RecordWrapper → 完整HDF5
 └─ A公开builder → reset完整demo+初始帧 → A客户端 → env.step → 终态
                          E1固定动作；E2固定观测与服务返回，各自验收
维护后 B
相同输入 [SHA必须与A一致，不改数]
 ├─ B生成准备 → B任务/规划器 → B RecordWrapper → 独立HDF5 → 全字段比A
 └─ B公开builder → reset完整demo+初始帧 → B客户端 → env.step → 逐步比A
```

各跳记录原始shape/dtype/nbytes与“是否改数”；客户端resize、状态拼接、动作转换尤其单独记录。双RGB按实际 `uint8[H,W,3]` 记每帧 `6HW` 字节；8维动作float32为32字节、float64为64字节，不能先cast再掩盖差异。实际尺寸/帧数由采集确认，不预设224/512。无训练，可训练参数变化为0。

以下判定行均是拟实现合同，不是本轮运行结果：

| 查什么 | 怎么查 | 通过说明什么／判定行 |
|---|---|---|
| 基线及导入 | 完整SHA、实际路径、依赖/设备/输入/工具指纹 | 归因前提成立：`MAINT_BASELINE=PASS` |
| 冻结交付 | 前后全量哈希相同 | 资产不变：`MAINT_FROZEN=PASS changed=0` |
| 身份完整 | 三配置逐键连接，缺/多/重复为0 | 同一批对象：`MAINT_IDENTITIES=PASS` |
| 生成准备与内容 | 合法输入、绑定、全字段/完整序列零差 | `MAINT_GEN_PREP=PASS`、`MAINT_GEN_CONTENT=PASS`；整文件另列`MAINT_GEN_BYTES` |
| 完整固定动作环境 | E1全demo/观测/动作/终态对拍 | `MAINT_EVAL_ENV=PASS scope=test,test-hard,test-hard-compat` |
| 客户端与边界 | E2真实循环、消息/动作/错误/上限夹具 | `MAINT_EVAL_CLIENT=PASS` |
| 生命周期 | 预算、半写、信号、重启、同步故障夹具 | `MAINT_LIFECYCLE=PASS` |
| 测试覆盖与时间 | nodeid映射、核心非空、退出码/实际计时 | `MAINT_TEST_COVERAGE=PASS`、`MAINT_CORE=PASS wall_s=实测值` |
| 汇总 | 必选项全部覆盖，无未解释语义差异 | `MAINT_ACCEPT=PASS scope=fixed-input` |

任何失败、缺证据、录像降级/截断均不得汇总PASS；缺证据记NOT_VERIFIED并非零退出。内容一致而容器字节不同，只有事先确认的精确元信息白名单才能支持内容层通过，并保留字节层FAIL。噪声闸门另列，绝不把“容差内”重标为“全等”。

### 子代理分工与合并（简述）

主会话冻结公共合同、基线、预算和最终整合；测试、规格预检、身份清单、站点消费、生命周期、对拍工具分独立worktree。先交付公共工具并冻结，再采A；维护后采B。各文件一个负责人，整合前审边界与定向测试，整合后复核接口和资产哈希。子代理不暂存/提交/push，主会话只接收授权文件。

| 阶段 | 内容 | 判据 |
|---|---|---|
| S0 | 冻结版本/输入/预算/环境、一次确认scope与B5等待定项 | 预算和资源清单获准，受保护覆盖无越界 |
| S1 | 实现公共对拍合同及负例，固定HARNESS_SHA | 漏行/错值/尾帧/终态反例均拒绝 |
| S2 | 每条链先单任务单局smoke，再采完整A | 身份齐全、基线证据完整，失败如实记录 |
| S3 | 按清单维护、定向测试、审查整合，固定AFTER_SHA | 测试映射和G1/B6/D3合同通过 |
| S4 | 同环境同输入采B、离线逐项比较 | 各具名判据给真实结果；不放宽 |
| S5 | 资产复核、核心耗时、留档与逐项结案 | 必选项全过才称维护等价完成 |

### 实测结果（后续实施填写）

本轮没有执行维护代码、pytest、生成、reset、evaluation或模型推理。历史782/17/1不能写作本轮结果。未来在此追加A/B/工具SHA、实际预算、判定行、证据路径、耗时与未解决差异，不改写原判据。

# 第二部分（技术细节，供 agent 追踪）

## 〇、前置声明与红线

- R1：本轮只写本文；资源删除、噪声基线实跑、Oracle新模型不属于本次实施授权。
- R2：冻结 `src/robomme/`、三个官方入口、官方vendor、正式交付规格/HDF5、旧容差及旧H:H2判定。生产观察器不覆写官方方法；测试内mock按规则限定在测试进程并恢复。
- R3：新增脚本只进已有 `scripts/parity/`；生产代码不import tests。其他代理或用户的在途文件不动。
- R4：所有Python经uv、显式UV_CACHE_DIR；NFS设UV_LINK_MODE=copy；计算节点只用已安装环境的 `uv run --frozen --no-sync`。各执行副本独立venv，不共用会被更新的环境。
- R5：各侧/配置/worker独立输出到 `artifacts/maintenance-parity/<run_name>/`；不覆盖输出、不写交付链接目标，不以chmod改变硬链接共享实体。
- R6：超过5分钟进具名detached tmux，pipefail、行缓冲tee及EXIT_CODE齐全；成功/失败接续先以无仿真夹具验过。没有代理唤醒回执不承诺无人值守。
- R7：普通任务失败不重试；基础设施重试/诊断默认0；构造隐式reset、smoke、恢复全计账。GPU同席串行，不新增高频全卡监控。

## 一、逐文件清单

1. **C1/C2**：`test_TaskGoal.py`、`test_step_error_handling.py` 调用真实方法验证；mock用作用域受控fixture。两个 `test_zz_summary_line` 去除全会话耦合。共享 `tests/_shared/v7_tier_values.py` 计划改名 `tier_values.py`，原值不变，全部引用同迁。删除旧测试前提交精确nodeid/夹具路径/契约去向表，不按glob授权批删。
2. **核心集**：`pyproject.toml::tool.pytest.ini_options` 增testpaths与core标记；`tests/conftest.py` 仅在实际选择机制需要时修改。核心必须包含V9配额/身份、开关、官方锚点、规格签名反例、生成状态机、manifest连接、客户端cap/accepted账本和新比较器反例；耗时较长的信号/视频测试留定向集，D3修改时仍必须跑。
3. **G1**：`scripts/injection-dev/_freeze.py::freeze` 将/2、/3预检绑定其schema合法tiers，/4继续V8_TIERS；纯函数夹具比合法header/rows/签名，不做额外抽样reset。
4. **B6/C2-9**：`export_eval_identities.py::main/check_rows` 的docstring/help与实际关档 `official=skipped` 一致；补 `hard_regression.py::cmd_xhard0_reset_parity` 关档SystemExit测试。新测试不得吞异常后写PASS。
5. **B6/D3清单**：`scripts/eval-official/v8_manifest.py::check_source/build/build_v9/write_outputs` 显式消费身份模式。历史992偏移与目标配置不符时拒绝，或经独立转换输出新文件并保存映射；不得静默减12。新manifest/shard在新暂存目录完整校验后发布，OSError只清理本轮临时文件，已有输出不覆盖。
6. **B6站点**：`scripts/injection-dev/site/v8_site_catalog.py::expected_identities/build_catalog/validate_catalog` 共享身份模式；不能把常量12直接改0。旧992站点仍能读，新默认800另建catalog；若改交互，补Playwright，不重启既有站。
7. **D3生命周期**：`run_seat.sh::policy_loop/kill_group/stop_server`、`run_v8_gl.sh::finalize/stop_run_seat/reap_orphans/sync_recordings`。重启计数按run/seat/policy/reason持久化，先计账再重启；与现有AttemptLedger职责分开。父子共享总截止时间，核实真实KillWait和预告信号，不沿用父等25秒/子等60秒的矛盾；同步有期限，未完成保留清单，禁止伪装成功或杀无关进程。`V8_EVAL_CLEANUP` 当前未实现，应新增明确语义或由独立报告核查，不拿 `V8_SEAT_DONE` 代替。
8. **拟新增对拍**：`scripts/parity/maintenance_parity.py` 管计划、锁、严格比较/报告；`maintenance_capture.py` 管版本隔离和完整E1/E2采集及生成报告接入。公共工具冻结后不随B失败调阈值。
9. **拟新增测试**：`tests/lightweight/test_maintenance_parity.py` 覆盖错版本/输入、漏行、重复、末帧、dtype/shape、数值/终态篡改、零值键丢失、半写JSON与退出0但failed>0；必须写文件再读回比较。`tests/dataset/test_maintenance_eval_parity.py` 标GPU/环境条件，真实smoke计预算。
10. **留档与规则**：主会话写运行留档、scripts README、待定条目及AGENTS标记块外核心命令。只对实际通过的条目结案，A1/A5与模型问题不顺手结案。

## 二、子代理分配表

以下是后续建议分工，本轮只有只读探索代理。所有写入型代理独立worktree，禁触R2及其他负责人文件，不暂存/提交/push。表内简称文件的完整目录以上节为准；M1的旧测试删除集合必须先展开精确附件，附件未定前不得派删改。

| 编号/目标 | 独占可写集合 | 接口依赖与整合顺序 | 验收与环境 | 资源/共享裁决 |
|---|---|---|---|---|
| M0主会话 | 本文、pyproject、必要conftest、核心清单、README、AGENTS覆盖项、待定清单、留档 | 公共合同先定，核心收集最终统一 | 本机CPU，diff检查/核心计时/最终报告 | 统一预算、run_name、tmux/job清单 |
| M1测试维护 | TaskGoal/step_error测试；v7_tier_values迁移与其引用文件；精确获批的旧测试/夹具清单 | 正反例迁移后删旧；不得写M2～M6专属测试 | 各worktree定向pytest，TEST_COVERAGE | CPU；共享test_v8_regression_cmds/test_v8_delivery_flow归M1 |
| M2规格预检 | _freeze.py、test_v7_freeze_schema.py、test_v8_specs_schema.py | 固定schema输出契约；先于M1最终清理 | 本机CPU，schema正反例 | 不占GPU，不写规格产物 |
| M3身份/manifest | exporter、v8_manifest、test_v8_eval_manifest、新增test_eval_identity_modes | 持有mode和发布协议；先于M4/M6接入 | 本机CPU，800/992联测及半写故障 | 不起模型；M5不写manifest |
| M4站点 | v8_site_catalog、test_v8_site_catalog | 依赖M3合同；不能自定义第二套计数 | 本机CPU集合比；必要时Playwright | 不改已有服务；临时端口核空闲后登记 |
| M5生命周期 | 两个shell运行器、test_eval_official_run_seat、test_v8_eval_orchestration、两个report/video_mover测试 | 持久账本/收尾协议；包含两条会话耦合断言修复 | 本机CPU假服务故障夹具，LIFECYCLE | 仅本轮PID/端口；不占模型GPU |
| M6对拍 | 两个maintenance脚本/测试、新增test_xhard0_disabled_paths | S1先冻结工具，S3后只采集比较；共用M3身份合同 | CPU负例；获批A40同席串行E1/生成 | 前缀maint-；总账归M0，不自建额度 |
| M7复核 | 无 | 每块整合前后核写集合、差异与证据 | 只读diff/报告/退出码 | 问题交原负责人，不自行修文件 |

M1要修改M2/M3专属文件里的导入或core标记时交对应负责人完成。未列的env_client、策略客户端、模型及任务源码保持只读；发现必须修改时列具体函数及必要性处理新增范围，不能代理自扩权。

## 三、完整对拍预算与开跑前决策

**本轮执行额度0。** 下表是完整固定输入验收的提议，未获运行授权；N均引用第一部分第七节的任务×档位×局数乘式。抽样版本须另冻结集合，不能冒称全量完成。

| 项 | 轨迹尝试乘式 | 环境reset上限 |
|---|---|---|
| G生成 | `2侧 × N_V9=1600` | `1600 × 2=3200` |
| E1官方test | `2侧 × N_TEST=1600` | `1600 × 2=3200` |
| E1默认test-hard | `2侧 × N_V9=1600` | `1600 × 2=3200` |
| E1兼容test-hard | `2侧 × (N_V9+16任务×xhard0×12局)=1984` | `1984 × 2=3968` |
| E2协议/故障夹具 | 真实环境轨迹0 | 真实环境reset0 |
| E3、A:A/B:B、基础设施重试、递补 | 默认0 | 默认0 |

合计 `2×[N_V9+N_TEST+N_V9+(N_V9+16×1×12)]=6784` 次轨迹尝试、最多 `13568` 次环境reset。每条链最小smoke `1任务×1档×1局×2侧` 从上述集合取首局，条件完全相同且不重跑时已计入；开发Ada smoke与正式A40不同，若另跑，须额外列入批准预算，不能声称已包含。

每局2次是**固定源码和已查依赖下的静态上界**：`BaseEnv.__init__` 隐式一次 + 生成worker的 `record_env.reset` 或评估的公开 `env.reset` 一次；demo规划和 `solve_strong_reset` 走动作/规划，不额外环境reset。限定joint_angle、每局新建一次环境、无自动恢复/探针/重试；agent/controller自身初始化不另算环境reset。运行节点必须重新核实同一调用链和指纹，否则此预算失效、不得开跑。

已查本机ManiSkill `sapien_env.py` SHA256为 `d16b9fdc8b0f17db850903d73f650ee8cf6491e4acffd40db1b004b17e915789`；其registration为 `bbc7ed7c6bd03f8ab394a36a2d08c68b771117ffa1e91cfedbcc5b2e45bf609e`；Gymnasium 0.29.1的registration为 `c19435118cef037e21a3b64b4a53328119a61c49086ad3e6c13f54bbb23e013b`。这些是安装实物指纹，不代表已经验证远端环境或做过运行计数。

预算守卫在启动每局子进程前原子预占最坏2次，失败/进程死/消费未知不退款；A/B/所有worker共享一份总账。指纹约束保证无内部额外reset，不能靠只包外层reset而漏构造，也不通过monkeypatch官方BaseEnv来计数。任何额外校准/连续worker重置/重跑都须先有额度。

S0一次确认：B5处置、E3是否纳入、全量或样本、身份/输入合同、两侧worker数、硬件/地点、job数和规格、run_name、输出目录、全部预算、重试0、期限与停止条件。已有授权沿用，不分阶段重复询问。正式生成按A40及greatlakes规则；本机CPU检查不占GPU。run_name/席位尚未指定，预计耗时和磁盘需求尚未实测，不编造数字；先用可比历史日志估计，获批smoke后更新，估计不构成加跑许可。

## 四、闸门反例与现有工具适用范围

| 闸门 | 必须拒绝的例子 | 处置 |
|---|---|---|
| 基线/资产 | 两侧实际导入同路径、依赖/输入不同、交付被改 | 仿真前停止，保留指纹差异 |
| 身份 | 800按992解释、错12偏移、缺/多/重复、同seed覆盖不同tier | 不调度，输出完整差集 |
| 生成 | 退出0但failed>0、h5缺失、两侧都失败被标通过、只比较共同帧 | 生成门禁FAIL，保留部分产物 |
| 内容 | setup/目标改动、dtype转换掩差、任一末帧/属性/终态不同 | 首差定位，旧容差不动 |
| 客户端 | exec_equal=false仍PASS、cap后继续step、错误/None吞掉 | 客户端FAIL，普通失败不重试 |
| 生命周期 | supervisor重启清额度、重复accepted、半写被消费、同步超时假成功、误杀他人 | 无GPU故障夹具先阻断 |
| 汇总 | 零键消失、半行JSON、报告崩溃、未知字段默认0、录像降级 | FAIL/NOT_VERIFIED，独立监督通知 |

`recorder.py::EpisodeRecorder` 有空间不足降级行为；复用时若丢帧或降级必须使完整对拍未通过。所有数值差保留可还原数组/帧，不只保存SHA却承诺计算幅度。关键帧可辅助目视，但不能代替全字段检查。

## 五、执行手册

以下命令是未来实施用，不在本文细化时执行。先检查路径、输出实体与归属；独立执行副本须干净，主副本他人在途内容保留。

现有入口：

```bash
command -v uv
test -f uv.lock && test -f pyproject.toml
export UV_CACHE_DIR="$HOME/.cache/uv"
git status --short
git rev-parse HEAD
uv run --frozen --no-sync python scripts/parity/upstream_guard.py check --require-upstream
uv run --frozen --no-sync python -m pytest tests/lightweight/test_TaskGoal.py tests/lightweight/test_step_error_handling.py -q
```

当前旧核心全量历史耗时超过5分钟；若要重跑完整基线，应走tmux留档。维护后拟命令：

```bash
timeout 280s uv run --frozen --no-sync python -m pytest tests/lightweight/ -m 'core and not gpu and not slow' -q --durations=20
```

`core` 当前尚未定义，只有实现并检查收集非空、契约覆盖之后才可用；退出124是超时失败。定向功能测试仍按改动范围执行，首次完整计时通过后不无意义重复全跑。

现有生成重放形式（占位参数须替换、只在获批后用）：

```text
uv run --frozen --no-sync python scripts/injection-dev/generate_h5.py
  --mode replay --identities <gen-identities.jsonl> --src-root <当前侧worktree>
  --pkg robomme_hard --output <当前侧独立目录> --workers <获批数量> --gpu <获批设备>
```

两侧从自己的入口启动；外层验证完整candidate/spec/attempt。`load_identities` 目前只留下task/tier/seed，不能用该缩减集合代替最终身份核验。正式不加dev-smoke；dev-smoke和正式分环境证据，额外次数另计。

拟新增接口，当前文件/参数不存在：

```text
maintenance_parity.py plan
  --before-sha --harness-sha --scope --input-lock --out
  只生成固定身份、模式、输入/判据哈希、预算，不触发仿真。
maintenance_capture.py generation|evaluation|client
  --side before|after --code-root --plan --output
  检查版本/来源/预算后采集；按真实逐局结果汇总。
maintenance_parity.py compare
  --plan --after-sha --before --after --out
  只读比较；任何必选缺证据/差异非零退出。
maintenance_parity.py report
  --plan --comparisons --out
  汇总具名门禁、task_success与首差，不提升INFO为PASS。
```

S3后绑定AFTER_SHA时身份/输入/判据/预算哈希不变；最终比较拒绝未绑定版本。A/B/汇总各自独立完成信号；接续必须真实序列化报告后验证零计数、正常任务失败、缺文件及检查器崩溃，不只等EXIT_CODE。正式采集期间冻结产品与工具版本。

## 六、风险与盲区

- 历史生成已有分叉，不能承诺全量严格通过；失败如实保留，噪声合同另验，不改数据/候选/容差。
- 固定动作只覆盖所选动作带；E2离线不证明线上模型；E3未选必须明确模型闭环未验证。
- 观察器/录像可能影响墙钟敏感路径；两侧工具和记录量相同，不宣称零扰动。若需额外校准，先列预算。
- 旧测试清理可能丢负例：nodeid映射必须含空集、重复/漏身份、错签名、错绑定、跨版本数量、当前状态机；测试数量相近不是覆盖证据。
- 本机安装依赖的reset静态上界不能替代运行节点核验；不同设备/驱动/worker条件不能用旧数值基线推导一致。
- 运行耗时、磁盘需求、真实KillWait与资源尚待S0核实；同步来不及必须保留未完成状态。
- 核心短测通过不代表生成/评估通过，sample不代表全集，历史结果不代表本次结果。原因解释不能替代验收。

## 七、留档、提交与结案

`artifacts/maintenance-parity/<run_name>/` 保留锁、固定计划、A/B证据、逐身份报告和预算账本；新attempt另目录，原失败不覆盖。`docs/validation/<run_name>/launch.md` 记用户原话、三类SHA、环境、scope、完整命令、预算与tmux/job/端口清单；`result.md` 记判定、差异/成败迁移、首差、耗时与盲区；`records/` 只放轻量实测，不复制脚本/配置/大HDF5/权重。

每块定向测试及审查后由主会话提交，最终AFTER_SHA在B采集期间冻结；运行后的文档提交不冒称被跑版本。只逐路径暂存本轮文件，保留他人暂存和未暂存内容；按现有授权推当前分支既有upstream，拒绝即报告，不强推。

收尾更新AGENTS只改标记块外已实测核心命令；待定清单只结案已通过子项，保留原记录与用户裁决。A1/A5、MME历史问题、资源清理、噪声基线是否完成各有独立依据。

本轮文档交付只执行diff空白检查、两部分结构、链接/符号/文件范围与原事项保留检查，不启动pytest或生成评估；文档检查PASS不表示维护或对拍已完成。
