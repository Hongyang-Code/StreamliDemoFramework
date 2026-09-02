from __future__ import annotations

from pathlib import Path

import streamlit as st


ASSET_DIR = Path(__file__).parent / "assets"


def _read(name: str) -> str:
    return (ASSET_DIR / name).read_text(encoding="utf-8")


sample_grid_component = st.components.v2.component(
    "sample_grid",
    html=_read("grid.html"),
    css=_read("grid.css"),
    js=_read("grid.js"),
)


def render_sample_grid(*, data: dict, rows: int, key: str = "sample_grid"):
    row_height = max(190, min(370, 700 / max(1, rows)))
    component_height = max(280, int(rows * row_height + max(0, rows - 1) * 10 + 62))
    return sample_grid_component(
        data=data,
        default={"cols": data["cols"], "show_badges": True},
        on_cols_change=lambda: None,
        on_show_badges_change=lambda: None,
        on_action_change=lambda: None,
        key=key,
        height=component_height,
    )
