import time, sys
sys.path.insert(0, "."); from mclib import *
lay = inner_layout("VideoUnmaskSwap", 9100001)
S = inner_states(lay["bins"])
t=time.perf_counter(); n=0; ok=0
for a in range(4):
    for b in range(a+1,4):
        ok += inner_pair_ok(S,a,b); n+=1
print("inner 6 pairs", time.perf_counter()-t, ok)
