#!/bin/bash
# 席位内：restage.sh <seat> <cond>:<policy> [<cond>:<policy> ...]
# 只处理显式点名、且对应步骤已结束的 /tmp/v75-<cond>-<seat>-<policy>-<job>（绝不用通配符扫全部目录——会误删在跑步骤的输出）
N=/nfs/turbo/coe-chaijy-unreplicated/hongzefu/v75eval
SEAT=$1; shift; J=${SLURM_JOB_ID:?}
rc=0; n_ok=0
for cp in "$@"; do
  COND=${cp%%:*}; POL=${cp##*:}
  d=/tmp/v75-$COND-$SEAT-$POL-$J
  [ -d "$d" ] || { echo "RESTAGE_ABSENT $d"; continue; }
  if pgrep -u "$USER" -f "[r]un_seat.sh .*--cond $COND .*--out $d" >/dev/null; then echo "RESTAGE_BUSY $d"; rc=8; continue; fi
  DST=$N/stage/$COND/$POL/s-$SEAT; mkdir -p "$DST"
  if rsync -rt "$d/" "$DST/"; then n=$(rsync -rc --dry-run --out-format="%n" "$d/" "$DST/" | { grep -v "/$" || true; } | wc -l); else n=err; fi
  if [ "$n" = 0 ]; then
    rm -rf "${d:?}"; printf '{"rc": 0, "restaged": true, "src": "%s", "end": "%s"}\n' "$d" "$(date -Is)" > "$N/reports/$COND-$POL-s-$SEAT.json"
    echo "RESTAGED cond=$COND policy=$POL seat=$SEAT dst=$DST"; n_ok=$((n_ok+1))
  else echo "RESTAGE_FAIL $d n=$n"; rc=7; fi
done
echo "RESTAGE_DONE seat=$SEAT ok=$n_ok rc=$rc"; exit $rc
