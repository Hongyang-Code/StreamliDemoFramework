from __future__ import annotations

import colorsys
import fcntl
import hashlib
import json
import os
import re
import sqlite3
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
RESERVED_LABELS = {"sample_notes", "label_settings", ".label_index", ".store"}


class StorageError(RuntimeError):
    pass


class CorruptNotesError(StorageError):
    pass


def stable_color(name: str) -> str:
    digest = hashlib.sha256(name.encode("utf-8")).digest()
    hue = int.from_bytes(digest[:2], "big") / 65535
    saturation = 0.62 + digest[2] / 255 * 0.18
    lightness = 0.48 + digest[3] / 255 * 0.12
    red, green, blue = colorsys.hls_to_rgb(hue, lightness, saturation)
    return f"#{round(red * 255):02X}{round(green * 255):02X}{round(blue * 255):02X}"


def validate_label_name(name: str) -> str:
    candidate = name.strip()
    if (
        not candidate
        or candidate in {".", ".."}
        or candidate.casefold() in RESERVED_LABELS
        or "/" in candidate
        or "\\" in candidate
        or CONTROL_RE.search(candidate)
    ):
        raise StorageError("标签名为空、非法或属于保留名称")
    return candidate


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    previous_mode = None
    try:
        previous_mode = path.stat().st_mode & 0o777
    except FileNotFoundError:
        pass
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp_path, previous_mode or 0o644)
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


class LabelStore:
    def __init__(self, label_dir: Path, valid_samples: Iterable[str]):
        self.label_dir = label_dir.resolve()
        self.label_dir.mkdir(parents=True, exist_ok=True)
        self.notes_path = self.label_dir / "sample_notes.json"
        self.settings_path = self.label_dir / "label_settings.json"
        self.index_path = self.label_dir / ".label_index.sqlite3"
        self.lock_path = self.label_dir / ".store.lock"
        self.valid_samples = frozenset(valid_samples)
        self.notes_error = ""
        self.refresh_index()

    @contextmanager
    def _lock(self):
        with self.lock_path.open("a+", encoding="utf-8") as stream:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    def _label_paths(self) -> list[Path]:
        return sorted(
            (path for path in self.label_dir.glob("*.txt") if path.is_file()),
            key=lambda path: path.name.casefold(),
        )

    def _read_label(self, path: Path, repair: bool = True) -> tuple[str, set[str]]:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError as exc:
            raise StorageError(f"标签文件不是 UTF-8: {path.name}") from exc
        nonempty = [line.strip() for line in lines if line.strip()]
        repaired = False
        if nonempty and COLOR_RE.fullmatch(nonempty[0]):
            color = nonempty[0].upper()
            samples = set(nonempty[1:])
            repaired = color != nonempty[0] or nonempty != lines
        else:
            color = stable_color(path.stem)
            samples = set(nonempty)
            repaired = True
        if repair and repaired:
            self._write_label(path, color, samples)
        return color, samples

    @staticmethod
    def _write_label(path: Path, color: str, samples: Iterable[str]) -> None:
        normalized = color.upper()
        if not COLOR_RE.fullmatch(normalized):
            raise StorageError("颜色必须为 #RRGGBB")
        content = normalized + "\n"
        values = sorted(set(samples), key=str.casefold)
        if values:
            content += "\n".join(values) + "\n"
        _atomic_write(path, content)

    def _source_signature(self) -> str:
        digest = hashlib.sha256()
        for path in self._label_paths():
            digest.update(path.name.encode("utf-8"))
            digest.update(path.read_bytes())
        if self.notes_path.exists():
            digest.update(self.notes_path.name.encode("utf-8"))
            digest.update(self.notes_path.read_bytes())
        return digest.hexdigest()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.index_path, timeout=30)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS labels (
                name TEXT PRIMARY KEY,
                color TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS memberships (
                label_name TEXT NOT NULL,
                sample TEXT NOT NULL,
                PRIMARY KEY (label_name, sample)
            );
            CREATE INDEX IF NOT EXISTS memberships_sample_idx ON memberships(sample);
            CREATE TABLE IF NOT EXISTS noted_samples (sample TEXT PRIMARY KEY);
            """
        )
        return connection

    def refresh_index(self, force: bool = False) -> None:
        with self._lock():
            label_rows: list[tuple[str, str]] = []
            membership_rows: list[tuple[str, str]] = []
            for path in self._label_paths():
                color, samples = self._read_label(path, repair=True)
                label_rows.append((path.stem, color))
                membership_rows.extend((path.stem, sample) for sample in samples)
            try:
                notes = self._load_notes(create=False)
                self.notes_error = ""
            except CorruptNotesError as exc:
                notes = self._empty_notes()
                self.notes_error = str(exc)
            signature = self._source_signature()
            with self._connect() as connection:
                old = connection.execute("SELECT value FROM meta WHERE key='signature'").fetchone()
                if not force and old and old[0] == signature:
                    return
                connection.execute("DELETE FROM labels")
                connection.execute("DELETE FROM memberships")
                connection.execute("DELETE FROM noted_samples")
                connection.executemany("INSERT INTO labels(name, color) VALUES (?, ?)", label_rows)
                connection.executemany(
                    "INSERT OR IGNORE INTO memberships(label_name, sample) VALUES (?, ?)", membership_rows
                )
                connection.executemany(
                    "INSERT INTO noted_samples(sample) VALUES (?)",
                    ((name,) for name, value in notes.get("samples", {}).items() if value.get("current")),
                )
                connection.execute(
                    "INSERT OR REPLACE INTO meta(key, value) VALUES ('signature', ?)", (signature,)
                )

    def list_labels(self) -> dict[str, str]:
        self.refresh_index()
        with self._connect() as connection:
            return dict(connection.execute("SELECT name, color FROM labels ORDER BY name COLLATE NOCASE"))

    @staticmethod
    def _empty_label_settings() -> dict:
        return {"version": 1, "labels": {}}

    def _load_label_settings(self) -> dict:
        if not self.settings_path.exists():
            return self._empty_label_settings()
        try:
            value = json.loads(self.settings_path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise StorageError("label_settings.json 已损坏，请修复或备份后再修改标签设置") from exc
        if value.get("version") != 1 or not isinstance(value.get("labels"), dict):
            raise StorageError("label_settings.json 结构不受支持或缺少 version/labels")
        return value

    def get_label_styles(self) -> dict[str, str]:
        with self._lock():
            settings = self._load_label_settings()
        labels = self.list_labels()
        return {
            name: settings["labels"].get(name, {}).get("style", "badge")
            if settings["labels"].get(name, {}).get("style", "badge") in {"badge", "border"}
            else "badge"
            for name in labels
        }

    def set_label_style(self, name: str, style: str) -> None:
        name = validate_label_name(name)
        if style not in {"badge", "border"}:
            raise StorageError("标签样式只能是角标或外框")
        with self._lock():
            if not (self.label_dir / f"{name}.txt").exists():
                raise StorageError("标签不存在")
            settings = self._load_label_settings()
            settings["labels"].setdefault(name, {})["style"] = style
            _atomic_write(self.settings_path, json.dumps(settings, ensure_ascii=False, indent=2) + "\n")

    def page_state(self, samples: Iterable[str]) -> tuple[dict[str, list[dict[str, str]]], set[str]]:
        names = list(samples)
        if not names:
            return {}, set()
        self.refresh_index()
        placeholders = ",".join("?" for _ in names)
        labels_by_sample = {name: [] for name in names}
        with self._connect() as connection:
            rows = connection.execute(
                f"""SELECT m.sample, m.label_name, l.color
                    FROM memberships m JOIN labels l ON l.name=m.label_name
                    WHERE m.sample IN ({placeholders}) ORDER BY m.label_name COLLATE NOCASE""",
                names,
            )
            for sample, label, color in rows:
                labels_by_sample[sample].append({"name": label, "color": color})
            noted = {
                row[0]
                for row in connection.execute(
                    f"SELECT sample FROM noted_samples WHERE sample IN ({placeholders})", names
                )
            }
        return labels_by_sample, noted

    def create_label(self, name: str, color: str) -> None:
        name = validate_label_name(name)
        with self._lock():
            path = self.label_dir / f"{name}.txt"
            if path.exists():
                raise StorageError("标签已存在")
            self._write_label(path, color, ())
        self.refresh_index(force=True)

    def rename_label(self, old_name: str, new_name: str) -> None:
        old_name = validate_label_name(old_name)
        new_name = validate_label_name(new_name)
        with self._lock():
            old_path = self.label_dir / f"{old_name}.txt"
            new_path = self.label_dir / f"{new_name}.txt"
            if not old_path.exists():
                raise StorageError("原标签不存在")
            if new_path.exists():
                raise StorageError("新标签名已存在")
            settings = self._load_label_settings()
            os.replace(old_path, new_path)
            if old_name in settings["labels"]:
                settings["labels"][new_name] = settings["labels"].pop(old_name)
                _atomic_write(self.settings_path, json.dumps(settings, ensure_ascii=False, indent=2) + "\n")
        self.refresh_index(force=True)

    def delete_label(self, name: str) -> None:
        name = validate_label_name(name)
        with self._lock():
            path = self.label_dir / f"{name}.txt"
            if not path.exists():
                raise StorageError("标签不存在")
            settings = self._load_label_settings()
            path.unlink()
            if settings["labels"].pop(name, None) is not None:
                _atomic_write(self.settings_path, json.dumps(settings, ensure_ascii=False, indent=2) + "\n")
        self.refresh_index(force=True)

    def set_label_color(self, name: str, color: str) -> None:
        name = validate_label_name(name)
        with self._lock():
            path = self.label_dir / f"{name}.txt"
            if not path.exists():
                raise StorageError("标签不存在")
            _, samples = self._read_label(path, repair=False)
            self._write_label(path, color, samples)
        self.refresh_index(force=True)

    def set_membership(self, label_name: str, sample: str, assigned: bool) -> None:
        label_name = validate_label_name(label_name)
        if sample not in self.valid_samples:
            raise StorageError("样本不在当前一级目录索引中")
        with self._lock():
            path = self.label_dir / f"{label_name}.txt"
            if not path.exists():
                raise StorageError("标签不存在")
            color, samples = self._read_label(path, repair=False)
            if assigned:
                samples.add(sample)
            else:
                samples.discard(sample)
            self._write_label(path, color, samples)
        self.refresh_index(force=True)

    def set_memberships(self, operations: Iterable[dict]) -> None:
        normalized: list[tuple[str, str, bool]] = []
        for operation in operations:
            if not isinstance(operation, dict):
                raise StorageError("批量标签操作格式错误")
            label_name = validate_label_name(str(operation.get("label", "")))
            sample = str(operation.get("sample", ""))
            if sample not in self.valid_samples:
                raise StorageError("样本不在当前一级目录索引中")
            normalized.append((label_name, sample, bool(operation.get("assigned"))))
        if not normalized:
            return
        with self._lock():
            grouped: dict[str, list[tuple[str, bool]]] = {}
            for label_name, sample, assigned in normalized:
                grouped.setdefault(label_name, []).append((sample, assigned))
            for label_name, changes in grouped.items():
                path = self.label_dir / f"{label_name}.txt"
                if not path.exists():
                    raise StorageError("标签不存在")
                color, samples = self._read_label(path, repair=False)
                for sample, assigned in changes:
                    if assigned:
                        samples.add(sample)
                    else:
                        samples.discard(sample)
                self._write_label(path, color, samples)
        self.refresh_index(force=True)

    def _empty_notes(self) -> dict:
        return {"version": 1, "samples": {}}

    def _load_notes(self, create: bool = True) -> dict:
        if not self.notes_path.exists():
            if create:
                value = self._empty_notes()
                _atomic_write(self.notes_path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")
                return value
            return self._empty_notes()
        try:
            value = json.loads(self.notes_path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CorruptNotesError(
                f"{self.notes_path} 已损坏；为防止覆盖，已停止备注写入，请先修复或备份该文件。"
            ) from exc
        if value.get("version") != 1 or not isinstance(value.get("samples"), dict):
            raise CorruptNotesError("sample_notes.json 结构不受支持或缺少 version/samples")
        return value

    def get_notes(self, samples: Iterable[str]) -> dict[str, dict]:
        with self._lock():
            notes = self._load_notes(create=True)
        return {name: notes["samples"].get(name, {"current": "", "updated_at": "", "history": []}) for name in samples}

    def save_note(self, sample: str, text: str) -> bool:
        if sample not in self.valid_samples:
            raise StorageError("样本不在当前一级目录索引中")
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        with self._lock():
            notes = self._load_notes(create=True)
            record = notes["samples"].setdefault(
                sample, {"current": "", "updated_at": "", "history": []}
            )
            if record.get("current", "") == normalized:
                return False
            timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            action = "save" if normalized else "clear"
            record["current"] = normalized
            record["updated_at"] = timestamp
            record.setdefault("history", []).append(
                {"text": normalized, "updated_at": timestamp, "action": action}
            )
            _atomic_write(self.notes_path, json.dumps(notes, ensure_ascii=False, indent=2) + "\n")
        self.refresh_index(force=True)
        return True
