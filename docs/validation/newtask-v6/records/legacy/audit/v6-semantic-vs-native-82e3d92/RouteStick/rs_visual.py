"""Visual verification: project targets / TCP path into front_rgb, check red highlight identity and on-screen rotation sense."""
import json, math
from pathlib import Path
import h5py, numpy as np, cv2

OUT = Path('/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/RouteStick')
R = json.load(open(OUT / 'records_raw.json'))

def target_xyz(n, th):
    t = math.radians(th); x0, y0 = -0.1, (n - 4) * 0.07
    return np.array([x0 * math.cos(t) - y0 * math.sin(t), x0 * math.sin(t) + y0 * math.cos(t), 0.01 if n % 2 == 0 else -0.01])

def proj(E, K, p):
    c = E[:, :3] @ p + E[:, 3]
    return np.array([K[0, 0] * c[0] / c[2] + K[0, 2], K[1, 1] * c[1] / c[2] + K[1, 2]])

def redness(img, uv, r=3):
    u, v = int(round(uv[0])), int(round(uv[1]))
    w = img[max(0, v - r):v + r + 1, max(0, u - r):u + r + 1].astype(float)
    red = (w[..., 0] > 150) & (w[..., 1] < 90) & (w[..., 2] < 90)
    return float(red.mean())

summary = []
for r in R:
    f = h5py.File(r['h5'], 'r'); ep = f[next(iter(f))]
    K = ep['setup/front_camera_intrinsic'][()]
    th = r['theta_spec'] if r['theta_spec'] is not None else r['theta_fit']
    T = [target_xyz(n, th) for n in range(9)]
    E0 = ep['timestep_0/obs/front_camera_extrinsic'][()]
    xyz = np.array([ep[f'timestep_{i}/obs/eef_state'][()][:3] for i in range(r['frames'])])
    seg_checks = []
    for s in r['segments']:
        e = s['end'] - 1
        img = ep[f'timestep_{e}/obs/front_rgb'][()]
        E = ep[f'timestep_{e}/obs/front_camera_extrinsic'][()]
        reds = {n: redness(img, proj(E, K, T[n])) for n in range(0, 9, 2)}
        # red at segment start for the new target (should be not-yet-highlighted unless revisited within 40 steps)
        img0 = ep[f'timestep_{s["start"]}/obs/front_rgb'][()]
        red0 = redness(img0, proj(E, K, T[s['curr']]))
        # on-screen rotation sense: project path, use y-up screen coords
        uv = np.array([proj(E, K, p) for p in xyz[s['start']:s['end']]])
        a = proj(E, K, T[s['prev']]); b = proj(E, K, T[s['curr']])
        a2 = proj(E, K, np.array([*T[s['prev']][:2], xyz[s['start'], 2]])); b2 = proj(E, K, np.array([*T[s['curr']][:2], xyz[s['start'], 2]]))  # chord at TCP height
        A = np.array([a2[0], -a2[1]]); Bv = np.array([b2[0], -b2[1]]); P = np.stack([uv[:, 0], -uv[:, 1]], 1) - A
        L = Bv - A; cr = L[0] * P[:, 1] - L[1] * P[:, 0]
        screen_dir = 'clockwise' if cr.mean() > 0 else 'counterclockwise'
        # obstacle (odd index) enclosed side: obstacle projected should lie on opposite side of path bulge -> check path passes on one side of obstacle
        odd = s['passes_odd_between'][0]
        o = proj(E, K, T[odd] + np.array([0, 0, 0.05]))
        seg_checks.append(dict(start=s['start'], end=s['end'], demo=s['demo'], label=s['label'], prev=s['prev'], curr=s['curr'],
            red_at_end=reds, red_argmax=max(reds, key=reds.get), red_expected=reds[s['curr']], red_curr_at_start=red0,
            screen_dir=screen_dir, screen_dir_ok=screen_dir == s['label_dir'], screen_side='right' if b[0] > a[0] else 'left'))
    ok_red = all(c['red_argmax'] == c['curr'] and c['red_expected'] > 0.2 for c in seg_checks)
    ok_dir = all(c['screen_dir_ok'] for c in seg_checks)
    summary.append(dict(tier=r['tier'], episode=r['episode'], n_segs=len(seg_checks), red_identity_ok=ok_red, screen_dir_ok=ok_dir,
        red_fail=[c for c in seg_checks if not (c['red_argmax'] == c['curr'] and c['red_expected'] > 0.2)][:5],
        min_red_expected=min(c['red_expected'] for c in seg_checks), camera_static=bool(all(np.allclose(ep[f'timestep_{i}/obs/front_camera_extrinsic'][()], E0) for i in range(0, r['frames'], 97))),
        seg_checks=seg_checks))
    print(r['tier'], r['episode'], 'segs', len(seg_checks), 'red_identity_ok', ok_red, 'min_red', round(summary[-1]['min_red_expected'], 2),
          'screen_dir_ok', ok_dir, 'screen_side(image-right)=label?', sum(c['screen_side'] == ('right' if 'left' in c['label'] else 'left') for c in seg_checks), '/', len(seg_checks))
    # annotated montage
    panels = []
    picks = [r['segments'][0], r['segments'][r['n_demo_segs'] - 1], r['segments'][r['n_demo_segs']], r['segments'][-1]]
    for s in picks:
        e = s['end'] - 1
        img = ep[f'timestep_{e}/obs/front_rgb'][()][..., ::-1].copy()
        E = ep[f'timestep_{e}/obs/front_camera_extrinsic'][()]
        big = cv2.resize(img, (512, 512), interpolation=cv2.INTER_NEAREST)
        uv = np.array([proj(E, K, p) for p in xyz[s['start']:s['end']]]) * 2
        for k in range(len(uv) - 1):
            cv2.line(big, tuple(int(v) for v in uv[k]), tuple(int(v) for v in uv[k + 1]), (0, 255, 255), 1)
        cv2.arrowedLine(big, tuple(int(v) for v in uv[-6]), tuple(int(v) for v in uv[-1]), (0, 255, 255), 2, tipLength=0.5)
        for n in range(0, 9, 2):
            q = proj(E, K, T[n]) * 2
            col = (0, 255, 0) if n == s['curr'] else ((255, 128, 0) if n == s['prev'] else (200, 200, 200))
            cv2.circle(big, tuple(int(v) for v in q), 14, col, 2); cv2.putText(big, str(n), (int(q[0]) - 5, int(q[1]) + 30), 0, 0.5, col, 1)
        hdr = np.full((70, 512, 3), 255, np.uint8)
        cv2.putText(hdr, f"{r['tier']} ep{r['episode']} {'DEMO' if s['demo'] else 'EXEC'} frames {s['start']}-{e}  node {s['prev']}->{s['curr']}", (4, 18), 0, 0.45, (0, 0, 0), 1)
        cv2.putText(hdr, s['label'][:62], (4, 40), 0, 0.4, (0, 0, 0), 1)
        cv2.putText(hdr, s['label'][62:] + f"  | traj={s['dir_traj']}", (4, 60), 0, 0.4, (0, 0, 0), 1)
        panels.append(np.vstack([hdr, big]))
    cv2.imwrite(str(OUT / f"frames/{r['tier']}_ep{r['episode']}_segends_f{picks[0]['end']-1:04d}_f{picks[1]['end']-1:04d}_f{picks[2]['end']-1:04d}_f{picks[3]['end']-1:04d}.png"), np.hstack(panels))
json.dump(summary, open(OUT / 'visual_checks.json', 'w'), indent=1)
