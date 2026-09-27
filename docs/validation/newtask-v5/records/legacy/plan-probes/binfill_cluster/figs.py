# 俯视图：ep3 布局（按钮/孔板/方块、spawn 序号、面间距<2cm 的对）+ V4 3000 局的位置密度热图
import sys, pickle, numpy as np, matplotlib
matplotlib.use('Agg'); import matplotlib.pyplot as plt
from matplotlib.patches import Polygon, Rectangle
D='/tmp/claude-114466650/-data-hongzefu-robomme-benchmark-MotionJEPANewTask/4d4f0ebe-f95a-4495-b425-f61bacbd7855/scratchpad/v5/binfill_cluster'
sys.path.insert(0,D)
from analyze_lib import arr, spec_layouts, sq, LO, HI
import binfill_sampler as bs
specs=spec_layouts(); ep3=[L for L in specs if L['seed']==4400300][0]
sims=[L for L in pickle.load(open(D+'/sim_v4_exact.pkl','rb')) if L]
fig,ax=plt.subplots(1,2,figsize=(13,6))
a=ax[0]
a.add_patch(Rectangle((-0.3,-0.25),0.4,0.5,fill=False,ls='--',color='k'))
bx,by=ep3['button']; a.add_patch(Rectangle((bx-0.05625,by-0.05625),0.1125,0.1125,color='gray',alpha=0.4)); a.text(bx,by,'button',ha='center')
gx,gy,_=ep3['board']; a.add_patch(Rectangle((gx-0.05,gy-0.05),0.1,0.1,color='peru',alpha=0.5)); a.text(gx,gy,'board',ha='center')
colmap={'red':'r','blue':'b','green':'g'}
for c in ep3['cubes']:
    a.add_patch(Polygon(sq(c['x'],c['y'],c['yaw']),color=colmap[c['color']]))
    a.text(c['x'],c['y']+0.028,f"{c['color'][0]}{c['idx']}#{c['spawn_idx']}",ha='center',fontsize=8)
a.set_xlim(-0.33,0.2); a.set_ylim(-0.3,0.3); a.set_aspect('equal'); a.set_xlabel('x (m, +x toward camera)'); a.set_ylabel('y (m)')
a.set_title('BinFill ep3 seed4400300: name#spawn_idx')
P=np.concatenate([arr(L)[0] for L in sims])
H,xe,ye=np.histogram2d(P[:,0],P[:,1],bins=[18,23],range=[[LO[0],HI[0]],[LO[1],HI[1]]])
im=ax[1].imshow((H/H.mean()).T,origin='lower',extent=[LO[0],HI[0],LO[1],HI[1]],cmap='viridis',vmin=0.4,vmax=1.8)
plt.colorbar(im,ax=ax[1],label='density / uniform'); ax[1].set_title('V4 xhard cube centres, 3000 layouts (36000 cubes)'); ax[1].set_xlabel('x'); ax[1].set_ylabel('y')
plt.tight_layout(); plt.savefig(D+'/fig_ep3_topdown_and_density.png',dpi=90)
print('FIG_DONE')
