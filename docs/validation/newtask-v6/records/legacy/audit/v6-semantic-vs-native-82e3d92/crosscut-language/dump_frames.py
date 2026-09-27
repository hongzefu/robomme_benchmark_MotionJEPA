"""只读：按 (h5, t, 标注点) 导出 front_rgb 放大 PNG（最近邻）到本证据目录。"""
import sys, json, h5py, cv2, os
HERE = "/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/crosscut-language/frames"
os.makedirs(HERE, exist_ok=True)
for spec in json.loads(sys.argv[1]):
    f = h5py.File(spec["h5"], "r"); g = f[[k for k in f if k.startswith("episode_")][0]]
    img = g[f"timestep_{spec['t']}"]["obs"]["front_rgb"][()]
    big = cv2.resize(img, (512, 512), interpolation=cv2.INTER_NEAREST)
    for (r, c) in spec.get("pts", []):
        cv2.circle(big, (c * 2, r * 2), 12, (255, 255, 255), 1)
    out = os.path.join(HERE, spec["name"] + f"_t{spec['t']}.png")
    cv2.imwrite(out, cv2.cvtColor(big, cv2.COLOR_RGB2BGR)); print(out)
