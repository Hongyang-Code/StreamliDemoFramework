from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path


DEFAULT_PREVIEW_LIMITS = {"image": 8.0, "video": 32.0, "text": 1.0}
DEFAULT_TITLE = "实验结果展示与标注"


@dataclass(frozen=True)
class AppConfig:
    title: str
    mode: str
    data_dir: Path
    label_dir: Path
    preview_limit_mb: float
    page_payload_limit_mb: float
    preview_cache_mb: float


def parse_args(argv: list[str] | None = None) -> AppConfig:
    parser = argparse.ArgumentParser(description="Streamlit 多模态实验结果展示与标注工具")
    parser.add_argument("--title", default=DEFAULT_TITLE, help=f"页面标题，默认：{DEFAULT_TITLE}")
    parser.add_argument("--mode", required=True, choices=("image", "video", "text"))
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--preview-limit-mb", type=float)
    parser.add_argument("--page-payload-limit-mb", type=float, default=128.0)
    parser.add_argument("--preview-cache-mb", type=float, default=2048.0)
    args = parser.parse_args(argv)

    data_dir = args.data_dir.expanduser().resolve()
    title = args.title.strip()
    if not title:
        parser.error("--title 不能为空")
    if any(ord(character) < 32 or ord(character) == 127 for character in title):
        parser.error("--title 不能包含控制字符")
    if not data_dir.is_dir():
        parser.error(f"数据目录不存在或不是目录: {data_dir}")
    if args.preview_limit_mb is not None and args.preview_limit_mb <= 0:
        parser.error("--preview-limit-mb 必须大于 0")
    if args.page_payload_limit_mb <= 0 or args.preview_cache_mb <= 0:
        parser.error("页面与缓存上限必须大于 0")

    label_dir = data_dir / "label"
    label_dir.mkdir(parents=True, exist_ok=True)
    probe = label_dir / ".write_probe"
    try:
        probe.touch(exist_ok=True)
        probe.unlink(missing_ok=True)
    except OSError as exc:
        parser.error(f"标签目录不可写: {label_dir}: {exc}")

    return AppConfig(
        title=title,
        mode=args.mode,
        data_dir=data_dir,
        label_dir=label_dir,
        preview_limit_mb=args.preview_limit_mb or DEFAULT_PREVIEW_LIMITS[args.mode],
        page_payload_limit_mb=args.page_payload_limit_mb,
        preview_cache_mb=args.preview_cache_mb,
    )
