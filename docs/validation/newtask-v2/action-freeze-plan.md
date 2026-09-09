# episode 对象与动作冻结扩展：实施与验收计划

状态：用户已批准实施；完整五项对拍必须重新执行，不沿用旧结果。

## 用户要求

- 「固定内容需要加入VideoUnmaskSwap VideoRepick的swap对象 pick起来的目标对象 RouteStick的实际游走动作」
- 「仍然是从冻结快照读取 但你要做到固定这些」
- 「和现在的机制一样！都是按episode冻结！你为什么没看清楚`!」
- 确认「对，沿用配置与 seed」：不新增逐 episode 结果表。
- 「所有的plan都要包含技术细节！」
- 「仍然要做和原先一样的对拍测试」
- 最终指令「PLEASE IMPLEMENT THIS PLAN: # 扩展冻结配置，并完整重跑原有五项对拍」。

## 技术实现

1. schema 3 在 parameters 中新增 VideoUnmaskSwap/VideoRepick 的 object_selection、swap_selection，以及 RouteStick.walk。原调用点读取操作元；原 generator、调用形状、顺序及数值类型保持不变。具体字段与绑定语义见 scripts/README.md 的对象与动作表。
2. 视频任务保留原索引映射；实际抓取的 func、solve、segment、描述及失败判定一致。最近邻仍在原 step 的交换窗口内首次确定，使用 XY norm 与严格小于比较，等距保留首个对象。
3. 路线继续按线性邻居生成，steps+1 个节点与 steps 个方向；单候选仍消费随机数，端点无其他邻居时回退。方向阈值允许 [0,1] 有限数值，其余新策略只接受原值。
4. AST 分别覆盖旧基线和已存在 NATIVE_SAMPLING 但没有新块的版本。历史规则必须由原 AST 证明，不能回填当前默认值。结构、类型、策略和来源指纹均检查；任务直接构造也校验。
5. 测试观察器在原任务命名空间包装既有事件，只读目标、swap_schedule、selected_buttons、swing_directions 和任务绑定。物体按生成列表索引识别；不增加 reset/evaluate/抽样/物理步。

## 完整对拍

- A1/A2：94449db0a068a6b454b55a13ebd48f0394d89cc8 原基线两次独立运行；B：本轮默认配置；C：本轮显式 schema 3。逐格比较 A1-A2、A1-B、A1-C、B-C。
- 冻结 cases.json 的 15 格：BinFill 三难度乘 dynamic 两分支（medium/True 用 ep2，其余沿原表）；另三任务各三难度。全部重新生成，共 60 次。
- ①：③通过后取三路关键帧并集及前后邻帧，正面与腕部无损 PNG，全量出图并逐图查看，记录散列与目视结论。
- ②：构造、两次初始化、reset、逐步状态及事件全部比较；新增抓取对象、实际交换双方和逐段路线方向证据。
- ③：原始 HDF5 全字段、逐元素、浮点按位模式比较；15 格隔离合并后重复比较，不能将不同难度的同 episode 编号混入一份合并输入。
- ④：完整随机调用参数、结果和前后状态，覆盖局部/实例 generator、全局 Torch、NumPy；保留拒绝采样与单候选调用。
- ⑤：同一真实 worker 运行 BinFill ep0 → VideoRepick ep0 → BinFill ep0；默认、显式配置及原基线参照，核对 PID、配置散列、缓存与独立产物。
- 原版无 RRT* 回退且自身逐位一致才作严格基线。失败与回退保留记录，按同格扫描替补；穷尽则受阻，不自行增加容差。
- 保留重试三路、16 任务显式配置 smoke、比较器反例与离线证据复验。

## 执行与留档

先定向轻量测试、原版观察器校准、BinFill 单局四路，再启动完整矩阵和后续检查。
代码改动后的短测不超过 5 分钟；完整对拍是独立长任务，使用 detached tmux、pipefail、
PYTHONUNBUFFERED、tee 与 EXIT_CODE。原始产物和日志留 artifacts/，报告与轻量证据留
docs/validation/newtask-v2/ 的独立运行目录。代码短测后提交；完整证据完成再提交，不推送。
