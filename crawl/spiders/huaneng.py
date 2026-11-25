"""中国华能集团电子商务平台。招标专栏与非招标专栏动态列表采集。"""
import logging
import re
from urllib.parse import urljoin

from selenium.webdriver.common.by import By

from collect.sources.huaneng_ec.constants import DETAIL_BOX, DETAIL_URL, FILE_HINTS, HOME_URL, LIST_ROW
from collect.sources.huaneng_ec.source import SOURCE
from crawl.browser import browser_session
from crawl.files import files_settled, store_files
from crawl.identity import content_id, skip_as_duplicate
from crawl.job import JobResult, channels_for
from crawl.progress import mark
from crawl.record import build_notice
from crawl.runtime import Page
from crawl.text import html_to_text
from crawl.trace import file_note, notice_line
from crawl.window import judge_date, label_of, outside_detail, window_bounds

logger = logging.getLogger(SOURCE.script)


class HuanengSpider:
    spec = SOURCE

    def run(self, job, store, profile):
        result = JobResult()
        with browser_session(profile, self.spec.id) as driver:
            page = Page(driver, job.pace)
            logger.info("打开 %s %s，范围 %s", self.spec.name, profile.describe(), label_of(job.span))
            for channel in channels_for(self.spec, job):
                channel_id, label = channel.code, channel.name
                try:
                    note = self._crawl_channel(driver, page, job, store, channel_id, label, result)
                    result.channels.append(f"{label}:{note}")
                except Exception as exc:
                    result.failed += 1
                    result.error = str(exc)
                    result.channels.append(f"{label}:失败")
                    logger.exception("栏目失败 %s", label)
        result.note = "；".join(result.channels)
        if result.saved == 0 and result.error and result.failed:
            result.status = "failed"
        elif result.failed:
            result.status = "partial"
        return result

    def _crawl_channel(self, driver, page, job, store, channel_id, label, result):
        logger.info("栏目 %s", label)
        section_index = 1 if channel_id.startswith("fzb_") else 0
        menu_title = label.split("-", 1)[-1]
        driver.get(HOME_URL)
        page.human_gap("page")
        mark(store, self.spec, channel_id, label, 1, result, "正在切换专栏栏目")
        if not self._select_menu(driver, page, section_index, menu_title):
            mark(store, self.spec, channel_id, label, 1, result, "未找到对应菜单")
            return "未找到对应菜单"
        start, end = window_bounds(job.lookback_hours)
        page_no = 0
        while True:
            page_no += 1
            if page_no > job.max_pages:
                mark(store, self.spec, channel_id, label, page_no, result, "到达单次页数上限")
                return "到达单次页数上限"
            if job.page_end and page_no > job.page_end:
                mark(store, self.spec, channel_id, label, page_no, result, "到达指定页")
                return "到达指定页"
            rows = self._read_rows(driver, section_index)
            if not rows:
                mark(store, self.spec, channel_id, label, page_no, result, "页面上没有列表")
                return "页面上没有列表"
            mark(store, self.spec, channel_id, label, page_no, result, f"正在看第 {page_no} 页")
            for row in rows:
                decision = judge_date(row["date"], start, end)
                if decision == "stop":
                    mark(store, self.spec, channel_id, label, page_no, result, "日期已早于采集范围")
                    return "日期已早于采集范围"
                if decision != "take":
                    continue
                self._take_row(driver, page, job, store, channel_id, label, row, result, start, end)
            if not self._next_page(driver, page, section_index):
                mark(store, self.spec, channel_id, label, page_no, result, "没有下一页")
                return "没有下一页"

    def _select_menu(self, driver, page, section_index, menu_title):
        try:
            page.wait_css("div.menu")
        except Exception:
            return False
        menus = driver.find_elements(By.CSS_SELECTOR, "div.menu")
        if len(menus) <= section_index:
            return False
        target_menu = menus[section_index]
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", target_menu)
        page.pause(0.6, 1.4)
        for item in target_menu.find_elements(By.CSS_SELECTOR, "div.menu-item, div.menu-checked"):
            if menu_title in (item.text or "").strip():
                if "menu-checked" not in (item.get_attribute("class") or ""):
                    driver.execute_script("arguments[0].click();", item)
                    page.human_gap("page")
                return True
        return False

    def _read_rows(self, driver, section_index):
        tables = driver.find_elements(By.CSS_SELECTOR, "div.table")
        if len(tables) <= section_index:
            return []
        table = tables[section_index]
        rows = []
        for tr in table.find_elements(By.CSS_SELECTOR, LIST_ROW):
            cols = tr.find_elements(By.TAG_NAME, "td")
            if not cols:
                continue
            title = " ".join((cols[0].text or "").split())
            date_text = (cols[-1].text or "").strip()[:10]
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_text):
                match = re.search(r"\d{4}-\d{2}-\d{2}", tr.text or "")
                date_text = match.group(0) if match else ""
            row_id = (tr.get_attribute("data-row-key") or "").strip()
            if title and row_id:
                rows.append({
                    "title": title,
                    "date": date_text,
                    "site_id": row_id,
                    "url": DETAIL_URL.format(notice_id=row_id),
                })
        return rows

    def _next_page(self, driver, page, section_index):
        paginations = driver.find_elements(By.CSS_SELECTOR, "ul.ant-pagination")
        if len(paginations) <= section_index:
            return False
        try:
            next_li = paginations[section_index].find_element(By.CSS_SELECTOR, "li.ant-pagination-next")
            if "ant-pagination-disabled" in (next_li.get_attribute("class") or ""):
                return False
            btn = next_li.find_element(By.TAG_NAME, "a")
            driver.execute_script("arguments[0].click();", btn)
            page.human_gap("page")
            return True
        except Exception:
            return False

    def _take_row(self, driver, page, job, store, channel_id, label, row, result, start, end):
        title = row["title"]
        fingerprint = content_id(title)
        if not fingerprint:
            return
        existing = store.find_notice(self.spec.id, fingerprint, row["date"])
        if skip_as_duplicate(existing, fingerprint) and self._files_ready(store, existing, fingerprint, label, title, result):
            return
        main = driver.current_window_handle
        try:
            page.open_tab(row["url"])
            page.pause(1.0, 2.0)
            page.wait_css(DETAIL_BOX)
            page.glance()
            content = driver.find_element(By.CSS_SELECTOR, DETAIL_BOX)
            html = content.get_attribute("outerHTML") or ""
            text = html_to_text(html) or (content.text or "")
            if outside_detail(text, start, end, job.lookback_hours):
                result.skipped += 1
                logger.info("%s", notice_line(label, "跳过", title, "发布时间早于采集范围"))
                return
            urls = []
            seen = set()
            for anchor in content.find_elements(By.TAG_NAME, "a"):
                href = (anchor.get_attribute("href") or "").strip()
                if not href or href.startswith("javascript:") or href in seen:
                    continue
                if any(hint in href.lower() for hint in FILE_HINTS):
                    seen.add(href)
                    urls.append(urljoin(HOME_URL, href))
            doc = build_notice(
                crawler_id=self.spec.id,
                source=self.spec.source,
                title=title,
                url=driver.current_url,
                content_id=fingerprint,
                create_time=row["date"],
                channel_id=channel_id,
                channel_label=label,
                node_id=job.node_id,
                detail_text=text,
                detail_html=html,
                file_urls=urls,
                site_notice_id=row["site_id"],
                biz_net=self.spec.net_name,
                industry_hint="能源电力",
            )
            saved = store_files(self.spec.net, self.spec.id, fingerprint, urls)
            doc["files"] = saved
            doc["script"] = self.spec.script
            outcome = store.save_notice(self.spec.id, doc)
            if outcome == "duplicate":
                store.attach_files(self.spec.id, fingerprint, saved, urls)
                result.skipped += 1
                step = "补附件"
            else:
                result.saved += 1
                step = "已保存"
            logger.info("%s", notice_line(label, step, title, file_note(saved)))
        except Exception as exc:
            result.failed += 1
            logger.warning("%s", notice_line(label, "失败", title, str(exc)[:120]))
        finally:
            page.close_tab(main)
            page.human_gap("detail")

    def _files_ready(self, store, existing, fingerprint, label, title, result):
        if files_settled(existing):
            result.skipped += 1
            logger.info("%s", notice_line(label, "跳过", title, "附件已齐"))
            return True
        urls = [url for url in (existing or {}).get("fileUrl") or [] if url]
        if not urls:
            return False
        saved = store_files(self.spec.net, self.spec.id, fingerprint, urls, existing=(existing or {}).get("files"))
        store.attach_files(self.spec.id, fingerprint, saved, urls)
        result.skipped += 1
        logger.info("%s", notice_line(label, "补附件", title, file_note(saved)))
        return True
