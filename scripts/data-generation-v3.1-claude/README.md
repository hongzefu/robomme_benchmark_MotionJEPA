# 数据生成 v3.1-claude：纯 CV 删臂 + 物体零误删 + 黑指尖保留

本目录在 [v3-claude](../data-generation-v3-claude/README.md) 的基础上换口径重做：
仍然**只用 RGB + 通用 computer vision 规则**（不碰 segmentation / depth / 任何仿真
真值），仍然输出红遮罩可视化（不重新仿真、不写 h5），但删除策略的优先级整个反
过来——v3 是「多删可接受、漏删不可接受」，v3.1 是：

1. **HARD A——任务物体零误删**：桌面上与被操作的任务物体一个像素都不得涂红，
   包括被夹持 / 推动 / 拖拽的接触帧；贴着物体边缘的红圈也算违规。
2. **HARD B——夹爪黑色指尖垫保留**：14 个夹爪任务里手指末端的黑色接触面（定义
   参考 v2.1：三通道均值 ≤100 的手指端部；但**定位纯 CV**，不用 v2.1 的
   segmentation）不得删除；手掌与腕部支架上的其他黑块不属于指尖，照删。
3. **STICK——panda_stick 任务（PatternLock / RouteStick）机器人全删**：含 stick
   工具，什么都不保留（用户追加口径：这两个任务不用管黑头）。
4. **SOFT——满足以上前提下机器人删得尽可能干净**。多删背景可容忍但要尽量少；
   「机器人残留」与「物体受损」二选一时永远牺牲前者。

## 方法：七变体锦标赛 + 两轮修复

按仓库 Workflow 规约跑了一次 29-agent 锦标赛（1 opus 方案设计 → 7 sonnet 并行
实现 → 14 sonnet 双盲目视验证（每变体 2 人 × 8 任务）→ 最优 2 个修复复验 →
1 opus 终评），七个机制不同的候选：

| 变体（`variants/`） | 机制一句话 | 第一轮硬伤 | 终评结论 |
|---|---|---:|---|
| `watershed_barrier` 🏆 | 背景/物体/臂三类种子 + `cv2.watershed`，边界交给真实图像边缘，零膨胀 | 2 | **胜出**：唯一两个 STICK 任务全过，修复后硬伤最少、净度/稳定双高 |
| `flow_affine_split` | 拟合臂的单一全局仿射运动，残差外点判物体并随光流前推 | 1→6 | 第一轮领跑、第二轮被打穿：被夹无彩物体与臂刚性同步、被判内点整块删 |
| `consensus_vote` | 五路正证据全票才删、四路物体证据一票否决 | 4 | 净度全场最高，但 stick 杆件近按钮时系统性停删 |
| `antiabsorb_antiring` | v3 外科切除：吸附/常驻区/膨胀三把杀器各加闸门 | 6 | 稳定性最高，但继承 v3 无彩接触失效（peg 整根被吞 ×3） |
| `arm_proof_gate` | 锚定域降级为 ROI、逐像素自证是臂 + 四条否决 | 6 | 三个历史 bug 全修，但灰白按钮贴近即被吞 |
| `limb_skeleton_geom` | 宽度单调测地生长，越出肢体几何判物体 | 8 | 思路最正交，几何假设在杆式机器人上直接反转 |
| `object_registry_track` | 显式物体登记册 + 跨接触跟踪做集合减法 | 22 | 并块即整删，被证伪 |

关键教训：**七个方案对有彩物体的保护全部奏效，真正的战场是无彩物体**（灰白
按钮、白 cup、淡紫 peg、白缆线）——渲染器自带的 `red_on_saturated` 红灯（S≥60）
对它们完全失明，全靠人眼逐像素抓。白色物体与白色臂壳在外观上（同为无彩、V 同在
230 平台）被证实**不可分**，只能靠几何/拓扑口径兜底。

胜出后又在主会话做了第二轮五项修复（根因全部像素级定位，细节见
`variants/watershed_barrier.py` 模块 docstring 与各实现处注释）：

1. **mid_sat 护栏**（HARD A）：S≥28 一律不判臂——堵住旧护栏 S∈(20,60) 的低饱和
   真空带（InsertPeg 淡紫 peg 误删 151px → 0）；
2. **内嵌暗块释放**（HARD A）：小/窄/暗且四周多为亮无彩表面的连通块拒删
   （ButtonUnmaskSwap 白 cup 沟槽蛇形误删 → 0）；
3. **指尖成对补全 + 领跑者兜底**（HARD B）：修「成对垫块只保一枚/全灭」的测地
   非对称（7 例实测全部恢复成对；垫块与腕块 V 分布实测同平台不可分，成对补全
   只靠距离几何、每帧最多补一枚）；
4. **带护栏 stuck 规则**（SOFT）：臂长驻被烤进背景板导致的整块留灰救回
   （VideoUnmask removed_fraction 0.048→0.103，复验净度 2/10 的根因）；
5. **底座部件级补涂**（SOFT/STICK）：occluder 部件完整落在顶部中央标准包络内才
   恒红（StopCube 被黑装置拉宽的部件自动拒涂，构造上不碰装置）。

## 结构

| 文件 | 作用 |
|---|---|
| `cv_base.py` | v3 算法逐字拷贝作共享基座（变体不得修改，按需 import 或拷走改） |
| `cv_base_params.json` | 基座参数（沿用 v3 收敛值） |
| `variants/__init__.py` | 变体契约（`NAME` / `DESCRIPTION` / `compute_masks` 三要素）与口径权威文本 |
| `variants/watershed_barrier.py` | **胜出变体（默认）**，自有参数集中在模块内 `P` 字典 |
| `variants/*.py` 其余六个 | 落选候选，保留作机制对照与再研究 |
| `variants/v3_baseline.py` | v3 原样对照基线（不满足 v3.1 硬约束，冒烟/对照用） |
| `render_variant_outputs.py` | 统一渲染入口：`--variant` 插件加载，出 preview / grid / summary |
| `../../tests/lightweight/test_arm_removal_v31_logic.py` | AST 防火墙：import 白名单 + 分割标识符禁用 + 变体契约 |

## 用法

```bash
# 胜出变体全量 16 任务（约 40 秒，纯 CPU；产物写 outputs/watershed_barrier/）
uv run --no-sync python scripts/data-generation-v3.1-claude/render_variant_outputs.py \
  --variant watershed_barrier --h5 artifacts/generated/v21-16env/record_dataset_*.h5 --no-grid

# 加全帧网格拼图（时序稳定性判读用，单张可达数十 MB，不入 git）：去掉 --no-grid
# 换变体对照：--variant consensus_vote 等；防火墙测试：
uv run --no-sync python -m pytest tests/lightweight/test_arm_removal_v31_logic.py -q
```

产物（`outputs/<variant>/`）：

- `<Task>_ep0_preview.png`：8 行均匀抽帧三联网格——原图 | 红遮罩 | mask
  （**白=删除、绿=保留的指尖垫**，绿色标注是 HARD B 的目视证据）；
- `summary.json`：逐任务 stats + `red_on_saturated`（彩色物体误删红灯，当前
  结构性恒 0）+ `tip_pixels_*`（指尖计数）+ stuck/base/released 各机制读数。

时序口径与 v3 相同：读 `v21-16env` 现成 h5、episode_0、时序降采样 4 倍、256×256。

## 实测结论（2026-08-10，16 任务 × episode_0）

- 全部跑通：删除占比 2.5%–10.3%（StopCube 最低——该 episode 115 帧里 95 帧臂
  不在画面内，属取景问题，已复核）；单任务 0.5–6.4 秒，合计约 40 秒；
- `red_on_saturated` 全 16 任务恒 0（mid_sat 护栏使其结构性成立，不再依赖抽样）；
- 两个 stick 任务 `tip_frames_nonzero` 恒 0（STICK 判据构造性满足）；
- 锦标赛复验点名的全部硬伤帧逐一像素复核归零：InsertPeg t=136 peg 误删 151→0、
  ButtonUnmaskSwap t=364 cup 蛇形 →0、VideoRepick t=216 / BinFill t=156 与 t=468 /
  ButtonUnmask t=40 与 t=164 / MoveCube t=120 / PickHighlight t=216 垫块全部恢复
  成对、SwingXtimes t=204 红方块啃边保持 0、VideoPlaceOrder 被夹蓝方块全程完好、
  VideoUnmaskSwap t=324 被夹白盒完好。

### 已知有界残留（诚实清单，均已定位根因）

1. **StopCube t=432 一块约 33px 的腕部黑块被成对规则误保**：腕块与垫块的暗像素
   V 分布实测完全重叠（同为 [38,60] 平台），外观不可分，距离几何（40px 上限）
   只能排除大部分误拉，此帧腕块距真垫 33.5px、在阈值内。
2. **被夹白色物体的边缘暗沟槽可能以绿色「指尖」标注保留**（ButtonUnmaskSwap
   t=364）：像素结果正确（不删），语义标注不纯。
3. **ButtonUnmaskSwap t=512 前缩指扇整块留灰**：该相位段夹爪停驻被烤进背景板且
   众数占比 ≈1，stuck 规则（要求占比 <0.95）不触发；锦标赛双验证者独立结论
   「无廉价安全解」，属 SOFT 留灰而非物体损伤。
4. **白色/浅灰机器人外壳件部分留灰**（RouteStick 安装圆钮、PatternLock label-bar
   等）：实测 RGB 与白色任务物体同为 (231,231,231) 硬平台，`white_mask` 护栏
   （HARD A 的支柱之一）无法区分，属「牺牲删除、绝不伤物」的直接代价。
5. **手掌 ≤130px 小黑块偶尔漏删**：内嵌暗块释放（修复 2）的声明代价。
6. **臂边缘 1px 抗锯齿灰边**：零膨胀设计的固有特性（膨胀正是 v3 红圈的来源，
   不回加）。
7. **复验覆盖为每任务 8 行采样帧 + 定点加密**，未做全帧逐像素审计；InsertPeg
   类「8 帧仅 1 帧失效」的间歇问题不能宣称绝对零残留，只能宣称已知案例全部
   归零且防回归判据（`red_on_saturated` 恒 0、stick 任务 tip 恒 0）结构性成立。
