from pathlib import Path

from PIL import Image

from streamlit_demo.index import DatasetIndex, FileEntry
from streamlit_demo.media import PreviewManager


def entry(path: Path) -> FileEntry:
    stat = path.stat()
    return FileEntry(path.name, path, stat.st_size, stat.st_mtime_ns, path.suffix.lower())


def test_large_image_is_compressed_to_budget(tmp_path: Path):
    path = tmp_path / "large.bmp"
    Image.new("RGB", (2400, 1800), (30, 120, 210)).save(path)
    manager = PreviewManager(tmp_path, 8)
    preview = manager.prepare(entry(path), "image", 80_000)
    assert preview.error == ""
    assert preview.source.startswith("data:image/webp;base64,")
    assert preview.size <= 80_000
    assert "压缩" in preview.notice


def test_text_truncation_and_chinese_decoding(tmp_path: Path):
    path = tmp_path / "sample.txt"
    path.write_text("中文内容\n" * 100, encoding="utf-8")
    preview = PreviewManager(tmp_path, 8).prepare(entry(path), "text", 50)
    assert "中文" in preview.source
    assert "截断" in preview.notice


def test_cache_pruning(tmp_path: Path):
    manager = PreviewManager(tmp_path, 0.001)
    for index in range(3):
        path = manager.cache_dir / f"{index}.bin"
        path.write_bytes(b"x" * 700)
    manager._prune()
    assert sum(path.stat().st_size for path in manager.cache_dir.iterdir()) <= manager.cache_limit_bytes


def test_incompatible_video_is_transcoded_to_h264_preview():
    project_root = Path(__file__).parents[1]
    data_dir = project_root / "sample_data" / "video"
    video = next(item for item in DatasetIndex(data_dir, "video").entries if item.extension == ".mkv")
    preview = PreviewManager(data_dir, 8).prepare(video, "video", 500_000)
    assert preview.error == ""
    assert preview.source.startswith("data:video/mp4;base64,")
    assert preview.size <= 525_000
    assert "压缩" in preview.notice
