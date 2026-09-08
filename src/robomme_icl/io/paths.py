"""所有新产物必须实际存储在当前仓库内。"""

from pathlib import Path


def repository_root() -> Path:
    """沿源码位置寻找本仓库，不根据调用者的工作目录猜测。"""
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").is_file() and (
            parent / "src" / "robomme"
        ).is_dir():
            return parent
    raise ValueError("无法从 robomme_icl 源码位置定位仓库根目录")


def output_path(value: str | Path, *, create_parent: bool = False) -> Path:
    """校验实体路径及最近已有父目录，拒绝符号链接和仓库外路径。"""
    root = repository_root().resolve()
    requested = Path(value).expanduser().absolute()
    for item in (requested, *requested.parents):
        if item.is_symlink():
            raise ValueError(f"输出路径不能包含符号链接：{item}")
    resolved = requested.resolve()
    if resolved == root or not resolved.is_relative_to(root):
        raise ValueError(f"输出路径必须位于仓库内：{resolved}")
    ancestor = resolved.parent
    while not ancestor.exists():
        ancestor = ancestor.parent
    if not ancestor.is_dir():
        raise ValueError(f"输出父路径不是目录：{ancestor}")
    if create_parent:
        resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved
