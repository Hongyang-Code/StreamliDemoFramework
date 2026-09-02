from pathlib import Path


ASSETS = Path(__file__).parents[1] / "streamlit_demo" / "assets"


def test_component_contains_required_interactions():
    javascript = (ASSETS / "grid.js").read_text(encoding="utf-8")
    for contract in (
        "contextmenu",
        "setTriggerValue('action'",
        "setStateValue('cols'",
        "show_badges",
        "assigned",
        "openViewer",
        "type: 'refresh'",
        "membership_batch",
        "orderedLabels",
        "frame-rings",
    ):
        assert contract in javascript


def test_component_uses_safe_text_rendering():
    javascript = (ASSETS / "grid.js").read_text(encoding="utf-8")
    assert ".textContent =" in javascript
    assert ".innerHTML" not in javascript


def test_column_input_has_no_maximum():
    javascript = (ASSETS / "grid.js").read_text(encoding="utf-8")
    app = (ASSETS.parents[1] / "app.py").read_text(encoding="utf-8")
    assert "data.cols, 1, null" in javascript
    assert "min(8" not in app


def test_component_has_no_pagination_controls():
    javascript = (ASSETS / "grid.js").read_text(encoding="utf-8")
    assert "上一页" not in javascript
    assert "下一页" not in javascript
    assert "页码" not in javascript
    assert "setStateValue('page'" not in javascript
