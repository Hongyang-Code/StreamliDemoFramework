from __future__ import annotations

import hashlib
import math
import sys
from pathlib import Path

import streamlit as st

from streamlit_demo.component import render_filename_search, render_label_manager, render_sample_grid
from streamlit_demo.config import AppConfig, parse_args
from streamlit_demo.index import DatasetIndex
from streamlit_demo.media import PreviewManager
from streamlit_demo.storage import CorruptNotesError, LabelStore, StorageError, next_palette_color


MODE_LABELS = {"image": "图片", "video": "视频", "text": "文本"}
DEFAULT_LAYOUTS = {"image": (2, 3), "video": (1, 2), "text": (2, 2)}
GRID_VIEW_KEYS = ("rows", "cols", "page", "show_badges")
GRID_QUERY_KEYS = {
    "rows": "grid_rows",
    "cols": "grid_cols",
    "page": "grid_page",
    "show_badges": "grid_marks",
}


@st.cache_resource(show_spinner=False)
def get_dataset_index(data_dir: str, mode: str) -> DatasetIndex:
    return DatasetIndex(Path(data_dir), mode)


@st.cache_resource(show_spinner=False)
def get_preview_manager(data_dir: str, cache_limit_mb: float) -> PreviewManager:
    return PreviewManager(Path(data_dir), cache_limit_mb)


def state_value(state, key: str, default):
    if state is None:
        return default
    if isinstance(state, dict):
        value = state.get(key, default)
    else:
        value = getattr(state, key, default)
    return default if value is None else value


def remember_grid_view(state) -> None:
    """Copy component-owned view settings into durable session keys.

    Sidebar actions can call ``st.rerun`` before the component is mounted. In
    that run Streamlit may discard the widget state, so layout state must not
    live only inside the component.
    """
    if state is None:
        return
    for key in GRID_VIEW_KEYS:
        value = state_value(state, key, None)
        if value is not None:
            st.session_state[f"grid_view_{key}"] = value


def grid_view_value(key: str, default):
    session_key = f"grid_view_{key}"
    if session_key in st.session_state:
        return st.session_state[session_key]
    query_value = st.query_params.get(GRID_QUERY_KEYS[key])
    if query_value is None:
        return default
    if key == "show_badges":
        return str(query_value).casefold() not in {"0", "false", "off", "no"}
    try:
        return max(1, int(query_value))
    except (TypeError, ValueError):
        return default


def sync_grid_view_query(rows: int, cols: int, page: int, show_badges: bool) -> None:
    values = {
        "grid_rows": str(rows),
        "grid_cols": str(cols),
        "grid_page": str(page),
        "grid_marks": "1" if show_badges else "0",
    }
    for key, value in values.items():
        if st.query_params.get(key) != value:
            st.query_params[key] = value


def render_create_label_form(store: LabelStore) -> None:
    if st.session_state.pop("reset_new_label_color", False):
        st.session_state.pop("new_label_color", None)
    default_color = next_palette_color(store.list_labels().values())
    with st.container(border=True):
        st.caption("新建标签")
        with st.form("create_label_form", clear_on_submit=True, enter_to_submit=True):
            # Streamlit submits the first form button on Enter. This invisible
            # primary submit keeps keyboard behavior independent of the visual
            # Cancel/Create column order below.
            with st.container(key="enter_create_submit"):
                enter_create = st.form_submit_button("回车创建标签")
            new_name = st.text_input("标签名称")
            new_color = st.color_picker("标签颜色", default_color, key="new_label_color")
            cancel_col, create_col = st.columns(2)
            create = create_col.form_submit_button("创建", type="primary", use_container_width=True)
            cancel = cancel_col.form_submit_button("取消", use_container_width=True)
    if cancel:
        st.session_state["show_create_label_form"] = False
        st.session_state["reset_new_label_color"] = True
        st.rerun()
    if create or enter_create:
        try:
            store.create_label(new_name, new_color)
            st.session_state["pending_active_label"] = new_name.strip()
            st.session_state["show_create_label_form"] = False
            st.session_state["reset_new_label_color"] = True
            st.rerun()
        except StorageError as exc:
            st.error(str(exc))


def handle_component_action(state, store: LabelStore, dataset: DatasetIndex) -> None:
    action = state_value(state, "action", None)
    if not action:
        return
    action = dict(action)
    op_id = str(action.get("op_id", ""))
    processed: list[str] = st.session_state.setdefault("processed_operation_ids", [])
    if not op_id or op_id in processed:
        return
    processed.append(op_id)
    del processed[:-200]
    try:
        if action.get("type") == "refresh":
            dataset.refresh()
            query = str(st.session_state.get("search_query", ""))
            st.session_state["search_results"] = list(dataset.search(query))
            st.toast("文件列表已刷新，当前页保持不变", icon="🔄")
        elif action.get("type") == "search":
            query = str(action.get("query", "")).strip()
            st.session_state["search_query"] = query
            st.session_state["search_results"] = list(dataset.search(query))
            st.session_state.pop("search_target", None)
        elif action.get("type") == "search_navigate":
            query = str(action.get("query", "")).strip()
            requested = str(action.get("sample", ""))
            target = requested if requested in dataset.names and query.casefold() in requested.casefold() else ""
            if not target:
                matches = dataset.search(query, limit=1)
                target = matches[0] if matches else ""
            st.session_state["search_query"] = query
            st.session_state["search_results"] = list(dataset.search(query))
            if target:
                position = dataset.position(target)
                rows = max(1, int(st.session_state.get("grid_view_rows", 1)))
                cols = max(1, int(st.session_state.get("grid_view_cols", 1)))
                if position is not None:
                    st.session_state["grid_view_page"] = position // (rows * cols) + 1
                    st.session_state["search_target"] = target
        elif action.get("type") == "membership":
            store.set_membership(
                str(action.get("label", "")),
                str(action.get("sample", "")),
                bool(action.get("assigned")),
            )
        elif action.get("type") == "membership_batch":
            operations = action.get("operations", [])
            if not isinstance(operations, list):
                raise StorageError("批量标签操作格式错误")
            store.set_memberships(operations)
        elif action.get("type") == "note":
            changed = store.save_note(str(action.get("sample", "")), str(action.get("text", "")))
            st.toast("备注已保存" if changed else "备注没有变化", icon="📝")
        else:
            raise StorageError("未知的页面操作")
    except StorageError as exc:
        st.session_state["operation_error"] = str(exc)


def handle_label_manager_action(state, store: LabelStore) -> None:
    action = state_value(state, "action", None)
    if not action:
        return
    action = dict(action)
    op_id = str(action.get("op_id", ""))
    processed: list[str] = st.session_state.setdefault("processed_label_operation_ids", [])
    if not op_id or op_id in processed:
        return
    processed.append(op_id)
    del processed[:-100]
    try:
        action_type = action.get("type")
        name = str(action.get("name", ""))
        if action_type == "select":
            if name not in store.list_labels():
                raise StorageError("标签不存在")
            st.session_state["active_label"] = name
        elif action_type == "delete":
            store.delete_label(name)
            if st.session_state.get("active_label") == name:
                st.session_state["active_label"] = None
        elif action_type == "reorder":
            order = action.get("order", [])
            if not isinstance(order, list):
                raise StorageError("标签顺序格式错误")
            store.set_label_order(order)
        elif action_type == "update":
            updated_name = store.update_label(
                name,
                str(action.get("new_name", "")),
                str(action.get("color", "")),
                str(action.get("style", "")),
            )
            if st.session_state.get("active_label") == name:
                st.session_state["active_label"] = updated_name
            st.toast("标签设置已保存", icon="✅")
        else:
            raise StorageError("未知的标签操作")
    except StorageError as exc:
        st.session_state["label_manager_error"] = str(exc)


def render_sidebar(store: LabelStore) -> dict[str, str] | None:
    with st.sidebar:
        st.header("标签管理")
        handle_label_manager_action(st.session_state.get("label_manager"), store)
        labels = store.list_labels()
        label_styles = store.get_label_styles()
        if "pending_active_label" in st.session_state:
            pending = st.session_state.pop("pending_active_label")
            st.session_state["active_label"] = pending if pending in labels else None
        active = st.session_state.get("active_label")
        if active not in labels:
            active = None
            st.session_state["active_label"] = None

        if active:
            st.caption(f"当前标签：{active}")
            if st.button("取消当前标签", use_container_width=True):
                st.session_state["active_label"] = None
                st.rerun()
        else:
            st.caption("当前标签：未选择")

        if st.button("＋ 新建标签", use_container_width=True):
            st.session_state["show_create_label_form"] = True
        if st.session_state.get("show_create_label_form", False):
            render_create_label_form(store)

        manager_error = st.session_state.pop("label_manager_error", None)
        if manager_error:
            st.error(manager_error)
        render_label_manager(
            data={
                "labels": [
                    {
                        "name": name,
                        "color": color,
                        "style": label_styles.get(name, "badge"),
                        "token": hashlib.sha1(name.encode("utf-8")).hexdigest()[:10],
                    }
                    for name, color in labels.items()
                ],
                "active_label": active,
            }
        )

        with st.container(key="sidebar_guide"):
            st.page_link(
                "pages/操作指南.py",
                label="操作指南",
                icon=":material/info:",
                help="选择标签后左键样本进行标记；右键可添加单样本备注；A / D 翻页。点击打开完整操作指南。",
                use_container_width=True,
            )

    active = st.session_state.get("active_label")
    if active and active in labels:
        return {"name": active, "color": labels[active], "style": label_styles.get(active, "badge")}
    return None


def main(config: AppConfig) -> None:
    st.set_page_config(page_title=config.title, page_icon="🧭", layout="wide")
    st.markdown(
        """
        <style>
        .block-container { max-width: 100%; padding-top: 2.35rem; padding-bottom: .5rem; }
        [data-testid="stSidebar"] { border-right: 1px solid rgba(148,163,184,.25); }
        [data-testid="stSidebarNav"] { display:none; }
        [data-testid="stSidebarUserContent"] > div > [data-testid="stVerticalBlock"] { min-height:calc(100dvh - 134px); }
        [data-testid="stSidebar"] [data-testid="stLayoutWrapper"]:has(> .st-key-sidebar_guide) { margin-top:auto!important; }
        [data-testid="stSidebar"] .st-key-sidebar_guide { padding-top:.25rem; }
        [data-testid="stSidebar"] .st-key-sidebar_guide a { min-height:34px; border:0; color:#64748b; justify-content:flex-start; padding:.3rem .35rem; }
        [data-testid="stSidebar"] .st-key-sidebar_guide a:hover { color:var(--text-color); background:rgba(148,163,184,.10); }
        .st-key-enter_create_submit { display:none!important; }
        .st-key-filename_search_component { position:fixed!important; left:-1000px; top:-1000px; z-index:1001;
          width:190px; height:31px; margin:0!important; padding:0!important; }
        .st-key-filename_search_component iframe { display:block; width:100%!important; border:0; }
        .status-float { position: relative; z-index: 30; width: fit-content; min-width: 210px; margin: 1.35rem 0 4px auto;
          border: 1px solid rgba(148,163,184,.35); border-radius: 999px; background: rgba(255,255,255,.92);
          box-shadow: 0 6px 22px rgba(15,23,42,.08); backdrop-filter: blur(10px); cursor: default; }
        .status-summary { display: flex; align-items: center; gap: 10px; height: 38px; padding: 0 15px; font-size: 13px; font-weight: 650; }
        .status-summary i { width: 7px; height: 7px; border-radius: 50%; background: #2563EB; box-shadow: 0 0 0 4px rgba(37,99,235,.11); }
        </style>
        """,
        unsafe_allow_html=True,
    )

    dataset = get_dataset_index(str(config.data_dir), config.mode)
    if st.session_state.pop("refresh_dataset", False):
        dataset.refresh()
    store = LabelStore(config.label_dir, dataset.names)
    component_state = st.session_state.get("sample_grid")
    remember_grid_view(component_state)
    handle_component_action(component_state, store, dataset)

    active_label = render_sidebar(store)
    operation_error = st.session_state.pop("operation_error", None)
    if operation_error:
        st.error(f"上一次操作失败：{operation_error}")

    header_main, header_status = st.columns([6, 1.35], vertical_alignment="top")
    with header_main:
        st.title(config.title)
        st.caption(str(config.data_dir))
    with header_status:
        st.markdown(
            f"""
            <div class="status-float" aria-label="数据概况">
              <div class="status-summary"><i></i><span>{MODE_LABELS[config.mode]}模式</span><span>·</span><span>{len(dataset.entries):,} 个样本</span></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    if config.mode == "video":
        ok, message = PreviewManager.check_video_tools()
        if not ok:
            st.error(message)

    default_rows, default_cols = DEFAULT_LAYOUTS[config.mode]
    rows = max(1, int(grid_view_value("rows", default_rows)))
    cols = max(1, int(grid_view_value("cols", default_cols)))
    per_page = rows * cols
    total_pages = math.ceil(len(dataset.entries) / per_page) if dataset.entries else 0
    requested_page = int(grid_view_value("page", 1))
    page = 1 if total_pages == 0 else max(1, min(total_pages, requested_page))
    show_badges = bool(grid_view_value("show_badges", True))
    st.session_state["grid_view_rows"] = rows
    st.session_state["grid_view_cols"] = cols
    st.session_state["grid_view_page"] = page
    st.session_state["grid_view_show_badges"] = show_badges
    sync_grid_view_query(rows, cols, page, show_badges)
    entries = dataset.page(page, per_page)

    manager = get_preview_manager(str(config.data_dir), config.preview_cache_mb)
    with st.spinner("正在准备当前页预览……", show_time=True):
        previews = manager.prepare_page(
            entries,
            config.mode,
            config.preview_limit_mb,
            config.page_payload_limit_mb,
        )
    filenames = [entry.name for entry in entries]
    labels_by_sample, noted = store.page_state(filenames)
    label_styles = store.get_label_styles()
    try:
        notes = store.get_notes(filenames)
    except CorruptNotesError as exc:
        notes = {name: {"current": "", "updated_at": "", "history": []} for name in filenames}
        st.error(str(exc))

    samples = []
    page_start = (page - 1) * per_page
    for page_offset, (entry, preview) in enumerate(zip(entries, previews)):
        samples.append(
            {
                "name": entry.name,
                "global_index": page_start + page_offset,
                "kind": preview.kind,
                "source": preview.source,
                "notice": preview.notice,
                "error": preview.error,
                "labels": [
                    {**label, "style": label_styles.get(label["name"], "badge")}
                    for label in labels_by_sample.get(entry.name, [])
                ],
                "has_note": entry.name in noted,
                "note": notes.get(entry.name, {}),
            }
        )

    with st.container(key="filename_search_component"):
        search_state = render_filename_search(
            query=st.session_state.get("search_query", ""),
            results=st.session_state.get("search_results", []),
        )
    search_action = state_value(search_state, "type", None)
    search_op_id = state_value(search_state, "op_id", None)
    if search_action and search_op_id not in st.session_state.setdefault("processed_operation_ids", []):
        handle_component_action({"action": search_state}, store, dataset)
        st.rerun()

    render_sample_grid(
        rows=rows,
        data={
            "samples": samples,
            "rows": rows,
            "cols": cols,
            "page": page,
            "total_pages": total_pages,
            "total_count": len(dataset.entries),
            "show_badges": show_badges,
            "active_label": active_label,
            "label_order": list(store.list_labels()),
            "search_query": st.session_state.get("search_query", ""),
            "search_results": st.session_state.get("search_results", []),
            "search_target": st.session_state.get("search_target", ""),
        },
    )


if __name__ == "__main__":
    main(parse_args(sys.argv[1:]))
