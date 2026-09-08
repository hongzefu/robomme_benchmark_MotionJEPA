"""归档的模块入口；当前使用 scripts 下四个独立脚本。"""

if __package__:
    from .cli import main
else:
    from cli import main


if __name__ == "__main__":
    raise SystemExit(main())
