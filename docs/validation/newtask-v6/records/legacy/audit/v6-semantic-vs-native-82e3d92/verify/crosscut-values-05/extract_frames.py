import h5py, cv2, sys, os

def extract(h5path, out_prefix, timesteps):
    with h5py.File(h5path, 'r') as f:
        ep = list(f.keys())[0]
        difficulty = f[ep]['setup']['difficulty'][()]
        if isinstance(difficulty, bytes):
            difficulty = difficulty.decode()
        goal = f[ep]['setup']['task_goal'][()]
        if hasattr(goal, '__len__') and not isinstance(goal, (str, bytes)):
            goal = goal[0]
        if isinstance(goal, bytes):
            goal = goal.decode()
        print(f"{h5path}: difficulty={difficulty} goal={goal}")
        for t in timesteps:
            key = f"timestep_{t}"
            if key not in f[ep]:
                print(f"  {key} not present, skipping")
                continue
            img = f[ep][key]['obs']['front_rgb'][()]
            out_path = f"{out_prefix}_t{t}.png"
            cv2.imwrite(out_path, cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
            print(f"  saved {out_path}")

if __name__ == "__main__":
    h5path = sys.argv[1]
    out_prefix = sys.argv[2]
    timesteps = [int(x) for x in sys.argv[3:]]
    extract(h5path, out_prefix, timesteps)
