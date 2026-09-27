import cv2, numpy as np, sys, glob

def count_white_blobs(path, min_area=60):
    img = cv2.imread(path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # containers/button are light gray/white against brown wood table and gray robot arm.
    # Use a brightness threshold plus low saturation (near-white/gray) to separate from wood (orange/brown, high saturation).
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    sat = hsv[:,:,1]
    mask = (gray > 140) & (sat < 60)
    mask = mask.astype(np.uint8) * 255
    # remove top strip (robot arm / gripper region), keep y > 40 (table area)
    mask[:40, :] = 0
    num, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)
    blobs = []
    for i in range(1, num):
        area = stats[i, cv2.CC_STAT_AREA]
        if area >= min_area:
            cx, cy = centroids[i]
            blobs.append((area, cx, cy))
    return blobs, mask

if __name__ == "__main__":
    for path in sorted(sys.argv[1:]):
        blobs, mask = count_white_blobs(path)
        outmask = path.replace('.png', '_mask.png')
        cv2.imwrite(outmask, mask)
        print(f"{path}: n_blobs={len(blobs)}")
        for area, cx, cy in sorted(blobs, key=lambda b: -b[0]):
            print(f"    area={area} centroid=({cx:.1f},{cy:.1f})")
