# Streamlit 多模态实验结果展示与标注框架

一个面向实验结果检查、筛选和备注的本地 Web 工具。项目使用 Streamlit 1.62 构建，支持图片、视频和文本三种独立模式，并针对大型目录、快速连续标注和大文件预览进行了优化。

## 功能

- 图片、视频、文本三种启动模式；每个进程只加载一种模态。
- 输入目录只需配置一次，程序自动创建 `<数据目录>/label/`。
- 标签兼容旧格式：每个标签一个 TXT，第一行颜色，后续每行一个文件名。
- 自动修复空标签文件、缺少颜色或颜色格式不合法的旧标签文件。
- 多标签使用样本右下角彩色圆形角标展示，可一键隐藏。
- 左键即时标记；前端先响应，后端采用幂等目标状态和原子写入。
- 右键样本打开“单个样本备注”；当前备注和完整历史集中保存到一个 JSON。
- A/D 键翻页，行列变化后立即更新当前页和总页数。
- 大图片自动缩放压缩、大视频自动转码、超大文本按上限截断。
- 只向浏览器发送当前页，原始媒体不进入无界内存缓存。

## 安装

建议使用 Python 3.10 或更新版本：

```bash
cd /data4/lhy/project/StramlitDemoFramework
python -m pip install -r requirements.txt
```

视频模式还需要系统可以找到 `ffmpeg` 和 `ffprobe`：

```bash
ffmpeg -version
ffprobe -version
```

如果缺少，需先通过服务器的软件环境或 Conda 安装 ffmpeg。图片和文本模式不依赖 ffmpeg。

## 一条 Bash 命令启动

`demo_scripts/` 专门保存各台服务器的私有配置，Git 会忽略其中脚本。先复制模板：

```bash
cp examples/demo_scripts/image_demo.sh demo_scripts/my_image_demo.sh
```

修改其中的端口和数据目录后，无论当前终端在哪个目录，都可以直接运行：

```bash
bash /data4/lhy/project/StramlitDemoFramework/demo_scripts/my_image_demo.sh
```

模板包含：

- `examples/demo_scripts/image_demo.sh`：图片样例，默认端口 10081。
- `examples/demo_scripts/video_demo.sh`：视频样例，默认端口 10082。
- `examples/demo_scripts/text_demo.sh`：文本样例，默认端口 10083。

也可以直接启动自己的数据：

```bash
python -m streamlit run app.py \
  --server.address 0.0.0.0 \
  --server.port 10081 \
  -- \
  --mode image \
  --data-dir /absolute/path/to/flat/data
```

注意：Streamlit 参数必须写在 `--` 前，应用参数必须写在 `--` 后。

## 应用参数

| 参数 | 必填 | 说明 |
|---|---:|---|
| `--mode image\|video\|text` | 是 | 当前进程的模态 |
| `--data-dir PATH` | 是 | 所有输入文件平铺所在的一级目录 |
| `--preview-limit-mb N` | 否 | 单样本预览上限；图片 8、视频 32、文本 1 MB |
| `--page-payload-limit-mb N` | 否 | 当前页总预览预算，默认 128 MB |
| `--preview-cache-mb N` | 否 | `/tmp` 磁盘预览缓存上限，默认 2048 MB |

输入目录可以包含有效的文件软链接。程序不递归子目录，并忽略自动创建的 `label/`。

## 页面操作

1. 在右侧创建并选择一个标签。
2. 左键点击样本，立即添加或取消当前标签。
3. 右键点击样本，选择“单个样本备注”。
4. 使用 A/D 或底部按钮翻页。
5. 修改底部行数、列数后，网格和总页数会立即重算。
6. 取消“显示角标”可临时隐藏彩色标签，不会删除数据。

在输入框、备注框或视频控件中操作时，A/D 不会触发翻页。

## 标签与备注格式

一个标签对应一个 TXT：

```text
#2F80ED
sample_a.jpg
sample_b.jpg
```

如果第一行不是合法的 `#RRGGBB`，程序会把原内容全部保留为文件名，并根据标签名生成稳定颜色插入第一行。修复和所有写入都使用文件锁、临时文件和原子替换。

所有单样本备注集中保存为 `label/sample_notes.json`：

```json
{
  "version": 1,
  "samples": {
    "sample_a.jpg": {
      "current": "当前备注",
      "updated_at": "2026-09-02T08:00:00Z",
      "history": [
        {
          "text": "当前备注",
          "updated_at": "2026-09-02T08:00:00Z",
          "action": "save"
        }
      ]
    }
  }
}
```

`label/.label_index.sqlite3` 是可删除、可自动重建的查询索引，不是权威数据。TXT 和 `sample_notes.json` 才是需要备份的数据。

如果备注 JSON 已损坏，程序会显示错误并停止备注写入，绝不会静默覆盖原文件。

## 大文件与缓存

- 图片超过有效预算时，最长边缩放到 1920 像素以内并编码为 WebP；大型 GIF 使用首帧预览。
- 视频超过预算或浏览器不兼容时转为 720p 或 480p H.264/AAC MP4。
- 文本优先按 UTF-8 读取，失败后尝试 GB18030；超过上限只展示前部内容并提示截断。
- 当前页预算会平均分配给当前格子，防止增加行列后传输量失控。
- 转码结果保存在 `/tmp/streamlit-demo-framework/`，按最近使用时间淘汰；不会修改原始文件。
- 内存不保留访问过的所有页面，也不会缓存全量原始媒体。

## 参考数据

仓库提供三组可直接运行的数据：

- `sample_data/image/`
- `sample_data/video/`
- `sample_data/text/`

第一次运行任一模板时，对应目录下会自动创建 `label/`。这些运行时标签目录已被 Git 忽略。

## 测试

```bash
python -m pip install -r requirements-dev.txt
pytest
```

测试覆盖目录扫描、软链接、标签补色、标签 CRUD、并发写入、幂等标记、备注历史、损坏 JSON 保护、图片压缩、文本截断、缓存淘汰和前端组件关键交互契约。

## 常见问题

### 页面没有文件

确认启动模态与扩展名匹配，且文件位于输入目录一级。点击页面顶部“刷新文件”重新扫描。

### 视频显示转码失败

先确认 `ffmpeg`、`ffprobe` 在启动 Streamlit 的同一个 Python/Conda 环境的 `PATH` 中。某些专有编码也可能无法解码，错误会显示在对应卡片上。

### 手工修改标签后没有立即出现

标签文件签名会被检查并重建索引；也可以点击“刷新文件”或刷新浏览器触发重新加载。

### 备注文件损坏

先备份 `sample_notes.json`，修复为合法 UTF-8 JSON 后再继续。程序会保护损坏文件，不会用空内容覆盖。
