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


def test_row_and_column_inputs_have_no_maximum():
    javascript = (ASSETS / "grid.js").read_text(encoding="utf-8")
    app = (ASSETS.parents[1] / "app.py").read_text(encoding="utf-8")
    assert "data.rows, 1, null" in javascript
    assert "data.cols, 1, null" in javascript
    assert "min(8" not in app


def test_grid_rows_share_the_fixed_viewport_without_scrolling():
    javascript = (ASSETS / "grid.js").read_text(encoding="utf-8")
    css = (ASSETS / "grid.css").read_text(encoding="utf-8")
    assert "gridTemplateRows = `repeat(${data.rows}, minmax(0, 1fr))`" in javascript
    assert ".sample-grid" in css and "overflow: hidden" in css


def test_component_tracks_the_actual_browser_viewport():
    javascript = (ASSETS / "grid.js").read_text(encoding="utf-8")
    component = (ASSETS.parents[1] / "streamlit_demo" / "component.py").read_text(encoding="utf-8")
    assert "visualViewport?.height" in javascript
    assert "root.getBoundingClientRect().top" in javascript
    assert "addEventListener('resize', fitToViewport)" in javascript
    assert 'height="content"' in component


def test_label_manager_supports_long_press_reordering_and_editing():
    javascript = (ASSETS / "label_manager.js").read_text(encoding="utf-8")
    for contract in (
        "setPointerCapture",
        "type: 'reorder'",
        "type: 'select'",
        "type: 'delete'",
        "type: 'update'",
        "root._optimisticOrder",
        "320",
    ):
        assert contract in javascript


def test_image_viewer_supports_adjacent_navigation():
    javascript = (ASSETS / "grid.js").read_text(encoding="utf-8")
    html = (ASSETS / "grid.html").read_text(encoding="utf-8")
    assert "showViewerSample" in javascript
    assert "ArrowLeft" in javascript and "ArrowRight" in javascript
    assert 'data-role="viewer-previous"' in html
    assert 'data-role="viewer-next"' in html
