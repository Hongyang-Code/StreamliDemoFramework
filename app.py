from __future__ import annotations

import math
import sys
from pathlib import Path

import streamlit as st

from streamlit_demo.component import render_sample_grid
from streamlit_demo.config import AppConfig, parse_args
from streamlit_demo.index import DatasetIndex
from streamlit_demo.media import PreviewManager
from streamlit_demo.storage import CorruptNotesError, LabelStore, StorageError, stable_color


MODE_LABELS = {"image": "图片", "video": "视频", "text": "文本"}
DEFAULT_LAYOUTS = {"image": (2, 3), "video": (1, 2), "text": (2, 2)}


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


def handle_component_action(state, store: LabelStore) -> None:
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
        if action.get("type") == "membership":
            store.set_membership(
                str(action.get("label", "")),
                str(action.get("sample", "")),
                bool(action.get("assigned")),
            )
            st.toast("标签已保存", icon="✅")
        elif action.get("type") == "note":
            changed = store.save_note(str(action.get("sample", "")), str(action.get("text", "")))
            st.toast("备注已保存" if changed else "备注没有变化", icon="📝")
        else:
            raise StorageError("未知的页面操作")
    except StorageError as exc:
        st.session_state["operation_error"] = str(exc)
    st.rerun()


def render_sidebar(store: LabelStore) -> dict[str, str] | None:
    with st.sidebar:
        st.header("标签管理")
        labels = store.list_labels()
        names = list(labels)
        if "pending_active_label" in st.session_state:
            pending = st.session_state.pop("pending_active_label")
            st.session_state["active_label"] = pending if pending in labels else None
            st.session_state["label_radio"] = pending if pending in labels else "（不选择标签）"
        current = st.session_state.get("active_label")
        if current not in labels:
            current = None
            st.session_state["active_label"] = None
            if st.session_state.get("label_radio") not in (None, "（不选择标签）"):
                st.session_state["label_radio"] = "（不选择标签）"

        choices = ["（不选择标签）", *names]
        current_index = names.index(current) + 1 if current in names else 0
        selected = st.radio("当前标签", choices, index=current_index, key="label_radio")
        st.session_state["active_label"] = None if selected == choices[0] else selected

        with st.expander("新建标签", expanded=not labels):
            with st.form("create_label_form", clear_on_submit=True):
                new_name = st.text_input("标签名称")
                new_color = st.color_picker("标签颜色", stable_color(new_name or "新标签"))
                if st.form_submit_button("创建", type="primary", use_container_width=True):
                    try:
                        store.create_label(new_name, new_color)
                        st.session_state["active_label"] = new_name.strip()
                        st.session_state["pending_active_label"] = new_name.strip()
                        st.rerun()
                    except StorageError as exc:
                        st.error(str(exc))

        active = st.session_state.get("active_label")
        if active and active in labels:
            st.divider()
            st.caption(f"编辑标签：{active}")
            selected_color = st.color_picker("颜色", labels[active], key=f"color_{active}")
            if st.button("保存颜色", use_container_width=True):
                try:
                    store.set_label_color(active, selected_color)
                    st.rerun()
                except StorageError as exc:
                    st.error(str(exc))
            rename_value = st.text_input("新名称", value=active, key=f"rename_{active}")
            if st.button("重命名", use_container_width=True, disabled=rename_value.strip() == active):
                try:
                    store.rename_label(active, rename_value)
                    st.session_state["active_label"] = rename_value.strip()
                    st.session_state["pending_active_label"] = rename_value.strip()
                    st.rerun()
                except StorageError as exc:
                    st.error(str(exc))
            confirm_delete = st.checkbox("确认删除此标签", key=f"delete_confirm_{active}")
            if st.button("删除标签", type="secondary", use_container_width=True, disabled=not confirm_delete):
                try:
                    store.delete_label(active)
                    st.session_state["active_label"] = None
                    st.session_state["pending_active_label"] = None
                    st.rerun()
                except StorageError as exc:
                    st.error(str(exc))

        st.divider()
        st.caption("操作提示")
        st.markdown("选择标签后左键样本即可标记；右键样本可编辑单样本备注；使用 **A / D** 翻页。")

    active = st.session_state.get("active_label")
    if active and active in labels:
        return {"name": active, "color": labels[active]}
    return None


def main(config: AppConfig) -> None:
    st.set_page_config(page_title="实验结果展示与标注", page_icon="🧭", layout="wide")
    st.markdown(
        """
        <style>
        .block-container { max-width: 100%; padding-top: 1.2rem; padding-bottom: 1rem; }
        [data-testid="stSidebar"] { border-right: 1px solid rgba(148,163,184,.25); }
        [data-testid="stMetric"] { background: rgba(148,163,184,.08); border-radius: 12px; padding: 10px 14px; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    dataset = get_dataset_index(str(config.data_dir), config.mode)
    if st.session_state.pop("refresh_dataset", False):
        dataset.refresh()
    store = LabelStore(config.label_dir, dataset.names)
    component_state = st.session_state.get("sample_grid")
    handle_component_action(component_state, store)

    active_label = render_sidebar(store)
    operation_error = st.session_state.pop("operation_error", None)
    if operation_error:
        st.error(f"上一次操作失败：{operation_error}")

    title_col, refresh_col = st.columns([8, 1])
    with title_col:
        st.title("实验结果展示与标注")
        st.caption(str(config.data_dir))
    with refresh_col:
        st.write("")
        st.write("")
        if st.button("刷新文件", use_container_width=True):
            dataset.refresh()
            st.rerun()

    info_a, info_b, info_c, info_d = st.columns(4)
    info_a.metric("当前模态", MODE_LABELS[config.mode])
    info_b.metric("样本数量", f"{len(dataset.entries):,}")
    info_c.metric("单样本上限", f"{config.preview_limit_mb:g} MB")
    info_d.metric("单页上限", f"{config.page_payload_limit_mb:g} MB")

    if config.mode == "video":
        ok, message = PreviewManager.check_video_tools()
        if not ok:
            st.error(message)

    default_rows, default_cols = DEFAULT_LAYOUTS[config.mode]
    rows = max(1, min(8, int(state_value(component_state, "rows", default_rows))))
    cols = max(1, min(8, int(state_value(component_state, "cols", default_cols))))
    per_page = rows * cols
    total_pages = math.ceil(len(dataset.entries) / per_page) if dataset.entries else 0
    requested_page = int(state_value(component_state, "page", 1))
    page = 1 if total_pages == 0 else max(1, min(total_pages, requested_page))
    show_badges = bool(state_value(component_state, "show_badges", True))
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
    try:
        notes = store.get_notes(filenames)
    except CorruptNotesError as exc:
        notes = {name: {"current": "", "updated_at": "", "history": []} for name in filenames}
        st.error(str(exc))

    samples = []
    for entry, preview in zip(entries, previews):
        samples.append(
            {
                "name": entry.name,
                "kind": preview.kind,
                "source": preview.source,
                "notice": preview.notice,
                "error": preview.error,
                "labels": labels_by_sample.get(entry.name, []),
                "has_note": entry.name in noted,
                "note": notes.get(entry.name, {}),
            }
        )

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
        },
    )


if __name__ == "__main__":
    main(parse_args(sys.argv[1:]))
