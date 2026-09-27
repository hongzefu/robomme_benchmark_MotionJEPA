# InsertPeg-01 独立验证

AUDIT_BASE=82e3d922b78d48ec1e825b168cccc0e1b8c690c1（源码只读 `git show`）；数据只读 h5py 打开。

## 1. 源码锚点核实

`git show 82e3d922b78d48ec1e825b168cccc0e1b8c690c1:src/robomme/robomme_env/InsertPeg.py`
`_initialize_episode` 内 `tasks` 列表：

- task[1]（demonstration=True）：`"name": f"Insert the peg from the {self.insert_way} side of the box"`
- task[5]（demonstration=False）：`"name": f"Insert the peg from the {self.insert_way} side"`

逐字符匹配 finding 的 `native_behavior` 引述。全仓库只有这一份 `InsertPeg.py`
（`git ls-tree` 确认无 v6/xhard 专属重写文件），且 `tests/lightweight/test_v5_xhard_insertpeg.py`
文档字符串明确写「原三档：`_xhard_sample_pegs` 只在 `if xhard` 分支里被调用，**原生循环不读任何
V5 新键**」——即 task 列表/文本生成逻辑对 native 与 xhard 完全共用同一份代码，xhard 分支只改变
peg/box 几何采样，不触碰这两行文本。

## 2. 用真实交付数据独立复现（不依赖被审计报告的截图/摘录）

用 `inspect_h5.py`（本目录）对 `episode_N/timestep_M/info/simple_subgoal` 逐步扫描，
按文本变化切段，独立跑出的段边界：

| 档位 | 文件 | demo 段 (timestep) | exec 段 (timestep) |
|---|---|---|---|
| easy ep0 | InsertPeg_ep0_seed13000.h5 | 123–237: `'Insert the peg from the left side of the box'` | 361–462: `'Insert the peg from the left side'` |
| medium ep10(seed14001) | InsertPeg_ep10_seed14001.h5 | 118–226: `'...of the box'` | 345–445: `'...side'`（无"of the box"） |
| hard ep11 | InsertPeg_ep11_seed14100.h5 | 121–246: `'Insert the peg from the right side of the box'` | 368–492: `'Insert the peg from the right side'` |
| xhard4 ep6 | InsertPeg_ep6_seed7300600.h5 | 109–218: `'...right side of the box'` | 328–434: `'...right side'` |
| xhard4 ep2 | InsertPeg_ep2_seed7300200.h5 | 123–231: `'...left side of the box'` | 355–451: `'...left side'` |
| xhard4 ep4 | InsertPeg_ep4_seed7300400.h5 | 128–213: `'...left side of the box'` | 342–415: `'...left side'` |

**步区间与 finding 引述的 hard ep11 (121-246 / 368-492)、easy ep0 (123-237 / 361-462)、
xhard4 ep6/ep2/ep4 全部逐字节一致**——finding 引述的具体步号未经我改写、直接由本次独立脚本
复现，非抄自被审计报告。

- 新档索引 `new-tier-index.json` 里 InsertPeg 只交付了 xhard4 的 3 条（ep2/ep4/ep6，
  xhard1-3 无 InsertPeg 交付数据，因此本条只能在 xhard4 上验证，与 finding 的
  `tiers_affected` 一致）。
- mp4 文件名里的档位标签（`_easy_`/`_medium_`/`_hard_`）与我独立映射的 episode↔tier
  对应关系一致（`InsertPeg_episode_0→easy`、`InsertPeg_episode_10→medium(seed14001)`、
  `InsertPeg_episode_11→hard`）。

## 3. 视觉/物理侧核对（部分支持，量级有出入，不构成反驳）

`compare_eef.py` 用 `obs/eef_state` 前 3 维（xyz）在 demo 段末帧 vs exec 段末帧算欧氏距离：

```
easy_ep0:   dist=0.04528 m
hard_ep11:  dist=0.00175 m
xhard4_ep6: dist=0.00398 m
xhard4_ep2: dist=0.03074 m
xhard4_ep4: dist=0.03681 m
```

finding 声称"final eef within 0.0066 m across all 12 episodes"；我用同一量（`eef_state`
段末帧）复测出的值在 0.0017–0.045 m 之间，**部分超过 0.0066 m**，量级对不上。推测原因：
exec 段的 `solve` 传了 `cut_retreat=True`（`InsertPeg.py` task[5] 的 `"solve"` lambda），
即插入完成后会**回退**手臂，而 demo 段没有这个回退，因此 exec 段末帧的 eef 位置已经不是
插入瞬间的位置，而是回退后的位置，与 demo 段末帧（插入瞬间）不是同一物理时刻，直接末帧
比较会引入回退位移的噪声。这说明 finding 具体的"0.0066 m"这个数字所用的测量口径
（大概率是 peg/box 接触判据触发那一帧、而非整段最后一帧）与我这里的粗测口径不同，
**我没能逐位复现这个具体数字**，但这不影响核心语义结论——两段执行的都是"把销钉插入盒子
的同一侧"这个动作，且 `is_A_insert_notB` 判据函数（demo 与 exec 分别对应 task[1]/task[5]
的 `func`）在方向参数 `direction=self.direction` 上完全相同，只是 exec 版本额外带
`mark_end_flag=True`（用于标记任务完成，不改变插入方向判据本身）。

## 4. 结论

- **CONFIRMED**：文本差异（"...side of the box" vs "...side"）真实存在，源码锚点
  `InsertPeg.py` task[1]/task[5] 逐字符核实无误；native 三档（easy/medium/hard）与
  xhard4 均独立复现出同样的文本切分模式，步区间与 finding 引述完全一致。
- **category=native_same 正确**：xhard 分支（`_xhard_sample_pegs`）只改变几何采样，
  不读写 task 文本字段（测试文件文档字符串明确佐证），因此该文本差异是 native env 代码
  本身的既有行为，在新档位里原样保留，不是 xhard 机制引入的新分歧，也不是仅存在于
  xhard 的新现象。
- 不是排除清单中任何一条的重复（排除清单中与 InsertPeg 相关的只有 D6"near/far x-axis"，
  与本条"of the box"文本差异是完全不同的问题）。
- 不需要新模拟：本条可以完全用已交付的 h5 数据核实，未运行任何仿真。
- 唯一的小出入是"final eef within 0.0066 m"这一具体量化数字未能用我的粗测口径复现
  （见第 3 节），但这只影响细节表述精度，不影响该 finding 的核心语义判断和分类。
