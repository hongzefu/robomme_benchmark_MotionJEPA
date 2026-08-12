# 数据生成 v4.1：两分布（纯背景 + 背景∪物体混合）+ 臂分布的弱监督标定

本目录回答的问题与 [v4](../data-generation-v4/README.md) 相同——**把 RoboMME
`front_rgb` 里的机械臂标出来、涂成纯红 (255,0,0)**——但把 GT 的使用口径**再削弱一档**
（用户 2026-08-12 拍板）：

| 方面 | v4 | **v4.1（本目录）** |
|---|---|---|
| GT 提供什么 | 背景 / 物体 / 机械臂**三类**像素分布 | **两个场景级分布 + 臂分布**：纯背景像素、背景∪物体像素（混合，物体不单独可见、类先验未知）、机械臂像素 |
| 判据 | 计数 argmax（最大后验，类先验隐含在计数里）+ 共享色否决 | **各列归一化似然 argmax（类先验不参与）+ 混合支撑否决** |
| 标定集 | train split ep 0–9 | **benchmark val split ep 0–9**（seed 固定，与 train split 零重叠） |
| 评估 / 出图 | train split ep 10–19 留出集 | **train split episode_0**（三栏对比图）；ep 10–19 留出集验证仍可用 `render_outputs.py` 跑 |
| 宗旨 | 绝不误标其他物体；允许少量机械臂没被标进去 | 不变 |

动机：三类分布要求物体级逐像素分割；两分布 + 臂分布等价于「无臂空场景」「摆了物体但
无臂的场景」两种**画面级**监督加臂自身的外观样本——更弱、更接近真实可得的监督。本目录
量化这一削弱付出的代价。

## 口径（用户逐条拍板，2026-08-12）

1. **标定集 = val split ep 0–9**（每任务 10 条）。benchmark 的三套 split
   （`src/robomme/env_metadata/{train,val,test}/`）seed 固定；val 编码为
   `1_000_000 + task_index*10000 + ep*100 + retry`。标定数据集
   `artifacts/generated/v4seg-16env-val10ep` 由本目录 `generate_dataset.py --split val`
   生成（16 任务 × 10 episode，带 GT segmentation）。
2. **判别规则 = 归一化似然 argmax + 混合支撑否决**：
   - 拟合侧三列 =（纯背景计数，背景∪物体混合计数，臂计数），**重叠计数**——背景像素
     同时进列 0 与列 1，物体像素只进列 1，臂像素只进列 2；
   - 分类时各列各自归一化成 `P(颜色|类)` 再取 argmax，**类先验不参与**；列序
     （背景，混合，臂）使平手偏向非臂；
   - **不做「混合 − 背景」减法**：两列逐色对减等于变相恢复物体分布，违背「物体类先验
     未知」的设定；
   - veto（默认开）= argmax 判臂后，凡混合列计数 > 0 的颜色一律改判混合——无臂场景里
     出现过的颜色无法排除属于物体；
   - 三列都没见过的颜色仍给 `UNKNOWN` 保守不标。臂列的存在让「未见」保得住保守语义
     （若只有两个分布，臂只能定义为「未被解释的颜色」，未见色会被迫判臂，失效方向与
     宗旨相反——这是三类 → 两分布讨论中先行论证过的结论）。
3. **出图 = 每任务一张三栏对比图**（`outputs/compare_veto/`）：veto | noveto |
   ground truth，都取 train split episode_0（未参与标定），每栏 8 帧 ×
   （原图 | 红遮罩 | 误差图）三联。

## 方法

### 一、两分布 + 臂的精确颜色表（`color_model.py`）

统计每种 24 位 RGB 颜色在三列里的计数，推理时逐像素查表、按归一化似然取 argmax。
精确颜色（不用直方图 bin 或高斯）的理由与 v4 相同：ManiSkill 渲染确定性极强，颜色
本身就是天然离散量，一个超参都不需要。落盘 schema 版本 `color-model-v4.1-2dist`，
v4 三类表的 npz 在 `ColorModel.load` 处直接报错，防止口径混用。

### 二、四条形态学规则（`arm_mask_v4.py`，与 v4 逐字相同）

输入只有上一步的标签图，按顺序执行：

1. **开运算**（先腐蚀后膨胀，3×3）——去掉抗锯齿边缘与阴影上的零星臂色噪点。
2. **只保留从上方进入的连通域**——机械臂根部固定在画面顶部；桌面上的任务物体不触顶。
3. **时间平滑**——3 帧滑动多数表决，严格按 `info/is_video_demo` 相位分段。
4. **保守收缩**——**白名单**：只保留**当前帧自己**被判成机械臂的像素（一并扣掉判为
   混合、背景与 UNKNOWN 的像素；写成「扣掉物体」的黑名单不够——时间平滑的多数表决会把
   本帧不在候选里的像素补进来，v4 留出集上实测抓到过 292 个这样的误标像素），再整体
   腐蚀一次。

四条规则方向刻意统一：每一条都只会让标定区域变小或持平。

### 三、生成侧：`--split` 支持

`generate_dataset.py` 相对 v4 新增 `--split {train,val,test}`（默认 train），从对应
metadata 目录读固定 seed / difficulty。v2.1 的 `read_train_metadata` 把「恰好 100 条」
写死成 train 口径，v4.1 对 val/test 用本地 `_read_split_metadata` 复刻同等强度校验
（条数换成 50）。官方参考数据只有 train，val/test 生成须配 `--no-reference-validation`。

## 结构

| 文件 | 作用 |
|---|---|
| `record_wrapper_v4.py` | 薄子类，只新增 `obs/front_camera_segmentation` 落盘（沿用 v4） |
| `generate_dataset.py` | 生成入口（v4 基础上新增 `--split`） |
| `color_model.py` | 两分布 + 臂的颜色表拟合 / 推理（**唯一碰 GT 的模块**） |
| `arm_mask_v4.py` | 四条形态学规则 + 涂红（与 v4 逐字相同） |
| `fit_color_model.py` | 拟合入口 |
| `render_outputs.py` | 留出集推理 + 对 GT 验证 + preview 出图入口 |
| `compare_veto.py` | **三栏对比出图入口**（veto / noveto / GT，train ep0） |
| `color_distribution.py` | **颜色判决分布出图入口**（veto / noveto 两版 + 否决差异图 + `stats.json`；不读 h5，只读颜色表） |
| `segmentation_walkthrough.py` | **分割过程走查出图入口**（真实帧逐阶段拆解 + 逐像素举例） |
| `reports/color_distribution_report.md` | 上面两个入口的**判读报告**（含召回/精确率的两段分解） |
| `../../tests/lightweight/test_arm_mask_v4_1.py` | GT 映射、重叠计数、归一化似然、否决与四条规则的逻辑测试（19 个，秒级；v4 的测试文件继续护 v4 不动） |
| `../../tests/lightweight/test_color_distribution.py` | 出图链路的复算对拍测试（10 个，秒级）——`decide` 对 `classify`、`stagewise_masks` 对 `arm_masks_for_episode` 都要逐位一致 |

## 用法

```bash
# 1. 生成带 GT segmentation 的 val split 标定数据集（16 任务 × 10 episode，双卡）
#    ⚠ 正式生成前须与用户确认新的 --output-dir 名字
uv run --locked scripts/data-generation-v4.1/generate_dataset.py \
  --output-dir artifacts/generated/v4seg-16env-val10ep --env all --episodes 10 \
  --workers 16 --gpus 0,1 --split val \
  --reference-root /data/hongzefu/robomme_data_h5 --no-reference-validation

# 2. 在标定集（val ep 0-9）上拟合两分布 + 臂颜色表
uv run --no-sync python scripts/data-generation-v4.1/fit_color_model.py \
  --h5 'artifacts/generated/v4seg-16env-val10ep/record_dataset_*.h5' \
  --episodes 0-9 --out scripts/data-generation-v4.1/outputs/color_model.npz

# 3. 三栏对比出图（veto | noveto | GT，train ep0，16 张 + metrics.json）
uv run --no-sync python scripts/data-generation-v4.1/compare_veto.py \
  --h5 'artifacts/generated/v4seg-16env-20ep/record_dataset_*.h5' \
  --model scripts/data-generation-v4.1/outputs/color_model.npz \
  --out scripts/data-generation-v4.1/outputs/compare_veto

# 4.（可选）train ep10-19 留出集全帧指标，与 v4 三类表对照
uv run --no-sync python scripts/data-generation-v4.1/render_outputs.py \
  --h5 'artifacts/generated/v4seg-16env-20ep/record_dataset_*.h5' \
  --model scripts/data-generation-v4.1/outputs/color_model.npz \
  --episodes 10-19 --out scripts/data-generation-v4.1/outputs/holdout

# 5. 颜色判决分布出图（veto / noveto 两版 + 差异图 + stats.json，约 30 秒；只读颜色表，不碰 h5）
uv run --no-sync python scripts/data-generation-v4.1/color_distribution.py

# 6. 分割过程走查出图（16 任务 × 留出集 ep10，每任务两张：逐阶段走查 + 逐像素举例，实测 25.7 秒）
uv run --no-sync python scripts/data-generation-v4.1/segmentation_walkthrough.py

# 7. 单元测试（v4 + v4.1 两套一起跑，互不污染）
uv run --no-sync python -m pytest tests/lightweight/test_arm_mask_v4.py \
  tests/lightweight/test_arm_mask_v4_1.py tests/lightweight/test_color_distribution.py -q
```

三栏图（`outputs/compare_veto/<Task>_veto_compare.png`）：每栏 8 帧 ×
（原图 | 红遮罩 | 误差图）。误差图配色：**白 = 标对的机械臂、红 = 误标到物体
（核心红线）、黄 = 误标到背景、蓝 = 漏标的机械臂**。GT 栏的红遮罩直接涂 GT 臂像素，
误差图应全白（自校验）。

## 实测结论（2026-08-12）

### 标定数据集与颜色表

- `artifacts/generated/v4seg-16env-val10ep`：16 任务 × val ep 0–9 = 160 episode，
  **160/160 全部成功**，66 GB，双卡 16 worker 约 1 小时；逐任务抽查 `setup/seed` 与
  val metadata 逐位一致（BinFill ep0 = 1040000 等）。
- 拟合（160 episode 全帧，单进程 19.2 分钟）：**唯一颜色 16297 种**，npz 104 KB；
  各列像素数 背景 47.3 亿 / 混合 48.5 亿 / 臂 3.43 亿，各列颜色数 12214 / 14627 / 1796；
  **臂∩混合共享 126 色、臂∩纯背景共享 0 色**、臂独有 1670 色；混合支撑否决按拟合集
  计带走 9.08% 的臂像素。

### 留出集（train ep 10–19，160 episode / 77272 帧全帧口径）

| 指标 | 默认（混合支撑否决） | 对照（`--no-shared-veto`，纯似然 argmax） |
|---|---:|---:|
| **误标物体像素** | **0** | 406615 |
| 误标背景像素 | **0** | 0 |
| **标定精确率** | **1.000** | 0.998701 |
| 机械臂召回 | 0.818412 | 0.917670 |
| 存在物体误标的帧占比 | **0** | 13.82% |
| 未见颜色占比 | 0.187% | 0.187% |

逐任务召回从 0.684（StopCube）到 0.852（MoveCube）。

### train ep0 三栏对比图（`outputs/compare_veto/`，16 张 + metrics.json）

veto 口径 **16/16 任务误标物体 = 0**；noveto 有 13/16 任务出现误标（最大
ButtonUnmask 5226 px、VideoUnmask 4625 px，InsertPeg / MoveCube 为 0）。GT 栏
误差图全白（自校验通过）。全部 16 张出图 23 秒。

### 与 v4 三类表的对照（同一留出集）

| | v4（三类，train ep0-9 标定） | **v4.1（两分布+臂，val ep0-9 标定）** |
|---|---:|---:|
| veto：误标物体 / 精确率 / 召回 | 0 / 1.000 / 0.818417 | **0 / 1.000 / 0.818412** |
| noveto：误标物体 / 召回 | 241765 / 0.908982 | 406615 / 0.917670 |

**结论：veto 口径下把监督从三类分割削弱到「两个场景级分布 + 臂分布」几乎零代价**
——召回只差 5 位小数（pred_pixels 278740822 vs 278742663，差 1841 px，来自两套标定集
的颜色支撑差异），红线指标逐位同款。原因与此前的理论分析吻合：臂∩纯背景共享色实测
为 0，于是「混合列出现过」与 v4 的「物体列出现过」在臂色上圈出几乎同一批颜色，
支撑否决只用「出现过 / 没出现过」，先验与似然的削弱根本不进裁决。代价集中在 noveto
一侧：失去物体单列后纯 argmax 的误标比 v4 多 68%（406615 vs 241765）——似然裁决确实
变弱了，只是默认口径根本不依赖它。

### 颜色判决分布与分割过程走查（2026-08-12 补做）

完整判读见 [reports/color_distribution_report.md](reports/color_distribution_report.md)，
要点：

- **判臂颜色上的成分**：veto 口径下判臂的 1670 种颜色在标定集里的**非臂像素恰好为 0**
  （颜色阶段精确率上界 1.000，noveto 只有 0.943）——「留出集零物体误标」是这条否决规则
  的**构造性结果**，不是调出来的巧合；代价是颜色阶段召回上界从 0.9975 掉到 0.9092。
- **被否决翻转的恰好 120 种颜色，饱和度实测最大值为 0.000**，即全部是 `R = G = B` 的
  纯灰阶；它们带走 8.83% 的臂像素，同时挡下 20,498,259 个非臂像素。前 3 种
  （`#6C6C6C` / `#A8A8A8` / `#A9A9A9`）就占掉 5.86 个百分点，长尾极陡。
- **臂的像素质量几乎全在灰白上**：判臂色里低饱和的 470 种占 90.91% 的臂像素，高饱和的
  1200 种只占 0.0075%（纯色数长尾，且混合列计数全为 0，从不进否决）。
- **两段分解**：颜色阶段 0.9092 → 留出集实测 0.8184，四条形态学规则再收掉一成召回；
  反过来 noveto 的颜色级精确率上界 0.943 被形态学（主要是触顶连通域）救到 0.9987，
  但**救不干净**，仍剩 406,615 个误标物体像素 / 13.82% 的帧碰到物体。

## 已知代价（诚实清单）

1. **臂与混合共享的颜色被否决全部带走**：灰白臂壳与灰白任务物体同色的部分照旧漏标，
   且否决门限比 v4 更宽——只要颜色在无臂场景（含纯背景）出现过就不判臂。
2. **物体误标不再有理论零保证**：v4 的物体硬否决建立在「物体列可见」上；v4.1 的混合列
   把背景与物体混在一起，noveto 口径下臂似然占优的共享色会被判臂，veto 口径下依赖
   支撑集覆盖完整。数字以实测为准。
3. **未见颜色仍一律不标**：标定集（val ep0-9）没见过的颜色在评估域出现时按「不是
   机械臂」处理。
4. **触顶规则漏掉非从上方入画的臂**（沿用 v4 口径，属可接受漏标）。
