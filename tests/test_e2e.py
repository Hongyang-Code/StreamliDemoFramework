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
            expect(cards).to_have_count(3, timeout=30_000)

            page.get_by_label("标签名称").fill("待复核")
            page.get_by_role("button", name="创建", exact=True).click()
            expect(page.get_by_text("编辑标签：待复核", exact=True)).to_be_visible(timeout=30_000)
            expect(page.locator(".active-label")).to_have_text("当前标签：待复核", timeout=30_000)

            first = page.locator(".sample-card").first
            first.click()
            expect(first.locator(".badge")).to_have_count(1, timeout=10_000)
            label_path = data_dir / "label" / "待复核.txt"
            save_deadline = time.monotonic() + 10
            while time.monotonic() < save_deadline:
                if label_path.exists() and len(label_path.read_text(encoding="utf-8").splitlines()) > 1:
                    break
                time.sleep(0.05)
            else:
                raise AssertionError("optimistic badge appeared but the label was not persisted")
            expect(page.locator(".active-label")).to_have_text("当前标签：待复核", timeout=10_000)

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

            badge_toggle = page.locator(".toolbar label", has_text="显示角标").locator("input")
            badge_toggle.uncheck()
            expect(page.locator(".sample-card").first.locator(".badge")).to_have_count(0)

            cols = page.locator(".toolbar label", has_text="列").locator("input")
            cols.fill("1")
            cols.press("Tab")
            expect(page.locator(".toolbar")).to_contain_text("/ 2 页", timeout=10_000)
            page.locator("body").press("d")
            page_input = page.locator(".toolbar label", has_text="页码").locator("input")
            expect(page_input).to_have_value("2", timeout=10_000)
            expect(page.locator(".sample-card")).to_have_count(1)
            browser.close()
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
