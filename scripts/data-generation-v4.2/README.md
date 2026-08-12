# 数据生成 v4.2：只保留「否决全开」一条口径的机械臂标定

本目录回答的问题与 [v4](../data-generation-v4/README.md) /
[v4.1](../data-generation-v4.1/README.md) 完全相同——**把 RoboMME `front_rgb` 里的机械臂
标出来、涂成纯红 (255,0,0)**——判别规则与四条形态学规则**一个字都没改**，唯一的变化是
**把「不带混合支撑否决」的对照口径整条删掉**，从此本链路只有一条口径。

| 方面 | v4.1 | **v4.2（本目录）** |
|---|---|---|
| 判别口径 | 否决默认开，但保留 `veto_shared=False` 对照口径，每个出图入口出两版 | **只有否决全开这一条**，无开关、无对照版 |
| 误标物体的守法 | 写进 `metrics.json`，人自己看 | **代码硬闸门**：非 0 就打明细并以非零退出码退出 |
| 对比出图 | `compare_veto.py`，三栏 veto \| noveto \| GT | `compare_gt.py`，**两栏 预测 \| GT** |
| 颜色分布出图 | 两版分布图 + 否决翻转差异图 | **一张判决分布图**；否决代价改用**纯支撑集**口径统计 |
| 走查出图 | 上下两行 = noveto / veto，参照带 6 格 | **单行走查**，参照带 4 格 |
| 拟合侧 | —— | **逐字未变**，颜色表与 v4.1 逐位相同（已对拍） |

用户 2026-08-12 关键决策原话：

> 「生成 v4.2 只使用 veto 全规则完整的规则 不要再保留 no veto 产物重新生成 dataset
> 不要再重造了 所有 noveto 内容全部删除 作为用户关键决策 因为后续还需要对齐 wan-vae
> 的编码网格 所以在此不保留两个变体 太复杂了 到时候 wan-vae 还会从网格上保守 降低采样」

> 「注意 v4.2 的 veto 要和之前的 veto 保留一个刚性原则 不得判错物体加入 robot arm
> 注意这里的判错用 ground truth 得到」

即：标定结果后续要对齐 Wan VAE 的编码网格（届时还会在网格层面进一步保守、降低采样），
两个变体并存会让网格对齐的口径复杂度翻倍，因此就此收敛到一条。

---

## 〇、刚性原则（第一判据，凌驾于其它一切指标）

> **不得把物体判错成 robot arm。「判错」以 ground truth 为准。**

设 GT 三类标签 `gt(p) ∈ {背景, 物体, 臂}`（由 `labels_from_segmentation` 从
`obs/front_camera_segmentation` 得到），第 t 帧最终标定的像素集合为 `D_t`，则

```
false_object = Σ_t #{ p ∈ D_t : gt(p) = 物体 }   ≡ 0
```

三件事必须一起成立，缺一条这条原则就是空话：

1. **判定口径偏保守，不偏宽松。** GT 侧的「物体」集合含**兜底项**：`setup/flow_objects`
   与 `setup/flow_excluded` 是 `reset()` 那一刻对 `segmentation_id_map` 的快照，
   **episode 运行中动态创建的 seg id 不在里面**（实测 5 个任务会出现：InsertPeg 箱顶
   插孔标记、PickHighlight 绿色高亮块、SwingXtimes 靶心圆盘、PatternLock 图案连线节点
   id 涨到 572、RouteStick 路线曲线涨到 710）。这些 id **一律兜底归物体**。也就是说
   凡认不出的东西都算物体，红线只会更严不会更松；这部分像素同时被 `uncovered_mask`
   单独计数，兜底不许静默。

2. **在拟合集上它是恒等式，不是调出来的巧合。** 由下面第二节的退化引理，判臂颜色恒满足
   `N₁(c) = 0`，而 `N₁` 已经把 GT 物体像素全部计入，所以判臂颜色在拟合集上的物体像素
   **恰为 0**。评估集上唯一可能的漏洞是「拟合集里只在臂上见过、评估集里却出现在物体上」
   的颜色（未见色走 `UNKNOWN` 不标，不构成误标来源）——**正是这一格必须逐次实测**。

3. **落成 fail-loud 硬闸门，且刻意不提供豁免开关。** `render_outputs.enforce_no_false_object`
   是唯一实现，被两个评估入口共用：
   - `render_outputs.py`（留出集 train ep10-19 全帧）**逐 episode** 校验；
   - `compare_gt.py`（train ep0）**逐任务**校验，GT 栏按构造恒为 0 不参与。

   非 0 时打印逐条明细并让 `main()` 返回 1（= 进程退出码非 0）。
   背景误标 `false_background_pixels` 继续记录但**不设闸门**——宗旨只针对物体。
   再加一道：`color_distribution.py` 跑完会断言「判臂颜色上的真实非臂像素 == 0」这个
   恒等式，被破坏就 `SystemExit`，用来兜住「颜色表或判别算式本身坏掉」的情形。

---

## 一、口径（用户逐条拍板，2026-08-12）

1. **标定集 = benchmark val split ep 0–9**（每任务 10 条，共 160 episode）。三套 split
   （`src/robomme/env_metadata/{train,val,test}/`）seed 固定；val 编码为
   `1_000_000 + task_index*10000 + ep*100 + retry`。标定数据集
   `artifacts/generated/v4seg-16env-val10ep` 由本目录 `generate_dataset.py --split val`
   生成，**v4.2 不重造数据集**，直接复用。
2. **GT 只允许提供两个场景级分布 + 臂分布**，不提供物体级逐像素分割（v4.1 起的削弱口径，
   现实语义 = 拿得到「没有臂的空场景」和「摆了物体但没有臂的场景」两种画面级监督，
   外加臂自己的外观样本）。
3. **判别规则 = 归一化似然 argmax + 混合支撑否决**，两步都是规则的固有组成部分，无开关。
4. **评估集**：train split ep 0（两栏对比图与走查图）、train split ep 10–19（留出集全帧
   指标）。两者都与标定集零重叠。

---

## 二、判别规则的数学精确表述

### 2.1 记号

- 像素域 `Ω = {0,…,255} × {0,…,255}`（`front_rgb` 就是 256×256），像素 `p ∈ Ω`。
- **颜色键**（`pack_rgb`，24 位无损打包成 `uint32`）：

  ```
  k(p) = 2¹⁶·R(p) + 2⁸·G(p) + B(p) ∈ [0, 2²⁴)
  ```

  输入必须是 `(H, W, 3)` 且 dtype 恰为 `uint8`，否则 fail-loud。用精确颜色而不是直方图
  bin 或高斯，是因为它一个超参都不需要：ManiSkill 渲染确定性极强，颜色本身就是离散量。
- 拟合集 `F` = 标定集全部 160 个 episode 的全部帧的全部像素。

### 2.2 GT seg_id → 三个 id 集合（`class_ids_from_setup`）

以 `E = setup/flow_excluded`、`O = setup/flow_objects` 为源：

```
A_id = { seg_id(e) : e ∈ E, reason(e) = "robot_link" }  ∪  { seg_id(o) : o ∈ O, kind(o) = "tcp" }
B_id = { 0 }  ∪  { seg_id(e) : e ∈ E, reason(e) = "background_prop" }
O_id = { seg_id(o) : o ∈ O, kind(o) ≠ "tcp" }
```

- `seg_id 0` = 没有任何几何体命中的像素，归背景；
- `kind == "tcp"`（`panda_hand_tcp`）是夹爪工具中心点，一个不参与渲染的虚拟坐标点，
  语义上属于机器人，**归臂**（实测其 seg_id 从不出现在 segmentation 图里，纯防御分支）；
- 未知的 `reason` 直接抛错；三集合两两不交由断言把关。

GT 三类标签图（`labels_from_segmentation`，dtype `int8`）：

```
gt(p) = 臂     if seg(p) ∈ A_id
        背景   if seg(p) ∈ B_id
        物体   否则                      ← 兜底：不在任何集合里的 seg id 一律归物体
```

### 2.3 三列重叠计数（`accumulate_frames`）

对每个颜色键 `c`：

```
N₀(c) = #{ p ∈ F : k(p) = c ∧ gt(p) = 背景 }                 （纯背景列）
N₁(c) = #{ p ∈ F : k(p) = c ∧ gt(p) ∈ {背景, 物体} }          （背景∪物体混合列）
N₂(c) = #{ p ∈ F : k(p) = c ∧ gt(p) = 臂 }                    （机械臂列）
```

**背景像素同时计入列 0 与列 1**，这就是「重叠计数」。两条由构造直接得到的性质，后面全靠它们：

```
(P1)  N₁(c) ≥ N₀(c)  ∀c        ⟹  supp(N₀) ⊆ supp(N₁)
(P2)  Σ_c N₁(c) + Σ_c N₂(c) = |F|      （列 1 与列 2 恰好各记一次，不重不漏）
```

其中 `supp(N_j) = { c : N_j(c) > 0 }`。列总量记 `T_j = Σ_c N_j(c)`。

⚠ **不做「混合 − 背景」减法**：两列逐色对减等于变相恢复物体分布，违背「物体类先验未知」
的设定。归一化似然是不动用先验时唯一诚实的比较方式。

### 2.4 逐像素判决（`ColorModel.classify`）

对像素 `p`，令 `c = k(p)`，按顺序执行：

**第 1 步 查表。** `searchsorted` 在升序 `colors` 里定位后**验命中**；
未命中即 `c ∉ supp(N₀) ∪ supp(N₁) ∪ supp(N₂)`，最终标签置 `UNKNOWN = −1`。

**第 2 步 归一化似然 argmax。** 逐列除以本列总量：

```
P(c | j) = N_j(c) / T_j ,   j ∈ {0=背景, 1=混合, 2=臂}
j*(c) = min ( argmax_j P(c | j) )
```

`min` 是因为 `np.argmax` 取**首个**最大值下标，而列序恰为 (背景, 混合, 臂)——
**平手一律偏向非臂，判臂必须严格胜出**。若某列 `T_j = 0` 直接抛错，不静默。

**第 3 步 混合支撑否决。**

```
ŷ(c) = 混合(1)   if j*(c) = 臂 ∧ N₁(c) > 0
       j*(c)     否则
```

门限就是「出现过 / 没出现过」，即 0，不引入任何新阈值。理由：该颜色只要在无臂场景
（背景∪物体）里出现过，就无法排除它属于物体，按「绝不误标物体」倒向保守。

**第 4 步 未见色覆盖。** `c` 未命中 ⟹ `ŷ(c) = UNKNOWN(−1)`，下游一律按「不是机械臂」处理。

输出标签图 `L: Ω → {−1, 0, 1, 2}`，dtype `int8`。

> 臂列的存在是「未见色保守」得以成立的前提：若只有两个分布，臂只能被定义成「未被解释的
> 颜色」，未见色就会被迫判臂，失效方向与宗旨相反。

### 2.5 退化引理：似然的数值根本不进臂的裁决

> **引理.** 在 (P1) 成立的前提下，
> ```
> ŷ(c) = 臂  ⟺  N₁(c) = 0  ∧  N₂(c) > 0
> ```
>
> **证明.**
> (⇐) 设 `N₁(c) = 0`。由 (P1) 得 `N₀(c) = 0`，故 `P(c|0) = P(c|1) = 0`；又
> `N₂(c) > 0 ⟹ P(c|2) > 0`，于是 `j*(c) = 臂`。且 `N₁(c) = 0` 不满足否决条件，
> 第 3 步不改判。故 `ŷ(c) = 臂`。
> (⇒) 设 `ŷ(c) = 臂`。第 3 步没把它改判，故 `N₁(c) = 0`；第 2 步选中臂，故
> `P(c|2) > 0`，即 `N₂(c) > 0`。∎

三条推论，都是 v4.2 判读的基石：

- **推论 1（红线是恒等式）.** 判臂颜色上的拟合集非臂像素
  `Σ_{ŷ(c)=臂} N₁(c) = 0`。所以「颜色阶段精确率上界 = 1.000」不是经验数字，是恒等式。
  代码仍把它算出来打印，是**当自校验用**——不为 0 就说明表或算式坏了，直接 `SystemExit`。
- **推论 2（漏标代价的闭式）.** 颜色阶段丢掉的臂像素恰为臂∩混合共享色上的臂像素：
  `Σ_{c ∈ supp(N₁) ∩ supp(N₂)} N₂(c)`。这是**纯支撑集**表达式，不需要「未否决的 argmax」。
- **推论 3（似然只管一个下游不看的区分）.** 似然大小与类先验只影响「背景 vs 混合」的划分，
  而下游只关心「是不是臂」。这正是「把监督从 v4 的三类分割削弱到两分布 + 臂几乎零代价」
  的机理——v4.1 观察到了这个现象，这里给出它的证明。

⚠ 代码**仍保留完整的 argmax + 否决两步**，不按引理化简。规则要写成它的完整形态；
等价性由 `tests/lightweight/test_arm_mask_v4_2.py::test_判臂等价于纯支撑判据` 钉死。

实测核验（本目录 `outputs/color_model.npz`，16297 色）：完整流程判臂 **1670** 色，
纯支撑判据 `N₁=0 ∧ N₂>0` 判臂 **1670** 色，两者**逐位一致**；且
`1796（臂支撑色）− 126（臂∩混合共享色）= 1670`。

---

## 三、四条形态学规则的数学精确表述

输入只有上一步的标签图，**完全不看 ground truth**。

### 3.1 记号与结构元

一个相位段内的帧序 `t = 0,…,T−1`，标签图 `L_t : Ω → {−1,0,1,2}`。**候选集**：

```
C_t = { p ∈ Ω : L_t(p) = 臂 }
```

结构元固定为 **3×3 全 1 方形（八邻域）**，不作为可调项：

```
S = { (dy, dx) ∈ ℤ² : |dy| ≤ 1 , |dx| ≤ 1 }        |S| = 9
```

腐蚀与膨胀（`cv2.erode` / `cv2.dilate` 的集合定义）：

```
X ⊖ S = { p : p + S ⊆ X }          X ⊕ S = { p + s : p ∈ X , s ∈ S }
```

⚠ 边界语义按 OpenCV 形态学的默认行为：**腐蚀时把画面外视作前景**，所以贴着画面边缘的
前景不会被边界削掉。这一点对第 ② 条的「触到第 0 行」判定是有影响的，属于口径的一部分。
实测核验（`cv2.erode`，3×3 全 1，`iterations=1`，前景块 `m[0:3, 0:3]`）：

```
原图 [[1 1 1 0 …]      腐蚀后 [[1 1 0 0 …]
      [1 1 1 0 …]              [1 1 0 0 …]
      [1 1 1 0 …]              [0 0 0 0 …]
      [0 0 0 0 …]]             [0 0 0 0 …]]
```

`(0,0)` 与 `(0,1)` 得以保留，正是因为上边界与左边界外侧被当成前景；若当成背景，整块
贴边前景会被腐蚀掉一圈，② 的触顶判定随之改变。

### 3.2 四条规则

**① 开运算**（`_open`，`cv2.morphologyEx(MORPH_OPEN, S, iterations=1)`）

```
A_t = (C_t ⊖ S) ⊕ S                    A_t ⊆ C_t
```

去掉抗锯齿边缘与阴影上零星的臂色噪点。先腐蚀保证只会变小或持平，不会往物体那边长。
（OpenCV 的 `iterations = n` 语义是「腐蚀 n 次再膨胀 n 次」，不是做 n 次完整开运算；
默认 `n = 1`，两者等价。）

**② 触顶连通域**（`_keep_top_entering`，`cv2.connectedComponents(connectivity=8)`）

令 `R₀ = { (0, x) : 0 ≤ x < 256 }` 为画面**第 0 行**（恰好一行，不是前 N 行），
`CC₈(A_t)` 为 `A_t` 的八连通分量族：

```
B_t = ⋃ { K ∈ CC₈(A_t) : K ∩ R₀ ≠ ∅ }              B_t ⊆ A_t
```

机械臂根部固定在画面顶部、整条臂从上方伸进来；桌面上的任务物体不触顶。这一条是
「不误标物体」最主要的结构性保障，比任何颜色阈值都硬。空输入或无触顶分量时返回空集。

**③ 时间平滑**（`_temporal_majority`，窗口 `W = 3`，`h = W // 2 = 1`）

窗口在序列两端**自动截断、不补边**：

```
𝒲(t) = { s ∈ ℤ : max(0, t−h) ≤ s < min(T, t+h+1) }        k_t = |𝒲(t)|
M_t  = { p ∈ Ω : 2 · Σ_{s ∈ 𝒲(t)} 1[ p ∈ B_s ] > k_t }     （严格多数）
```

逐情形展开（`W = 3`）：`T ≥ 3` 的内部帧 `k_t = 3`，需 3 帧中至少 2 帧命中；
首尾帧 `k_t = 2`，需 2 帧全中，即退化成 `B₀ ∩ B₁`（尾端同理）；
`T = 2` 时两帧输出都是 `B₀ ∩ B₁`；`T = 1` 时恒等。
`MaskParams` 强制时间窗为**正奇数**，否则抛错。

⚠ **③ 是四条里唯一不单调的一条**：多数表决会把「本帧不在候选、前后帧在」的像素
**补进来**，即一般地 `M_t ⊄ B_t`。这不是 bug，是多数表决的定义使然。

**④ 保守收缩**（`_erode`，白名单交在前、腐蚀在后）

```
D_t = ( M_t ∩ C_t ) ⊖ S
```

白名单 `∩ C_t` = **只保留当前帧自己被判成机械臂的像素**，一次性扣掉判为混合的、判为
背景的、以及未见色 `UNKNOWN` 的像素（哪怕它与臂连成一片，即接触帧）。

⚠ 这里写成白名单而不是黑名单 `∖ 物体` 是**必须的**，v4.1 留出集实测抓到过反例：
③ 的多数表决把 InsertPeg 的 **292 个**像素补了进来，它们的颜色（品红系 `(135,38,114)` 等）
在拟合表里压根没出现过。收紧成白名单之后，③ 就只能删不能加。

### 3.3 整条链的单调性

> **命题.** `D_t ⊆ C_t` 恒成立。
>
> **证明.** `D_t = (M_t ∩ C_t) ⊖ S ⊆ M_t ∩ C_t ⊆ C_t`（腐蚀 anti-extensive，交集含于分量）。∎

即**整条链相对候选集是单调收缩的**，正对应本链路的宗旨——绝不误标物体，允许少量机械臂
没被标进去。但请注意这个精确的说法：

- ①②④ **逐条**单调（`A_t ⊆ C_t`、`B_t ⊆ A_t`、`D_t ⊆ M_t ∩ C_t`）；
- ③ **单独看不单调**，是 ④ 的白名单把它兜回来的；
- 所以「每一条规则都只会让标定区域变小或持平」这句话**只对 ①②④ 成立**，对整条链成立，
  但**对 ③ 不成立**。`<Task>_walkthrough.png` 每格脚注的带符号增量把这件事画了出来
  （③ 那格出现 `+n` 就是它在补像素），`walkthrough.json` 的 `该帧时间平滑增量` 字段
  是它的机读版本。

### 3.4 相位切段

`info/is_video_demo` 标出的两个相位之间场景会重摆，跨相位做时间平滑等于把两个不同场景
的帧混在一起投票。因此把 `[0, T)` 按 `bool(is_video_demo[t])` 的**极大等值连续段**切开，
每段独立跑 ①–④，段间互不影响（帧数与相位标记数对不上时抛错，切段没盖全帧时抛错）。

### 3.5 输出

`apply_red_mask` 把 `D_t` 内的像素涂成 `RED = (255, 0, 0)`，其余像素与原图**逐位相同**
（写在副本上，不改输入数组）。

### 3.6 三个可调项

只有三个整数，且都是形态学的最小配置：开运算 1 次、时间窗 3 帧、最终腐蚀 1 次。
**它们不是「阈值」**——没有任何一个是在某个连续量上切一刀，调大调小只改变收缩的力度，
不改变判据本身。整条链路的**浮点阈值数量为 0**。

---

## 四、结构

| 文件 | 作用 |
|---|---|
| `record_wrapper_v4.py` | 薄子类，只新增 `obs/front_camera_segmentation` 落盘（沿用 v4，逐字未变） |
| `generate_dataset.py` | 生成入口（支持 `--split {train,val,test}`） |
| `color_model.py` | 两分布 + 臂的颜色表拟合 / 推理（**唯一碰 GT 的模块**），含退化引理 |
| `arm_mask_v4.py` | 四条形态学规则 + 涂红（与 v4 / v4.1 运算逐字相同） |
| `fit_color_model.py` | 拟合入口 |
| `render_outputs.py` | 留出集推理 + 对 GT 验证 + preview 出图，**刚性闸门 `enforce_no_false_object` 的定义处** |
| `compare_gt.py` | **两栏对比出图入口**（预测 / GT，train ep0），复用同一个闸门 |
| `color_distribution.py` | **颜色判决分布出图入口**（一张图 + `stats.json`；不读 h5，只读颜色表） |
| `segmentation_walkthrough.py` | **分割过程走查出图入口**（真实帧逐阶段拆解 + 逐像素举例） |
| `reports/color_distribution_report.md` | 上面两个入口的**判读报告** |
| `../../tests/lightweight/test_arm_mask_v4_2.py` | GT 映射、重叠计数、判臂等价于纯支撑判据、四条规则的逻辑测试 |
| `../../tests/lightweight/test_color_distribution_v4_2.py` | 出图链路的复算对拍与闸门测试 |

⚠ `color_model` / `arm_mask_v4` 这两个模块名在 v4、v4.1、v4.2 **三个目录里同名**，
测试文件必须用各自的 `sys.modules` 隔离导入器，否则按导入顺序会静默拿到错的实现。

---

## 五、用法

```bash
# 1.（一般不用跑）生成带 GT segmentation 的 val split 标定数据集
#    ⚠ 正式生成前须与用户确认新的 --output-dir 名字；v4.2 直接复用 v4.1 生成的同名产物
uv run --locked scripts/data-generation-v4.2/generate_dataset.py \
  --output-dir artifacts/generated/v4seg-16env-val10ep --env all --episodes 10 \
  --workers 16 --gpus 0,1 --split val \
  --reference-root /data/hongzefu/robomme_data_h5 --no-reference-validation

# 2. 在标定集（val ep 0-9）上拟合两分布 + 臂颜色表（单进程，实测约 19 分钟）
uv run --no-sync python scripts/data-generation-v4.2/fit_color_model.py \
  --h5 'artifacts/generated/v4seg-16env-val10ep/record_dataset_*.h5' \
  --episodes 0-9 --out scripts/data-generation-v4.2/outputs/color_model.npz

# 3. 留出集全帧指标 + preview（train ep10-19，160 episode，含刚性闸门）
uv run --no-sync python scripts/data-generation-v4.2/render_outputs.py \
  --h5 'artifacts/generated/v4seg-16env-20ep/record_dataset_*.h5' \
  --episodes 10-19 --out scripts/data-generation-v4.2/outputs/holdout

# 4. 两栏对比出图（预测 | GT，train ep0，16 张 + metrics.json，含刚性闸门）
uv run --no-sync python scripts/data-generation-v4.2/compare_gt.py \
  --h5 'artifacts/generated/v4seg-16env-20ep/record_dataset_*.h5' \
  --out scripts/data-generation-v4.2/outputs/compare_gt

# 5. 颜色判决分布出图（一张图 + stats.json；只读颜色表，不碰 h5）
uv run --no-sync python scripts/data-generation-v4.2/color_distribution.py

# 6. 分割过程走查出图（16 任务 × 留出集 ep10，每任务两张）
uv run --no-sync python scripts/data-generation-v4.2/segmentation_walkthrough.py

# 7. 单元测试（v4 / v4.1 / v4.2 三套一起跑，互不污染）
uv run --no-sync python -m pytest tests/lightweight/test_arm_mask_v4.py \
  tests/lightweight/test_arm_mask_v4_1.py tests/lightweight/test_color_distribution.py \
  tests/lightweight/test_arm_mask_v4_2.py tests/lightweight/test_color_distribution_v4_2.py -q
```

两栏图（`outputs/compare_gt/<Task>_compare.png`）：每栏 8 帧 ×（原图 | 红遮罩 | 误差图）。
误差图配色：**白 = 标对的机械臂、红 = 误标到物体（核心红线）、黄 = 误标到背景、
蓝 = 漏标的机械臂**。GT 栏的红遮罩直接涂 GT 臂像素，误差图应全白（出图链路自校验）。

---

## 六、实测结论（2026-08-12，全部来自 v4.2 自己重新生成的产物）

### 6.1 颜色表与 v4.1 逐位相同（拟合口径逐字未变）

重新在 val ep0–9 全帧上拟合，单进程 **1140.1 秒**，**唯一颜色 16297 种**，npz 108 KB。
与 `../data-generation-v4.1/outputs/color_model.npz` 对拍：`schema_version`、`colors`、
`counts` **三项全部逐位相等**。v4.2 只改推理侧，拟合侧一个字没动，这条对拍把它坐实。

| 列 | 语义 | 像素数 | 支撑色数 |
|---|---|---:|---:|
| 列 0 | 纯背景 | 4,731,895,750 | 12,214 |
| 列 1 | 背景∪物体混合 | 4,846,769,500 | 14,627 |
| 列 2 | 机械臂 | 342,829,732 | 1,796 |

支撑交叠：**臂 ∩ 纯背景 = 0 色**，**臂 ∩ 混合 = 126 色**，臂独有 1670 色。
「臂与纯背景零共享」是整条链路能成立的结构性前提——臂的灰白只和**物体**撞色，
不和桌面背景撞色。

### 6.2 退化引理实测核验

| 项 | 值 |
|---|---:|
| 完整流程（argmax + 否决）判臂色数 | **1670** |
| 纯支撑判据 `N₁(c)=0 ∧ N₂(c)>0` 判臂色数 | **1670** |
| 两者逐位一致 | **是** |
| 判臂颜色上的真实臂像素 | 311,704,569 |
| **判臂颜色上的真实非臂像素** | **0**（推论 1，恒等式） |
| 颜色阶段召回上界 | 0.909211 |
| 颜色阶段精确率上界 | **1.000000** |

否决代价（推论 2 的闭式，纯支撑集口径）：**126 种**臂∩混合共享色带走
**31,125,163** 个臂像素 = 全部臂像素的 **9.0789%**（`1 − 0.090789 = 0.909211`，与召回
上界严丝合缝对上）；同时这 126 色上压着 **53,143,358** 个非臂像素——这就是它们必须被
挡下的理由。

### 6.3 留出集全帧（train ep10–19，160 episode / 77,272 帧）

| 指标 | 值 |
|---|---:|
| **误标物体像素（刚性红线）** | **0** |
| 误标背景像素 | **0** |
| **标定精确率** | **1.000000** |
| 机械臂召回 | 0.818412 |
| 存在物体误标的帧占比 | **0** |
| 未见颜色占比 | 0.1866% |
| GT 兜底（setup 未覆盖 seg id）像素 | 2,278,922，其中被误标进机械臂 **0** |

逐任务召回从 **0.684357**（StopCube）到 **0.851516**（MoveCube）。
闸门输出：`刚性红线通过：留出集逐 episode 共 160 项，GT 判定的误标物体像素全部为 0`。
耗时 41.0 秒（16 进程）。

⚠ 这三个数（0 / 1.000000 / 0.818412）与 v4.1 的 veto 口径**逐位相同**——同一张表、
同一条规则，本来就该相同；相同本身就是「v4.2 只删对照口径、没动判据」的实证。

### 6.4 train ep0 两栏对比（16 张 + metrics.json）

**16/16 任务误标物体 = 0**，GT 栏自校验误标也全为 0（出图链路自身没走样）。
逐任务召回 0.719397（StopCube）～ 0.854263（VideoUnmask）。耗时 10.1 秒。

### 6.5 分割过程走查（留出集 ep10，32 张）

16 个任务全部 `该帧误标物体 0 px`；逐阶段复算与 `arm_masks_for_episode` 的运行期
逐位断言全部通过。耗时 11.7 秒。

**③ 时间平滑在 7/16 个任务的走查帧上「补」了像素**（ButtonUnmask +5、InsertPeg +4、
PatternLock +1、VideoPlaceButton +14、VideoPlaceOrder +28、VideoRepick +3、
VideoUnmaskSwap +1），其余 9 个持平或减少。这是 §3.3「③ 单独看不单调」的直接实证。
最典型的 VideoPlaceOrder ep10 第 102 帧：

| 阶段 | 像素数 | 增量 |
|---|---:|---:|
| 候选：判臂像素 | 16,636 | — |
| ① 开运算 | 16,621 | −15 |
| ② 触顶连通域 | 16,621 | ±0 |
| ③ 时间平滑 | **16,649** | **+28** ← 多数表决在补像素 |
| ④ 保守收缩 + 腐蚀 | **16,003** | −646 |

④ 的白名单交把 ③ 补进来的那 28 个像素连同边缘一起收掉，最终 mask 仍是候选的子集。

## 七、已知代价（诚实清单）

1. **臂与混合共享的颜色被否决全部带走**：灰白臂壳与灰白任务物体同色的部分照旧漏标。
   这是刚性原则的直接价钱，且由推论 2 可精确写出闭式，不是模糊的「大概损失一些」。
2. **物体误标在评估集上没有理论零保证**：拟合集上是恒等式（推论 1），评估集上依赖
   「拟合集的颜色支撑覆盖得够全」。所以才有硬闸门——数字以每次实测为准，不以推理为准。
3. **未见颜色一律不标**：标定集（val ep0-9）没见过的颜色在评估集出现时按「不是机械臂」
   处理。方向与宗旨一致（宁可漏标）。
4. **触顶规则漏掉非从上方入画的臂**（沿用 v4 口径，属可接受漏标）。
5. **③ 时间平滑单独看不单调**：整条链的单调性靠 ④ 的白名单兜住（6.5 节实测 7/16 个
   走查帧上 ③ 在补像素）。改动 ④ 时务必记得这点。

---

## 八、归档文件清单

| 路径 | 内容 |
|---|---|
| `outputs/color_model.npz` | 颜色表（16297 色，与 v4.1 逐位相同） |
| `outputs/color_model_summary.json` | 拟合摘要（各列像素数、支撑交叠、否决代价） |
| `outputs/holdout/` | 留出集 16 张 preview + `metrics.json`（全帧口径） |
| `outputs/compare_gt/` | train ep0 的 16 张两栏对比图 + `metrics.json` |
| `outputs/color_distribution/` | `color_distribution.png` + `stats.json` |
| `outputs/walkthrough/` | 16 张逐阶段走查 + 16 张逐像素举例 + `walkthrough.json` |
| `reports/color_distribution_report.md` | 判读报告 |
| `reports/generation_report.{json,md}` | 标定数据集的生成报告（数据集未重造，与 v4.1 同源） |
| `outputs/logs/` | 五个入口的运行日志（gitignore，不入库） |
