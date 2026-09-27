import json,re,cv2
R=json.load(open('/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/SwingXtimes/raw_extract.json'))
ORD=["first","second","third","fourth","fifth","sixth","seventh","eighth","ninth","tenth"]
W={w:i+1 for i,w in enumerate("one two three four five six seven eight nine ten eleven twelve".split())}
out=[]
for r in R:
    names=[s['simple'] for s in r['segments']]
    col=r['goal_color']; n=W.get(r['goal_word'],1)
    exp=[f"pick up the {col} cube"]
    for i in range(n):
        o=ORD[i] if i<10 else f"{i+1}th"
        exp+= [f"move to the top of the right-side target for the {o} time", f"move to the top of the left-side target for the {o} time"]
    exp+=[f"put the {col} cube on the table","press the button","All tasks completed"]
    letters=[]
    for fr,ca in r['choice_changes']:
        c=json.loads(ca)['choice']
        if not letters or letters[-1]!=c: letters.append(c)
    # full choice sequence needs all frames; choice_changes is truncated at 60 -> recompute from segments count
    cap=[cv2.VideoCapture(m) for m in r['mp4']]
    vinfo=[(int(c.get(cv2.CAP_PROP_FRAME_COUNT)),int(c.get(cv2.CAP_PROP_FRAME_WIDTH)),int(c.get(cv2.CAP_PROP_FRAME_HEIGHT))) for c in cap]
    rng=r['n_frames']
    out.append(dict(tier=r['difficulty'],ep=r['episode'],chain_match=names==exp,n=n,frames=rng,video=vinfo,letters_head=letters))
    print(r['difficulty'],r['episode'],'chain==expected',names==exp,'n',n,'frames',rng,'video',vinfo,letters)
    if names!=exp:
        for a,b in zip(names,exp):
            if a!=b: print('   diff',a,'|',b)
json.dump(out,open('/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/SwingXtimes/seqcheck.json','w'),indent=1)
