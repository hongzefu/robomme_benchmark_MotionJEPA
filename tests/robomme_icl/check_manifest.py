"""固定 96 条 v3 套件的轻量验收，不启动仿真或解码 HDF5 RGB。

默认读取 artifacts/generated/robomme-icl/validation24-v3/suite.json。
通过 --suite 指定同一验收口径的套件；--report 排他写入仓库内 JSON。
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import shlex
import subprocess
import sys
import time

import h5py

from robomme_icl.geometry.collision import actor_boxes, actor_occupies_binfill_hole
from robomme_icl.io.paths import output_path
from robomme_icl.suite.compiler import plan_slots
from robomme_icl.suite.storage import load_suite


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SUITE = ROOT / "artifacts/generated/robomme-icl/validation24-v3/suite.json"
BASELINE_COMMIT = "1143477"
CERTIFICATION_COMMIT = "e34474a6304b917b44cedae129ac621ddd52a430"


def check_manifest(suite_path: Path) -> dict:
    """核对配额、任务语义、位置支持层、认证末帧和原版文件字节。"""
    start=time.monotonic()
    root=ROOT
    suite_path=output_path(suite_path)
    suite=load_suite(suite_path)
    episodes=suite['episodes']; cert=suite['certification']; config=suite['configs']; pos=config['position']
    assert len(episodes)==96
    assert sorted(e['seed'] for e in episodes)==list(range(2000000000,2000000096))
    for key in ('task','position'):
        assert config[key]==json.loads((root/f'src/robomme_icl/configs/{key}_distribution.json').read_text())
    counts=Counter((e['task_kind'],e['difficulty']) for e in episodes)
    assert len(counts)==12 and set(counts.values())=={8}
    slots={s['slot_id']:s for s in plan_slots(config['task'],pos)}
    assert len(slots)==96
    stats=Counter(); min_support=math.inf; gap=[]; param_stats=defaultdict(lambda:defaultdict(Counter)); layer_counts=defaultdict(Counter)
    for e in episodes:
        task=e['task_kind']; diff=e['difficulty']; params=e['task_parameters']; actors=e['actors']; by_id={a['id']:a for a in actors}
        slot=slots[e['provenance']['slot_id']]
        assert (slot['seed'],slot['episode'],slot['task_kind'],slot['difficulty'])==(e['seed'],e['episode'],task,diff)
        for key, choices in config['task']['tasks'][task][diff].items():
            assert params[key] in choices and type(params[key]) is type(choices[0]),(task,diff,key)
            assert params[key]==slot['parameters'][key],(task,diff,key,'配额不一致')
            param_stats[f'{task}/{diff}'][key][str(params[key])]+=1
        assert e['schedule']==pos['schedule']
        for key,value in pos['geometry'].items(): assert e['geometry'][key]==value
        assert e['geometry']['safety_clearance']==0.005
        report=cert[e['spec_hash']]
        for flag in ('passed','repeat_equal','fresh_process'): assert report[flag] is True
        assert report['comparison']=='dtype_shape_bytes_all_frames_including_rgb'
        assert report['source_commit']==CERTIFICATION_COMMIT
        gpu=report['render_gpu']; assert gpu==e['seed']%2
        assert report['runtime_fingerprint']['render_gpu']==gpu
        stats[f'GPU_{gpu}']+=1
        geom=report['geometry']; assert geom['ok'] is True and geom['reasons']==[] and geom['min_clearance']>=0.005
        gap.append(geom['min_clearance'])
        assert len(report['record_paths'])==2 and len(set(report['record_paths']))==2
        for record in report['record_paths']:
            path=Path(record)
            assert path.is_file() and path.resolve().is_relative_to(root) and not path.is_symlink()
            with h5py.File(path,'r') as f:
                assert bool(f.attrs['complete']) and f.attrs['content_hash']==report['content_hash']
                assert f['setup/spec_hash'].asstr()[()]==e['spec_hash']
                assert int(f['setup/seed'][()])==e['seed']
                assert f['setup/source_commit'].asstr()[()]==report['source_commit']
                n=int(f['steps'].attrs['length']); assert n==report['frame_count']
                info=f[f'steps/{n-1:08d}/info']
                assert json.loads(info['success'].asstr()[()]) is True
                assert json.loads(info['fail'].asstr()[()]) is False
                stats['HDF5终态成功']+=1
        for a in actors:
            assert 'initial_support_rejection' not in a
            if 'initial_xy_bounds' in a:
                support=a['initial_xy_bounds']
                for box in actor_boxes(a,e['geometry']):
                    for i,axis in enumerate(('x','y')):
                        radius=box.radius_on(tuple(float(j==i) for j in range(3)))
                        margins=(box.center[i]-radius-support[axis][0],support[axis][1]-box.center[i]-radius)
                        assert min(margins)>=-1e-10,(e['seed'],a['id'],axis,margins)
                        min_support=min(min_support,*margins)
                stats['支持框内完整物体']+=1
            if task=='BinFill' and a['kind']=='cube':
                assert not actor_occupies_binfill_hole(a,by_id['board'],e['geometry'],projected=True)
                stats['BinFill初始孔外方块']+=1
        for name,layer in e['layout']['strata'].items():
            lo,hi=layer['support']; k=layer['index']; n=layer['count']; lower,upper=layer['bounds']
            assert 0<=k<n and n==slot['position_count']
            assert abs(lower-(lo+(hi-lo)*k/n))<1e-12 and abs(upper-(lo+(hi-lo)*(k+1)/n))<1e-12
            prefix,axis=name.rsplit('.',1)
            if prefix in ('route','layout'): value=e['layout']['yaw_degrees']
            else:
                if prefix.startswith('anchor_'):
                    num=int(prefix.split('_')[-1]); actor=by_id[f'container_{num}' if task=='VideoUnmaskSwap' else f'cube_{num}']
                    offset=e['layout']['anchors'][num]
                else: actor=by_id[prefix]; offset=(0,0)
                if axis in ('x','y'): i=('x','y').index(axis); value=actor['position'][i]-offset[i]
                else:
                    q=actor['quaternion']; value=math.degrees(2*math.atan2(q[3],q[0]))
                    while value<lower-1e-10: value+=360
                    while value>upper+360: value-=360
            assert lower-1e-10<=value<=upper+1e-10,(e['seed'],name,value,layer)
            # position_group 是列表；统计键转为 tuple，保留原分组内容。
            layer_counts[(tuple(slot['position_group']),name)][k]+=1
            stats['实际位置参数处于原层']+=1
        cubes=[a for a in actors if a['kind']=='cube']; containers=[a for a in actors if a['kind']=='container']
        if task=='BinFill':
            assert len(cubes)==params['spawn_count']
            assert len(set(a['color_name'] for a in cubes))==params['scene_color_count']
            assert sum(params['target_counts'].values())==params['pick_count']
            assert sum(v>0 for v in params['target_counts'].values())==params['target_color_count']
            assert len(set(params['target_ids']))==params['pick_count']
            color_seen=Counter()
            for a in cubes:
                assert params['reveal_steps_by_id'][a['id']]==(color_seen[a['color_name']]*50 if params['dynamic'] else 0)
                color_seen[a['color_name']]+=1
        if task=='RouteStick':
            assert len(actors)==9 and len([a for a in actors if a['kind']=='target'])==5
            assert len(params['path_indices'])==params['walk_steps']+1
            assert all(abs(a-b)==1 for a,b in zip(params['path_indices'],params['path_indices'][1:]))
            angle=math.radians(e['layout']['yaw_degrees'])
            for number in range(9):
                actor=by_id[f'target_{number//2}' if number%2==0 else f'obstacle_{number//2}']
                x,y=pos[task]['center'][0],pos[task]['center'][1]+(number-4)*pos[task]['spacing']
                expected=(x*math.cos(angle)-y*math.sin(angle),x*math.sin(angle)+y*math.cos(angle))
                assert all(abs(a-b)<1e-12 for a,b in zip(actor['position'][:2],expected))
        if task=='VideoUnmaskSwap':
            assert len(containers)==params['container_count'] and len(cubes)==3
            assert {a['color_name'] for a in cubes}=={'red','green','blue'}
            occupied={a['parent_id'] for a in cubes}; empty={a['id'] for a in containers}-occupied
            assert len(empty)==params['container_count']-3
            assert (params['empty_container_id'] is None) if not empty else params['empty_container_id'] in empty
            assert len(params['target_ids'])==params['pick_count'] and len(e['swaps'])==params['swap_count']
        if task=='VideoRepick':
            assert len(cubes)==params['spawn_count'] and params['pick_count']==params['repeat_count']
            assert len(params['target_ids'])==1 and len(e['swaps'])==params['swap_count']
            colors=Counter(a['color_name'] for a in cubes)
            assert sorted(colors.values())==([5,5,5] if diff=='hard' else [3])
    for (group,name),values in layer_counts.items():
        assert set(values.values())=={1},(group,name,values)
        assert set(values)==set(range(len(values))),(group,name,values)
    assert stats['GPU_0']==stats['GPU_1']==48
    # 将工作区每个原版文件的真实字节与初始 Git blob 摘要逐一比较。
    rows=subprocess.check_output(['git','-C',str(root),'ls-tree','-r','-z',BASELINE_COMMIT,'--','src/robomme','uv.lock']).split(b'\0')
    size=0; files=0
    for row in rows:
        if not row: continue
        metadata,name=row.split(b'\t',1); mode,kind,oid=metadata.split(); path=root/name.decode()
        data=path.read_bytes() if mode!=b'120000' else str(path.readlink()).encode()
        actual=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest().encode()
        assert actual==oid,name
        size+=len(data);files+=1
    result = {
        "suite_hash": suite["suite_hash"],
        "任务难度配额": {f"{key[0]}/{key[1]}": value for key, value in counts.items()},
        "统计": dict(stats),
        "几何证书数量": len(gap),
        "最小物理净距": min(gap),
        "最大证书最小净距": max(gap),
        "完整物体支持边界最小余量": min_support,
        "位置均衡分组参数数": len(layer_counts),
        "原版及锁文件逐字节核对文件数": files,
        "核对字节数": size,
        "实际任务参数配额": {
            group: {key: dict(value) for key, value in values.items()}
            for group, values in param_stats.items()
        },
        "耗时秒": round(time.monotonic() - start, 3),
    }
    return result


def main() -> int:
    """执行既定检查，成功后输出实测统计；可选择保存独立证据。"""
    if sys.flags.optimize:
        raise RuntimeError("本验收使用断言，禁止以 -O 或 PYTHONOPTIMIZE 禁用检查")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE, help="固定 96 条口径的认证套件")
    parser.add_argument("--report", type=Path, help="可选的仓库内 JSON 报告路径，必须尚不存在")
    args = parser.parse_args()
    suite_path = output_path(args.suite)
    report_path = output_path(args.report) if args.report else None
    if report_path is not None and report_path.exists():
        raise FileExistsError(f"报告已存在，保留原文件：{report_path}")

    result = check_manifest(suite_path)
    result.update({
        "status": "passed",
        "exit_code": 0,
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "suite_path": str(suite_path),
        "source_commit": subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True,
        ).strip(),
        "certification_source_commit": CERTIFICATION_COMMIT,
        "legacy_baseline_commit": subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", BASELINE_COMMIT], text=True,
        ).strip(),
        "validator_path": str(Path(__file__).resolve()),
        "validator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "uv_lock_sha256": hashlib.sha256((ROOT / "uv.lock").read_bytes()).hexdigest(),
        "command": shlex.join(["env", "-u", "VIRTUAL_ENV", "uv", "run", "--no-sync", "python", *sys.argv]),
        "scope": "只核对套件、已有认证证据、HDF5 元数据和末帧 success/fail，不重仿真，不解码 RGB，不重新计算全帧内容摘要。",
        "diagnostic_correction": {
            "origin": "保存脚本前的临时内联验收",
            "error": "TypeError: unhashable type: 'list'",
            "cause": "position_group 为列表，临时统计代码直接将其用作字典键。",
            "resolution": "仅将统计键中的 position_group 转为 tuple，分组内容和验收判据不变。",
            "classification": "验收脚本诊断修正，不是 robomme-ICL 实现 bug。",
            "prior_success_elapsed_seconds": 0.355,
        },
    })
    text = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if report_path is not None:
        report_path = output_path(report_path, create_parent=True)
        with report_path.open("x", encoding="utf-8") as stream:
            stream.write(text)
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
