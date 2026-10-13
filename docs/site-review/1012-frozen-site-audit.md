# 8092 页面冻结审查与 H5 只读复核

## 范围与版本

本轮按用户指令更新计划站点，新增交换机制栏并保留配对第二版的图2与图3；另为16个环境各派一位独立子代理核对第二、三、四页，三路子代理核对第五页的格式、实物与证据范围。

用户关键原话依次为：

1. 「根据现在冻结的代码就可以开始改这个，开始做这个页面了。」「这两张图都要保留。」「使用子代理先进行详尽调查」
2. 「制作站点的子代理全部都用 Astra。」
3. 「对于每个环境都进行一次子代理的调查，保证这个二三四大业都是正确的。」
4. 「然后再派一些子代理负责检查H5产物，就是第五节的这个正确性。」
5. 确认模型分工：「是，审查用 Sol，制作用 Astra」。

`AUDIT_BASE=f98c779a2c3f086759d9fcc4663a06da7deec083`（2.98Beta）。发起与静态审查收官时主检出均为此版本，`git status --porcelain` 为空。该版本已记录18项GPU契约通过、四身份冒烟三成功一图拒绝；全量验收不在本次冻结证据中。页面制作使用独立工作树，不修改环境、生成器、依赖、参数或运行判据。

审查角色使用 `gpt-6.1-sol`，页面制作使用 `gpt-6-astra`。早期两位 Luna 仅做站点入口与图源定位，其中图源调查在用户指定模型后中断；不承担16环境及H5审查结论。

## 逐环境审查摘要

以下为静态审查与已提交记录核对，不是本轮重新运行环境。当前配置以 `src/robomme_xhard/configs.py::TIER_CONFIGS` 为准，目标模板以 `src/robomme/robomme_env/utils/task_goal.py::get_language_goal` 为准。

|编号|环境|页面需准确表达的边界|
|---|---|---|
|1.1|BinFill|固定母总数4，五档5至9；库存以实际生成对象为准，不足拒绝，不由计划生成10至12块推断必够。|
|1.2|PickXtimes|五档6至10，不再固定九次；总目标随档位生成，抓放子目标按次数扩展。|
|1.3|SwingXtimes|往返4/5/7/8/9，母档3；一次往返含左右两次移动，不混淆次数与子目标数。|
|1.4|StopCube|四个有效档为4/80、5/80、7/60、6/80；旧次数翻倍方案不再适用；运动参考时刻不等于H5总长度。|
|2.1|VideoUnmask|只有三抓派生档；第三色动态读取；历史单seed实跑8帧遗漏为0，用户已决定保留。|
|2.2|ButtonUnmask|按一次按钮后执行三抓；增加一次抓取而非新物体；历史单seed遗漏0，不能写必漏。|
|2.3|VideoUnmaskSwap|次数4/5/7/9/11；新配对不再受最近邻限制；旧合成和旧生成长度不是配对第二版的全量统计。|
|2.4|ButtonUnmaskSwap|五档P/S固定；正确侧按压上升沿推进；第一抓前等待是求解器行为，不是额外子目标或任意策略成功判据。|
|3.1|PickHighlight|六块库存、选4/5/6块；末块抓起即结束，没有末放桌或末按钮；仅派生目标句删末按钮。|
|3.2|VideoRepick|母来源medium、重抓2次；冻结目标分支有三句；第二版冒烟单卡1367帧不是全量中位数。|
|3.3|VideoPlaceButton|前侧在target_0前、后侧在target_1后；后侧与原post_flag插入位置不同；母4句、修正版派生3句。|
|3.4|VideoPlaceOrder|固定母N=3追加唯一剩余目标为4；保留母前缀、答案与按钮位置，增加的是演示抓放组。|
|4.1|MoveCube|只有hard母档，无长度不变的新档；动作方式沿用各母seed，不均为抓放。|
|4.2|InsertPeg|只有hard母档，同一peg、抓取端与插入侧；历史25样本摘要不是当前母卡实测。|
|4.3|PatternLock|5×5、八邻接、不重复节点；重新采整路径，无母路径前缀保证；历史xhard16比xhard14短26步。|
|4.4|RouteStick|边数6至10、访问节点数7至11，允许重复；五个路径按钮位置与九个目标actor不是同一计数。|

第二页现行配置与历史估算分开，第三页实际目标模板与历史实例分开，第四页结构扩展与参数越界分开。主会话复核了关键分支，包括 BinFill 实际库存、ButtonUnmaskSwap 等待钩子、VideoRepick 三条目标及官方顺序的单seed历史结果表。

## H5 实物复核

执行位置：sled-aspen 的本仓库；只读打开已完成的 `artifacts/xhard/xhard-1011/final/` 与 `vpbfix-1012/`，未读取正在生成的交换第二版全量目录，没有下载、安装、写入原数据或读取图像像素。

日期：2026-10-12（America/Detroit）。工具未保留精确启动时刻；代理交回时读取时钟为22:04:11 EDT，不将该时间冒充扫描启动时间。

原始输出：`H5_READ=PASS files=71 elapsed_seconds=18.304`，命令退出0。范围为最终批次68文件（52派生与16母档），另加VideoPlaceButton修正版3文件。此判定表示文件可读和单episode、连续timestep断言成立；其余检查值逐文件打印，不能将尾行理解成所有下游训练契约通过。

对逐文件输出的人工汇总：71文件的首步RGB均为256×256×3 uint8，首步演示/完成标记均为标量bool，均存在完成位置且满足 `c+2<=T`。最终52派生文件中24个具有非空演示前缀，28个演示帧为0。**未执行MotionJEPA真实扫描入口、白名单、建库或训练。**

独立首步结构比较原始输出如下，命令退出0：

```text
FIRST_TIMESTEP_SCHEMA=PASS files=54
[]
SETUP_DTYPE_SHAPE_DIFF=[["artifacts/xhard/xhard-1011/vpbfix-1012/xhard12/hdf5_files/VideoPlaceButton_ep7_seed10701.h5", {"task_goal": [["object", [4]], ["object", [3]]]}], ["artifacts/xhard/xhard-1011/vpbfix-1012/xhard14/hdf5_files/VideoPlaceButton_ep7_seed10701.h5", {"task_goal": [["object", [4]], ["object", [3]]]}]]
```

54指52个最终派生文件加2个修正版派生文件；每个与同任务母档比较首timestep的完整dataset键、dtype和shape。它不是所有timestep、像素/动作数值、官方参考集或交换第二版全量的一致性证明。

实物中VideoRepick母标签为medium，其余母档hard，派生标签为对应xhard档。VideoPlaceButton旧final派生仍4句，应使用vpbfix的3句修版；两派生长度1132/1265、演示帧924/1059、首完成位置1118/1251，母档4句。

初次目录探测曾把timestep误认为在setup内，退出1；核对实际键树后更正。没有因这个检查错误修改数据，成功扫描及独立比较均退出0。

### 已执行的读取命令

```bash
ssh sled-aspen 'cd /data/hongzefu/robomme_benchmark_newtask-v3-MotionJepa1006 && UV_CACHE_DIR=/home/hongzefu/.cache/uv timeout 240s .venv/bin/python -' <<'PY'
import h5py,pathlib,json,time
root=pathlib.Path('artifacts/xhard/xhard-1011'); begin=time.monotonic(); count=0
for run in ['final','vpbfix-1012']:
 for path in sorted((root/run).glob('*/hdf5_files/*.h5')):
  with h5py.File(path,'r') as f:
   assert len(f)==1
   ep=f[next(iter(f))]; setup=ep['setup']; names=sorted([k for k in ep if k.startswith('timestep_')], key=lambda s:int(s[9:])); assert names==['timestep_'+str(i) for i in range(len(names))]
   first=ep[names[0]]; schema={}
   first.visititems(lambda k,v: schema.update({k:[str(v.dtype),list(v.shape)]}) if isinstance(v,h5py.Dataset) else None)
   demos=[bool(ep[n]['info/is_video_demo'][()]) for n in names]; done=[bool(ep[n]['info/is_completed'][()]) for n in names]
   value=setup['difficulty'][()]; difficulty=value.decode() if isinstance(value,bytes) else str(value)
   goals=setup['task_goal']; d=sum(demos); c=next((i for i,x in enumerate(done) if x),None)
   print(json.dumps(dict(file=str(path),task=path.name.split('_ep')[0],tier=path.parts[-3],run=run,T=len(names),difficulty=difficulty,task_goal_shape=list(goals.shape),task_goal_count=1 if goals.shape==() else len(goals),demo=d,completed=c,scan_shape=schema.get('obs/front_rgb')==['uint8',[256,256,3]],scan_flags=all(schema.get('info/'+k)==['bool',[]] for k in ['is_video_demo','is_completed']),demo_prefix=d>0 and demos==[True]*d+[False]*(len(names)-d),completed_tail=c is not None and c+2<=len(names),schema=schema if count==0 else None),ensure_ascii=False));count+=1
print('H5_READ=PASS files=%d elapsed_seconds=%.3f'%(count,time.monotonic()-begin))
PY
```

### 已执行的首步比较命令

```bash
ssh sled-aspen 'cd /data/hongzefu/robomme_benchmark_newtask-v3-MotionJepa1006 && UV_CACHE_DIR=/home/hongzefu/.cache/uv timeout 60s .venv/bin/python -' <<'PY'
import h5py,pathlib,json
root=pathlib.Path('artifacts/xhard/xhard-1011'); schemas={}; counts=0; errors=[]; setups=[]
def schema(g):
 out={};g.visititems(lambda k,v:out.update({k:(str(v.dtype),v.shape)}) if isinstance(v,h5py.Dataset) else None);return out
for p in sorted((root/'final/mother/hdf5_files').glob('*.h5')):
 with h5py.File(p,'r') as f:
  e=f[next(iter(f))];schemas[p.name]=(schema(e['timestep_0']),schema(e['setup']))
for run in ['final','vpbfix-1012']:
 for p in sorted((root/run).glob('xhard*/hdf5_files/*.h5')):
  with h5py.File(p,'r') as f:
   e=f[next(iter(f))];s,su=schemas[p.name];now=schema(e['timestep_0']);cur=schema(e['setup']);counts+=1
   if s!=now:errors.append((str(p),{k:[s.get(k),now.get(k)] for k in s.keys()|now.keys() if s.get(k)!=now.get(k)}))
   dif={k:[su.get(k),cur.get(k)] for k in su.keys()|cur.keys() if su.get(k)!=cur.get(k)}
   if dif:setups.append((str(p),dif))
print('FIRST_TIMESTEP_SCHEMA='+('PASS' if not errors else 'FAIL')+' files='+str(counts));print(json.dumps(errors));print('SETUP_DTYPE_SHAPE_DIFF='+json.dumps(setups))
PY
```

## 不同证据不能合并计数

历史审查脚本的52个样本与两对HF样本已删除，其结论只能按旧样本范围引用。正式xhard-1011的68卡、VideoPlaceButton修版3卡、旧碰撞第一版165/180和配对第二版冒烟三成功H5属于不同批次。相同录像器只是来源依据，不能推出全部字段或训练兼容性必然相同。新配对全量的完成与否由其独立留档负责，本页只呈现冻结点已有证据。
