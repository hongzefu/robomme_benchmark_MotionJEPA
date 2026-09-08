"""只读取认证清单，保存四任务实际次数配额、布局和位置分布图。"""

import argparse
from pathlib import Path

from _icl.common import safe_output


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    from _icl.plots import plot_distributions

    result = plot_distributions(args.suite, safe_output(args.output_dir))
    print(f"分布图与统计已保存：{result['summary_path']}；复用={result['resumed']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
