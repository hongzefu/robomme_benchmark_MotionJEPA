"""允许通过 uv run python -m robomme_icl 调用新版工具。"""

from .cli import main


if __name__ == "__main__":
    raise SystemExit(main())
