from pathlib import Path

import streamlit as st


PROJECT_ROOT = Path(__file__).parents[1]

st.set_page_config(page_title="操作指南 · 实验结果展示与标注", page_icon="📖", layout="wide")
st.markdown(
    """
    <style>
    [data-testid="stSidebarNav"] { display:none; }
    .block-container { max-width:1120px; padding-top:.8rem; padding-bottom:2rem; }
    .guide-card { padding:16px 18px; border:1px solid #DCE3ED; border-radius:14px; background:#F8FAFC; margin:8px 0 14px; }
    .demo-sample { position:relative; height:190px; border-radius:14px; overflow:hidden; background:linear-gradient(135deg,#DBEAFE,#F5D0FE); border:1px solid #CBD5E1; }
    .demo-name { position:absolute; left:0; right:0; bottom:0; padding:8px 10px; background:white; color:#172033; font-size:12px; font-weight:650; }
    .demo-badges { position:absolute; right:10px; bottom:40px; display:flex; gap:5px; padding:5px; border-radius:99px; background:#FFFFFFE8; }
    .demo-badges i { width:14px; height:14px; border:2px solid white; border-radius:50%; box-shadow:0 1px 3px #0005; }
    .demo-frame { position:absolute; inset:0; border-radius:13px; box-shadow:inset 0 0 0 4px #7C3AED,inset 0 0 0 8px #34D399; pointer-events:none; }
    kbd { padding:2px 7px; border:1px solid #CBD5E1; border-bottom-width:2px; border-radius:6px; background:white; font-family:inherit; }
    </style>
    """,
    unsafe_allow_html=True,
)

top_left, top_right = st.columns([5, 1])
with top_left:
    st.title("📖 操作指南")
    st.caption("图片、视频、文本结果查看与标注的完整使用说明")
with top_right:
    st.page_link("app.py", label="返回标注页面", icon="↩️", use_container_width=True)

st.info("最快上手：选择左侧标签 → 左键样本完成标记 → 右键添加单样本备注 → 使用 A / D 翻页。")

overview_tab, labels_tab, media_tab, data_tab = st.tabs(["快速上手", "标签与标记", "查看与备注", "数据与故障排查"])

with overview_tab:
    st.subheader("1. 启动一个演示")
    st.markdown(
        "复制 `examples/demo_scripts/` 中对应模态的脚本到 `demo_scripts/`，修改数据目录和端口后运行。"
        "输入目录只扫描一级文件，应用会自动创建其中的 `label/` 子目录。"
    )
    st.code("bash demo_scripts/image_demo.sh", language="bash")

    st.subheader("2. 完成一次标注")
    st.markdown(
        """
        1. 点击左侧某个彩色标签卡片，将它设为当前标签。
        2. 左键点击样本。角标或外框会立即出现，不需要等待保存完成。
        3. 再点一次同一样本，即可取消当前标签。
        4. 快速连续点击多个样本时，操作会在浏览器中立即显示，并合并写入标签文件。
        """
    )
    image_path = PROJECT_ROOT / "sample_data" / "image" / "彩色测试图.jpg"
    if image_path.exists():
        st.image(str(image_path), caption="仓库自带图片样例；实际页面会在卡片下方显示文件名。", width=620)

    st.subheader("3. 翻页与布局")
    st.markdown(
        "底栏可以修改行数、列数和页码。行列数不设上限，修改后网格、当前页切片和总页数立即重算。"
        "展示区域会跟随浏览器窗口的实际可视高度自动缩放，当前页中的所有行会等分剩余空间，"
        "因此切换大小显示器后也不需要上下滚动才能看完这一页。"
        "输入框和视频控件未聚焦时，可以按 <kbd>A</kbd> 上一页、<kbd>D</kbd> 下一页。",
        unsafe_allow_html=True,
    )

with labels_tab:
    st.subheader("标签卡片怎么使用")
    st.markdown(
        """
        - 点击标签名称：选中这个标签；选中的卡片会有彩色强调，并在名称前显示 `✓`。
        - 新建标签：填写名称后可以直接按 Enter 创建，无需再移动鼠标点击“创建”。
        - 点击“编辑”：打开该标签自己的颜色、标记形式和重命名设置；再次点击可关闭。
          完成修改后可以直接按 Enter 保存，与点击“保存设置”效果相同。
        - 点击“删除”：直接删除该标签及其 TXT 文件，请在点击前确认标签名称。
        - 长按标签卡片约 0.3 秒后上下拖动：调整标签顺序；角标与外框会采用新顺序，重新启动后仍保留。
        - 点击顶部“取消当前标签”：进入只查看、不进行左键标记的状态。
        """
    )

    st.subheader("角标和外框可以混合使用")
    badge_col, border_col = st.columns(2)
    with badge_col:
        st.markdown("**角标标签示例**")
        st.markdown(
            """
            <div class="demo-sample">
              <div class="demo-badges"><i style="background:#7C3AED"></i><i style="background:#34D399"></i></div>
              <div class="demo-name">sample_badges.jpg</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.caption("角标位于右下角；多个角标从左到右按标签列表顺序排列。")
    with border_col:
        st.markdown("**外框标签示例**")
        st.markdown(
            """
            <div class="demo-sample">
              <div class="demo-frame"></div>
              <div class="demo-name">sample_frames.jpg</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.caption("外框覆盖在样本卡片最上层；多个外框从内向外按标签列表顺序排列。")

    st.markdown(
        '<div class="guide-card"><b>顺序规则</b><br>标记的显示顺序只取决于左侧标签列表顺序，和点击先后无关。'
        '一个标签可以使用角标，另一个标签同时使用外框；底栏“显示标记”会一起隐藏或恢复两种视觉标记。</div>',
        unsafe_allow_html=True,
    )

with media_tab:
    st.subheader("图片：单独查看与缩放")
    st.markdown(
        "将鼠标移到图片卡片上，点击右上角 `⛶`；也可以右键选择“单独查看”。"
        "查看窗口支持加减按钮、鼠标滚轮缩放、拖拽平移和恢复 100%，缩放范围为 25%～800%。"
        "使用窗口两侧按钮或键盘左右方向键可以连续切换整个数据集的前后图片；越过当前页边界时，"
        "底层网格会自动切换到上一页或下一页。切换后自动恢复 100% 并居中，只有数据集首尾图片不能继续越界。"
    )

    st.subheader("视频与文本")
    st.markdown(
        "视频卡片使用浏览器原生播放控件；文本卡片保留换行并可在卡片内部滚动。"
        "大视频会按预算转码，大文本只读取预览范围，不会把整个超大文件载入内存。"
    )

    st.subheader("单样本备注")
    st.markdown(
        "右键任意样本，选择“单个样本备注”。保存和清空都会记录 UTC 时间及修订历史。"
        "备注统一保存在 `<数据目录>/label/sample_notes.json`，已有备注的样本左下角显示 📝。"
    )

with data_tab:
    st.subheader("自定义标题")
    st.markdown(
        "在启动脚本的应用参数中加入 `--title \"我的实验名称\"`，即可同时修改页面大标题和浏览器标签页标题；"
        "不传时使用默认标题“实验结果展示与标注”。"
    )

    st.subheader("刷新与新增文件")
    st.markdown(
        "向输入目录一级加入新文件后，点击底栏“刷新”。应用会重新扫描文件并保持当前页；"
        "只有当前页超过刷新后的总页数时，才调整到最后一个有效页面。浏览器自身刷新、断线重连或服务热重载时，"
        "行数、列数、当前页和标记显示状态会从页面地址恢复，不会返回默认布局。"
    )

    st.subheader("标签文件")
    st.code("#7C3AED\nsample_a.jpg\nsample_b.jpg", language="text")
    st.markdown(
        "每个标签仍对应一个可人工查看的 TXT。第一行是颜色，后续每行一个样本文件名。"
        "每个标签的角标/外框属性保存在 `label/label_settings.json`。不要在应用运行时同时用多个程序覆盖同一个文件。"
    )

    st.subheader("常见问题")
    st.markdown(
        """
        - **看不到文件：**确认模态与扩展名匹配、文件位于输入目录一级，然后点击“刷新”。
        - **看不到标记：**确认底栏“显示标记”已勾选，并确认样本确实属于至少一个标签。
        - **视频转码失败：**确认启动环境的 `PATH` 中能找到 `ffmpeg` 和 `ffprobe`。
        - **备注 JSON 损坏：**先备份并修复 JSON；应用会停止写入，不会用空内容覆盖原文件。
        - **标签设置 JSON 损坏：**备份并修复 `label_settings.json` 后再修改颜色或标记形式。
        """
    )

st.divider()
st.page_link("app.py", label="返回实验结果展示与标注", icon="↩️", use_container_width=True)
