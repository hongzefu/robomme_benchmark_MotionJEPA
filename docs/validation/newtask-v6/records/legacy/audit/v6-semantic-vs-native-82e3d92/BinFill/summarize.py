import json
R=json.load(open('/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/BinFill/records.json'))
for r in R:
    print('==',r['kind'],r['difficulty'],r['episode'],'steps',r['n_steps'],'segs',len(r['segments']),'bounds',len(r['boundaries']))
    gc=r['grounded_checks']
    bad=[g for g in gc if g['expected'] and g['color_at_point']!=g['expected']]
    print(' grounded picks',sum(1 for g in gc if g['expected']),'mismatch',[(g['t'],g['text'],g['color_at_point'],g['color_px']) for g in bad])
    oth=sorted(set((g['text'][:40],tuple(g['world_xyz'])) for g in gc if not g['expected']))
    print(' non-pick grounded',oth)
    dm=[(d['seg_start'],d['named_color'],d['above_hole_color']) for d in r['drops'] if d['named_color']!=d['above_hole_color']]
    print(' drops',len(r['drops']),'mismatch',dm)
    print(' t0',{c:v['n'] for c,v in r['table_blobs_t0'].items()},'last',{c:v['n'] for c,v in r['table_blobs_last'].items()})
    if 'trace' in r:
        t=r['trace'];print(' trace spawn',t['objects.spawn_numbers'],'target',t['objects.target_numbers'],'dyn',t['layout.dynamic'],'redraws',t.get('objects.color_redraws'),'fallback',t.get('objects.color_mix_fallback'),'maxcomp',t.get('objects.color_mix_max_component'),'board',[round(x,3) for x in t['layout.board.offsets']])
