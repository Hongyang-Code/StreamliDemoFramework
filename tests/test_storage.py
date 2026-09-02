import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from streamlit_demo.storage import CorruptNotesError, LabelStore, StorageError, stable_color


def make_store(tmp_path: Path) -> LabelStore:
    label = tmp_path / "label"
    label.mkdir()
    return LabelStore(label, {"a.jpg", "b.jpg", "c.jpg"})


def test_missing_color_is_repaired_without_losing_first_sample(tmp_path: Path):
    label = tmp_path / "label"
    label.mkdir()
    (label / "质量问题.txt").write_text("a.jpg\nb.jpg\n", encoding="utf-8")
    store = LabelStore(label, {"a.jpg", "b.jpg"})
    lines = (label / "质量问题.txt").read_text(encoding="utf-8").splitlines()
    assert lines == [stable_color("质量问题"), "a.jpg", "b.jpg"]
    assert store.page_state(["a.jpg"])[0]["a.jpg"][0]["name"] == "质量问题"


def test_empty_label_and_lowercase_color_are_normalized(tmp_path: Path):
    label = tmp_path / "label"
    label.mkdir()
    (label / "empty.txt").write_text("", encoding="utf-8")
    (label / "color.txt").write_text("#aabbcc\na.jpg\n\na.jpg\n", encoding="utf-8")
    LabelStore(label, {"a.jpg"})
    assert (label / "empty.txt").read_text().startswith("#")
    assert (label / "color.txt").read_text().splitlines() == ["#AABBCC", "a.jpg"]


def test_label_crud_and_idempotent_membership(tmp_path: Path):
    store = make_store(tmp_path)
    store.create_label("good", "#123456")
    store.set_membership("good", "a.jpg", True)
    store.set_membership("good", "a.jpg", True)
    assert (tmp_path / "label" / "good.txt").read_text().splitlines() == ["#123456", "a.jpg"]
    store.set_label_color("good", "#ABCDEF")
    store.rename_label("good", "better")
    assert store.list_labels() == {"better": "#ABCDEF"}
    store.set_membership("better", "a.jpg", False)
    assert (tmp_path / "label" / "better.txt").read_text().splitlines() == ["#ABCDEF"]
    store.delete_label("better")
    assert store.list_labels() == {}


def test_invalid_names_and_unknown_samples_are_rejected(tmp_path: Path):
    store = make_store(tmp_path)
    for name in ("", ".", "..", "../escape", "x/y", "sample_notes"):
        with pytest.raises(StorageError):
            store.create_label(name, "#123456")
    store.create_label("valid", "#123456")
    with pytest.raises(StorageError):
        store.set_membership("valid", "../a.jpg", True)


def test_notes_keep_current_and_full_history(tmp_path: Path):
    store = make_store(tmp_path)
    assert store.save_note("a.jpg", "第一次") is True
    assert store.save_note("a.jpg", "第一次") is False
    assert store.save_note("a.jpg", "第二次") is True
    assert store.save_note("a.jpg", "") is True
    note = store.get_notes(["a.jpg"])["a.jpg"]
    assert note["current"] == ""
    assert [item["action"] for item in note["history"]] == ["save", "save", "clear"]
    parsed = json.loads((tmp_path / "label" / "sample_notes.json").read_text())
    assert parsed["version"] == 1


def test_corrupt_notes_are_never_overwritten(tmp_path: Path):
    store = make_store(tmp_path)
    notes_path = tmp_path / "label" / "sample_notes.json"
    notes_path.write_text("{broken", encoding="utf-8")
    original = notes_path.read_bytes()
    with pytest.raises(CorruptNotesError):
        store.save_note("a.jpg", "do not overwrite")
    assert notes_path.read_bytes() == original


def test_concurrent_writes_to_different_samples_are_preserved(tmp_path: Path):
    store = make_store(tmp_path)
    store.create_label("tag", "#334455")
    with ThreadPoolExecutor(max_workers=3) as executor:
        list(executor.map(lambda name: store.set_membership("tag", name, True), ["a.jpg", "b.jpg", "c.jpg"]))
    assert set((tmp_path / "label" / "tag.txt").read_text().splitlines()[1:]) == {"a.jpg", "b.jpg", "c.jpg"}


def test_batched_memberships_keep_latest_target_state(tmp_path: Path):
    store = make_store(tmp_path)
    store.create_label("tag", "#334455")
    store.set_memberships(
        [
            {"label": "tag", "sample": "a.jpg", "assigned": True},
            {"label": "tag", "sample": "b.jpg", "assigned": True},
            {"label": "tag", "sample": "a.jpg", "assigned": False},
            {"label": "tag", "sample": "c.jpg", "assigned": True},
        ]
    )
    assert (tmp_path / "label" / "tag.txt").read_text().splitlines() == ["#334455", "b.jpg", "c.jpg"]


def test_per_label_style_survives_rename_and_is_removed_on_delete(tmp_path: Path):
    store = make_store(tmp_path)
    store.create_label("tag", "#334455")
    assert store.get_label_styles() == {"tag": "badge"}
    store.set_label_style("tag", "border")
    assert store.get_label_styles() == {"tag": "border"}
    store.rename_label("tag", "renamed")
    assert store.get_label_styles() == {"renamed": "border"}
    store.delete_label("renamed")
    assert store.get_label_styles() == {}
