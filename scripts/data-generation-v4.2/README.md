# 数据生成 v4.2：机械臂标定（先验颜色表 + 纯支撑判据 + 形态学收缩）

本目录做一件事：**把 RoboMME `front_rgb` 里的机械臂标出来、涂成纯红 (255,0,0)**。
方法是先在标定集上建一张先验颜色表，再用它逐像素判别，最后过四条形态学规则收缩成
最终 mask。

**刚性原则（第一判据，凌驾于其它一切指标）：不得把物体判错成 robot arm，「判错」以
ground truth 为准。** 精确说法：整段 episode 每一帧被标成臂的像素，逐个查它在 GT
（`obs/front_camera_segmentation`）里的真身，真身是「物体」的像素数累加必须恒为 0
（各处指标里叫 `false_object_pixels`）。三点保障：

1. **口径偏保守**：GT 侧凡 setup 两张表认不出的 seg id 一律兜底归物体（实测 5 个任务会
   出现运行中动态创建的 id），红线只会更严不会更松；兜底像素由 `uncovered_mask` 单独
   计数，不许静默。
2. **标定集上是恒等式**：判臂的定义就是「混合列一次都没出现过」，而混合列已把 GT 物体
   像素全部计入，所以判臂颜色在标定集上的物体像素恰为 0。评估集上唯一可能的漏洞是
   「标定集只在臂上见过、评估集却出现在物体上」的颜色——正是这一格必须逐次实测。
3. **fail-loud 硬闸门，无豁免开关**：`render_outputs.enforce_no_false_object` 逐 episode
   校验，非 0 打明细并以非零退出码退出。背景误标继续记录但不设闸门——宗旨只针对物体。
   另外 `color_distribution.py` 跑完会断言「判臂颜色上的真实非臂像素 == 0」，被破坏就
   `SystemExit`，兜住颜色表或判别算式本身坏掉的情形。

---

## 一、先验颜色表怎么建立

**标定集 = benchmark val split ep0–9**（16 任务 × 10 条 = 160 episode）的**全部帧的
全部像素**。split 判定读 h5 里的 `<episode>/setup/seed`，不靠目录名猜。拟合入口
`fit_color_model.py`，产物 `outputs/color_model.npz`。

**颜色当键**：每个像素的 R、G、B 三字节拼成 24 位整数（红最高 8 位），无损可逆、天然可
排序，查表二分。输入必须是 uint8 的 H×W×3，否则当场报错。用精确颜色而不是直方图 bin
或高斯拟合，理由是它一个超参都不需要——ManiSkill 渲染确定性极强，颜色本身就是天然的
离散量。

**GT seg_id 三分类**（`class_ids_from_setup` + `labels_from_segmentation`）：

| 类 | 收哪些 seg_id |
|---|---|
| 机械臂 | `flow_excluded` 里 `reason == "robot_link"`；外加 `flow_objects` 里 `kind == "tcp"`（虚拟点，纯防御） |
| 背景 | `flow_excluded` 里 `reason == "background_prop"`；外加 seg_id 0（未命中几何体） |
| 物体 | `flow_objects` 里除 tcp 外的全部；**外加一切认不出的 seg_id（兜底，偏保守）** |

未知 `reason` 抛错；三类两两不相交由断言把关。

**三列重叠计数**（`accumulate_frames`）——对每种颜色记三个数：

| 列 | 统计的是 |
|---|---|
| 列 0（纯背景） | 该颜色出现在 GT 背景像素上的次数 |
| 列 1（背景∪物体混合） | 该颜色出现在 GT 背景**或**物体像素上的次数 |
| 列 2（机械臂） | 该颜色出现在 GT 臂像素上的次数 |

背景像素同时进列 0 和列 1（重叠计数），换来两条后面全靠的性质：①列 1 逐色 ≥ 列 0，
所以列 1 没出现过 ⇒ 列 0 也没出现过；②列 1 + 列 2 把每个像素恰好各记一次，「像素量
口径」都按此。⚠ 不做「混合 − 背景」的减法——那等于变相还原物体分布，而本链路的设定
就是拿不到物体级监督（GT 只允许提供两个场景级分布 + 臂分布）。

**判别 = 纯支撑三段式判据**（`ColorModel.classify`）：查表未命中判 `UNKNOWN`（下游按
「不是机械臂」处理）；命中则只看三列各自「出现过 / 没出现过」，计数数值大小完全不参与：

| 判决 | 条件 | 读法 |
|---|---|---|
| 纯背景 | 列 0 > 0 | 在没有物体也没有臂的画面里出现过 |
| 机械臂 | 列 1 = 0 且 列 2 > 0 | 任何无臂画面里都没出现过，却在臂上出现过 |
| 混合 | 其余（= 列 0 = 0、列 1 > 0） | 只在摆了物体的无臂画面里出现过 |

三段互斥且穷尽（由性质①，前提由 `ColorModel.__post_init__` 两道守卫 fail-loud 兜着）；
一个超参都没有；判臂那条往保守方向倒——该颜色在无臂场景出现过就无法排除属于物体。
这条规则是早期「归一化似然 argmax + 混合支撑否决」写法的退化形态，实测三段判决逐位
等价（见三、实测结论），故直接写成真实形态。「计数值零作用」由
`tests/lightweight/test_arm_mask_v4_2.py` 的放大计数测试钉死。

---

## 二、mask 怎么产生、怎么验证

### 2.1 四条形态学规则（`arm_mask_v4.py`）

输入只有判别标签图，**完全不看 GT**。结构元统一为 3×3 方窗（八邻域）；OpenCV 腐蚀把
画面外当前景，贴边前景不被边界削掉（已实测核验，直接影响②的触顶判定）。先按
`info/is_video_demo` 的极大等值连续段切开相位（跨相位投票会混两个场景，两处 fail-loud），
每段独立跑：

1. **开运算**（腐蚀 1 次再膨胀 1 次）：去抗锯齿/阴影噪点，结果一定是候选（本帧判臂
   像素）的子集。
2. **只保留触到画面第 0 行的连通域**（八连通，整块保留/整块删除）：机械臂根部固定在
   画面顶部、任务物体不触顶，这是「不误标物体」最主要的结构性保障。
3. **3 帧滑动多数表决**（命中帧数严格超过窗口一半；段两端自动截断不补边，段长 1 原样
   不动；时间窗必须正奇数）：⚠ 这是四条里**唯一可能让区域变大**的一条——多数表决会把
   「本帧不在候选、但前后帧在」的像素补进来。
4. **保守收缩**：先与本帧候选取交（**白名单**），再腐蚀 1 次，顺序不能反。白名单是必须
   的：v4.1 实测抓到过③补进 292 个**未见色**像素（品红系），黑名单「扣掉物体」拦不住
   这种像素。

**单调性**：④的白名单交保证最终 mask 一定是本帧候选的子集——整条链相对候选单调收缩，
①②④逐条单调，③单独看不单调、靠④兜回来。改动④时务必记得这点。最终 mask 涂纯红
(255,0,0)，其余像素与原图逐位相同。可调项只有三个整数（开运算 1、时间窗 3、末腐蚀 1），
**浮点阈值数量为 0**。

### 2.2 验证怎么做（三个入口）

**评估集 = 同一 val split 的 ep10–19**（160 episode），与标定集同 split、不同 episode、
seed 零重叠。标定与评估同住一份数据集 `artifacts/generated/v4seg-16env-val20ep`
（⚠ 生成器 `--episodes` 是「从 ep0 起的数量」不是区间；ep0-9 seed 固定，与旧
`v4seg-16env-val10ep` 逐位相同已对拍，颜色表不必重拟合）。产物目录名自带口径
（`validation_val_ep10-19` 等），`ls outputs/` 一眼看出每批数字算在哪。

| 入口 | 验的是什么 |
|---|---|
| `render_outputs.py` | **唯一全量指标**：val ep10-19 全帧推理 + 对 GT 逐像素验证，产出 `metrics.json`（不出图），**刚性闸门定义处**，逐 episode 校验红线 |
| `color_distribution.py` | 颜色表自身：四面板判决分布图 + `stats.json`（不碰 h5），跑完断言红线恒等式，破坏即 `SystemExit`。⚠ 它给的召回/精确率是**上界**不是实测 |
| `segmentation_walkthrough.py` | mask 产生过程：16 任务 × ep0-5 逐帧渲染「候选→①→②→③→④」逐阶段走查视频，逐阶段复算与运行期逐位断言 |

### 2.3 用法

```bash
# 1.（一般不用跑）生成 val split 数据集：ep0-9 当标定集、ep10-19 当评估集
#    ⚠ 正式生成前须与用户确认新的 --output-dir 名字（必须是不存在或空的目录）
uv run --locked scripts/data-generation-v4.2/generate_dataset.py \
  --output-dir artifacts/generated/v4seg-16env-val20ep --env all --episodes 20 \
  --workers 16 --gpus 0,1 --split val \
  --reference-root /data/hongzefu/robomme_data_h5 --no-reference-validation

# 2. 在标定集（val ep0-9）上拟合先验颜色表（单进程，实测约 19 分钟）
uv run --no-sync python scripts/data-generation-v4.2/fit_color_model.py \
  --h5 'artifacts/generated/v4seg-16env-val20ep/record_dataset_*.h5' \
  --episodes 0-9 --out scripts/data-generation-v4.2/outputs/color_model.npz

# 3. 评估集全帧指标（val ep10-19，含刚性闸门；--h5/--episodes/--out 已是默认值）
uv run --no-sync python scripts/data-generation-v4.2/render_outputs.py --workers 16

# 4. 颜色判决分布出图（四面板一张图 + stats.json；只读颜色表，不碰 h5）
uv run --no-sync python scripts/data-generation-v4.2/color_distribution.py

# 5. 分割过程走查出视频（16 任务 × ep0-5 = 96 段 mp4）
uv run --no-sync python scripts/data-generation-v4.2/segmentation_walkthrough.py --workers 16

# 6. 单元测试（v4 / v4.1 / v4.2 三套一起跑，互不污染）
uv run --no-sync python -m pytest tests/lightweight/test_arm_mask_v4.py \
  tests/lightweight/test_arm_mask_v4_1.py tests/lightweight/test_color_distribution.py \
  tests/lightweight/test_arm_mask_v4_2.py tests/lightweight/test_color_distribution_v4_2.py -q
```

### 2.4 文件结构

| 文件 | 作用 |
|---|---|
| `record_wrapper_v4.py` | 薄子类，只新增 `obs/front_camera_segmentation` 落盘（沿用 v4） |
| `generate_dataset.py` | 生成入口（支持 `--split {train,val,test}`） |
| `color_model.py` | 先验颜色表拟合 / 推理（**唯一碰 GT 的模块**），含判别规则 |
| `arm_mask_v4.py` | 四条形态学规则 + 涂红（与 v4 / v4.1 运算逐字相同） |
| `fit_color_model.py` | 拟合入口 |
| `render_outputs.py` | 全量指标 + 刚性闸门 `enforce_no_false_object` 定义处；`_error_image` / `_grid` 共享件也在这里 |
| `color_distribution.py` | 颜色判决分布出图入口 |
| `segmentation_walkthrough.py` | 逐阶段走查出视频入口 |
| `reports/color_distribution_report.md` | 判读报告 |
| `../../tests/lightweight/test_arm_mask_v4_2.py` | GT 映射、重叠计数、判臂等价于纯支撑判据、四条规则的逻辑测试 |
| `../../tests/lightweight/test_color_distribution_v4_2.py` | 出图链路的复算对拍与闸门测试 |

⚠ `color_model` / `arm_mask_v4` 两个模块名在 v4、v4.1、v4.2 三个目录里同名，测试文件
必须用各自的 `sys.modules` 隔离导入器，否则按导入顺序会静默拿到错的实现。

---

## 三、现有实测结论（2026-08-12，全部来自 v4.2 自己重新生成的产物）

### 3.1 先验颜色表本身

val ep0–9 全帧拟合，单进程 1140.1 秒，**唯一颜色 16297 种**，npz 108 KB；与 v4.1 的表
对拍 `schema_version` / `colors` / `counts` **三项逐位相等**（v4.2 只改推理侧，拟合侧
一个字没动）。

| 列 | 像素数 | 支撑色数 |
|---|---:|---:|
| 纯背景 | 4,731,895,750 | 12,214 |
| 背景∪物体混合 | 4,846,769,500 | 14,627 |
| 机械臂 | 342,829,732 | 1,796 |

支撑交叠：**臂 ∩ 纯背景 = 0 色**，臂 ∩ 混合 = 126 色，臂独有 1670 色。「臂与纯背景
零共享」是整条链路能成立的结构性前提——臂的灰白只和物体撞色，不和桌面背景撞色。

### 3.2 判别规则的等价性与代价

- **三段退化实测**：16297 色逐个核验，纯支撑判据与旧「似然 argmax + 否决」写法三段判决
  **全部逐位一致**（背景 12214 / 混合 2413 / 臂 1670 色），那 145 亿个计数值一个都没进
  判决；改写后重跑全部入口，**产物数字一个都没变**（metrics 只有规则字符串与耗时两行
  diff，图逐字节相同）。判臂段是恒等式永远成立；背景 vs 混合段只是本批数据碰巧成立，
  但下游只消费「臂」，不影响任何产物。
- **红线与代价的闭式**：判臂颜色上的真实非臂像素 = **0**（恒等式，颜色阶段精确率上界
  **1.000000**）；颜色阶段召回上界 **0.909211**——126 种臂∩混合共享色带走 31,125,163
  个臂像素（占 9.0789%），它们压着 53,143,358 个非臂像素，这就是必须挡下的理由。这
  126 色实测**全部是 R=G=B 的中性灰白**，单个最重的 `#6C6C6C` 一色吃掉 2.99% 臂像素。

### 3.3 评估集全帧（val ep10–19，160 episode / 78,764 帧）

| 指标 | 值 |
|---|---:|
| **误标物体像素（刚性红线）** | **0** |
| 误标背景像素 | **0** |
| **标定精确率** | **1.000000** |
| 机械臂召回 | **0.817440** |
| 存在物体误标的帧占比 | **0** |
| 未见颜色占比 | 0.1914% |
| GT 兜底（setup 未覆盖 seg id）像素 | 2,267,011，其中误标进臂 **0** |

逐任务召回从 0.672621（StopCube）到 0.851839（MoveCube）。闸门输出：逐 episode 共
160 项误标物体像素全部为 0。耗时 37.8 秒（16 进程）。

### 3.4 走查实测（val ep10 代表帧）

16 任务全部「该帧误标物体 0 px」，逐阶段复算与运行期逐位断言全部通过。**③时间平滑在
3/16 个任务的走查帧上补了像素**（VideoRepick +10、ButtonUnmaskSwap +5、SwingXtimes +3），
④的白名单交把补进来的像素连同边缘一起收掉，最终 mask 仍是候选子集——这是「③单独看
不单调」的直接实证。⚠ 这个比例逐评估集重测、不许照抄（v4.1 noveto 口径 13/16、
train ep10 口径 7/16），走查每任务只取一帧，抽样噪声很强；它证明的是「③确实会补」这个
定性事实，不是稳定指标。

### 3.5 已知代价（诚实清单）

1. 臂与混合共享的 126 种灰白色被规则全部挡下：灰白臂壳与灰白物体同色的部分照旧漏标
   （代价有闭式，见 3.2）。
2. 物体误标在评估集上没有理论零保证（标定集上才是恒等式），所以才有硬闸门——数字以
   每次实测为准，不以推理为准。
3. 未见颜色一律不标，方向与宗旨一致（宁可漏标）。
4. 触顶规则漏掉非从上方入画的臂（沿用 v4 口径，可接受漏标）。
5. ③时间平滑单独看不单调，整条链的单调性靠④的白名单兜住；改动④时务必记得。

### 3.6 归档文件清单

| 路径 | 内容 |
|---|---|
| `outputs/color_model.npz` | 先验颜色表（16297 色，与 v4.1 逐位相同） |
| `outputs/color_model_summary.json` | 拟合摘要（键名里的「否决」是历史措辞，含义未变） |
| `outputs/validation_val_ep10-19/` | val ep10-19 全帧 `metrics.json`（唯一全量口径，本入口不出图） |
| `outputs/color_distribution_val_ep0-9/` | 标定集四面板 `color_distribution.png` + `stats.json`（召回/精确率是上界） |
| `outputs/walkthrough_val_ep0-5/` | 96 段逐阶段走查视频 + `walkthrough.json`（不产生指标） |
| `reports/color_distribution_report.md` | 判读报告 |
| `reports/generation_report.{json,md}` | 标定数据集生成报告（数据集与 v4.1 同源） |
| `outputs/logs/` | 各入口运行日志（gitignore，不入库） |
