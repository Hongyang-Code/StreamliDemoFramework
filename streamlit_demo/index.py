from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


EXTENSIONS = {
    "image": {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tif", ".tiff"},
    "video": {".mp4", ".webm", ".ogg", ".mov", ".avi", ".mkv", ".m4v"},
    "text": {".txt", ".log", ".csv", ".json", ".md", ".yaml", ".yml"},
}


@dataclass(frozen=True, slots=True)
class FileEntry:
    name: str
    path: Path
    size: int
    mtime_ns: int
    extension: str


class DatasetIndex:
    """A compact, explicitly refreshed, single-directory index."""

    def __init__(self, data_dir: Path, mode: str):
        self.data_dir = data_dir.resolve()
        self.mode = mode
        self.entries: tuple[FileEntry, ...] = ()
        self._names: frozenset[str] = frozenset()
        self.refresh()

    @property
    def names(self) -> frozenset[str]:
        return self._names

    def refresh(self) -> None:
        allowed = EXTENSIONS[self.mode]
        entries: list[FileEntry] = []
        with os.scandir(self.data_dir) as iterator:
            for item in iterator:
                if item.name == "label" or Path(item.name).suffix.lower() not in allowed:
                    continue
                try:
                    if not item.is_file(follow_symlinks=True):
                        continue
                    stat = item.stat(follow_symlinks=True)
                    resolved = Path(item.path).resolve(strict=True)
                except (FileNotFoundError, OSError):
                    continue
                entries.append(
                    FileEntry(
                        name=item.name,
                        path=resolved,
                        size=stat.st_size,
                        mtime_ns=stat.st_mtime_ns,
                        extension=Path(item.name).suffix.lower(),
                    )
                )
        entries.sort(key=lambda entry: entry.name.casefold())
        self.entries = tuple(entries)
        self._names = frozenset(entry.name for entry in entries)

    def page(self, page: int, per_page: int) -> tuple[FileEntry, ...]:
        if per_page < 1:
            raise ValueError("per_page must be positive")
        start = max(0, page - 1) * per_page
        return self.entries[start : start + per_page]
