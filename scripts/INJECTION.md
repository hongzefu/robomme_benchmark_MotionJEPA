# 新值注入的原理

一句话：**环境侧开了两个互相独立的 kwarg 注入口（`sampling_config` + `episode_spec`），上游由 `candidates.jsonl` 这一份冻结快照统一喂进来，生成器只负责转发、不再自己造值。**

注入**没有**引入新的环境包装层、新的子类或第二套执行逻辑。它的全部做法是：在四个任务（`BinFill`、`RouteStick`、`VideoUnmaskSwap`、`VideoRepick`）原有的每个取值点上开一个 `if spec is None:` 岔路——不传时逐字走原路径，传了就用规格里的最终值，并把那一次随机调用整个跳过。

```text
scripts/configs/newtask-v2/{injection_contract_v3,native_sampling,delivery_400}.json
        |  scripts.injection.candidates（纯 CPU，不导入仿真）
        v
artifacts/injection/<run-id>/candidates/candidates.jsonl   ← 冻结快照，唯一环境输入，进 Git
        |  header 行内嵌 sampling_config / runtime / 来源指纹
        |  每条候选行内嵌该 episode 的完整 spec
        |
        |  scripts.injection.rollout（execute_scope 只读取、校验、转发）
        v
generate_dataset_newseed 的 EpisodeJob（sampling_config / episode_spec 各一份 deepcopy）
        |
        v
gym.make(task, seed=..., difficulty=..., sampling_config=..., episode_spec=...)
        |
        v
任务 __init__ → _load_scene → _initialize_episode 上的各个取值点岔路
```

---

## 一、两个注入口的分工

| 注入口 | 粒度 | 作用 |
|---|---|---|
| `sampling_config` | 每 task 一份 | 只替换**候选与区间的来源**（原类级 `configs` 字典与散落的字面常量 → 实例副本），抽样表达式、`torch.randint` / `torch.rand` 的运算元与顺序原样保留 |
| `episode_spec` | 每 episode 一条 | 直接**定死这一局的具体值**（board 的 xy 与 yaw、button 中心、每个 cube 的 xy 与 yaw、生成顺序、配额、动作序列、`dynamic` 等），命中的量不再走随机流 |

两者独立：可以只传前者（随机流位置与原版完全一致，只是候选表换了来源），也可以两个都传（正式实跑就是两个都传）。都不传时链路与改动前逐字相同，`DEFAULT_PARITY` 就靠这一条成立。

## 二、kwarg 怎么进到环境里

`gym.make` 的 kwargs 被任务 `__init__` 的显式形参接住（两个参数都有 `None` 默认值），第一时间 resolve 成实例私有副本，赋给 `self._sampling` 与 `self._episode_spec`，同时初始化只读证据字典 `self._injection_evidence`。

`_resolve_sampling_config` 与 `_resolve_episode_spec` 只做三件事：**类型与键集校验 → `copy.deepcopy` → 返回**，全程不调用任何随机数。

三条硬约束及其原因：

1. **必须显式取走。** `BaseEnv.__init__` 是纯显式形参、没有 `**kwargs`，漏接一个未知 kwarg 直接 `TypeError`。
2. **必须 deepcopy。** gymnasium 会把传入 kwargs 字典的**引用**存进 `env.unwrapped.spec.kwargs`，多个环境会共享同一个 dict；而且构造期内部 reset 与外层 reset 会各重建一次工作态，两次都要从同一份原始规格重建，不能复用上一次被改过的状态。任务内只改这份私有副本，绝不碰调用方传进来的原对象。
3. **必须落在 `torch.Generator()` 创建之前、任何随机数调用之前。** 在这里多抽或少抽一次随机数，会平移其后全部取值。

不传 `sampling_config` 时，fallback 到任务模块顶层的 `NATIVE_SAMPLING` 常量，并把类级难度字典 `configs` 也复制进实例副本。这份常量同时是 `generate_dataset_newseed` 的 `--extract-config` 的 AST 提取目标，因此"提取到的原值"与"实际跑的默认值"永远是同一处，不存在双真值。

## 三、`sampling_config` 怎么替换取值：只换来源，不换算式

原来直接写字面量、或直接下标类级 `configs` 的地方，全部改成读 `self._sampling[...]`，**表达式一字不动**。例如 board 的偏移量仍是 `torch.rand(...) * scale - subtract` 这一行，只是 `scale` 与 `subtract` 从配置里取；难度参数读的是 `self._sampling["parameters"]["configs"][self.difficulty]` 而不是 `self.configs[...]`。

配套的四条口径：

- **JSON 里存的是运算元，不是折算好的区间。** 存 `base_position` / `scale` / `subtract`，禁止折算成 `[min, max]`：`0.15 + (u * 0.2 - 0.2)` 与 `-0.05 + u * 0.2` 的 float64 位模式实测不同，折算就破坏逐字节复现。
- **整数区间照旧交给原 `torch.randint(low, high + 1)`**，固定整数仍直接取值，没有统一成新的抽样器。
- **配置值一律以 Python 标量参与运算**，不包成 `torch.tensor`，否则会把 `rotate_points_random`、`build_button` 内部的 float32 路径提升成 float64。
- **类级 `configs` 的读点必须全部改成读实例副本**（`BinFill._load_scene` 一处、`RouteStick._load_scene` 一处、`VideoUnmaskSwap` 的 `__init__` 两处与 `_load_scene` 两处、`VideoRepick` 的 `__init__` 一处与 `_load_scene` 两处），漏改任一处就会产生"不传配置时相同、传配置时才发散"的隐性双真值，逐层对拍抓不到。

## 四、`episode_spec` 怎么定死值：三种手法

**手法 A：关掉被调工具的随机开关，直接喂最终值。** button 的注入即属此类：规格给的是**最终中心**，调用 `build_button` 时传 `center_xy=spec["layout"]["button_xy"]` 并把 `randomize` 置为 `False`，于是 `build_button` 内部不抽随机数，其余（缩放、travel、连杆、OBB）全走原路径。

**手法 B：反解回原公式的中间变量，位置计算行本身不动。** board 的规格存的是最终位置，注入时用 `最终 xy − base_position` 反解出原公式里的 `x_var` / `y_var`，`yaw` 直接取规格值，后面构造旋转四元数与调用 `build_board_with_hole` 的那几行与原路径共用，一字未改。

**手法 C：给底层 spawn 工具加固定值通道，短路整个拒绝采样循环。** `spawn_random_cube` 新增 `fixed_xy` / `fixed_yaw` 参数：传了就直接用该位姿建方块，不进入"三次 `torch.rand` + 避让判定"的重试循环。为杜绝两份创建代码漂移，原来内联在循环里的创建段被提取成共用的 `_finalize_cube`，两条路径共用。固定值路径不抽随机数，所以原本 `generator is None` 就报错的强制检查放宽为"`generator` 为空**且**没给固定值才报错"。运行时不再做几何可行性判定——可行性已在冻结候选之前用同一套 OBB 判据筛过。

**顺序与配额同样归规格管。** 原来用 `torch.randperm` 打乱方块生成顺序，传规格时改为按 `spec["layout"]["cubes"]` 的列表次序重排（并借 `color` 与 `color_index` 对上 `object_id`）；`_initialize_episode` 里决定颜色遍历顺序的那次 `randperm` 由 `spec["objects"]["initialize_color_order"]` 顶掉；每色的 `spawn_count` / `target_count` 直接由规格给出，整段配额抽样一次随机数都不走。

## 五、随机流语义：规格覆盖的量由规格决定，不刻意对齐

规格分支**不会**为了对齐随机流而补抽一次废弃的随机数。后果是明确的、被接受的：规格覆盖的量由规格决定；规格没有覆盖的量（如 `inject_fail_grasp` 的抽取）会因随机流位置平移而与原版不同，这些量不在验收范围内。

不传 `episode_spec` 时每个消费点都走原随机路径，链路与改动前逐字相同——这是默认对拍成立的前提。

另外注意 seed 的入口没有变：`seed` 仍是 `gym.make` 的 kwarg，由任务 `__init__` 的显式形参接住并自建 `torch.Generator().manual_seed(seed)`；`record_env.reset()` 不传 seed。若把 seed 改挂到 `reset(seed=...)`，会同时改变 ManiSkill 的 `_main_seed` / `_episode_seed` 并触发 `fork_rng` 分支，原链立即失守。

## 六、注入是否真的生效：两套证据

- **静态证据。** 传了规格时，`_load_scene` 末尾把"创建输入 vs 创建后 actor 实际位姿"写进 `self._injection_evidence`（请求的 xy 与 yaw、实际的 `p` 与 `q`、`spec_sha256`、配额等）。只读位姿，不改状态、不抽随机数，供绑定核验消费。
- **动态证据。** 运行期算出来的东西必须与规格预写的一致，不一致就抛 `SpecBindingError`。典型是 `VideoUnmaskSwap._verify_swap_binding`：用同一套扫描语义独立复算一次最近邻，发起者或搭档与规格对不上直接失败，**禁止换搭档**。`VideoRepick` 同理。

`SpecBindingError` 与 `BinCollisionError` 在生成器里被归入"任务性失败"，只是为了不被连续非任务性失败的计数器当成代码 bug；正式实跑固定单次尝试，因此它们**不会**触发换 seed 重试。

## 七、上游：为什么生成器不再自己造值

`candidates.jsonl` 是环境启动的唯一数据入口，冻结后进 Git：

- **header 行**内嵌完整的 `sampling_config`、`runtime`、交付配置快照与来源指纹；冻结后不再读取外部配置来覆盖快照，显式提供配置时只允许断言相等。
- **候选行**内嵌该 episode 的完整 `spec`、身份散列、筛查证据、`split`（train/test）与派生角色。

候选由 `scripts.injection.candidates` 在**纯 CPU、不导入仿真**的进程里生成并做碰撞筛查，所以"造值"这一步与"跑仿真"这一步彻底分离。

`scripts.injection.rollout` 的 `execute_scope` 做的事只有：`load_candidates` 校验封套版本、完整键集、内外身份、旧规格散列与采样快照源码指纹 → `validate_sampling_config(header["sampling_config"])` → 对每条候选 `project_spec` 取出规格（深拷贝，绝不补键或删键）→ `validate_episode_spec` → 拼成 `EpisodeJob` 交给生成器的 `_run_jobs`。

生成器侧只多了转发这一步，其余与原版逐字相同：

```python
if job.sampling_config is not None: kwargs["sampling_config"] = job.sampling_config
if job.episode_spec  is not None: kwargs["episode_spec"]  = job.episode_spec
base_env = gym.make(job.task, **kwargs)
```

父进程读一次配置、每个 job 各 deepcopy 一份独立副本，因此同一进程里的下一局不会被上一局改到。

> 遗留边界：`scripts/hf_release.py` 本轮冻结，仍按迁移前的交付清单路径工作；再次发布须先把它改为读 `results.jsonl` 的 `role`。

同一份快照的 test 分片由 `rollout/reset_check.py` 消费，只做 make / reset / close，证明能建环境——不能当成能完成任务或能出 HDF5。策略侧未来入口同样只认这一份读取契约。

## 八、落地命令

两个阶段各一条入口，均在仓库根目录用 `uv` 启动：

```bash
uv run --no-sync python -m scripts.injection.candidates --run-id <新运行编号> \
  --contract scripts/configs/newtask-v2/injection_contract_v3.json \
  --delivery-config scripts/configs/newtask-v2/delivery_400.json
```

```bash
uv run --no-sync python -m scripts.injection.rollout --run-id <编号> --tier <每卡worker数> --gpus 0,1
```

已有候选禁止覆盖，失败重试用新编号；正式大规模仿真前先跑单组、单条、单 worker 冒烟。运行编号、产物布局、续跑与恢复协议、角色与配额规则、图表与报告口径等运维细节，见 `INJECTION_REFACTOR_PLAN.md` 与 `docs/validation/newtask-v2/20260917-injection-refactor/README.md`；本文件只讲注入原理。
