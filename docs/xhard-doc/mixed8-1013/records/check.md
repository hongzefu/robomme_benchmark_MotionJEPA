# 混合档 H5 校验

```text
H5_SCHEMA=FAIL files=99 steps=69222 missing=1 extra=0 dtype_shape=0
H5_CONTENT=FAIL files=99 fails=1
H5_COUNTS=FAIL tasks=16 episodes=8 per_tier_ok=0
PLAN_VS_RECORD=FAIL files=52 rules_expected=80 rules_run=79 mismatch=1 exempt=12
```

## 样本与失败证据

```json
{
  "missing": [
    "('VideoPlaceOrder', 3) 首条样本缺失或重复"
  ],
  "product_errors": [],
  "failures": [],
  "identity": {
    "episodes": 128,
    "missing": 3,
    "dup": 0,
    "unknown": 0,
    "mismatch": 1,
    "pass": false,
    "errors": [
      "('VideoPlaceOrder', 3) 缺少成功记录",
      "('VideoPlaceOrder', 3) 缺少metadata",
      "('VideoPlaceOrder', 3) 缺少H5",
      "('VideoPlaceOrder', 3) attempt 必须为连续失败后唯一成功，实际 [0, 1, 2]"
    ]
  }
}
```
