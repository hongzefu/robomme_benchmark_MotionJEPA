# vendoring 来源清单（第 24 条）

| 项 | 值 |
|---|---|
| 来源仓库 | `hongzefu/robomme_benchmark_MotionJEPA` |
| 来源分支 | `newtask-v2.1refractor` |
| 来源 commit | `ce72b04fdb7806dbc98de2baa3c92118b98e6902`（2026-09-21，`11.33 登记四个4CPU占位job编号`） |
| 源路径 | `src/robomme/robomme_env/utils/bin_collision.py` |
| 本地路径 | `src/robomme_xhard/collision/bin_collision.py` |
| 文件 sha256 | `bbe87eec3c36ab54e703a6ff741a5fdd3217c11e2a1541eb95d8f013c852302b` |
| 行数 | 899 |
| 拷贝日期 | 2026-10-12 |
| 修改 | **无**。逐字节拷贝；阈值常量 `EPS_M=1e-6`、`MAX_DEPTH=20`、`MAX_INTERVALS=4096` 原样，不加放宽开关。 |

核对命令（任一不等即 `XHARD_COLL_VENDOR=FAIL`）：

```bash
git fetch origin newtask-v2.1refractor
git show ce72b04fdb7806dbc98de2baa3c92118b98e6902:src/robomme/robomme_env/utils/bin_collision.py | sha256sum
sha256sum src/robomme_xhard/collision/bin_collision.py
```

升级来源时：在此表追加新 commit、新 sha256 与 `git diff <旧> <新>` 的差异摘要，不覆盖旧行。本包只在 `__init__.py` 补 `SwapCollisionError` / `SwapBindingError` 两个异常类，不改判据。
