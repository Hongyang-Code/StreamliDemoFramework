from __future__ import annotations

import os
import hashlib
import json
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
        "--title",
        "自动化测试标题",
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
            expect(page.get_by_text("自动化测试标题", exact=True).first).to_be_visible(timeout=30_000)
            expect(page).to_have_title("自动化测试标题")
            cards = page.locator(".sample-card")
            expect(cards).to_have_count(6, timeout=30_000)
            expect(page.get_by_text("图片模式", exact=True)).to_be_visible()
            expect(page.get_by_text("30 个样本", exact=True)).to_be_visible()
            expect(page.get_by_text("单样本上限", exact=True)).to_have_count(0)
            expect(page.locator(".status-detail")).to_have_count(0)

            def label_card(name: str):
                token = hashlib.sha1(name.encode("utf-8")).hexdigest()[:10]
                return page.locator(f".st-key-label_card_{token}")

            page.get_by_role("button", name="＋ 新建标签", exact=True).click()
            page.get_by_label("标签名称").fill("样例标签一")
            page.get_by_label("标签名称").press("Enter")
            expect(page.locator(".active-label")).to_have_text("当前标签：样例标签一", timeout=30_000)
            first_color = (data_dir / "label" / "样例标签一.txt").read_text(encoding="utf-8").splitlines()[0]

            page.get_by_role("button", name="＋ 新建标签", exact=True).click()
            page.get_by_label("标签名称").fill("样例标签二")
            page.get_by_role("button", name="创建", exact=True).click()
            expect(page.locator(".active-label")).to_have_text("当前标签：样例标签二", timeout=30_000)
            second_color = (data_dir / "label" / "样例标签二.txt").read_text(encoding="utf-8").splitlines()[0]
            assert first_color != second_color

            first_card = label_card("样例标签一")
            second_card = label_card("样例标签二")
            page.locator(".label-manager").evaluate(
                """root => {
                    root._orderHistory = [];
                    root._orderObserver = new MutationObserver(() => {
                        root._orderHistory.push([...root.querySelectorAll('.label-card')].map(card => card.dataset.label));
                    });
                    root._orderObserver.observe(root, {childList: true});
                }"""
            )
            source_box = second_card.get_by_role("button", name="样例标签二", exact=True).bounding_box()
            target_box = first_card.bounding_box()
            assert source_box and target_box
            page.mouse.move(source_box["x"] + 15, source_box["y"] + source_box["height"] / 2)
            page.mouse.down()
            page.wait_for_timeout(380)
            page.mouse.move(target_box["x"] + 15, target_box["y"] + 2, steps=5)
            page.mouse.up()
            expect(page.locator(".label-card").first).to_have_attribute("data-label", "样例标签二")
            order_deadline = time.monotonic() + 10
            while time.monotonic() < order_deadline:
                order = json.loads((data_dir / "label" / "label_settings.json").read_text(encoding="utf-8"))["order"]
                if order == ["样例标签二", "样例标签一"]:
                    break
                time.sleep(0.05)
            else:
                raise AssertionError("dragged label order was not persisted")
            page.wait_for_timeout(300)
            order_history = page.locator(".label-manager").evaluate("root => root._orderHistory")
            first_new_order = order_history.index(["样例标签二", "样例标签一"])
            assert ["样例标签一", "样例标签二"] not in order_history[first_new_order + 1 :]

            label_boxes = page.locator('[class*="st-key-label_card_"]').evaluate_all(
                "cards => cards.map(card => ({top: card.getBoundingClientRect().top, bottom: card.getBoundingClientRect().bottom}))"
            )
            assert label_boxes[1]["top"] - label_boxes[0]["bottom"] <= 12
            guide = page.locator(".st-key-sidebar_guide")
            guide_box = guide.evaluate(
                "element => ({bottom: element.getBoundingClientRect().bottom, viewport: window.innerHeight})"
            )
            assert guide_box["viewport"] - guide_box["bottom"] <= 40
            guide.get_by_test_id("stTooltipHoverTarget").hover()
            expect(
                page.get_by_text(
                    "选择标签后左键样本进行标记；右键可添加单样本备注；A / D 翻页。点击打开完整操作指南。",
                    exact=True,
                )
            ).to_be_visible()

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

            first_card = label_card("样例标签一")
            first_card.get_by_role("button", name="编辑", exact=True).click()
            first_card.get_by_label("标记形式").select_option("border")
            first_card.get_by_role("button", name="保存设置", exact=True).click()
            expect(first_card.get_by_label("标记形式")).to_be_hidden()
            first_card.get_by_role("button", name="样例标签一", exact=True).click()
            expect(page.locator(".active-label")).to_have_text("当前标签：样例标签一", timeout=10_000)
            first = page.locator(".sample-card").first
            first.click()
            expect(first.locator(".badge")).to_have_count(1)
            expect(first.locator(".frame-rings")).to_have_count(1)
            expect(first.locator(".frame-rings")).to_be_visible()
            assert first.locator(".badge").evaluate_all("nodes => nodes.map(node => node.title)") == ["样例标签二"]

            second_card = label_card("样例标签二")
            second_card.get_by_role("button", name="样例标签二", exact=True).click()
            expect(page.locator(".active-label")).to_have_text("当前标签：样例标签二", timeout=10_000)

            second_card = label_card("样例标签二")
            second_card.get_by_role("button", name="编辑", exact=True).click()
            second_card.get_by_label("新名称").fill("样例标签二已修改")
            second_card.get_by_label("新名称").press("Enter")
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
            expect(viewer.get_by_role("button", name="上一张图片")).to_be_disabled()
            viewer.get_by_role("button", name="放大").click()
            expect(viewer.locator('[data-role="zoom-value"]')).to_have_text("125%")
            viewer.get_by_role("button", name="下一张图片").click()
            expect(viewer.locator('[data-role="viewer-position"]')).to_have_text("2 / 30")
            expect(viewer.locator('[data-role="zoom-value"]')).to_have_text("100%")
            page.keyboard.press("ArrowLeft")
            expect(viewer.locator('[data-role="viewer-position"]')).to_have_text("1 / 30")
            for _ in range(5):
                page.keyboard.press("ArrowRight")
            expect(viewer.locator('[data-role="viewer-position"]')).to_have_text("6 / 30")
            viewer.get_by_role("button", name="下一张图片").click()
            expect(page.locator(".toolbar label", has_text="页码").locator("input")).to_have_value("2", timeout=30_000)
            expect(viewer).to_be_visible()
            expect(viewer.locator('[data-role="viewer-position"]')).to_have_text("7 / 30", timeout=30_000)
            viewer.get_by_role("button", name="上一张图片").click()
            expect(page.locator(".toolbar label", has_text="页码").locator("input")).to_have_value("1", timeout=30_000)
            expect(viewer.locator('[data-role="viewer-position"]')).to_have_text("6 / 30", timeout=30_000)
            viewer.get_by_role("button", name="关闭").click()

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
            expect(page.locator(".sample-card").first.locator(".frame-rings")).to_have_count(0)

            rows = page.locator(".toolbar label", has_text="行").locator("input")
            rows.fill("12")
            rows.press("Tab")
            expect(rows).to_have_value("12", timeout=10_000)
            expect(page.locator(".sample-card")).to_have_count(30)
            grid_size = page.locator(".sample-grid").evaluate(
                "grid => ({clientHeight: grid.clientHeight, scrollHeight: grid.scrollHeight})"
            )
            assert grid_size["scrollHeight"] <= grid_size["clientHeight"] + 1
            main_size = page.locator('[data-testid="stMain"]').evaluate(
                "main => ({clientHeight: main.clientHeight, scrollHeight: main.scrollHeight})"
            )
            assert main_size["scrollHeight"] <= main_size["clientHeight"] + 1
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

            page.reload(wait_until="networkidle")
            expect(page.locator(".toolbar label", has_text="行").locator("input")).to_have_value("2", timeout=30_000)
            expect(page.locator(".toolbar label", has_text="列").locator("input")).to_have_value("1")
            expect(page.locator(".toolbar label", has_text="页码").locator("input")).to_have_value("2")
            expect(page.locator(".toolbar label", has_text="显示标记").locator("input")).not_to_be_checked()
            expect(page.locator(".sample-card")).to_have_count(2)
            assert "grid_rows=2" in page.url
            assert "grid_cols=1" in page.url
            assert "grid_page=2" in page.url
            assert "grid_marks=0" in page.url

            page.set_viewport_size({"width": 1280, "height": 650})
            page.wait_for_timeout(300)
            responsive_main = page.locator('[data-testid="stMain"]').evaluate(
                "main => ({clientHeight: main.clientHeight, scrollHeight: main.scrollHeight})"
            )
            responsive_grid = page.locator(".sample-app").evaluate(
                "grid => ({bottom: grid.getBoundingClientRect().bottom, viewport: window.innerHeight})"
            )
            assert responsive_main["scrollHeight"] <= responsive_main["clientHeight"] + 1
            assert responsive_grid["bottom"] <= responsive_grid["viewport"]
            page.set_viewport_size({"width": 1440, "height": 1000})
            page.wait_for_timeout(300)

            renamed_card = label_card("样例标签二已修改")
            renamed_card.get_by_role("button", name="删除", exact=True).click()
            expect(renamed_card).to_have_count(0)
            expect(page.locator(".toolbar label", has_text="行").locator("input")).to_have_value("2")
            expect(page.locator(".toolbar label", has_text="列").locator("input")).to_have_value("1")
            expect(page.locator(".toolbar label", has_text="页码").locator("input")).to_have_value("2")
            expect(page.locator(".toolbar")).to_contain_text("/ 15 页")
            expect(page.locator(".sample-card")).to_have_count(2)
            page.get_by_role("button", name="＋ 新建标签", exact=True).click()
            page.get_by_label("标签名称").fill("回收颜色测试")
            page.get_by_role("button", name="创建", exact=True).click()
            recycled_path = data_dir / "label" / "回收颜色测试.txt"
            recycled_deadline = time.monotonic() + 10
            while time.monotonic() < recycled_deadline and not recycled_path.exists():
                time.sleep(0.05)
            assert recycled_path.exists()
            recycled_color = recycled_path.read_text(encoding="utf-8").splitlines()[0]
            assert recycled_color == second_color
            label_card("回收颜色测试").get_by_role("button", name="删除", exact=True).click()
            expect(label_card("回收颜色测试")).to_have_count(0)

            page.locator(".st-key-sidebar_guide").get_by_test_id("stTooltipHoverTarget").get_by_test_id(
                "stPageLink-NavLink"
            ).click()
            expect(page.get_by_text("📖 操作指南", exact=True)).to_be_visible(timeout=20_000)
            page.get_by_role("tab", name="标签与标记", exact=True).click()
            expect(page.get_by_text("角标和外框可以混合使用", exact=True)).to_be_visible()
            browser.close()
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
