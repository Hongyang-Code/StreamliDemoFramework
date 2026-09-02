from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import streamlit as st

from streamlit_demo.component import render_sample_grid
from streamlit_demo.config import AppConfig, parse_args
from streamlit_demo.index import DatasetIndex
from streamlit_demo.media import PreviewManager
from streamlit_demo.storage import CorruptNotesError, LabelStore, StorageError, stable_color


MODE_LABELS = {"image": "图片", "video": "视频", "text": "文本"}
DEFAULT_COLUMNS = {"image": 3, "video": 2, "text": 2}


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


def render_create_label_form(store: LabelStore) -> None:
    with st.container(border=True):
        st.caption("新建标签")
        with st.form("create_label_form", clear_on_submit=True):
            new_name = st.text_input("标签名称")
            new_color = st.color_picker("标签颜色", stable_color(new_name or "新标签"))
            cancel_col, create_col = st.columns(2)
            cancel = cancel_col.form_submit_button("取消", use_container_width=True)
            create = create_col.form_submit_button("创建", type="primary", use_container_width=True)
    if cancel:
        st.session_state["show_create_label_form"] = False
        st.rerun()
    if create:
        try:
            store.create_label(new_name, new_color)
            st.session_state["pending_active_label"] = new_name.strip()
            st.session_state["show_create_label_form"] = False
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
            st.toast("文件列表已刷新", icon="🔄")
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


def render_sidebar(store: LabelStore) -> dict[str, str] | None:
    with st.sidebar:
        st.header("标签管理")
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

        for name, color in labels.items():
            token = hashlib.sha1(name.encode("utf-8")).hexdigest()[:10]
            selected_css = f"border-color:{color}!important;box-shadow:0 0 0 1px {color}33!important;" if name == active else ""
            st.markdown(
                f"""
                <style>
                .st-key-label_card_{token} {{ padding:.18rem .28rem!important; margin-bottom:.35rem; {selected_css} }}
                .st-key-label_card_{token} [data-testid="stVerticalBlock"] {{ gap:.25rem; }}
                .st-key-select_{token} button {{ border:0!important; background:transparent!important; padding:.22rem .25rem!important; min-height:30px; text-align:left; }}
                .st-key-select_{token} button p {{ color:{color}!important; font-weight:750!important; }}
                .st-key-edit_{token} button, .st-key-delete_{token} button {{ padding:.22rem .32rem!important; min-height:30px; font-size:.72rem; }}
                </style>
                """,
                unsafe_allow_html=True,
            )
            with st.container(border=True, key=f"label_card_{token}"):
                name_col, edit_col, delete_col = st.columns([4.2, 2, 2], gap="small", vertical_alignment="center")
                if name_col.button(
                    f"{'✓  ' if name == active else ''}{name}",
                    key=f"select_{token}",
                    use_container_width=True,
                ):
                    st.session_state["active_label"] = name
                    st.rerun()
                if edit_col.button("编辑", key=f"edit_{token}", use_container_width=True):
                    st.session_state["editing_label"] = None if st.session_state.get("editing_label") == name else name
                    st.rerun()
                if delete_col.button("删除", key=f"delete_{token}", use_container_width=True):
                    try:
                        store.delete_label(name)
                        if name == active:
                            st.session_state["active_label"] = None
                        if st.session_state.get("editing_label") == name:
                            st.session_state["editing_label"] = None
                        st.rerun()
                    except StorageError as exc:
                        st.error(str(exc))

                if st.session_state.get("editing_label") == name:
                    st.caption("标签设置")
                    selected_color = st.color_picker("颜色", color, key=f"color_{token}")
                    selected_style_name = st.radio(
                        "标记形式",
                        ["角标", "外框"],
                        index=0 if label_styles.get(name, "badge") == "badge" else 1,
                        horizontal=True,
                        key=f"style_{token}",
                    )
                    if st.button("保存设置", key=f"save_settings_{token}", use_container_width=True, type="primary"):
                        try:
                            store.set_label_color(name, selected_color)
                            store.set_label_style(name, "badge" if selected_style_name == "角标" else "border")
                            st.session_state["editing_label"] = None
                            st.rerun()
                        except StorageError as exc:
                            st.error(str(exc))

                    with st.form(f"rename_form_{token}"):
                        rename_value = st.text_input("新名称", value=name)
                        rename = st.form_submit_button("重命名", use_container_width=True)
                    if rename:
                        if rename_value.strip() == name:
                            st.info("请输入一个不同的新名称")
                        else:
                            try:
                                store.rename_label(name, rename_value)
                                if name == active:
                                    st.session_state["pending_active_label"] = rename_value.strip()
                                st.session_state["editing_label"] = None
                                st.rerun()
                            except StorageError as exc:
                                st.error(str(exc))

        st.divider()
        st.page_link("pages/操作指南.py", label="打开操作指南", icon="📖", use_container_width=True)

    active = st.session_state.get("active_label")
    if active and active in labels:
        return {"name": active, "color": labels[active], "style": label_styles.get(active, "badge")}
    return None


def main(config: AppConfig) -> None:
    st.set_page_config(page_title="实验结果展示与标注", page_icon="🧭", layout="wide")
    st.markdown(
        """
        <style>
        .block-container { max-width: 100%; padding-top: 2.35rem; padding-bottom: .5rem; }
        [data-testid="stSidebar"] { border-right: 1px solid rgba(148,163,184,.25); }
        [data-testid="stSidebarNav"] { display:none; }
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
    handle_component_action(component_state, store, dataset)

    active_label = render_sidebar(store)
    operation_error = st.session_state.pop("operation_error", None)
    if operation_error:
        st.error(f"上一次操作失败：{operation_error}")

    header_main, header_status = st.columns([6, 1.35], vertical_alignment="top")
    with header_main:
        st.title("实验结果展示与标注")
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

    default_cols = DEFAULT_COLUMNS[config.mode]
    cols = max(1, int(state_value(component_state, "cols", default_cols)))
    show_badges = bool(state_value(component_state, "show_badges", True))
    entries = dataset.entries
    rows = max(1, (len(entries) + cols - 1) // cols)

    manager = get_preview_manager(str(config.data_dir), config.preview_cache_mb)
    with st.spinner("正在准备全部样本预览……", show_time=True):
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
    for entry, preview in zip(entries, previews):
        samples.append(
            {
                "name": entry.name,
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

    render_sample_grid(
        rows=rows,
        data={
            "samples": samples,
            "rows": rows,
            "cols": cols,
            "total_count": len(dataset.entries),
            "show_badges": show_badges,
            "active_label": active_label,
            "label_order": list(store.list_labels()),
        },
    )


if __name__ == "__main__":
    main(parse_args(sys.argv[1:]))
