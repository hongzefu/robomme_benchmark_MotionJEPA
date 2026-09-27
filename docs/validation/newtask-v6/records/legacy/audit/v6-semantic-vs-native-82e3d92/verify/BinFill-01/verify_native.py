import h5py, glob, re, json

files = sorted(glob.glob('/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v6/v1/base/B/BinFill_episode_*/hdf5_files/*.h5'))
print('n files', len(files))
total_segments = 0
total_nocoord = 0
details = []
for fp in files:
    f = h5py.File(fp, 'r')
    e = f[list(f.keys())[0]]
    n_steps = len([k for k in e.keys() if k.startswith('timestep_')])
    prev = None
    seg_start = 0
    texts = []
    for t in range(n_steps):
        try:
            txt = e[f'timestep_{t}/info/grounded_subgoal_online'][()].decode()
        except KeyError:
            txt = None
        texts.append(txt)
    # segment by change in text prefix ignoring coordinate? Actually segment by change in underlying subgoal - approximate via text without coord suffix
    # simpler: find contiguous run boundaries where text (with coord stripped) changes name meaningfully.
    def strip_coord(s):
        return re.sub(r'\s*at\s*<[^>]*>','',s) if s else s
    stripped = [strip_coord(t) for t in texts]
    segs=[]
    i=0
    while i < n_steps:
        j=i
        while j+1<n_steps and stripped[j+1]==stripped[i]:
            j+=1
        segs.append((i,j,stripped[i]))
        i=j+1
    for (s,eidx,name) in segs:
        total_segments+=1
        has_coord = any('<' in (texts[k] or '') for k in range(s,eidx+1))
        if not has_coord:
            total_nocoord+=1
            details.append((fp,s,eidx,name))
print('total_segments',total_segments,'total_nocoord',total_nocoord)
for d in details:
    print(d)
