from pathlib import Path

import pytest

from streamlit_demo.config import DEFAULT_TITLE, parse_args


PROJECT_ROOT = Path(__file__).parents[1]


def test_title_uses_default_and_accepts_custom_value(tmp_path: Path):
    default = parse_args(["--mode", "image", "--data-dir", str(tmp_path)])
    custom = parse_args(
        ["--mode", "image", "--data-dir", str(tmp_path), "--title", "  我的图片实验  "]
    )

    assert default.title == DEFAULT_TITLE
    assert custom.title == "我的图片实验"


@pytest.mark.parametrize("title", ["", "   ", "标题\n换行"])
def test_title_rejects_empty_or_control_characters(tmp_path: Path, title: str):
    with pytest.raises(SystemExit):
        parse_args(["--mode", "image", "--data-dir", str(tmp_path), "--title", title])


def test_demo_launchers_disable_source_watcher():
    config = (PROJECT_ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8")
    assert 'fileWatcherType = "none"' in config
    for mode in ("image", "video", "text"):
        script = (PROJECT_ROOT / "examples" / "demo_scripts" / f"{mode}_demo.sh").read_text(encoding="utf-8")
        assert "--server.fileWatcherType none" in script
