from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright


PROJECT_ROOT = Path(__file__).parents[1]


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.mark.e2e
def test_browser_label_note_layout_badges_and_keyboard(tmp_path: Path):
    data_dir = tmp_path / "images"
    data_dir.mkdir()
    for source in sorted((PROJECT_ROOT / "sample_data" / "image").iterdir()):
        if source.is_file():
            shutil.copy2(source, data_dir / source.name)

    port = free_port()
    command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(PROJECT_ROOT / "app.py"),
        "--server.headless",
        "true",
        "--server.address",
        "127.0.0.1",
        "--server.port",
        str(port),
        "--",
        "--mode",
        "image",
        "--data-dir",
        str(data_dir),
    ]
    process = subprocess.Popen(
        command,
        cwd=PROJECT_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
    )
    url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(f"{url}/_stcore/health", timeout=1) as response:
                    if response.status == 200:
                        break
            except OSError:
                time.sleep(0.2)
        else:
            raise AssertionError("Streamlit server did not become healthy")

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.goto(url, wait_until="networkidle")
            expect(page.get_by_text("实验结果展示与标注", exact=True).first).to_be_visible(timeout=30_000)
            cards = page.locator(".sample-card")
            expect(cards).to_have_count(6, timeout=30_000)
            expect(page.get_by_text("图片模式", exact=True)).to_be_visible()
            expect(page.get_by_text("30 个样本", exact=True)).to_be_visible()
            expect(page.get_by_text("单样本上限", exact=True)).to_have_count(0)
            expect(page.locator(".status-detail")).to_have_count(0)

            def open_label_card(name: str):
                card = page.locator("details", has_text=name).first
                if card.get_attribute("open") is None:
                    card.locator("summary").click()
                return card

            page.get_by_role("button", name="＋ 新建标签", exact=True).click()
            page.get_by_label("标签名称").fill("样例标签一")
            page.get_by_role("button", name="创建", exact=True).click()
            expect(page.locator(".active-label")).to_have_text("当前标签：样例标签一", timeout=30_000)

            page.get_by_role("button", name="＋ 新建标签", exact=True).click()
            page.get_by_label("标签名称").fill("样例标签二")
            page.get_by_role("button", name="创建", exact=True).click()
            expect(page.locator(".active-label")).to_have_text("当前标签：样例标签二", timeout=30_000)

            first = page.locator(".sample-card").first
            first.click()
            second_label_path = data_dir / "label" / "样例标签二.txt"
            save_deadline = time.monotonic() + 10
            while time.monotonic() < save_deadline:
                if second_label_path.exists() and len(second_label_path.read_text(encoding="utf-8").splitlines()) > 1:
                    break
                time.sleep(0.05)
            else:
                raise AssertionError("batched label operation was not persisted")

            first_card = open_label_card("样例标签一")
            first_card.get_by_role("button", name="设为当前标签", exact=True).click()
            expect(page.locator(".active-label")).to_have_text("当前标签：样例标签一", timeout=10_000)
            first = page.locator(".sample-card").first
            first.click()
            expect(first.locator(".badge")).to_have_count(2)
            assert first.locator(".badge").evaluate_all("nodes => nodes.map(node => node.title)") == ["样例标签一", "样例标签二"]

            second_card = open_label_card("样例标签二")
            second_card.get_by_role("button", name="设为当前标签", exact=True).click()
            expect(page.locator(".active-label")).to_have_text("当前标签：样例标签二", timeout=10_000)

            second_card = open_label_card("样例标签二")
            second_card.get_by_label("新名称").fill("样例标签二已修改")
            second_card.get_by_role("button", name="重命名", exact=True).click()
            expect(page.locator(".active-label")).to_have_text("当前标签：样例标签二已修改", timeout=10_000)

            rapid = page.locator(".sample-card").evaluate_all(
                """cards => {
                    const started = performance.now();
                    cards.slice(1, 5).forEach(card => card.click());
                    return {
                        elapsed: performance.now() - started,
                        visible: cards.slice(1, 5).every(card => card.querySelectorAll('.badge').length === 1),
                    };
                }"""
            )
            assert rapid["visible"] is True
            assert rapid["elapsed"] < 100
            renamed_path = data_dir / "label" / "样例标签二已修改.txt"
            save_deadline = time.monotonic() + 10
            while time.monotonic() < save_deadline:
                if renamed_path.exists() and len(renamed_path.read_text(encoding="utf-8").splitlines()) >= 6:
                    break
                time.sleep(0.05)
            else:
                raise AssertionError("rapid batched labels were not persisted")

            first = page.locator(".sample-card").first
            first.hover()
            first.locator(".view-button").click()
            viewer = page.locator(".viewer-dialog")
            expect(viewer).to_be_visible()
            viewer.get_by_role("button", name="放大").click()
            expect(viewer.locator('[data-role="zoom-value"]')).to_have_text("125%")
            viewer.get_by_role("button", name="关闭").click()

            badge_colors = first.locator(".badge").evaluate_all("nodes => nodes.map(node => getComputedStyle(node).backgroundColor)")
            page.locator(".toolbar label", has_text="标记样式").locator("select").select_option("border")
            expect(first.locator(".badge")).to_have_count(0)
            shadow = first.evaluate("card => card.style.boxShadow")
            assert shadow.index(badge_colors[0]) < shadow.index(badge_colors[1])
            page.locator(".toolbar label", has_text="标记样式").locator("select").select_option("badge")
            expect(first.locator(".badge")).to_have_count(2)

            page.locator(".sample-card").first.click(button="right")
            page.get_by_role("button", name="📝 单个样本备注").click()
            note = page.locator(".note-dialog textarea")
            expect(note).to_be_visible()
            note.fill("浏览器端备注测试")
            page.locator(".note-dialog").get_by_role("button", name="保存").click()
            expect(page.locator(".sample-card").first.locator(".note-indicator")).to_be_visible(timeout=10_000)

            page.locator(".sample-card").first.click(button="right")
            page.get_by_role("button", name="📝 单个样本备注").click()
            expect(page.locator(".history-entry")).to_contain_text("浏览器端备注测试")
            page.locator(".note-dialog").get_by_role("button", name="取消").click()

            badge_toggle = page.locator(".toolbar label", has_text="显示标记").locator("input")
            badge_toggle.uncheck()
            expect(page.locator(".sample-card").first.locator(".badge")).to_have_count(0)

            rows = page.locator(".toolbar label", has_text="行").locator("input")
            rows.fill("12")
            rows.press("Tab")
            expect(rows).to_have_value("12", timeout=10_000)
            expect(page.locator(".sample-card")).to_have_count(30)
            rows.fill("2")
            rows.press("Tab")
            expect(page.locator(".toolbar label", has_text="行").locator("input")).to_have_value("2", timeout=10_000)
            expect(page.locator(".sample-card")).to_have_count(6, timeout=10_000)

            cols = page.locator(".toolbar label", has_text="列").locator("input")
            cols.fill("1")
            cols.press("Tab")
            expect(page.locator(".toolbar")).to_contain_text("/ 15 页", timeout=10_000)
            page.locator("body").press("d")
            page_input = page.locator(".toolbar label", has_text="页码").locator("input")
            expect(page_input).to_have_value("2", timeout=10_000)
            expect(page.locator(".sample-card")).to_have_count(2)
            page.get_by_role("button", name="↻ 刷新", exact=True).click()
            expect(page_input).to_have_value("2", timeout=10_000)
            expect(page.locator(".sample-card")).to_have_count(2)

            renamed_card = open_label_card("样例标签二已修改")
            renamed_card.get_by_text("确认删除此标签", exact=True).click()
            delete_button = renamed_card.get_by_role("button", name="删除标签", exact=True)
            expect(delete_button).to_be_enabled(timeout=10_000)
            delete_button.click()
            expect(page.locator("details", has_text="样例标签二已修改")).to_have_count(0)
            browser.close()
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
