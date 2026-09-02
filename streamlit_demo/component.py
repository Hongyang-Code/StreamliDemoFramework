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
    return sample_grid_component(
        data=data,
        default={"rows": rows, "cols": data["cols"], "page": data["page"], "show_badges": True},
        on_rows_change=lambda: None,
        on_cols_change=lambda: None,
        on_page_change=lambda: None,
        on_show_badges_change=lambda: None,
        on_action_change=lambda: None,
        key=key,
        height=780,
    )
