#!/bin/bash
# NFS 暂存 → /data 搬运：只搬编排器报告已存在的片；rsync 后 --checksum 零差异才删 NFS 副本
N=/nfs/turbo/coe-chaijy-unreplicated/hongzefu/v75eval
D=/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/v7.5eval/official-rec
mkdir -p "$D"
while true; do
  for src in "$N"/stage/*/*/s*; do
    [ -d "$src" ] || continue
    rel=${src#$N/stage/}; run=${rel%%/*}; shard=${rel##*/}
    rep="$N/reports/$run-$shard.json"
    [ "$run" = R1smoke ] && rep="$N/reports/R1smoke-done.json"
    pol=${rel#*/}; pol=${pol%%/*}; [ -f "$rep" ] || rep="$N/reports/$run-$pol-$shard.json"
    [ -f "$rep" ] || continue
    mkdir -p "$D/$(dirname "$rel")"
    rsync -a "$src/" "$D/$rel/" || { echo "MOVE_FAIL rsync $rel"; continue; }
    n=$(rsync -a --checksum --dry-run --itemize-changes "$src/" "$D/$rel/" | wc -l)
    if [ "$n" = 0 ]; then rm -rf "${src:?}"; echo "MOVED $rel $(du -sh "$D/$rel" | cut -f1) $(date -Is)"; else echo "MOVE_DIFF $rel items=$n"; fi
  done
  df -BG --output=avail /data | tail -1 | sed 's/^/DATA_FREE /'
  sleep 600
done
