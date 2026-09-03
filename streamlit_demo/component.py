from __future__ import annotations

from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components


ASSET_DIR = Path(__file__).parent / "assets"

filename_search_component = components.declare_component(
    "filename_search",
    path=ASSET_DIR / "filename_search",
)


def _read(name: str) -> str:
    return (ASSET_DIR / name).read_text(encoding="utf-8")


sample_grid_component = st.components.v2.component(
    "sample_grid",
    html=_read("grid.html"),
    css=_read("grid.css"),
    js=_read("grid.js"),
)

label_manager_component = st.components.v2.component(
    "label_manager",
    html=_read("label_manager.html"),
    css=_read("label_manager.css"),
    js=_read("label_manager.js"),
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
        # The component measures its viewport-aware root instead of reserving a
        # fixed 700 px, so shorter displays do not acquire a page scrollbar.
        height="content",
    )


def render_label_manager(*, data: dict, key: str = "label_manager"):
    return label_manager_component(
        data=data,
        default={},
        on_action_change=lambda: None,
        key=key,
        height="content",
    )


def render_filename_search(*, query: str, results: list[str], key: str = "filename_search"):
    return filename_search_component(
        query=query,
        results=results,
        default={},
        key=key,
    )
