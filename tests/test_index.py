import resource
from pathlib import Path

from streamlit_demo.index import DatasetIndex, FileEntry


def test_index_is_flat_filtered_sorted_and_supports_symlinks(tmp_path: Path):
    (tmp_path / "b.JPG").write_bytes(b"b")
    (tmp_path / "a.png").write_bytes(b"a")
    (tmp_path / "ignore.txt").write_text("text")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "hidden.jpg").write_bytes(b"hidden")
    (tmp_path / "label").mkdir()
    (tmp_path / "linked.jpeg").symlink_to(tmp_path / "a.png")
    (tmp_path / "broken.jpg").symlink_to(tmp_path / "missing.jpg")

    index = DatasetIndex(tmp_path, "image")

    assert [entry.name for entry in index.entries] == ["a.png", "b.JPG", "linked.jpeg"]
    assert [entry.name for entry in index.page(2, 2)] == ["linked.jpeg"]
    assert "hidden.jpg" not in index.names


def test_text_extensions(tmp_path: Path):
    for name in ("a.txt", "b.log", "c.csv", "d.json", "e.md", "f.yaml", "g.yml", "no.jpg"):
        (tmp_path / name).write_text("x")
    index = DatasetIndex(tmp_path, "text")
    assert len(index.entries) == 7


def test_hundred_thousand_entry_pagination_stays_bounded(tmp_path: Path):
    index = DatasetIndex.__new__(DatasetIndex)
    index.data_dir = tmp_path
    index.mode = "image"
    index.entries = tuple(
        FileEntry(f"sample_{number:06d}.jpg", tmp_path / f"sample_{number:06d}.jpg", 1, number, ".jpg")
        for number in range(100_000)
    )
    index._names = frozenset()
    rss_before_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    pages = [index.page(page, 24) for page in range(1, 101)]
    rss_after_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    assert all(len(page) == 24 for page in pages)
    assert sum(len(page) for page in pages) == 2_400
    assert rss_after_kb - rss_before_kb < 100 * 1024
