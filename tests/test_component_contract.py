from pathlib import Path


ASSETS = Path(__file__).parents[1] / "streamlit_demo" / "assets"


def test_component_contains_required_interactions():
    javascript = (ASSETS / "grid.js").read_text(encoding="utf-8")
    for contract in (
        "contextmenu",
        "setTriggerValue('action'",
        "setStateValue('page'",
        "setStateValue('rows'",
        "setStateValue('cols'",
        "show_badges",
        "assigned",
    ):
        assert contract in javascript


def test_component_uses_safe_text_rendering():
    javascript = (ASSETS / "grid.js").read_text(encoding="utf-8")
    assert ".textContent =" in javascript
    assert ".innerHTML" not in javascript
