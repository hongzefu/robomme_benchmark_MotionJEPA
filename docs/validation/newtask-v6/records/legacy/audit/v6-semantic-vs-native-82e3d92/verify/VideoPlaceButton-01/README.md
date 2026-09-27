# VideoPlaceButton-01 独立反驳性核验

AUDIT_BASE=82e3d922b78d48ec1e825b168cccc0e1b8c690c1（只读，git show 读取）

## 结论：CONFIRMED

## 独立证据

1. `reproduce_source.py`：从 AUDIT_BASE 的
   `src/robomme/robomme_env/VideoPlaceButton.py::VideoPlaceButton._load_scene_xhard_tail`
   摘出候选集计算逻辑（`occupied = demo_before_targets 索引`, `candidates = targets 中
   不在 occupied 且不等于 target_target 的索引`），在 targets==4（config_xhard 系列固定值）
   且 demo_count==2（xhard3/xhard4）时，独立证明 side="before" 的候选集恒为
   `demo_after_targets` 索引集的非空子集——与 finding 的核心论断完全一致。

2. `reproduce_h5_traces.py` + `h5_traces.json`：不复用上一轮审查的 `records.json`，
   直接用 h5py 重新打开三个原始 HDF5（`info/is_subgoal_boundary` + `info/grounded_subgoal`），
   独立复现出的 target-drop 坐标序列与上一轮审查记录逐字相同：
   - xhard3 ep0（seed13000001）：`<90,98> <130,166> <115,91> | 按钮 | <78,164> <115,91>`
     —— 额外放台落点 `<115,91>` 与按钮后第二次放台坐标完全相同（同方块起降同一台）。
   - xhard4 ep0（seed7000000）：`<100,89> <75,92> <82,161> | 按钮 | <104,168> <82,161> <75,92>`
     —— 额外放台前 `<82,161>` 与按钮后第二次放台 `<82,161>` 完全相同（拿起蓝方块 pick<80,162>→
     放回同一台，净位移 ≈2px），是纯粹的"拿起-放回原处"空转；
     额外放台后 `<75,92>` 又与按钮前第二次放台 `<75,92>` 完全相同，对称地印证 extra_after 同理
     落在 before-target 上（same机制，非本 finding 主张范围但结构一致）。
   - xhard4 ep3（seed7000302）：六次放台坐标 `<96,100> <110,123> <142,176> | 按钮 |
     <135,144> <142,176> <96,100>`——`<142,176>` 与 `<96,100>` 各出现两次，但因
     `_extra_place_owners` 对 2 元素用 `torch.randperm` 保证 extra_before 与 extra_after
     的 owner 恒为两个不同的演示方块，本集里两次重复坐标均落在"另一方块"的位置上而非
     "同方块自我复位"，与上一轮审查 `checks.noop_replacements=[]` 一致——这正是 finding
     所说"仅 xhard4 ep3 避开了自我空转（但代价是与 F6 占用冲突场景合流）"的独立印证。

3. `native_hard_ep11_trace.txt`：直接读取原生 hard 档 ep11（
   `artifacts/newtask-v6/v1/base/B/VideoPlaceButton_episode_11/hdf5_files/VideoPlaceButton_ep11_seed11100.h5`），
   独立确认原生三档（`additional_place=False`）确实恰好 2 次 target 放置且坐标互不相同
   （`<124,162>` → 按钮 → `<96,160>`），无任何空转，印证 finding 对"原生行为"一节的刻画准确。

## 判定依据

- **是否可反驳**：未能反驳。从 AUDIT_BASE 源码独立推导出的组合数学结论（targets==4 时
  before/after 目标索引互补，candidates 恒落在 after 侧）与三个独立重新读取的原始 HDF5
  轨迹完全吻合，且原生三档的对照轨迹也独立确认无此现象。
- **是否与已排除项重复**：不重复。已排除清单中的 F6（`VideoPlaceButton extra-place
  occupancy conflict`）覆盖的是"额外方块与已有方块争夺同一 target"的场景，是本 finding
  明确指出的"owner 不是自己时的另一分支"；本 finding 的主张是"owner 是自己时退化为无效
  空转"，是与 F6 互斥、互补的另一半机制描述，不是同一条问题的重复表述。
- **分类是否正确**：`new_tier_only` 正确——该额外放置机制（`extra_place_before/after`、
  `_load_scene_xhard_tail`、`_extra_place_owners`）仅在 `is_v6_tier` 分支存在；
  原生 easy/medium/hard 走的是完全不同且默认关闭的 `additional_place` 机制
  （`config_easy/medium/hard` 均 `"additional_place": False`，xhard 若误传
  `additional_place=True` 会直接 `raise SceneGenerationError`），二者在源码层面互斥、不可比，
  不存在"新档偏离原生某个已启用行为"的 mismatch 语境。
- **是否需要新模拟**：不需要。现有 165 条已交付的 xhard3/xhard4 successes 与已抽取的
  HDF5/mp4 足以支持结论，未运行任何新仿真。
