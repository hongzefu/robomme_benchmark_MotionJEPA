"""Independent reproduction of finding ButtonUnmask-01.

Read-only. Only reads:
- git show AUDIT_BASE:<path> for source anchors
- the h5 files already delivered under artifacts/newtask-v6/...
- the NO_OBJECT mp4 frame count via cv2
- new-tier-index.json
- native ButtonUnmask episodes 0,1,2,3,4,6,7,10,11 under artifacts/newtask-v6/v1/base/B/

Writes only into this verify subdir.
"""
import glob
import json
import subprocess
from pathlib import Path

import cv2
import h5py

REPO = "/data/hongzefu/robomme_benchmark_MotionJEPANewTask"
AUDIT_BASE = "82e3d922b78d48ec1e825b168cccc0e1b8c690c1"

XHARD4_H5 = f"{REPO}/artifacts/newtask-v6/v6-01/xhard4/rollout/run1/episodes/ButtonUnmask_episode_6/hdf5_files/ButtonUnmask_ep6_seed6800600.h5"
NO_OBJECT_MP4 = (
    f"{REPO}/artifacts/newtask-v6/v6-01/xhard4/rollout/run1/episodes/ButtonUnmask_episode_6/videos/"
    "success_NO_OBJECT_ButtonUnmask_ep6_seed6800600_xhard4_first_press_the_button_then_pick_up_the_container_hiding_the_green_cube_next_pick_up_another_container_hiding_the_blue_cube_finally_pick_up_another_container_hiding_the_red_cube.mp4"
)
NATIVE_EPISODES = [0, 1, 2, 3, 4, 6, 7, 10, 11]

result = {"audit_base": AUDIT_BASE, "finding_id": "ButtonUnmask-01"}

# 1. xhard4 ep6 blue-cube segment: grounded_subgoal vs grounded_subgoal_online for all steps t280-385
f = h5py.File(XHARD4_H5, "r")
ep = f["episode_6"]
names = sorted((k for k in ep if k.startswith("timestep_")), key=lambda k: int(k.split("_")[1]))
seg = [n for n in names if 280 <= int(n.split("_")[1]) <= 384]  # 385 is next segment's boundary step
gs_vals = {ep[n]["info/grounded_subgoal"][()].decode() for n in seg}
gso_vals = {ep[n]["info/grounded_subgoal_online"][()].decode() for n in seg}
result["xhard4_ep6_blue_segment"] = {
    "n_steps": len(seg),
    "grounded_subgoal_unique_values": sorted(gs_vals),
    "grounded_subgoal_online_unique_values": sorted(gso_vals),
    "gs_has_no_coords_for_whole_segment": gs_vals == {"pick up the container that hides the blue cube"},
    "gso_has_coords": any("<78, 111>" in v for v in gso_vals),
    "choice_action_t280": json.loads(ep["timestep_280"]["action/choice_action"][()].decode()),
    "choice_action_t356_near_grasp": json.loads(ep["timestep_356"]["action/choice_action"][()].decode()),
}

# 2. NO_OBJECT mp4 frame count
cap = cv2.VideoCapture(NO_OBJECT_MP4)
n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
result["no_object_mp4_frame_count"] = n_frames

# 3. new-tier-index.json: xhard4 ep6 entry lists 2 mp4s, others list 1
index = json.loads(Path(f"{REPO}/artifacts/audit/v6-semantic-vs-native-82e3d92/new-tier-index.json").read_text())
bu_entries = index["ButtonUnmask"]
ep6_entries = [e for e in bu_entries if e["episode"] == 6]
result["new_tier_index_ep6_mp4_counts"] = {e["difficulty"]: len(e["mp4"]) for e in ep6_entries}

# 4. Native tiers: 9 episodes, every pick segment has coordinates, zero NO_OBJECT videos
native_rows = []
for epn in NATIVE_EPISODES:
    d = f"{REPO}/artifacts/newtask-v6/v1/base/B/ButtonUnmask_episode_{epn}"
    videos = glob.glob(f"{d}/videos/*.mp4")
    no_object_videos = [v for v in videos if "NO_OBJECT" in v]
    h5files = glob.glob(f"{d}/hdf5_files/*.h5")
    assert len(h5files) == 1
    nf = h5py.File(h5files[0], "r")
    ekey = list(nf.keys())[0]
    e2 = nf[ekey]
    names2 = sorted((k for k in e2 if k.startswith("timestep_")), key=lambda k: int(k.split("_")[1]))
    prev = None
    picks = []
    for name in names2:
        t = e2[name]
        ss = t["info/simple_subgoal"][()].decode()
        if ss != prev and ss.startswith("pick up"):
            gs = t["info/grounded_subgoal"][()].decode()
            picks.append({"timestep": int(name.split("_")[1]), "simple_subgoal": ss, "grounded_subgoal": gs, "has_coords": "<" in gs})
        prev = ss
    native_rows.append({"episode": epn, "n_no_object_videos": len(no_object_videos), "picks": picks})

result["native_tier_rows"] = native_rows
result["native_all_picks_have_coords"] = all(p["has_coords"] for row in native_rows for p in row["picks"])
result["native_total_no_object_videos"] = sum(row["n_no_object_videos"] for row in native_rows)

# 5. source anchor check: process_segmentation only fills centers on subgoal switch, no_object_flag path
seg_src = subprocess.check_output([
    "git", "-C", REPO, "show", f"{AUDIT_BASE}:src/robomme/robomme_env/utils/segmentation_utils.py"
]).decode()
result["source_anchor_present"] = {
    "process_segmentation_def": "def process_segmentation(" in seg_src,
    "switch_gate": "if current_subgoal_segment != previous_subgoal_segment:" in seg_src,
    "no_object_flag_var": "no_object_flag" in seg_src,
}
task_src = subprocess.check_output([
    "git", "-C", REPO, "show", f"{AUDIT_BASE}:src/robomme/robomme_env/ButtonUnmask.py"
]).decode()
result["source_anchor_present"]["_append_xhard_pick_tasks_def"] = "_append_xhard_pick_tasks" in task_src
result["source_anchor_present"]["subgoal_segment_template"] = (
    "subgoal_segment\":f\"pick up the container at <> that hides the {self.color_names" in task_src
    or 'subgoal_segment":f"pick up the container at <> that hides the {self.color_names' in task_src
)

# 6. plan mentions of this mechanism (expect none)
try:
    plan_src = subprocess.check_output([
        "git", "-C", REPO, "show", f"{AUDIT_BASE}:0925-newtask-release-v6-plan.md"
    ]).decode()
    result["plan_mentions_no_object_or_occlusion"] = any(
        kw in plan_src for kw in ["NO_OBJECT", "no_object", "遮挡", "occlu"]
    )
except subprocess.CalledProcessError:
    result["plan_mentions_no_object_or_occlusion"] = None

Path("/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/verify/ButtonUnmask-01/verify_result.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2) + "\n"
)
print(json.dumps(result, ensure_ascii=False, indent=2))
