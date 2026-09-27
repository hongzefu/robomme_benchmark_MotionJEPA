import sys,json,h5py,numpy as np
sys.path.insert(0,sys.argv[1]); from geom import world
r=json.load(open(sys.argv[1]+'/scan_raw.json'))
x=[x for x in r if x['task']=='VideoUnmask' and x['setup']['difficulty']=='xhard1' and x['episode']==0][0]
with h5py.File(x['h5']) as f:
    g=f['episode_0']
    for t in (0,40):
        pw,d=world(g,t)
        print(t,'depth range',d.min(),d.max())
        z=pw[...,2]
        print(' z pct',np.percentile(z,[1,5,50,95,99]))
        for (u,v) in [(128,200),(33,137),(65,90),(140,170)]:
            print('  px',u,v,pw[v,u])
